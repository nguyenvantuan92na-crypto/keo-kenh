"""
Icon của tool "Kéo Kênh": kênh mạnh (chấm đặc) → mũi tên → kênh cần kéo (vòng tròn), trên ô vuông bo góc
chuyển màu xanh → tím.

Mỗi cỡ được VẼ RIÊNG đúng kích thước (không thu nhỏ từ ảnh lớn) để luôn sắc nét:
- cỡ nhỏ (<= 32px): hình rút gọn, nét đậm, làm sắc cạnh;
- cỡ lớn: thêm quầng sáng nhẹ quanh hình trắng (phát sáng) và viền sáng mảnh quanh ô.
Chạy trực tiếp file này để tạo lại icon/keo_kenh.ico + icon/keo_kenh.png.
"""
import os

from PIL import Image, ImageDraw, ImageFilter

C1, C2 = (0x25, 0x63, 0xEB), (0x7C, 0x3A, 0xED)   # xanh dương đậm -> tím rực (cùng tông xanh–tím, tương phản cao)
WHITE = (255, 255, 255, 255)
ICO_SIZES = [16, 20, 24, 28, 30, 32, 36, 40, 48, 56, 60, 64, 72, 80, 96, 128, 256]


def _gradient(n):
    g = Image.new("RGBA", (n, n))
    px = g.load()
    for y in range(n):
        for x in range(n):
            t = (x + y) / (2 * (n - 1))
            px[x, y] = tuple(int(C1[i] + (C2[i] - C1[i]) * t) for i in range(3)) + (255,)
    return g


def _glyph(n, small):
    """Lớp hình trắng (L mask) cỡ n×n: chấm đặc → mũi tên → vòng tròn."""
    m = Image.new("L", (n, n), 0)
    d = ImageDraw.Draw(m)
    u, cy = n / 1024, n / 2
    if small:
        r1, cx1 = 138 * u, 222 * u
        r2, th, cx2 = 178 * u, 88 * u, 792 * u
    else:
        r1, cx1 = 124 * u, 232 * u
        r2, th, cx2 = 168 * u, 66 * u, 784 * u
    d.ellipse([cx1 - r1, cy - r1, cx1 + r1, cy + r1], fill=255)
    d.ellipse([cx2 - r2, cy - r2, cx2 + r2, cy + r2], fill=255)
    ri = r2 - th
    d.ellipse([cx2 - ri, cy - ri, cx2 + ri, cy + ri], fill=0)
    gap = (38 if small else 40) * u
    x0, tip = cx1 + r1 + gap, cx2 - r2 - gap
    if small:   # cỡ nhỏ: chỉ đầu mũi tên tam giác to
        h = (tip - x0) * 0.62
        d.polygon([(tip, cy), (x0, cy - h), (x0, cy + h)], fill=255)
    else:
        head, sh = 104 * u, 46 * u
        d.rounded_rectangle([x0, cy - sh / 2, tip - head + 10 * u, cy + sh / 2], radius=sh / 2, fill=255)
        d.polygon([(tip, cy), (tip - head, cy - head * 0.82), (tip - head, cy + head * 0.82)], fill=255)
    return m


def render(size):
    """Icon đúng `size`×`size` px, vẽ riêng cho cỡ đó."""
    small = size <= 32
    ss = 8 if size <= 64 else 4 if size <= 128 else 2
    n = size * ss
    pad = round(n * (0.03 if small else 0.04))
    rad = round(n * 0.22)
    shape = Image.new("L", (n, n), 0)
    ImageDraw.Draw(shape).rounded_rectangle([pad, pad, n - pad - 1, n - pad - 1], radius=rad, fill=255)
    img = Image.new("RGBA", (n, n), (0, 0, 0, 0))
    img.paste(_gradient(n), (0, 0), shape)
    glyph = _glyph(n, small)
    if not small:   # quầng sáng (phát sáng) quanh hình trắng
        glow = glyph.filter(ImageFilter.GaussianBlur(n * 0.035)).point(lambda v: int(v * 0.55))
        img.paste((190, 225, 255, 255), (0, 0), Image.composite(glow, Image.new("L", (n, n), 0), shape))
        # viền sáng mảnh quanh ô (cạnh sắc, chuyên nghiệp)
        rim = Image.new("L", (n, n), 0)
        ImageDraw.Draw(rim).rounded_rectangle([pad, pad, n - pad - 1, n - pad - 1], radius=rad,
                                              outline=70, width=max(1, round(n * 0.008)))
        img.paste(WHITE, (0, 0), rim)
    img.paste(WHITE, (0, 0), glyph)
    out = img.resize((size, size), Image.BOX)       # BOX: trung bình điểm ảnh, không gợn / nhòe
    if size <= 64:
        out = out.filter(ImageFilter.UnsharpMask(radius=0.6, percent=140, threshold=0))
    return out


def build(folder):
    os.makedirs(folder, exist_ok=True)
    imgs = {s: render(s) for s in ICO_SIZES}
    imgs[256].save(os.path.join(folder, "keo_kenh.png"))
    imgs[256].save(os.path.join(folder, "keo_kenh.ico"), format="ICO", sizes=[(s, s) for s in ICO_SIZES],
                   append_images=[imgs[s] for s in ICO_SIZES if s != 256])
    return imgs


if __name__ == "__main__":
    build(os.path.join(os.path.dirname(os.path.abspath(__file__)), "icon"))
    print("Đã tạo icon/keo_kenh.ico và icon/keo_kenh.png")
