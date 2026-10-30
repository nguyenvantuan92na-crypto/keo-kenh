"""
GỠ SẠCH phần tool đã kéo trên KÊNH MẠNH – đúng từng mục, đúng vị trí, có kiểm tra lại sau khi gỡ.

Nguyên tắc an toàn:
- Chỉ gỡ đúng thứ tool đã gắn (đối chiếu mã video / nội dung / link đã ghi trong nhật ký).
- Thứ đang có trên kênh KHÁC với thứ tool gắn (có người đã sửa) -> KHÔNG đụng, báo "Gỡ thủ công".
- Sau khi gỡ, tool mở lại đúng chỗ đó kiểm tra: còn sót -> báo lỗi (không bao giờ báo "đã gỡ" khi chưa sạch).
- Mục đã không còn trên kênh (bị gỡ từ trước) -> tính là đã sạch.
Mọi hàm trả về câu mô tả (đã gỡ / đã sạch sẵn); lỗi -> StepError; cần người xem -> NeedsCheck.
"""
import re

import editors
import studio
import human  # noqa: F401
from labels import L
from studio import (STUDIO, NeedsCheck, StepError, _collab_boxes, _delete_post, _delete_thread, _existing_posts,
                    _handle, _home_section, _ids_in, _remove_profile_links, _save_video_page, _say, _show_more,
                    _scroll_to_comments, _vid_of, _visible_list, click, close_dialogs, dialog, open_editor_panel,
                    set_home_video, video_id, _dialog_button)

GONE = "đã sạch – trên kênh không còn mục này"
DEL_ITEM = re.compile(r"^\s*(Xóa|Xoá|Gỡ|Remove|Delete)\b", re.I)


def _norm(t):
    return re.sub(r"\s+", " ", str(t or "")).strip().lower()


# ============================================================ bình luận ghim
def use_channel(page, channel_id):
    """Chuyển YouTube / Studio sang đúng kênh (cùng tài khoản Google có nhiều kênh) trước khi thao tác."""
    if not channel_id:
        return
    try:
        page.goto(f"{STUDIO}/channel/{channel_id}", wait_until="domcontentloaded")
        page.wait_for_timeout(5000)
    except Exception:
        pass


def comment(page, url, key):
    """Xóa MỌI bình luận của tool (đúng nội dung) trên video – ghim hay đã bị bỏ ghim – kiểm tra ngay trên trang."""
    key = studio.comment_key(key)
    if not key:
        raise NeedsCheck("Nhật ký không ghi nội dung bình luận – không biết bình luận nào của tool, hãy gỡ tay.")

    def mine():
        page.wait_for_timeout(1500)
        out = []
        for th in _visible_list(page.locator("ytd-comment-thread-renderer")):
            try:
                txt = th.locator("#content-text").first.inner_text() if th.locator("#content-text").count() \
                    else th.inner_text()
                if key in studio.comment_text_norm(txt):
                    out.append(th)
            except Exception:
                continue
        return out

    def load():
        page.goto(url, wait_until="domcontentloaded")
        page.wait_for_timeout(5000)
        try:
            page.evaluate("document.querySelector('video')?.pause()")
        except Exception:
            pass
        _scroll_to_comments(page)
        page.wait_for_timeout(3000)

    try:
        load()
    except StepError:
        st, _o = _public_status(page, video_id(url))
        if st in ("ERROR", "UNPLAYABLE"):
            return f"{GONE} (video đã bị xóa / không còn trên YouTube)"
        raise
    found = mine()
    if not found:
        return GONE
    n = 0
    for _ in range(5):
        found = mine()
        if not found:
            break
        _say(f"xóa bình luận của tool ({len(found)} bình luận khớp nội dung)")
        _delete_thread(page, found[0])
        n += 1
    # kiểm tra ngay trên trang đang mở (không tải lại trang video lần nữa)
    page.wait_for_timeout(2500)
    if mine():
        raise StepError("Đã bấm xóa nhưng trên trang vẫn còn bình luận của tool – hãy kiểm tra.")
    return f"đã xóa {n} bình luận của tool – trên trang không còn"


# ============================================================ video còn tồn tại không
class VideoGone(Exception):
    """Video đã bị xóa khỏi kênh -> mọi thứ gắn trên video đó cũng không còn (đã sạch)."""


STUDIO_ERR = re.compile(r"Rất tiếc, đã xảy ra lỗi|Oops, something went wrong|Đã xảy ra lỗi|Something went wrong", re.I)


STRONG_ID = ""   # kênh mạnh đang gỡ (main.py đặt trước khi gỡ) – tool CHỈ thao tác trên kênh này


class NotOurs(Exception):
    """Video / mục không thuộc kênh mạnh đang gỡ -> KHÔNG đụng (không chuyển sang kênh khác)."""


def check_video(page, url):
    """Mở trang Chi tiết video trên Studio của KÊNH MẠNH đang gỡ.
    - mở được -> video thuộc kênh mạnh, gỡ tiếp;
    - video đã bị xóa -> VideoGone (tính là sạch);
    - video thuộc kênh khác -> NotOurs (không đụng, không chuyển kênh)."""
    vid = video_id(url)
    if _open_edit(page, vid):
        return
    st, owner = _public_status(page, vid)
    if st in ("ERROR", "UNPLAYABLE", "gone"):
        raise VideoGone(f"video {vid} đã bị xóa / không còn trên YouTube – không còn gì để gỡ")
    if st == "OK" and owner and STRONG_ID and owner != STRONG_ID:
        raise NotOurs(f"video {vid} thuộc kênh {owner}, không phải kênh mạnh {STRONG_ID} – không đụng")
    raise StepError(f"Studio không mở được video {vid} của kênh mạnh (trạng thái: {st or 'không rõ'}).")


def verify_channel(page, strong_id):
    """Đảm bảo trình duyệt đang ở ĐÚNG kênh mạnh. Không vào được -> dừng cả lượt gỡ (không làm gì sai chỗ).
    Lúc mở trình duyệt tool đã xác nhận đúng kênh này -> không vào Studio thêm lần nữa."""
    if strong_id and getattr(page, "_keo_channel_ok", "") == strong_id:
        return True
    use_channel(page, strong_id)
    for _ in range(10):
        if f"/channel/{strong_id}" in (page.url or ""):
            return True
        page.wait_for_timeout(800)
    return False


def _open_edit(page, vid):
    """Mở trang Chi tiết video trên Studio. True = mở được (đúng chủ kênh)."""
    studio.open_edit_page(page, vid)
    for _ in range(30):
        page.wait_for_timeout(500)
        if page.locator("ytcp-video-metadata-editor").count():
            return True
        try:
            if STUDIO_ERR.search(page.inner_text("body")[:3000]):
                return False
        except Exception:
            pass
    return False


def _public_status(page, vid):
    """(trạng thái, chủ kênh) của video – hỏi nền, KHÔNG mở thêm tab trên kênh."""
    import ytinfo
    try:
        return ytinfo.public_status(vid, page)
    except Exception:
        return "", ""


def _gone_or(fn):
    """Bọc hàm gỡ theo video: video đã bị xóa -> trả về 'đã sạch'."""
    def run(page, url, *a, **k):
        try:
            check_video(page, url)
        except VideoGone as e:
            return f"{GONE} ({e})"
        return fn(page, url, *a, **k)
    run.__name__ = fn.__name__
    return run


# ============================================================ màn hình kết thúc / thẻ
@_gone_or
def end_screen(page, url, expected=None):
    """Mở trình chỉnh sửa Màn hình kết thúc 1 LẦN: xem -> xóa -> thấy trống -> Lưu. Không mở lại để xem."""
    vid = video_id(url)
    open_editor_panel(page, vid, "end_screen")
    page.wait_for_timeout(1500)
    n = len(editors._es_items(page))
    if not n:
        editors._close_without_saving(page)
        return GONE
    if expected and n not in (expected, expected + 1):  # +1: mẫu '1 video, 1 đăng ký' có thêm ô Đăng ký
        editors._close_without_saving(page)
        raise NeedsCheck(f"Màn hình kết thúc đang có {n} thành phần, tool chỉ gắn {expected} – không xóa, hãy gỡ tay.")
    editors.say(f"gỡ {n} thành phần màn hình kết thúc")
    editors._es_clear(page)
    page.wait_for_timeout(1000)
    left = len(editors._es_items(page))
    if left:
        editors._close_without_saving(page)
        raise StepError(f"Đã xóa nhưng khung xem trước vẫn còn {left} thành phần – không lưu, hãy kiểm tra.")
    editors._save(page)
    return "đã gỡ màn hình kết thúc (khung xem trước trống, đã Lưu)"


@_gone_or
def cards(page, url, expected=None):
    """Mở trình chỉnh sửa Thẻ 1 LẦN: xem -> xóa -> thấy hết thẻ -> Lưu. Không mở lại để xem."""
    vid = video_id(url)
    open_editor_panel(page, vid, "cards")
    page.wait_for_timeout(1500)
    n = len(editors._visible(page, editors.CARD_MARKER))
    if not n:
        editors._close_without_saving(page)
        return GONE
    if expected and n != expected:
        editors._close_without_saving(page)
        raise NeedsCheck(f"Video đang có {n} thẻ, tool chỉ gắn {expected} – không xóa, hãy gỡ tay.")
    editors.say(f"gỡ {n} thẻ")
    editors._cards_clear(page)
    page.wait_for_timeout(1000)
    left = len(editors._visible(page, editors.CARD_MARKER))
    if left:
        editors._close_without_saving(page)
        raise StepError(f"Đã xóa nhưng vẫn còn {left} thẻ trong trình chỉnh sửa – không lưu, hãy kiểm tra.")
    editors._save(page)
    return "đã gỡ thẻ (trình chỉnh sửa không còn thẻ nào, đã Lưu)"


# ============================================================ cộng tác
def _open_collab_dialog(p, vid):
    studio.close_editor(p)
    studio.open_edit_page(p, vid)
    for _ in range(40):
        p.wait_for_timeout(500)
        if p.locator("ytcp-video-metadata-editor").count():
            break
    p.wait_for_timeout(1500)
    _show_more(p)
    btn = _visible_list(p.locator("ytcp-button#collaboration-button"))
    if not btn:
        for bx in _collab_boxes(p):
            btn = _visible_list(bx.get_by_role("button", name=L("invite_collab"))) or \
                _visible_list(bx.get_by_text(L("invite_collab")))
            if btn:
                break
    if not btn:
        return None
    btn[0].click()
    p.wait_for_timeout(2500)
    return dialog(p)


ROW_JS = r"""(d, keys) => {
  const vis = e => { const r = e.getBoundingClientRect(); return r.width > 0 && r.height > 0; };
  document.querySelectorAll('[data-keo-crow]').forEach(e => e.removeAttribute('data-keo-crow'));
  const btns = [...d.querySelectorAll('ytcp-icon-button, button')].filter(vis)
    .filter(b => /Tu[ỳỷ] chọn khác|Tùy chọn|More|Options/i.test(b.getAttribute('aria-label') || ''));
  for (const b of btns) {
    let row = b;
    for (let i = 0; i < 6 && row.parentElement; i++) {
      row = row.parentElement;
      const t = (row.innerText || '').toLowerCase();
      if (keys.some(k => k && t.includes(k))) {
        if (row.querySelectorAll('ytcp-icon-button, button').length > 6) break;   // đã lên tới cả hộp
        b.setAttribute('data-keo-crow', '1');
        return true;
      }
    }
  }
  return false; }"""


@_gone_or
def collab(p, url, weak):
    """Gỡ kênh cần kéo khỏi mục Cộng tác của video: Mời cộng sự → ⋮ của kênh → Xóa → Lưu → kiểm tra lại."""
    vid = video_id(url)
    name = str(weak.get("name") or "").strip()
    handle = _handle(weak.get("url", ""))
    keys = [k.lower() for k in (name, handle) if k]
    if not keys:
        raise NeedsCheck("Kênh cần kéo chưa có tên / link – không biết gỡ kênh nào, hãy gỡ tay.")
    d = _open_collab_dialog(p, vid)
    if d is None:
        raise StepError("Không mở được hộp Cộng tác của video.")

    def present():
        try:
            return any(k in (d.inner_text() or "").lower() for k in keys)
        except Exception:
            return False
    if not present():
        close_dialogs(p)
        return GONE
    if not d.evaluate(ROW_JS, keys):
        close_dialogs(p)
        raise StepError(f"Thấy {name or handle} trong hộp Cộng tác nhưng không thấy nút ⋮ của dòng đó.")
    _say(f"bấm ⋮ của {name or handle}")
    p.locator("[data-keo-crow='1']").first.click()
    p.wait_for_timeout(1000)
    items = [i for i in _visible_list(p.locator("tp-yt-paper-item, [role=menuitem]"))
             if i.get_attribute("test-id") == "REMOVE" or DEL_ITEM.search(i.inner_text() or "")]
    if not items:
        p.keyboard.press("Escape")
        raise StepError("Menu ⋮ không có mục 'Xóa'.")
    _say("chọn 'Xóa'")
    items[0].click()
    p.wait_for_timeout(1500)
    b = _dialog_button(p, [r"^\s*(Xóa|Xoá|Remove|Delete)\s*$", r"^\s*(Lưu|Save)\s*$"], wait_ms=4000)
    while b is not None:          # xác nhận Xóa (nếu hỏi) rồi Lưu hộp Mời cộng sự
        _say(f"bấm '{b[0]}'")
        b[1].click()
        p.wait_for_timeout(2000)
        if re.search(r"Lưu|Save", b[0], re.I):
            break
        b = _dialog_button(p, [r"^\s*(Lưu|Save)\s*$"], wait_ms=4000)
    try:
        _save_video_page(p)
    except StepError:
        pass
    # kiểm tra ngay trên trang đang mở: mục Cộng tác không còn kênh cần kéo (không mở lại hộp lần nữa)
    p.wait_for_timeout(1500)
    still = False
    for bx in _collab_boxes(p):
        try:
            if any(k in (bx.inner_text() or "").lower() for k in keys):
                still = True
        except Exception:
            pass
    close_dialogs(p)
    if still:
        raise StepError(f"Mục Cộng tác trên trang vẫn còn {name or handle} – hãy kiểm tra.")
    return f"đã gỡ {name or handle} khỏi mục Cộng tác"


# ============================================================ Hồ sơ – đường liên kết
def _profile_has(page, url):
    try:
        key = _vid_of(url).lower()
    except StepError:
        key = url.rstrip("/").lower()
    vals = page.evaluate("() => [...document.querySelectorAll('input, textarea')].map(i => i.value)")
    return any(key in (v or "").lower() for v in vals)


def profile_links(page, strong_id, urls):
    page.goto(f"{STUDIO}/channel/{strong_id}/editing/profile", wait_until="domcontentloaded")
    page.wait_for_timeout(6000)
    urls = [u for u in urls if u]
    present = [u for u in urls if _profile_has(page, u)]
    if not present:
        return GONE
    removed = _remove_profile_links(page, present)
    page.wait_for_timeout(800)
    left = [u for u in urls if _profile_has(page, u)]   # kiểm tra ngay trên trang, không tải lại
    if left:
        raise StepError(f"Đã xóa nhưng trên trang Hồ sơ vẫn còn đường liên kết: {', '.join(left)} – chưa Xuất bản.")
    if removed:
        _say("bấm Xuất bản")
        click(page, "publish", timeout=8000)
        page.wait_for_timeout(5000)
    return f"đã xóa đường liên kết {', '.join(present)} và Xuất bản"


# ============================================================ Thẻ Trang chủ
def _open_home_tab(page, strong_id):
    page.goto(f"{STUDIO}/channel/{strong_id}/editing/profile", wait_until="domcontentloaded")
    page.wait_for_timeout(6000)
    for loc in (page.get_by_role("tab", name=L("home_tab")), page.get_by_text(L("home_tab"))):
        try:
            loc.first.wait_for(state="visible", timeout=5000)
            loc.first.click()
            page.wait_for_timeout(4000)
            return
        except Exception:
            continue
    raise StepError("Không thấy tab 'Thẻ Trang chủ' trên trang Tùy chỉnh kênh.")


OVF_JS = r"""(box) => {
  document.querySelectorAll('[data-keo-ovf]').forEach(x => x.removeAttribute('data-keo-ovf'));
  let e = box;
  for (let i = 0; i < 8 && e; i++, e = e.parentElement) {
    const bs = e.querySelectorAll('#overflow-menu-button');
    if (bs.length === 1) { bs[0].setAttribute('data-keo-ovf', '1'); return true; }
    if (bs.length > 1) return false;
  }
  return false; }"""

FIND_SEC_JS = r"""(keys) => {
  // khung phần trên Thẻ Trang chủ chứa link / chữ khớp 1 trong các khóa (link danh sách phát, @handle, tên kênh)
  document.querySelectorAll('[data-keo-hsec]').forEach(x => x.removeAttribute('data-keo-hsec'));
  const btns = [...document.querySelectorAll('#overflow-menu-button')];
  for (const b of btns) {
    let e = b;
    for (let i = 0; i < 8 && e.parentElement; i++) {
      e = e.parentElement;
      if (e.querySelectorAll('#overflow-menu-button').length > 1) break;
      const html = (e.innerHTML || '').toLowerCase(), txt = (e.innerText || '').toLowerCase();
      if (keys.some(k => k && (html.includes(k) || txt.includes(k)))) {
        e.setAttribute('data-keo-hsec', '1');
        return true;
      }
    }
  }
  return false; }"""


FIND_TITLE_JS = r"""(title) => {
  // phần trên Thẻ Trang chủ có TIÊU ĐỀ đúng bằng `title` (không tính chữ trong danh sách bên trong phần khác)
  const want = title.trim().toLowerCase();
  document.querySelectorAll('[data-keo-hsec]').forEach(x => x.removeAttribute('data-keo-hsec'));
  const hits = [];
  for (const b of document.querySelectorAll('#overflow-menu-button')) {
    let e = b, sec = null;
    for (let i = 0; i < 8 && e.parentElement; i++) {
      e = e.parentElement;
      if (e.querySelectorAll('#overflow-menu-button').length > 1) break;
      sec = e;
    }
    if (!sec) continue;
    const heads = [...sec.querySelectorAll('h1, h2, h3, #title, .title, [id*=title]')]
      .map(h => (h.textContent || '').trim().toLowerCase());
    if (heads.includes(want)) hits.push(sec);
  }
  if (hits.length) hits[0].setAttribute('data-keo-hsec', '1');
  return hits.length; }"""


def _playlist_title(page, url):
    """Tên danh sách phát – hỏi nền (không mở thêm tab nào)."""
    import html as _html
    import ytinfo
    body = ""
    try:
        _st, body = ytinfo._get(url)
    except Exception:
        try:
            _st, body = ytinfo._browser_get(page, url)
        except Exception:
            return ""
    m = re.search(r'<meta property="og:title" content="([^"]*)"', body or "") or \
        re.search(r"<title>(.*?)(?: - YouTube)?</title>", body or "", re.S)
    return _html.unescape(m.group(1)).strip() if m else ""


def _delete_section(page, sec):
    """⋮ của phần → Xóa (… ) → xác nhận nếu hỏi."""
    sec.hover()
    page.wait_for_timeout(700)
    if not sec.evaluate(OVF_JS):
        raise StepError("Không thấy nút ⋮ của phần này.")
    page.locator("[data-keo-ovf='1']").first.click()
    page.wait_for_timeout(1000)
    items = [i for i in _visible_list(page.locator("tp-yt-paper-item, [role=menuitem], [role=option]"))
             if DEL_ITEM.search(_norm(i.inner_text()))]
    if not items:
        names = ", ".join(_norm(i.inner_text()) for i in
                          _visible_list(page.locator("tp-yt-paper-item, [role=menuitem]")))[:120]
        page.keyboard.press("Escape")
        raise StepError(f"Menu ⋮ không có mục Xóa (menu có: {names or 'trống'}).")
    _say(f"chọn '{(items[0].inner_text() or '').strip()}'")
    items[0].click()
    page.wait_for_timeout(1500)
    b = _dialog_button(page, [r"^\s*(Xóa|Xoá|Remove|Delete|Gỡ)\b"], wait_ms=2500)
    if b is not None:
        b[1].click()
        page.wait_for_timeout(1500)


HOME_VIDEO_SLOTS = {"Trang chủ – Video giới thiệu (người chưa ĐK)": ("sec_trailer",
                                                                     "Video giới thiệu kênh cho người chưa đăng ký"),
                    "Trang chủ – Video nổi bật (người ĐK cũ)": ("sec_featured",
                                                                "Video nổi bật dành cho người đăng ký cũ")}


def home(page, strong_id, items, weak):
    """Gỡ phần Trang chủ tool đã làm. Video giới thiệu / nổi bật: nếu trước đó kênh có video cũ -> TRẢ LẠI video cũ,
    không có -> xóa video tool đặt. Danh sách phát đơn / Kênh nổi bật: xóa đúng phần tool đã thêm."""
    _open_home_tab(page, strong_id)
    notes, manual, changed = [], [], False
    for it in items:
        slot = it.get("slot", "")
        if slot in HOME_VIDEO_SLOTS:
            key, name = HOME_VIDEO_SLOTS[slot]
            ours = it.get("id", "")
            sec = _home_section(page, key)
            have = _ids_in(sec) if sec is not None else []
            if not ours or ours not in have:
                notes.append(f"{name}: " + ("đã không còn video của tool" if not have else
                                            f"đang là video khác ({', '.join(have)}) – không đụng"))
                continue
            old = [x for x in str(it.get("old") or "").split(",") if x.strip() and x.strip() != ours]
            if old:
                _say(f"{name}: trả lại video cũ {old[0]}")
                set_home_video(page, key, name, f"https://www.youtube.com/watch?v={old[0].strip()}")
                notes.append(f"{name}: đã trả lại video cũ {old[0]}")
            else:
                _say(f"{name}: xóa video {ours} tool đã đặt")
                _delete_section(page, sec)
                notes.append(f"{name}: đã xóa video {ours}")
            changed = True
        elif "Danh sách phát" in slot:
            url = str(it.get("url") or "")
            m = re.search(r"list=([\w-]+)", url)
            pl_id = m.group(1) if m else ""
            title = _playlist_title(page, url) if pl_id else ""
            if pl_id and page.evaluate(FIND_SEC_JS, [pl_id.lower()]):
                _say(f"xóa phần danh sách phát '{title or pl_id}'")
                _delete_section(page, page.locator("[data-keo-hsec='1']").first)
                notes.append(f"{slot}: đã xóa phần '{title or pl_id}'")
            elif title:
                n = page.evaluate(FIND_TITLE_JS, title)
                if n == 0:
                    notes.append(f"{slot}: đã không còn phần danh sách phát '{title}'")
                    continue
                # tool kéo nhiều lần có thể đã thêm cùng 1 danh sách phát nhiều lần -> xóa hết các phần đó
                k = 0
                while n and k < 6:
                    _say(f"xóa phần danh sách phát '{title}'")
                    _delete_section(page, page.locator("[data-keo-hsec='1']").first)
                    k += 1
                    page.wait_for_timeout(1200)
                    n = page.evaluate(FIND_TITLE_JS, title)
                notes.append(f"{slot}: đã xóa {k} phần '{title}'" if k > 1 else f"{slot}: đã xóa phần '{title}'")
            else:
                # không đọc được tên (danh sách phát đã bị xóa / riêng tư) và không phần nào trỏ tới nó -> sạch
                notes.append(f"{slot}: không còn phần nào trỏ tới danh sách phát {pl_id or url}")
                continue
            it["_title"] = title
            changed = True
        else:   # kênh nổi bật: nhận theo @handle / tên / mã kênh
            url = str(it.get("url") or "")
            cid = re.search(r"/channel/(UC[\w-]{20,})", url)
            keys = [str(k).lower() for k in (_handle(url), cid.group(1) if cid else "",
                                             it.get("title") or it.get("name") or "") if k]
            if not keys:
                manual.append(f"{slot}: thiếu tên / link kênh cần kéo – hãy xem lại tay")
                continue
            if not page.evaluate(FIND_SEC_JS, keys):
                notes.append(f"{slot}: đã không còn phần kênh nổi bật của kênh cần kéo")
                continue
            k = 0
            while k < 6:   # kéo nhiều lần có thể đã thêm nhiều phần kênh nổi bật giống nhau -> xóa hết
                _say(f"xóa phần '{slot}'")
                _delete_section(page, page.locator("[data-keo-hsec='1']").first)
                k += 1
                page.wait_for_timeout(1200)
                if not page.evaluate(FIND_SEC_JS, keys):
                    break
            notes.append(f"{slot}: đã xóa" + (f" {k} phần" if k > 1 else ""))
            it["_keys"] = keys
            changed = True
    if changed:
        # kiểm tra ngay trên trang đang mở (trước khi Xuất bản) – không mở lại tab Thẻ Trang chủ
        page.wait_for_timeout(1200)
        for it in items:
            if it.get("_title") and page.evaluate(FIND_TITLE_JS, it["_title"]):
                raise StepError(f"Đã xóa nhưng trên trang vẫn còn phần danh sách phát '{it['_title']}' – chưa Xuất bản.")
            if it.get("_keys") and page.evaluate(FIND_SEC_JS, it["_keys"]):
                raise StepError("Đã xóa nhưng trên trang vẫn còn phần kênh nổi bật của kênh cần kéo – chưa Xuất bản.")
        _say("bấm Xuất bản")
        click(page, "publish", timeout=8000)
        page.wait_for_timeout(5000)
    if manual:
        raise NeedsCheck(" | ".join(notes + manual))
    return " | ".join(notes) or GONE


# ============================================================ Bài đăng
def posts(page, strong_id, vids_titles):
    """Xóa các bài đăng video tool đã đăng (theo mã video). Mở tab Bài đăng 1 LẦN, xóa xong kiểm tra ngay trên
    trang đó (bài đã xóa biến mất khỏi trang) – không tải lại tab."""
    # (đầu lượt gỡ tool đã chuyển đúng kênh mạnh – không cần vào Studio thêm lần nữa)
    page.goto(f"https://www.youtube.com/channel/{strong_id}/posts", wait_until="domcontentloaded")
    page.wait_for_timeout(5000)
    for _ in range(3):
        page.mouse.wheel(0, 1500)
        page.wait_for_timeout(900)
    n = 0
    last_err = {}
    for vid, title in vids_titles:
        for _ in range(4):
            cur = _existing_posts(page, vid, "")
            if not cur:
                break
            _say(f"xóa bài đăng có video {vid}")
            tag = f"{vid}-{n}-{_}"
            try:
                cur[0].evaluate("(e, t) => e.setAttribute('data-keo-del', t)", tag)   # đánh dấu đúng bài này
            except Exception:
                pass
            try:
                _delete_post(page, cur[0])
            except Exception as e:
                last_err[vid] = str(e).splitlines()[0][:150]
            # bài vừa xóa phải biến khỏi trang (chờ tối đa 10 giây) – không bấm lại vào bài đã xóa
            gone = False
            mark = page.locator(f"[data-keo-del='{tag}']")
            for _w in range(20):
                try:
                    gone = mark.count() == 0 or not mark.first.is_visible()
                except Exception:
                    gone = True    # phần tử đã bị gỡ khỏi trang
                if gone:
                    break
                page.wait_for_timeout(500)
            if not gone:
                break
            n += 1
            last_err.pop(vid, None)
    page.wait_for_timeout(1500)
    left = [vid for vid, _t in vids_titles if _existing_posts(page, vid, "")]
    if left:
        why = "; ".join(f"{v}: {last_err[v]}" for v in left if v in last_err)
        raise StepError(f"Trên tab Bài đăng vẫn còn bài của video: {', '.join(left)}" + (f" ({why})" if why else ""))
    return f"đã xóa {n} bài đăng – trên tab Bài đăng không còn" if n else GONE


def _gone_or_light(fn):
    """Như _gone_or nhưng KHÔNG mở Studio: hỏi nền video còn không / của kênh nào, rồi vào thẳng trang video
    (bình luận nằm ở trang xem video – vào đúng 1 lần)."""
    def run(page, url, *a, **k):
        vid = video_id(url)
        st, owner = _public_status(page, vid)
        if st in ("ERROR", "UNPLAYABLE"):
            return f"{GONE} (video {vid} đã bị xóa / không còn trên YouTube)"
        if st == "OK" and owner and STRONG_ID and owner != STRONG_ID:
            raise NotOurs(f"video {vid} thuộc kênh {owner}, không phải kênh mạnh {STRONG_ID} – không đụng")
        return fn(page, url, *a, **k)
    run.__name__ = fn.__name__
    return run


comment = _gone_or_light(comment)   # trước khi xóa bình luận: chuyển đúng kênh chủ video, video đã xóa -> sạch
