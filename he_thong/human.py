"""
Thao tác chuột & bàn phím giống người thật.

Sau khi import file này, MỌI lệnh .click() / .fill() / .hover() trong tool
được thay bằng:
  - cuộn tới nút bằng con lăn chuột,
  - di chuột theo đường cong (nhanh ở giữa, chậm khi gần tới),
  - bấm vào 1 điểm ngẫu nhiên gần giữa nút, nhấn - nhả có độ trễ,
  - gõ chữ từng ký tự với tốc độ không đều.
"""
import math
import random
import time

from playwright.sync_api import Locator

SPEED = {"move_steps": (9, 16), "step_ms": (3, 7), "think_ms": (90, 220),
         "press_ms": (40, 90), "type_ms": (25, 70)}

# mũi tên chuột nhỏ hiển thị vị trí chuột của tool trên trang
CURSOR_JS = r"""
(() => {
  if (window.__keoCursor) return;
  window.__keoCursor = true;
  const add = () => {
    if (!document.body) return setTimeout(add, 200);
    const d = document.createElement('div');
    d.id = '__keo_cursor';
    d.style.cssText = 'position:fixed;left:0;top:0;width:18px;height:26px;z-index:2147483647;' +
      'pointer-events:none;display:none;transform-origin:0 0;transition:transform .06s';
    d.innerHTML = '<svg width="18" height="26" viewBox="0 0 18 26" xmlns="http://www.w3.org/2000/svg">' +
      '<path d="M1 1 L1 20 L5.6 15.6 L9 24 L12.2 22.6 L8.8 14.4 L15 14.4 Z" ' +
      'fill="#111" stroke="#fff" stroke-width="1.4" stroke-linejoin="round"/></svg>';
    document.body.appendChild(d);
    document.addEventListener('mousemove', e => {
      d.style.display = 'block'; d.style.left = e.clientX + 'px'; d.style.top = e.clientY + 'px'; }, true);
    document.addEventListener('mousedown', () => d.style.transform = 'scale(.82)', true);
    document.addEventListener('mouseup', () => d.style.transform = 'scale(1)', true);
  };
  add();
})();
"""


BASE_SPEED = dict(SPEED)


def set_speed(factor):
    """factor < 1: nhanh hơn, > 1: chậm hơn (áp cho di chuột, ngập ngừng, bấm, gõ phím)."""
    f = max(0.3, min(3.0, float(factor or 1)))
    for k, (lo, hi) in BASE_SPEED.items():
        SPEED[k] = (lo * f, hi * f) if k != "move_steps" else (max(4, int(lo * min(f, 1.6))), max(6, int(hi * min(f, 1.6))))


def _r(rng):
    return random.uniform(*rng)


def _pos(page):
    return getattr(page, "_keo_mouse", None) or (random.uniform(300, 700), random.uniform(200, 400))


def _viewport(page):
    try:
        w, h = page.evaluate("[window.innerWidth, window.innerHeight]")
        return w, h
    except Exception:
        return 1366, 768


def move_to(page, x, y):
    """Di chuột theo đường cong Bezier, nhanh ở giữa và chậm dần khi tới nơi."""
    x0, y0 = _pos(page)
    dist = math.hypot(x - x0, y - y0)
    steps = int(_r(SPEED["move_steps"]) * min(1.6, max(0.5, dist / 500)))
    # điểm uốn ngẫu nhiên lệch khỏi đường thẳng
    cx = (x0 + x) / 2 + random.uniform(-0.25, 0.25) * dist
    cy = (y0 + y) / 2 + random.uniform(-0.25, 0.25) * dist
    for i in range(1, steps + 1):
        t = i / steps
        t = t * t * (3 - 2 * t)  # nhanh ở giữa, chậm ở hai đầu
        px = (1 - t) ** 2 * x0 + 2 * (1 - t) * t * cx + t ** 2 * x
        py = (1 - t) ** 2 * y0 + 2 * (1 - t) * t * cy + t ** 2 * y
        page.mouse.move(px + random.uniform(-0.6, 0.6), py + random.uniform(-0.6, 0.6))
        time.sleep(_r(SPEED["step_ms"]) / 1000)
    page.mouse.move(x, y)
    page._keo_mouse = (x, y)


def mouse_click(page, x, y):
    """Di chuột tới (x, y), ngập ngừng một chút rồi nhấn - nhả."""
    move_to(page, x, y)
    time.sleep(_r(SPEED["think_ms"]) / 1000)
    page.mouse.down()
    time.sleep(_r(SPEED["press_ms"]) / 1000)
    page.mouse.up()
    time.sleep(random.uniform(0.08, 0.18))


def drag(page, x0, y0, x1, y1):
    """Nhấn giữ tại (x0, y0), kéo tới (x1, y1) rồi thả - như kéo thanh trượt bằng tay."""
    move_to(page, x0, y0)
    time.sleep(random.uniform(0.1, 0.2))
    page.mouse.down()
    time.sleep(random.uniform(0.08, 0.15))
    move_to(page, x1, y1)
    time.sleep(random.uniform(0.08, 0.15))
    page.mouse.up()
    time.sleep(random.uniform(0.15, 0.3))


def bbox(loc, timeout=4000):
    """Vị trí phần tử trên màn hình. Phần tử vừa bị Studio vẽ lại / ẩn đi -> None sau tối đa 4 giây
    (thay vì đứng chờ 30 giây rồi báo lỗi)."""
    for _ in range(2):
        try:
            return loc.bounding_box(timeout=timeout)
        except Exception:
            time.sleep(0.3)
    return None


def _scroll_into_view(page, loc):
    """Cuộn bằng con lăn chuột (đặt chuột trên vùng chứa nút) cho tới khi nút nằm trong màn hình."""
    w, h = _viewport(page)
    last_top = None
    for _ in range(25):
        bb = bbox(loc)
        if not bb:
            return None
        if 70 < bb["y"] and bb["y"] + bb["height"] < h - 40:
            return bb
        if last_top is not None and abs(bb["y"] - last_top) < 2:
            break  # con lăn không cuộn được vùng này -> dùng cách dự phòng
        last_top = bb["y"]
        mx = min(max(bb["x"] + bb["width"] / 2, 40), w - 40)
        move_to(page, mx, h / 2 + random.uniform(-60, 60))
        delta = max(-650, min(650, (bb["y"] - h / 2) * random.uniform(0.6, 0.9)))
        page.mouse.wheel(0, delta)
        time.sleep(random.uniform(0.12, 0.25))
    try:
        loc.scroll_into_view_if_needed(timeout=3000)
        time.sleep(0.2)
    except Exception:
        pass
    return bbox(loc)


HIT_JS = """(e, p) => { const t = document.elementFromPoint(p[0], p[1]);
    return !!t && (e === t || e.contains(t) || t.contains(e)); }"""


def _hits(loc, pt):
    """Điểm (x, y) có đúng là phần tử `loc` (không bị phần tử khác che) không."""
    try:
        return bool(loc.evaluate(HIT_JS, [pt[0], pt[1]]))
    except Exception:
        return True


def _safe_point(page, loc, bb):
    """Chọn điểm bấm nằm trên đúng phần tử. Nếu bị che (vd: nằm dưới mép khung cuộn),
    cuộn phần tử ra giữa khung rồi chọn lại."""
    for attempt in range(3):
        if attempt == 1:
            try:
                loc.scroll_into_view_if_needed(timeout=3000)
            except Exception:
                pass
        elif attempt == 2:
            try:
                loc.evaluate("e => e.scrollIntoView({block: 'center', inline: 'center'})")
            except Exception:
                pass
        if attempt:
            time.sleep(0.35)
            bb = bbox(loc) or bb
        cands = [_target_point(bb) for _ in range(5)] + \
                [(bb["x"] + bb["width"] / 2, bb["y"] + bb["height"] / 2)]
        for pt in cands:
            if _hits(loc, pt):
                return pt
    return None


def _target_point(bb):
    """Điểm bấm ngẫu nhiên trong vùng giữa của nút (tránh mép)."""
    return (bb["x"] + bb["width"] * random.uniform(0.3, 0.7),
            bb["y"] + bb["height"] * random.uniform(0.35, 0.65))


# ---------------------------------------------------------------- thay thế lệnh gốc
_orig_click = Locator.click
_orig_fill = Locator.fill
_orig_hover = Locator.hover


def _human_click(self, *args, timeout=None, force=False, **kw):
    page = self.page
    try:
        self.wait_for(state="visible", timeout=timeout or 15000)
    except Exception:
        if force:
            return _orig_click(self, *args, timeout=timeout, force=True, **kw)
        raise
    bb = _scroll_into_view(page, self)
    if not bb or bb["width"] < 1 or bb["height"] < 1:
        return _orig_click(self, *args, timeout=timeout, force=force, **kw)
    pt = _safe_point(page, self, bb)
    if pt is None:  # phần tử bị che hoàn toàn -> để Playwright tự xử lý (sẽ báo lỗi rõ ràng)
        return _orig_click(self, *args, timeout=timeout, force=force, **kw)
    mouse_click(page, *pt)


def _human_hover(self, *args, timeout=None, **kw):
    page = self.page
    self.wait_for(state="visible", timeout=timeout or 15000)
    bb = _scroll_into_view(page, self)
    if not bb:
        return _orig_hover(self, *args, timeout=timeout, **kw)
    pt = _safe_point(page, self, bb) or _target_point(bb)
    move_to(page, *pt)
    time.sleep(random.uniform(0.1, 0.25))


def _human_fill(self, value, *args, timeout=None, **kw):
    """Bấm vào ô, xóa chữ cũ, rồi gõ từng ký tự."""
    page = self.page
    _human_click(self, timeout=timeout)
    page.keyboard.press("Control+A")
    time.sleep(random.uniform(0.05, 0.12))
    page.keyboard.press("Backspace")
    time.sleep(random.uniform(0.08, 0.18))
    for ch in str(value):
        if ch == "\n":
            page.keyboard.press("Shift+Enter")
        else:
            page.keyboard.type(ch)
        time.sleep(_r(SPEED["type_ms"]) / 1000)
        if random.random() < 0.03:  # thỉnh thoảng ngừng lâu hơn như người đang nghĩ
            time.sleep(random.uniform(0.2, 0.45))
    time.sleep(random.uniform(0.1, 0.25))


def paste(loc, text, retries=3):
    """Bấm vào ô, xóa chữ cũ rồi DÁN cả chuỗi 1 lần (như Ctrl+V) và kiểm tra ô đã đúng nội dung.
    Dùng cho link/ô tìm kiếm: gõ từng ký tự vào ô tìm-ngay-khi-gõ dễ bị chèn sai chữ."""
    page = loc.page
    for _ in range(retries):
        _human_click(loc)
        time.sleep(random.uniform(0.15, 0.3))
        focused = loc.evaluate("e => e === document.activeElement")
        if not focused:
            loc.focus()
            time.sleep(0.2)
            focused = loc.evaluate("e => e === document.activeElement")
        if not focused:
            continue  # KHÔNG bấm Ctrl+A khi con trỏ không ở trong ô (tránh bôi đen cả trang)
        page.keyboard.press("Control+A")
        time.sleep(random.uniform(0.05, 0.12))
        page.keyboard.press("Backspace")
        time.sleep(random.uniform(0.1, 0.2))
        page.keyboard.insert_text(text)
        time.sleep(random.uniform(0.3, 0.5))
        try:
            if (loc.input_value() or "").strip() == text.strip():
                return True
        except Exception:
            return True  # không đọc được giá trị (ô không phải input) -> coi như đã dán
    return False


def install():
    Locator.click = _human_click
    Locator.fill = _human_fill
    Locator.hover = _human_hover


install()
