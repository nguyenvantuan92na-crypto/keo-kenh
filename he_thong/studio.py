"""
Các thao tác tự động trên YouTube / YouTube Studio.

Mỗi hàm hoặc chạy xong, hoặc ném StepError kèm lời giải thích để tool ghi
"❌ LỖI" vào báo cáo. Nhãn nút nằm trong labels.py.
"""
import os
import re

import human  # noqa: F401  (thay mọi click/fill/hover bằng thao tác kiểu người thật)
from labels import L

STUDIO = "https://studio.youtube.com"


class StepError(Exception):
    pass


class NeedsCheck(Exception):
    """Đã làm phần chính nhưng có phần cần người kiểm tra lại (⚠️)."""


# Kênh ĐÃ có đúng nội dung bạn điền (link video / kênh trong file kênh) -> bỏ qua, ghi ✅ hoàn thành.
# Dòng nhật ký có chữ này: tính là ĐÃ XONG (lần sau bỏ qua) nhưng KHÔNG gỡ (lần này tool không gắn gì mới).
ALREADY_OK = "Đã hoàn thành – đã đúng sẵn trên kênh"


def already_ok(what):
    return f"{ALREADY_OK}: {what}"


# ===================== tiện ích chung =====================

def video_id(url: str) -> str:
    m = re.search(r"(?:v=|youtu\.be/|/video/|/shorts/)([\w-]{11})", url)
    if not m:
        raise StepError(f"Không đọc được ID video từ link: {url}")
    return m.group(1)


def playlist_url(url) -> str:
    """Đổi mọi dạng link có list=... thành link danh sách phát chuẩn."""
    url = str(url or "")
    m = re.search(r"[?&]list=([\w-]+)", url)
    return f"https://www.youtube.com/playlist?list={m.group(1)}" if m else url


def _handle(url) -> str:
    m = re.search(r"/(@[\w.-]+)", str(url or ""))
    return m.group(1) if m else ""


def close_dialogs(page):
    """Đóng hộp thoại đang mở (bấm nút X, rồi Escape)."""
    for _ in range(3):
        btn = page.get_by_role("button", name=L("close"))
        try:
            if btn.count() and btn.last.is_visible():
                btn.last.click(timeout=3000)
                page.wait_for_timeout(800)
                continue
        except Exception:
            pass
        page.keyboard.press("Escape")
        page.wait_for_timeout(600)


def find(page, key, scope=None, timeout=4000):
    """Tìm phần tử theo nhãn (nút, mục menu, lựa chọn, ô nhập, chữ)."""
    root = scope or page
    pat = L(key)
    cands = [root.get_by_role(r, name=pat) for r in
             ("button", "menuitem", "option", "tab", "link", "radio", "textbox")]
    cands += [root.get_by_label(pat), root.get_by_placeholder(pat), root.get_by_text(pat)]
    per = max(500, timeout // len(cands))
    for loc in cands:
        try:
            loc.first.wait_for(state="visible", timeout=per)
            return loc.first
        except Exception:
            continue
    raise StepError(f"Không tìm thấy nút/mục '{key}' trên trang. "
                    f"Kiểm tra lại chữ trong labels.py hoặc ngôn ngữ giao diện.")


def click(page, key, scope=None, timeout=4000):
    el = find(page, key, scope, timeout)
    if el.get_attribute("aria-disabled") == "true":
        raise StepError(f"Nút '{key}' đang bị khóa (chưa chọn đủ thông tin trong hộp thoại).")
    el.click(timeout=8000)
    page.wait_for_timeout(800)


def exists(page, key, scope=None, timeout=1500):
    try:
        find(page, key, scope, timeout)
        return True
    except StepError:
        return False


def dialog(page):
    """Hộp thoại đang mở trên cùng (editor màn hình kết thúc, thẻ...)."""
    d = page.locator("tp-yt-paper-dialog:visible, ytcp-dialog:visible, [role=dialog]:visible").last
    try:
        d.wait_for(state="visible", timeout=8000)
        return d
    except Exception:
        return page


RESULT_SEL = ("ytcp-entity-card:visible, ytcp-video-pick-dialog-entity:visible, [role=option]:visible, "
              ".entity:visible, ytcp-entity-list-item:visible, ytcp-channel-pick-dialog-entity:visible, "
              "#channel-entity:visible, ytcp-featured-channels-entity:visible")


LIST_STATE_JS = r"""
() => {
  // đếm ảnh thu nhỏ & dòng chữ đang hiển thị trong hộp chọn / bảng bên trái
  const vis = e => { const r = e.getBoundingClientRect(); return r.width > 20 && r.height > 15; };
  const roots = [...document.querySelectorAll(
      'tp-yt-paper-dialog, ytcp-dialog, [role=dialog], ytve-modal-host, ytcp-video-pick-dialog')].filter(vis);
  const root = roots.length ? roots[roots.length - 1] : document.body;
  const imgs = [...root.querySelectorAll('img, yt-image, ytcp-thumbnail, ytcp-video-thumbnail-with-info')]
      .filter(vis);
  const busy = [...root.querySelectorAll('tp-yt-paper-spinner[active], tp-yt-paper-spinner-lite[active]')]
      .filter(vis).length;
  return {imgs: imgs.length, busy: busy, text: (root.innerText || '').length};
}"""


def wait_list_loaded(page, what="danh sách video", timeout=15000, min_items=1):
    """Chờ tới khi danh sách thật sự hiện ra: có ảnh thu nhỏ, hết vòng xoay tải,
    và số lượng không đổi trong ~1,5 giây. Hết thời gian mà không thấy -> báo lỗi rõ ràng."""
    waited, last, stable = 0, None, 0
    while waited < timeout:
        try:
            st = page.evaluate(LIST_STATE_JS)
        except Exception:
            st = None
        if st and st["imgs"] >= min_items and not st["busy"]:
            cur = (st["imgs"], st["text"])
            stable = stable + 1 if cur == last else 0
            last = cur
            if stable >= 3:
                return st["imgs"]
        page.wait_for_timeout(500)
        waited += 500
    if last and last[0] >= max(min_items, 1):
        return last[0]  # danh sách đã có video, chỉ là chưa "đứng yên" hẳn -> làm tiếp
    raise StepError(f"Chờ {timeout // 1000} giây nhưng {what} không hiện ra.")


def video_title(ctx, url):
    """Lấy tên video (mở tab phụ, đọc tiêu đề trang)."""
    import json as _json
    p = ctx.new_page()
    try:
        p.goto("https://www.youtube.com/oembed?format=json&url=" + url, wait_until="domcontentloaded")
        return _json.loads(p.inner_text("body"))["title"].strip()
    except Exception:
        p.goto(url, wait_until="domcontentloaded")
        p.wait_for_timeout(4000)
        return re.sub(r"^\(\d+\)\s*|\s*-\s*YouTube\s*$", "", p.title()).strip()
    finally:
        p.close()


def _title_key(title):
    """Một đoạn đầu tên video đủ để nhận diện (bỏ ký tự dễ bị hiển thị khác)."""
    t = re.sub(r"\s+", " ", title).strip()
    return t[:28]


def _norm(t):
    t = re.sub(r"[\"'“”‘’«»|#]", " ", t or "")
    return re.sub(r"\s+", " ", t).strip().lower()


def _click_video_by_id(page, vid):
    """Bấm vào ảnh thu nhỏ (hoặc dòng) của video có mã `vid` trong danh sách đang hiện."""
    for sel in (f"img[src*='{vid}']", f"a[href*='{vid}']", f"[style*='{vid}']"):
        loc = page.locator(sel)
        for i in range(loc.count()):
            el = loc.nth(i)
            try:
                bb = human.bbox(el)
                if bb and bb["width"] > 20 and el.is_visible():
                    el.click(timeout=5000)
                    return True
            except Exception:
                continue
    return False


def _click_video_by_title(page, scope, title):
    want = _norm(title)[:24]
    if not want:
        return False
    cands = scope.locator("ytcp-entity-card, ytcp-video-pick-dialog-entity, [role=option], "
                          "ytcp-video-row, #video-title, .entity, li, tr")
    for i in range(cands.count()):
        el = cands.nth(i)
        try:
            if el.is_visible() and want in _norm(el.inner_text()):
                el.click(timeout=5000)
                return True
        except Exception:
            continue
    return False


def _after_pick(page):
    """Chờ hộp chọn đóng (= đã nhận video); nếu có nút xác nhận 'Chọn' thì bấm."""
    for _ in range(12):
        if not _picker_open(page):
            page.wait_for_timeout(800)
            return
        page.wait_for_timeout(500)
    if exists(page, "select", timeout=1500):
        click(page, "select")
        page.wait_for_timeout(1500)


def pick_video(page, url, title):
    """Trong danh sách video: chuyển sang 'video bất kỳ trên YouTube' (nếu có), dán link,
    rồi bấm đúng video theo MÃ VIDEO (có trong ảnh thu nhỏ). Không bấm bừa video khác."""
    vid = video_id(url)
    scope = dialog(page)
    try:
        wait_list_loaded(page, "danh sách video", min_items=0)
    except StepError:
        pass
    # video đã có sẵn trong danh sách đang hiện -> bấm luôn
    if _click_video_by_id(page, vid):
        _after_pick(page)
        return
    for loc in (scope.get_by_role("tab", name=L("any_video_tab")), scope.get_by_text(L("any_video_tab"))):
        try:
            if loc.count() and loc.first.is_visible():
                loc.first.click(timeout=4000)
                wait_list_loaded(page, "danh sách 'video bất kỳ trên YouTube'", min_items=0)
                break
        except Exception:
            pass
    box = _search_box(scope)
    for query in (url, f"https://youtu.be/{vid}", title):
        if not query:
            continue
        box.fill(query)
        box.press("Enter")
        try:
            wait_list_loaded(page, "kết quả tìm kiếm video")
        except StepError:
            continue
        if _click_video_by_id(page, vid) or _click_video_by_title(page, scope, title):
            _after_pick(page)
            return
    raise StepError(f"Danh sách có hiện nhưng không thấy video mã {vid} ('{(title or '')[:30]}…').")


def _search_box(scope):
    """Ô tìm kiếm trong hộp chọn. Ưu tiên ô 'bất kỳ trên YouTube' (tìm được kênh/danh sách khác)."""
    anywhere = scope.get_by_placeholder(L("any_on_youtube"))
    try:
        anywhere.first.wait_for(state="visible", timeout=3000)
        return anywhere.first
    except Exception:
        pass
    # tránh ô "Section title"/"Tiêu đề phần": chỉ lấy ô có placeholder tìm kiếm hoặc nằm trong khung search
    for sel in ("#search-input input:visible", "input[placeholder]:visible", "input[type=search]:visible"):
        loc = scope.locator(sel)
        try:
            loc.first.wait_for(state="visible", timeout=2000)
            return loc.first
        except Exception:
            continue
    raise StepError("Không thấy ô tìm kiếm trong hộp chọn video/danh sách phát/kênh.")


CHECKBOX_SEL = "[role=checkbox], ytcp-checkbox-lit, tp-yt-paper-checkbox, input[type=checkbox]"


def _tick_row(page, scope, name):
    """Hộp chọn dạng danh sách có ô tích: tích vào ô của dòng có đúng tên `name`."""
    rows = scope.locator("*").filter(has=page.locator(CHECKBOX_SEL), has_text=name)
    n = rows.count()
    if not n:
        return False
    row = rows.nth(n - 1)  # phần tử sâu nhất chứa cả tên và ô tích = đúng dòng đó
    box = row.locator(CHECKBOX_SEL).first
    if not box.is_visible():
        return False
    if (box.get_attribute("aria-checked") or "") != "true":
        box.click(timeout=5000)
        page.wait_for_timeout(1000)
    return True


def fill_search_and_pick(page, scope, text, alternatives=(), match_text=None):
    """Tìm và chọn kết quả đầu tiên. Thử lần lượt `text` rồi các `alternatives`
    (ví dụ: link kênh -> tên kênh). Nếu không nhận ra khung kết quả, bấm vào dòng có chữ `match_text`."""
    box = _search_box(scope)
    for query in [text, *alternatives]:
        if not query:
            continue
        human.paste(box, query)
        box.press("Enter")
        page.wait_for_timeout(3500)
        if match_text:
            try:
                if _tick_row(page, scope, match_text):
                    return
            except Exception:
                pass
        item = scope.locator(RESULT_SEL).first
        try:
            item.wait_for(state="visible", timeout=6000)
            item.click()
            page.wait_for_timeout(1500)
            return
        except Exception:
            pass
        if match_text:
            hit = scope.get_by_text(match_text, exact=False)
            try:
                for i in range(hit.count()):
                    el = hit.nth(i)
                    if el.is_visible():
                        el.click()
                        page.wait_for_timeout(1500)
                        return
            except Exception:
                pass
    raise StepError(f"Không tìm thấy kết quả cho: {' / '.join(q for q in [text, *alternatives] if q)}")


def save_studio(page):
    try:
        click(page, "save", timeout=6000)
    except StepError as e:
        raise StepError(f"Không lưu được: {e} Có thể các thành phần đang chồng lên nhau trong khung video.")
    page.wait_for_timeout(3000)


EDITOR_SEL = ("ytve-modal-host:visible, ytve-endscreen-modal:visible, ytve-info-cards-editor:visible, "
              "tp-yt-paper-dialog:visible, ytcp-dialog:visible, [role=dialog]:visible")


def _editor_open(page):
    try:
        page.locator(EDITOR_SEL).last.wait_for(state="visible", timeout=6000)
        return True
    except Exception:
        return False


def on_page(page, url):
    """Trình duyệt ĐANG ở đúng trang `url` (bỏ qua phần ?… #…) -> không cần mở lại."""
    cur = re.sub(r"[?#].*$", "", page.url or "").rstrip("/")
    return bool(cur) and cur == re.sub(r"[?#].*$", "", url).rstrip("/")


def open_edit_page(page, vid, fresh=False):
    """Trang Chi tiết video của Studio: đang ở đó và trang còn 'sạch' -> dùng luôn, không tải lại.
    Đã mở 1 trình chỉnh sửa (Màn hình kết thúc / Thẻ) trên trang này rồi, hoặc fresh=True -> tải trang mới:
    2 trình chỉnh sửa dùng chung 1 khung trên Studio, khung cũ còn sót làm bước sau đứng chờ."""
    url = f"{STUDIO}/video/{vid}/edit"
    if not fresh and on_page(page, url) and not getattr(page, "_keo_editor_used", False):
        try:
            if page.locator("ytcp-video-metadata-editor").count():
                return False
        except Exception:
            pass
    page.goto(url, wait_until="domcontentloaded")
    page._keo_editor_used = False
    return True


def close_editor(page):
    """Đóng trình chỉnh sửa đang mở dở (bỏ thay đổi chưa lưu) để bước sau không bị kẹt."""
    for _ in range(2):
        if not _editor_open_quick(page):
            return
        try:
            click(page, "discard", timeout=2500)
            page.wait_for_timeout(1200)
            if exists(page, "confirm_discard", timeout=1500):
                click(page, "confirm_discard")
                page.wait_for_timeout(1200)
        except Exception:
            close_dialogs(page)


def _editor_open_quick(page):
    try:
        return page.locator("ytve-modal-host:visible, ytve-endscreen-modal:visible, "
                            "ytve-info-cards-editor:visible").count() > 0
    except Exception:
        return False


EDITOR_LINKS = "ytcp-text-dropdown-trigger.classic-studio-editors-links"   # từ bản ghi thật
EDITOR_READY = "ytve-modal-host ytcp-button#save-button"


def _right_editor(page, key):
    """Trình chỉnh sửa vừa mở KHÔNG phải cái còn sót của bước trước (Màn hình kết thúc và Thẻ dùng chung 1 khung).
    Thấy dấu hiệu của trình chỉnh sửa kia đang hiện -> False (tải lại trang Chi tiết video rồi mở lại)."""
    other = ("ytve-info-cards-editor:visible, ytve-info-cards-editor-options-panel:visible" if key == "end_screen"
             else "ytve-endscreen-template-picker:visible, ytve-endscreen-modal:visible")
    try:
        if page.locator(other).count():
            print(f"      · trình chỉnh sửa đang hiện không phải "
                  f"'{'Màn hình kết thúc' if key == 'end_screen' else 'Thẻ'}' – tải lại trang Chi tiết video rồi mở lại",
                  flush=True)
            return False
    except Exception:
        pass
    return True


def _wait_editor(page, timeout_ms):
    """Chờ trình chỉnh sửa tải xong (nút Lưu của trình chỉnh sửa hiện ra)."""
    waited = 0
    while waited < timeout_ms:
        try:
            loc = page.locator(EDITOR_READY)
            if loc.count() and loc.first.is_visible():
                return True
        except Exception:
            pass
        page.wait_for_timeout(500)
        waited += 500
    return False


EDITOR_LINK_ID = {"end_screen": "#endscreen-editor-link", "cards": "#info-cards-editor-link"}   # mã thật
SIDEPANEL = "ytcp-video-metadata-editor-sidepanel"

PAGE_STATE_JS = r"""() => {
  const t = (document.body.innerText || '').toLowerCase();
  return {url: location.href, kids: /dành cho trẻ em|made for kids/.test(t) && /có, nội dung này dành cho trẻ em|yes, it.s made for kids/.test(t),
          editor: !!document.querySelector('ytcp-video-metadata-editor'),
          side: !!document.querySelector('ytcp-video-metadata-editor-sidepanel'),
          noaccess: /không có quyền|không tìm thấy video|you don.t have permission|video not found/.test(t),
          login: /accounts\.google\.com|signin/.test(location.href)};
}"""


def _find_editor_link(page, key):
    for sel in (EDITOR_LINK_ID.get(key, ""), None):
        if sel:
            loc = page.locator(sel)
        else:
            loc = page.locator(EDITOR_LINKS).filter(has_text=L(key))
        try:
            for i in range(loc.count()):
                el = loc.nth(i)
                if el.is_visible():
                    return el
        except Exception:
            pass
    return None


ON_WRONG_CHANNEL = None   # main.py gắn hàm chọn lại đúng kênh mạnh
STRONG_ID = ""            # main.py gắn mã kênh mạnh (để thử mở video qua trang Nội dung của kênh)


class StudioVideoError(StepError):
    """Studio không mở được trang Chi tiết của RIÊNG video này (kênh đúng) – lỗi phía YouTube."""


def _studio_error(page):
    try:
        return bool(re.search(r"Rất tiếc, đã xảy ra lỗi|Oops, something went wrong",
                              page.inner_text("body", timeout=2000)[:3000]))
    except Exception:
        return False


def open_editor_panel(page, vid, key):
    """Mở trình chỉnh sửa Màn hình kết thúc / Thẻ ở trang Chi tiết video: chờ trang tải đủ,
    tìm đúng mục theo mã thật (#endscreen-editor-link / #info-cards-editor-link), bấm 1 lần rồi chờ tải xong.
    Không mở được -> báo rõ lý do (video dành cho trẻ em, không có quyền, chưa đăng nhập...)."""
    close_editor(page)
    name = "Màn hình kết thúc" if key == "end_screen" else "Thẻ"
    last_state = {}
    for attempt in range(3):
        if attempt == 0 or vid not in page.url or "/edit" not in page.url:
            open_edit_page(page, vid, fresh=_editor_open_quick(page))
        else:
            print(f"      · chưa thấy mục '{name}' – tải lại trang (lần {attempt + 1})", flush=True)
            page.reload(wait_until="domcontentloaded")
            page._keo_editor_used = False
        link = None
        for i in range(50):  # tối đa ~25 giây
            page.wait_for_timeout(500)
            link = _find_editor_link(page, key)
            if link is not None:
                break
            if i in (4, 8, 12, 16, 20) and _studio_error(page):
                import studio_bad
                # 1) "Rất tiếc, đã xảy ra lỗi": trình duyệt lệch kênh -> chọn lại đúng kênh / tải lại 1 lần
                fix = ON_WRONG_CHANNEL
                if fix and not getattr(page, "_keo_channel_fixed", False):
                    page._keo_channel_fixed = True
                    if fix(page, vid):
                        open_edit_page(page, vid, fresh=True)
                        continue
                # 2) thử đường khác 1 lần: vào trang Nội dung của kênh trước, rồi mới mở video
                tried = getattr(page, "_keo_alt_tried", set())
                if STRONG_ID and vid not in tried:
                    tried.add(vid)
                    page._keo_alt_tried = tried
                    print("      · Studio vẫn báo lỗi – thử mở video qua trang Nội dung của kênh", flush=True)
                    try:
                        page.goto(f"https://studio.youtube.com/channel/{STRONG_ID}/videos/upload",
                                  wait_until="domcontentloaded")
                        page.wait_for_timeout(4000)
                    except Exception:
                        pass
                    open_edit_page(page, vid, fresh=True)
                    continue
                # 3) kênh đúng mà Studio vẫn không mở được RIÊNG video này -> ghi nhớ, không thử lại vô ích
                studio_bad.mark(vid, STRONG_ID)
                raise StudioVideoError(
                    f"YouTube Studio không mở được trang Chi tiết của video {vid} (Studio tự báo 'Rất tiếc, đã xảy ra "
                    f"lỗi' dù kênh đúng, đã tải lại và thử đường khác) – thường do video ĐÃ BỊ XÓA hoặc đang bị YouTube "
                    f"hạn chế. Tool bỏ các bước Studio của video này và lấy video nhiều view khác của kênh thay vào.")
            if i in (10, 20, 30, 40):
                try:  # bảng bên phải có thể chưa hiện: cuộn tới đó, đóng thông báo che trang
                    page.keyboard.press("Escape")
                    page.evaluate(f"""() => {{ const s = document.querySelector('{SIDEPANEL}');
                                       if (s) s.scrollIntoView({{block: 'center'}}); }}""")
                except Exception:
                    pass
        if link is None:
            try:
                last_state = page.evaluate(PAGE_STATE_JS)
            except Exception:
                last_state = {}
            if last_state.get("login"):
                raise StepError("Trình duyệt đang ở trang đăng nhập Google – kênh mạnh chưa đăng nhập / hết phiên.")
            if last_state.get("noaccess"):
                raise StepError(f"Tài khoản đang đăng nhập không có quyền sửa video {vid} – video không thuộc "
                                f"kênh mạnh của bộ kênh này (kiểm tra ID kênh mạnh và đăng nhập lại bước 1).")
            continue
        if (link.get_attribute("aria-disabled") or "") == "true" or link.get_attribute("disabled") is not None:
            raise StepError(f"Mục '{name}' trên trang video đang bị khóa – thường do video đặt 'Dành cho trẻ em', "
                            f"là video Shorts, hoặc (màn hình kết thúc) video ngắn hơn 25 giây.")
        try:
            link.click()
        except Exception as e:
            print(f"      · bấm mục '{name}' chưa được: {str(e).splitlines()[0][:100]}", flush=True)
            continue
        if _wait_editor(page, 25000) and _right_editor(page, key):
            try:   # Studio đã mở lại được video từng lỗi -> xóa khỏi danh sách nhớ
                import studio_bad
                studio_bad.forget(vid)
            except Exception:
                pass
            page._keo_editor_used = True
            page.wait_for_timeout(2500)  # chờ video trong trình chỉnh sửa tải
            return editor_root(page)
        print(f"      · đã bấm '{name}' nhưng trình chỉnh sửa chưa mở – thử lại", flush=True)
        close_editor(page)
        page._keo_editor_used = True     # lần sau tải trang mới, không dùng lại trang này
    why = ""
    if last_state.get("kids"):
        why = " Video đang đặt 'Dành cho trẻ em' nên YouTube tắt Màn hình kết thúc và Thẻ."
    elif last_state and not last_state.get("editor"):
        why = f" Trang Chi tiết video không tải được (đang ở: {last_state.get('url', '')[:80]})."
    elif last_state and not last_state.get("side"):
        why = " Trang video không có bảng bên phải (cửa sổ trình duyệt quá hẹp hoặc YouTube đổi giao diện)."
    raise StepError(f"Không mở được '{name}' của video {vid} sau 3 lần thử.{why} "
                    f"Xem ảnh chụp lỗi trong logs/screenshots.")


def editor_root(page):
    for sel in ("ytve-modal-host:visible", "ytve-endscreen-modal:visible", "ytve-info-cards-editor:visible"):
        loc = page.locator(sel)
        if loc.count():
            return loc.last
    return page


# ===================== 1. Bình luận ghim =====================

def _scroll_to_comments(page):
    for _ in range(12):
        if page.locator("#simplebox-placeholder").count():
            return
        page.mouse.wheel(0, 900)
        page.wait_for_timeout(1200)
    raise StepError("Không tải được phần bình luận (video có thể đã tắt bình luận).")


def get_duration(page) -> float:
    try:
        return float(page.evaluate("document.querySelector('video')?.duration || 0"))
    except Exception:
        return 0.0


def _sub(name, fn):
    """Chạy 1 thao tác con; lỗi thì ghi rõ tên thao tác để biết kẹt ở đâu."""
    try:
        return fn()
    except (StepError, NeedsCheck):
        raise
    except Exception as e:
        raise StepError(f"[{name}] {type(e).__name__}: {str(e).splitlines()[0][:160]}")


def _first_visible(loc, timeout=8000):
    loc.first.wait_for(state="attached", timeout=timeout)
    for i in range(loc.count()):
        el = loc.nth(i)
        if el.is_visible():
            return el
    raise StepError("phần tử không hiển thị")


COMMENT_REPLACED = False   # lần ghim vừa rồi có xóa bình luận ghim cũ không (main.py đọc để ghi nhật ký)


PINNED_JS = r"""() => {
  // bình luận ĐANG GHIM thật sự: huy hiệu "Đã ghim bởi … / Pinned by …" HIỆN RA và có chữ.
  // (giao diện mới: MỌI bình luận đều chứa sẵn khung #pinned-comment-badge bị ẩn -> không được tính)
  const vis = e => { if (!e) return false; const r = e.getBoundingClientRect(), s = getComputedStyle(e);
    return r.width > 0 && r.height > 0 && s.visibility !== 'hidden' && s.display !== 'none'; };
  document.querySelectorAll('[data-keo-pin]').forEach(x => x.removeAttribute('data-keo-pin'));
  const rx = /(đã ghim bởi|ghim bởi|pinned by|đã ghim)/i;
  for (const th of document.querySelectorAll('ytd-comment-thread-renderer')) {
    const top = th.querySelector(':scope > #comment, :scope > ytd-comment-view-model, :scope > ytd-comment-renderer')
              || th.querySelector('ytd-comment-view-model, ytd-comment-renderer') || th;
    let ok = false;
    for (const b of top.querySelectorAll('#pinned-comment-badge, ytd-pinned-comment-badge-renderer, ' +
                                         'ytd-pinned-comment-badge-view-model, [id*="pinned"]')) {
      if (b.closest('ytd-comment-replies-renderer, #replies')) continue;
      const t = (b.innerText || b.textContent || '').trim();
      if (vis(b) && t && rx.test(t)) { ok = true; break; }
    }
    if (ok) { th.setAttribute('data-keo-pin', '1'); return true; }
  }
  return false; }"""


def _pinned_thread(page):
    """Khung bình luận đang ghim (đọc huy hiệu 'Đã ghim bởi…' đang hiện), không có -> None."""
    try:
        if page.evaluate(PINNED_JS):
            return page.locator("[data-keo-pin='1']").first
    except Exception:
        pass
    return None


def _is_pinned(page, thread):
    th = _pinned_thread(page)
    if th is None:
        return False
    try:
        return thread.evaluate("e => e.getAttribute('data-keo-pin') === '1'")
    except Exception:
        return False


MENU_ITEM_JS = r"""(rx) => {
  // mục trong menu ⋮ đang mở – nhận cả kiểu menu cũ (ytd-menu-*-item-renderer) lẫn kiểu mới (yt-list-item-view-model)
  const re = new RegExp(rx, 'i');
  const vis = e => { const r = e.getBoundingClientRect(), s = getComputedStyle(e);
    return r.width > 0 && r.height > 0 && s.visibility !== 'hidden' && s.display !== 'none'; };
  document.querySelectorAll('[data-keo-mi]').forEach(x => x.removeAttribute('data-keo-mi'));
  const menus = [...document.querySelectorAll('tp-yt-iron-dropdown, ytd-menu-popup-renderer, yt-sheet-view-model, ' +
                                              'ytd-popup-container, [role=menu], [role=listbox]')].filter(vis);
  const sel = 'ytd-menu-navigation-item-renderer, ytd-menu-service-item-renderer, tp-yt-paper-item, ' +
              'yt-list-item-view-model, [role=menuitem], [role=option], .yt-list-item-view-model-wiz';
  for (const m of menus.reverse()) {
    for (const it of m.querySelectorAll(sel)) {
      if (!vis(it)) continue;
      const t = (it.innerText || it.getAttribute('aria-label') || '').replace(/\s+/g, ' ').trim();
      if (t && re.test(t)) { it.setAttribute('data-keo-mi', '1'); return t; }
    }
  }
  return ''; }"""


def _menu_pick(page, pattern, what):
    """Chọn 1 mục trong menu ⋮ đang mở của YouTube (không cuộn trang để menu không đóng)."""
    rx = pattern.pattern if hasattr(pattern, "pattern") else str(pattern)
    got = ""
    for _ in range(6):   # menu có thể hiện chậm
        got = page.evaluate(MENU_ITEM_JS, rx)
        if got:
            break
        page.wait_for_timeout(500)
    if not got:
        raise StepError(f"Menu ⋮ không có mục '{what}'.")
    item = page.locator("[data-keo-mi='1']").first
    try:
        item.click(timeout=6000)
    except Exception:
        item.evaluate("e => e.click()")   # menu ở sát mép màn hình: bấm thẳng, không cuộn
    page.wait_for_timeout(1000)


def _delete_thread(page, thread):
    """Xóa 1 bình luận (của chính kênh) qua menu ⋮ → Xóa → xác nhận Xóa."""
    thread.scroll_into_view_if_needed()
    page.wait_for_timeout(600)
    thread.hover()
    page.wait_for_timeout(600)
    opened = False
    for sel in ("#action-menu-button button", "ytd-menu-renderer yt-icon-button button", "ytd-menu-renderer button",
                "#action-menu button", "#action-menu-button"):   # ưu tiên đúng NÚT ⋮, không bấm khung bao ngoài
        loc = thread.locator(sel)
        if not loc.count():
            continue
        btn = loc.first
        try:
            btn.click(timeout=8000, force=True)
        except Exception:
            btn.evaluate("e => e.click()")
        page.wait_for_timeout(1000)
        if page.evaluate(MENU_ITEM_JS, r"\S"):
            opened = True
            break
    if not opened:
        raise StepError("không mở được menu ⋮ của bình luận")
    # CHỈ bình luận của chính kênh mới có 'Chỉnh sửa' + 'Xóa'. Bình luận khán giả chỉ có 'Ghim / Loại bỏ /
    # Báo vi phạm' -> đóng menu, KHÔNG đụng tới (tránh xóa / loại bỏ nhầm bình luận người khác).
    own = ""
    for _ in range(6):
        own = page.evaluate(MENU_ITEM_JS, r"^\s*(Chỉnh sửa|Edit)\s*$")
        if own:
            break
        page.wait_for_timeout(400)
    if not own:
        try:
            page.keyboard.press("Escape")
        except Exception:
            pass
        raise StepError("bình luận này không phải của kênh (menu ⋮ không có Chỉnh sửa / Xóa) – không xóa")
    _menu_pick(page, r"^\s*(Xóa|Xoá|Delete)\s*$", "Xóa")
    _confirm_delete(page)
    page.wait_for_timeout(1500)


CONFIRM_JS = r"""(rx) => {
  // nút xác nhận 'Xóa' trong hộp thoại đang mở – nhận cả kiểu cũ (#confirm-button) lẫn kiểu mới (yt-button-view-model)
  const re = new RegExp(rx, 'i');
  const vis = e => { const r = e.getBoundingClientRect(), s = getComputedStyle(e);
    return r.width > 0 && r.height > 0 && s.visibility !== 'hidden' && s.display !== 'none'; };
  document.querySelectorAll('[data-keo-conf]').forEach(x => x.removeAttribute('data-keo-conf'));
  const dlgs = [...document.querySelectorAll('yt-confirm-dialog-renderer, tp-yt-paper-dialog, yt-dialog-view-model, ' +
                                             '[role=dialog], [role=alertdialog], ytd-popup-container')].filter(vis);
  for (const d of dlgs.reverse()) {
    const fixed = d.querySelector('#confirm-button button') || d.querySelector('#confirm-button');   // đúng NÚT
    if (fixed && vis(fixed)) { fixed.setAttribute('data-keo-conf', '1'); return 'confirm-button'; }
    for (const b of d.querySelectorAll('button, yt-button-view-model, tp-yt-paper-button, [role=button]')) {
      const t = (b.innerText || b.getAttribute('aria-label') || '').replace(/\s+/g, ' ').trim();
      if (vis(b) && t && re.test(t)) { b.setAttribute('data-keo-conf', '1'); return t; }
    }
  }
  return ''; }"""


def _confirm_delete(page):
    """Bấm xác nhận 'Xóa' NẾU YouTube hiện hộp xác nhận. Không có hộp (YouTube xóa ngay) -> không sao:
    việc còn / hết được kiểm tra lại bằng cách tải lại trang, không báo lỗi chỉ vì không thấy hộp xác nhận."""
    rx = L("confirm_delete").pattern
    for _ in range(8):
        got = page.evaluate(CONFIRM_JS, rx)
        if got:
            b = page.locator("[data-keo-conf='1']").first
            try:
                b.click(timeout=5000)
            except Exception:
                b.evaluate("e => e.click()")
            return True
        page.wait_for_timeout(500)
    return False


def comment_key(text):
    """Dấu nhận bình luận của tool trên trang: BỎ đường link (YouTube hiển thị link rút gọn / thành tên video),
    bỏ emoji & ký hiệu, chữ thường; lấy ~30 ký tự chữ đầu tiên."""
    t = re.sub(r"https?://\S+|www\.\S+|youtu\.be/\S+", " ", str(text or ""))
    t = re.sub(r"[^\w\s]", " ", t.lower(), flags=re.U)
    return re.sub(r"\s+", " ", t).strip()[:30]


def comment_text_norm(text):
    """Chữ của 1 bình luận trên trang, chuẩn hóa giống comment_key (để so khớp)."""
    t = re.sub(r"https?://\S+|www\.\S+|youtu\.be/\S+|youtube\.com/\S+", " ", str(text or ""))
    t = re.sub(r"[^\w\s]", " ", t.lower(), flags=re.U)
    return re.sub(r"\s+", " ", t).strip()


OWN_JS = r"""(keys) => {
  // bình luận GỐC của chính kênh (không tính phần phản hồi): tên tác giả là kênh, hoặc có huy hiệu tên kênh
  const vis = e => { if (!e) return false; const r = e.getBoundingClientRect(), s = getComputedStyle(e);
    return r.width > 0 && r.height > 0 && s.visibility !== 'hidden' && s.display !== 'none'; };
  const norm = h => (h || '').toLowerCase().split('?')[0].replace(/\/+$/, '');
  const own = (keys || []).map(norm).filter(Boolean);
  document.querySelectorAll('[data-keo-own]').forEach(x => x.removeAttribute('data-keo-own'));
  const out = [];
  [...document.querySelectorAll('ytd-comment-thread-renderer')].forEach((th, i) => {
    const top = th.querySelector(':scope > #comment, :scope > ytd-comment-view-model, :scope > ytd-comment-renderer')
              || th.querySelector('ytd-comment-view-model, ytd-comment-renderer');
    if (!top) return;
    const a = top.querySelector('#author-text');
    const h = norm(a && a.getAttribute('href'));
    const badge = top.querySelector('#author-comment-badge ytd-author-comment-badge-renderer, ' +
                                    'ytd-author-comment-badge-renderer');
    const mine = (!!h && own.some(k => h === k || h.endsWith(k))) ||
                 (!!badge && !badge.closest('#replies, ytd-comment-replies-renderer') && vis(badge) &&
                  (badge.innerText || '').trim().length > 0);
    if (!mine) return;
    th.setAttribute('data-keo-own', String(i));
    const t = top.querySelector('#content-text');
    out.push({i, text: ((t && (t.innerText || t.textContent)) || '').trim()});
  });
  return out; }"""


def _owner_keys(page):
    """Đường dẫn kênh chủ video (/@handle, /channel/UC...) – đọc trên trang xem video."""
    keys = []
    try:
        keys = page.evaluate(r"""() => [...document.querySelectorAll('ytd-video-owner-renderer a[href], #owner a[href]')]
                                  .map(a => (a.getAttribute('href') || '')).filter(h => /^\/(@|channel\/)/.test(h))""")
    except Exception:
        pass
    if STRONG_ID:
        keys.append(f"/channel/{STRONG_ID}")
    return list(dict.fromkeys(k.lower().rstrip("/") for k in keys if k))


def _load_all_comments(page, cap=400):
    """Sắp xếp 'Mới nhất' rồi cuộn tải hết bình luận (để không sót bình luận cũ của kênh)."""
    try:
        import replier
        replier._sort_newest(page)
    except Exception:
        pass
    last, same = -1, 0
    for _ in range(80):
        n = page.locator("ytd-comment-thread-renderer").count()
        if n >= cap or (n == last and (same := same + 1) >= 3):
            break
        if n != last:
            same = 0
        last = n
        page.evaluate("window.scrollTo(0, document.documentElement.scrollHeight)")
        page.wait_for_timeout(1300)
    try:
        page.evaluate("document.querySelector('video')?.pause()")
    except Exception:
        pass


def own_comments(page):
    return page.evaluate(OWN_JS, _owner_keys(page))


def keep_only_one(page, key, keep_pinned=True, log=None):
    """TRÊN MỖI VIDEO CHỈ GIỮ ĐÚNG 1 BÌNH LUẬN CỦA KÊNH: bình luận đang ghim có đúng nội dung `key`.
    Mọi bình luận gốc khác của kênh -> ⋮ → Xóa (chỉ xóa khi menu có 'Chỉnh sửa' = đúng là của kênh).
    Phản hồi của kênh dưới bình luận khán giả và bình luận của khán giả: KHÔNG đụng tới. Trả về số đã xóa."""
    say = log or _say
    deleted, kept_one = 0, False
    for _ in range(30):
        own = own_comments(page)
        pin = _pinned_thread(page)
        pinned_i = None
        if pin is not None:
            try:
                pinned_i = pin.evaluate("e => e.getAttribute('data-keo-own')")
            except Exception:
                pinned_i = None
        # bình luận được giữ: bình luận ĐANG GHIM đúng nội dung; chưa ghim thì bình luận đúng nội dung đầu tiên
        keep = None
        for o in own:
            if key and key in comment_text_norm(o["text"]) and \
                    (str(o["i"]) == str(pinned_i) or (not keep_pinned and keep is None)):
                keep = o["i"]
                break
        if keep is None:   # an toàn: không bao giờ xóa luôn bình luận đúng nội dung mới
            keep = next((o["i"] for o in own if key and key in comment_text_norm(o["text"])), None)
        extra = [o for o in own if o["i"] != keep]
        if not extra:
            kept_one = keep is not None
            break
        o = extra[0]
        say(f"xóa bình luận cũ / thừa của kênh: \"{o['text'][:60]}\"")
        try:
            _delete_thread(page, page.locator(f"[data-keo-own='{o['i']}']").first)
            deleted += 1
            page.wait_for_timeout(1500)
        except StepError as e:
            say(f"không xóa được ({e}) – bỏ qua bình luận này")
            page.keyboard.press("Escape")
            break
    return deleted


def pin_comment(page, url, text, replace=False) -> float:
    """Đăng + ghim bình luận, rồi đảm bảo video CHỈ CÒN ĐÚNG 1 bình luận của kênh (bình luận vừa ghim)."""
    global COMMENT_REPLACED
    dur = _pin_once(page, url, text, replace)
    key = comment_key(text)
    page.wait_for_timeout(1500)
    n = keep_only_one(page, key)
    if n:
        COMMENT_REPLACED = True
        _say(f"đã xóa {n} bình luận thừa của kênh – video chỉ còn 1 bình luận ghim")
    if len(own_comments(page)) > 1:
        raise NeedsCheck("Đã ghim bình luận mới nhưng trên video vẫn còn bình luận khác của kênh chưa xóa được – "
                         "hãy kiểm tra tay.")
    return dur


def _pin_once(page, url, text, replace=False) -> float:
    return _pin_comment(page, url, text, replace)


def _pin_comment(page, url, text, replace=False) -> float:
    """Đăng và ghim bình luận. Trả về độ dài video (giây) để tính mốc thẻ.
    replace=True: bình luận đang ghim KHÁC nội dung mới -> xóa bình luận ghim cũ rồi đăng + ghim bình luận mới."""
    page.goto(url, wait_until="domcontentloaded")
    page.wait_for_timeout(5000)
    duration = get_duration(page)
    try:  # dừng video cho nhẹ trang
        page.evaluate("document.querySelector('video')?.pause()")
    except Exception:
        pass
    _sub("tải phần bình luận", lambda: _scroll_to_comments(page))
    page.wait_for_timeout(2500)

    # bình luận này đã được đăng ở lần chạy trước (nhưng chưa ghim) -> dùng lại, không đăng trùng
    key = comment_key(text)
    if not key:
        raise StepError("Nội dung bình luận ghim chỉ có đường link – hãy thêm vài chữ để tool nhận ra bình luận của mình.")

    def mine_threads():
        out = []
        for th in _visible_list(page.locator("ytd-comment-thread-renderer")):
            try:
                body = th.locator("#content-text").first.inner_text() if th.locator("#content-text").count() \
                    else th.inner_text()
                if key in comment_text_norm(body):
                    out.append(th)
            except Exception:
                continue
        return out
    # MỖI VIDEO CHỈ 1 BÌNH LUẬN CỦA KÊNH: tải hết bình luận, xóa mọi bình luận cũ của kênh khác nội dung mới
    _sub("tải hết bình luận để tìm bình luận cũ của kênh", lambda: _load_all_comments(page))
    n_del = keep_only_one(page, key, keep_pinned=False)
    if n_del:
        global COMMENT_REPLACED
        COMMENT_REPLACED = True
        _say(f"đã xóa {n_del} bình luận cũ của kênh")
    page.evaluate("window.scrollTo(0, 0)")
    _scroll_to_comments(page)
    page.wait_for_timeout(1500)
    existing = mine_threads()
    if existing:
        target = existing[0]
        if _is_pinned(page, target):
            return duration  # đã đăng và đã ghim rồi (đọc đúng huy hiệu 'Đã ghim bởi…')
        _say("bình luận đã đăng từ trước nhưng chưa ghim – ghim ngay")
    else:
        target = None

    def open_box():
        ph = _first_visible(page.locator("ytd-comments #simplebox-placeholder, #simplebox-placeholder"))
        ph.scroll_into_view_if_needed()
        ph.click(timeout=8000)
        ed = _first_visible(page.locator("ytd-commentbox #contenteditable-root, #contenteditable-root"))
        ed.click(timeout=5000)
        return ed
    def type_text():
        editor.fill(text)
        page.wait_for_timeout(500)
        if not (editor.inner_text() or "").strip():  # một số bản không nhận fill -> gõ từng chữ
            editor.press_sequentially(text, delay=15)
    def submit():
        loc = page.locator("ytd-commentbox #submit-button button")   # bấm đúng NÚT, không bấm khung bao ngoài
        btn = _first_visible(loc if loc.count() else page.locator("ytd-commentbox #submit-button"))
        btn.click(timeout=8000)
        page.wait_for_timeout(4000)

    if target is None:
        editor = _sub("mở ô viết bình luận", open_box)
        _sub("gõ nội dung bình luận", type_text)
        _sub("bấm nút Bình luận", submit)

    def ours_pinned():
        """Bình luận đang ghim có đúng là bình luận mới không (tìm lại trên trang, không dùng chỗ trỏ cũ)."""
        th = _pinned_thread(page)
        try:
            return th is not None and key in comment_text_norm(th.inner_text())
        except Exception:
            return False

    def ours():
        """Khung bình luận MỚI của tool (tìm lại theo nội dung mỗi lần). Không thấy -> báo lỗi,
        TUYỆT ĐỐI không lấy bình luận đầu tiên (có thể là của khán giả -> ghim nhầm)."""
        for _ in range(20):
            found = mine_threads()
            if found:
                return found[0]
            page.wait_for_timeout(500)
        raise StepError("không tìm thấy bình luận vừa đăng trên trang – không ghim (tránh ghim nhầm bình luận người khác)")

    def open_menu():
        last = None
        for attempt in range(3):
            th = ours()
            try:
                th.scroll_into_view_if_needed()
                th.hover()
                page.wait_for_timeout(600)
                btn = None
                for sel in ("#action-menu-button button", "ytd-menu-renderer yt-icon-button button",
                            "ytd-menu-renderer button", "#action-menu-button"):   # ưu tiên đúng NÚT ⋮
                    loc = th.locator(sel)
                    if loc.count():
                        btn = loc.first
                        break
                if btn is None:
                    raise StepError("không thấy nút ⋮ của bình luận")
                try:
                    btn.click(timeout=6000, force=True)
                except Exception:
                    btn.evaluate("e => e.click()")
                page.wait_for_timeout(1000)
                if page.locator("tp-yt-iron-dropdown:visible, ytd-menu-popup-renderer:visible").count() or \
                        page.evaluate(MENU_ITEM_JS, L("pin").pattern):
                    return
            except Exception as e:
                last = e
            page.wait_for_timeout(1500)
        raise StepError(f"không mở được menu ⋮ của bình luận mới ({str(last).splitlines()[0][:80] if last else 'menu không hiện'})")

    if ours_pinned():
        return duration  # bình luận mới đã được ghim
    try:
        _sub("mở menu ⋮ của bình luận", open_menu)
        _sub("chọn 'Ghim' trong menu", lambda: _menu_pick(page, L("pin"), "Ghim"))

        def confirm():
            # hộp "Ghim bình luận này?" -> bấm đúng nút Ghim (kiểu cũ #confirm-button hoặc kiểu mới)
            for _ in range(10):
                got = page.evaluate(CONFIRM_JS, r"^\s*(Ghim|Pin)\s*$")
                if got:
                    b = page.locator("[data-keo-conf='1']").first
                    inner = b.locator("button")
                    try:
                        (inner.first if inner.count() else b).click(timeout=6000)
                    except Exception:
                        b.evaluate("e => e.click()")
                    break
                if ours_pinned():   # có bản YouTube ghim luôn, không hỏi lại
                    return
                page.wait_for_timeout(500)
            else:
                raise StepError("không thấy hộp xác nhận Ghim")
            page.wait_for_timeout(2500)
        _sub("xác nhận Ghim", confirm)
    except StepError:
        page.wait_for_timeout(1500)
        if ours_pinned():   # thực tế đã ghim đúng bình luận mới -> không báo lỗi
            return duration
        raise
    for _ in range(10):
        if ours_pinned():
            return duration
        page.wait_for_timeout(500)
    raise NeedsCheck("Đã đăng bình luận nhưng chưa xác nhận được bình luận mới đang được ghim.")


def check_comment(page, url, text):
    """Xem lại trên YouTube: bình luận ĐANG GHIM có đúng nội dung bạn điền không (dùng khi bước vừa báo lỗi)."""
    key = comment_key(text)
    page.goto(url, wait_until="domcontentloaded")
    page.wait_for_timeout(5000)
    try:
        page.evaluate("document.querySelector('video')?.pause()")
    except Exception:
        pass
    _scroll_to_comments(page)
    for _ in range(12):
        th = _pinned_thread(page)
        try:
            if th is not None and key and key in comment_text_norm(th.inner_text()):
                return f"bình luận '{key[:40]}' đang được ghim – bỏ qua"
        except Exception:
            pass
        page.wait_for_timeout(700)
    return ""


def check_collab(page, vid, weak):
    """Xem lại trang Chi tiết video: mục Cộng tác đã có kênh cần kéo chưa (dùng khi bước vừa báo lỗi).
    Lời mời còn đang chờ chấp nhận -> chưa tính là xong."""
    name = str(weak.get("name") or "").strip()
    handle = _handle(weak.get("url", ""))
    page.goto(f"{STUDIO}/video/{vid}/edit", wait_until="domcontentloaded")
    for _ in range(40):
        page.wait_for_timeout(500)
        if page.locator("ytcp-video-metadata-editor").count():
            break
    page.wait_for_timeout(1500)
    _show_more(page)
    for _ in range(8):
        for bx in _collab_boxes(page):
            t = re.sub(r"\s+", " ", bx.inner_text() or "")
            if (name and name.lower() in t.lower()) or (handle and handle.lower() in t.lower()):
                if re.search(r"đang chờ|chờ chấp nhận|chờ xác nhận|pending|awaiting", t, re.I):
                    return ""
                return f"{name or handle} đã có trong mục Cộng tác của video – bỏ qua"
        page.wait_for_timeout(800)
    # mục Cộng tác không liệt kê tên -> mở hộp "Quản lý cộng tác viên" xem danh sách rồi đóng lại (không đổi gì)
    sec = _collab_section(page)
    if sec is None:
        return ""
    btn = _visible_list(page.locator("ytcp-button#collaboration-button")) or \
        _visible_list(sec.get_by_role("button", name=L("invite_collab"))) or \
        _visible_list(sec.get_by_text(L("invite_collab")))
    if not btn:
        return ""
    btn[0].click()
    page.wait_for_timeout(2500)
    try:
        t = (dialog(page).inner_text() or "").lower()
    finally:
        close_dialogs(page)
    if ((name and name.lower() in t) or (handle and handle.lower() in t)) and \
            not re.search(r"đang chờ|pending|awaiting", t):
        return f"{name or handle} đã là cộng tác viên của video – bỏ qua"
    return ""


def unpin_delete_comment(page, url, key=""):
    """Xóa bình luận ghim mà tool đã đăng. `key`: đoạn đầu nội dung bình luận đã ghi trong nhật ký –
    bình luận ghim hiện tại không khớp thì KHÔNG xóa (tránh xóa nhầm bình luận khác)."""
    page.goto(url, wait_until="domcontentloaded")
    page.wait_for_timeout(5000)
    _scroll_to_comments(page)
    page.wait_for_timeout(3000)
    pinned = _pinned_thread(page)
    if pinned is None:
        raise StepError("Không còn thấy bình luận ghim (có thể đã bị gỡ trước đó).")
    if key:
        norm = lambda t: re.sub(r"\s+", " ", t or "").strip().lower()
        text = norm(pinned.locator("#content-text").first.inner_text() if pinned.locator("#content-text").count()
                    else pinned.inner_text())
        if norm(key)[:30] not in text:
            raise NeedsCheck("Bình luận đang ghim không phải bình luận tool đã đăng – không xóa, hãy kiểm tra tay.")
    _delete_thread(page, pinned)


# ===================== 2. Màn hình kết thúc =====================

def _delete_all_elements(page, scope, max_items=10):
    removed = 0
    for _ in range(max_items):
        btn = scope.get_by_role("button", name=L("delete"))
        if not btn.count():
            break
        btn.first.click()
        page.wait_for_timeout(800)
        removed += 1
    return removed


def _click_row_plus(page, scope, key):
    """Bấm nút (dấu +) ở cuối dòng có chữ `key`, ví dụ dòng 'Video  +' trong trình chỉnh sửa Thẻ."""
    btn_sel = "ytcp-icon-button, button, [role=button], tp-yt-iron-icon, yt-icon"
    rows = scope.locator("*").filter(has_text=L(key)).filter(has=page.locator(btn_sel))
    n = rows.count()
    if n:
        row = rows.nth(n - 1)
        try:
            row.locator(btn_sel).last.click(timeout=6000)
            page.wait_for_timeout(2000)
            return
        except Exception:
            try:
                row.click(timeout=6000)
                page.wait_for_timeout(2000)
                return
            except Exception:
                pass
    click(page, key, scope=scope)


ADD_ON_TIMELINE_JS = r"""
(root) => {
  // nút "+" ở đầu hàng thẻ trên dòng thời gian: nút nhỏ, nằm bên trái, thấp hơn ô thời gian
  const timeBox = [...root.querySelectorAll('input')].find(e => /^\d+:\d\d:\d\d:\d\d$/.test(e.value));
  const minY = timeBox ? timeBox.getBoundingClientRect().bottom : 0;
  const btns = [...root.querySelectorAll('ytcp-icon-button, button, [role=button]')].filter(b => {
    const r = b.getBoundingClientRect();
    return r.width > 0 && r.width < 70 && r.left < 260 && r.top > minY + 20;
  }).sort((a, b) => a.getBoundingClientRect().top - b.getBoundingClientRect().top);
  if (!btns.length) return null;
  const r = btns[0].getBoundingClientRect();
  return {x: r.left + r.width / 2, y: r.top + r.height / 2};
}"""


def _open_card_types(page, scope):
    """Đảm bảo danh sách loại thẻ (Video +, Danh sách phát +...) đang hiện.
    Sau khi thêm 1 thẻ, YouTube chuyển sang phần chi tiết thẻ -> cần bấm '+' trên dòng thời gian."""
    rows = scope.locator("*").filter(has_text=L("type_video")).filter(
        has=page.locator("ytcp-icon-button, button, [role=button]"))
    try:
        if rows.count() and rows.nth(rows.count() - 1).is_visible():
            return
    except Exception:
        pass
    try:
        click(page, "add_card", scope=scope, timeout=4000)  # nút "+ Thẻ" góc trên bên trái
        page.wait_for_timeout(1500)
        return
    except StepError:
        pass
    root = scope if scope is not page else page.locator("body")
    pt = root.evaluate(ADD_ON_TIMELINE_JS)
    if pt:
        human.mouse_click(page, pt["x"], pt["y"])
        page.wait_for_timeout(1500)
        return
    raise StepError("Đã thêm thẻ trước nhưng không mở lại được danh sách loại thẻ để thêm thẻ tiếp.")


TIMECODE = re.compile(r"^\s*\d+:\d\d:\d\d:\d\d\s*$")


def _tc_to_sec(tc):
    """Đọc mốc thời gian ở MỌI dạng YouTube hiển thị:
    0:05:00:00 (giờ:phút:giây:khung hình) · 05:00:00 (phút:giây:khung hình – video dưới 1 giờ,
    giao diện tiếng Anh, vd thước thời gian ghi 42:28:00 cho video 42 phút 28 giây) · 5:00 (phút:giây).
    Ô đang gõ dở (vd '0:05:00:') -> bỏ phần trống cuối."""
    parts = [x for x in re.split(r"[:.]", str(tc or "").strip())]
    while parts and parts[-1] == "":
        parts.pop()
    if not parts or not all(x.isdigit() for x in parts):
        raise ValueError(f"không đọc được mốc thời gian '{tc}'")
    p = [int(x) for x in parts]
    if str(tc).strip().count(":") >= 3:   # dạng 4 phần (kể cả đang gõ dở '0:05:00:')
        p = (p + [0, 0, 0, 0])[:4]
    if len(p) >= 4:
        return p[0] * 3600 + p[1] * 60 + p[2]
    if len(p) == 3:
        return p[0] * 60 + p[1]
    if len(p) == 2:
        return p[0] * 60 + p[1]
    return p[0]


def _timecode_boxes(scope):
    """Các ô thời gian dạng 0:00:00:00 đang hiển thị: [(top, value)], xếp từ trên xuống."""
    vals = scope.locator("input").evaluate_all("""els => els
        .filter(e => { const r = e.getBoundingClientRect(); return r.width > 0 && r.height > 0; })
        .map(e => [e.getBoundingClientRect().top, e.value])""")
    return sorted([(t, v) for t, v in vals if TIMECODE.match(v or "")])


def _playhead_value(page, scope):
    """Ô thời gian của THANH TRƯỢT = ô nằm thấp nhất (ô của thẻ nằm phía trên)."""
    boxes = _timecode_boxes(scope)
    return _tc_to_sec(boxes[-1][1]) if boxes else None


def _card_time_value(scope):
    """Ô thời gian của THẺ đang mở = ô nằm cao nhất (chỉ khi có từ 2 ô trở lên)."""
    boxes = _timecode_boxes(scope)
    return _tc_to_sec(boxes[0][1]) if len(boxes) >= 2 else None


def _seek_timeline(page, scope, sec, duration):
    """Kéo thanh trượt trên dòng thời gian tới mốc `sec` bằng chuột (như người kéo tay)."""
    labels = page.get_by_text(TIMECODE)
    marks = []
    for i in range(labels.count()):
        el = labels.nth(i)
        try:
            bb = human.bbox(el)
            if bb and el.is_visible():
                marks.append((bb, el.inner_text().strip()))
        except Exception:
            continue
    if len(marks) < 2:
        raise NeedsCheck("không thấy thước thời gian")
    marks.sort(key=lambda m: m[0]["x"])
    start_bb, start_txt = marks[0]
    end_bb, end_txt = marks[-1]
    total = duration or _tc_to_sec(end_txt)
    if not total:
        raise NeedsCheck("không đọc được độ dài video trên thước thời gian")
    x_start = start_bb["x"] - 6  # vạch 0 nằm ngay trước chữ "0:00:00:00"
    x_end = end_bb["x"] + end_bb["width"]
    y = start_bb["y"] + start_bb["height"] / 2
    x = x_start + (x_end - x_start) * min(sec, total) / total
    # nhấn vào đầu thanh trượt hiện tại rồi kéo sang phải tới mốc
    cur = _playhead_value(page, scope) or 0
    x_cur = x_start + (x_end - x_start) * min(cur, total) / total
    human.drag(page, x_cur, y + 4, x, y + 4)
    page.wait_for_timeout(800)
    got = _playhead_value(page, scope)
    if got is None or abs(got - sec) > 30:  # kéo chưa tới -> bấm thẳng vào vị trí trên thước
        human.mouse_click(page, x, y + 4)
        page.wait_for_timeout(800)
        got = _playhead_value(page, scope)
    if got is None or abs(got - sec) > 30:
        _set_playhead(page, scope, sec)  # cuối cùng: gõ mốc vào ô thời gian


def _set_card_time(page, scope, sec):
    """Ô thời gian riêng của thẻ (cạnh chữ 'Thẻ video') = ô dạng 0:00:00:00 nằm cao nhất."""
    value = f"{sec // 3600}:{sec % 3600 // 60:02d}:{sec % 60:02d}:00"
    idx = scope.locator("input").evaluate_all("""els => {
        let best = -1, top = 1e9;
        els.forEach((e, i) => {
          const r = e.getBoundingClientRect();
          if (r.width > 0 && /^\\d+:\\d\\d:\\d\\d:\\d\\d$/.test(e.value) && r.top < top) { top = r.top; best = i; }
        });
        return best; }""")
    if idx is None or idx < 0:
        raise NeedsCheck("không thấy ô thời gian của thẻ")
    box = scope.locator("input").nth(idx)
    try:
        if abs(_tc_to_sec(box.input_value()) - sec) <= 2:
            return  # thẻ đã nằm đúng mốc nhờ kéo thanh trượt
    except Exception:
        pass
    for _ in range(2):  # gõ mốc đúng vào ô thời gian của thẻ rồi đọc lại để xác nhận
        human.paste(box, value)
        box.press("Enter")
        page.wait_for_timeout(1500)
        try:
            if abs(_tc_to_sec(box.input_value()) - sec) <= 2:
                return
        except Exception:
            pass
    raise NeedsCheck(f"thẻ chưa vào đúng mốc {value} (ô thời gian hiện: {box.input_value()})")


def _set_playhead(page, scope, sec):
    """Đặt ô thời gian dạng 0:00:00:00 (giờ:phút:giây:khung hình) tới mốc `sec`."""
    value = f"{sec // 3600}:{sec % 3600 // 60:02d}:{sec % 60:02d}:00"
    idx = scope.locator("input").evaluate_all("""els => {
        let best = -1, top = -1;   // ô thời gian của thanh trượt = ô dạng 0:00:00:00 nằm THẤP nhất
        els.forEach((e, i) => { const r = e.getBoundingClientRect();
          if (r.width > 0 && /^\\d+:\\d\\d:\\d\\d:\\d\\d$/.test(e.value) && r.top > top) { top = r.top; best = i; } });
        return best; }""")
    if idx is None or idx < 0:
        raise NeedsCheck("không thấy ô thời gian dạng 0:00:00:00")
    box = scope.locator("input").nth(idx)
    box.click()
    box.press("Control+A")
    box.fill(value)
    box.press("Enter")
    page.wait_for_timeout(1500)


def _radio_checked(page):
    r = page.get_by_role("radio", name=L("choose_specific_video"))
    try:
        return r.count() > 0 and r.first.get_attribute("aria-checked") == "true"
    except Exception:
        return False


def _choose_specific(page, scope):
    """Tích nút tròn 'Chọn một video cụ thể'. Trả về False nếu không có lựa chọn này."""
    try:
        text = find(page, "choose_specific_video", scope=scope, timeout=5000)
    except StepError:
        return False
    text.scroll_into_view_if_needed()
    page.wait_for_timeout(600)
    attempts = []
    r = page.get_by_role("radio", name=L("choose_specific_video"))
    if r.count():
        attempts.append(lambda: r.first.click(timeout=4000))
    attempts.append(lambda: text.click(timeout=4000))

    def click_circle():  # bấm thẳng vào hình tròn nằm bên trái dòng chữ
        bb = human.bbox(text)
        human.mouse_click(page, bb["x"] - 33, bb["y"] + bb["height"] / 2 + 14)
    attempts.append(click_circle)

    for act in attempts:
        try:
            act()
            page.wait_for_timeout(1800)
        except Exception:
            continue
        if _radio_checked(page) or _picker_open(page):
            wait_list_loaded(page, "danh sách video (sau khi tích 'Chọn một video cụ thể')")
            return True
    raise StepError("Không tích được 'Chọn một video cụ thể'.")


def _picker_open(page):
    """Danh sách/ô tìm video cụ thể đã hiện ra chưa."""
    try:
        return page.get_by_placeholder(L("any_on_youtube")).count() > 0 or \
            page.locator("ytcp-video-pick-dialog:visible, ytcp-entity-card:visible, "
                         "ytcp-video-pick-dialog-entity:visible").count() > 0
    except Exception:
        return False


def _add_element(page, scope, type_key):
    click(page, "add_element", scope=scope)
    click(page, type_key, scope=page)


PREVIEW_BOX_JS = r"""
(el) => {
  // từ dòng chữ trong ô xem trước -> khung ô thành phần và vùng màn hình kết thúc chứa nó
  let box = el;
  while (box.parentElement && box.getBoundingClientRect().width < 110) box = box.parentElement;
  let area = box.parentElement;
  while (area && area.parentElement && area.getBoundingClientRect().width < box.getBoundingClientRect().width * 2.2)
    area = area.parentElement;
  const b = box.getBoundingClientRect(), a = (area || document.body).getBoundingClientRect();
  return {bx: b.left, by: b.top, bw: b.width, bh: b.height, ax: a.left, ay: a.top, aw: a.width, ah: a.height};
}"""


def _preview_label(page, key):
    """Dòng chữ của ô thành phần trong khung XEM TRƯỚC (nửa phải, phía trên) có chứa `key`."""
    w, h = page.evaluate("[innerWidth, innerHeight]")
    hits = page.get_by_text(key, exact=False)
    best = None
    for i in range(hits.count()):
        el = hits.nth(i)
        try:
            bb = human.bbox(el)
        except Exception:
            continue
        if bb and bb["x"] > w * 0.45 and bb["y"] < h * 0.62 and el.is_visible():
            if best is None or bb["y"] < best[1]["y"]:
                best = (el, bb)
    return best


def _drag_element_right(page, key):
    """Dùng chuột kéo ô thành phần (tìm theo chữ `key`) sang sát mép phải khung xem trước."""
    found = _preview_label(page, key)
    if not found:
        raise NeedsCheck("không thấy ô video thứ 2 trong khung xem trước để kéo sang phải")
    el, bb = found
    g = el.evaluate(PREVIEW_BOX_JS)
    target_left = g["ax"] + g["aw"] - g["bw"] - 12
    dx = target_left - g["bx"]
    if dx < 20:
        return  # đã nằm bên phải
    x0 = g["bx"] + g["bw"] * 0.5
    y0 = g["by"] + g["bh"] * 0.55
    human.drag(page, x0, y0, x0 + dx, y0)
    page.wait_for_timeout(1200)


def end_screen(page, vid, weak, clear_existing=True):
    """Màn hình kết thúc = 2 video mới nhất của kênh cần kéo (thêm từng thành phần như làm tay)."""
    d = open_editor_panel(page, vid, "end_screen")
    if clear_existing:
        _delete_all_elements(page, d)
        page.wait_for_timeout(1000)

    videos = weak["videos"][:2]
    titles = weak.get("video_titles", {})
    for i, v in enumerate(videos):
        _add_element(page, d, "type_video")  # "+ Thành phần" -> "Video"
        if not _choose_specific(page, d):
            raise StepError(f"Video {i + 1}: không thấy lựa chọn 'Chọn một video cụ thể'.")
        try:
            pick_video(page, v, titles.get(v) or v)
        except StepError as e:
            raise StepError(f"Video {i + 1}: {e}")

    warn = ""
    if len(videos) > 1:
        try:
            _drag_element_right(page, _title_key(titles.get(videos[1]) or "")[:20] or "Video")
        except NeedsCheck as e:
            warn = str(e)
    save_studio(page)
    if exists(page, "save", timeout=1500):
        raise StepError("Bấm Lưu nhưng trình chỉnh sửa vẫn mở — có thể 2 ô video đang chồng nhau (xem ảnh chụp).")
    if warn:
        raise NeedsCheck(warn)
    return f"{len(videos)} video"


def clear_end_screen(page, vid):
    d = open_editor_panel(page, vid, "end_screen")
    _delete_all_elements(page, d)
    save_studio(page)


# ===================== 3. Thẻ =====================

def card_times(duration_sec, n, start_min, interval_min):
    """Mốc thời gian thẻ (giây). Video ngắn hơn thì chia đều trong độ dài video."""
    times = [int((start_min + i * interval_min) * 60) for i in range(n)]
    if duration_sec and times[-1] >= duration_sec - 5:
        span = max(duration_sec - 10, n)
        times = [int(i * span / n) for i in range(n)]
    return times


def _fmt(sec):
    return f"{sec // 3600}:{sec % 3600 // 60:02d}:{sec % 60:02d}" if sec >= 3600 else f"{sec // 60}:{sec % 60:02d}"


def _set_last_card_time(page, scope, sec):
    inputs = scope.locator("input[aria-label*=':'], ytcp-media-timestamp-input input, "
                           "input.ytcp-media-timestamp-input")
    if not inputs.count():
        raise NeedsCheck("Không tìm thấy ô thời gian của thẻ – thẻ đã thêm nhưng cần chỉnh mốc tay.")
    box = inputs.last
    box.click()
    box.fill(_fmt(sec))
    box.press("Enter")
    page.wait_for_timeout(800)


def cards(page, vid, weak, duration, cfg_cards):
    d = open_editor_panel(page, vid, "cards")
    if cfg_cards.get("replace_existing", False):
        _delete_all_elements(page, d)

    items = [("type_video", v) for v in weak["videos"][:3]]  # 3 thẻ video
    times = card_times(duration, len(items), cfg_cards.get("start_minute", 0),
                       cfg_cards.get("interval_minutes", 5))
    warn = []
    for n, ((kind, link), t) in enumerate(zip(items, times), 1):
        try:
            _seek_timeline(page, d, t, duration)
        except NeedsCheck as e:
            warn.append(f"thẻ {n} @{_fmt(t)}: {e}")
        _open_card_types(page, d)
        _click_row_plus(page, d, kind)
        if kind == "type_video":
            # thẻ video mở thẳng hộp chọn video; chỉ tích 'Chọn một video cụ thể' nếu có lựa chọn đó
            if page.get_by_role("radio", name=L("choose_specific_video")).count():
                _choose_specific(page, d)
            try:
                pick_video(page, link, weak.get("video_titles", {}).get(link) or link)
            except StepError as e:
                raise StepError(f"Thẻ {n}: {e}")
        elif kind == "type_channel":
            fill_search_and_pick(page, dialog(page), link, alternatives=[weak["name"]], match_text=weak["name"])
        else:
            fill_search_and_pick(page, dialog(page), link)
        try:
            _set_card_time(page, d, t)
        except NeedsCheck as e:
            warn.append(f"thẻ @{_fmt(t)}: {e}")
        if kind == "type_channel":
            for key in ("message", "teaser"):
                try:
                    find(page, key, timeout=4000).fill(weak["name"])
                except StepError:
                    warn.append(f"không điền được '{key}'")
            if exists(page, "done"):
                click(page, "done")
        page.wait_for_timeout(1500)
    save_studio(page)
    if warn:
        raise NeedsCheck("; ".join(warn))
    return [_fmt(t) for t in times]


def clear_cards(page, vid):
    d = open_editor_panel(page, vid, "cards")
    _delete_all_elements(page, d)
    save_studio(page)


# ===================== 4. Tính năng cộng tác =====================

def _collab_boxes(page):
    """Các khung có tiêu đề chứa chữ Cộng tác / Collaboration trên trang Chi tiết video (bỏ menu, hộp thoại)."""
    out = []
    for h in _visible_list(page.get_by_text(L("collaborate"))):
        try:
            if h.evaluate("e => !!e.closest('tp-yt-paper-dialog, [role=dialog], ytcp-text-menu, nav, "
                          "ytcp-navigation-drawer, #navigation, tp-yt-paper-tooltip')"):
                continue
            box = h.locator("xpath=ancestor::*[.//button or .//ytcp-button][1]")
            if box.count() and box.first.is_visible():
                txt = re.sub(r"\s+", " ", box.first.inner_text() or "")
                if L("show_more").search(txt.strip()) or re.search(r"Hiện thêm|Show more", txt, re.I):
                    continue   # đây là nút "Hiện thêm" (mô tả có chữ 'cộng tác'), KHÔNG phải mục Cộng tác
                out.append(box.first)
        except Exception:
            continue
    return out


def _collab_section(page):
    """Khung mục Cộng tác: ưu tiên khung CÓ nút 'Mời cộng sự'."""
    boxes = _collab_boxes(page)
    for bx in boxes:
        if _visible_list(bx.get_by_role("button", name=L("invite_collab"))) or \
                _visible_list(bx.get_by_text(L("invite_collab"))):
            return bx
    return boxes[0] if boxes else None


def _show_more(page):
    """Bấm 'Hiện thêm' ở trang Chi tiết video (nút có thêm dòng mô tả 'Nội dung được trả tiền…, cộng tác…')."""
    cands = []
    for loc in (page.locator("ytcp-button#toggle-button, #toggle-button"),
                page.get_by_role("button", name=L("show_more")), page.get_by_text(L("show_more"))):
        cands += [c for c in _visible_list(loc) if re.search(r"Hiện thêm|Show more",
                                                            (c.inner_text() or c.get_attribute("aria-label") or ""), re.I)]
    if not cands:
        return False
    _say("bấm 'Hiện thêm'")
    b = cands[0]
    try:
        b.scroll_into_view_if_needed()
        b.click(timeout=6000)
    except Exception:
        b.evaluate("e => e.click()")
    page.wait_for_timeout(2500)
    return True


COLLAB_CONFIRM = [r"Tạo đường liên kết|Create link", r"Gửi lời mời|Send invite", r"^\s*(Mời|Invite)\s*$",
                  r"^\s*(Lưu|Save)\s*$", r"^\s*(Xong|Done)\s*$", r"^\s*(Thêm|Add)\s*$"]
NEVER_CLICK = re.compile(r"Hủy|Huỷ|Cancel|Sao chép|Copy|Chia sẻ|Share|Quay lại|Back", re.I)
DIALOG_BTN_JS = r"""() => {
  const vis = e => { const r = e.getBoundingClientRect(), s = getComputedStyle(e);
    return r.width > 0 && r.height > 0 && s.visibility !== 'hidden' && s.display !== 'none'; };
  document.querySelectorAll('[data-keo-dlg-btn]').forEach(e => e.removeAttribute('data-keo-dlg-btn'));
  const dlgs = [...document.querySelectorAll('tp-yt-paper-dialog, ytcp-dialog, [role=dialog], [role=alertdialog]')]
    .filter(vis);
  const out = []; let n = 0;
  for (const d of dlgs) for (const b of d.querySelectorAll('ytcp-button, button, tp-yt-paper-button, [role=button]')) {
    if (!vis(b) || b.closest('[data-keo-dlg-btn]')) continue;
    const t = (b.innerText || b.getAttribute('aria-label') || '').replace(/\s+/g, ' ').trim();
    if (!t || t.length > 40) continue;
    const dis = b.getAttribute('aria-disabled') === 'true' || b.hasAttribute('disabled');
    b.setAttribute('data-keo-dlg-btn', String(n)); out.push({i: n++, t, dis});
  }
  return out; }"""


def _dialog_button(p, order, wait_ms=6000, allow_close=False):
    """Nút trong MỌI hộp thoại đang hiện (tìm lại mỗi lần – YouTube thay hộp thoại mới sau mỗi bước),
    ưu tiên theo `order`. Chờ nút hết bị khóa. Không bao giờ trả về nút Hủy / Sao chép.
    Trả về (chữ trên nút, locator) hoặc None."""
    rank = lambda t: next((i for i, rx in enumerate(order) if re.search(rx, t, re.I)), None)
    waited = 0
    while True:
        try:
            btns = p.evaluate(DIALOG_BTN_JS) or []
        except Exception:
            btns = []
        btns = [b for b in btns if rank(b["t"]) is not None and not NEVER_CLICK.search(b["t"])
                and (allow_close or not re.search(r"^\s*(Đóng|Close)\s*$", b["t"], re.I))]
        ready = sorted([b for b in btns if not b["dis"]], key=lambda b: rank(b["t"]))
        if ready:
            return ready[0]["t"], p.locator(f"[data-keo-dlg-btn='{ready[0]['i']}']").first
        if not btns or waited >= wait_ms:
            return None
        p.wait_for_timeout(500)
        waited += 500


def _click_el(p, el):
    try:
        el.scroll_into_view_if_needed(timeout=3000)
    except Exception:
        pass
    try:
        el.click(timeout=6000)
    except Exception:
        try:
            el.evaluate("e => (e.querySelector('button') || e).click()")
        except Exception:
            pass


def _save_video_page(p):
    """Bấm nút Lưu của trang Chi tiết video (ngoài hộp thoại), chờ nút hết bị khóa tối đa 15 giây."""
    outside = "e => !e.closest('tp-yt-paper-dialog, ytcp-dialog, [role=dialog]')"
    for _ in range(30):
        cands = [b for b in _visible_list(p.locator("ytcp-button#save, ytcp-button#save-button"))
                 if b.evaluate(outside)]
        if not cands:
            cands = [b for b in _visible_list(p.get_by_role("button", name=L("save"))) if b.evaluate(outside)]
        ready = [b for b in cands if b.get_attribute("aria-disabled") != "true" and b.get_attribute("disabled") is None]
        if ready:
            _click_el(p, ready[0])
            p.wait_for_timeout(3500)
            return True
        p.wait_for_timeout(500)
    raise StepError("nút Lưu của video đang bị khóa / không thấy – có thể YouTube đã tự lưu, không có gì thay đổi.")


SHARE_DLG_JS = r"""(act) => {
  // Hộp "Sao chép và chia sẻ đường liên kết của lời mời" (mã thật: ytcp-video-collaborator-invite-link-dialog).
  // KHÔNG nhầm với hộp "Mời cộng sự" (dòng mô tả của nó cũng có chữ "Sao chép và chia sẻ đường liên kết...").
  const vis = e => { const r = e.getBoundingClientRect(), s = getComputedStyle(e);
    return r.width > 0 && r.height > 0 && s.visibility !== 'hidden' && s.display !== 'none'; };
  document.querySelectorAll('[data-keo-x]').forEach(e => e.removeAttribute('data-keo-x'));
  let roots = [...document.querySelectorAll('ytcp-video-collaborator-invite-link-dialog tp-yt-paper-dialog')].filter(vis);
  if (!roots.length) {
    const title = /^\s*(Sao chép và chia sẻ đường liên kết của lời mời|Copy and share (the )?invit\w* link)\s*$/i;
    roots = [...document.querySelectorAll('tp-yt-paper-dialog, ytcp-dialog, [role=dialog]')].filter(vis)
      .filter(d => [...d.querySelectorAll('h1, h2, #dialog-title')].some(h => title.test(h.textContent || '')))
      .filter(d => !d.querySelector('input#search-input, input[placeholder="Tìm kênh"], input[placeholder="Search channels"]'));
  }
  if (!roots.length) return false;
  const d = roots[roots.length - 1];
  const x = [...d.querySelectorAll('#close-button, ytcp-icon-button[icon="close"], [aria-label="Đóng"], [aria-label="Close"]')]
    .find(vis);
  if (act === 'mark') { if (x) x.setAttribute('data-keo-x', '1'); return !!x; }
  if (act === 'link') { const l = d.querySelector('.invite-link'); return l ? l.textContent.trim() : ''; }
  return true; }"""


def _share_dialog_open(p):
    try:
        return bool(p.evaluate(SHARE_DLG_JS, False))
    except Exception:
        return False


def _close_share_dialog(p):
    """Bấm dấu X (nút 'Đóng' ở góc trên bên phải) của hộp 'Sao chép và chia sẻ đường liên kết của lời mời'."""
    for _ in range(3):
        try:
            if p.evaluate(SHARE_DLG_JS, "mark"):
                x = p.locator("[data-keo-x='1']").first
                try:
                    x.click(timeout=5000)
                except Exception:
                    x.evaluate("e => e.click()")
        except Exception:
            pass
        for _w in range(8):
            p.wait_for_timeout(500)
            if not _share_dialog_open(p):
                return True
    return False


def collab(strong_page, weak_page, vid, weak, strong_id=""):
    """Cộng tác theo đúng cách làm trên YouTube Studio:
    Chi tiết video → Hiện thêm → mục Cộng tác → Mời cộng sự → chọn kênh cần kéo → gửi lời mời → Lưu.
    Sau đó kênh cần kéo chấp nhận lời mời (tool thử bấm Chấp nhận trong Studio của kênh cần kéo)."""
    p = strong_page
    name = str(weak.get("name") or "").strip()
    handle = _handle(weak.get("url", ""))
    close_editor(p)
    open_edit_page(p, vid)
    for _ in range(40):  # chờ trang Chi tiết video tải xong
        p.wait_for_timeout(500)
        if p.locator("ytcp-video-metadata-editor").count():
            break
    p.wait_for_timeout(1500)
    _show_more(p)   # mục Cộng tác nằm trong phần "Hiện thêm" -> luôn mở phần này trước
    sec = None
    for _ in range(10):
        sec = _collab_section(p)
        if sec is not None:
            break
        p.wait_for_timeout(800)
    if sec is None:
        raise StepError("Không thấy mục Cộng tác / Collaboration trên trang Chi tiết video (đã bấm Hiện thêm). "
                        "Kênh mạnh có thể chưa được YouTube mở tính năng này – bỏ tích 'Cộng tác' để chạy tiếp.")
    sec.scroll_into_view_if_needed()
    for bx in _collab_boxes(p) or [sec]:   # kênh cần kéo đã là cộng sự (hoặc đang chờ chấp nhận) -> giữ nguyên
        text = (bx.inner_text() or "").lower()
        if (name and name.lower() in text) or (handle and handle.lower() in text):
            if not re.search(r"đang chờ|chờ chấp nhận|chờ xác nhận|pending|awaiting", text, re.I):
                return already_ok(f"{name or handle} đã có trong mục Cộng tác của video – bỏ qua")
            _say(f"{name or handle} đã được mời nhưng còn chờ chấp nhận – kênh cần kéo vào chấp nhận")
            lk = _invite_url(weak, strong_id)
            if lk and _accept_invite(weak_page, lk):
                return f"Kênh cần kéo {name or handle} đã CHẤP NHẬN lời mời cộng tác ({lk})"
            try:
                weak_page.goto(STUDIO, wait_until="domcontentloaded")
                weak_page.wait_for_timeout(6000)
                v = _visible_list(weak_page.get_by_role("button", name=re.compile("Thông báo|Notifications", re.I)))
                if v:
                    v[0].click()
                    weak_page.wait_for_timeout(2500)
                if _accept_on(weak_page):
                    return f"Kênh cần kéo {name or handle} đã chấp nhận lời mời cộng tác"
            except Exception:
                pass
            raise NeedsCheck(f"{name or handle} đã được mời cộng tác nhưng còn chờ chấp nhận – hãy mở đường liên "
                             f"kết mời bằng tài khoản kênh cần kéo và bấm Chấp nhận.")
    btn = _visible_list(p.locator("ytcp-button#collaboration-button")) or \
          [b for b in _visible_list(sec.get_by_role("button", name=L("invite_collab")))] or \
          [b for b in _visible_list(sec.get_by_text(L("invite_collab")))] or \
          [b for b in _visible_list(p.get_by_role("button", name=L("invite_collab")))
           if not b.evaluate("e => !!e.closest('tp-yt-paper-dialog, [role=dialog]')")]
    if not btn:
        seen = " | ".join(re.sub(r"\s+", " ", (bx.inner_text() or ""))[:80] for bx in _collab_boxes(p)[:3])
        raise StepError(f"Thấy mục Cộng tác nhưng không thấy nút 'Mời cộng sự'. Mục đang hiện: {seen or '(trống)'}")
    blabel = re.sub(r"\s+", " ", (btn[0].inner_text() or btn[0].get_attribute("aria-label") or "Mời cộng sự")).strip()
    _say(f"bấm '{blabel[:40]}'")
    btn[0].click()
    p.wait_for_timeout(2500)
    d = dialog(p)
    picked = False
    pre_link = ""
    try:
        dt = (d.inner_text() or "").lower()
        if (name and name.lower() in dt) or (handle and handle.lower() in dt):
            if re.search(r"đang chờ chấp nhận|pending", dt):
                # lời mời đã tạo từ trước, đang chờ -> lấy lại đường liên kết mời để kênh cần kéo chấp nhận
                _say(f"{name or handle} đã có trong hộp Mời cộng sự (Đang chờ chấp nhận)")
                picked = True
                cp = [b_ for b_ in _visible_list(d.get_by_text(re.compile(
                    r"Sao chép đường liên kết của lời mời|Copy invite link", re.I)))]
                if cp:
                    _say("bấm 'Sao chép đường liên kết của lời mời' để lấy link mời")
                    _click_el(p, cp[0])
                    for _ in range(12):
                        p.wait_for_timeout(500)
                        if _share_dialog_open(p):
                            break
            else:   # đã là cộng tác viên (đã chấp nhận) -> xong, đóng hộp, không đổi gì
                close_dialogs(p)
                return already_ok(f"{name or handle} đã là cộng tác viên của video – bỏ qua")
    except StepError:
        raise
    except Exception:
        pass
    for q in ([] if picked else [x for x in (handle, name, weak.get("url", "")) if x]):
        boxes = [x for x in _visible_list(d.locator("input")) if x.is_editable()]
        if not boxes:
            break
        _say(f"tìm kênh: {q}")
        human.paste(boxes[0], q)
        boxes[0].press("Enter")
        p.wait_for_timeout(3500)
        rows = [r for r in _visible_list(d.locator("[role=option], ytcp-entity-card, tp-yt-paper-item, li, "
                                                   "ytcp-channel-pick-dialog-entity, [role=checkbox]"))
                if (name and name.lower() in (r.inner_text() or "").lower())
                or (handle and handle.lower() in (r.inner_text() or "").lower())]
        if rows:
            _say(f"chọn kênh: {(rows[0].inner_text() or '').strip().splitlines()[0][:50]}")
            rows[0].click()
            p.wait_for_timeout(1200)
            picked = True
            break
    if not picked:
        close_dialogs(p)
        raise StepError(f"Hộp 'Mời cộng sự' không tìm thấy kênh '{name or handle}'. Tool KHÔNG mời kênh khác.")
    # xác nhận trong hộp mời. YouTube hiện: hộp "Mời người cộng tác" (ảnh + tên kênh) -> nút "Tạo đường liên kết"
    # -> YouTube tạo ĐƯỜNG LIÊN KẾT MỜI -> kênh cần kéo mở link đó và bấm Chấp nhận.
    # Đúng lộ trình YouTube:
    #  1) hộp "Mời người cộng tác" -> bấm "Tạo đường liên kết"
    #  2) hộp "Sao chép và chia sẻ đường liên kết của lời mời" -> đọc link mời -> bấm dấu X (KHÔNG bấm Chia sẻ)
    #  3) quay về hộp "Mời cộng sự" (kênh hiện "Đang chờ chấp nhận") -> bấm "Lưu" ở dưới cùng hộp đó
    invite_link = ""
    saved_dialog = False
    for _ in range(8):
        if _share_dialog_open(p):
            invite_link = invite_link or _invite_link(p, weak)
            _say("đóng hộp 'Sao chép và chia sẻ đường liên kết của lời mời' (dấu X)")
            if not _close_share_dialog(p):
                raise StepError("Không bấm được dấu X của hộp 'Sao chép và chia sẻ đường liên kết của lời mời'.")
            p.wait_for_timeout(1500)
            continue
        b = _dialog_button(p, COLLAB_CONFIRM, wait_ms=6000)
        if b is None:
            break
        label, el = b
        _say(f"bấm '{label}' trong hộp mời cộng tác")
        _click_el(p, el)
        if re.search(r"Tạo đường liên kết|Create link", label, re.I):
            for _ in range(20):   # chờ hộp chia sẻ đường liên kết hiện ra
                p.wait_for_timeout(750)
                if _share_dialog_open(p):
                    break
        elif re.search(r"^\s*(Lưu|Save)\s*$", label, re.I):
            p.wait_for_timeout(3000)
            saved_dialog = True
            if _dialog_button(p, [r"^\s*(Lưu|Save)\s*$"], wait_ms=0) is None:
                break   # hộp "Mời cộng sự" đã đóng sau khi Lưu
        else:
            p.wait_for_timeout(2500)
    if invite_link:
        _say(f"đường liên kết mời: {invite_link}")
    if not saved_dialog:
        _say("   nút Lưu của hộp 'Mời cộng sự' không bấm được (không có gì thay đổi) – đóng hộp")
        close_dialogs(p)
    _say("bấm Lưu video")
    try:
        _save_video_page(p)
    except StepError as e:
        _say(f"   {e}")
    shown = False
    for _ in range(10):
        sec = _collab_section(p)
        t = (sec.inner_text() if sec is not None else "") or ""
        if (name and name.lower() in t.lower()) or (handle and handle.lower() in t.lower()):
            shown = True
            break
        p.wait_for_timeout(600)
    if not invite_link and not shown and not _invite_url(weak, strong_id):
        raise NeedsCheck(f"Đã chọn {name or handle} nhưng chưa lấy được đường liên kết mời và mục Cộng tác chưa hiện "
                         f"tên kênh – hãy mở video kiểm tra.")

    # kênh cần kéo chấp nhận: mở đường liên kết mời bằng trình duyệt (đã đăng nhập) của kênh cần kéo -> Chấp nhận
    # Link mời của YouTube có dạng: studio.youtube.com/channel/<mã kênh cần kéo>/collaboration/<mã kênh mạnh>
    built = _invite_url(weak, strong_id)
    links = list(dict.fromkeys(x for x in (invite_link, built) if x))
    for lk in links:
        if _accept_invite(weak_page, lk):
            return f"Đã tạo lời mời cộng tác và kênh cần kéo {name or handle} đã CHẤP NHẬN ({lk})"
    try:   # cách dự phòng: thông báo trong Studio của kênh cần kéo
        w = weak_page
        w.goto(STUDIO, wait_until="domcontentloaded")
        w.wait_for_timeout(6000)
        v = _visible_list(w.get_by_role("button", name=re.compile("Thông báo|Notifications", re.I)))
        if v:
            v[0].click()
            w.wait_for_timeout(2500)
            if _accept_on(w):
                return f"Đã mời {name or handle} và kênh cần kéo đã chấp nhận (qua Thông báo)"
    except Exception:
        pass
    _weak_snapshot(weak_page, "congtac_kenh_can_keo")
    raise NeedsCheck(f"Đã tạo lời mời cộng tác cho {name or handle}" +
                     (f" (đường liên kết: {links[0]})" if links else "") +
                     ". Tool chưa bấm được Chấp nhận bên kênh cần kéo – đã chụp lại trang của kênh cần kéo "
                     "(logs/screenshots/*congtac_kenh_can_keo*) để sửa; tạm thời hãy mở link đó bằng trình duyệt "
                     "của kênh cần kéo và bấm Chấp nhận.")


WEAK_SNAPSHOT = None   # main.py gán hàm chụp ảnh + ghi chẩn đoán


def _weak_snapshot(page, tag):
    try:
        if WEAK_SNAPSHOT:
            WEAK_SNAPSHOT(page, tag)
    except Exception:
        pass


def _invite_url(weak, strong_id):
    wid = str(weak.get("channel_id") or "").strip()
    sid = str(strong_id or "").strip()
    if re.fullmatch(r"UC[\w-]{22}", wid) and re.fullmatch(r"UC[\w-]{22}", sid):
        return f"{STUDIO}/channel/{wid}/collaboration/{sid}"
    return ""


ACCEPT_JS = r"""(act) => {
  const vis = e => { const r = e.getBoundingClientRect(), s = getComputedStyle(e);
    return r.width > 0 && r.height > 0 && s.visibility !== 'hidden' && s.display !== 'none'; };
  const ok = /^(Chấp nhận|Chấp nhận lời mời|Đồng ý|Đồng ý và tham gia|Tham gia|Bắt đầu cộng tác|Accept|Accept invite|Accept invitation|Agree|Join)$/i;
  const bad = /Từ chối|Decline|Reject|Hủy|Cancel/i;
  const btns = [...document.querySelectorAll('ytcp-button, button, tp-yt-paper-button, [role=button]')].filter(vis)
    .filter(b => !b.parentElement.closest('ytcp-button, tp-yt-paper-button'));
  const lab = b => (b.innerText || b.getAttribute('aria-label') || '').replace(/\s+/g, ' ').trim();
  const acc = btns.filter(b => ok.test(lab(b)) && !bad.test(lab(b)));
  acc.sort((a, b) => (b.closest('tp-yt-paper-dialog, ytcp-dialog, [role=dialog]') ? 1 : 0) -
                     (a.closest('tp-yt-paper-dialog, ytcp-dialog, [role=dialog]') ? 1 : 0));
  const en = acc.filter(b => b.getAttribute('aria-disabled') !== 'true' && !b.hasAttribute('disabled') &&
                             !(b.querySelector('button') || {}).disabled);
  if (act === 'tick' && acc.length && !en.length) {   // nút Chấp nhận bị khóa -> tích ô đồng ý trong cùng hộp
    const root = acc[0].closest('tp-yt-paper-dialog, ytcp-dialog, [role=dialog]') || document.body;
    let n = 0;
    root.querySelectorAll('ytcp-checkbox-lit, tp-yt-paper-checkbox, [role=checkbox], input[type=checkbox]').forEach(c => {
      if (!vis(c)) return;
      const on = c.getAttribute('aria-checked') === 'true' || c.hasAttribute('checked') || c.checked;
      if (!on) { (c.querySelector('[role=checkbox]') || c).click(); n++; } });
    return {ticked: n};
  }
  if (act === 'click' && en.length) { const t = lab(en[0]); (en[0].querySelector('button') || en[0]).click(); return {clicked: t}; }
  return {found: acc.length, enabled: en.length, labels: acc.map(lab)}; }"""


def _accept_invite(w, link):
    """Mở link mời bằng trình duyệt của kênh cần kéo và bấm Chấp nhận. True = đã chấp nhận
    (nút Chấp nhận biến mất / trang báo đã là cộng tác viên)."""
    try:
        _say(f"kênh cần kéo: mở đường liên kết mời {link}")
        w.goto(link, wait_until="domcontentloaded")
    except Exception as e:
        _say(f"   không mở được link mời: {str(e).splitlines()[0][:80]}")
        return False
    st = {}
    for _ in range(40):   # Studio tải chậm: chờ tối đa 20 giây cho nút Chấp nhận hiện ra
        w.wait_for_timeout(500)
        try:
            st = w.evaluate(ACCEPT_JS, "") or {}
        except Exception:
            st = {}
        if st.get("found"):
            break
    if not st.get("found"):
        body = ""
        try:
            body = re.sub(r"\s+", " ", w.inner_text("body"))[:3000]
        except Exception:
            pass
        if re.search(r"đã chấp nhận|đã là cộng tác viên|already (a )?collaborat|accepted", body, re.I):
            _say("   kênh cần kéo đã chấp nhận lời mời từ trước")
            return True
        _say("   trang link mời không có nút Chấp nhận")
        _weak_snapshot(w, "congtac_link_moi")
        return False
    for _ in range(3):
        if not st.get("enabled"):
            r = w.evaluate(ACCEPT_JS, "tick") or {}
            if r.get("ticked"):
                _say(f"   tích {r['ticked']} ô đồng ý để mở khóa nút Chấp nhận")
            w.wait_for_timeout(1000)
        r = w.evaluate(ACCEPT_JS, "click") or {}
        if r.get("clicked"):
            _say(f"kênh cần kéo: bấm '{r['clicked']}'")
            w.wait_for_timeout(4000)
        st = w.evaluate(ACCEPT_JS, "") or {}
        if not st.get("found"):
            return True
    _weak_snapshot(w, "congtac_chap_nhan")
    return False


INVITE_LINK_JS = r"""() => { const out = [];
  const roots = [...document.querySelectorAll('tp-yt-paper-dialog, [role=dialog], ytcp-dialog')]
    .filter(d => d.offsetParent !== null || d.getClientRects().length);
  for (const r of roots) {
    r.querySelectorAll('input, textarea').forEach(i => out.push(i.value || ''));
    r.querySelectorAll('a[href]').forEach(a => out.push(a.href));
    out.push(r.innerText || '');
  }
  return out.join('\n'); }"""


def _invite_link(page, weak):
    """Đường liên kết mời cộng tác YouTube vừa tạo (trong hộp thoại đang mở)."""
    try:
        lk = page.evaluate(SHARE_DLG_JS, "link") or ""
        if re.match(r"https?://studio\.youtube\.com/channel/[\w-]+/collaboration/[\w-]+", lk):
            return lk
    except Exception:
        pass
    try:
        txt = page.evaluate(INVITE_LINK_JS) or ""
    except Exception:
        return ""
    m = re.search(r"https?://studio\.youtube\.com/channel/[\w-]+/collaboration/[\w-]+", txt)
    if m:
        return m.group(0)
    return ""   # chỉ nhận đúng link mời dạng .../collaboration/... (không lấy nhầm link video youtu.be)


def _copy_invite_link(page):
    """Hộp chỉ có nút 'Sao chép đường liên kết' (không hiện chữ link) -> bấm sao chép rồi đọc bộ nhớ tạm."""
    btn = [b for b in _visible_list(page.get_by_role("button", name=L("copy_link")))]
    if not btn:
        return ""
    try:
        page.context.grant_permissions(["clipboard-read", "clipboard-write"])
    except Exception:
        pass
    try:
        _say("bấm 'Sao chép đường liên kết'")
        btn[0].click()
        page.wait_for_timeout(1200)
        txt = page.evaluate("navigator.clipboard.readText()") or ""
        m = re.search(r"https?://\S+", txt)
        return m.group(0) if m else ""
    except Exception:
        return ""


def _accept_on(w):
    """Bấm nút Chấp nhận / Accept trên trang đang mở của kênh cần kéo. True = đã bấm và nút biến mất."""
    for _ in range(10):
        acc = [b for b in _visible_list(w.get_by_role("button", name=L("accept")))
               if b.get_attribute("aria-disabled") != "true"]
        if acc:
            _say(f"kênh cần kéo: bấm '{(acc[0].inner_text() or '').strip()[:30]}'")
            acc[0].click()
            w.wait_for_timeout(3500)
            # hộp xác nhận thêm (nếu có)
            more = [b for b in _visible_list(w.get_by_role("button", name=L("accept")))
                    if b.evaluate("e => !!e.closest('tp-yt-paper-dialog, [role=dialog], ytcp-dialog')")]
            if more:
                more[0].click()
                w.wait_for_timeout(3000)
            return True
        w.wait_for_timeout(1000)
    return False


# ===================== 5. Tùy chỉnh kênh mạnh =====================

def _last_editable(cands):
    """Ô nhập hiển thị & sửa được cuối cùng trong các cách tìm (theo thứ tự ưu tiên)."""
    for loc in cands:
        try:
            for i in range(loc.count() - 1, -1, -1):
                el = loc.nth(i)
                if el.is_visible() and el.is_editable():
                    return el
        except Exception:
            continue
    return None


def _type_into(el, text):
    """Dán chữ vào ô và KIỂM TRA ô đã đúng nội dung (không bấm Ctrl+A khi con trỏ chưa nằm trong ô)."""
    if human.paste(el, text):
        return
    el.click()
    el.press("Control+A")
    el.press_sequentially(text, delay=30)
    try:
        if (el.input_value() or "").strip() != text.strip():
            raise StepError(f"Không điền được '{text[:40]}' vào ô (ô đang hiện: '{el.input_value()[:40]}').")
    except StepError:
        raise
    except Exception:
        pass


def _remove_profile_links(page, urls):
    """Xóa các dòng đường liên kết ở Hồ sơ có URL nằm trong `urls` (đường liên kết tool đã gắn lần trước)."""
    removed = []
    for u in urls:
        try:
            key = _vid_of(u).lower()
        except StepError:
            key = u.rstrip("/").lower()
        for _ in range(3):
            hit = None
            for inp in _visible_list(page.locator("input")):
                try:
                    if key and key in (inp.input_value() or "").lower():
                        hit = inp
                        break
                except Exception:
                    continue
            if hit is None:
                break
            row = hit.locator("xpath=ancestor::*[.//ytcp-icon-button or .//button][1]")
            btns = [b for b in _visible_list(row.first.locator("ytcp-icon-button, button"))
                    if L("delete").search(b.get_attribute("aria-label") or "") or "delete" in (b.get_attribute("icon") or "")]
            if not btns:
                btns = [b for b in _visible_list(row.first.locator("ytcp-icon-button, button"))
                        if not (b.inner_text() or "").strip()][-1:]
            if not btns:
                raise StepError(f"Thấy đường liên kết cũ {u} nhưng không thấy nút xóa của dòng đó.")
            print(f"      · xóa đường liên kết cũ: {u}", flush=True)
            btns[0].click()
            page.wait_for_timeout(1200)
            removed.append(u)
            break
    return removed


def add_profile_link(page, strong_id, weak, title_text="", link_url="", remove_urls=()):
    """Thêm 1 đường liên kết ở mục Hồ sơ -> Đường liên kết của kênh mạnh.
    link_url: link bạn muốn đặt (vd: link video cần kéo); trống = link kênh cần kéo."""
    url_w = str(link_url or weak.get("url") or "").strip()
    name_w = str(title_text or "").strip() or str(weak.get("name") or "").strip() or _handle(url_w) or "Kênh"
    if not url_w.startswith("http"):
        raise StepError("Chưa có URL cho đường liên kết (điền ở Thông tin kênh → Tùy chỉnh kênh mạnh).")
    page.goto(f"{STUDIO}/channel/{strong_id}/editing/profile", wait_until="domcontentloaded")
    page.wait_for_timeout(6000)

    removed = _remove_profile_links(page, [u for u in remove_urls if u and u != url_w]) if remove_urls else []

    # đã có đường liên kết tới kênh cần kéo thì thôi (so cả link @handle lẫn link /channel/UC...)
    keys = {url_w.rstrip("/").lower()}
    try:  # link video: so theo mã video (watch?v= / youtu.be đều khớp)
        keys = {_vid_of(url_w).lower()}
    except StepError:
        if _handle(url_w):
            keys.add(_handle(url_w).lower())
        if not link_url and weak.get("channel_id"):
            keys.add(str(weak["channel_id"]).lower())
    try:
        values = page.evaluate("() => [...document.querySelectorAll('input, textarea')].map(i => i.value)")
        if any(k and k in (v or "").lower() for v in values for k in keys):
            if removed:
                click(page, "publish", timeout=6000)
                page.wait_for_timeout(4000)
                return f"Đã xóa đường liên kết cũ ({', '.join(removed)}); " + already_ok(f"đường liên kết {url_w}")
            return already_ok(f"Hồ sơ đã có đường liên kết {url_w} – bỏ qua")
    except Exception:
        pass

    title_cands = lambda: [page.get_by_placeholder(L("link_title_ph")), page.get_by_label(L("link_title"))]
    url_cands = lambda: [page.get_by_placeholder(L("link_url_ph")), page.get_by_label(L("link_url"))]

    # nếu đang có sẵn 1 hàng trống (ví dụ từ lần chạy lỗi trước) thì dùng luôn, không thêm hàng mới
    title = _last_editable([page.get_by_placeholder(L("link_title_ph"))])
    if title is not None and (title.input_value() or "").strip():
        title = None
    if title is None:
        print("      · bấm 'Thêm đường liên kết'", flush=True)
        btn = find(page, "add_link", timeout=10000)
        btn.click()
        page.wait_for_timeout(1500)
        title = _last_editable(title_cands())
    url = _last_editable(url_cands())
    if title is None or url is None:
        raise StepError("Đã bấm 'Thêm đường liên kết' nhưng không thấy ô 'Nhập tiêu đề' / 'Nhập URL'.")
    print(f"      · điền tiêu đề: {name_w}", flush=True)
    _type_into(title, name_w)
    print(f"      · điền URL: {url_w}", flush=True)
    _type_into(url, url_w)
    page.wait_for_timeout(1200)

    pub = find(page, "publish", timeout=6000)
    if pub.get_attribute("aria-disabled") == "true" or pub.is_disabled():
        raise StepError("Nút Xuất bản đang bị khóa – trên trang có ô bị báo lỗi (xem ảnh chụp).")
    print("      · bấm Xuất bản", flush=True)
    pub.click()
    page.wait_for_timeout(4000)
    return (f"Đã xóa đường liên kết cũ ({', '.join(removed)}). " if removed else "") + \
        f"Đã thêm đường liên kết: {name_w} – {url_w}"


def check_profile_link(page, strong_id, link_url):
    """Xem lại Hồ sơ kênh mạnh: đã có đường liên kết bạn điền chưa (dùng khi bước vừa báo lỗi)."""
    url_w = str(link_url or "").strip()
    if not url_w:
        return ""
    try:
        key = _vid_of(url_w).lower()
    except StepError:
        key = url_w.rstrip("/").lower()
    page.goto(f"{STUDIO}/channel/{strong_id}/editing/profile", wait_until="domcontentloaded")
    page.wait_for_timeout(6000)
    values = page.evaluate("() => [...document.querySelectorAll('input, textarea')].map(i => i.value)")
    if any(key in (v or "").lower() for v in values):
        return f"Hồ sơ đã có đường liên kết {url_w} – bỏ qua"
    return ""


def _empty_inputs(page):
    """Vị trí các ô nhập đang trống và hiển thị trên trang."""
    try:
        return page.evaluate("""() => [...document.querySelectorAll('input')]
            .filter(i => { const r = i.getBoundingClientRect(); return r.width > 0 && r.height > 0; })
            .map((i, n) => i.value === '' && (i.type === 'text' || i.type === 'url' || !i.type) ? n : -1)
            .filter(n => n >= 0)""")
    except Exception:
        return []


HOME_PARTS = ("Video giới thiệu cho người chưa ĐK", "Video nổi bật cho người ĐK cũ",
              "Danh sách phát đơn", "Kênh nổi bật")
# 2 phần video tự kiểm tra video đang đặt -> luôn chạy (đã đúng thì bỏ qua); 2 phần sau chỉ làm 1 lần
HOME_ONCE = ("Danh sách phát đơn", "Kênh nổi bật")

VID_IN_JS = r"""(root, id) => {
  const hit = e => ((e.getAttribute && (e.getAttribute('src') || '') + ' ' + (e.getAttribute('style') || '') + ' ' +
                     (e.getAttribute('href') || '')) || '').includes(id);
  if (hit(root)) return true;
  return [...root.querySelectorAll('img, [style*="/vi/"], a[href], [src]')].some(hit);
}"""

IDS_IN_JS = r"""(root) => {
  const out = new Set();
  root.querySelectorAll('img, [style*="/vi/"], a[href], [src]').forEach(e => {
    const s = (e.getAttribute('src') || '') + ' ' + (e.getAttribute('style') || '') + ' ' + (e.getAttribute('href') || '');
    const m = s.match(/(?:\/vi(?:_webp)?\/|[?&]v=|youtu\.be\/|\/shorts\/)([\w-]{11})/);
    if (m) out.add(m[1]);
  });
  return [...out];
}"""


def _vid_of(link):
    """Mã 11 ký tự của 1 link video (watch / youtu.be / shorts / live) hoặc chính mã video."""
    link = str(link or "").strip()
    m = re.search(r"(?:v=|youtu\.be/|/shorts/|/video/|/live/)([\w-]{11})", link) or re.fullmatch(r"([\w-]{11})", link)
    if not m:
        raise StepError(f"Không đọc được mã video từ link: {link or '(trống)'}")
    return m.group(1)


def _say(msg):
    print(f"      · {msg}", flush=True)


def _visible_list(loc):
    try:
        return [loc.nth(i) for i in range(loc.count()) if loc.nth(i).is_visible()]
    except Exception:
        return []


SECTION_JS = r"""(h, tag) => {
  // đi ngược lên từ dòng tiêu đề tới khung của phần (khung có ảnh video, hoặc đủ cao)
  let e = h;
  for (let i = 0; i < 8 && e.parentElement; i++) {
    e = e.parentElement;
    const r = e.getBoundingClientRect();
    if (e.querySelector('img') && r.height > 60) break;
    if (r.height > 110) break;
  }
  document.querySelectorAll('[data-keo-sec="' + tag + '"]').forEach(x => x.removeAttribute('data-keo-sec'));
  e.setAttribute('data-keo-sec', tag);
  return true;
}"""


def _home_section(page, key):
    """Khung của phần trên Thẻ Trang chủ có tiêu đề khớp nhãn `key` (bỏ qua chữ nằm trong menu)."""
    pat = L(key)
    heads = [h for h in _visible_list(page.get_by_text(pat)) if not h.evaluate(
        "e => !!e.closest('tp-yt-paper-listbox, ytcp-text-menu, [role=menu], [role=listbox], tp-yt-paper-dialog')")]
    if not heads:
        return None
    heads[0].evaluate(SECTION_JS, key)
    loc = page.locator(f"[data-keo-sec='{key}']")
    return loc.first if loc.count() else None


def _ids_in(loc):
    try:
        return loc.evaluate(IDS_IN_JS)
    except Exception:
        return []


def _top_dialog(page):
    for sel in ("ytcp-video-pick-dialog tp-yt-paper-dialog", "tp-yt-paper-dialog", "ytcp-dialog",
                "[role=dialog]", "ytd-popup-container tp-yt-paper-dialog"):
        v = _visible_list(page.locator(sel))
        if v:
            return v[-1]
    return None


def pick_video_any(page, link, what):
    """Chọn ĐÚNG video `link` trong hộp chọn video đang mở (bất kỳ loại hộp nào của YouTube):
    dán link vào ô tìm kiếm, chỉ bấm vào kết quả có ảnh mang ĐÚNG mã video; không có -> báo lỗi, không chọn bừa."""
    import editors
    vid = _vid_of(link)
    url = f"https://www.youtube.com/watch?v={vid}"
    # hộp chọn video chuẩn của Studio (có ô "Tìm kiếm video của các kênh khác")
    if editors._wait(page, lambda: len(editors._visible(page, f"{editors.PICKER} input#search-any")) > 0, 6000):
        got, title = editors.pick_video(page, url=url, verify=False)
        if got != vid:
            raise StepError(f"{what}: hộp chọn trả về video {got}, không phải {vid}.")
        return title
    d = _top_dialog(page)
    if d is None:
        raise StepError(f"{what}: hộp chọn video không mở ra.")
    for tab in _visible_list(d.get_by_role("tab", name=L("url_tab"))):
        tab.click()
        page.wait_for_timeout(800)
        break
    boxes = [b for b in _visible_list(d.locator("input")) if b.is_editable()]
    if not boxes:
        raise StepError(f"{what}: hộp chọn video không có ô tìm kiếm / ô dán link.")
    box = boxes[0]
    found = None
    for q in (url, f"https://youtu.be/{vid}", vid):
        _say(f"dán '{q}' vào ô tìm kiếm của hộp chọn")
        human.paste(box, q)
        box.press("Enter")
        for _ in range(30):
            page.wait_for_timeout(500)
            cands = _visible_list(d.locator(f"[style*='{vid}'], img[src*='{vid}'], a[href*='{vid}']"))
            if cands:
                found = cands[0]
                break
        if found:
            break
    if not found:
        raise StepError(f"{what}: dán link nhưng hộp chọn không hiện video mã {vid} – YouTube có thể chỉ cho "
                        f"chọn video của chính kênh mạnh ở mục này. Tool KHÔNG chọn video khác.")
    opt = found.locator("xpath=ancestor-or-self::*[@role='option' or self::ytcp-entity-card or "
                        "self::ytd-video-renderer or self::ytcp-video-row][1]")
    target = opt.first if opt.count() else found
    title = (target.get_attribute("aria-label") or target.inner_text() or "").strip().splitlines()[0][:80] \
        if target else ""
    _say(f"bấm vào video {vid}")
    target.click()
    page.wait_for_timeout(1200)
    if d.is_visible():  # có hộp thì phải bấm Chọn / Xong / Thêm
        for key in ("select", "done", "add"):
            btns = [b for b in _visible_list(d.get_by_role("button", name=L(key)))
                    if b.get_attribute("aria-disabled") != "true"]
            if btns:
                btns[-1].click()
                page.wait_for_timeout(1500)
                break
    return title


LIST_ITEMS_JS = r"""(root) => {
  // các video trong hộp chọn, theo thứ tự hiển thị (trên xuống) – mỗi mục: mã video + vị trí
  const seen = new Set(), out = [];
  root.querySelectorAll('img, [style*="/vi/"], a[href*="watch?v="], a[href*="/shorts/"]').forEach(e => {
    const s = (e.getAttribute('src') || '') + ' ' + (e.getAttribute('style') || '') + ' ' + (e.getAttribute('href') || '');
    const m = s.match(/(?:\/vi(?:_webp)?\/|[?&]v=|\/shorts\/)([\w-]{11})/);
    if (!m || seen.has(m[1])) return;
    const r = e.getBoundingClientRect();
    if (r.width < 20 || r.height < 12) return;
    seen.add(m[1]); out.push({id: m[1], y: r.top, x: r.left});
  });
  return out;
}"""


def pick_from_list(page, vid=None, what="Bài đăng video", fallback_root=None):
    """Hộp chọn video dạng DANH SÁCH (không có ô dán link – vd hộp Video của Bài đăng):
    vid=None -> bấm video ĐẦU TIÊN (mới nhất); vid=mã -> chỉ bấm đúng video có mã đó.
    Trả về (mã video, tiêu đề)."""
    d = None
    items = []
    for i in range(40):  # ~20 giây: chờ danh sách + ảnh thu nhỏ tải xong
        page.wait_for_timeout(500)
        roots = [r for r in (_top_dialog(page), fallback_root() if fallback_root else None) if r is not None]
        for r in roots:  # hộp thoại riêng, hoặc danh sách hiện ngay trong khung soạn bài
            try:
                items = r.evaluate(LIST_ITEMS_JS)
            except Exception:
                items = []
            if items:
                d = r
                break
        if items:
            break
        if i in (8, 16, 24):  # ảnh tải chậm: cuộn nhẹ trong vùng danh sách để YouTube tải ảnh
            try:
                for r in roots:
                    r.evaluate("e => { e.scrollTop = 200; e.scrollTop = 0; }")
            except Exception:
                pass
    if not items:
        raise StepError(f"{what}: đã bấm 'Video' nhưng không thấy danh sách video để chọn "
                        f"(xem ảnh lỗi trong logs/screenshots).")
    if vid is None:
        target_id = items[0]["id"]
        _say(f"chọn video MỚI NHẤT trong danh sách: {target_id}")
    else:
        if vid not in [i["id"] for i in items]:
            raise StepError(f"{what}: danh sách trong hộp chọn không có video {vid} (hộp này chỉ hiện video "
                            f"của chính kênh mạnh). Tool KHÔNG chọn video khác.")
        target_id = vid
    el = d.locator(f"img[src*='{target_id}'], [style*='{target_id}'], a[href*='{target_id}']").first
    opt = el.locator("xpath=ancestor-or-self::*[@role='option' or @role='button' or self::a or "
                     "self::ytd-video-renderer or self::ytcp-entity-card][1]")
    target = opt.first if opt.count() else el
    title = ""
    try:
        title = (target.get_attribute("aria-label") or target.get_attribute("title") or "").strip()
        if not title:
            row = el.locator("xpath=ancestor::*[string-length(normalize-space(.)) > 3][1]")
            title = (row.first.inner_text() or "").strip().splitlines()[0]
    except Exception:
        pass
    _say(f"bấm vào video {target_id} {('– ' + title[:50]) if title else ''}")
    target.click()
    page.wait_for_timeout(1200)
    try:
        still = d.is_visible() and d.evaluate("e => !!e.closest('tp-yt-paper-dialog, [role=dialog], ytd-popup-container')")
    except Exception:
        still = False
    if still:  # hộp thoại riêng: bấm Chọn / Xong / Thêm
        for key in ("select", "done", "add"):
            btns = [b for b in _visible_list(d.get_by_role("button", name=L(key)))
                    if b.get_attribute("aria-disabled") != "true"]
            if btns:
                btns[-1].click()
                page.wait_for_timeout(1500)
                break
    return target_id, title


def set_home_video(page, key, name, link):
    """Đặt ĐÚNG video `link` vào phần `name` của Thẻ Trang chủ (phần video giới thiệu / video nổi bật).
    Trả về (ghi chú, mã video cũ)."""
    vid = _vid_of(link)
    sec = _home_section(page, key)
    old = _ids_in(sec) if sec is not None else []
    if sec is not None and vid in old:
        return f"{name}: đã đúng video {vid} – giữ nguyên", ",".join(old)
    if sec is not None:
        _say(f"'{name}' đang là video {', '.join(old) or '(không rõ)'} – đổi sang {vid}")
        sec.hover()
        page.wait_for_timeout(800)
        # nút ⋮ thật: ytcp-icon-button#overflow-menu-button (aria-label "Tùy chọn"), nằm cạnh tiêu đề phần
        try:
            sec.evaluate("""(box, key) => {
                document.querySelectorAll('[data-keo-ovf]').forEach(x => x.removeAttribute('data-keo-ovf'));
                let e = box;
                for (let i = 0; i < 8 && e; i++, e = e.parentElement) {
                  const bs = e.querySelectorAll('#overflow-menu-button');
                  if (bs.length === 1) { bs[0].setAttribute('data-keo-ovf', key); return true; }
                  if (bs.length > 1) return false;   // đã lên tới khung chứa nhiều phần -> dừng
                }
                return false; }""", key)
        except Exception:
            pass
        ovf = page.locator(f"[data-keo-ovf='{key}']")
        btns = ([ovf.first] if ovf.count() else []) + \
            _visible_list(sec.locator("ytcp-icon-button, button, [role=button]"))
        menu = ([btns[0]] if ovf.count() else []) or \
            [b for b in btns if L("more_actions").search(b.get_attribute("aria-label") or "")
             or "more" in (b.get_attribute("icon") or "")]
        if not menu:  # nút ⋮ không có nhãn: lấy nút biểu tượng (không có chữ) cuối cùng trong khung
            menu = [b for b in btns if not (b.inner_text() or "").strip()][-1:]
        opened = False
        how = "không thấy nút ⋮ của phần này"
        if menu:
            menu[-1].click()
            page.wait_for_timeout(1000)
            all_items = _visible_list(page.locator("tp-yt-paper-item, [role=menuitem], [role=option]"))
            names = [re.sub(r"\s+", " ", (i.inner_text() or "")).strip() for i in all_items]
            items = [i for i, n in zip(all_items, names) if L("change_video").search(n)]
            how = "menu ⋮ có: " + (", ".join(n for n in names if n)[:150] or "(trống)")
            if items:
                _say(f"chọn '{names[all_items.index(items[0])]}' trong menu ⋮")
                items[0].click()
                opened = True
            else:
                page.keyboard.press("Escape")
        if not opened:
            # không có menu: bấm vào ảnh / tiêu đề video trong phần đó
            _say("bấm vào ảnh video của phần này để đổi video")
            tgt = _visible_list(sec.locator("img")) or [sec]
            tgt[0].click()
            how += "; đã bấm vào ảnh video"
    else:
        _say(f"chưa có phần '{name}' – bấm 'Thêm phần kênh'")
        how = "bấm 'Thêm phần kênh'"
        click(page, "add_section", timeout=8000)
        page.wait_for_timeout(1000)
        items = [i for i in _visible_list(page.locator("tp-yt-paper-item, [role=menuitem], [role=option], "
                                                       "ytcp-ve, li"))
                 if L(key).search(i.inner_text() or "")]
        if not items:
            page.keyboard.press("Escape")
            raise StepError(f"Menu 'Thêm phần kênh' không có mục '{name}'.")
        items[-1].click()
    page.wait_for_timeout(1500)
    try:
        title = pick_video_any(page, link, name)
    except StepError as e:
        d = _top_dialog(page)
        seen = re.sub(r"\s+", " ", (d.inner_text() if d is not None else "") or "")[:120]
        raise StepError(f"{e} [{how}; hộp đang mở: {seen or 'không có'}]")
    # kiểm tra: phần đó phải hiện ĐÚNG video vừa chọn
    for _ in range(20):
        page.wait_for_timeout(500)
        sec = _home_section(page, key)
        if sec is not None and vid in _ids_in(sec):
            return f"{name}: {title[:40]} ({vid})", ",".join(old)
    raise StepError(f"{name}: đã chọn video {vid} nhưng phần này chưa hiện đúng video đó.")


def setup_home_tab(page, strong_id, weak, already=(), opts=None, notes=()):
    """`opts` (strong_setup trong file kênh): link video giới thiệu / video nổi bật, bật/tắt từng phần.
    `already`: tên các phần làm 1 lần đã xong ở lần chạy trước -> bỏ qua để không bị trùng.
    Trả về ghi chú; kèm danh sách mục đã gắn trong thuộc tính HOME_LAST (để ghi nhật ký đối soát)."""
    global HOME_LAST
    HOME_LAST = []
    opts = opts or {}
    url = f"{STUDIO}/channel/{strong_id}/editing/profile"
    if on_page(page, url) and not getattr(page, "_keo_profile_dirty", True):
        say_ = "đang ở trang Tùy chỉnh kênh (vừa làm xong Hồ sơ) – chuyển sang tab Thẻ Trang chủ, không tải lại"
        print(f"      · {say_}", flush=True)
    else:
        page.goto(url, wait_until="domcontentloaded")
        page.wait_for_timeout(6000)
    tab = None
    for loc in (page.get_by_role("tab", name=L("home_tab")), page.get_by_text(L("home_tab"))):
        try:
            loc.first.wait_for(state="visible", timeout=5000)
            tab = loc.first
            break
        except Exception:
            continue
    if tab is None:
        raise StepError("Không thấy tab 'Thẻ Trang chủ' trên trang Tùy chỉnh kênh.")
    tab.click()
    page.wait_for_timeout(4000)
    done, warn, skipped, nodata, changed = [], [], [], [], False

    def part(name, fn, ready=True, why="", enabled=True):
        nonlocal changed
        if not enabled:
            return
        if name in already and name in HOME_ONCE:
            skipped.append(name)
            return
        if not ready:
            nodata.append(f"{name} ({why})")
            _say(f"bỏ qua '{name}': {why}")
            return
        _say(name)
        try:
            res = fn()
            if isinstance(res, str) and "giữ nguyên" in res:
                skipped.append(name)
                _say(f"   {res}")
            else:
                done.append(name)
                changed = True
        except Exception as e:
            warn.append(f"{name}: {str(e).splitlines()[0][:180]}")
            try:
                close_dialogs(page)
            except Exception:
                pass

    def video_part(key, name, link, slot):
        def run():
            note, old = set_home_video(page, key, name, link)
            if "giữ nguyên" in note:   # video đã đúng từ trước – tool không đổi gì, không ghi là đã gắn
                return note
            HOME_LAST.append(dict(slot=slot, time="", id=_vid_of(link), url=link,
                                  title=note.split(": ", 1)[-1], owner="weak", old=old))
            return note
        return run

    def playlist():
        click(page, "add_section")
        click(page, "single_playlist")
        fill_search_and_pick(page, dialog(page), playlist_url(pl))
        HOME_LAST.append(dict(slot="Trang chủ – Danh sách phát đơn", time="", id="", url=playlist_url(pl),
                              title="Danh sách phát", owner="weak"))

    def featured():
        click(page, "add_section")
        click(page, "featured_channels")
        d = dialog(page)
        title = d.get_by_label(L("section_title"))
        try:
            if title.count() and title.first.is_visible():
                _type_into(title.first, weak["name"])
        except Exception:
            pass
        fill_search_and_pick(page, d, weak["name"], alternatives=[weak["url"], _handle(weak["url"])],
                             match_text=weak["name"])
        click(page, "done", scope=d)
        HOME_LAST.append(dict(slot="Trang chủ – Kênh nổi bật", time="", id="", url=weak.get("url", ""),
                              title=weak.get("name", ""), owner="weak"))

    trailer = str(opts.get("trailer_video") or "").strip()
    feat = str(opts.get("featured_video") or "").strip()
    pl = str(weak.get("playlist") or "").strip()
    part("Video giới thiệu cho người chưa ĐK",
         video_part("sec_trailer", "Video giới thiệu kênh cho người chưa đăng ký", trailer,
                    "Trang chủ – Video giới thiệu (người chưa ĐK)"),
         bool(trailer), "chưa dán link video", opts.get("do_trailer", True))
    part("Video nổi bật cho người ĐK cũ",
         video_part("sec_featured", "Video nổi bật dành cho người đăng ký cũ", feat,
                    "Trang chủ – Video nổi bật (người ĐK cũ)"),
         bool(feat), "chưa dán link video", opts.get("do_featured", True))
    part("Danh sách phát đơn", playlist, "list=" in pl, "chưa điền link danh sách phát",
         opts.get("do_playlist", True))
    part("Kênh nổi bật", featured, bool(weak.get("name") or weak.get("url")), "chưa điền tên/link kênh cần kéo",
         opts.get("do_featured_channel", True))
    warn += [n for n in notes if n]

    note = (f"Đã làm: {', '.join(done)}. " if done else "") + \
           (f"Đã có sẵn: {', '.join(skipped)}. " if skipped else "") + \
           (f"Không làm (bạn để trống): {'; '.join(nodata)}. " if nodata else "")   # để trống = chủ ý, không phải lỗi
    if changed:
        _say("bấm Xuất bản")
        click(page, "publish", timeout=6000)
        page.wait_for_timeout(4000)
    if not done and not skipped and not warn:
        return already_ok("không có phần Trang chủ nào cần làm") if not nodata else note.strip()
    if not done and not skipped:
        raise StepError("Không làm được phần nào trên thẻ Trang chủ. " + " | ".join(warn))
    if not warn:
        return note.strip()
    raise NeedsCheck(note + " | ".join(warn))


HOME_LAST = []


# ===================== Bài đăng có video (trang kênh mạnh) =====================

def _composer(page):
    """Khung soạn bài đăng: phần tử nhỏ nhất chứa cả nút 'Đăng' và nút 'Hủy'."""
    for sel in ("ytd-backstage-post-dialog-renderer", "ytd-commentbox#commentbox", "#creation-box"):
        v = _visible_list(page.locator(sel))
        if v:
            return v[0]
    btn = _visible_list(page.get_by_role("button", name=L("post_submit")))
    if btn:
        box = btn[0].locator("xpath=ancestor::*[.//*[@contenteditable='true'] or .//textarea][1]")
        if box.count():
            return box.first
    return None


def _norm_space(t):
    return re.sub(r"\s+", " ", str(t or "").replace("\u00a0", " ")).strip()


POST_CONFIRM = re.compile(r"^\s*(Chèn|Insert|Lưu|Thêm|Thêm video|Chọn|Xong|Đính kèm|Tiếp|Đồng ý|OK|"
                          r"Save|Add|Add video|Select|Done|Attach|Next)\s*$", re.I)

POST_PICKER_TITLE = re.compile(r"Thêm một video YouTube hiện có|Add an existing YouTube video|"
                               r"Thêm video|Add a video|Chọn video|Select a video", re.I)
MY_CHANNEL = re.compile(r"^\s*(Kênh của tôi|My channel|Your channel|Kênh của bạn)\s*$", re.I)

FIRST_ROW_JS = r"""(root) => {
  // dòng video ĐẦU TIÊN ngay dưới chữ "Kênh của tôi" (video đăng mới nhất); đánh dấu để bấm
  root = root || document.body;
  const vis = e => { const r = e.getBoundingClientRect(); return r.width > 40 && r.height > 30; };
  // CHỈ tìm trong hộp "Thêm một video YouTube hiện có": phần tử nhỏ nhất chứa cả tiêu đề hộp và chữ
  // "Kênh của tôi" (KHÔNG lấy mục "Kênh của bạn" ở cột menu trái của YouTube)
  const heads = [...root.querySelectorAll('*')].filter(e => e.childElementCount === 0 && vis2(e) &&
      /^\s*(Kênh của tôi|My channel)\s*$/i.test(e.textContent || ''));
  function vis2(e) { const r = e.getBoundingClientRect(); return r.width > 0 && r.height > 0; }
  if (!heads.length) return null;
  const TITLE = /Thêm một video YouTube hiện có|Add an existing YouTube video/i;
  let box = heads[0];
  while (box && box !== root && !TITLE.test(box.innerText || '')) box = box.parentElement;
  if (!box || box === document.body || box === document.documentElement) {
    // hộp nằm trong khung riêng (iframe) không có tiêu đề -> lấy khung gần nhất chứa nhiều dòng video
    box = heads[0].parentElement;
    for (let i = 0; i < 6 && box && box.parentElement && box !== document.body; i++) box = box.parentElement;
  }
  if (!box || box === document.body && !TITLE.test(document.body.innerText || '')) return null;
  root = box;
  const headY = heads[0].getBoundingClientRect().bottom;
  const isRow = e => vis(e) && e.querySelector('img, yt-image, [style*="/vi/"]') && (e.innerText || '').trim().length > 5;
  // dòng = phần tử nhỏ nhất có ảnh + chữ, nằm dưới "Kênh của tôi"
  let rows = [...root.querySelectorAll('*')].filter(e => isRow(e) &&
      e.getBoundingClientRect().top >= headY - 2 &&
      ![...e.children].some(c => isRow(c) && /lượt xem|views?\b|•/i.test(c.innerText || '')));
  const views = rows.filter(e => /lượt xem|views?\b|•/i.test(e.innerText || ''));
  if (views.length) rows = views;
  rows.sort((a, b) => a.getBoundingClientRect().top - b.getBoundingClientRect().top ||
                      a.getBoundingClientRect().left - b.getBoundingClientRect().left);
  if (!rows.length) return null;
  const row = rows[0];
  document.querySelectorAll('[data-keo-row]').forEach(x => x.removeAttribute('data-keo-row'));
  row.setAttribute('data-keo-row', '1');
  const lines = (row.innerText || '').split('\n').map(s => s.trim()).filter(s => s && !/^\d+(:\d\d)+$/.test(s));
  const s = [...row.querySelectorAll('img, a[href], [style*="/vi/"]')].map(e =>
      (e.getAttribute('src') || '') + ' ' + (e.getAttribute('href') || '') + ' ' + (e.getAttribute('style') || '')).join(' ');
  const m = s.match(/(?:\/vi(?:_webp)?\/|[?&]v=|youtu\.be\/|\/shorts\/)([\w-]{11})/);
  return {title: lines[0] || '', id: m ? m[1] : ''};
}"""


def _post_picker(page):
    """Hộp 'Thêm một video YouTube hiện có' của Bài đăng (phần tử chứa tiêu đề hộp + ô tìm kiếm)."""
    for h in _visible_list(page.get_by_text(POST_PICKER_TITLE)):
        box = h.locator("xpath=ancestor::*[.//input][1]")
        try:
            if box.count() and box.first.is_visible():
                return box.first
        except Exception:
            continue
    return _top_dialog(page)


POST_ITEM = "ytd-backstage-post-thread-renderer, ytd-post-renderer, ytd-backstage-post-renderer"


def _existing_posts(page, vid="", title=""):
    """Các bài đăng ĐÃ CÓ trên tab Bài đăng có gắn video này (theo mã video hoặc đúng tiêu đề)."""
    key = _norm_space(title).lower()[:40]
    out = []
    for it in _visible_list(page.locator(POST_ITEM)):
        try:
            if it.evaluate("e => !!e.parentElement && !!e.parentElement.closest('ytd-backstage-post-thread-renderer, "
                           "ytd-post-renderer, ytd-backstage-post-renderer')"):
                continue   # phần tử con của 1 bài đăng khác
            if (vid and vid in _ids_in(it)) or (key and key in _norm_space(it.inner_text()).lower()):
                out.append(it)
        except Exception:
            continue
    return out


POST_MENU_JS = r"""(post) => {
  // nút ⋮ CỦA BÀI ĐĂNG (góc trên bên phải), KHÔNG phải nút ⋮ của video gắn trong bài
  const vis = e => { const r = e.getBoundingClientRect(); return r.width > 0 && r.height > 0; };
  document.querySelectorAll('[data-keo-pmenu]').forEach(x => x.removeAttribute('data-keo-pmenu'));
  const inner = 'ytd-video-renderer, ytd-grid-video-renderer, ytd-compact-video-renderer, yt-lockup-view-model, ' +
                '#content-attachment, ytd-backstage-image-renderer, ytd-post-multi-image-renderer';
  // đúng như trang thật: ⋮ của bài đăng nằm trong #action-menu của ytd-backstage-post-renderer
  const own = [...post.querySelectorAll('#action-menu ytd-menu-renderer button, #action-menu button')]
    .filter(b => !b.closest(inner) && vis(b));
  if (own.length) { own[0].setAttribute('data-keo-pmenu', '1'); return own.length; }
  const cands = [...post.querySelectorAll('ytd-menu-renderer button, ytd-menu-renderer yt-icon-button, ' +
                                          '#action-menu button, #action-menu-button button, button[aria-label]')]
    .filter(vis).filter(b => !b.closest(inner))
    .filter(b => (b.innerText || '').trim().length <= 2 || /tác vụ|thao tác|action|thêm|more/i.test(b.getAttribute('aria-label') || ''));
  if (!cands.length) return 0;
  const pr = post.getBoundingClientRect();
  cands.sort((a, b) => a.getBoundingClientRect().top - b.getBoundingClientRect().top ||
                       b.getBoundingClientRect().left - a.getBoundingClientRect().left);
  // chỉ lấy nút nằm ở phần đầu bài (trên ảnh video)
  const top = cands.filter(b => b.getBoundingClientRect().top - pr.top < 120);
  (top[0] || cands[0]).setAttribute('data-keo-pmenu', '1');
  return cands.length; }"""


def _delete_post(page, post):
    """Xóa 1 bài đăng: ⋮ CỦA BÀI (góc trên bên phải) → Xóa → xác nhận Xóa.
    Không bấm nhầm ⋮ của video gắn trong bài (menu đó chỉ có 'Thêm vào danh sách chờ', 'Lưu'...)."""
    post.scroll_into_view_if_needed()
    post.hover()
    page.wait_for_timeout(700)
    if not post.evaluate(POST_MENU_JS):
        raise StepError("Không thấy nút ⋮ của bài đăng.")
    btn = page.locator("[data-keo-pmenu='1']").first
    try:
        btn.click(timeout=6000)
    except Exception:
        btn.evaluate("e => e.click()")
    page.wait_for_timeout(1200)
    got = ""
    for _ in range(6):
        got = page.evaluate(MENU_ITEM_JS, L("delete").pattern)
        if got:
            break
        page.wait_for_timeout(500)
    if not got:
        names = ""
        try:
            names = re.sub(r"\s+", " ", page.locator("tp-yt-iron-dropdown:visible, ytd-menu-popup-renderer:visible")
                           .last.inner_text() or "")[:120]
        except Exception:
            pass
        page.keyboard.press("Escape")
        raise StepError(f"Menu ⋮ của bài đăng không có 'Xóa' (menu có: {names or 'trống'}) – tài khoản đang đăng "
                        f"nhập có thể không phải chủ kênh.")
    _menu_pick(page, L("delete"), "Xóa")
    _confirm_delete(page)
    page.wait_for_timeout(2000)


POST_LAST_ID = ""   # video của bài đăng vừa làm (để kiểm tra lại khi bước báo lỗi)


def check_post(page, strong_id, vid):
    """Tải lại tab Bài đăng: đã có bài đăng của video `vid` -> trả câu mô tả (bước coi như hoàn thành)."""
    if not vid:
        return ""
    page.goto(f"https://www.youtube.com/channel/{strong_id}/posts", wait_until="domcontentloaded")
    page.wait_for_timeout(5000)
    for _ in range(3):
        page.mouse.wheel(0, 1500)
        page.wait_for_timeout(800)
    if _existing_posts(page, vid, ""):
        return f"tải lại tab Bài đăng thấy đã có bài đăng của video ({vid})"
    return ""


def post_video(page, strong_id, link=None, text="", skip_ids=(), replace=False):
    """Bài đăng có video trên trang kênh mạnh – đúng như làm tay:
    tab Bài đăng → Video → hộp 'Thêm một video YouTube hiện có' → bấm video ĐẦU TIÊN ở mục 'Kênh của tôi'
    (video đăng mới nhất) → nội dung bài = ĐÚNG tiêu đề video đó (nếu không điền nội dung riêng) → Đăng.
    link: chỉ định 1 video cụ thể (dán link vào ô tìm kiếm của hộp). skip_ids: video đã đăng bài -> không đăng trùng."""
    global POST_LAST_ID
    vid = _vid_of(link) if link else None
    POST_LAST_ID = vid or ""
    page.goto(f"https://www.youtube.com/channel/{strong_id}/posts", wait_until="domcontentloaded")
    page.wait_for_timeout(6000)
    comp = _composer(page)
    if comp is None or not _visible_list(comp.get_by_text(L("type_video"))):
        for loc in (page.get_by_placeholder(L("post_box")), page.get_by_text(L("post_box")),
                    page.locator("ytd-backstage-post-dialog-renderer, #placeholder-area, #commentbox")):
            v = _visible_list(loc)
            if v:
                v[0].click()
                page.wait_for_timeout(1500)
                break
        comp = _composer(page)
    if comp is None:
        raise StepError("Không thấy khung tạo Bài đăng trên trang kênh mạnh (tab Bài đăng).")
    vbtn = [b for b in _visible_list(comp.get_by_text(L("type_video")))]
    if not vbtn:
        raise StepError("Không thấy nút 'Video' trong khung tạo Bài đăng.")
    _say("bấm 'Video' trong khung tạo bài đăng")
    vbtn[0].click()

    def cancel():
        """Đóng hộp chọn video (nút X ở góc hộp) rồi bấm Hủy ở khung soạn bài."""
        for fr in page.frames:
            try:
                if not fr.evaluate(f"() => !!({FIRST_ROW_JS})(document.body)"):
                    continue
                xs = [x for x in _visible_list(fr.get_by_role("button", name=re.compile(r"Đóng|Close|Hủy|Cancel", re.I)))
                      if not x.evaluate("e => !!e.closest('ytd-backstage-post-dialog-renderer')")]
                if xs:
                    xs[0].click(timeout=5000)
                    page.wait_for_timeout(1000)
            except Exception:
                continue
        page.keyboard.press("Escape")
        page.wait_for_timeout(600)
        for b in _visible_list(page.get_by_role("button", name=L("post_cancel"))):
            try:
                b.click(timeout=5000)
            except Exception:
                pass
            break
        page.wait_for_timeout(800)

    # --- chọn video trong hộp "Thêm một video YouTube hiện có" (hộp có thể nằm trong khung trang riêng - iframe)
    info, frame, pasted = None, None, False
    for _ in range(50):  # ~25 giây chờ hộp + danh sách "Kênh của tôi" hiện ra
        page.wait_for_timeout(500)
        for fr in page.frames:
            if vid and not pasted:
                try:
                    boxes = [x for x in _visible_list(fr.get_by_placeholder(
                        re.compile("dán URL|paste URL|Tìm kiếm|Search", re.I))) if x.is_editable()]
                except Exception:
                    boxes = []
                if boxes:
                    _say(f"dán link video vào ô tìm kiếm: {link}")
                    human.paste(boxes[0], f"https://www.youtube.com/watch?v={vid}")
                    boxes[0].press("Enter")
                    pasted = True
                    page.wait_for_timeout(3500)
            try:
                info = fr.evaluate(f"() => ({FIRST_ROW_JS})(document.body)")
            except Exception:
                info = None
            if info:
                frame = fr
                break
        if info:
            break
    if not info:
        cancel()
        raise StepError("Đã mở hộp 'Thêm một video YouTube hiện có' nhưng không thấy dòng video nào dưới "
                        f"'Kênh của tôi' (đã tìm trong {len(page.frames)} khung trang).")
    if vid and info.get("id") and info["id"] != vid:
        cancel()
        raise StepError(f"Kết quả tìm kiếm là video {info['id']}, không phải {vid} – không đăng.")
    title = info.get("title", "").strip()
    POST_LAST_ID = info.get("id") or vid or ""
    olds = _existing_posts(page, info.get("id") or vid or "", title)
    if olds:   # video này ĐÃ có bài đăng (đúng như yêu cầu) -> bỏ qua, kể cả khi chọn "Thay thế cái cũ"
        cancel()
        return already_ok(f"video '{title[:60]}'" + (f" ({info['id']})" if info.get("id") else "") +
                          " đã có bài đăng trên tab Bài đăng – bỏ qua")
    _say(f"bấm vào video {'mới nhất' if not vid else ''}: {title[:70]}" + (f" ({info['id']})" if info.get("id") else ""))
    row = frame.locator("[data-keo-row='1']").first
    try:
        row.click(timeout=8000)
    except Exception:  # bấm thẳng vào giữa dòng video
        bb = human.bbox(row)
        if not bb:
            cancel()
            raise StepError("Không bấm được vào dòng video mới nhất.")
        human.mouse_click(page, bb["x"] + min(120, bb["width"] / 2), bb["y"] + bb["height"] / 2)
    page.wait_for_timeout(2500)

    # --- hộp chọn phải đóng lại, và trang phải hiện video vừa bấm (ảnh có mã video hoặc đúng tiêu đề)
    def picker_open():
        """Hộp chọn còn mở = vẫn còn thấy mục 'Kênh của tôi' với các dòng video (không dựa vào chữ tiêu đề,
        vì chữ 'Thêm một video YouTube hiện có' còn nằm trong chú thích của nút Video)."""
        for fr in page.frames:
            try:
                if fr.evaluate(f"() => !!({FIRST_ROW_JS})(document.body)"):
                    return fr
            except Exception:
                continue
        return None
    def confirm_picker(fr):
        """Hộp chọn còn mở sau khi tích video -> cuộn xuống cuối hộp, bấm nút xác nhận (Lưu / Thêm / Chọn / Xong)."""
        btns = []
        for loc in (fr.get_by_role("button", name=POST_CONFIRM), fr.locator("button, ytd-button-renderer, "
                    "yt-button-shape, tp-yt-paper-button").filter(has_text=POST_CONFIRM)):
            try:
                for i in range(loc.count()):
                    b = loc.nth(i)
                    txt = re.sub(r"\s+", " ", (b.inner_text() or b.get_attribute("aria-label") or "")).strip()
                    in_box = fr is not page.main_frame or b.evaluate(
                        "e => !!e.closest('tp-yt-paper-dialog, ytd-popup-container, [role=dialog], "
                        "yt-dialog-view-model, ytd-unified-share-panel-renderer, [aria-modal=true]') || "
                        "(() => { let x = e; for (let i = 0; i < 12 && x; i++, x = x.parentElement)"
                        "  if (x.querySelector && x.querySelector('[data-keo-row]') && x !== document.body) return true;"
                        "  return false; })()")
                    if POST_CONFIRM.match(txt) and b.get_attribute("aria-disabled") != "true" and in_box \
                            and b.is_visible():
                        btns.append((b, txt))
            except Exception:
                continue
        if not btns:
            return False
        btns.sort(key=lambda bt: 0 if re.match(r"^\s*(Chèn|Insert)\s*$", bt[1], re.I) else 1)  # ưu tiên nút "Chèn"
        b, txt = btns[0]
        try:
            b.evaluate("e => e.scrollIntoView({block: 'center'})")   # nút ở cuối hộp: cuộn xuống trước
            page.wait_for_timeout(500)
        except Exception:
            pass
        _say(f"kéo xuống cuối hộp, bấm '{txt}'")
        try:
            b.click(timeout=6000)
        except Exception:
            b.evaluate("e => e.click()")
        page.wait_for_timeout(2000)
        return True

    ok, got_id = False, info.get("id") or ""
    key = _norm_space(title)[:28]
    for i in range(60):  # ~30 giây
        page.wait_for_timeout(500)
        fr_open = picker_open()
        if fr_open is not None:
            if i % 4 == 0:   # hộp vẫn mở -> bấm nút xác nhận ở cuối hộp
                confirm_picker(fr_open)
            continue
        comp = _composer(page)
        ids = _ids_in(comp) if comp is not None else []
        if got_id and got_id in ids:
            ok = True
            break
        if key and comp is not None:   # chỉ tính video hiện TRONG khung soạn bài, không tính bài đăng cũ bên dưới
            box = comp.locator("xpath=ancestor-or-self::*[.//*[@contenteditable='true'] or .//textarea]"
                               "[.//button][1]")
            scope = box.first if box.count() else comp
            if key.lower() in _norm_space(scope.inner_text()).lower():
                ok = True
                got_id = got_id or (ids[0] if len(ids) == 1 else "")
                break
    if not ok:
        try:  # chụp NGAY lúc lỗi (trước khi hủy) để biết YouTube đang hiện gì
            import os
            from datetime import datetime
            os.makedirs(os.path.join("logs", "screenshots"), exist_ok=True)
            page.screenshot(path=os.path.join("logs", "screenshots",
                                              f"{datetime.now():%Y%m%d_%H%M%S}_baidang_truoc_khi_huy.png"))
        except Exception:
            pass
        cancel()
        raise StepError(f"Đã bấm video '{title[:50]}' nhưng sau 30 giây khung bài đăng vẫn chưa hiện video đó "
                        f"(video mới có thể đang xử lý / chưa công khai) – đã hủy, không đăng.")
    if got_id and got_id in set(skip_ids or ()):
        cancel()
        return already_ok(f"video ({got_id}) đã được đăng bài trước đó – không đăng trùng")

    # --- nội dung bài = đúng tiêu đề video (hoặc nội dung bạn điền riêng)
    body = (text or "").strip() or title
    if body:
        ed = _visible_list(comp.locator("[contenteditable='true'], textarea"))
        if ed:
            _say(f"điền nội dung bài đăng: {body[:70]}")
            ed[0].click()
            page.keyboard.press("Control+A") if ed[0].evaluate("e => e === document.activeElement || e.contains(document.activeElement)") else None
            page.keyboard.insert_text(body)
            page.wait_for_timeout(600)
    sub = []
    for _ in range(20):   # nút Đăng mở khi YouTube xử lý xong video gắn kèm
        sub = [b for b in _visible_list(comp.get_by_role("button", name=L("post_submit")))
               if b.get_attribute("aria-disabled") != "true" and not b.is_disabled()]
        if sub:
            break
        page.wait_for_timeout(500)
    if not sub:
        cancel()
        raise StepError("Nút 'Đăng' vẫn khóa sau 10 giây – video chưa gắn được vào bài (đã hủy, không đăng).")
    _say("bấm Đăng")
    sub[-1].click()
    page.wait_for_timeout(5000)
    if got_id:
        posted = _visible_list(page.locator(f"ytd-backstage-post-thread-renderer:has([href*='{got_id}']), "
                                            f"ytd-backstage-post-thread-renderer:has(img[src*='{got_id}']), "
                                            f"ytd-post-renderer:has([href*='{got_id}'])"))
        if not posted:
            raise NeedsCheck(f"Đã bấm Đăng bài có video '{title[:50]}' ({got_id}) nhưng chưa thấy bài trong "
                             f"danh sách – hãy xem lại tab Bài đăng.")
    return f"Bài đăng video: {title[:60]}" + (f" ({got_id})" if got_id else "")


# ===================== Quét video đang có view =====================

REALTIME_JS = r"""
(labels) => {
  const rowsFrom = (root) => {
    const out = [];
    root.querySelectorAll('a[href*="/video/"]').forEach(a => {
      const m = a.href.match(/\/video\/([\w-]{11})/);
      if (!m) return;
      let row = a, i = 0;
      while (row.parentElement && i < 6 && !/\d/.test((row.innerText || '').replace(m[1], ''))) {
        row = row.parentElement; i++;
      }
      const nums = ((row.innerText || '').match(/\d[\d.,]*/g) || [])
        .map(s => parseInt(s.replace(/[.,]/g, ''))).filter(n => !isNaN(n));
      out.push({id: m[1], views: nums.length ? nums[nums.length - 1] : 0});
    });
    return out;
  };
  // tìm khung "Thời gian thực" rồi chỉ đọc video trong khung đó
  const all = [...document.querySelectorAll('*')].filter(e =>
      e.childElementCount === 0 && labels.some(l => (e.textContent || '').trim().startsWith(l)));
  for (const h of all) {
    let c = h;
    for (let i = 0; i < 10 && c; i++) {
      c = c.parentElement;
      if (c && c.querySelector('a[href*="/video/"]')) return {scope: 'realtime', rows: rowsFrom(c)};
    }
  }
  return {scope: 'page', rows: rowsFrom(document)};
}"""


def scan_realtime(page, strong_id, min_views):
    """Mở Số liệu phân tích, tự đọc khung 'Thời gian thực'. Trả về list (link, số view) đạt ngưỡng."""
    print("Đang mở trang Số liệu phân tích của kênh mạnh...", flush=True)
    page.bring_to_front()
    page.goto(f"{STUDIO}/channel/{strong_id}/analytics/tab-overview/period-default",
              wait_until="domcontentloaded")
    page.wait_for_timeout(8000)
    try:  # cuộn tới khung Thời gian thực cho dễ nhìn
        find(page, "realtime", timeout=6000).scroll_into_view_if_needed()
        page.wait_for_timeout(2500)
    except StepError:
        print("⚠️ Không thấy khung 'Thời gian thực' – tool sẽ đọc toàn trang.", flush=True)
    print("Đang đọc danh sách video đang có view...", flush=True)
    labels = [v.strip("^$") for v in __import__("labels").LABELS[__import__("labels")._lang]["realtime"]]
    res = page.evaluate(REALTIME_JS, labels)
    best = {}
    for r in res["rows"]:
        best[r["id"]] = max(best.get(r["id"], 0), r["views"])
    print(f"Đọc được {len(best)} video trong {'khung Thời gian thực' if res['scope'] == 'realtime' else 'trang'}.",
          flush=True)
    return [(f"https://www.youtube.com/watch?v={k}", v)
            for k, v in sorted(best.items(), key=lambda x: -x[1]) if v >= min_views]


# ===================== Video nhiều view nhất 48 giờ qua (Hiệu suất theo thời gian thực) =====================

RT48_JS = r"""() => {
  // Bảng "Hiệu suất theo thời gian thực": đọc cột '48 giờ qua' và '60 phút trước' theo VỊ TRÍ cột trên màn hình
  // (không phụ thuộc cấu trúc trang). Dòng không có ảnh/link video thật (vd dòng '…' không tên) -> bỏ.
  const vis = e => { const r = e.getBoundingClientRect(); return r.width > 0 && r.height > 0; };
  const T = e => ((e && (e.innerText || e.textContent)) || '').replace(/\s+/g, ' ').trim();
  const leaves = [...document.querySelectorAll('body *')].filter(e => e.childElementCount === 0 && vis(e));
  const head = rx => leaves.find(e => rx.test(T(e)));
  const h48 = head(/^(48 giờ qua|48 giờ trước|last 48 hours|48 hours)$/i);
  const h60 = head(/^(60 phút trước|60 phút qua|last 60 minutes|60 minutes)$/i);
  if (!h48) return {rows: [], why: 'không thấy cột 48 giờ qua'};
  const col = (h, other) => {   // khung cột: leo lên tới khi đủ rộng nhưng chưa chứa tiêu đề cột khác
    let c = h, best = h.getBoundingClientRect();
    for (let i = 0; i < 6 && c.parentElement; i++) {
      c = c.parentElement;
      if ((other && c.contains(other)) || /Nội dung|Content|Ngày xuất bản|Published/i.test(T(c).replace(T(h), ''))) break;
      const r = c.getBoundingClientRect();
      if (r.width > best.width) best = r;
      if (r.width >= 160) break;
    }
    return [best.left - 4, best.right + 4];
  };
  const c48 = col(h48, h60), c60 = h60 ? col(h60, h48) : null;
  const headY = h48.getBoundingClientRect().bottom;
  const nums = leaves.map(e => ({e, t: T(e), r: e.getBoundingClientRect()}))
                     .filter(o => /^\d[\d.,]*\s*(N|K|Tr|M)?$/i.test(o.t) && o.r.top > headY);
  const val = t => { const m = t.match(/^([\d.,]+)\s*(N|K|Tr|M)?$/i); if (!m) return null;
    if (m[2]) return Math.round(parseFloat(m[1].replace(',', '.')) * ({n: 1e3, k: 1e3, tr: 1e6, m: 1e6})[m[2].toLowerCase()]);
    return parseInt(m[1].replace(/[.,]/g, ''), 10); };
  const seen = new Set(), rows = [];
  document.querySelectorAll('img[src*="/vi/"], img[src*="/vi_webp/"], a[href*="/video/"]').forEach(el => {
    const m = (el.getAttribute('src') || el.getAttribute('href') || '')
              .match(/\/vi(?:_webp)?\/([\w-]{11})\/|\/video\/([\w-]{11})/);
    if (!m || !vis(el)) return;
    const id = m[1] || m[2];
    const r = el.getBoundingClientRect();
    if (seen.has(id) || r.top <= headY) return;
    const cy = r.top + r.height / 2;
    const inRow = o => { const y = o.r.top + o.r.height / 2; return Math.abs(y - cy) <= Math.max(18, r.height / 2 + 6); };
    const inCol = (o, c) => { const x = o.r.left + o.r.width / 2; return c && x >= c[0] && x <= c[1]; };
    const v48 = nums.find(o => inRow(o) && inCol(o, c48));
    if (!v48) return;
    const v60 = nums.find(o => inRow(o) && inCol(o, c60));
    // tên video: chữ dài nhất trên cùng dòng, bên trái cột số
    const title = leaves.filter(e => { const rr = e.getBoundingClientRect(); const y = rr.top + rr.height / 2;
                    return Math.abs(y - cy) <= 20 && rr.right < c48[0] && T(e).length > 6 && !/^\d/.test(T(e)); })
                  .map(T).sort((a, b) => b.length - a.length)[0] || '';
    seen.add(id);
    rows.push({id, v48: val(v48.t), v60: v60 ? val(v60.t) : null, title});
  });
  return {rows, why: ''}; }"""


def realtime_48h(page, strong_id, log=print):
    """Video của kênh xếp theo lượt xem 48 GIỜ QUA (Studio → Số liệu phân tích → Thời gian thực → Xem thêm).
    Trả về [(mã video, view 48 giờ, view 60 phút, tên)] – nhiều view nhất trước. Không đọc được -> []."""
    page.goto(f"{STUDIO}/channel/{strong_id}/analytics/tab-overview/period-default", wait_until="domcontentloaded")
    page.wait_for_timeout(7000)
    labels = [v.strip("^$") for v in __import__("labels").LABELS[__import__("labels")._lang]["realtime"]]
    # mở báo cáo đầy đủ: nút 'Xem thêm' trong khung Thời gian thực
    opened = page.evaluate(r"""(labels) => {
      const T = e => ((e && (e.innerText || e.textContent)) || '').replace(/\s+/g, ' ').trim();
      const heads = [...document.querySelectorAll('*')].filter(e => e.childElementCount === 0 &&
                    labels.some(l => T(e).startsWith(l)));
      for (const h of heads) {
        let c = h;
        for (let i = 0; i < 10 && c; i++) {
          c = c.parentElement;
          if (!c) break;
          const b = [...c.querySelectorAll('a, button, ytcp-button, [role=button]')]
                    .find(x => /^(Xem thêm|See more|Xem thêm chi tiết)$/i.test(T(x)));
          if (b) { b.setAttribute('data-keo-rtmore', '1'); return true; }
        }
      }
      return false; }""", labels)
    rows = []
    if opened:
        try:
            b = page.locator("[data-keo-rtmore='1']").first
            inner = b.locator("button")
            (inner.first if inner.count() else b).click(timeout=8000)
        except Exception:
            opened = False
        for _ in range(24):
            page.wait_for_timeout(1000)
            res = page.evaluate(RT48_JS)
            if res["rows"]:
                rows = res["rows"]
                break
    try:   # lưu trang để đối chiếu khi cần (đi kèm gói chẩn đoán)
        import datetime as _dt
        os.makedirs(os.path.join("logs", "screenshots"), exist_ok=True)
        with open(os.path.join("logs", "screenshots", f"{_dt.datetime.now():%Y%m%d_%H%M%S}_thoi_gian_thuc.html"),
                  "w", encoding="utf-8") as f:
            f.write(page.content()[:3_000_000])
    except Exception:
        pass
    if rows:
        out = [(r["id"], r["v48"] or 0, r["v60"], r["title"]) for r in rows if r.get("v48") is not None]
        out.sort(key=lambda x: -x[1])
        log(f"   Đọc báo cáo 'Hiệu suất theo thời gian thực': {len(out)} video (xếp theo lượt xem 48 giờ qua).")
        return out
    # dự phòng: danh sách video trong khung Thời gian thực ở trang Tổng quan (cũng là lượt xem 48 giờ)
    if opened:
        page.go_back(wait_until="domcontentloaded")
        page.wait_for_timeout(5000)
    res = page.evaluate(REALTIME_JS, labels)
    best = {}
    for r in res["rows"]:
        best[r["id"]] = max(best.get(r["id"], 0), r["views"])
    log(f"   Đọc khung 'Thời gian thực' ở trang Tổng quan: {len(best)} video.")
    return [(k, v, None, "") for k, v in sorted(best.items(), key=lambda x: -x[1])]
