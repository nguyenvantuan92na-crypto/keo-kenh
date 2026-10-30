"""
Kho câu cảm ơn đa dạng cho bình luận KHEN của khán giả (đúng ngôn ngữ người viết).

- Mỗi ngôn ngữ chính có nhiều câu; câu được chọn xoay vòng, KHÔNG lặp lại câu vừa dùng gần đây.
- Bình luận nhắc tới giọng đọc / câu chuyện / cái kết / âm thanh / nhạc / ... -> câu cảm ơn nhắc đúng ý đó.
- Câu ngắn, tự nhiên, không chèn link, không quảng cáo, tối đa 1–2 emoji.
"""
import random
import re
from collections import deque

_RECENT = deque(maxlen=150)

# ---- câu chung (theo ngôn ngữ)
BANK = {
    "en": [
        "Thank you so much for listening! ❤️",
        "Really glad you enjoyed it – thanks for being here! 🙏",
        "Your kind words mean a lot to us, thank you! 😊",
        "Thanks a million for the support! ❤️",
        "So happy this one made your day – thank you! 🌟",
        "Thank you for watching and for taking the time to comment! 🙏",
        "Comments like yours keep us going – thank you! ❤️",
        "Much appreciated, thank you for listening along! 🎧",
        "We're thrilled you liked it – thanks so much! 😊",
        "Thank you! More stories are on the way, stay tuned 🎧",
        "Lovely to hear that – thanks for your support! 💛",
        "Thank you kindly! Hope you enjoy the next one too 🙏",
        "That's wonderful to hear, thank you! ❤️",
        "Big thanks for listening – it really means a lot! 🌟",
        "Thanks for the lovely comment, glad you're here! 😊",
        "Appreciate you so much – thanks for tuning in! 🎧",
    ],
    "vi": [
        "Cảm ơn bạn rất nhiều đã lắng nghe! ❤️",
        "Rất vui vì bạn thích video này, cảm ơn bạn nhé! 🙏",
        "Lời khen của bạn là động lực lớn với kênh, cảm ơn bạn! 😊",
        "Cảm ơn bạn đã luôn ủng hộ kênh! ❤️",
        "Cảm ơn bạn đã xem và để lại bình luận dễ thương này! 🌟",
        "Kênh sẽ cố gắng ra thêm nhiều video hay nữa, cảm ơn bạn nhé! 🎧",
        "Đọc bình luận của bạn mà vui cả ngày, cảm ơn bạn! 💛",
        "Cảm ơn bạn đã dành thời gian nghe hết video! 🙏",
        "Rất trân trọng sự ủng hộ của bạn, cảm ơn nhiều! ❤️",
        "Cảm ơn bạn! Hẹn gặp bạn ở video tiếp theo nhé 😊",
        "Vui quá khi video làm bạn hài lòng, cảm ơn bạn! 🌟",
        "Cảm ơn bạn đã đồng hành cùng kênh! 🎧",
    ],
    "tl": [
        "Maraming salamat po sa panonood! ❤️",
        "Salamat po sa suporta, sobrang natuwa kami! 🙏",
        "Salamat po sa magandang komento! 😊",
        "Maraming salamat po, abangan ang susunod! 🎧",
        "Nakakataba ng puso, salamat po! ❤️",
        "Salamat po sa pakikinig hanggang dulo! 🌟",
    ],
    "es": [
        "¡Muchas gracias por escuchar! ❤️",
        "¡Qué alegría que te haya gustado, gracias! 🙏",
        "¡Gracias por tu apoyo y tu comentario! 😊",
        "¡Mil gracias! Pronto habrá más historias 🎧",
        "¡Tus palabras nos animan mucho, gracias! 🌟",
        "¡Gracias por estar aquí! ❤️",
    ],
    "pt": [
        "Muito obrigado por assistir! ❤️",
        "Que bom que você gostou, obrigado! 🙏",
        "Obrigado pelo apoio e pelo comentário! 😊",
        "Valeu demais! Tem mais histórias chegando 🎧",
        "Seu comentário nos motiva muito, obrigado! 🌟",
    ],
    "fr": [
        "Merci beaucoup pour l'écoute ! ❤️",
        "Ravi que ça vous ait plu, merci ! 🙏",
        "Merci pour votre soutien et ce gentil message ! 😊",
        "Mille mercis ! D'autres histoires arrivent bientôt 🎧",
        "Vos mots nous font très plaisir, merci ! 🌟",
    ],
    "de": [
        "Vielen Dank fürs Zuhören! ❤️",
        "Schön, dass es dir gefallen hat – danke! 🙏",
        "Danke für die Unterstützung und den lieben Kommentar! 😊",
        "Tausend Dank! Weitere Geschichten folgen bald 🎧",
        "Deine Worte freuen uns sehr, danke! 🌟",
    ],
    "it": [
        "Grazie mille per l'ascolto! ❤️",
        "Felici che ti sia piaciuto, grazie! 🙏",
        "Grazie per il supporto e il bel commento! 😊",
        "Grazie davvero! Altre storie in arrivo 🎧",
    ],
    "id": [
        "Terima kasih banyak sudah menonton! ❤️",
        "Senang sekali kamu suka, terima kasih! 🙏",
        "Terima kasih atas dukungannya! 😊",
        "Makasih ya! Nantikan cerita berikutnya 🎧",
    ],
}

# ---- câu nhắc đúng ý người khen (từ khóa trong bình luận -> câu cảm ơn riêng)
TOPICS = {
    "en": [
        (r"\b(voice|narrat|reader|read(ing)?|actor|acting|cast|performance)", [
            "Thank you! The cast really brought this one to life 🎭",
            "So glad you enjoyed the performances – thank you! 🎧",
            "Thanks! The voices make all the difference, don't they? 😊"]),
        (r"\b(ending|twist|end|finale|climax)", [
            "Thank you! That ending gets everyone 😄",
            "Didn't see that twist coming either? Thanks for listening! 🔎",
            "So glad the ending worked for you – thank you! ❤️"]),
        (r"(mystery|detective|christie|poirot|holmes|murder|whodunit)", [
            "Thank you! A good mystery is hard to beat 🔎",
            "Thanks! Did you guess the culprit before the end? 🔎"]),
        (r"\b(story|stories|plot|tale)", [
            "So glad you enjoyed the story – thanks for listening! 📖",
            "Thanks! Plenty more classic tales coming up 🎧"]),
        (r"\b(sound|music|audio|quality|atmosphere)", [
            "Thank you! The atmosphere is half the fun 🎶",
            "Glad the sound worked for you – thanks for listening! 🎧"]),
        (r"(sleep|relax|bedtime|night|calm)", [
            "Thank you! Sweet dreams and happy listening 🌙",
            "So glad it helped you relax – thank you! 😌"]),
        (r"\b(nostalg|childhood|remember|memories|grew up|old days)", [
            "Thank you! Lovely to bring back those memories 📻",
            "So glad it brought back good memories – thanks! ❤️"]),
    ],
    "vi": [
        (r"(giọng|đọc|diễn|lồng tiếng|diễn viên)", [
            "Cảm ơn bạn! Giọng đọc chính là linh hồn của câu chuyện 🎧",
            "Rất vui vì bạn thích phần diễn xuất, cảm ơn bạn! 🎭"]),
        (r"(cái kết|kết thúc|đoạn cuối|bất ngờ)", [
            "Cảm ơn bạn! Cái kết đó ai nghe cũng bất ngờ 😄",
            "Vui quá khi bạn thích đoạn kết, cảm ơn bạn nhé! ❤️"]),
        (r"(truyện|câu chuyện|cốt truyện|trinh thám|vụ án)", [
            "Cảm ơn bạn! Kênh sẽ có thêm nhiều truyện hay nữa 📖",
            "Rất vui vì bạn thích câu chuyện, cảm ơn bạn! 🔎"]),
        (r"(ngủ|thư giãn|đêm|dễ chịu)", [
            "Cảm ơn bạn! Chúc bạn ngủ ngon và nghe truyện vui 🌙"]),
    ],
}

FALLBACK = {   # ngôn ngữ chưa có kho riêng: câu gốc + vài cách kết khác nhau
    "_ends": ["❤️", "🙏", "😊", "🌟", "🎧"],
}


def remember(lines):
    """Nạp các câu đã gửi ở lần chạy trước (từ binh_luan.db) để lần này không lặp lại."""
    for s in lines or []:
        if s and s not in _RECENT:
            _RECENT.append(s)


def pick(lang, comment="", base="", avoid=None):
    """Chọn 1 câu cảm ơn đúng ngôn ngữ, ưu tiên câu nhắc đúng ý bình luận, KHÔNG lặp câu đã dùng
    (gần đây + `avoid`). Hết câu theo chủ đề thì lấy câu chung chưa dùng."""
    low = (comment or "").lower()
    used = set(_RECENT) | set(avoid or ())
    topic = []
    for rx, lines in TOPICS.get(lang, []):
        if re.search(rx, low):
            topic += lines
    general = list(BANK.get(lang, []))
    if not general and not topic:   # ngôn ngữ khác: câu cảm ơn gốc với cách kết khác nhau
        core = re.sub(r"[\s❤️🙏😊🌟🎧!]+$", "", base or "Thank you so much")
        general = [f"{core}! {e}" for e in FALLBACK["_ends"]]
    fresh = [p for p in topic if p not in used] or [p for p in general if p not in used]
    if not fresh:   # đã dùng hết cả kho: lấy câu dùng LÂU NHẤT rồi
        order = list(_RECENT)
        allp = topic + general
        fresh = sorted(allp, key=lambda p: order.index(p) if p in order else -1)[:1] or allp
    choice = random.choice(fresh)
    if choice in _RECENT:
        _RECENT.remove(choice)
    _RECENT.append(choice)
    return choice
