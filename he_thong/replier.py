"""
Trả lời bình luận của khán giả trên các video của KÊNH MẠNH (kênh của bạn).

- Mở lần lượt video của kênh (tab Video), tải HẾT bình luận (sắp xếp Mới nhất, cuộn tới cuối).
- Mỗi bình luận: nhận ngôn ngữ + loại (cmt_lang). CHỈ bình luận KHEN mới được tự trả lời cảm ơn
  (đúng ngôn ngữ người viết), thả tim, bấm thích – theo các ô bạn tích.
- KHÔNG trả lời trùng: bỏ qua bình luận của chính kênh, bình luận kênh đã trả lời rồi (đọc phần phản hồi),
  bình luận tool đã xử lý (lưu trong binh_luan.db).
- Mỗi lần trả lời xong tool đọc lại đúng bình luận đó để xác nhận câu trả lời đã hiện, rồi mới ghi ✅.
"""
import os
import random
import re
import sqlite3
import threading
from datetime import datetime

import cmt_lang
from studio import StepError, _scroll_to_comments

BASE = os.path.dirname(os.path.abspath(__file__))
import paths   # noqa: E402
DB_PATH = os.path.join(paths.DATA, "binh_luan.db")

S_SENT, S_PREVIEW, S_SKIP, S_FAIL, S_DONE_BEFORE, S_HEARTED = (
    "✅ Đã trả lời", "Xem trước – chưa gửi", "Bỏ qua (không phải khen)", "⚠️ Chưa làm được",
    "Kênh đã trả lời trước", "✅ Đã tim / thích")

SCHEMA = """
CREATE TABLE IF NOT EXISTS comments (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    cid TEXT UNIQUE, channel_id TEXT, video_id TEXT, video_title TEXT,
    author TEXT, author_url TEXT, text TEXT, lang TEXT, kind TEXT, why TEXT, reply TEXT,
    status TEXT, actions TEXT, note TEXT, seen_at TEXT, done_at TEXT
);
CREATE INDEX IF NOT EXISTS idx_c_video ON comments(video_id);
CREATE TABLE IF NOT EXISTS videos_done (
    video_id TEXT PRIMARY KEY, channel_id TEXT, title TEXT, count INTEGER, done_at TEXT
);
"""


class DB:
    def __init__(self, path=DB_PATH):
        self.lock = threading.RLock()
        self.conn = sqlite3.connect(path, check_same_thread=False)
        self.conn.row_factory = sqlite3.Row
        with self.lock:
            self.conn.executescript(SCHEMA)
            self.conn.commit()

    def get(self, cid):
        with self.lock:
            r = self.conn.execute("SELECT * FROM comments WHERE cid=?", (cid,)).fetchone()
        return dict(r) if r else None

    def save(self, d):
        d = dict(d)
        d.setdefault("seen_at", _now())
        keys = list(d)
        with self.lock:
            self.conn.execute(
                f"INSERT INTO comments({','.join(keys)}) VALUES ({','.join('?' * len(keys))}) "
                f"ON CONFLICT(cid) DO UPDATE SET {', '.join(f'{k}=excluded.{k}' for k in keys if k != 'cid')}",
                [d[k] for k in keys])
            self.conn.commit()

    def video_done(self, vid):
        with self.lock:
            r = self.conn.execute("SELECT * FROM videos_done WHERE video_id=?", (vid,)).fetchone()
        return dict(r) if r else None

    def mark_video(self, vid, channel_id, title, count):
        with self.lock:
            self.conn.execute("INSERT INTO videos_done(video_id, channel_id, title, count, done_at) VALUES (?,?,?,?,?) "
                              "ON CONFLICT(video_id) DO UPDATE SET count=excluded.count, done_at=excluded.done_at, "
                              "title=excluded.title", (vid, channel_id, title, count, _now()))
            self.conn.commit()

    def rows(self, limit=3000, channel_id=None):
        with self.lock:
            if channel_id:
                rs = self.conn.execute("SELECT * FROM comments WHERE channel_id=? ORDER BY id DESC LIMIT ?",
                                       (channel_id, limit)).fetchall()
            else:
                rs = self.conn.execute("SELECT * FROM comments ORDER BY id DESC LIMIT ?", (limit,)).fetchall()
        return [dict(r) for r in rs]

    def clear(self):
        with self.lock:
            self.conn.execute("DELETE FROM videos_done")
            self.conn.execute("DELETE FROM comments")
            self.conn.commit()

    def export(self, path, rows):
        head = ["STT", "Thời gian", "Video", "Link video", "Người bình luận", "Bình luận", "Ngôn ngữ", "Loại",
                "Lý do", "Câu trả lời", "Đã làm", "Trạng thái", "Ghi chú"]
        data = [[i, r.get("done_at") or r.get("seen_at"), r.get("video_title"),
                 f"https://www.youtube.com/watch?v={r.get('video_id')}&lc={r.get('cid')}", r.get("author"),
                 r.get("text"), cmt_lang.lang_name(r.get("lang")), r.get("kind"), r.get("why"), r.get("reply"),
                 r.get("actions"), r.get("status"), r.get("note")] for i, r in enumerate(rows, 1)]
        if path.lower().endswith(".xlsx"):
            from openpyxl import Workbook
            from openpyxl.styles import Alignment, Font, PatternFill
            wb = Workbook()
            ws = wb.active
            ws.title = "Trả lời bình luận"
            ws.append(head)
            for c in ws[1]:
                c.font = Font(bold=True, color="FFFFFF")
                c.fill = PatternFill("solid", fgColor="2F3542")
            for row in data:
                ws.append(row)
            for i, w in enumerate([6, 19, 40, 44, 22, 60, 14, 16, 30, 30, 18, 20, 30], 1):
                ws.column_dimensions[ws.cell(1, i).column_letter].width = w
            for row in ws.iter_rows(min_row=2):
                for c in row:
                    c.alignment = Alignment(wrap_text=True, vertical="top")
            ws.freeze_panes = "A2"
            wb.save(path)
        else:
            import csv
            with open(path, "w", newline="", encoding="utf-8-sig") as f:
                w = csv.writer(f)
                w.writerow(head)
                w.writerows(data)
        return path


def _now():
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")


def _dump(th, it, msg):
    """Lưu đoạn trang của bình luận không làm được vào logs/ (đi kèm gói chẩn đoán) để sửa đúng chỗ."""
    try:
        d = os.path.join(paths.DATA, "logs")
        os.makedirs(d, exist_ok=True)
        html = th.evaluate("e => e.outerHTML")[:60000]
        name = os.path.join(d, f"tra_loi_loi_{datetime.now():%Y%m%d_%H%M%S}.html")
        with open(name, "w", encoding="utf-8") as f:
            f.write(f"<!-- {it.get('author')} | {msg} -->\n{html}")
    except Exception:
        pass


def _say(msg):
    print(f"      · {msg}", flush=True)


# ====================================================================== danh sách video của kênh
VIDEOS_JS = r"""() => {
  const out = [], seen = new Set();
  for (const a of document.querySelectorAll('a#video-title-link, a#video-title, a#thumbnail, ' +
                                            'ytd-rich-grid-media a[href*="watch?v="], a.yt-lockup-metadata-view-model-wiz__title, ' +
                                            'yt-lockup-view-model a[href*="watch?v="]')) {
    const m = (a.getAttribute('href') || '').match(/[?&]v=([\w-]{11})/);
    if (!m || seen.has(m[1])) continue;
    seen.add(m[1]);
    const box = a.closest('ytd-rich-item-renderer, ytd-grid-video-renderer, yt-lockup-view-model') || a;
    const t = box.querySelector('#video-title, h3, [title]');
    out.push([m[1], ((t && (t.getAttribute('title') || t.textContent)) || a.getAttribute('title') || '').trim()]);
  }
  return out; }"""


def list_videos(page, channel_id, limit=0):
    """Video (không tính Shorts) trên tab Video của kênh, mới nhất trước. limit=0 -> tất cả."""
    page.goto(f"https://www.youtube.com/channel/{channel_id}/videos", wait_until="domcontentloaded")
    page.wait_for_timeout(5000)
    got, same = [], 0
    for _ in range(200):
        cur = page.evaluate(VIDEOS_JS)
        if limit and len(cur) >= limit:
            got = cur
            break
        if len(cur) == len(got):
            same += 1
            if same >= 3:
                break
        else:
            same = 0
        got = cur
        page.mouse.wheel(0, 4000)
        page.wait_for_timeout(1500)
    return got[:limit] if limit else got


# ====================================================================== đọc bình luận của 1 video
THREADS_JS = r"""(owner) => {
  // đọc mọi bình luận gốc đang có trên trang; đánh dấu từng khung bằng data-keo-t để thao tác lại đúng khung
  const vis = e => { if (!e) return false; const r = e.getBoundingClientRect(), s = getComputedStyle(e);
    return r.width > 0 && r.height > 0 && s.visibility !== 'hidden' && s.display !== 'none'; };
  const own = (h) => { h = (h || '').toLowerCase().replace(/\/+$/, ''); return !!owner &&
    owner.some(o => o && (h.endsWith('/' + o) || h.endsWith(o))); };
  const out = [];
  const threads = [...document.querySelectorAll('ytd-comment-thread-renderer')];
  threads.forEach((th, i) => {
    th.setAttribute('data-keo-t', String(i));
    const top = th.querySelector(':scope > #comment, :scope > ytd-comment-view-model, :scope > ytd-comment-renderer')
              || th.querySelector('ytd-comment-view-model, ytd-comment-renderer');
    if (!top) return;
    const a = top.querySelector('#author-text');
    const author = ((a && a.textContent) || '').replace(/\s+/g, ' ').trim();
    const aurl = (a && a.getAttribute('href')) || '';
    const textEl = top.querySelector('#content-text');
    const text = ((textEl && (textEl.innerText || textEl.textContent)) || '').trim();
    const link = top.querySelector('#published-time-text a, a[href*="lc="]');
    const lc = ((link && link.getAttribute('href')) || '').match(/[?&]lc=([\w.-]+)/);
    const badge = top.querySelector('ytd-author-comment-badge-renderer, #author-comment-badge');
    const isOwner = own(aurl) || (!!badge && vis(badge) && (badge.textContent || '').trim().length > 0);
    // phản hồi: kênh đã trả lời chưa (ảnh đại diện chủ kênh trên nút "N phản hồi" hoặc phản hồi có huy hiệu chủ kênh)
    const reps = th.querySelector('ytd-comment-replies-renderer, #replies');
    let ownerReplied = false, nReplies = 0;
    if (reps) {
      const ct = reps.querySelector('#creator-thumbnail');
      if (ct && vis(ct)) ownerReplied = true;
      const items = [...reps.querySelectorAll('ytd-comment-view-model, ytd-comment-renderer')];
      nReplies = items.length;
      for (const it of items) {
        const ra = it.querySelector('#author-text');
        const rb = it.querySelector('ytd-author-comment-badge-renderer, #author-comment-badge');
        if (own(ra && ra.getAttribute('href')) || (rb && vis(rb) && (rb.textContent || '').trim())) ownerReplied = true;
      }
    }
    const more = reps && reps.querySelector('#more-replies button, #more-replies, ' +
                                           'ytd-button-renderer#more-replies button');
    const lab = b => ((b && (b.getAttribute('aria-label') || b.innerText)) || '').toLowerCase();
    const likeB = top.querySelector('#like-button button, ytd-toggle-button-renderer#like-button button, ' +
                                    'like-button-view-model button');
    const heartB = top.querySelector('#creator-heart-button, #creator-heart button, ytd-creator-heart-renderer button');
    const heartR = top.querySelector('ytd-creator-heart-renderer, #creator-heart');
    const hearted = !!heartR && (!!heartR.querySelector('#hearted:not([hidden]), [is-hearted], .hearted') ||
                    (heartB && (heartB.getAttribute('aria-pressed') === 'true' || /bỏ|un-?heart|remove/.test(lab(heartB)))));
    out.push({i, author, aurl, text, cid: lc ? lc[1] : '', owner: isOwner, ownerReplied,
              hasReplies: !!(more && vis(more)) || nReplies > 0,
              liked: !!likeB && likeB.getAttribute('aria-pressed') === 'true',
              hearted, canHeart: !!heartB});
  });
  return out; }"""


def _owner_keys(page, channel_id, handle=""):
    """Khóa nhận ra chủ kênh: mã kênh UC..., @handle (đọc trên trang video)."""
    keys = {channel_id.lower()} if channel_id else set()
    if handle:
        keys.add(handle.lower().lstrip("/"))
    try:
        h = page.evaluate("() => (document.querySelector('ytd-video-owner-renderer a[href], #owner a[href]')"
                          " || {}).getAttribute?.('href') || ''")
        if h:
            keys.add(h.lower().strip("/").split("/")[-1])
    except Exception:
        pass
    return [k for k in keys if k]


def _sort_newest(page):
    """Sắp xếp bình luận 'Mới nhất trước' (để tải được hết, không bị ẩn bớt như 'Hàng đầu')."""
    try:
        btn = page.locator("ytd-comments #sort-menu tp-yt-paper-button, ytd-comments #sort-menu yt-sort-filter-sub-menu-renderer "
                           "#trigger, #sort-menu #label, ytd-comments-header-renderer #sort-menu").first
        if not btn.count():
            return
        btn.click(timeout=5000)
        page.wait_for_timeout(800)
        items = page.locator("tp-yt-paper-listbox a, tp-yt-paper-listbox tp-yt-paper-item, "
                             "yt-dropdown-menu tp-yt-paper-item").filter(
            has_text=re.compile(r"Mới nhất|Newest", re.I))
        if items.count():
            items.first.click(timeout=5000)
            page.wait_for_timeout(2500)
        else:
            page.keyboard.press("Escape")
    except Exception:
        try:
            page.keyboard.press("Escape")
        except Exception:
            pass


COUNT_JS = r"""() => {
  // số bình luận ghi ở đầu phần bình luận ("12 bình luận" / "1.234 Comments"); viết tắt (1,2 N / 1.2K) -> null
  const h = document.querySelector('ytd-comments-header-renderer #count, ytd-comments-header-renderer h2');
  const t = ((h && h.innerText) || '').trim();
  const m = t.match(/^([\d.,\s]+)\s*(\S*)/);
  if (!m) return null;
  if (/^(N|K|M|Tr|nghìn|triệu)/i.test(m[2] || '')) return null;
  const n = parseInt(m[1].replace(/[.,\s]/g, ''), 10);
  return isNaN(n) ? null : n; }"""


def comment_count(page):
    try:
        for _ in range(6):
            n = page.evaluate(COUNT_JS)
            if n is not None:
                return n
            page.wait_for_timeout(700)
    except Exception:
        pass
    return None


def open_comments(page, url):
    """Mở video, cuộn tới phần bình luận (chưa tải hết)."""
    page.goto(url, wait_until="domcontentloaded")
    page.wait_for_timeout(5000)
    try:
        page.evaluate("document.querySelector('video')?.pause()")
    except Exception:
        pass
    _scroll_to_comments(page)
    page.wait_for_timeout(2500)


def load_all(page, url, max_comments=0, opened=False):
    """Mở video, tải phần bình luận tới hết (hoặc tới max_comments)."""
    if not opened:
        open_comments(page, url)
    _sort_newest(page)
    last, same = -1, 0
    for _ in range(300):
        n = page.locator("ytd-comment-thread-renderer").count()
        if max_comments and n >= max_comments:
            break
        if n == last:
            same += 1
            if same >= 3:
                break
        else:
            same = 0
        last = n
        page.evaluate("window.scrollTo(0, document.documentElement.scrollHeight)")
        page.wait_for_timeout(1600)
    try:
        page.evaluate("document.querySelector('video')?.pause()")
    except Exception:
        pass


def _thread(page, i):
    return page.locator(f"ytd-comment-thread-renderer[data-keo-t='{i}']").first


def _top(th):
    loc = th.locator(":scope > #comment, :scope > ytd-comment-view-model, :scope > ytd-comment-renderer")
    return loc.first if loc.count() else th.locator("ytd-comment-view-model, ytd-comment-renderer").first


def _expand_replies(page, th):
    """Mở phần phản hồi của bình luận (để xem kênh đã trả lời chưa)."""
    b = th.locator("#more-replies button, ytd-button-renderer#more-replies button, #more-replies").first
    try:
        if b.count() and b.is_visible():
            b.scroll_into_view_if_needed()
            b.click(timeout=5000)
            page.wait_for_timeout(2500)
            return True
    except Exception:
        pass
    return False


def _norm(t):
    return re.sub(r"\s+", " ", t or "").strip().lower()


def _reply(page, th, text):
    """Bấm Phản hồi trên đúng bình luận → gõ câu cảm ơn → bấm Phản hồi → đọc lại xác nhận đã hiện."""
    top = _top(th)
    top.scroll_into_view_if_needed()
    btn = None
    for loc in (top.locator("#reply-button-end button"),
                top.get_by_role("button", name=re.compile(r"^\s*(Phản hồi|Trả lời|Reply)\s*$", re.I)),
                top.locator("#reply-button-end")):
        try:
            vis = [loc.nth(k) for k in range(loc.count()) if loc.nth(k).is_visible()]
        except Exception:
            vis = []
        if vis:
            btn = vis[0]
            break
    if btn is None:
        raise StepError("không thấy nút Phản hồi của bình luận")
    btn.click(timeout=6000)
    page.wait_for_timeout(1200)
    box = None
    for _ in range(16):
        for sel in ("ytd-comment-reply-dialog-renderer #contenteditable-root", "#reply-dialog #contenteditable-root",
                    "ytd-commentbox #contenteditable-root"):
            loc = th.locator(sel)
            if loc.count() and loc.first.is_visible():
                box = loc.first
                break
        if box is not None:
            break
        page.wait_for_timeout(500)
    if box is None:
        raise StepError("bấm Phản hồi nhưng không thấy ô viết câu trả lời")
    box.click()
    page.wait_for_timeout(300)
    # gõ như người thật (có sự kiện nhập liệu – YouTube mới mở khóa nút gửi); bỏ phần @tên YouTube tự điền sẵn
    try:
        page.keyboard.press("Control+A")
        page.keyboard.press("Delete")
        page.keyboard.insert_text(text)
    except Exception:
        box.fill(text)
    page.wait_for_timeout(500)
    if _words(text)[:12] not in _words(box.inner_text()):
        box.fill("")
        box.press_sequentially(text, delay=25)
        page.wait_for_timeout(400)
    sub = None
    for sel in ("ytd-comment-reply-dialog-renderer #submit-button button", "#reply-dialog #submit-button button",
                "ytd-commentbox #submit-button button", "ytd-commentbox #submit-button"):
        loc = th.locator(sel)
        if loc.count() and loc.first.is_visible():
            sub = loc.first
            break
    if sub is None:
        raise StepError("không thấy nút gửi câu trả lời")
    for _ in range(10):   # chờ nút gửi hết bị khóa
        try:
            if sub.get_attribute("aria-disabled") != "true" and sub.get_attribute("disabled") is None:
                break
        except Exception:
            break
        page.wait_for_timeout(300)
    sub.click(timeout=6000)
    key = _words(text)[:24]
    try:
        top_txt = _words(top.locator("#content-text").first.inner_text())
    except Exception:
        top_txt = ""

    def seen():
        if not key:
            return False
        try:
            reps = th.locator("ytd-comment-replies-renderer, #replies")
            if reps.count() and key in _words(reps.first.inner_text()):
                return True
            # câu trả lời mới có thể nằm ngoài khung phản hồi cũ: có trong khung bình luận nhưng không phải chữ gốc
            return key in _words(th.inner_text()) and key not in top_txt
        except Exception:
            return False

    def box_open():
        try:
            return box.is_visible() and bool(_words(box.inner_text()))
        except Exception:
            return False
    for _ in range(24):   # ~12 giây
        page.wait_for_timeout(500)
        if seen():
            return True
        if not box_open():
            break
    if seen():
        return True
    if not box_open():
        # YouTube đã nhận (ô viết đã đóng / trống) – câu trả lời có thể nằm trong phần phản hồi đang thu gọn
        _expand_replies(page, th)
        for _ in range(6):
            if seen():
                return True
            page.wait_for_timeout(500)
        return "sent"
    raise StepError("YouTube chưa nhận câu trả lời (ô viết vẫn mở sau khi bấm gửi)")


def _words(t):
    """Chỉ giữ chữ và số (bỏ emoji, dấu câu, @tên) để so khớp câu trả lời trên trang."""
    return re.sub(r"[^\w]+", " ", str(t or "").lower(), flags=re.U).strip()


def _toggle(page, th, kind):
    """Bấm thích ('like') hoặc thả tim ('heart') trên bình luận gốc; bỏ qua nếu đã bật. Trả True nếu đã bật xong."""
    top = _top(th)
    sels = (["#like-button button", "like-button-view-model button", "ytd-toggle-button-renderer#like-button button"]
            if kind == "like" else
            ["ytd-creator-heart-renderer button", "#creator-heart button", "button#creator-heart-button",
             "#creator-heart-button"])
    b = None
    for sel in sels:
        loc = top.locator(sel)
        if loc.count():
            b = loc.first
            break
    if b is None:
        return False
    on = lambda: (b.get_attribute("aria-pressed") == "true") or bool(
        re.search(r"bỏ|un-?heart|remove|đã thả", (b.get_attribute("aria-label") or "").lower()))
    if kind == "heart":
        def on():   # noqa: F811
            try:
                return bool(top.evaluate(
                    "t => { const r = t.querySelector('ytd-creator-heart-renderer, #creator-heart'); if (!r) return false;"
                    " const b = r.querySelector('button, #creator-heart-button');"
                    " return !!r.querySelector('#hearted:not([hidden]), [is-hearted], .hearted') ||"
                    " (b && (b.getAttribute('aria-pressed') === 'true' ||"
                    " /bỏ|un-?heart|remove/i.test(b.getAttribute('aria-label') || ''))); }"))
            except Exception:
                return False
    if on():
        return True
    b.scroll_into_view_if_needed()
    b.click(timeout=5000)
    page.wait_for_timeout(1200)
    return on()


# ====================================================================== chạy
def run(page, cfg, opts, db=None, log=print):
    """opts: videos (0 = tất cả), max_per_video, reply, heart, like, scope ('praise'|'all_ok'),
    preview (chỉ đọc), default_lang, ai (provider, model, key) hoặc None, delay (giây giữa các thao tác)."""
    db = db or DB()
    s = cfg["strong_channel"]
    cid_ch = s.get("channel_id", "")
    handle = ""
    m = re.search(r"/(@[\w.\-%]+)", str(s.get("url") or ""))
    if m:
        handle = m.group(1)
    target = max(1, int(opts.get("videos") or 4))      # số video CẦN XỬ LÝ mỗi lượt (mới nhất trước)
    scan_cap = max(target * 4, 20)                      # xem tối đa bấy nhiêu video để tìm đủ
    vids = list_videos(page, cid_ch, scan_cap)
    if not vids:
        raise StepError("Không đọc được video nào trên tab Video của kênh mạnh.")
    log(f"Xử lý {target} video mới nhất có bình luận mới của kênh {s.get('name')} "
        f"(video đã tương tác hết thì bỏ qua, lấy video kế tiếp)."
        + (" CHẾ ĐỘ XEM TRƯỚC – chỉ đọc, không trả lời." if opts.get("preview") else ""))
    total = {"sent": 0, "liked": 0, "hearted": 0, "skip": 0, "fail": 0, "before": 0, "praise": 0, "videos": 0,
             "skipped_videos": 0}
    max_total = int(opts.get("max_replies") or 0)
    try:   # câu đã gửi ở các lần trước -> lần này không lặp lại
        import thanks_bank
        thanks_bank.remember([r["reply"] for r in db.rows(400, cid_ch)
                              if r.get("reply") and r.get("status") == S_SENT][::-1])
    except Exception:
        pass
    for n, (vid, title) in enumerate(vids, 1):
        if total["videos"] >= target:
            break
        url = f"https://www.youtube.com/watch?v={vid}"
        try:
            open_comments(page, url)
        except StepError as e:
            log(f"\n↷ {title[:70]}: {e} – bỏ qua")
            continue
        cnt = comment_count(page)
        prev = db.video_done(vid)
        if cnt == 0:
            log(f"\n↷ {title[:70]}: chưa có bình luận – bỏ qua")
            continue
        if prev and cnt is not None and prev.get("count") is not None and cnt <= int(prev["count"]):
            total["skipped_videos"] += 1
            log(f"\n↷ {title[:70]}: đã tương tác hết từ lần trước, không có bình luận mới – bỏ qua")
            continue
        total["videos"] += 1
        sent_before, fail_before = total["sent"], total["fail"]
        log(f"\n▶ Video {total['videos']}/{target}: {title[:80]}"
            + (f" ({cnt} bình luận" + (f", {cnt - int(prev['count'])} mới" if prev and prev.get('count') is not None else "")
               + ")" if cnt is not None else ""))
        try:
            load_all(page, url, int(opts.get("max_per_video") or 0), opened=True)
        except StepError as e:
            log(f"   ↷ bỏ qua video này: {e}")
            continue
        owner = _owner_keys(page, cid_ch, handle)
        items = page.evaluate(THREADS_JS, owner)
        kinds = {}
        plan = []
        for it in items:
            key = it["cid"] or f"{vid}:{_norm(it['author'])}:{_norm(it['text'])[:80]}"
            a = cmt_lang.analyze(it["text"], it["owner"], opts.get("default_lang", "en"))
            if a["kind"] not in (cmt_lang.OWNER,) and opts.get("ai"):
                ai = cmt_lang.ai_check(it["text"], *opts["ai"])
                if ai:
                    # AI và tool phải CÙNG nói "khen" thì mới trả lời; ngôn ngữ ưu tiên theo AI
                    if a["kind"] == cmt_lang.PRAISE and ai["kind"] != cmt_lang.PRAISE:
                        a["kind"], a["why"] = ai["kind"], f"AI không chắc là khen ({ai['kind']})"
                    if ai["lang"]:
                        a["lang"] = ai["lang"]
                        a["lang_name"] = cmt_lang.lang_name(ai["lang"])
                        try:
                            import thanks_bank
                            a["reply"] = thanks_bank.pick(ai["lang"], it["text"], cmt_lang.THANKS[ai["lang"]][1])
                        except Exception:
                            a["reply"] = cmt_lang.THANKS[ai["lang"]][1]
            kinds[a["kind"]] = kinds.get(a["kind"], 0) + 1
            plan.append((it, key, a))
        log(f"   đọc được {len(items)} bình luận: " + (", ".join(f"{v} {k.lower()}" for k, v in kinds.items()) or "0"))
        for it, key, a in plan:
            if a["kind"] == cmt_lang.OWNER:
                continue
            old = db.get(key)
            row = dict(cid=key, channel_id=cid_ch, video_id=vid, video_title=title, author=it["author"],
                       author_url=it["aurl"], text=it["text"], lang=a["lang"], kind=a["kind"], why=a["why"],
                       reply=a["reply"] if a["kind"] == cmt_lang.PRAISE else "")
            ok_kind = a["kind"] == cmt_lang.PRAISE or (
                opts.get("scope") == "all_ok" and a["kind"] in (cmt_lang.OTHER, cmt_lang.QUESTION))
            if old and old.get("status") in (S_SENT, S_DONE_BEFORE):
                continue   # đã trả lời từ lần trước (tool hoặc chính bạn)
            if not ok_kind:
                db.save(dict(row, status=S_SKIP, note=a["why"]))
                total["skip"] += 1
                continue
            if a["kind"] == cmt_lang.PRAISE:
                total["praise"] += 1
            short = (it["text"] or "").replace("\n", " ")[:70]
            if opts.get("preview"):
                db.save(dict(row, status=S_PREVIEW if a["kind"] == cmt_lang.PRAISE else S_SKIP,
                             note="xem trước – chưa gửi"))
                log(f"   • {it['author']} [{a['lang_name']}] \"{short}\" → sẽ trả lời: {a['reply']}"
                    if a["kind"] == cmt_lang.PRAISE else f"   • {it['author']}: \"{short}\" → sẽ tim/thích")
                continue
            th = _thread(page, it["i"])
            done, note = [], ""
            try:
                want_reply = opts.get("reply", True) and a["kind"] == cmt_lang.PRAISE
                if want_reply and (it["ownerReplied"] or it["hasReplies"]):
                    if it["hasReplies"] and not it["ownerReplied"]:
                        _expand_replies(page, th)
                        again = page.evaluate(THREADS_JS, owner)
                        it2 = next((x for x in again if x["i"] == it["i"]), it)
                        it["ownerReplied"] = it2["ownerReplied"]
                    if it["ownerReplied"]:
                        want_reply = False
                        note = "kênh đã trả lời bình luận này từ trước"
                        total["before"] += 1
                # THÍCH hoặc TIM – chỉ 1 trong 2, chọn theo nội dung bình luận (đã có 1 trong 2 thì thôi)
                act, _why = cmt_lang.choose_react(it["text"], opts.get("like", True), opts.get("heart", True))
                if act == "heart" and not it["canHeart"] and opts.get("like", True):
                    act = "like"
                if act and not it["liked"] and not it["hearted"]:
                    if _toggle(page, th, act):
                        done.append("❤ tim" if act == "heart" else "👍 thích")
                        total["hearted" if act == "heart" else "liked"] += 1
                if want_reply:
                    if max_total and total["sent"] >= max_total:
                        note = f"đã đủ {max_total} câu trả lời cho lượt này – để lần sau"
                    else:
                        _reply(page, th, a["reply"])
                        done.append("💬 trả lời")
                        total["sent"] += 1
                if "💬 trả lời" in done:
                    status = S_SENT
                elif "từ trước" in note:
                    status = S_DONE_BEFORE
                elif done:
                    status = S_HEARTED
                else:
                    status = S_SKIP
                db.save(dict(row, status=status, actions=", ".join(done), note=note, done_at=_now()))
                if done:
                    log(f"   ✅ {it['author']} [{a['lang_name']}] \"{short}\" → " + " · ".join(done)
                        + (f": {a['reply']}" if "💬 trả lời" in done else ""))
                elif note:
                    log(f"   ↷ {it['author']}: {note}")
            except Exception as e:
                msg = str(e).splitlines()[0][:150]
                total["fail"] += 1
                _dump(th, it, msg)
                db.save(dict(row, status=S_FAIL, actions=", ".join(done), note=msg, done_at=_now()))
                log(f"   ⚠️ {it['author']}: chưa làm được ({msg})")
                try:
                    page.keyboard.press("Escape")
                except Exception:
                    pass
            page.wait_for_timeout(int(1000 * random.uniform(*opts.get("delay", (2.5, 5.0)))))
        # video xử lý trọn vẹn (không lỗi) -> ghi nhớ số bình luận; lần sau không có bình luận mới thì bỏ qua
        if not opts.get("preview") and total["fail"] == fail_before:
            base = cnt if cnt is not None else len(items)
            db.mark_video(vid, cid_ch, title, base + (total["sent"] - sent_before))
    if total["videos"] == 0:
        log("\nKhông có video nào có bình luận mới cần tương tác.")
    log(f"\n🏁 Xong {total['videos']} video"
        + (f" (bỏ qua {total['skipped_videos']} video đã tương tác hết)" if total["skipped_videos"] else "")
        + f": {total['sent']} câu trả lời · {total['hearted']} tim · {total['liked']} thích · "
        f"{total['before']} bình luận kênh đã trả lời trước · {total['skip']} bình luận không phải khen (để bạn tự xem)"
        + (f" · {total['fail']} chưa làm được" if total["fail"] else ""))
    return total
