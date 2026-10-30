"""
Đồ họa cho giao diện: bộ icon vẽ bằng vector (khử răng cưa), nền kim loại, nút bo tròn.

Mỗi icon là danh sách nét vẽ trên lưới 24x24:
    ("l", [x1, y1, x2, y2, ...])     đường gấp khúc
    ("p", [..])                      đa giác (viền)          ("P", [..])  đa giác (tô đặc)
    ("c", cx, cy, r)                 hình tròn (viền)        ("C", cx, cy, r)  hình tròn (tô đặc)
    ("a", cx, cy, r, từ°, tới°)      cung tròn (độ, ngược chiều kim đồng hồ, 0° = bên phải)
    ("r", x1, y1, x2, y2, bo)        chữ nhật bo góc (viền)  ("R", ...)  tô đặc
Cần thư viện Pillow; thiếu Pillow thì giao diện vẫn chạy, chỉ không có icon và hiệu ứng kim loại.
"""
import math

try:
    from PIL import Image, ImageDraw, ImageTk
    HAS_PIL = True
except Exception:  # pragma: no cover
    HAS_PIL = False


def _arc(cx, cy, r, a0, a1, n=None):
    n = n or max(8, int(abs(a1 - a0) / 8))
    pts = []
    for i in range(n + 1):
        a = math.radians(a0 + (a1 - a0) * i / n)
        pts += [cx + r * math.cos(a), cy - r * math.sin(a)]
    return pts


def _ellipse(cx, cy, rx, ry, n=36):
    pts = []
    for i in range(n + 1):
        a = 2 * math.pi * i / n
        pts += [cx + rx * math.cos(a), cy - ry * math.sin(a)]
    return pts


def _crescent():
    """Mặt trăng khuyết: phần đĩa lớn nằm ngoài đĩa nhỏ lệch lên phải."""
    cx, cy, r = 12, 12, 8.5
    ox, oy, orr = 16.5, 7.5, 7
    pts = []
    for i in range(0, 361, 4):
        a = math.radians(i)
        x, y = cx + r * math.cos(a), cy - r * math.sin(a)
        if (x - ox) ** 2 + (y - oy) ** 2 >= orr ** 2:
            pts.append((i, x, y))
    # nối mép trong theo cung của đĩa nhỏ
    out = [v for _, x, y in pts for v in (x, y)]
    if not pts:
        return out
    (_, x0, y0), (_, x1, y1) = pts[-1], pts[0]
    a0 = math.degrees(math.atan2(-(y0 - oy), x0 - ox))
    a1 = math.degrees(math.atan2(-(y1 - oy), x1 - ox))
    if a1 > a0:
        a1 -= 360
    out += _arc(ox, oy, orr, a0, a1)
    return out


ICONS = {
    # --- điều hướng
    "id_card": [("r", 2.5, 4.5, 21.5, 19.5, 2.5), ("c", 8.5, 10.5, 2.3), ("a", 8.5, 17.8, 3.6, 10, 170),
                ("l", [13.5, 10, 18.5, 10]), ("l", [13.5, 14, 17, 14])],
    "rocket": [("p", [12, 2.5, 15.6, 6.5, 16.2, 13.5, 12, 17.5, 7.8, 13.5, 8.4, 6.5, 12, 2.5]),
               ("c", 12, 9.5, 1.9), ("l", [8.2, 12.2, 4.8, 15.4, 5.4, 19.2, 8.6, 16.6]),
               ("l", [15.8, 12.2, 19.2, 15.4, 18.6, 19.2, 15.4, 16.6]), ("l", [10.4, 19.3, 12, 22, 13.6, 19.3])],
    "chart": [("l", [3, 20.5, 21, 20.5]), ("R", 5, 12, 8.6, 20.5, 1), ("R", 10.2, 7, 13.8, 20.5, 1),
              ("R", 15.4, 3.5, 19, 20.5, 1)],
    # --- thẻ / mục
    "bolt": [("P", [13.5, 2, 4.5, 13.6, 11, 13.6, 10, 22, 19.5, 9.8, 13, 9.8])],
    "target": [("c", 12, 12, 9), ("c", 12, 12, 5), ("C", 12, 12, 1.9)],
    "sliders": [("l", [4, 6, 20, 6]), ("l", [4, 12, 20, 12]), ("l", [4, 18, 20, 18]),
                ("C", 9, 6, 2.6), ("C", 15.5, 12, 2.6), ("C", 7.5, 18, 2.6)],
    "layers": [("p", [12, 3, 21, 8, 12, 13, 3, 8, 12, 3]), ("l", [3, 12.2, 12, 17.2, 21, 12.2]),
               ("l", [3, 16.4, 12, 21.4, 21, 16.4])],
    "checklist": [("l", [3, 6.2, 5, 8.2, 8.4, 4.4]), ("l", [11.5, 6.4, 21, 6.4]),
                  ("l", [3, 13.2, 5, 15.2, 8.4, 11.4]), ("l", [11.5, 13.4, 21, 13.4]),
                  ("C", 5.5, 19.8, 1.5), ("l", [11.5, 19.8, 21, 19.8])],
    "magnet": [("l", [5, 3.5, 5, 12] + _arc(12, 12, 7, 180, 360)[2:] + [19, 3.5]),
               ("l", [9.4, 3.5, 9.4, 12] + _arc(12, 12, 2.6, 180, 360)[2:] + [14.6, 3.5]),
               ("l", [5, 7.4, 9.4, 7.4]), ("l", [14.6, 7.4, 19, 7.4])],
    "list_video": [("l", [3.5, 6, 14.5, 6]), ("l", [3.5, 11.5, 14.5, 11.5]), ("l", [3.5, 17, 10, 17]),
                   ("P", [15, 12.5, 15, 21.5, 22, 17])],
    "terminal": [("r", 2.5, 4, 21.5, 20, 2.5), ("l", [6.5, 9, 10, 12, 6.5, 15]), ("l", [12, 15.5, 17.5, 15.5])],
    # --- bước chuẩn bị
    "key": [("c", 7.5, 15.5, 4.3), ("l", [10.6, 12.4, 20, 3]), ("l", [16.2, 6.8, 19, 9.6]),
            ("l", [13.6, 9.4, 15.8, 11.6])],
    "user_plus": [("c", 9, 8, 3.8), ("a", 9, 21, 6.6, 15, 165), ("l", [19, 7.5, 19, 14.5]),
                  ("l", [15.5, 11, 22.5, 11])],
    "wand": [("l", [3.5, 20.5, 14.5, 9.5]), ("l", [12.6, 7.6, 16.4, 11.4]), ("l", [18, 2.5, 18, 7]),
             ("l", [15.8, 4.8, 20.2, 4.8]), ("l", [20.5, 11, 20.5, 14]), ("l", [19, 12.5, 22, 12.5]),
             ("l", [8.5, 2.5, 8.5, 5.5]), ("l", [7, 4, 10, 4])],
    "search_trend": [("c", 10.5, 10.5, 7), ("l", [15.6, 15.6, 21, 21]), ("l", [6.8, 12.6, 9.4, 10, 11.2, 11.8, 14.2, 8.6])],
    # --- các bước kéo
    "comment_pin": [("r", 2.5, 3.5, 21.5, 16.5, 3), ("P", [7, 15.5, 7, 21, 12.5, 15.5]),
                    ("l", [7, 8.3, 17, 8.3]), ("l", [7, 11.8, 13.5, 11.8])],
    "reply": [("r", 2.5, 3.5, 21.5, 16.5, 3), ("P", [7, 15.5, 7, 21, 12.5, 15.5]),
              ("l", [14.5, 6.6, 10.5, 10, 14.5, 13.4])],
    "heart": [("p", [12, 20, 4.2, 12.6, 3.2, 8.8, 5, 5.6, 8.4, 4.6, 12, 7.6, 15.6, 4.6, 19, 5.6, 20.8, 8.8,
                     19.8, 12.6, 12, 20])],
    "endscreen": [("r", 2, 3.5, 22, 18, 2.2), ("R", 5, 6.8, 11.2, 12.6, 1), ("R", 12.8, 6.8, 19, 12.6, 1),
                  ("l", [8.5, 21, 15.5, 21])],
    "info_card": [("c", 12, 12, 9), ("l", [12, 11, 12, 16.8]), ("C", 12, 7.6, 1.35)],
    "collab": [("c", 8.5, 8, 3.4), ("a", 8.5, 20.6, 6, 15, 165), ("c", 16.8, 9, 2.7),
               ("l", [15.2, 14.2] + _arc(16.8, 20.2, 5, 70, 15)[2:])],
    # --- nút hành động
    "play": [("P", [7, 4, 7, 20, 20, 12])],
    "play_all": [("P", [2.5, 5, 2.5, 19, 11.5, 12]), ("P", [12, 5, 12, 19, 21, 12])],
    "save": [("r", 4, 4, 20, 20, 2.2), ("l", [8, 4, 8, 9, 15, 9, 15, 4]), ("r", 7.5, 13.5, 16.5, 20, 1)],
    "check": [("l", [4.5, 12.5, 9.5, 17.5, 19.5, 6.5])],
    "plus": [("l", [12, 5, 12, 19]), ("l", [5, 12, 19, 12])],
    "copy": [("r", 8.5, 8.5, 20.5, 20.5, 2), ("l", [15.5, 8.5, 15.5, 5.5, 14, 3.5, 5.5, 3.5, 3.5, 5.5, 3.5, 14,
                                                    5.5, 15.5, 8.5, 15.5])],
    "arrow_up": [("l", [12, 19.5, 12, 5]), ("l", [6, 11, 12, 5, 18, 11])],
    "arrow_down": [("l", [12, 4.5, 12, 19]), ("l", [6, 13, 12, 19, 18, 13])],
    "trash": [("l", [4, 6.8, 20, 6.8]), ("l", [6, 6.8, 7, 20.5, 17, 20.5, 18, 6.8]),
              ("l", [9, 6.8, 9, 3.8, 15, 3.8, 15, 6.8]), ("l", [10.2, 10.8, 10.2, 16.5]), ("l", [13.8, 10.8, 13.8, 16.5])],
    "list_x": [("l", [3.5, 6, 15, 6]), ("l", [3.5, 11.5, 15, 11.5]), ("l", [3.5, 17, 10, 17]),
               ("l", [14.5, 14.5, 20.5, 20.5]), ("l", [20.5, 14.5, 14.5, 20.5])],
    "eraser": [("p", [8.5, 20, 3, 14.5, 13, 4.5, 21, 12.5, 12.5, 20, 8.5, 20]), ("l", [8, 9.5, 15.5, 17]),
               ("l", [12.5, 20, 21, 20])],
    "stop": [("R", 6, 6, 18, 18, 2.4)],
    "refresh": [("l", _arc(12, 12, 8, 50, 330)), ("l", [17.3, 2.6, 17.4, 6.8, 13.3, 7.4])],
    "table": [("r", 3, 3.5, 21, 20.5, 2.2), ("l", [3, 9.3, 21, 9.3]), ("l", [3, 14.9, 21, 14.9]),
              ("l", [9.5, 3.5, 9.5, 20.5])],
    "folder": [("p", [3, 5, 9.6, 5, 11.8, 7.8, 21, 7.8, 21, 19, 3, 19, 3, 5]), ("l", [3, 10.6, 21, 10.6])],
    "undo": [("l", [8.5, 4, 3.8, 8.8, 8.5, 13.6]), ("l", [3.8, 8.8, 14.5, 8.8] + _arc(14.5, 14.3, 5.5, 90, -90)[2:]
                                                     + [9, 19.8])],
    "record": [("c", 12, 12, 9), ("C", 12, 12, 4.6)],
    "package": [("p", [12, 2.5, 21, 7.2, 21, 16.8, 12, 21.5, 3, 16.8, 3, 7.2, 12, 2.5]),
                ("l", [3, 7.2, 12, 12, 21, 7.2]), ("l", [12, 12, 12, 21.5]), ("l", [7.5, 4.8, 16.5, 9.6])],
    "swap": [("l", [3.5, 8, 19, 8]), ("l", [15, 4, 19, 8, 15, 12]), ("l", [20.5, 16, 5, 16]),
             ("l", [9, 12, 5, 16, 9, 20])],
    "history": [("l", _arc(12, 12, 8.5, 160, -160)), ("l", [2.6, 8, 3.8, 12.6, 8.2, 11.4]),
                ("l", [12, 7.5, 12, 12, 15.2, 14.2])],
    "eye_off": [("l", _ellipse(12, 12, 9.5, 5.6)), ("c", 12, 12, 2.6), ("l", [4, 4, 20, 20])],
    "pencil": [("p", [15.5, 4, 20, 8.5, 9, 19.5, 3.8, 20.2, 4.5, 15, 15.5, 4]), ("l", [13, 6.5, 17.5, 11])],
    # --- trạng thái
    "check_circle": [("c", 12, 12, 9), ("l", [7.8, 12.3, 10.8, 15.3, 16.4, 9.2])],
    "warn": [("p", [12, 3.2, 21.8, 20, 2.2, 20, 12, 3.2]), ("l", [12, 9.2, 12, 13.8]), ("C", 12, 16.8, 1.3)],
    "x": [("l", [6, 6, 18, 18]), ("l", [18, 6, 6, 18])],
    "minus": [("l", [5, 12, 19, 12])],
    "bell": [("p", [6, 16.5, 6, 10.5, 9, 6, 12, 5.2, 15, 6, 18, 10.5, 18, 16.5, 19.5, 18, 4.5, 18, 6, 16.5]),
             ("l", [10.2, 20.5, 13.8, 20.5])],
    "x_circle": [("c", 12, 12, 9), ("l", [8.8, 8.8, 15.2, 15.2]), ("l", [15.2, 8.8, 8.8, 15.2])],
    "sun": [("c", 12, 12, 4.4)] + [("l", [12 + 7 * math.cos(math.radians(a)), 12 - 7 * math.sin(math.radians(a)),
                                          12 + 9.6 * math.cos(math.radians(a)), 12 - 9.6 * math.sin(math.radians(a))])
                                   for a in range(0, 360, 45)],
    "moon": [("P", _crescent())],
}


# ============================================================ vẽ
_cache = {}


def _rgb(hexcolor, alpha=255):
    h = hexcolor.lstrip("#")
    return (int(h[0:2], 16), int(h[2:4], 16), int(h[4:6], 16), alpha)


def _draw_shapes(d, shapes, s, ox, oy, col, w):
    """Vẽ các nét lên ImageDraw ở tỉ lệ `s` (pixel / đơn vị), gốc (ox, oy)."""
    P = lambda pts: [(ox + pts[i] * s, oy + pts[i + 1] * s) for i in range(0, len(pts), 2)]
    rr = w / 2

    def line(pts, closed=False):
        pp = P(pts)
        if closed and pp[0] != pp[-1]:
            pp.append(pp[0])
        d.line(pp, fill=col, width=int(round(w)), joint="curve")
        for x, y in pp:  # đầu & khớp nối tròn
            d.ellipse([x - rr, y - rr, x + rr, y + rr], fill=col)

    for sh in shapes:
        k = sh[0]
        if k == "l":
            line(sh[1])
        elif k == "p":
            line(sh[1], closed=True)
        elif k == "P":
            d.polygon(P(sh[1]), fill=col)
        elif k in ("c", "C"):
            _, cx, cy, r = sh
            box = [ox + (cx - r) * s, oy + (cy - r) * s, ox + (cx + r) * s, oy + (cy + r) * s]
            if k == "C":
                d.ellipse(box, fill=col)
            else:
                d.ellipse(box, outline=col, width=int(round(w)))
        elif k == "a":
            _, cx, cy, r, a0, a1 = sh
            line(_arc(cx, cy, r, a0, a1))
        elif k in ("r", "R"):
            _, x1, y1, x2, y2, rad = sh
            box = [ox + x1 * s, oy + y1 * s, ox + x2 * s, oy + y2 * s]
            if k == "R":
                d.rounded_rectangle(box, radius=rad * s, fill=col)
            else:
                d.rounded_rectangle(box, radius=rad * s, outline=col, width=int(round(w)))


def _render(name, px, color, stroke=2.0, ss=4):
    big = px * ss
    img = Image.new("RGBA", (big, big), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    s = big / 24.0
    _draw_shapes(d, ICONS[name], s, 0, 0, _rgb(color), stroke * s)
    return img.resize((px, px), Image.LANCZOS)


def icon(name, size=16, color="#FFFFFF", stroke=2.0):
    """Icon trong suốt (PhotoImage) hoặc None khi không có Pillow / không có icon."""
    if not HAS_PIL or not name or name not in ICONS:
        return None
    key = ("i", name, size, color, stroke)
    if key not in _cache:
        _cache[key] = ImageTk.PhotoImage(_render(name, size, color, stroke))
    return _cache[key]


def badge(name, size, color, tint_alpha=46, radius=None, glyph=0.56, stroke=2.1, solid=False):
    """Ô vuông bo góc nền màu nhạt (trong suốt) + icon cùng màu ở giữa. solid=True: nền đặc, icon trắng."""
    if not HAS_PIL or not name or name not in ICONS:
        return None
    key = ("b", name, size, color, tint_alpha, radius, glyph, solid)
    if key in _cache:
        return _cache[key]
    ss = 4
    big = size * ss
    img = Image.new("RGBA", (big, big), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    rad = (radius if radius is not None else size * 0.3) * ss
    if solid:
        top, bot = _rgb(_shade(color, 0.18)), _rgb(_shade(color, -0.18))
        grad = Image.new("RGBA", (big, big))
        gd = ImageDraw.Draw(grad)
        for y in range(big):
            t = y / max(1, big - 1)
            gd.line([(0, y), (big, y)], fill=tuple(int(top[i] + (bot[i] - top[i]) * t) for i in range(4)))
        mask = Image.new("L", (big, big), 0)
        ImageDraw.Draw(mask).rounded_rectangle([0, 0, big - 1, big - 1], radius=rad, fill=255)
        img.paste(grad, (0, 0), mask)
        # viền sáng phía trên (ánh kim)
        hl = Image.new("L", (big, big), 0)
        ImageDraw.Draw(hl).rounded_rectangle([0, 0, big - 1, big - 1], radius=rad, outline=110, width=ss)
        hl.paste(0, (0, big // 2, big, big))
        img.paste((255, 255, 255, 255), (0, 0), hl)
        fg = "#FFFFFF"
    else:
        d.rounded_rectangle([0, 0, big - 1, big - 1], radius=rad, fill=_rgb(color, tint_alpha))
        d.rounded_rectangle([0, 0, big - 1, big - 1], radius=rad, outline=_rgb(color, min(255, tint_alpha + 40)),
                            width=max(1, ss // 2))
        fg = color
    g = big * glyph
    s = g / 24.0
    off = (big - g) / 2
    _draw_shapes(d if not solid else ImageDraw.Draw(img), ICONS[name], s, off, off, _rgb(fg), stroke * s)
    out = img.resize((size, size), Image.LANCZOS)
    _cache[key] = ImageTk.PhotoImage(out)
    return _cache[key]


def _shade(hexcolor, amt):
    """amt > 0: sáng hơn; amt < 0: tối hơn."""
    r, g, b, _ = _rgb(hexcolor)
    if amt >= 0:
        r, g, b = (int(c + (255 - c) * amt) for c in (r, g, b))
    else:
        r, g, b = (int(c * (1 + amt)) for c in (r, g, b))
    return f"#{r:02X}{g:02X}{b:02X}"


shade = _shade


def mix(a, b, t):
    ra, ga, ba, _ = _rgb(a)
    rb, gb, bb, _ = _rgb(b)
    return "#%02X%02X%02X" % (int(ra + (rb - ra) * t), int(ga + (gb - ga) * t), int(ba + (bb - ba) * t))


def metal(w, h, top, bottom, sheen=0.10, grain=0.05, sheen_angle=True, light=False):
    """Nền kim loại xước: chuyển màu dọc + vệt sáng chéo + vân xước ngang mảnh."""
    if not HAS_PIL or w < 2 or h < 2:
        return None
    key = ("m", w, h, top, bottom, sheen, grain, sheen_angle)
    if key in _cache:
        return _cache[key]
    base = Image.new("RGB", (1, 256))
    t0, t1 = _rgb(top), _rgb(bottom)
    for y in range(256):
        t = y / 255
        base.putpixel((0, y), tuple(int(t0[i] + (t1[i] - t0[i]) * t) for i in range(3)))
    img = base.resize((w, h), Image.BILINEAR)
    if sheen:
        # vệt sáng chéo mềm
        m = Image.new("L", (256, 256), 0)
        md = ImageDraw.Draw(m)
        for x in range(256):
            v = math.exp(-((x - 90) / 38.0) ** 2) * 255 * sheen + math.exp(-((x - 175) / 14.0) ** 2) * 255 * sheen * 0.5
            md.line([(x, 0), (x, 255)], fill=int(v))
        if sheen_angle:
            m = m.rotate(-28, resample=Image.BILINEAR, expand=False)
        m = m.resize((w, h), Image.BILINEAR)
        img.paste((255, 255, 255) if not light else (255, 255, 255), (0, 0), m)
    if grain:
        try:
            n = Image.effect_noise((max(1, w // 6), h), 64).resize((w, h), Image.BILINEAR)
            n = n.point(lambda v: int(abs(v - 128) * grain * 2))
            img.paste((255, 255, 255) if not light else (0, 0, 0), (0, 0), n)
        except Exception:
            pass
    ph = ImageTk.PhotoImage(img)
    _cache[key] = ph
    return ph


def banner(w, h, top, bottom, accents, radius=14, light=False, card_bg=None):
    """Băng tiêu đề kim loại bo góc, dưới đáy có dải màu chuyển nhiều sắc."""
    if not HAS_PIL or w < 20 or h < 20:
        return None
    key = ("ban", w, h, top, bottom, tuple(accents), radius, light, card_bg)
    if key in _cache:
        return _cache[key]
    base = Image.new("RGB", (1, 256))
    t0, t1 = _rgb(top), _rgb(bottom)
    for y in range(256):
        t = y / 255
        base.putpixel((0, y), tuple(int(t0[i] + (t1[i] - t0[i]) * t) for i in range(3)))
    img = base.resize((w, h), Image.BILINEAR).convert("RGBA")
    # vệt sáng chéo
    m = Image.new("L", (256, 64), 0)
    md = ImageDraw.Draw(m)
    for x in range(256):
        v = math.exp(-((x - 150) / 30.0) ** 2) * (34 if not light else 70) + math.exp(-((x - 196) / 9.0) ** 2) * 18
        md.line([(x, 0), (x, 63)], fill=int(v))
    m = m.resize((w, h), Image.BILINEAR)
    img.paste((255, 255, 255, 255), (0, 0), m)
    try:  # vân xước kim loại
        n = Image.effect_noise((max(1, w // 8), h), 64).resize((w, h), Image.BILINEAR)
        n = n.point(lambda v: int(abs(v - 128) * (0.10 if not light else 0.06)))
        img.paste((255, 255, 255, 255) if not light else (0, 0, 0, 255), (0, 0), n)
    except Exception:
        pass
    # dải màu đáy
    stripe = Image.new("RGBA", (max(2, len(accents) * 64), 1))
    for x in range(stripe.width):
        p = x / (stripe.width - 1) * (len(accents) - 1)
        i = min(int(p), len(accents) - 2)
        a, b = _rgb(accents[i]), _rgb(accents[i + 1])
        t = p - i
        stripe.putpixel((x, 0), tuple(int(a[k] + (b[k] - a[k]) * t) for k in range(4)))
    stripe = stripe.resize((w, 3), Image.BILINEAR)
    img.paste(stripe, (0, h - 3))
    # viền sáng mảnh phía trên
    ImageDraw.Draw(img).line([(radius, 0), (w - radius, 0)], fill=(255, 255, 255, 46 if not light else 255))
    # bo góc
    ss = 3
    mask = Image.new("L", (w * ss, h * ss), 0)
    ImageDraw.Draw(mask).rounded_rectangle([0, 0, w * ss - 1, h * ss - 1], radius=radius * ss, fill=255)
    mask = mask.resize((w, h), Image.LANCZOS)
    out = Image.new("RGBA", (w, h), (0, 0, 0, 0) if card_bg is None else _rgb(card_bg))
    out.paste(img, (0, 0), mask)
    _cache[key] = ImageTk.PhotoImage(out)
    return _cache[key]


def pill(w, h, left, right, radius=None, bg=None, glow=0):
    """Dải bo tròn chuyển màu ngang (dùng cho mục đang chọn ở thanh bên, công tắc sáng/tối)."""
    if not HAS_PIL:
        return None
    key = ("pill", w, h, left, right, radius, bg)
    if key in _cache:
        return _cache[key]
    ss = 3
    W, H = w * ss, h * ss
    grad = Image.new("RGBA", (W, 1))
    a, b = _rgb(left), _rgb(right)
    for x in range(W):
        t = x / max(1, W - 1)
        grad.putpixel((x, 0), tuple(int(a[i] + (b[i] - a[i]) * t) for i in range(4)))
    grad = grad.resize((W, H))
    mask = Image.new("L", (W, H), 0)
    r = (radius if radius is not None else h / 2) * ss
    ImageDraw.Draw(mask).rounded_rectangle([0, 0, W - 1, H - 1], radius=r, fill=255)
    img = Image.new("RGBA", (W, H), (0, 0, 0, 0) if bg is None else _rgb(bg))
    img.paste(grad, (0, 0), mask)
    hl = Image.new("L", (W, H), 0)
    ImageDraw.Draw(hl).rounded_rectangle([0, 0, W - 1, H - 1], radius=r, outline=90, width=ss)
    hl.paste(0, (0, H // 2, W, H))
    img.paste((255, 255, 255, 255), (0, 0), hl)
    out = img.resize((w, h), Image.LANCZOS)
    _cache[key] = ImageTk.PhotoImage(out)
    return _cache[key]


def logo(size=40):
    """Biểu tượng ứng dụng: nút play đỏ kiểu YouTube, nền chuyển màu + viền ánh kim."""
    if not HAS_PIL:
        return None
    key = ("logo", size)
    if key in _cache:
        return _cache[key]
    ss = 4
    S = size * ss
    img = Image.new("RGBA", (S, S), (0, 0, 0, 0))
    grad = Image.new("RGBA", (1, S))
    top, bot = _rgb("#FF5A5F"), _rgb("#C4161C")
    for y in range(S):
        t = y / (S - 1)
        grad.putpixel((0, y), tuple(int(top[i] + (bot[i] - top[i]) * t) for i in range(4)))
    grad = grad.resize((S, S))
    mask = Image.new("L", (S, S), 0)
    ImageDraw.Draw(mask).rounded_rectangle([0, int(S * .12), S - 1, int(S * .88)], radius=S * 0.24, fill=255)
    img.paste(grad, (0, 0), mask)
    d = ImageDraw.Draw(img)
    d.rounded_rectangle([0, int(S * .12), S - 1, int(S * .88)], radius=S * 0.24, outline=(255, 210, 140, 150),
                        width=ss * 2)
    d.polygon([(S * .40, S * .33), (S * .40, S * .67), (S * .69, S * .50)], fill=(255, 255, 255, 255))
    out = img.resize((size, size), Image.LANCZOS)
    _cache[key] = ImageTk.PhotoImage(out)
    return _cache[key]


def preview_sheet(path, names=None, size=32, color="#E6B450", bg="#15171C"):
    """Tạo bảng xem trước toàn bộ icon (dùng khi kiểm tra)."""
    names = names or list(ICONS)
    cols = 8
    rows = (len(names) + cols - 1) // cols
    cell = size + 28
    sheet = Image.new("RGBA", (cols * cell, rows * cell), _rgb(bg))
    for i, n in enumerate(names):
        im = _render(n, size, color)
        x, y = (i % cols) * cell + 14, (i // cols) * cell + 6
        sheet.paste(im, (x, y), im)
        ImageDraw.Draw(sheet).text((x - 10, y + size + 4), n[:11], fill=(160, 160, 170, 255))
    sheet.save(path)


def hgrad(w, h, left, right, radius=6, fade_at=0.88):
    """Nền chuyển màu ngang, KHÔNG viền sáng: mục menu đang mở (màu mục 30% -> trong suốt ở 88% chiều ngang)."""
    if not HAS_PIL:
        return None
    key = ("hgrad", w, h, left, right, radius, fade_at)
    if key in _cache:
        return _cache[key]
    ss = 3
    W, H = w * ss, h * ss
    a, b = _rgb(left), _rgb(right)
    grad = Image.new("RGBA", (W, 1))
    for x in range(W):
        t = min(1.0, x / max(1, (W - 1) * fade_at))
        grad.putpixel((x, 0), tuple(int(a[i] + (b[i] - a[i]) * t) for i in range(4)))
    grad = grad.resize((W, H))
    mask = Image.new("L", (W, H), 0)
    ImageDraw.Draw(mask).rounded_rectangle([0, 0, W - 1, H - 1], radius=radius * ss, fill=255)
    img = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    img.paste(grad, (0, 0), mask)
    out = ImageTk.PhotoImage(img.resize((w, h), Image.LANCZOS))
    _cache[key] = out
    return out


def brand_mark(size, c1, c2, radius=6):
    """Logo vuông bo góc nền gradient (xanh -> tím, chéo 145°) + nút play trắng."""
    if not HAS_PIL:
        return None
    key = ("brand", size, c1, c2, radius)
    if key in _cache:
        return _cache[key]
    ss = 4
    S = size * ss
    a, b = _rgb(c1), _rgb(c2)
    grad = Image.new("RGBA", (S, S))
    px = grad.load()
    for y in range(S):
        for x in range(S):
            t = (x + y) / (2 * (S - 1))
            px[x, y] = tuple(int(a[i] + (b[i] - a[i]) * t) for i in range(4))
    mask = Image.new("L", (S, S), 0)
    ImageDraw.Draw(mask).rounded_rectangle([0, 0, S - 1, S - 1], radius=radius * ss, fill=255)
    img = Image.new("RGBA", (S, S), (0, 0, 0, 0))
    img.paste(grad, (0, 0), mask)
    d = ImageDraw.Draw(img)
    d.polygon([(S * 0.38, S * 0.28), (S * 0.38, S * 0.72), (S * 0.74, S * 0.5)], fill=(255, 255, 255, 255))
    out = ImageTk.PhotoImage(img.resize((size, size), Image.LANCZOS))
    _cache[key] = out
    return out


def rounded(w, h, fill, outline=None, radius=10, width=1):
    """Khung bo góc (dùng cho thẻ số liệu / công tắc)."""
    if not HAS_PIL:
        return None
    key = ("round", w, h, fill, outline, radius, width)
    if key in _cache:
        return _cache[key]
    ss = 3
    img = Image.new("RGBA", (w * ss, h * ss), (0, 0, 0, 0))
    ImageDraw.Draw(img).rounded_rectangle([0, 0, w * ss - 1, h * ss - 1], radius=radius * ss, fill=_rgb(fill),
                                          outline=_rgb(outline) if outline else None, width=width * ss)
    out = ImageTk.PhotoImage(img.resize((w, h), Image.LANCZOS))
    _cache[key] = out
    return out


def file_icon(path, size):
    """Ảnh icon của tool (icon/keo_kenh.png) thu nhỏ cho giao diện."""
    if not HAS_PIL:
        return None
    key = ("file", path, size)
    if key in _cache:
        return _cache[key]
    try:
        out = ImageTk.PhotoImage(Image.open(path).convert("RGBA").resize((size, size), Image.LANCZOS))
    except Exception:
        return None
    _cache[key] = out
    return out


def app_logo(size):
    """Icon của tool vẽ riêng đúng `size` px (sắc nét, không thu nhỏ từ ảnh lớn)."""
    if not HAS_PIL:
        return None
    key = ("applogo", size)
    if key in _cache:
        return _cache[key]
    try:
        import app_icon
        out = ImageTk.PhotoImage(app_icon.render(size))
    except Exception:
        return None
    _cache[key] = out
    return out
