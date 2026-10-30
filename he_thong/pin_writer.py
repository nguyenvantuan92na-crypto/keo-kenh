"""
Tự soạn BÌNH LUẬN GHIM theo đúng nội dung video (dùng khi bạn để trống ô Bình luận ghim).

- Đọc tên video đang gắn bình luận + tên video cần đẩy view (hỏi nền, không mở tab).
- Rút gọn tên truyện (bỏ tiền tố chung như "BBC RADIO DRAMA", bỏ tên kênh), viết hoa cho dễ đọc.
- Nhận thể loại (trinh thám / kịch truyền thanh / chung) và ngôn ngữ của kênh -> chọn mẫu câu hợp.
- Mỗi video một câu KHÁC nhau (chọn theo mã video), câu gợi tò mò, mời nghe tiếp – KHÔNG bịa số liệu,
  không khen quá lời, không hashtag. Câu luôn có chữ TRƯỚC đường link (để tool nhận ra bình luận của mình).
"""
import re
import zlib

GENERIC_PARTS = r"^(bbc )?(radio drama|old time radio|otr|audio drama|audiobook|full (episode|audiobook)s?|" \
                r"radio play|classic radio|mystery theatre|radio)$"
MYSTERY = r"mystery|murder|detective|christie|poirot|holmes|marple|wimsey|crime|whodunit|inspector|maigret|" \
          r"vụ án|hung thủ|trinh thám|thám tử"

TEMPLATES = {
    "en": {
        "any": [
            "🎧 Enjoyed “{cur}”? Your next listen is “{tgt}” – stay until the final scene and tell us what you think 👉 {link}",
            "Which moment hooked you most in this one? If you loved it, “{tgt}” is next on the list 👉 {link}",
            "📻 The story continues with “{tgt}” – grab a cup of tea and press play ☕ 👉 {link}",
            "Thanks for listening! ❤️ If “{cur}” kept you hooked, don't miss “{tgt}” 👉 {link}",
            "Ready for another one? “{tgt}” is waiting for you – who's your favourite character so far? 👉 {link}",
            "🎙️ Up next on the channel: “{tgt}”. Who's listening tonight? 👉 {link}",
        ],
        "mystery": [
            "🔎 Another case to crack: “{tgt}”. Can you name the culprit before the reveal? 👉 {link}",
            "🕵️ Think you can solve “{tgt}” before the detective does? Tell us your guess! 👉 {link}",
            "Did you spot the clue in “{cur}”? Put your skills to the test with “{tgt}” 🔎 👉 {link}",
        ],
    },
    "vi": {
        "any": [
            "🎧 Thích “{cur}” chứ? Nghe tiếp “{tgt}” nhé – nghe đến cuối rồi kể cho kênh cảm nhận của bạn 👉 {link}",
            "Đoạn nào trong video này làm bạn nhớ nhất? Nếu thích, nghe tiếp “{tgt}” nha 👉 {link}",
            "📻 Câu chuyện tiếp theo: “{tgt}” – pha ly trà và bấm nghe thôi ☕ 👉 {link}",
            "Cảm ơn bạn đã nghe! ❤️ Nếu “{cur}” cuốn bạn, đừng bỏ lỡ “{tgt}” 👉 {link}",
            "Sẵn sàng nghe thêm chưa? “{tgt}” đang chờ bạn – bạn thích nhân vật nào nhất? 👉 {link}",
        ],
        "mystery": [
            "🔎 Thêm một vụ án nữa: “{tgt}”. Bạn đoán ra hung thủ trước khi lộ diện không? 👉 {link}",
            "🕵️ Thử tài phá án với “{tgt}” – để lại dự đoán của bạn nhé! 👉 {link}",
        ],
    },
}


def short_title(title, channel_name=""):
    """'BBC RADIO DRAMA | CINDERS by Ali Taylor | Tên Kênh' -> 'Cinders by Ali Taylor'."""
    t = re.sub(r"\s+", " ", str(title or "")).strip()
    if not t:
        return ""
    parts = [p.strip(" -–:") for p in re.split(r"\s*[|｜]\s*|\s+[–-]\s+|:\s+", t) if p.strip(" -–:")]
    ch = re.sub(r"\W+", "", str(channel_name or "").lower())
    keep = [p for p in parts if not re.match(GENERIC_PARTS, p.lower().strip())
            and (not ch or re.sub(r"\W+", "", p.lower()) != ch)]
    best = (keep or parts)[0]          # tên truyện thường đứng đầu (sau tiền tố chung)
    small = {"a", "an", "the", "of", "by", "in", "on", "at", "to", "and", "for"}
    words = []
    for i, w in enumerate(best.split()):
        if len(w) > 1 and w.isupper() and not re.fullmatch(r"[IVXLC]+", w):   # CHỮ HOA -> Viết Hoa Đầu
            w = w.lower()
            w = w if (i and w in small) else w[:1].upper() + w[1:]
        words.append(w)
    return " ".join(words)[:70]


def detect_lang(*texts):
    try:
        import pt_ai
        langs = [pt_ai.detect_lang(t) for t in texts if t]
        langs = [x for x in langs if x]
        if langs:
            return max(set(langs), key=langs.count)
    except Exception:
        pass
    return "en"


def write(cur_title, tgt_title, link, vid="", channel_name="", lang=None):
    """Bình luận ghim cho 1 video. `vid` (mã video đang gắn) quyết định mẫu câu -> mỗi video 1 câu khác nhau."""
    cur = short_title(cur_title, channel_name) or "this one"
    tgt = short_title(tgt_title, channel_name)
    lang = lang or detect_lang(cur_title, tgt_title)
    bank = TEMPLATES.get(lang) or TEMPLATES["en"]
    if lang not in TEMPLATES:
        lang = "en"
    if not tgt:   # không đọc được tên video cần đẩy: câu không nhắc tên
        tgt = "the next story" if lang == "en" else "câu chuyện tiếp theo"
    mystery = re.search(MYSTERY, f"{cur_title} {tgt_title}", re.I)
    pool = (bank["mystery"] + bank["any"]) if mystery else bank["any"]
    if cur == "this one":
        pool = [p for p in pool if "{cur}" not in p] or pool
    i = zlib.crc32((vid or tgt).encode("utf-8")) % len(pool)
    if all(p in _USED for p in pool):   # đã dùng hết mẫu trong lượt này -> bắt đầu vòng mới
        _USED.difference_update(pool)
    while pool[i] in _USED:               # mỗi video 1 mẫu KHÁC trong cùng lượt chạy
        i = (i + 1) % len(pool)
    _USED.add(pool[i])
    return pool[i].format(cur=cur, tgt=tgt, link=link).strip() + "\n"


_USED = set()
