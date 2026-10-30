"""
Màn hình kết thúc & Thẻ – viết theo ĐÚNG bản ghi thao tác làm tay của người dùng
(chan_doan_20261003_2342.zip). Mọi mã nhận diện bên dưới lấy từ giao diện thật.

Hộp chọn video (dùng chung cho màn hình kết thúc và thẻ):
  ytcp-video-pick-dialog
    input#search-yours      "Tìm kiếm video của bạn"
    input#search-any        "Tìm kiếm video của các kênh khác"
    ytcp-entity-card[role=option][aria-label="<tên video>"]
        div.thumbnail       ảnh nền chứa /vi/<mã video>/   <- bấm vào đây để chọn
"""
import re

import human  # noqa: F401  (click/fill/hover kiểu người thật)
from studio import (NeedsCheck, StepError, _fmt, already_ok, _playhead_value, _set_card_time, _set_playhead,
                    _tc_to_sec, _editor_open_quick, card_times, open_editor_panel, video_id)

PICKER = "ytcp-video-pick-dialog"
PICKER_DIALOG = "ytcp-video-pick-dialog tp-yt-paper-dialog"
PICK_CARD = "ytcp-video-pick-dialog ytcp-entity-card[role=option]"
SAVE_BTN = "ytve-modal-host ytcp-button#save-button"

# Màn hình kết thúc
ES_ITEM = "ytve-endscreen-editor-preview-overlay-item"
ES_DELETE = "ytve-endscreen-editor-options-panel ytcp-icon-button#delete"
ES_TEMPLATE_CARD = "ytve-endscreen-template-picker div.card[role=gridcell]"
ES_TEMPLATE_2V = "2v"   # mẫu tên ĐÚNG "2 video" / "2 videos" (không phải "2 videos, 1 subscribe")
ES_TEMPLATE_1V = "1v"   # mẫu "1 video, 1 đăng ký" / "1 video, 1 subscribe"
ES_TEMPLATE_1V1P = "1v1p"  # mẫu "1 video, 1 danh sách phát" / "1 video, 1 playlist"
TEMPLATE_RE = {"2v": re.compile(r"^\s*2\s+videos?\s*$", re.I),
               "1v": re.compile(r"^\s*1\s+video\s*,\s*1\s+(đăng ký|subscribe)\s*$", re.I),
               "1v1p": re.compile(r"^\s*1\s+video\s*,\s*1\s+(danh sách phát|playlist)\s*$", re.I)}


ES_CHOOSE_VIDEO = "tp-yt-paper-radio-button#choose-video"

# Thẻ
CARD_MARKER = "ytve-point-marker"
CARD_DEFAULT_ADD_VIDEO = "ytve-info-cards-editor-default-options ytcp-icon-button.add-card-icon-button"
CARD_ADD_BTN = "ytcp-button#add-card-button"
CARD_MENU_ITEM = "ytcp-text-menu tp-yt-paper-item"
CARD_DELETE = "ytve-info-cards-editor-options-panel ytcp-icon-button.delete"   # aria-label "Xóa thẻ"
CONFIRM_BTN = "ytcp-confirmation-dialog #confirm-button, tp-yt-paper-dialog #confirm-button"
PLAYHEAD = "ytve-playhead#playhead #touch-area"
# ô thời gian (mã thật từ bản ghi):
PLAYHEAD_TIME = "ytve-toolbar ytcp-media-timestamp-input input"                 # ô của THANH TRƯỢT
CARD_TIME = "ytcp-media-timestamp-input.teaser-start-time-input input"           # ô RIÊNG của từng thẻ
RULER = "ytve-timeline-markers"


SHAPE_JS = r"""(card) => {
  // đếm hình trong ô mẫu: hình tròn (ô Đăng ký) và hình chữ nhật (ô video)
  const cr = card.getBoundingClientRect();
  let circles = 0, rects = 0;
  card.querySelectorAll('*').forEach(e => {
    const r = e.getBoundingClientRect(), st = getComputedStyle(e);
    if (r.width < cr.width * 0.12 || r.height < 12 || r.width > cr.width * 0.95) return;
    const bg = st.backgroundColor;
    if (!bg || bg === 'transparent' || bg === 'rgba(0, 0, 0, 0)') return;
    const round = parseFloat(st.borderTopLeftRadius) >= Math.min(r.width, r.height) / 2 - 1;
    if (round) circles++; else rects++;
  });
  return [rects, circles];
}"""


def _template_label(c):
    label = (c.get_attribute("aria-label") or "").strip()
    if label:
        return label
    for loc in (c, c.locator("xpath=..")):   # chữ chú thích nằm trong ô hoặc ngay dưới ô
        try:
            lines = [x.strip() for x in (loc.inner_text() or "").splitlines() if x.strip()]
            if lines:
                return lines[-1]
        except Exception:
            pass
    return ""


def _templates(page, kind):
    """Các ô mẫu màn hình kết thúc đúng loại `kind`. Thử lần lượt: tên (aria-label) đúng chính xác,
    chữ chú thích dưới ô, rồi HÌNH DẠNG mẫu (2 video = 2 hình chữ nhật, không có hình tròn)."""
    cards = _visible(page, ES_TEMPLATE_CARD) or _visible(page, "ytve-endscreen-template-picker [role=gridcell]")
    labels = [_template_label(c) for c in cards]
    out = [c for c, lb in zip(cards, labels) if TEMPLATE_RE[kind].match(lb)]
    if out:
        return out
    if kind == "2v":
        out = [c for c, lb in zip(cards, labels) if re.match(r"^\s*2\s+videos?\b", lb, re.I) and "," not in lb]
        if out:
            return out
        for c in cards:
            try:
                rects, circles = c.evaluate(SHAPE_JS)
            except Exception:
                continue
            if rects == 2 and circles == 0:
                out.append(c)
    elif kind == "1v":
        out = [c for c, lb in zip(cards, labels) if re.match(r"^\s*1\s+video\s*,", lb, re.I)
               and not re.search(r"danh sách phát|playlist", lb, re.I)]
    return out


# Danh sách video VỪA được gắn ở bước gần nhất (main.py đọc để ghi nhật ký đối soát):
# [{"slot": "Thẻ 2", "time": "5:00", "id": "...", "title": "...", "owner": "weak"|"strong", "saved": True}]
LAST = None


def say(msg):
    print(f"      · {msg}", flush=True)


def _visible(page, sel):
    loc = page.locator(sel)
    return [loc.nth(i) for i in range(loc.count()) if loc.nth(i).is_visible()]


def _first_visible(page, sel, what):
    """Phần tử ĐANG HIỂN THỊ đầu tiên. YouTube giữ lại bản cũ đã ẩn (hộp chọn, nút Lưu...)
    nên không được lấy phần tử đầu tiên trong trang."""
    v = _visible(page, sel)
    if not v:
        raise StepError(f"Không thấy {what} đang hiển thị.")
    return v[0]


def _hover_click(page, outer, inner_sel=None, tries=3):
    """Rê chuột lên `outer` rồi bấm (lớp phủ `inner_sel` chỉ hiện khi rê chuột lên).
    Bị che / đang chạy hiệu ứng -> chờ rồi thử lại; lần cuối bấm thẳng vào giữa phần tử bằng chuột."""
    last = None
    for attempt in range(tries):
        try:
            outer.wait_for(state="visible", timeout=8000)
            try:
                outer.scroll_into_view_if_needed(timeout=3000)
            except Exception:
                pass
            outer.hover(timeout=5000)
            page.wait_for_timeout(400)
            if inner_sel:
                inner = outer.locator(inner_sel)
                try:
                    if inner.count() and inner.first.is_visible():
                        inner.first.click(timeout=4000)
                        return
                except Exception:
                    pass
            outer.click(timeout=6000)
            return
        except Exception as e:
            last = e
            say(f"   chưa bấm được (lần {attempt + 1}) – chờ rồi thử lại")
            page.wait_for_timeout(1500)
    # dự phòng: bấm chuột thẳng vào điểm giữa phần tử (không chờ kiểm tra "có bị che không")
    bb = human.bbox(outer)
    if bb and bb["width"] > 2 and bb["height"] > 2:
        human.mouse_click(page, bb["x"] + bb["width"] / 2, bb["y"] + bb["height"] / 2)
        return
    raise StepError(f"Không bấm được vào phần tử sau {tries} lần thử: {str(last).splitlines()[0][:120]}")


def _wait(page, cond, timeout_ms, step=300):
    waited = 0
    while waited < timeout_ms:
        try:
            if cond():
                return True
        except Exception:
            pass
        page.wait_for_timeout(step)
        waited += step
    return False


# ============================================================ hộp chọn video
def _card_id(card):
    """Mã video của 1 ô trong hộp chọn – đọc MỌI ảnh thu nhỏ trong ô (ảnh có thể chưa tải xong)."""
    try:
        s = card.evaluate("""c => [...c.querySelectorAll('div.thumbnail, [style*="/vi/"], img')]
            .map(e => (e.getAttribute('style') || '') + ' ' + (e.getAttribute('src') || '')).join(' ')""")
    except Exception:
        s = ""
    m = re.search(r"/vi(?:_webp)?/([\w-]{11})/", s or "")
    return m.group(1) if m else ""


def _card_title(card):
    t = card.get_attribute("aria-label") or ""
    return re.sub(r",\s*(Chưa chọn|Đã chọn|Not selected|Selected)\s*$", "", t).strip()


def _norm_txt(t):
    return re.sub(r"\s+", " ", str(t or "").replace("\u00a0", " ")).strip().lower()


def _verify_chosen(page, vid, title):
    """Sau khi hộp chọn đóng: trình chỉnh sửa phải hiện đúng video vừa chọn
    (ảnh có mã video, hoặc dòng 'Video: <tên video>' – so không phân biệt hoa/thường, khoảng trắng)."""
    key = _norm_txt(title)[:18]

    def ok():
        if vid and page.locator(f"ytve-modal-host [style*='{vid}'], ytve-modal-host img[src*='{vid}']").count():
            return True
        if not key:
            return False
        return any(key in _norm_txt(h.inner_text()) for h in _visible(page, "ytve-modal-host"))
    if not _wait(page, ok, 8000):
        raise StepError(f"Đã bấm video '{title[:40]}' ({vid or '?'}) nhưng trình chỉnh sửa chưa hiện video đó.")


def pick_video(page, url=None, index=None, exclude=None, verify=True):
    """Chọn 1 video trong hộp 'Chọn một video cụ thể' và kiểm tra YouTube đã nhận đúng video.
    - url:   video kênh khác -> gõ link vào ô 'Tìm kiếm video của các kênh khác', bấm đúng ảnh có mã video.
    - index: video thứ `index` (0 = mới nhất) trong danh sách video của kênh mình, bỏ qua video `exclude`.
    Trả về (mã video, tên video)."""
    search_any = f"{PICKER} input#search-any"
    if not _wait(page, lambda: len(_visible(page, search_any)) > 0, 20000):
        raise StepError("Hộp 'Chọn một video cụ thể' không mở ra.")
    page.wait_for_timeout(800)

    if index is not None:
        if not _wait(page, lambda: len(_visible(page, PICK_CARD)) > 0, 20000):
            raise StepError("Hộp chọn không hiện danh sách video của kênh mạnh.")
        cards = [c for c in _visible(page, PICK_CARD) if _card_id(c) and _card_id(c) != exclude]
        if index >= len(cards):
            raise StepError(f"Danh sách chỉ có {len(cards)} video, không có video thứ {index + 1}.")
        target = cards[index]
    else:
        vid = video_id(url)
        card_sel = f"{PICK_CARD}:has(div.thumbnail[style*='{vid}'])"
        if not _visible(page, card_sel):
            box = _first_visible(page, search_any, "ô 'Tìm kiếm video của các kênh khác'")
            found = False
            for query in (f"https://www.youtube.com/watch?v={vid}", f"https://youtu.be/{vid}", vid):
                say(f"dán '{query}' vào ô 'Tìm kiếm video của các kênh khác'")
                if not human.paste(box, query):  # dán cả link 1 lần, kiểm tra ô đúng link
                    say("   ô tìm kiếm không nhận nội dung, thử lại")
                    continue
                box.press("Enter")
                if _wait(page, lambda: len(_visible(page, card_sel)) > 0, 15000):
                    found = True
                    break
            if not found:
                raise StepError(f"Đã dán link vào ô 'Tìm kiếm video của các kênh khác' nhưng không thấy video mã {vid}.")
            page.wait_for_timeout(500)
        target = _visible(page, card_sel)[0]

    got, title = _card_id(target), _card_title(target)
    if index is not None or not got:
        vid = got or (vid if index is None else "")
    elif got != vid:
        raise StepError(f"Ô tìm được là video {got}, không phải {vid} – không chọn.")
    say(f"bấm vào video: {title[:50]} ({vid or '?'})")
    _hover_click(page, target.locator("div.thumbnail").first)
    # bấm ảnh xong hộp chọn tự đóng = YouTube đã nhận video
    if not _wait(page, lambda: not _visible(page, PICKER_DIALOG), 10000):
        raise StepError("Đã bấm vào video nhưng hộp chọn không đóng lại.")
    page.wait_for_timeout(800)
    if verify:
        _verify_chosen(page, vid, title)
    return vid, title


# ============================================================ hộp chọn DANH SÁCH PHÁT
PL_DIALOGS = ("ytcp-playlist-pick-dialog tp-yt-paper-dialog, ytcp-playlist-pick-dialog, "
              "ytcp-entity-pick-dialog tp-yt-paper-dialog, tp-yt-paper-dialog")
PL_DIALOG_INFO_JS = r"""(d) => ({
  tag: (d.closest('[class*="dialog"], tp-yt-paper-dialog') || d).tagName.toLowerCase(),
  parent: (d.parentElement ? d.parentElement.tagName.toLowerCase() : ''),
  inputs: [...d.querySelectorAll('input')].filter(i => i.offsetParent).map(i =>
      (i.id || '') + '|' + (i.getAttribute('placeholder') || i.getAttribute('aria-label') || '')),
  options: [...d.querySelectorAll('[role=option], ytcp-entity-card')].slice(0, 4).map(o =>
      (o.getAttribute('aria-label') || o.innerText || '').trim().slice(0, 50)),
  head: (d.innerText || '').trim().split('\n').slice(0, 3).join(' / ').slice(0, 120)})"""


def _pl_dialog(page):
    """Hộp chọn danh sách phát đang mở (hộp có ô nhập, KHÔNG phải hộp chọn video)."""
    for d in _visible(page, PL_DIALOGS):
        try:
            inside_video = d.evaluate("e => !!e.closest('ytcp-video-pick-dialog')")
        except Exception:
            inside_video = False
        if not inside_video and d.locator("input").count():
            return d
    return None


def _pl_option(d, pid, title):
    key = _norm_txt(title)[:22]
    for o in [o for o in (d.locator("[role=option], ytcp-entity-card").all()) if o.is_visible()]:
        try:
            html = o.evaluate("e => e.outerHTML")
            txt = _norm_txt((o.get_attribute("aria-label") or "") + " " + (o.inner_text() or ""))
        except Exception:
            continue
        if (pid and pid in html) or (key and key in txt):
            return o
    return None


def pick_playlist(page, pl):
    """Chọn danh sách phát `pl` ({'id','url','title'}) trong hộp chọn danh sách phát vừa mở:
    tìm sẵn trong danh sách / dán link vào ô tìm kiếm -> bấm đúng ô có mã hoặc tên danh sách phát
    -> hộp đóng -> kiểm tra trình chỉnh sửa hiện đúng danh sách phát. Không chắc chắn -> báo lỗi, không đoán."""
    if not _wait(page, lambda: _pl_dialog(page) is not None, 15000):
        raise StepError("Hộp chọn danh sách phát không mở ra.")
    page.wait_for_timeout(800)
    d = _pl_dialog(page)
    pid, title = pl.get("id", ""), pl.get("title", "")
    target = _pl_option(d, pid, title)
    if target is None:
        inputs = [i for i in d.locator("input").all() if i.is_visible()]
        pref = [i for i in inputs if re.search(r"khác|other|youtube|url|link",
                                               (i.get_attribute("id") or "") + " " +
                                               (i.get_attribute("placeholder") or "") + " " +
                                               (i.get_attribute("aria-label") or ""), re.I)]
        for box in (pref or inputs)[:2]:
            for query in (pl.get("url") or "", pid, title):
                if not query:
                    continue
                say(f"dán '{query[:60]}' vào ô tìm danh sách phát")
                if not human.paste(box, query):
                    continue
                box.press("Enter")
                if _wait(page, lambda: _pl_option(d, pid, title) is not None, 12000):
                    target = _pl_option(d, pid, title)
                    break
            if target is not None:
                break
    if target is None:
        try:
            info = d.evaluate(PL_DIALOG_INFO_JS)
        except Exception:
            info = {}
        raise StepError(f"Không tìm thấy danh sách phát '{title[:40]}' ({pid}) trong hộp chọn. "
                        f"[hộp: {info.get('parent') or info.get('tag')} · ô nhập: {info.get('inputs')} · "
                        f"ô hiện có: {info.get('options')}]")
    say(f"bấm vào danh sách phát: {title[:50] or pid}")
    _hover_click(page, target)
    if not _wait(page, lambda: _pl_dialog(page) is None, 10000):
        raise StepError("Đã bấm danh sách phát nhưng hộp chọn không đóng lại.")
    page.wait_for_timeout(800)
    key = _norm_txt(title)[:18]

    def shown():
        if pid and page.locator(f"ytve-modal-host [href*='{pid}'], ytve-modal-host [style*='{pid}']").count():
            return True
        return bool(key) and any(key in _norm_txt(h.inner_text()) for h in _visible(page, "ytve-modal-host"))
    if not _wait(page, shown, 8000):
        raise StepError(f"Đã chọn danh sách phát '{title[:40]}' nhưng trình chỉnh sửa chưa hiện nó.")
    return pid, title


PL_PANEL_JS = r"""(root) => {
  // ô thành phần DANH SÁCH PHÁT đang chọn: bấm lựa chọn 'danh sách phát cụ thể' / nút 'Chọn danh sách phát'
  const re = /(danh sách phát cụ thể|specific playlist|chọn (một )?danh sách phát|choose (a )?playlist|select playlist)/i;
  const els = [...root.querySelectorAll('tp-yt-paper-radio-button, ytcp-button, button, ytcp-dropdown-trigger, [role=button], [role=radio]')]
    .filter(e => e.offsetParent && re.test((e.innerText || e.getAttribute('aria-label') || '').trim()));
  if (!els.length) return false;
  els[0].setAttribute('data-keo-pl', '1');
  return (els[0].innerText || els[0].getAttribute('aria-label') || '').trim().slice(0, 60);
}"""


def _open_pl_picker_from_panel(page):
    root = "ytve-endscreen-editor-options-panel"
    if not page.locator(root).count():
        root = "ytve-modal-host"
    try:
        hit = page.locator(root).first.evaluate(PL_PANEL_JS)
    except Exception:
        hit = False
    if not hit:
        return False
    say(f"bấm '{hit}'")
    _hover_click(page, page.locator("[data-keo-pl='1']").first)
    return _wait(page, lambda: _pl_dialog(page) is not None, 8000)


def _add_playlist_card(page):
    """Thẻ mới loại DANH SÁCH PHÁT: dấu + có nhãn 'danh sách phát/playlist' (khi chưa có thẻ) hoặc
    '+ Thẻ' -> 'Danh sách phát'. Chỉ trả về khi hộp chọn danh sách phát ĐÃ mở."""
    pl_re = re.compile(r"(danh sách phát|playlist)\s*$", re.I)
    for attempt in range(2):
        plus = [b for b in _visible(page, CARD_DEFAULT_ADD_VIDEO.replace(".add-card-icon-button", "")
                                    + ".add-card-icon-button")
                if pl_re.search((b.get_attribute("aria-label") or "").strip())]
        if plus:
            plus[0].click()
        else:
            btn = _visible(page, CARD_ADD_BTN)
            if not btn:
                raise StepError("Không thấy nút '+ Thẻ'.")
            btn[0].click()

            def menu_pl():
                items = _visible(page, CARD_MENU) or _visible(page, CARD_MENU_ITEM)
                return [it for it in items if re.fullmatch(r"\s*(danh sách phát|playlist)\s*", it.inner_text() or "", re.I)
                        or it.get_attribute("test-id") in ("PLAYLIST",)]
            if not _wait(page, lambda: len(menu_pl()) > 0, 5000):
                if attempt:
                    raise StepError("Đã bấm '+ Thẻ' nhưng menu 'Danh sách phát' không hiện.")
                page.keyboard.press("Escape")
                continue
            menu_pl()[0].click()
        if _wait(page, lambda: _pl_dialog(page) is not None, 10000):
            return
        say("   hộp chọn danh sách phát chưa mở – thử lại")
    raise StepError("Đã bấm thêm thẻ Danh sách phát nhưng hộp chọn danh sách phát không mở ra.")


def _close_without_saving(page):
    """Thoát trình chỉnh sửa mà không thay đổi gì."""
    from studio import close_editor
    try:
        close_editor(page)
    except Exception:
        pass


def _save(page):
    """Bấm Lưu. Nếu nút Lưu bị khóa vì không có gì thay đổi (video chọn trùng với video cũ),
    thoát ra không lưu và trả về False – video đã đúng sẵn."""
    btn = _first_visible(page, SAVE_BTN, "nút Lưu")
    page.wait_for_timeout(800)
    disabled = (btn.get_attribute("aria-disabled") == "true" or btn.get_attribute("disabled") is not None)
    if disabled:
        say("nút Lưu bị khóa: video đã chọn trùng với video cũ – không có gì thay đổi")
        _close_without_saving(page)
        return False
    say("bấm Lưu")
    btn.click()
    if not _wait(page, lambda: not _visible(page, SAVE_BTN), 15000):
        raise StepError("Bấm Lưu nhưng trình chỉnh sửa không đóng – YouTube có thể đang báo lỗi (xem ảnh chụp).")
    page.wait_for_timeout(1500)
    return True


# ============================================================ màn hình kết thúc
def _es_items(page):
    """Ô thành phần THẬT đang có trong khung xem trước = ô có lớp 'visible' (như bản ghi thật).
    YouTube giữ lại các bản sao / thành phần đã xóa ở dạng ẩn (vẫn có lớp 'active', 'resizeable'
    nhưng KHÔNG có 'visible') – không được tính, bấm vào đó là bấm vào chỗ trống."""
    return [it for it in _visible(page, ES_ITEM) if "visible" in (it.get_attribute("class") or "").split()]


def _cls(loc):
    try:
        return (loc.get_attribute("class") or "").split()
    except Exception:
        return []


def _es_clear(page):
    for _ in range(8):
        items = _es_items(page)
        if not items:
            return
        say(f"xóa thành phần cũ (còn {len(items)})")
        _hover_click(page, items[0], "div.edit-overlay")  # chọn thành phần
        if not _wait(page, lambda: len(_visible(page, ES_DELETE)) > 0, 5000):
            raise StepError("Không thấy nút 'Xóa thành phần'.")
        _hover_click(page, _visible(page, ES_DELETE)[0])
        _confirm_if_asked(page)
        n = len(items)
        _wait(page, lambda: len(_es_items(page)) < n, 5000)
    if _es_items(page):
        raise StepError("Không xóa hết được thành phần cũ của màn hình kết thúc.")


def _weak_ids(weak):
    """Mã các video của kênh cần kéo (bỏ trùng, giữ thứ tự). Nhận link watch / youtu.be / shorts / mã 11 ký tự."""
    out = []
    for v in weak.get("videos") or []:
        v = str(v or "").strip()
        if not v:
            continue
        m = re.search(r"(?:v=|youtu\.be/|/shorts/|/video/|/live/)([\w-]{11})", v) or re.fullmatch(r"([\w-]{11})", v)
        if m:
            out.append(m.group(1))
        else:
            say(f"⚠️ bỏ qua link không đọc được mã video: {v}")
    return list(dict.fromkeys(out))


def _open_picker_from_panel(page):
    """Ô đang chọn đã là 'video cụ thể' (bấm nút radio không mở hộp chọn) -> bấm dòng 'Video: ...'
    / nút 'Chọn video' trong bảng tùy chọn để mở lại hộp chọn."""
    for sel in ("ytve-endscreen-editor-options-panel #video-pick-button",
                "ytve-endscreen-editor-options-panel [aria-label='Chọn video']",
                "ytve-endscreen-editor-options-panel ytcp-dropdown-trigger"):
        v = _visible(page, sel)
        if v:
            v[0].click()
            return True
    return False


def _tick_choose_video(page, slot):
    """Tích 'Chọn một video cụ thể' cho ô đang chọn và chờ hộp chọn video mở ra."""
    search_any = f"{PICKER} input#search-any"
    if not _wait(page, lambda: len(_visible(page, ES_CHOOSE_VIDEO)) > 0, 8000):
        raise StepError(f"Video {slot}: không thấy lựa chọn 'Chọn một video cụ thể'.")
    radio = _visible(page, ES_CHOOSE_VIDEO)[0]
    say(f"ô video {slot}: tích 'Chọn một video cụ thể'")
    _hover_click(page, radio)
    if _wait(page, lambda: len(_visible(page, search_any)) > 0, 6000):
        return
    if _open_picker_from_panel(page) and _wait(page, lambda: len(_visible(page, search_any)) > 0, 8000):
        return
    _hover_click(page, radio)  # thử bấm lại 1 lần
    if not _wait(page, lambda: len(_visible(page, search_any)) > 0, 8000):
        raise StepError(f"Video {slot}: đã tích 'Chọn một video cụ thể' nhưng hộp chọn video không mở ra.")


def _slot_items(page):
    """Các ô thành phần thật, xếp từ TRÁI sang PHẢI (ô 1 = bên trái, ô 2 = bên phải)."""
    items = _es_items(page)
    boxes = []
    for it in items:
        bb = human.bbox(it) or {"x": 0, "y": 0}
        boxes.append((bb["x"], bb["y"], it))
    return [it for _, _, it in sorted(boxes, key=lambda t: (round(t[0] / 40), t[1]))]


def _select_es_slot(page, slot, n):
    """Chọn ô video thứ `slot` (theo vị trí trái -> phải) và chờ ô đó hiện lựa chọn 'Chọn một video cụ thể'.
    Ô không có lựa chọn video (vd ô Đăng ký) -> thử ô tiếp theo bên phải."""
    items = _slot_items(page)
    if len(items) < n:
        raise StepError(f"Video {slot}: khung xem trước chỉ có {len(items)} ô, cần {n} ô.")
    order = items[slot - 1:] + items[:slot - 1]
    for target in order:
        if "selected" not in _cls(target):
            say(f"bấm vào ô video {slot} trong khung xem trước")
            _hover_click(page, target, "div.edit-overlay")
            if not _wait(page, lambda: "selected" in _cls(target), 6000):
                continue
        if _wait(page, lambda: len(_visible(page, ES_CHOOSE_VIDEO)) > 0, 8000):
            return target
        say("   ô này không phải ô video (vd ô Đăng ký) – thử ô khác")
    raise StepError(f"Video {slot}: không tìm thấy ô video nào có lựa chọn 'Chọn một video cụ thể'.")


def _ids_in_preview(page):
    """Mã các video đang hiện (ảnh thu nhỏ) trong khung xem trước của màn hình kết thúc."""
    try:
        return page.evaluate("""() => { const out = new Set();
          document.querySelectorAll('ytve-endscreen-editor-preview-overlay-item.visible, ytve-endscreen-editor-preview-overlay-item.visible *')
            .forEach(e => { const s = (e.getAttribute('style') || '') + ' ' + (e.getAttribute('src') || '');
              const m = s.match(/\\/vi(?:_webp)?\\/([\\w-]{11})/); if (m) out.add(m[1]); });
          return [...out]; }""")
    except Exception:
        return []


def end_screen(page, vid, weak, clear_existing=False, source="weak"):
    """Màn hình kết thúc 1–2 video – y như cách làm tay:
    (xóa cũ nếu chọn Thay thế) -> mẫu '2 video' -> mỗi ô: bấm ô -> 'Chọn một video cụ thể'
    -> dán link -> bấm ảnh video -> kiểm tra cả 2 ô đã có video -> Lưu."""
    say("mở trình chỉnh sửa Màn hình kết thúc")
    open_editor_panel(page, vid, "end_screen")
    page.wait_for_timeout(1500)
    if _es_items(page):
        say(f"đang có {len(_es_items(page))} thành phần cũ")
        ok = end_screen_matches(page, vid, weak, source, exact=clear_existing)
        if ok:   # đã có đúng video bạn điền -> không xóa, không làm lại
            _close_without_saving(page)
            return already_ok(ok)
        if not clear_existing:
            _close_without_saving(page)
            return "đã có sẵn – giữ nguyên, không đụng vào"
        _es_clear(page)

    want = max(1, min(2, int(weak.get("_es_count", 2) or 2)))
    links = _weak_ids(weak)
    warn = []
    pl = weak.get("_pl") if source != "own_newest" and weak.get("_es_pl") else None
    if pl:
        want = 1          # mẫu '1 video, 1 danh sách phát'
        if not _wait(page, lambda: len(_templates(page, ES_TEMPLATE_1V1P)) > 0, 10000):
            seen = [(_template_label(c) or "?") for c in _visible(page, ES_TEMPLATE_CARD)]
            warn.append("không thấy mẫu '1 video, 1 danh sách phát' (các mẫu đang có: " +
                        (", ".join(seen) or "không có") + ") – chỉ gắn video")
            say("⚠️ " + warn[-1])
            pl = None
            want = max(1, min(2, int(weak.get("_es_count", 2) or 2)))
    if source == "own_newest":
        n = want
    else:
        n = min(want, len(links))
        if n == 0:
            raise StepError("Kênh cần kéo chưa có link video nào để gắn vào màn hình kết thúc.")
        if n < want:
            warn.append(f"Muốn gắn {want} video nhưng kênh cần kéo chỉ có {len(links)} link video khác nhau "
                        f"– chỉ gắn được {n}. Hãy thêm link ở trang Thông tin kênh.")
            say("⚠️ " + warn[-1])
    tpl, tname = (ES_TEMPLATE_1V1P, "1 video, 1 danh sách phát") if pl else \
        (ES_TEMPLATE_2V, "2 video") if n == 2 else (ES_TEMPLATE_1V, "1 video, 1 đăng ký")
    say(f"chọn mẫu '{tname}'")
    if not _wait(page, lambda: len(_templates(page, tpl)) > 0, 10000):
        seen = [(_template_label(c) or "?") for c in _visible(page, ES_TEMPLATE_CARD)]
        raise StepError(f"Không thấy mẫu '{tname}'. Các mẫu tool nhìn thấy: {', '.join(seen) or '(không có ô mẫu nào)'}")
    _hover_click(page, _templates(page, tpl)[0], ".preview-overlay")
    if not _wait(page, lambda: len(_es_items(page)) >= (2 if n == 2 or pl else 1), 15000):
        raise StepError(f"Đã bấm mẫu '{tname}' nhưng không thấy ô video trong khung xem trước.")
    page.wait_for_timeout(1000)  # chờ hiệu ứng hiện ô xong

    chosen = []
    for i in range(n):
        slot = i + 1
        if i == 0 and not _wait(page, lambda: len(_visible(page, ES_CHOOSE_VIDEO)) > 0, 8000):
            _select_es_slot(page, slot, n)    # chờ 8 giây vẫn không có lựa chọn video -> chọn ô 1 (bên trái)
        elif i > 0:
            _select_es_slot(page, slot, n)    # ô 2 = ô bên phải
        _tick_choose_video(page, slot)
        try:
            if source == "own_newest":
                chosen.append(pick_video(page, index=i, exclude=vid))
            else:
                chosen.append(pick_video(page, url=f"https://www.youtube.com/watch?v={links[i]}"))
        except StepError as e:
            raise StepError(f"Video {slot}: {e}")
        say(f"   ô video {slot} đã có video: {chosen[-1][1][:45]} ({chosen[-1][0]})")
    if len(chosen) == 2 and chosen[0][0] == chosen[1][0]:
        raise StepError("2 ô màn hình kết thúc đang cùng 1 video – không lưu.")
    pl_got = None
    if pl:   # ô còn lại = ô DANH SÁCH PHÁT
        vids = {v for v, _t in chosen}
        others = [it for it in _slot_items(page)
                  if not any(v in (it.evaluate("e => e.outerHTML") or "") for v in vids)]
        if not others:
            raise StepError("Không thấy ô danh sách phát trong khung xem trước.")
        say("bấm vào ô danh sách phát trong khung xem trước")
        _hover_click(page, others[0], "div.edit-overlay")
        page.wait_for_timeout(1200)
        if _pl_dialog(page) is None and not _open_pl_picker_from_panel(page):
            raise StepError("Đã bấm ô danh sách phát nhưng không thấy nút chọn danh sách phát.")
        pl_got = pick_playlist(page, pl)
        say(f"   ô danh sách phát đã có: {pl_got[1][:45]} ({pl_got[0]})")
    # kiểm tra lần cuối: ảnh của các video vừa chọn phải hiện trong khung xem trước
    shown = _ids_in_preview(page)
    if shown:
        miss = [v for v, _t in chosen if v not in shown]
        if miss:
            raise StepError(f"Khung xem trước chưa hiện video {', '.join(miss)} – không lưu.")
    saved = _save(page)
    global LAST
    LAST = [dict(slot=f"Màn hình kết thúc – ô {i + 1}", time="", id=v, title=t,
                 owner="strong" if source == "own_newest" or weak.get("_owner") == "strong" else "weak", saved=bool(saved))
            for i, (v, t) in enumerate(chosen)]
    if pl_got:
        LAST.append(dict(slot="Màn hình kết thúc – danh sách phát", time="", id=pl_got[0], title=pl_got[1],
                         url=f"https://www.youtube.com/playlist?list={pl_got[0]}", owner="weak", saved=bool(saved)))
        chosen = chosen + [(pl_got[0], "Danh sách phát: " + pl_got[1])]
    note = " | ".join(f"{t[:35]} ({v})" for v, t in chosen)
    note = note if saved else f"đã đúng sẵn, không cần lưu: {note}"
    if warn:
        raise NeedsCheck(note + " — " + " ".join(warn))
    return note


def clear_end_screen(page, vid, expected=None):
    """Gỡ màn hình kết thúc tool đã gắn. `expected`: số ô video tool đã gắn (theo nhật ký).
    Số ô hiện có khác số tool đã gắn -> có người sửa thêm -> không xóa, báo gỡ tay."""
    open_editor_panel(page, vid, "end_screen")
    page.wait_for_timeout(1500)
    n = len(_es_items(page))
    if n == 0:
        _close_without_saving(page)
        raise StepError("Video không còn màn hình kết thúc (có thể đã bị gỡ trước đó).")
    if expected and n not in (expected, expected + 1):  # +1: mẫu '1 video, 1 đăng ký' có thêm ô Đăng ký
        _close_without_saving(page)
        raise NeedsCheck(f"Màn hình kết thúc đang có {n} thành phần, tool chỉ gắn {expected} – không xóa, hãy gỡ tay.")
    say(f"gỡ {n} thành phần màn hình kết thúc")
    _es_clear(page)
    _save(page)


# ============================================================ thẻ
def _duration_from_ruler(page):
    try:
        txt = _first_visible(page, RULER, "thước thời gian").inner_text()
        tcs = re.findall(r"\d+:\d\d:\d\d(?::\d\d)?", txt)
        return max(_tc_to_sec(t) for t in tcs) if tcs else 0
    except Exception:
        return 0


def _tc(sec, like=""):
    """Viết mốc `sec` theo ĐÚNG dạng của ô (`like` = nội dung ô đang hiện):
    4 phần '0:05:00:00' (giờ:phút:giây:khung hình) hoặc 3 phần '05:00:00' (phút:giây:khung hình)."""
    h, m, s_ = sec // 3600, sec % 3600 // 60, sec % 60
    parts = [x for x in str(like or "").strip().split(":")]
    while parts and parts[-1] == "":
        parts.pop()
    if len(parts) == 3:
        return f"{h * 60 + m:02d}:{s_:02d}:00"
    if len(parts) == 2:
        return f"{h * 60 + m}:{s_:02d}"
    return f"{h}:{m:02d}:{s_:02d}:00"


def _read_tc(loc):
    try:
        return _tc_to_sec(loc.input_value())
    except Exception:
        return None


def _playhead_now(page):
    v = _visible(page, PLAYHEAD_TIME)
    return _read_tc(v[0]) if v else None


def _type_time(page, box, sec, what, tol=1):
    """Dán mốc thời gian vào ô, Enter, rồi đọc lại để xác nhận."""
    try:
        like = box.input_value()
    except Exception:
        like = ""
    if len([x for x in like.split(":") if x != ""]) < 2:  # ô trống / đang gõ dở -> lấy dạng từ chữ hiển thị
        try:
            like = box.evaluate("e => (e.closest('ytcp-media-timestamp-input') || e).querySelector('#display, #sizing')"
                                "?.textContent || ''").strip() or like
        except Exception:
            pass
    for _ in range(3):
        human.paste(box, _tc(sec, like))
        box.press("Enter")
        page.wait_for_timeout(1200)
        got = _read_tc(box)
        if got is not None and abs(got - sec) <= tol:
            return got
    raise StepError(f"Không đặt được {what} về {_fmt(sec)} (ô đang hiện {box.input_value()}).")


def seek(page, sec, duration):
    """Nhấn giữ thanh trượt và kéo tới mốc `sec`; chỉnh tinh bằng ô thời gian của THANH TRƯỢT."""
    total = duration or _duration_from_ruler(page)
    rv = _visible(page, RULER)
    ruler = human.bbox(rv[0]) if rv else None
    if total and ruler:
        px_per_sec = ruler["width"] / total
        for _ in range(3):
            cur = _playhead_now(page)
            if cur is not None and abs(cur - sec) <= 1:
                break
            ph = _visible(page, PLAYHEAD)
            hb = human.bbox(ph[0]) if ph else None
            if not hb or cur is None:
                break
            x0 = hb["x"] + hb["width"] / 2
            y = hb["y"] + min(30, hb["height"] * 0.25)
            dx = (sec - cur) * px_per_sec
            human.drag(page, x0, y, x0 + dx, y)
            page.wait_for_timeout(600)
            new = _playhead_now(page)
            if new is not None and abs(new - cur) > 2 and abs(dx) > 3:
                px_per_sec = abs(dx) / abs(new - cur)  # hiệu chỉnh tỉ lệ theo kết quả thật
    cur = _playhead_now(page)
    if cur is None or abs(cur - sec) > 1:
        boxes = _visible(page, PLAYHEAD_TIME)
        if not boxes:
            raise NeedsCheck("không thấy ô thời gian của thanh trượt")
        cur = _type_time(page, boxes[0], sec, "thanh trượt")
    say(f"   thanh trượt đang ở {_fmt(cur)}")


def _confirm_if_asked(page):
    btn = _visible(page, CONFIRM_BTN)
    if btn:
        btn[0].click()
        page.wait_for_timeout(800)


def _cards_clear(page):
    """Xóa từng thẻ cũ bằng nút 'Xóa thẻ' (thùng rác) trong bảng bên trái."""
    for _ in range(12):
        marks = _visible(page, CARD_MARKER)
        if not marks:
            return
        dels = _visible(page, CARD_DELETE)
        if not dels:  # bảng chưa hiện thẻ -> bấm vào thẻ trên dòng thời gian để hiện
            marks[0].click(force=True)
            page.wait_for_timeout(800)
            dels = _visible(page, CARD_DELETE)
        if not dels:
            raise StepError("Không thấy nút 'Xóa thẻ'.")
        n = len(marks)
        say(f"xóa thẻ cũ (còn {n})")
        dels[0].click()
        _confirm_if_asked(page)
        if not _wait(page, lambda: len(_visible(page, CARD_MARKER)) < n, 5000):
            raise StepError("Đã bấm 'Xóa thẻ' nhưng thẻ cũ vẫn còn.")
    if _visible(page, CARD_MARKER):
        raise StepError("Không xóa hết được thẻ cũ.")


CARD_ROW_SELECTED = "div.info-card-row[selected]"      # dòng thẻ đang chọn = thẻ VỪA thêm (theo bản ghi thật)
CARD_MENU = "ytcp-text-menu#info-card-type-selector tp-yt-paper-item"


def _card_markers(page):
    return len(_visible(page, CARD_MARKER))


def _add_video_card(page):
    """Mở hộp chọn video cho 1 thẻ mới: dấu + dòng Video (khi chưa có thẻ) hoặc '+ Thẻ' -> 'Video'.
    Chỉ trả về khi hộp chọn video ĐÃ mở."""
    search_any = f"{PICKER} input#search-any"
    for attempt in range(2):
        # 4 dấu +: video / danh sách phát / kênh / trang web -> lấy dấu + có nhãn kết thúc bằng "video"
        default_plus = [b for b in _visible(page, CARD_DEFAULT_ADD_VIDEO)
                        if (b.get_attribute("aria-label") or "").strip().lower().endswith("video")]
        if default_plus:
            default_plus[0].click()
        else:
            btn = _visible(page, CARD_ADD_BTN)
            if not btn:
                raise StepError("Không thấy nút '+ Thẻ'.")
            btn[0].click()

            def menu_video():
                items = _visible(page, CARD_MENU) or _visible(page, CARD_MENU_ITEM)
                return [it for it in items if (it.inner_text() or "").strip().lower() == "video"
                        or it.get_attribute("test-id") in ("0", "VIDEO")]
            if not _wait(page, lambda: len(menu_video()) > 0, 5000):
                if attempt:
                    raise StepError("Đã bấm '+ Thẻ' nhưng menu 'Video' không hiện.")
                page.keyboard.press("Escape")
                continue
            menu_video()[0].click()
        if _wait(page, lambda: len(_visible(page, search_any)) > 0, 10000):
            return
        say("   hộp chọn video chưa mở – thử lại")
    raise StepError("Đã bấm thêm thẻ Video nhưng hộp chọn video không mở ra.")


def _new_card_time_box(page):
    """Ô 'Thời gian bắt đầu' của thẻ VỪA thêm: nằm trong dòng thẻ đang chọn (div.info-card-row[selected]).
    Không dùng 'ô cuối cùng' vì YouTube xếp lại / dựng lại danh sách thẻ sau mỗi lần thêm."""
    sel = f"{CARD_ROW_SELECTED} {CARD_TIME}"
    if _wait(page, lambda: len(_visible(page, sel)) > 0, 4000):
        return _visible(page, sel)[0]
    return None


def _all_card_times(page):
    return sorted(t for t in (_read_tc(b) for b in _visible(page, CARD_TIME)) if t is not None)


def cards(page, vid, weak, duration, cfg_cards, source="weak"):
    """Thẻ video ở các mốc (mặc định phút 0, 5, 10) – y như cách làm tay:
    kéo thanh trượt tới mốc -> + Thẻ -> Video -> dán link -> bấm ảnh video
    -> đặt đúng giờ cho CHÍNH thẻ vừa thêm -> ... -> kiểm tra lại toàn bộ mốc -> Lưu."""
    say("mở trình chỉnh sửa Thẻ")
    open_editor_panel(page, vid, "cards")
    page.wait_for_timeout(1500)
    warn = []
    if _visible(page, CARD_MARKER):
        ok = cards_match(page, vid, weak, duration, cfg_cards, source,
                         exact=bool(cfg_cards.get("replace_existing", False)))
        if ok:   # đã có đúng thẻ bạn điền -> không xóa, không làm lại
            _close_without_saving(page)
            return already_ok(ok)
        if not cfg_cards.get("replace_existing", False):
            _close_without_saving(page)
            return "đã có sẵn – giữ nguyên, không đụng vào"
        _cards_clear(page)

    want = max(1, min(5, int(cfg_cards.get("count", 3) or 3)))   # YouTube cho tối đa 5 thẻ
    if source == "own_newest":
        videos = [None] * want
    else:
        ids = _weak_ids(weak)
        videos = [f"https://www.youtube.com/watch?v={i}" for i in ids][:want]
        if not videos:
            raise StepError("Kênh cần kéo chưa có link video nào để gắn vào thẻ.")
        if len(videos) < want:
            warn.append(f"Muốn gắn {want} thẻ nhưng kênh cần kéo chỉ có {len(videos)} link video khác nhau "
                        f"– chỉ gắn được {len(videos)} thẻ. Hãy thêm link ở trang Thông tin kênh")
            say("⚠️ " + warn[-1])
    pl = weak.get("_pl") if source != "own_newest" and cfg_cards.get("playlist") else None
    if pl and len(videos) >= 5:
        videos = videos[:4]          # YouTube cho tối đa 5 thẻ: 4 video + 1 danh sách phát
    chosen, actual = [], []
    total = duration or _duration_from_ruler(page)
    times = card_times(total, len(videos) + (1 if pl else 0), cfg_cards.get("start_minute", 0),
                       cfg_cards.get("interval_minutes", 5))
    pl_time = times[-1] if pl else None
    times = times[:len(videos)]
    for n, (url, t) in enumerate(zip(videos, times), 1):
        before = _card_markers(page)
        say(f"thẻ {n}: kéo thanh trượt tới {_fmt(t)}")
        try:
            seek(page, t, total)
        except NeedsCheck as e:
            warn.append(f"thẻ {n}: {e}")
        say(f"thẻ {n}: thêm thẻ video")
        try:
            _add_video_card(page)
            if source == "own_newest":
                chosen.append(pick_video(page, index=n - 1, exclude=vid))
            else:
                chosen.append(pick_video(page, url=url))
        except StepError as e:
            raise StepError(f"Thẻ {n}: {e}")
        if not _wait(page, lambda: _card_markers(page) > before, 6000):
            raise StepError(f"Thẻ {n}: đã chọn video nhưng trên dòng thời gian không có thêm thẻ mới "
                            f"(đang có {_card_markers(page)} thẻ).")
        box = _new_card_time_box(page)
        if box is None:
            warn.append(f"thẻ {n}: không thấy ô thời gian của thẻ vừa thêm")
            actual.append(None)
            continue
        got = _read_tc(box)
        if got is None or got != t:
            say(f"   thẻ {n} đang ở {_fmt(got) if got is not None else '?'} – đặt lại thành {_fmt(t)}")
            try:
                got = _type_time(page, box, t, f"thẻ {n}", tol=1)
            except StepError as e:
                warn.append(f"thẻ {n}: {e}")
                got = _read_tc(box)
        actual.append(got)
        say(f"   thẻ {n} nằm ở {_fmt(got) if got is not None else '?'} (yêu cầu {_fmt(t)}) – video {chosen[-1][1][:40]}")
        page.wait_for_timeout(600)

    if pl:   # thẻ DANH SÁCH PHÁT ở mốc kế tiếp
        before = _card_markers(page)
        say(f"thẻ danh sách phát: kéo thanh trượt tới {_fmt(pl_time)}")
        try:
            seek(page, pl_time, total)
        except NeedsCheck as e:
            warn.append(f"thẻ danh sách phát: {e}")
        try:
            _add_playlist_card(page)
            got_pl = pick_playlist(page, pl)
        except StepError as e:
            raise StepError(f"Thẻ danh sách phát: {e}")
        if not _wait(page, lambda: _card_markers(page) > before, 6000):
            raise StepError("Thẻ danh sách phát: đã chọn nhưng trên dòng thời gian không có thêm thẻ mới.")
        chosen.append(got_pl)
        times.append(pl_time)
        box = _new_card_time_box(page)
        got = _read_tc(box) if box is not None else None
        if box is not None and (got is None or got != pl_time):
            try:
                got = _type_time(page, box, pl_time, "thẻ danh sách phát", tol=1)
            except StepError as e:
                warn.append(f"thẻ danh sách phát: {e}")
                got = _read_tc(box)
        actual.append(got)
        say(f"   thẻ danh sách phát ở {_fmt(got) if got is not None else '?'} – {got_pl[1][:40]}")

    # kiểm tra lần cuối: đủ số thẻ và mỗi mốc yêu cầu đều có 1 thẻ
    n_cards = _card_markers(page)
    have = _all_card_times(page)
    missing = [t for t in times if not any(abs(h - t) <= 1 for h in have)]
    if n_cards != len(chosen):
        warn.append(f"trên dòng thời gian có {n_cards} thẻ, tool đã thêm {len(chosen)}")
    if missing:
        warn.append("không thấy thẻ ở mốc " + ", ".join(_fmt(t) for t in missing) +
                    " (các thẻ đang ở: " + ", ".join(_fmt(h) for h in have) + ")")
    saved = _save(page)
    global LAST
    LAST = [dict(slot=f"Thẻ {i + 1}" + (" – danh sách phát" if len(v) > 11 else ""),
                 time=_fmt(a if a is not None else t), id=v, title=ti,
                 **({"url": f"https://www.youtube.com/playlist?list={v}"} if len(v) > 11 else {}),
                 owner="strong" if source == "own_newest" or weak.get("_owner") == "strong" else "weak", saved=bool(saved))
            for i, ((v, ti), t, a) in enumerate(zip(chosen, times, actual))]
    summary = " | ".join(f"{_fmt(a if a is not None else t)} {ti[:30]} ({v})"
                         for (v, ti), t, a in zip(chosen, times, actual))
    if not saved:
        summary = "đã đúng sẵn, không cần lưu: " + summary
    if warn:
        raise NeedsCheck(summary + " — " + "; ".join(warn))
    return summary


def clear_cards(page, vid, expected=None):
    """Gỡ các thẻ tool đã gắn. Số thẻ hiện có khác số tool đã gắn -> không xóa, báo gỡ tay."""
    open_editor_panel(page, vid, "cards")
    page.wait_for_timeout(1500)
    n = len(_visible(page, CARD_MARKER))
    if n == 0:
        _close_without_saving(page)
        raise StepError("Video không còn thẻ (có thể đã bị gỡ trước đó).")
    if expected and n != expected:
        _close_without_saving(page)
        raise NeedsCheck(f"Video đang có {n} thẻ, tool chỉ gắn {expected} – không xóa, hãy gỡ tay.")
    say(f"gỡ {n} thẻ")
    _cards_clear(page)
    _save(page)


# ============================================================ kiểm tra "đã đúng sẵn"
IDS_UNDER_JS = r"""(sel) => { const out = [];
  document.querySelectorAll(sel).forEach(root => [root, ...root.querySelectorAll('*')].forEach(e => {
    const s = (e.getAttribute('style') || '') + ' ' + (e.getAttribute('src') || '') + ' ' + (e.getAttribute('href') || '');
    for (const m of s.matchAll(/\/vi(?:_webp)?\/([\w-]{11})|[?&]v=([\w-]{11})/g)) out.push(m[1] || m[2]); }));
  return [...new Set(out)]; }"""


def _ids_under(page, sel):
    try:
        return page.evaluate(IDS_UNDER_JS, sel) or []
    except Exception:
        return []


def _pl_in(page, sel, pl):
    """Danh sách phát `pl` đang có trong vùng `sel` (theo mã hoặc tên)."""
    key = _norm_txt(pl.get("title", ""))[:18]
    try:
        return bool(page.evaluate("""([sel, pid, key]) => [...document.querySelectorAll(sel)].some(e =>
            (pid && e.outerHTML.includes(pid)) || (key && (e.innerText || '').toLowerCase().replace(/\\s+/g, ' ').includes(key)))""",
                                  [sel, pl.get("id", ""), key]))
    except Exception:
        return False


def end_screen_matches(page, vid, weak, source="weak", exact=False):
    """Màn hình kết thúc đang mở đã có ĐÚNG video bạn điền chưa?
    Đúng = đủ số ô video và mọi video đang hiện đều là link trong danh sách video của kênh cần kéo.
    Trả về câu mô tả (đúng sẵn) hoặc "" (chưa đúng / không đọc được -> làm như bình thường)."""
    links = _weak_ids(weak)
    if source == "own_newest" or not links:
        return ""
    want = max(1, min(2, int(weak.get("_es_count", 2) or 2)))
    pl = weak.get("_pl") if weak.get("_es_pl") else None
    if pl:
        want = 1
        if not _pl_in(page, "ytve-endscreen-editor-preview-overlay-item.visible", pl):
            if exact or _es_items(page):
                say("   màn hình kết thúc chưa có danh sách phát cần gắn")
            return ""
    n = min(want, len(links))
    have = []
    for _ in range(10):   # ảnh thu nhỏ có thể tải chậm
        have = [i for i in _ids_in_preview(page) if i != vid]
        if len(have) >= n:
            break
        page.wait_for_timeout(500)
    if exact:   # THAY THẾ: chỉ bỏ qua khi đang gắn CHÍNH XÁC đúng các video cần gắn lần này
        if sorted(have) == sorted(links[:n]):
            return f"màn hình kết thúc đã đúng chính xác {n} video cần gắn ({', '.join(have)}) – bỏ qua"
        if have:
            say(f"   THAY THẾ: đang có {', '.join(have)} – cần gắn {', '.join(links[:n])} → xóa cũ, gắn mới")
        return ""
    if len(have) >= n and all(h in links for h in have):
        return f"màn hình kết thúc đã có {len(have)} video của kênh cần kéo ({', '.join(have)}) – bỏ qua"
    if have:
        say(f"   màn hình kết thúc đang có video {', '.join(have)} – không khớp danh sách video bạn điền")
    return ""


def cards_match(page, vid, weak, duration, cfg_cards, source="weak", exact=False):
    """Thẻ đang có đã ĐÚNG như yêu cầu chưa? Đúng = đủ số thẻ, (đọc được thì) đúng mốc thời gian,
    và (đọc được thì) mọi video trong thẻ đều là link của kênh cần kéo. Trả về câu mô tả hoặc ""."""
    links = _weak_ids(weak)
    want = max(1, min(5, int(cfg_cards.get("count", 3) or 3)))
    if source != "own_newest":
        if not links:
            return ""
        want = min(want, len(links))
    pl = weak.get("_pl") if cfg_cards.get("playlist") and source != "own_newest" else None
    if pl:
        want = min(want, 4)
        if not _pl_in(page, "ytve-info-cards-editor-options-panel", pl):
            return ""
    n = _card_markers(page) - (1 if pl else 0)
    if n < want:
        return ""
    total = duration or _duration_from_ruler(page)
    times = card_times(total, want, cfg_cards.get("start_minute", 0), cfg_cards.get("interval_minutes", 5))
    have = _all_card_times(page)
    if len(have) >= len(times) and any(not any(abs(h - t) <= 1 for h in have) for t in times):
        say("   thẻ đang có không đúng mốc yêu cầu (" + ", ".join(_fmt(h) for h in have) + ")")
        return ""
    ids = [i for i in _ids_under(page, "ytve-info-cards-editor-options-panel div.info-card-row") if i != vid]
    if exact and source != "own_newest":   # THAY THẾ: đúng số thẻ, đúng từng video cần gắn lần này
        if n != want or sorted(ids) != sorted(links[:want]):
            say(f"   THAY THẾ: thẻ đang có {', '.join(ids) or n} – cần gắn {', '.join(links[:want])} → xóa cũ, gắn mới")
            return ""
    if source != "own_newest" and ids and not all(i in links for i in ids):
        say(f"   thẻ đang có video {', '.join(ids)} – không khớp danh sách video bạn điền")
        return ""
    return (f"video đã có {n} thẻ" + (f" ở mốc {', '.join(_fmt(h) for h in have)}" if have else "") +
            (f" ({', '.join(ids)})" if ids else "") + " – bỏ qua")


def check_end_screen(page, vid, weak, source="weak"):
    """Xem kết quả THỰC TẾ ngay trong trình chỉnh sửa Màn hình kết thúc CÒN ĐANG MỞ (khi 1 bước vừa báo lỗi).
    Trình chỉnh sửa đã đóng -> không mở lại (mỗi mục chỉ vào 1 lần)."""
    if vid not in (page.url or "") or not _editor_open_quick(page):
        return ""
    page.wait_for_timeout(1000)
    try:
        return end_screen_matches(page, vid, weak, source) if _es_items(page) else ""
    finally:
        _close_without_saving(page)


def check_cards(page, vid, weak, duration, cfg_cards, source="weak"):
    if vid not in (page.url or "") or not _editor_open_quick(page):
        return ""                      # trình chỉnh sửa Thẻ đã đóng -> không mở lại
    page.wait_for_timeout(1000)
    try:
        return cards_match(page, vid, weak, duration, cfg_cards, source) if _visible(page, CARD_MARKER) else ""
    finally:
        _close_without_saving(page)
