"""
Tự soạn chữ cho Bài đăng cộng đồng (kèm 1 video) – đúng NGÔN NGỮ và CHỦ ĐỀ của kênh, mục đích mời khán giả
xem video và để lại bình luận. Bản nháp hiện trong ô "Nội dung chữ của bài đăng" để bạn đọc / sửa rồi mới Lưu.

· Đã cài AI ở trang Phân tích video (Claude / OpenAI / Gemini có khóa, hoặc Ollama trên máy) -> nhờ AI viết.
· Chưa có AI -> dùng kho câu mẫu theo ngôn ngữ, mỗi lần 1 kiểu khác nhau, không lặp kiểu vừa dùng.
Ngôn ngữ đọc từ tên các video của kênh (không đoán: không nhận ra -> tiếng Anh).
"""
import html
import json
import os
import random
import re
import urllib.parse
import urllib.request

import paths

USED_FILE = os.path.join(paths.DATA, "bai_dang_da_soan.json")

# {title} = tên video · {ch} = tên kênh · {q} = câu hỏi mời bình luận (lấy ngẫu nhiên trong QUESTIONS)
TEMPLATES = {
    "en": [
        "🎬 New on the channel: \"{title}\"\n\nGet comfortable and enjoy – this one is worth every minute.\n{q}",
        "Have you listened to \"{title}\" yet? 👀\n\nTell us in the comments what you think – we read every one! 💬",
        "Tonight's pick 🌙 \"{title}\"\n\nPerfect for a quiet evening. {q}",
        "If you enjoyed our last story, you'll love this one ❤️\n\"{title}\"\n\n{q}",
        "📢 Just in: \"{title}\"\n\nShare it with someone who loves a good story, and let us know your favourite moment!",
        "One question for you 👇\n{q}\n\nWhile you think about it, here's our latest: \"{title}\" 🎬",
        "Thank you for being part of this community 🙏\nHere's something new for you: \"{title}\"\n\n{q}",
        "Quick poll in the comments 💬 {q}\n\nAnd don't miss \"{title}\" – out now on {ch}!",
    ],
    "vi": [
        "🎬 Video mới trên kênh: \"{title}\"\n\nThư giãn và thưởng thức nhé – đáng xem từng phút!\n{q}",
        "Bạn đã xem \"{title}\" chưa? 👀\n\nĐể lại cảm nhận ở phần bình luận nhé – kênh đọc hết từng bình luận! 💬",
        "Gợi ý cho tối nay 🌙 \"{title}\"\n\n{q}",
        "Nếu bạn thích video trước, chắc chắn sẽ thích video này ❤️\n\"{title}\"\n\n{q}",
        "📢 Vừa lên sóng: \"{title}\"\n\nChia sẻ cho người bạn thích nghe chuyện hay và cho kênh biết đoạn bạn thích nhất nhé!",
        "Một câu hỏi nhỏ cho bạn 👇\n{q}\n\nTrong lúc nghĩ, mời bạn xem video mới nhất: \"{title}\" 🎬",
        "Cảm ơn bạn đã luôn đồng hành cùng kênh 🙏\nVideo mới dành cho bạn: \"{title}\"\n\n{q}",
    ],
    "tl": [
        "🎧 Bago sa channel: \"{title}\"\n\nMakinig at mag-relax – sulit bawat minuto!\n{q}",
        "Napanood mo na ba ang \"{title}\"? 👀\n\nI-comment mo ang opinyon mo – binabasa namin lahat! 💬",
        "Para sa gabing ito 🌙 \"{title}\"\n\n{q}",
        "Kung nagustuhan mo ang huli naming kwento, magugustuhan mo rin ito ❤️\n\"{title}\"\n\n{q}",
        "Salamat sa pagsuporta sa channel 🙏\nMay bago para sa inyo: \"{title}\"\n\n{q}",
    ],
    "ilo": [
        "🎧 Baro iti channel: \"{title}\"\n\nDengngen ken ayaten – maikari iti tunggal minuto!\n{q}",
        "Nabuya yo kadin ti \"{title}\"? 👀\n\nIsurat yo ti kapanunotan yo iti comment! 💬",
        "Agyamanak iti panangsuporta yo 🙏\nAdda baro para kadakayo: \"{title}\"\n\n{q}",
        "Para iti daytoy a rabii 🌙 \"{title}\"\n\n{q}",
    ],
    "ceb": [
        "🎧 Bag-o sa channel: \"{title}\"\n\nPaminaw ug pag-relax – sulit matag minuto!\n{q}",
        "Natan-aw na ba nimo ang \"{title}\"? 👀\n\nI-comment ang imong opinyon! 💬",
        "Salamat sa pagsuporta 🙏\nNaay bag-o para ninyo: \"{title}\"\n\n{q}",
        "Para karong gabii 🌙 \"{title}\"\n\n{q}",
    ],
    "es": [
        "🎧 Nuevo en el canal: \"{title}\"\n\nPonte los auriculares y disfruta – vale cada minuto.\n{q}",
        "¿Ya escuchaste \"{title}\"? 👀\n\nCuéntanos en los comentarios qué te pareció 💬",
        "Gracias por ser parte de esta comunidad 🙏\nAlgo nuevo para ti: \"{title}\"\n\n{q}",
        "Recomendación para esta noche 🌙 \"{title}\"\n\n{q}",
    ],
    "pt": [
        "🎧 Novo no canal: \"{title}\"\n\nColoque os fones e aproveite – vale cada minuto.\n{q}",
        "Você já assistiu \"{title}\"? 👀\n\nConta pra gente nos comentários o que achou 💬",
        "Obrigado por fazer parte desta comunidade 🙏\nNovidade para você: \"{title}\"\n\n{q}",
    ],
    "fr": [
        "🎧 Nouveau sur la chaîne : « {title} »\n\nMettez vos écouteurs et profitez – ça vaut chaque minute.\n{q}",
        "Vous avez déjà écouté « {title} » ? 👀\n\nDites-nous en commentaire ce que vous en pensez 💬",
        "Merci de faire partie de cette communauté 🙏\nDu nouveau pour vous : « {title} »\n\n{q}",
    ],
    "de": [
        "🎧 Neu auf dem Kanal: „{title}“\n\nKopfhörer auf und genießen – jede Minute wert.\n{q}",
        "Hast du „{title}“ schon gehört? 👀\n\nSchreib uns in die Kommentare, wie es dir gefallen hat 💬",
        "Danke, dass ihr Teil dieser Community seid 🙏\nNeu für euch: „{title}“\n\n{q}",
    ],
    "id": [
        "🎧 Baru di channel: \"{title}\"\n\nPasang headphone dan nikmati – layak setiap menitnya.\n{q}",
        "Sudah dengar \"{title}\"? 👀\n\nTulis pendapatmu di kolom komentar ya 💬",
        "Terima kasih sudah jadi bagian komunitas ini 🙏\nAda yang baru untukmu: \"{title}\"\n\n{q}",
    ],
}
QUESTIONS = {
    "en": ["Which part surprised you the most? 🤔", "Who was your favourite character? 💬",
           "Do you listen at night or during the day? 🌙☀️", "Rate it from 1 to 10 in the comments! ⭐",
           "What story should we bring next? 👇", "Where are you listening from today? 🌍"],
    "vi": ["Đoạn nào làm bạn bất ngờ nhất? 🤔", "Bạn thích nhân vật nào nhất? 💬",
           "Bạn hay nghe vào buổi tối hay ban ngày? 🌙☀️", "Chấm điểm từ 1 đến 10 ở phần bình luận nhé! ⭐",
           "Bạn muốn kênh làm câu chuyện nào tiếp theo? 👇", "Hôm nay bạn đang nghe từ đâu? 🌍"],
    "tl": ["Anong bahagi ang pinaka-nagulat ka? 🤔", "Sino ang paborito mong karakter? 💬",
           "I-rate mula 1 hanggang 10 sa comments! ⭐", "Saan ka nakikinig ngayon? 🌍"],
    "ilo": ["Ania ti kasayaatan a paset para kenka? 🤔", "Siasino ti paborito mo a karakter? 💬",
            "Ibilang manipud 1 agingga 10 iti comment! ⭐"],
    "ceb": ["Unsang bahina ang labing nakapakurat nimo? 🤔", "Kinsa ang imong paboritong karakter? 💬",
            "I-rate gikan 1 hangtod 10 sa comments! ⭐"],
    "es": ["¿Qué parte te sorprendió más? 🤔", "¿Quién es tu personaje favorito? 💬",
           "¡Califícalo del 1 al 10 en los comentarios! ⭐"],
    "pt": ["Qual parte mais te surpreendeu? 🤔", "Quem é seu personagem favorito? 💬",
           "Dê uma nota de 1 a 10 nos comentários! ⭐"],
    "fr": ["Quel passage vous a le plus surpris ? 🤔", "Quel est votre personnage préféré ? 💬",
           "Notez-le de 1 à 10 en commentaire ! ⭐"],
    "de": ["Welcher Teil hat dich am meisten überrascht? 🤔", "Wer ist deine Lieblingsfigur? 💬",
           "Bewerte es von 1 bis 10 in den Kommentaren! ⭐"],
    "id": ["Bagian mana yang paling mengejutkan? 🤔", "Siapa karakter favoritmu? 💬",
           "Beri nilai 1 sampai 10 di kolom komentar! ⭐"],
}


# ------------------------------------------------------------------ đọc tên video / kênh (yêu cầu nền, không mở tab)
def _get(url, timeout=15):
    req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0", "Accept-Language": "vi-VN,vi;q=0.9"})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return r.read().decode("utf-8", "replace")


def channel_feed(cid):
    """(tên kênh, [(mã video, tên video), ...] mới nhất trước) từ RSS công khai của kênh."""
    try:
        xml = _get(f"https://www.youtube.com/feeds/videos.xml?channel_id={cid}")
    except Exception:
        return "", []
    name = re.search(r"<author>\s*<name>([^<]*)</name>", xml)
    items = re.findall(r"<yt:videoId>([\w-]{11})</yt:videoId>\s*<yt:channelId>[^<]*</yt:channelId>\s*"
                       r"<title>([^<]*)</title>", xml)
    return (html.unescape(name.group(1)) if name else ""), [(v, html.unescape(t)) for v, t in items]


def video_title(link):
    try:
        data = json.loads(_get("https://www.youtube.com/oembed?format=json&url=" + urllib.parse.quote(link, safe="")))
        return data.get("title", ""), data.get("author_name", "")
    except Exception:
        return "", ""


# ------------------------------------------------------------------ soạn
def _used():
    try:
        with open(USED_FILE, encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return []


def _remember(key):
    old = [k for k in _used() if k != key][-40:]
    try:
        with open(USED_FILE, "w", encoding="utf-8") as f:
            json.dump(old + [key], f)
    except Exception:
        pass


def lang_of(titles, default="en"):
    import cmt_lang
    text = " ".join(t for t in titles if t)
    code = cmt_lang.detect(text, default=default) if text.strip() else default
    return code if code in TEMPLATES else "en"


def from_templates(title, channel, lang):
    lang = lang if lang in TEMPLATES else "en"
    used = set(_used())
    pool = [(i, t) for i, t in enumerate(TEMPLATES[lang]) if f"{lang}:{i}" not in used] or \
        list(enumerate(TEMPLATES[lang]))
    i, tpl = random.choice(pool)
    _remember(f"{lang}:{i}")
    q = random.choice(QUESTIONS.get(lang) or QUESTIONS["en"])
    title = re.sub(r"\s+", " ", title or "").strip()[:90] or channel
    return tpl.format(title=title, ch=channel or "", q=q).strip()


def from_ai(title, channel, lang, titles):
    """Nhờ AI đã cài ở trang Phân tích video viết. Không có AI / lỗi -> None (dùng câu mẫu)."""
    try:
        import pt_ai
        import pt_page
        st = pt_page.load_settings() or {}
        prov, model, key = st.get("provider"), st.get("model"), st.get("key") or ""
        if not prov or pt_ai.is_manual(prov) or not pt_ai.uses_ai(prov, key):
            return None
        if prov == pt_ai.OLLAMA:      # Ollama chưa chạy trên máy -> dùng câu mẫu, không chờ
            try:
                urllib.request.urlopen(pt_ai.OLLAMA_URL + "/api/tags", timeout=2).close()
            except Exception:
                return None
        import cmt_lang
        lname = cmt_lang.lang_name(lang) if lang in cmt_lang.THANKS else "English"
        system = ("You write short YouTube Community posts for a channel owner. Warm, natural, not salesy, "
                  "no hashtags spam, 2-4 short lines, 1-3 emojis, end with ONE question that invites comments. "
                  "Never invent facts about the video beyond its title. Reply as JSON: {\"post\": \"...\"}")
        prompt = (f"Language: {lname}. Channel: {channel}. The post links this video: \"{title}\". "
                  f"Other recent video titles on the channel (for topic and tone): {titles[:8]}. "
                  f"Write the post in {lname} only.")
        out = pt_ai.call_llm(prov, model, key, system, prompt, max_tokens=400)
        post = (pt_ai.parse_json(out) or {}).get("post", "")
        post = str(post).strip()
        return post if 10 < len(post) < 1200 else None
    except Exception:
        return None


def compose(cid="", link="", lang=None, log=print):
    """Soạn 1 bài đăng. cid = kênh đăng bài (đọc ngôn ngữ / chủ đề), link = video gắn kèm (trống = video mới
    nhất của kênh). Trả về (chữ bài đăng, mô tả nguồn) – không soạn được thì ("", lý do)."""
    channel, feed = channel_feed(cid) if str(cid).startswith("UC") else ("", [])
    title = ""
    if link:
        title, author = video_title(link)
        channel = channel or author
    elif feed:
        title = feed[0][1]
    if not title:
        return "", "Chưa đọc được tên video (kiểm tra mạng, ID kênh, hoặc link video)."
    titles = [t for _v, t in feed] + [title]
    lang = lang or lang_of(titles)
    post = from_ai(title, channel, lang, titles)
    how = "AI" if post else "câu mẫu"
    if not post:
        post = from_templates(title, channel, lang)
    import cmt_lang
    return post, f"{how} · {cmt_lang.lang_name(lang) if lang in cmt_lang.THANKS else lang} · video: {title[:60]}"
