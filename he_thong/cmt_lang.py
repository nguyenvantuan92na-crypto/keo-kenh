"""
Đọc 1 bình luận của khán giả: nhận NGÔN NGỮ và LOẠI bình luận (khen / hỏi / chê / quảng cáo / khác),
rồi soạn câu cảm ơn đúng ngôn ngữ đó.

Nguyên tắc chính xác: CHỈ coi là "khen" khi chắc chắn (có từ khen, không có từ chê, không phải câu hỏi,
không có link / quảng cáo, không có "nhưng/but..." kèm góp ý). Không chắc -> KHÔNG tự trả lời.
"""
import re
import unicodedata

PRAISE, QUESTION, NEGATIVE, SPAM, MIXED, OTHER, OWNER = (
    "Khen", "Hỏi", "Chê / góp ý", "Quảng cáo / link", "Khen kèm góp ý", "Khác", "Của chủ kênh")

# ------------------------------------------------------------------ câu cảm ơn theo ngôn ngữ
THANKS = {
    "en": ("English", "Thank you so much! ❤️"),
    "vi": ("Tiếng Việt", "Cảm ơn bạn rất nhiều! ❤️"),
    "tl": ("Tagalog", "Maraming salamat po! ❤️"),
    "ceb": ("Bisaya", "Daghang salamat kaayo! ❤️"),
    "ilo": ("Ilocano", "Agyamanak unay! ❤️"),
    "es": ("Español", "¡Muchas gracias! ❤️"),
    "pt": ("Português", "Muito obrigado! ❤️"),
    "fr": ("Français", "Merci beaucoup ! ❤️"),
    "de": ("Deutsch", "Vielen Dank! ❤️"),
    "it": ("Italiano", "Grazie mille! ❤️"),
    "nl": ("Nederlands", "Heel erg bedankt! ❤️"),
    "pl": ("Polski", "Dziękuję bardzo! ❤️"),
    "tr": ("Türkçe", "Çok teşekkür ederim! ❤️"),
    "id": ("Indonesia / Melayu", "Terima kasih banyak! ❤️"),
    "sv": ("Svenska", "Tack så mycket! ❤️"),
    "ro": ("Română", "Mulțumesc mult! ❤️"),
    "ru": ("Русский", "Большое спасибо! ❤️"),
    "uk": ("Українська", "Щиро дякую! ❤️"),
    "el": ("Ελληνικά", "Ευχαριστώ πολύ! ❤️"),
    "ar": ("العربية", "شكراً جزيلاً! ❤️"),
    "he": ("עברית", "תודה רבה! ❤️"),
    "hi": ("हिन्दी", "बहुत-बहुत धन्यवाद! ❤️"),
    "th": ("ไทย", "ขอบคุณมากๆ ❤️"),
    "ja": ("日本語", "本当にありがとうございます！❤️"),
    "ko": ("한국어", "정말 감사합니다! ❤️"),
    "zh": ("中文", "非常感谢！❤️"),
}
LANG_CHOICES = {v[0]: k for k, v in THANKS.items()}   # tên hiển thị -> mã


def lang_name(code):
    return THANKS.get(code, ("?", ""))[0]


# ------------------------------------------------------------------ nhận ngôn ngữ
_SCRIPTS = [  # (mã, khoảng ký tự)
    ("ja", r"[぀-ヿ]"), ("ko", r"[가-힯ᄀ-ᇿ]"), ("zh", r"[一-鿿]"),
    ("th", r"[฀-๿]"), ("ar", r"[؀-ۿ]"), ("he", r"[֐-׿]"),
    ("hi", r"[ऀ-ॿ]"), ("el", r"[Ͱ-Ͽ]"),
]
_VI = set("ăâđêôơưạảấầẩẫậắằẳẵặẹẻẽếềểễệỉịọỏốồổỗộớờởỡợụủứừửữựỳỵỷỹ")
_WORDS = {   # từ thường gặp (đặc trưng) của từng ngôn ngữ chữ Latinh
    "en": "the and is are was this that it of to in my you your i so very really what with for have has love "
          "story thank thanks great beautiful amazing listen listening one all just like such loved enjoyed "
          "wonderful excellent always these those they them but not can will would be been from radio play",
    "tl": "ang ng mga na ay ko mo siya hindi po ako ikaw talaga naman sobrang ganda galing salamat kwento "
          "nakakaiyak nakakatuwa yung lang din rin kasi pero sana grabe idol lodi ito iyan dito nga",
    "ceb": "ug kay wala dili unsa kini karon nindot kanindot kaayo salamat ganahan nalingaw akong imong "
           "jud gyud lagi bitaw kaau nimo nako ani amo",
    "ilo": "ti dagiti iti ken ket saan diak sika agyamanak unay napintas nagpintas nagsayaat naimbag "
           "nagimbag daytoy dayta isuna ngamin latta",
    "es": "el la los las es muy que de en y una un me encanta gracias hermoso hermosa precioso excelente "
          "historia esta este por para con pero bueno buena maravilloso",
    "pt": "o os as é muito que de em e uma um obrigado obrigada lindo linda adorei amei história essa esse "
          "por para com mas bom boa maravilhoso você",
    "fr": "le la les est très que de en et une un merci beaucoup magnifique superbe histoire cette ce pour "
          "avec mais bien c'est j'adore vous",
    "de": "der die das ist sehr und ein eine danke schön wunderschön toll geschichte diese dieser für mit "
          "aber gut nicht ich sie",
    "it": "il la gli è molto che di e una un grazie bellissimo bellissima storia questa questo per con ma "
          "bene complimenti",
    "nl": "de het een is zeer heel en van mooi prachtig bedankt verhaal deze dit voor met maar goed niet",
    "pl": "jest bardzo i w na to piękne dziękuję wspaniałe historia ta ten dla z ale dobrze nie",
    "tr": "bir ve bu çok güzel teşekkür ederim harika hikaye için ile ama iyi değil",
    "id": "yang dan ini itu sangat bagus terima kasih cerita untuk dengan tapi baik tidak keren mantap "
          "sekali banget",
    "sv": "och är det en ett tack så mycket mycket fin berättelse för med men bra inte",
    "vi": "là của và có không được quá nghe truyện cảm ơn hay mình bạn rất lắm thật này đó nhé ạ kênh",
    "ro": "și este foarte un o mulțumesc frumos frumoasă poveste pentru cu dar bine nu",
}
_WORDS = {k: set(v.split()) for k, v in _WORDS.items()}
_CHARS = {"pl": set("ąćęłńśźż"), "tr": set("ğış"), "ro": set("ăâîșț"), "de": set("ßäöü"),
          "es": set("ñ¿¡"), "pt": set("ãõç"), "fr": set("çœèêàù"), "sv": set("åäö")}


def detect(text, default="en"):
    """Mã ngôn ngữ của bình luận (theo chữ viết + từ đặc trưng). Không đủ căn cứ -> default."""
    t = (text or "").strip()
    if not t:
        return default
    for code, rx in _SCRIPTS:
        if len(re.findall(rx, t)) >= 2 or (len(re.findall(rx, t)) >= 1 and len(t) <= 6):
            return code
    if re.search(r"[Ѐ-ӿ]", t):
        return "uk" if re.search(r"[іїєґІЇЄҐ]", t) else "ru"
    low = t.lower()
    if sum(1 for ch in low if ch in _VI) >= 2:
        return "vi"
    toks = re.findall(r"[a-zà-ÿăâđêôơưąćęłńśźżğışșțœ'’-]+", low)
    if not toks:
        return default
    score = {k: sum(1 for w in toks if w in s) for k, s in _WORDS.items()}
    for k, cs in _CHARS.items():
        score[k] = score.get(k, 0) + 0.5 * sum(1 for ch in low if ch in cs)
    best = max(score, key=score.get)
    if score[best] <= 0:
        return default
    # Tagalog / Bisaya / Ilocano hay viết lẫn tiếng Anh: có từ đặc trưng là ưu tiên
    for k in ("ilo", "ceb", "tl"):
        if score[k] >= 1 and score[k] >= score["en"] * 0.5 and k != best and best == "en":
            best = k
            break
    return best


# ------------------------------------------------------------------ nhận loại bình luận
_PRAISE = {
    "en": ["love", "loved", "loving", "great", "amazing", "awesome", "beautiful", "beautifully", "wonderful",
           "excellent", "brilliant", "fantastic", "superb", "enjoyed", "enjoy", "enjoying", "best", "favorite",
           "favourite", "touched", "touching", "moving", "heartwarming", "nice", "so good", "very good",
           "well done", "bravo", "thank you", "thanks", "thank u", "thx", "perfect", "lovely", "gorgeous",
           "masterpiece", "incredible", "outstanding", "splendid", "delightful", "magnificent", "marvelous",
           "marvellous", "impressive", "inspiring", "keep it up", "keep up", "god bless", "great job", "good job",
           "recommend", "goosebumps", "gem", "treasure", "fabulous", "terrific", "charming", "riveting",
           "captivating", "gripping", "fascinating", "hooked", "loved it", "enjoyable", "good story", "classic",
           "superb", "stunning", "remarkable", "exceptional", "beautiful story", "so touched", "cried"],
    "vi": ["hay quá", "rất hay", "quá hay", "hay lắm", "hay thật", "truyện hay", "video hay", "hay ghê", "hay vậy",
           "hay qua", "tuyệt", "tuyệt vời", "cảm động", "xúc động", "rất thích", "thích quá", "yêu", "đỉnh",
           "cảm ơn", "cám ơn", "ý nghĩa", "ấm áp", "xuất sắc", "quá đỉnh", "hay", "tuyệt quá"],
    "tl": ["ganda", "maganda", "galing", "napakaganda", "salamat", "nakakaiyak", "nakakatuwa", "gusto ko",
           "idol", "husay", "mahusay", "lodi", "astig", "grabe ganda", "sobrang ganda", "ang ganda", "ang galing"],
    "ceb": ["nindot", "kanindot", "nalingaw", "salamat", "maayo kaayo", "ganahan ko", "nami kaayo"],
    "ilo": ["napintas", "nagpintas", "nagsayaat", "agyamanak", "naimbag", "nagimbag", "ayayatek"],
    "es": ["me encanta", "encanta", "hermoso", "hermosa", "precioso", "preciosa", "excelente", "maravilloso",
           "maravillosa", "genial", "buenísimo", "muy bueno", "muy buena", "gracias", "increíble", "bello",
           "bella", "bonito", "bonita", "felicidades", "bravo"],
    "pt": ["lindo", "linda", "maravilhoso", "maravilhosa", "excelente", "adorei", "amei", "obrigado", "obrigada",
           "incrível", "muito bom", "muito boa", "parabéns", "perfeito"],
    "fr": ["magnifique", "superbe", "génial", "excellent", "merci", "j'adore", "bravo", "très beau", "très belle",
           "très bien", "merveilleux", "formidable", "sublime"],
    "de": ["wunderschön", "toll", "super", "großartig", "danke", "wunderbar", "sehr schön", "klasse", "genial",
           "fantastisch"],
    "it": ["bellissimo", "bellissima", "stupendo", "meraviglioso", "grazie", "bravo", "complimenti", "fantastico",
           "magnifico", "adoro"],
    "nl": ["prachtig", "mooi", "geweldig", "bedankt", "dank je", "fantastisch", "heerlijk"],
    "pl": ["piękne", "wspaniałe", "super", "dziękuję", "świetne", "cudowne"],
    "tr": ["harika", "çok güzel", "güzel", "teşekkür", "mükemmel", "süper", "bayıldım"],
    "id": ["bagus", "keren", "mantap", "terima kasih", "luar biasa", "indah", "sangat bagus", "menyentuh"],
    "sv": ["underbar", "fantastisk", "tack", "jättebra", "vacker"],
    "ro": ["minunat", "frumos", "mulțumesc", "superb", "excelent"],
    "ru": ["прекрасно", "замечательно", "отлично", "спасибо", "класс", "супер", "великолепно", "красиво", "браво",
           "люблю", "чудесно"],
    "uk": ["дякую", "чудово", "прекрасно", "супер", "гарно"],
    "el": ["ευχαριστώ", "υπέροχο", "τέλειο", "μπράβο", "ωραίο"],
    "ar": ["رائع", "جميل", "شكرا", "ممتاز", "مبدع", "احسنت"],
    "he": ["תודה", "מדהים", "יפה", "מעולה"],
    "hi": ["बहुत अच्छा", "शानदार", "धन्यवाद", "सुंदर", "बढ़िया", "अद्भुत"],
    "th": ["ดีมาก", "ขอบคุณ", "สุดยอด", "ชอบ", "เยี่ยม", "ประทับใจ"],
    "ja": ["素晴らしい", "すごい", "ありがとう", "最高", "感動", "好き", "素敵"],
    "ko": ["최고", "감사", "좋아요", "멋져요", "감동", "대박", "사랑해요"],
    "zh": ["太好了", "好听", "很好", "谢谢", "感动", "精彩", "喜欢", "太棒"],
}
_NEG = ["boring", "bad", "worst", "hate", "terrible", "awful", "horrible", "stupid", "trash", "garbage", "fake",
        "scam", "sucks", "disappoint", "waste", "annoying", "poor", "not good", "not great", "didn't like",
        "dont like", "don't like", "dislike", "unsubscrib", "clickbait", "misleading", "too loud", "too low",
        "can't hear", "cant hear", "volume", "too many ads", "reupload", "re-upload", "stolen", "copyright",
        "ai voice", "robot voice", "ruined", "annoyed", "ugh", "meh", "mediocre", "pathetic", "rubbish",
        "dở", "chán", "tệ", "nhảm", "rác", "lừa đảo", "ghét", "không hay", "ko hay", "k hay",
        "pangit", "panget", "nakakabagot", "ayaw ko", "walang kwenta", "dili nindot", "saan a napintas",
        "aburrido", "malo", "mala", "odio", "chato", "ruim", "nul", "ennuyeux", "langweilig", "schlecht",
        "noioso", "brutto", "jelek", "membosankan", "плохо", "скучно", "ужасно"]
_BUT = ["but", "however", "although", "though", "except", "nhưng", "tuy nhiên", "pero", "kaso", "aber", "mais",
        "però", "maar", "ale", "ama", "tapi", "но", "lang sana", "sana"]
_Q_START = r"^(what|how|why|when|where|who|which|can|could|is|are|do|does|did|will|would|should|any|anyone|" \
           r"ano|paano|bakit|kailan|saan|sino|unsa|ngano|kanus-a|asa|sao|làm sao|khi nào|ở đâu|ai|có phải|" \
           r"qué|cómo|por qué|cuándo|dónde|quién)\b"
_SPAM = [r"https?://", r"www\.", r"\.(com|net|org|ly|me|io)\b", r"sub ?4 ?sub", r"subscribe to my", r"check (out )?my",
         r"my channel", r"whats ?app", r"telegram", r"t\.me/", r"\+?\d[\d\s-]{8,}\d", r"kênh của mình", r"ghé kênh",
         r"crypto", r"bitcoin", r"invest", r"earn \$", r"dm me", r"inbox me"]
_HEART_EMOJI = set("❤♥💕💖💗💓💞💘💝😍🥰😘👏👍🙏🔥💯⭐🌟😊☺🤗💐🌹✨🫶😭🥲💙💚💛💜🧡🤍")


def _has(text, words):
    for w in words:
        if re.search(r"[^\W\d_]", w) and len(w) <= 4 and " " not in w and w.isascii():
            if re.search(rf"(?<![\w']){re.escape(w)}(?![\w'])", text):
                return w
        elif w in text:
            return w
    return ""


def _praise_word(low):
    for lang, words in _PRAISE.items():
        if lang == "vi":   # "hay" đứng 1 mình còn nghĩa là "hoặc" -> chỉ tính các cụm rõ nghĩa
            w = _has(low, [x for x in words if x != "hay"])
            if not w and re.fullmatch(r"\W*hay\W*", low):
                w = "hay"
        else:
            w = _has(low, words)
        if w:
            return w
    return ""


def classify(text, author_is_owner=False):
    """(loại, lý do) – loại là PRAISE / QUESTION / NEGATIVE / SPAM / MIXED / OTHER / OWNER."""
    if author_is_owner:
        return OWNER, "bình luận của chính kênh"
    raw = unicodedata.normalize("NFC", text or "").strip()
    low = raw.lower().replace("’", "'")
    if not low:
        return OTHER, "trống"
    for rx in _SPAM:
        if re.search(rx, low):
            return SPAM, "có link / quảng cáo / số điện thoại"
    neg = _has(low, _NEG)
    pw = _praise_word(low)
    emo = [ch for ch in raw if ch in _HEART_EMOJI]
    letters = re.sub(r"[\W\d_]+", "", raw)
    if "?" in raw or "？" in raw or re.search(_Q_START, low):
        return QUESTION, "câu hỏi – nên tự trả lời"
    if neg:
        return (MIXED if pw else NEGATIVE), f"có từ chê / góp ý: '{neg}'"
    if pw:
        but = _has(low, _BUT)
        if but and len(low) > 60:
            return MIXED, f"có '{but}' – có thể kèm góp ý, nên tự đọc"
        if re.search(r"(?<![\w'])(not|no|never|isn't|wasn't|không|ko|hindi|dili|saan|no es|nicht|pas)\s+(\w+\s+)?"
                     + re.escape(pw.split()[0]), low):
            return MIXED, f"có phủ định trước '{pw}'"
        return PRAISE, f"khen: '{pw}'"
    if emo and len(letters) <= 2:
        return PRAISE, "chỉ thả biểu tượng cảm xúc tích cực"
    return OTHER, "không rõ là khen"


def analyze(text, author_is_owner=False, default_lang="en"):
    kind, why = classify(text, author_is_owner)
    letters = re.sub(r"[\W\d_]+", "", text or "")
    lang = detect(text, default_lang) if letters else default_lang
    base = THANKS.get(lang, THANKS[default_lang] if default_lang in THANKS else THANKS["en"])[1]
    try:   # nhiều câu cảm ơn khác nhau, nhắc đúng ý người khen, không lặp câu vừa dùng
        import thanks_bank
        reply = thanks_bank.pick(lang if lang in THANKS else default_lang, text, base)
    except Exception:
        reply = base
    return {"kind": kind, "why": why, "lang": lang, "lang_name": lang_name(lang), "reply": reply}


# ------------------------------------------------------------------ chọn TIM hay THÍCH (chỉ 1 trong 2)
# TIM: người xem bày tỏ TÌNH CẢM / CẢM XÚC / LỜI CẢM ƠN với video – hoặc viết lời khen dài, tâm huyết.
# THÍCH: lời khen mang tính đánh giá, ngắn gọn (hay, tuyệt, diễn viên giỏi nhất, good job...).
_HEART_WORDS = [
    # en
    "love", "loved", "loving", "lovely", "favourite", "favorite", "fave", "thank you", "thanks", "thank u", "thx",
    "cried", "crying", "tears", "teared", "touched", "touching", "moving", "heartwarming", "heart warming",
    "masterpiece", "adore", "adored", "god bless", "bless you", "my heart", "made my day", "goosebumps",
    "nostalgi", "memories", "childhood", "grew up", "treasure", "beautiful",
    # vi
    "yêu", "cảm ơn", "cám ơn", "cảm động", "xúc động", "khóc", "thương", "ấm áp", "nổi da gà", "kỷ niệm", "tuổi thơ",
    # tl / ceb / ilo
    "salamat", "nakakaiyak", "mahal", "agyamanak", "ayayatek",
    # es / pt / fr / de / it / nl / id / ...
    "me encanta", "gracias", "amo", "emocion", "amei", "adorei", "obrigad", "merci", "j'adore", "ému", "danke",
    "liebe", "grazie", "adoro", "bedankt", "terima kasih", "menyentuh", "dziękuję", "teşekkür", "спасибо",
    "люблю", "дякую", "ευχαριστώ", "شكرا", "תודה", "धन्यवाद", "ขอบคุณ", "ありがとう", "感動", "감사", "감동", "谢谢",
    "感动",
]
_HEART_EMOJI_STRONG = set("❤♥💕💖💗💓💞💘💝😍🥰😘🫶😭🥲🙏💙💚💛💜🧡🤍")


def react(text):
    """('heart' | 'like', lý do) cho 1 bình luận KHEN – chỉ chọn MỘT trong hai, theo nội dung."""
    raw = unicodedata.normalize("NFC", text or "").strip()
    low = raw.lower().replace("’", "'")
    w = _has(low, _HEART_WORDS)
    if w:
        return "heart", f"bày tỏ tình cảm / cảm ơn: '{w}'"
    emo = next((ch for ch in raw if ch in _HEART_EMOJI_STRONG), "")
    if emo:
        return "heart", f"thả biểu tượng {emo}"
    if len(re.sub(r"\s+", " ", raw)) >= 120:
        return "heart", "lời khen dài, viết tâm huyết"
    return "like", "lời khen ngắn / đánh giá"


def choose_react(text, allow_like=True, allow_heart=True):
    """Hành động sẽ làm (hoặc None) theo các ô bạn tích: tích cả 2 -> tool chọn 1 hợp nội dung."""
    if allow_like and allow_heart:
        return react(text)
    if allow_heart:
        return "heart", "chỉ bật Thả tim"
    if allow_like:
        return "like", "chỉ bật Bấm thích"
    return None, ""


# ------------------------------------------------------------------ AI kiểm tra lại (tùy chọn)
AI_SYSTEM = ("You classify YouTube comments left by viewers on a creator's own videos. "
             "Return ONLY JSON: {\"lang\": ISO 639 code (use 'tl' Tagalog, 'ceb' Bisaya/Cebuano, 'ilo' Ilocano), "
             "\"praise\": true only if the comment clearly compliments or thanks the video/creator with no "
             "complaint, question, request or advertising, \"kind\": one of praise|question|negative|spam|mixed|other}")


def ai_check(text, provider, model, key):
    """Hỏi AI (Ollama / API đã cài ở trang Phân tích video). Lỗi -> None (dùng kết quả của tool)."""
    try:
        import pt_ai
        out = pt_ai.parse_json(pt_ai.call_llm(provider, model, key, AI_SYSTEM, f"Comment:\n{text[:1500]}",
                                              max_tokens=200))
        kind = {"praise": PRAISE, "question": QUESTION, "negative": NEGATIVE, "spam": SPAM, "mixed": MIXED,
                "other": OTHER}.get(str(out.get("kind", "")).lower(), OTHER)
        if kind == PRAISE and out.get("praise") is not True:
            kind = OTHER
        lang = str(out.get("lang") or "").lower().split("-")[0]
        lang = {"fil": "tl", "tgl": "tl", "ms": "id", "zh_cn": "zh"}.get(lang, lang)
        return {"kind": kind, "lang": lang if lang in THANKS else ""}
    except Exception:
        return None
