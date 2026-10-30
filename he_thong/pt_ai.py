"""
AI cho module Phân tích video: chấm điểm nội dung thật (phụ đề / bản chép lời), phân loại, đề xuất,
và viết 3 bình luận khác nhau theo đúng nội dung video.

Hỗ trợ: Claude (Anthropic), OpenAI, Gemini – gọi thẳng qua HTTPS, không cần cài thêm thư viện.
Không có khóa API -> chấm điểm sơ bộ theo số liệu (không viết bình luận).
"""
import difflib
import json
import re
import urllib.error
import urllib.request

MANUAL = "Dán tay qua ChatGPT / Gemini / Claude (miễn phí)"
OLLAMA = "Ollama – AI chạy trên máy (miễn phí)"
NO_AI = "Không dùng AI (chấm sơ bộ)"
PROVIDERS = {
    OLLAMA: "qwen2.5:7b",
    "Claude – API (cần khóa)": "claude-sonnet-5-5",
    "OpenAI – API (cần khóa)": "gpt-4.1-mini",
    "Gemini – API (cần khóa)": "gemini-2.5-flash",
    NO_AI: "",
}
OLD_NAMES = {"Claude (Anthropic)": "Claude – API (cần khóa)", "OpenAI": "OpenAI – API (cần khóa)",
             "Gemini (Google)": "Gemini – API (cần khóa)"}
OLLAMA_URL = "http://127.0.0.1:11434"


OLLAMA_SETUP_URL = "https://ollama.com/download/OllamaSetup.exe"


def ollama_exe():
    """Đường dẫn Ollama đã cài trên Windows ('' nếu chưa cài)."""
    import os
    import shutil
    local = os.environ.get("LOCALAPPDATA", "")
    for p in (os.path.join(local, "Programs", "Ollama", "ollama.exe"),
              os.path.join(local, "Programs", "Ollama", "ollama app.exe")):
        if local and os.path.exists(p):
            return p
    return shutil.which("ollama") or ""


def ollama_models():
    with urllib.request.urlopen(f"{OLLAMA_URL}/api/tags", timeout=3) as r:
        return [m.get("name", "") for m in json.loads(r.read().decode("utf-8")).get("models", [])]


def install_ollama(model, log=print, progress=None, stop=None):
    """Cài Ollama + tải model ngay trong tool:
    1) chưa cài -> tải bộ cài chính thức từ ollama.com và mở bộ cài (bạn bấm Install), chờ cài xong;
    2) chưa chạy -> mở Ollama; 3) chưa có model -> tải model (hiện % tiến trình). Trả về True khi sẵn sàng."""
    import os
    import subprocess
    import tempfile
    import time
    progress = progress or (lambda done, total: None)
    stopped = lambda: bool(stop and stop())
    if os.name != "nt" and not ollama_exe():
        log("Máy này không phải Windows – hãy cài Ollama theo hướng dẫn ở ollama.com.")
        return False
    if not ollama_exe():
        path = os.path.join(tempfile.gettempdir(), "OllamaSetup.exe")
        log("Bước 1/3: tải bộ cài Ollama từ ollama.com (khoảng 1 GB, tùy mạng có thể mất vài phút)...")
        req = urllib.request.Request(OLLAMA_SETUP_URL, headers={"User-Agent": "Mozilla/5.0"})
        with urllib.request.urlopen(req, timeout=60) as r, open(path, "wb") as f:
            total = int(r.headers.get("Content-Length") or 0)
            done, last = 0, 0
            while True:
                if stopped():
                    log("Đã dừng tải.")
                    return False
                chunk = r.read(1024 * 512)
                if not chunk:
                    break
                f.write(chunk)
                done += len(chunk)
                progress(done, total or done)
                if total and done * 100 // total >= last + 10:
                    last = done * 100 // total
                    log(f"   đã tải {last}% ({done // 1048576} / {total // 1048576} MB)")
        log("Bước 1/3: mở bộ cài Ollama – hãy bấm Install trên cửa sổ cài đặt hiện ra...")
        try:
            subprocess.run([path], check=False)
        except Exception as e:
            log(f"❌ Không mở được bộ cài: {e}")
            return False
        for _ in range(120):   # bộ cài có thể chạy tiếp ở nền
            if ollama_exe():
                break
            time.sleep(1)
        if not ollama_exe():
            log("❌ Chưa thấy Ollama sau khi cài – hãy chạy lại bộ cài, hoặc tải tay ở ollama.com.")
            return False
        log("✅ Đã cài Ollama.")
    # bước 2: mở Ollama
    try:
        names = ollama_models()
    except Exception:
        log("Bước 2/3: mở Ollama...")
        exe = ollama_exe()
        try:
            args = [exe] if exe.endswith("app.exe") else [exe, "serve"]
            subprocess.Popen(args, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                             creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
        except Exception as e:
            log(f"❌ Không mở được Ollama: {e}")
            return False
        names = None
        for _ in range(40):
            time.sleep(1)
            try:
                names = ollama_models()
                break
            except Exception:
                continue
        if names is None:
            log("❌ Ollama chưa chạy được – hãy mở Ollama từ menu Start rồi bấm lại nút này.")
            return False
    want = model if ":" in model else model + ":latest"
    if any(n in (model, want) for n in names):
        log(f"✅ Ollama sẵn sàng, đã có model {model}.")
        progress(1, 1)
        return True
    # bước 3: tải model
    log(f"Bước 3/3: tải model {model} (khoảng 4–5 GB với qwen2.5:7b)...")
    req = urllib.request.Request(f"{OLLAMA_URL}/api/pull", data=json.dumps({"name": model, "stream": True}).encode(),
                                 headers={"Content-Type": "application/json"}, method="POST")
    last, status = -10, ""
    with urllib.request.urlopen(req, timeout=3600) as r:
        for line in r:
            if stopped():
                log("Đã dừng tải model (lần sau bấm lại sẽ tải tiếp).")
                return False
            try:
                d = json.loads(line.decode("utf-8"))
            except Exception:
                continue
            if d.get("error"):
                log(f"❌ Ollama báo lỗi: {d['error']}")
                return False
            if d.get("total") and d.get("completed") is not None:
                progress(d["completed"], d["total"])
                pct = d["completed"] * 100 // d["total"]
                if pct >= last + 10:
                    last = pct
                    log(f"   model: {pct}% ({d['completed'] // 1048576} / {d['total'] // 1048576} MB)")
            if d.get("status") and d["status"] != status and not d.get("total"):
                status = d["status"]
                log(f"   {status}")
    ok = any(n in (model, want) for n in ollama_models())
    log(f"✅ Đã tải xong model {model} – Ollama sẵn sàng." if ok else f"❌ Tải model {model} chưa xong.")
    return ok


def ollama_ready(model, log=print):
    """Kiểm tra Ollama trước khi chạy: chưa mở thì tự mở (nếu đã cài), chưa có model thì báo rõ.
    Trả về "" nếu sẵn sàng, ngược lại là câu hướng dẫn."""
    import os
    import subprocess
    import time

    def tags():
        with urllib.request.urlopen(f"{OLLAMA_URL}/api/tags", timeout=3) as r:
            return [m.get("name", "") for m in json.loads(r.read().decode("utf-8")).get("models", [])]
    try:
        names = tags()
    except Exception:
        local = os.environ.get("LOCALAPPDATA", "")
        exe = next((p for p in (os.path.join(local, "Programs", "Ollama", "ollama app.exe"),
                                os.path.join(local, "Programs", "Ollama", "ollama.exe")) if p and os.path.exists(p)), "")
        if not exe:
            return ("Máy chưa cài Ollama. Vào ollama.com → Download → Windows, cài xong mở cửa sổ lệnh (cmd) chạy: "
                    f"ollama pull {model}  – hoặc chọn AI = 'Dán tay qua ChatGPT / Gemini / Claude'.")
        log("Ollama chưa chạy – tool đang mở Ollama...")
        try:
            args = [exe] if exe.endswith("app.exe") else [exe, "serve"]
            subprocess.Popen(args, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                             creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
        except Exception as e:
            return f"Không mở được Ollama: {e}"
        names = None
        for _ in range(30):
            time.sleep(1)
            try:
                names = tags()
                break
            except Exception:
                continue
        if names is None:
            return "Đã mở Ollama nhưng chưa kết nối được – hãy mở Ollama từ menu Start rồi bấm START lại."
    want = model if ":" in model else model + ":latest"
    if not any(n == want or n == model for n in names):
        return (f"Ollama chưa có model '{model}'. Mở cửa sổ lệnh (cmd) và chạy 1 lần: ollama pull {model}  "
                f"(đang có: {', '.join(names) or 'chưa có model nào'})")
    return ""


def is_manual(provider):
    return provider == MANUAL


def needs_key(provider):
    return "(cần khóa)" in (provider or "")


def uses_ai(provider, key=""):
    """Có AI chấm điểm + viết bình luận không (dán tay / Ollama luôn có; API cần khóa)."""
    if provider in (MANUAL, OLLAMA):
        return True
    return needs_key(provider) and bool(key)
COMMENT_LANGS = {
    "English": "English",
    "Tagalog": "Tagalog (Filipino)",
    "Ilocano": "Ilocano (Iloko)",
    "Bisaya": "Bisaya (Cebuano)",
    "Vietnamese": "Vietnamese (Tiếng Việt)",
}
CATS = ("Hay", "Trung bình", "Chưa hay")
RECS = ("Like", "Bỏ qua", "Dislike")


class AIError(Exception):
    pass


# ============================================================ ngôn ngữ
_STOP = {
    "en": {"the", "and", "is", "of", "to", "in", "you", "my", "with", "for", "this", "that", "his", "her", "was",
           "story", "love", "full", "episode", "drama", "radio", "audio", "wife", "husband", "when", "who"},
    "tl": {"ang", "ng", "mga", "na", "ay", "ko", "mo", "siya", "hindi", "kwento", "ako", "ikaw", "niya", "kanyang",
           "asawa", "pag-ibig", "pagibig", "buhay", "lalaki", "babae", "nang", "naman", "talaga", "dahil"},
    "ilo": {"ti", "dagiti", "iti", "ken", "ni", "ket", "saan", "diak", "sika", "ayat", "istorya", "biag", "baknang",
            "agassawa", "nagbiag", "kenkuana", "isu", "daytoy", "dayta", "manong", "manang", "ilocano", "iloko"},
    "ceb": {"ug", "kay", "wala", "dili", "unsa", "kini", "karon", "gugma", "bisaya", "cebuano", "ako", "imong",
            "akong", "iyang", "niya", "gihapon", "kaayo", "asa", "nganong", "pamilya", "tawo", "nga"},
}
_VI_CHARS = set("ăâđêôơưạảấầẩẫậắằẳẵặẹẻẽếềểễệỉịọỏốồổỗộớờởỡợụủứừửữựỳỵỷỹ")
LANG_NAMES = {"en": "English", "tl": "Tagalog", "ilo": "Ilocano", "ceb": "Bisaya", "vi": "Vietnamese", "": "?"}


def tokens(text):
    return [t for t in re.findall(r"[\w'-]+", (text or "").lower()) if not t.isdigit()]


def detect_lang(text):
    """Đoán ngôn ngữ của tiêu đề / mô tả: en, tl, ilo, ceb, vi (hoặc '')."""
    t = (text or "").lower()
    if not t.strip():
        return ""
    vi = sum(1 for ch in t if ch in _VI_CHARS)
    if vi >= 2:
        return "vi"
    toks = tokens(t)
    if not toks:
        return ""
    score = {k: sum(1 for w in toks if w in s) for k, s in _STOP.items()}
    # từ đặc trưng (không trùng giữa các ngôn ngữ) nặng gấp đôi
    for k, s in _STOP.items():
        others = set().union(*(v for kk, v in _STOP.items() if kk != k))
        score[k] += sum(1 for w in toks if w in s and w not in others)
    best = max(score, key=score.get)
    return best if score[best] > 0 else ""


_TOPICAL = {"story", "love", "drama", "radio", "audio", "wife", "husband", "kwento", "pag-ibig", "pagibig", "buhay",
            "asawa", "lalaki", "babae", "istorya", "ayat", "biag", "baknang", "agassawa", "gugma", "pamilya", "tawo",
            "ilocano", "iloko", "bisaya", "cebuano", "manong", "manang"}
STOPWORDS = (set().union(*_STOP.values()) - _TOPICAL) | {
    "a", "an", "on", "at", "by", "it", "be", "are", "or", "as", "from", "new", "full", "part", "ep", "vs", "2024",
    "2025", "2026", "latest", "official", "video", "videos", "live", "best", "top", "how", "what", "why", "i", "me",
    "we", "our", "your", "he", "she", "they", "them", "their", "not", "no", "so", "but", "if", "all", "one", "two",
    "va", "và", "của", "là", "có", "cho", "những", "một", "các", "trong", "với", "được", "người", "khi"}


# từ quá chung – có mặt KHÔNG đủ để coi là cùng chủ đề (vd "drama" có ở cả phim Philippines lẫn kịch BBC)
GENERIC = {"drama", "dramas", "story", "stories", "episode", "episodes", "full", "series", "part", "parts", "audio",
           "movie", "movies", "film", "films", "love", "official", "complete", "collection", "season", "chapter",
           "channel", "watch", "listen", "night", "day", "time", "life", "man", "woman", "new", "old", "best", "hour",
           "hours", "free", "english", "subtitles", "sub", "hd", "4k", "music", "video"}


def _stem(w):
    w = w.lower().strip("'-")
    return w[:-1] if len(w) > 4 and w.endswith("s") and not w.endswith("ss") else w


def _content(text):
    """Từ mang nghĩa chủ đề (bỏ từ nối, từ quá chung, số)."""
    return {_stem(w) for w in tokens(text) if len(w) >= 3 and w not in STOPWORDS and w not in GENERIC}


def lang_scores(text):
    toks = tokens(text)
    return {k: sum(1 for w in toks if w in s and w not in GENERIC) for k, s in _STOP.items()}


def foreign_lang(text, target):
    """Tiêu đề có >= 2 từ đặc trưng của 1 ngôn ngữ KHÁC ngôn ngữ kênh mục tiêu (tiêu đề trộn tiếng) -> tên ngôn ngữ đó."""
    if not target:
        return ""
    if target != "vi" and sum(1 for ch in (text or "").lower() if ch in _VI_CHARS) >= 2:
        return "vi"
    sc = lang_scores(text)
    for k, n in sc.items():
        if k != target and n >= 2 and n >= sc.get(target, 0):
            return k
    return ""


def topic_profile(titles, user_keywords=()):
    """Hồ sơ chủ đề của kênh mục tiêu: từ vựng (đã bỏ từ chung chung), từ khóa mạnh, cụm từ khóa bạn điền."""
    cnt = {}
    for t in titles or []:
        for w in _content(t):
            cnt[w] = cnt.get(w, 0) + 1
    strong = [w for w, n in sorted(cnt.items(), key=lambda kv: -kv[1]) if n >= 2][:10]
    phrases = [" ".join(tokens(k)) for k in user_keywords if k and k.strip()]
    return {"vocab": set(cnt), "strong": set(strong), "phrases": [p for p in phrases if p]}


def topic_match(title, prof):
    """Video có ĐÚNG chủ đề kênh mục tiêu không. Trả về (True/False, lý do).
    Đạt khi: có cụm từ khóa bạn điền, HOẶC trùng >= 2 từ chủ đề với kênh, HOẶC trùng 1 từ khóa mạnh của kênh."""
    if not prof or not (prof.get("vocab") or prof.get("phrases")):
        return True, ""
    tl = " ".join(tokens(title))
    for p in prof.get("phrases") or []:
        if " " in p and re.search(rf"(?<![\w-]){re.escape(p)}(?![\w-])", tl):
            return True, f"có cụm '{p}'"
    own = _content(title)
    hit = own & prof.get("vocab", set())
    if len(hit) >= 2:
        return True, "trùng chủ đề: " + ", ".join(sorted(hit)[:4])
    strong = hit & prof.get("strong", set())
    if strong:
        return True, "trùng từ khóa chính: " + ", ".join(sorted(strong))
    single = [p for p in prof.get("phrases") or [] if " " not in p and p not in GENERIC]
    if any(_stem(p) in own for p in single):
        return True, "có từ khóa bạn điền"
    return False, ("chỉ trùng từ chung chung" if own or tokens(title) else "tiêu đề trống")


def keywords_from_titles(titles, top=15):
    """Từ khóa chủ đề rút ra từ tiêu đề video của kênh mục tiêu (từ xuất hiện nhiều, bỏ từ vô nghĩa)."""
    cnt = {}
    for t in titles:
        seen = set()
        for w in tokens(t):
            if len(w) < 3 or w in STOPWORDS or w in seen:
                continue
            seen.add(w)
            cnt[w] = cnt.get(w, 0) + 1
    ranked = sorted(cnt.items(), key=lambda kv: (-kv[1], kv[0]))
    return [w for w, n in ranked if n >= 2][:top] or [w for w, _ in ranked[:top]]


def relevance(text, keywords, title_weight_text=""):
    """Độ liên quan 0–100: tỉ lệ từ khóa chủ đề có mặt (tiêu đề tính gấp đôi)."""
    kws = [k.lower().strip() for k in keywords if k and k.strip()]
    if not kws:
        return 50.0
    body = " ".join(tokens(text))
    title = " ".join(tokens(title_weight_text))
    hit = 0.0
    for k in kws:
        kk = " ".join(tokens(k))
        if not kk:
            continue
        if re.search(rf"(?<![\w-]){re.escape(kk)}(?![\w-])", title):
            hit += 2
        elif re.search(rf"(?<![\w-]){re.escape(kk)}(?![\w-])", body):
            hit += 1
    # đủ 3 từ khóa ở tiêu đề (hoặc 6 ở mô tả) = 100
    return round(min(100.0, hit / 6 * 100), 1)


# ============================================================ gọi AI
SYSTEM = (
    "Bạn là biên tập viên nội dung YouTube khó tính và công bằng. Bạn chấm điểm video dựa trên NỘI DUNG THẬT "
    "(bản chép lời/phụ đề của đoạn được phân tích, tiêu đề, mô tả), không dựa vào lượt xem. "
    "Bạn chỉ trả về MỘT đối tượng JSON hợp lệ, không thêm chữ nào khác.")

PROMPT = """Phân tích video YouTube sau.

CHỦ ĐỀ KÊNH MỤC TIÊU (để đánh giá độ liên quan): {topic}
Tiêu đề: {title}
Kênh: {channel}
Thời lượng: {duration}
Lượt xem: {views} | Lượt thích: {likes}
Mô tả (rút gọn): {description}

NỘI DUNG ĐOẠN PHÂN TÍCH ({window}, nguồn: {source}):
{transcript}

VÍ DỤ TIÊU ĐỀ VIDEO CỦA KÊNH MỤC TIÊU (để so chủ đề, thể loại, ngôn ngữ):
{samples}

Yêu cầu:
0. "same_niche": so với các tiêu đề ví dụ ở trên, xét THỂ LOẠI RỘNG và NGÔN NGỮ (không cần cùng tác giả / cùng
   chương trình). Ví dụ kênh kịch truyền thanh tiếng Anh: radio drama, old time radio, audio drama, radio play,
   mystery theatre, truyện trinh thám đọc / diễn trên radio... đều là true.
   Chỉ false khi RÕ RÀNG khác: khác ngôn ngữ (vd phim bộ tiếng Philippines), hoặc khác hẳn dạng nội dung (phim truyền
   hình, phim điện ảnh, nhạc, tin tức, game, vlog...) dù có chữ "drama". Không chắc -> true.
   "niche_reason": 1 câu tiếng Việt vì sao.
1. "topic": chủ đề video, 2–4 từ (ví dụ "Love Story", "Radio Drama", "Audio Story").
2. "score": điểm chất lượng 0–100 theo: nội dung có giá trị / câu chuyện hấp dẫn, mạch lạc, chất lượng lời thoại /
   kể chuyện, tiêu đề đúng với nội dung (không giật tít), mức độ liên quan với chủ đề kênh mục tiêu.
3. "category": "Hay" (score >= 75), "Trung bình" (50–74) hoặc "Chưa hay" (< 50).
4. "summary": tóm tắt 3–4 câu bằng tiếng Việt CHÍNH NỘI DUNG của đoạn được phân tích (ai, chuyện gì xảy ra,
   tình tiết chính) – để người dùng biết AI đã thực sự "nghe" đoạn này.
   "reasons": 3–5 nhận định bằng tiếng Việt, MỖI nhận định phải kèm mốc thời gian [phút:giây] hoặc câu thoại cụ thể
   lấy từ nội dung (ví dụ: "[3:42] cảnh thẩm vấn căng, lời thoại tự nhiên"); nêu cả điểm mạnh lẫn điểm yếu
   (nhịp truyện, diễn xuất / giọng đọc, âm thanh, tính hấp dẫn, tiêu đề có đúng nội dung). KHÔNG viết câu chung chung
   kiểu "nội dung hấp dẫn", "chất lượng tốt" nếu không chỉ ra chi tiết.
   Điểm phải phân biệt rõ: video bình thường 55–70, chỉ video thật sự xuất sắc mới trên 85.
5. "recommendation": "Like" nếu Hay; "Bỏ qua" nếu Trung bình; với Chưa hay chỉ đề xuất "Dislike" khi có căn cứ
   rõ ràng (giật tít / sai sự thật / nội dung rác, sao chép, âm thanh hỏng...), nếu không thì "Bỏ qua".
6. "dislike_basis": căn cứ cụ thể nếu đề xuất Dislike, ngược lại để "".
7. "comments": đúng 3 bình luận KHÁC NHAU bằng {lang}, viết như người xem thật đã nghe đoạn này:
   - nhắc tới chi tiết cụ thể trong nội dung (nhân vật, tình tiết, câu nói...), mỗi bình luận một ý khác nhau;
   - video Hay: khen tự nhiên, chân thành; video Trung bình / Chưa hay: góp ý mang tính xây dựng, lịch sự;
   - 1–3 câu, không chèn link, không quảng cáo kênh nào, không hashtag, tối đa 1 emoji, không dùng câu sáo rỗng
     kiểu "Great video!", "Nice content";
   - không được giống các câu đã dùng trước đây: {avoid}
{no_transcript_note}
Trả về JSON:
{{"same_niche": true, "niche_reason": "...", "topic": "...", "summary": "...", "score": 0, "category": "...",
"reasons": ["..."], "recommendation": "...", "dislike_basis": "", "comments": ["...", "...", "..."]}}"""


def _post(url, body, headers, timeout=90, local=False):
    req = urllib.request.Request(url, data=json.dumps(body).encode("utf-8"),
                                 headers={"Content-Type": "application/json", **headers}, method="POST")
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            return json.loads(r.read().decode("utf-8"))
    except urllib.error.HTTPError as e:
        try:
            detail = e.read().decode("utf-8", "ignore")[:300]
        except Exception:
            detail = ""
        if local and e.code == 404:
            raise AIError(f"Ollama chưa có model này. Mở cửa sổ lệnh (cmd) và chạy: ollama pull "
                          f"{body.get('model', 'qwen2.5:7b')}")
        if e.code in (401, 403):
            raise AIError(f"Khóa API không hợp lệ hoặc không có quyền (HTTP {e.code}). {detail}")
        if e.code == 429:
            raise AIError(f"AI báo quá giới hạn / hết hạn mức (HTTP 429). {detail}")
        raise AIError(f"AI trả lỗi HTTP {e.code}: {detail}")
    except urllib.error.URLError as e:
        if local:
            raise AIError("Chưa mở Ollama trên máy. Cài Ollama (ollama.com), mở nó lên, rồi chạy 1 lần lệnh: "
                          "ollama pull qwen2.5:7b")
        raise AIError(f"Không kết nối được tới AI: {e.reason}")
    except TimeoutError:
        raise AIError("AI trả lời quá lâu (máy chạy Ollama có thể quá yếu – thử model nhỏ hơn, vd qwen2.5:3b).")


def call_llm(provider, model, key, system, prompt, max_tokens=1600):
    """Gọi 1 lần, trả về chữ AI trả lời."""
    if provider == OLLAMA:
        data = _post(f"{OLLAMA_URL}/api/chat",
                     {"model": model or PROVIDERS[OLLAMA], "stream": False, "format": "json",
                      "options": {"num_ctx": 8192, "temperature": 0.7},
                      "messages": [{"role": "system", "content": system}, {"role": "user", "content": prompt}]},
                     {}, timeout=600, local=True)
        return (data.get("message") or {}).get("content", "")
    if not key:
        raise AIError("Chưa nhập khóa API.")
    if provider.startswith("Claude"):
        data = _post("https://api.anthropic.com/v1/messages",
                     {"model": model, "max_tokens": max_tokens, "system": system,
                      "messages": [{"role": "user", "content": prompt}]},
                     {"x-api-key": key, "anthropic-version": "2023-06-01"})
        return "".join(b.get("text", "") for b in data.get("content", []) if b.get("type") == "text")
    if provider.startswith("OpenAI"):
        data = _post("https://api.openai.com/v1/chat/completions",
                     {"model": model, "max_completion_tokens": max_tokens, "response_format": {"type": "json_object"},
                      "messages": [{"role": "system", "content": system}, {"role": "user", "content": prompt}]},
                     {"Authorization": f"Bearer {key}"})
        return data["choices"][0]["message"]["content"]
    if provider.startswith("Gemini"):
        data = _post(f"https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent?key={key}",
                     {"systemInstruction": {"parts": [{"text": system}]},
                      "contents": [{"role": "user", "parts": [{"text": prompt}]}],
                      "generationConfig": {"responseMimeType": "application/json", "maxOutputTokens": max_tokens}},
                     {})
        parts = data.get("candidates", [{}])[0].get("content", {}).get("parts", [])
        return "".join(p.get("text", "") for p in parts)
    raise AIError(f"Không hỗ trợ nhà cung cấp AI: {provider}")


def parse_json(text):
    """Lấy đối tượng JSON trong câu trả lời (bỏ ```json ... ``` nếu có)."""
    t = (text or "").strip()
    t = re.sub(r"^```(?:json)?\s*|\s*```$", "", t)
    try:
        return json.loads(t)
    except Exception:
        m = re.search(r"\{.*\}", t, re.S)
        if m:
            try:
                return json.loads(m.group(0))
            except Exception:
                pass
    raise AIError("AI trả về nội dung không đúng dạng JSON.")


def normalize(res, has_transcript=True):
    """Ép kết quả về đúng quy tắc: điểm 0–100, phân loại theo điểm, Dislike chỉ khi có căn cứ."""
    try:
        score = int(round(float(res.get("score", 0))))
    except Exception:
        score = 0
    score = max(0, min(100, score))
    cat = "Hay" if score >= 75 else "Trung bình" if score >= 50 else "Chưa hay"
    basis = str(res.get("dislike_basis") or "").strip()
    rec = str(res.get("recommendation") or "").strip()
    if cat == "Hay":
        rec = "Like"
    elif cat == "Trung bình":
        rec = "Bỏ qua"
    else:
        rec = "Dislike" if (rec.lower().startswith("dislike") and basis) else "Bỏ qua"
    if rec != "Dislike":
        basis = ""
    reasons = [str(x).strip() for x in (res.get("reasons") or []) if str(x).strip()][:5]
    summary = str(res.get("summary") or "").strip()
    if summary:
        reasons.insert(0, "Nội dung: " + summary)
    if not has_transcript:
        reasons.append("Không lấy được phụ đề – điểm dựa trên tiêu đề, mô tả và số liệu (độ tin cậy thấp hơn).")
    comments = []
    for c in res.get("comments") or []:
        c = re.sub(r"https?://\S+", "", str(c)).strip().strip('"')
        if c and all(difflib.SequenceMatcher(None, c.lower(), o.lower()).ratio() < 0.75 for o in comments):
            comments.append(c)
    off = str(res.get("same_niche", True)).strip().lower() in ("false", "0", "no", "không")
    if off:   # AI thấy KHÁC chủ đề kênh: không bao giờ đề xuất Like / Dislike
        rec, basis = "Bỏ qua", ""
        reasons.insert(0, "KHÁC CHỦ ĐỀ KÊNH: " + (str(res.get("niche_reason") or "").strip()
                                                  or "AI thấy video không cùng thể loại / ngôn ngữ với kênh"))
    return dict(topic=str(res.get("topic") or "").strip()[:40], score=score, category=cat, reasons=reasons,
                recommendation=rec, dislike_basis=basis, comments=comments[:3], off_topic=off)


def too_similar(comments, previous, limit=0.8):
    """Các bình luận gần giống câu đã dùng trước đây."""
    bad = []
    for c in comments:
        for p in previous:
            if difflib.SequenceMatcher(None, c.lower(), p.lower()).ratio() >= limit:
                bad.append(c)
                break
    return bad


def _fmt_dur(sec):
    sec = int(sec or 0)
    return f"{sec // 3600}:{sec % 3600 // 60:02d}:{sec % 60:02d}" if sec >= 3600 else f"{sec // 60}:{sec % 60:02d}"


def analyze(info, settings, previous_comments=()):
    """info: dữ liệu video (title, channel, description, duration, views, likes, transcript, window, source).
    settings: provider, model, key, comment_lang, topic. Trả về dict đã chuẩn hóa + 'ai' (tên AI đã dùng)."""
    provider = OLD_NAMES.get(settings.get("provider", ""), settings.get("provider", ""))
    has_tr = bool((info.get("transcript") or "").strip()) or bool(settings.get("title_only"))
    if not uses_ai(provider, settings.get("key")) or provider == MANUAL:
        res = heuristic(info, settings)
        res["ai"] = "Chấm sơ bộ (không AI)"
        return res
    prompt = build_prompt(info, settings, previous_comments)
    model = settings.get("model") or PROVIDERS[provider]
    key = settings.get("key", "")
    try:
        res = normalize(parse_json(call_llm(provider, model, key, SYSTEM, prompt)), has_tr)
    except AIError:   # AI trả lời hỏng / lỡ nhịp -> hỏi lại 1 lần trước khi báo lỗi
        res = normalize(parse_json(call_llm(provider, model, key, SYSTEM,
                                            prompt + "\nCHỈ trả về đúng 1 đối tượng JSON hợp lệ.")), has_tr)
    bad = too_similar(res["comments"], previous_comments)
    if bad or len(res["comments"]) < 3:   # viết lại 1 lần cho đủ 3 câu khác nhau, không lặp câu cũ
        extra = prompt + ("\nCÁC CÂU SAU QUÁ GIỐNG CÂU CŨ, HÃY VIẾT KHÁC HẲN: " + "; ".join(bad) if bad else "") + \
            "\nNhớ: đúng 3 bình luận khác nhau."
        try:
            res2 = normalize(parse_json(call_llm(provider, model, key, SYSTEM, extra)), has_tr)
            if len(res2["comments"]) >= len(res["comments"]) and not too_similar(res2["comments"], previous_comments):
                res["comments"] = res2["comments"]
        except AIError:
            pass
    res["ai"] = f"{provider.split(' ')[0]} · {model}"
    return res


TITLE_PROMPT = """Đánh giá video YouTube CHỈ DỰA VÀO TIÊU ĐỀ (không có lời thoại).

CHỦ ĐỀ KÊNH MỤC TIÊU: {topic}
VÍ DỤ TIÊU ĐỀ VIDEO CỦA KÊNH MỤC TIÊU (để so chủ đề, thể loại, ngôn ngữ):
{samples}
Tiêu đề: {title}
Kênh: {channel}
Thời lượng: {duration} | Lượt xem: {views} | Lượt thích: {likes}

Yêu cầu:
0. "same_niche": so với các tiêu đề ví dụ, xét THỂ LOẠI RỘNG và NGÔN NGỮ (không cần cùng tác giả / chương trình;
   vd radio drama, old time radio, audio drama, radio play, mystery theatre là cùng 1 thể loại). Chỉ false khi RÕ RÀNG
   khác ngôn ngữ hoặc khác hẳn dạng nội dung (phim truyền hình, phim, nhạc, tin tức, game, vlog...) – chỉ trùng chữ
   chung như "drama", "story", "full episodes" thì không tính là giống. Không chắc -> true.
   "niche_reason": 1 câu tiếng Việt vì sao.
1. "topic": chủ đề video, 2–4 từ (ví dụ "Love Story", "Radio Drama", "Audio Story").
2. "summary": 1–2 câu tiếng Việt: theo tiêu đề, video này nói về gì / thuộc loại nội dung nào.
3. "score": điểm 0–100 cho TIÊU ĐỀ và độ phù hợp, theo: tiêu đề rõ ràng, cụ thể (tên truyện, tác giả, thể loại...),
   hấp dẫn, gợi tò mò nhưng KHÔNG giật tít / câu view / viết hoa lộn xộn / nhồi từ khóa; mức liên quan với chủ đề kênh
   mục tiêu; tỉ lệ thích / xem nếu có. Phân biệt rõ: tiêu đề bình thường 55–70, chỉ tiêu đề thật sự tốt mới trên 85.
4. "category": "Hay" (score >= 75), "Trung bình" (50–74) hoặc "Chưa hay" (< 50).
5. "reasons": 3–4 nhận định ngắn bằng tiếng Việt, mỗi nhận định chỉ ra CHI TIẾT CỤ THỂ trong tiêu đề (cụm từ nào,
   vì sao tốt / chưa tốt), không viết chung chung.
6. "recommendation": "Like" nếu Hay; "Bỏ qua" nếu Trung bình; với Chưa hay chỉ "Dislike" khi tiêu đề giật tít /
   gây hiểu lầm / spam rõ ràng, nếu không thì "Bỏ qua".
7. "dislike_basis": căn cứ cụ thể nếu đề xuất Dislike, ngược lại "".
8. "comments": đúng 3 bình luận KHÁC NHAU bằng {lang}, tự nhiên như người xem thật, chỉ nhắc tới điều có trong
   tiêu đề (tên truyện, tác giả, nhân vật, thể loại); 1–2 câu, không link, không quảng cáo, không hashtag,
   tối đa 1 emoji, không dùng câu sáo rỗng kiểu "Great video!"; không giống các câu đã dùng: {avoid}
Trả về JSON:
{{"same_niche": true, "niche_reason": "...", "topic": "...", "summary": "...", "score": 0, "category": "...",
"reasons": ["..."], "recommendation": "...", "dislike_basis": "", "comments": ["...", "...", "..."]}}"""


def _samples(settings):
    t = [x for x in (settings.get("samples") or []) if x][:12]
    return "\n".join(f"- {x[:100]}" for x in t) or "(không có – dựa vào chủ đề ở trên)"


def build_prompt(info, settings, previous_comments=(), max_transcript=14000):
    has_tr = bool((info.get("transcript") or "").strip())
    lang = COMMENT_LANGS.get(settings.get("comment_lang", "English"), "English")
    avoid = "; ".join(f'"{c[:70]}"' for c in list(previous_comments)[:12]) or "(chưa có)"
    if settings.get("title_only"):
        return TITLE_PROMPT.format(topic=settings.get("topic") or "(không rõ)", samples=_samples(settings),
                                   title=info.get("title", ""),
                                   channel=info.get("channel", ""), duration=_fmt_dur(info.get("duration")),
                                   views=info.get("views") or "?", likes=info.get("likes") or "?",
                                   lang=lang, avoid=avoid)
    return PROMPT.format(
        topic=settings.get("topic") or "(không rõ)", samples=_samples(settings), title=info.get("title", ""), channel=info.get("channel", ""),
        duration=_fmt_dur(info.get("duration")), views=info.get("views") or "?", likes=info.get("likes") or "?",
        description=(info.get("description") or "")[:1500], window=info.get("window_label", ""),
        source=info.get("source") or "không có",
        transcript=(info.get("transcript") or "(không có phụ đề / bản chép lời)")[:max_transcript],
        lang=lang, avoid=avoid,
        no_transcript_note="" if has_tr else
        "LƯU Ý: không có bản chép lời – chấm điểm thận trọng dựa trên tiêu đề, mô tả, số liệu; "
        "bình luận chỉ nói tới điều có trong tiêu đề / mô tả.\n")


# ============================================================ dán tay qua ChatGPT / Gemini / Claude (web)
BATCH_HEAD = """Bạn là biên tập viên nội dung YouTube khó tính và công bằng. Dưới đây là {n} video. Với MỖI video, hãy
làm đúng theo phần "Yêu cầu" của video đó, rồi trả lời bằng MỘT mảng JSON (không thêm chữ nào khác ngoài mảng),
mỗi phần tử là kết quả của 1 video và PHẢI có thêm trường "video_id" đúng như mã ghi ở đầu video:
[{{"video_id": "...", "topic": "...", "summary": "...", "score": 0, "category": "...", "reasons": ["..."], "recommendation": "...",
"dislike_basis": "", "comments": ["...", "...", "..."]}}, ...]
Bình luận của các video khác nhau cũng phải khác nhau hoàn toàn.
"""


def batch_prompt(items, settings, previous_comments=()):
    """Yêu cầu gộp nhiều video (để dán 1 lần vào ChatGPT / Gemini / Claude trên web)."""
    parts = [BATCH_HEAD.format(n=len(items))]
    per = max(3000, 36000 // max(1, len(items)))   # giữ cả yêu cầu khoảng <= 40.000 ký tự
    for i, it in enumerate(items, 1):
        parts.append(f"\n==================== VIDEO {i} | video_id: {it['video_id']} ====================\n")
        parts.append(build_prompt(it, settings, previous_comments, max_transcript=per)
                     .replace("Trả về JSON:", "Kết quả của video này (một phần tử trong mảng, nhớ có \"video_id\"):"))
    parts.append("\nCHỈ trả về mảng JSON.")
    return "".join(parts)


def parse_batch(text, ids):
    """Đọc câu trả lời dán từ ChatGPT / Gemini / Claude: {video_id: kết quả đã chuẩn hóa}."""
    t = re.sub(r"```(?:json)?", "", (text or "")).strip()
    data = None
    for cand in (t, (re.search(r"\[.*\]", t, re.S) or [None])[0]):
        if not cand:
            continue
        try:
            d = json.loads(cand)
        except Exception:
            continue
        if isinstance(d, dict) or (isinstance(d, list) and any(isinstance(x, dict) for x in d)):
            data = d
            break
    if data is None:   # nhiều đối tượng rời rạc { } { }
        objs = []
        for m in re.finditer(r"\{(?:[^{}]|\{[^{}]*\})*\}", t, re.S):
            try:
                objs.append(json.loads(m.group(0)))
            except Exception:
                pass
        data = objs or None
    if isinstance(data, dict):
        data = data.get("results") or data.get("videos") or [data]
    if not isinstance(data, list) or not data:
        raise AIError("Không đọc được câu trả lời. Hãy sao chép NGUYÊN câu trả lời của AI (phần mảng JSON [ ... ]).")
    out = {}
    for i, d in enumerate(x for x in data if isinstance(x, dict)):
        vid = str(d.get("video_id") or d.get("id") or "").strip()
        if vid not in ids and i < len(ids) and not vid:
            vid = ids[i]   # AI quên ghi mã -> theo thứ tự
        if vid in ids:
            out[vid] = normalize(d, True)
    if not out:
        raise AIError("Câu trả lời không có video nào khớp mã video_id của lượt này.")
    return out


def heuristic(info, settings):
    """Chấm sơ bộ khi không có AI: dựa trên tỉ lệ thích/xem, có phụ đề, độ liên quan. Không viết bình luận."""
    score, reasons = 55, []
    views, likes = int(info.get("views") or 0), int(info.get("likes") or 0)
    if views >= 200 and likes:
        per_k = likes / views * 1000
        if per_k >= 40:
            score += 18
            reasons.append(f"Tỉ lệ thích rất cao ({per_k:.0f} lượt thích / 1.000 lượt xem).")
        elif per_k >= 20:
            score += 9
            reasons.append(f"Tỉ lệ thích khá ({per_k:.0f} / 1.000 lượt xem).")
        elif per_k < 5:
            score -= 10
            reasons.append(f"Tỉ lệ thích thấp ({per_k:.1f} / 1.000 lượt xem).")
    else:
        reasons.append("Chưa đủ lượt xem / lượt thích để đánh giá theo số liệu.")
    rel = float(info.get("relevance") or 0)
    if rel >= 60:
        score += 8
        reasons.append(f"Liên quan tốt với chủ đề kênh mục tiêu ({rel:.0f}/100).")
    elif rel < 25:
        score -= 6
        reasons.append(f"Ít liên quan tới chủ đề kênh mục tiêu ({rel:.0f}/100).")
    tr = info.get("transcript") or ""
    if tr:
        words = len(tokens(tr))
        score += 4 if words > 600 else 0
        reasons.append(f"Có bản chép lời đoạn phân tích ({words} từ).")
    else:
        reasons.append("Không có phụ đề – không đánh giá được nội dung lời thoại.")
    reasons.append("Chấm sơ bộ không dùng AI – nhập khóa API để chấm theo nội dung và viết bình luận.")
    res = normalize(dict(score=score, reasons=reasons, recommendation="", comments=[]), True)
    if not tr and res["recommendation"] == "Like":   # chưa xem được nội dung -> không đề xuất Like
        res["recommendation"] = "Bỏ qua"
    res["topic"] = info.get("topic_guess") or ""
    return res
