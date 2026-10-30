"""
Luồng chạy nền của module Phân tích & tương tác video.

- Dùng đúng trình duyệt + phiên đăng nhập của tool (browser.Browsers) – mở thêm TAB mới, không đụng tab khác.
- Tìm 4–6 video cùng chủ đề trên Trang chủ YouTube (thiếu thì bổ sung bằng tìm kiếm nếu bạn cho phép),
  mở mỗi video 1 tab, lần lượt chuyển tab, đọc phụ đề / bản chép lời của khoảng 6–10 phút, nhờ AI chấm điểm
  và viết 3 bình luận.
- KHÔNG tự Like / Dislike / bình luận: chỉ bấm Like / Dislike khi bạn bấm nút xác nhận trên tool;
  bình luận do bạn tự dán và đăng. Video được dừng phát ngay khi mở (không tạo lượt xem giả).

Toàn bộ thao tác Playwright chạy trên MỘT luồng (luồng này); giao diện chỉ gửi lệnh vào hàng đợi.
"""
import logging
import os
import queue
import re
import threading
import time
import traceback

import pt_ai

BASE = os.path.dirname(os.path.abspath(__file__))
import paths   # noqa: E402
LOG_DIR = os.path.join(paths.DATA, "logs")
os.makedirs(LOG_DIR, exist_ok=True)
log = logging.getLogger("phan_tich")
if not log.handlers:
    h = logging.FileHandler(os.path.join(LOG_DIR, "phan_tich.log"), encoding="utf-8")
    h.setFormatter(logging.Formatter("%(asctime)s %(levelname)s %(message)s"))
    log.addHandler(h)
    log.setLevel(logging.INFO)


class Stopped(Exception):
    pass


# ============================================================ đọc trang YouTube
LIST_JS = r"""() => {
  const out = [], seen = new Set();
  const items = document.querySelectorAll('ytd-rich-item-renderer, ytd-video-renderer, yt-lockup-view-model, ' +
                                          'ytd-compact-video-renderer, ytd-grid-video-renderer');
  for (const it of items) {
    if (it.parentElement && it.parentElement.closest('ytd-rich-item-renderer, ytd-video-renderer')) continue;
    if (it.closest('ytd-reel-shelf-renderer, ytd-rich-shelf-renderer[is-shorts], ytm-shorts-lockup-view-model')) continue;
    const a = it.querySelector('a[href*="/watch?v="]');
    if (!a) continue;
    const m = a.href.match(/[?&]v=([\w-]{11})/);
    if (!m || seen.has(m[1])) continue;
    const txt = it.innerText || '';
    if (it.querySelector('ytd-ad-slot-renderer, ytd-in-feed-ad-layout-renderer, [class*="ad-badge"]')) continue;
    const live = !!it.querySelector('.badge-style-type-live-now-alternate, [aria-label="LIVE"], [aria-label="TRỰC TIẾP"]');
    const tEl = it.querySelector('#video-title, a#video-title-link, .yt-lockup-metadata-view-model__title, ' +
                                 '.yt-lockup-metadata-view-model-wiz__title, h3 a, h3');
    let title = ((tEl && (tEl.getAttribute('title') || tEl.textContent)) || a.getAttribute('title') ||
                 a.getAttribute('aria-label') || '').replace(/\s+/g, ' ').trim();
    const chA = it.querySelector('ytd-channel-name a, a[href^="/@"], a[href*="youtube.com/@"], a[href*="/channel/"]');
    const dEl = it.querySelector('ytd-thumbnail-overlay-time-status-renderer #text, badge-shape .badge-shape-wiz__text, ' +
                                 '.yt-badge-shape__text, .badge-shape__text, #time-status #text');
    const lines = txt.split('\n').map(s => s.trim()).filter(Boolean);
    const viewLine = lines.find(s => /(lượt xem|views?|N người xem|watching)/i.test(s)) || '';
    seen.add(m[1]);
    out.push({video_id: m[1], title, live,
              channel: chA ? chA.textContent.replace(/\s+/g, ' ').trim() : '',
              channel_url: chA ? chA.href : '',
              duration_text: dEl ? dEl.textContent.trim() : '', views_text: viewLine});
  }
  return out;
}"""

INFO_JS = r"""() => {
  const pr = window.ytInitialPlayerResponse || {};
  const vd = pr.videoDetails || {};
  const mf = (pr.microformat || {}).playerMicroformatRenderer || {};
  const likeBtn = document.querySelector('like-button-view-model button, #segmented-like-button button, ' +
                                         'ytd-toggle-button-renderer#like-button button');
  const desc = vd.shortDescription ||
    (document.querySelector('#description-inline-expander, ytd-text-inline-expander, #description') || {}).innerText || '';
  const h1 = document.querySelector('h1.ytd-watch-metadata, h1 yt-formatted-string, #title h1');
  const ch = document.querySelector('ytd-video-owner-renderer ytd-channel-name a, #owner #channel-name a');
  return {video_id: vd.videoId || '', title: vd.title || (h1 ? h1.textContent.trim() : document.title),
          channel: vd.author || (ch ? ch.textContent.trim() : ''), channel_id: vd.channelId || '',
          channel_url: ch ? ch.href : '', duration: parseInt(vd.lengthSeconds || '0', 10),
          views: parseInt(vd.viewCount || '0', 10), description: desc, live: !!vd.isLiveContent && !!vd.isLive,
          keywords: vd.keywords || [], category: mf.category || '',
          like_label: likeBtn ? (likeBtn.getAttribute('aria-label') || likeBtn.innerText || '') : '',
          has_captions: !!(pr.captions && pr.captions.playerCaptionsTracklistRenderer)};
}"""

CAPTIONS_JS = r"""async (prefer) => {
  const pr = window.ytInitialPlayerResponse || {};
  const tracks = (((pr.captions || {}).playerCaptionsTracklistRenderer || {}).captionTracks) || [];
  if (!tracks.length) return {err: 'Video không có phụ đề'};
  const rank = t => { const l = (t.languageCode || '').toLowerCase(); const i = prefer.indexOf(l.split('-')[0]);
    return (t.kind === 'asr' ? 10 : 0) + (i < 0 ? 5 : i); };
  const t = [...tracks].sort((a, b) => rank(a) - rank(b))[0];
  try {
    const r = await fetch(t.baseUrl + (t.baseUrl.includes('fmt=') ? '' : '&fmt=json3'), {credentials: 'include'});
    const txt = await r.text();
    if (!txt) return {err: 'Phụ đề trả về rỗng', lang: t.languageCode};
    const j = JSON.parse(txt);
    const segs = (j.events || []).filter(e => e.segs).map(e => ({t: (e.tStartMs || 0) / 1000,
      s: e.segs.map(x => x.utf8 || '').join('').replace(/\s+/g, ' ').trim()})).filter(x => x.s);
    return {lang: t.languageCode, kind: t.kind === 'asr' ? 'phụ đề tự động' : 'phụ đề', segs};
  } catch (e) { return {err: 'Không đọc được phụ đề: ' + e, lang: t.languageCode}; }
}"""

PANEL_JS = r"""() => [...document.querySelectorAll('ytd-transcript-segment-renderer, transcript-segment-view-model')]
  .map(s => ({ts: ((s.querySelector('.segment-timestamp, .ytwTranscriptSegmentViewModelTimestamp') || {}).textContent || '').trim(),
              s: ((s.querySelector('.segment-text, yt-formatted-string, span[role=text]') || {}).textContent || '')
                 .replace(/\s+/g, ' ').trim()}))
  .filter(x => x.s)"""

LIKE_SEL = ("like-button-view-model button, #segmented-like-button button, "
            "ytd-toggle-button-renderer#like-button button, ytd-menu-renderer #top-level-buttons-computed "
            "ytd-toggle-button-renderer:first-child button")
DISLIKE_SEL = ("dislike-button-view-model button, #segmented-dislike-button button, "
               "ytd-toggle-button-renderer#dislike-button button")


def parse_count(text):
    """'1,2 Tr lượt xem' / '45 N lượt xem' / '1.2M views' / '3,4K' / '12.345 lượt xem' -> số."""
    t = (text or "").lower().replace(" ", " ")
    m = re.search(r"(\d+(?:[.,]\d+)*)\s*(tr|triệu|n|nghìn|ngàn|t|tỷ|k|m|b)?\b", t)
    if not m:
        return 0
    num, unit = m.group(1), (m.group(2) or "")
    mult = {"k": 1e3, "n": 1e3, "nghìn": 1e3, "ngàn": 1e3, "m": 1e6, "tr": 1e6, "triệu": 1e6,
            "b": 1e9, "t": 1e9, "tỷ": 1e9}.get(unit, 1)
    if unit:   # số thập phân: 1,2 / 1.2
        val = float(num.replace(",", ".")) if num.count(",") + num.count(".") == 1 else float(re.sub(r"[.,]", "", num))
    else:      # số nguyên có dấu ngăn cách nghìn: 12.345 / 12,345
        val = float(re.sub(r"[.,]", "", num))
    return int(val * mult)


def parse_dur(text):
    parts = [p for p in re.findall(r"\d+", text or "")]
    if not parts or not re.search(r"\d+:\d\d", text or ""):
        return 0
    sec = 0
    for p in parts[-3:]:
        sec = sec * 60 + int(p)
    return sec


def _ts(text):
    return parse_dur(text) if ":" in (text or "") else 0


def _channel_key(url):
    m = re.search(r"/(@[\w.\-%]+)|/channel/(UC[\w-]{22})", url or "")
    return (m.group(1) or m.group(2)).lower() if m else ""


# ============================================================ luồng chạy
class Worker(threading.Thread):
    """Phiên làm việc: giữ kết nối trình duyệt, nhận lệnh: analyze / like / dislike / open / close_tabs / quit."""

    def __init__(self, cfg, events, db, ctx_factory=None):
        super().__init__(daemon=True)
        self.cfg = cfg
        self.ev = events
        self.db = db
        self.cmds = queue.Queue()
        self.ctx_factory = ctx_factory
        self.run_ev = threading.Event()   # đặt = đang chạy (không tạm dừng)
        self.run_ev.set()
        self.stop_ev = threading.Event()
        self.next_ev = threading.Event()  # chế độ từng video: bạn bấm "Tiếp" mới sang video sau
        self.busy = False
        self.tabs = {}        # video_id -> page
        self.ctx = None
        self._browsers = None
        self._who = None
        self._cur = None
        self.run_id = None

    # ------------------------------------------------------------ gửi về giao diện
    def emit(self, kind, **data):
        self.ev.put((kind, data))

    def say(self, msg, level="info"):
        self.emit("log", msg=msg, level=level)
        getattr(log, "error" if level == "err" else "warning" if level == "warn" else "info")(msg)

    def status(self, text):
        self.emit("status", text=text)

    # ------------------------------------------------------------ điều khiển
    def pause(self):
        self.run_ev.clear()
        self.emit("state", state="paused")
        self.say("⏸ Tạm dừng – bấm TIẾP TỤC để chạy tiếp.", "warn")

    def resume(self):
        self.run_ev.set()
        self.emit("state", state="running" if self.busy else "idle")
        self.say("▶ Tiếp tục.")

    def stop(self):
        self.stop_ev.set()
        self.run_ev.set()
        self.next_ev.set()

    def next(self):
        self.next_ev.set()

    def _wait_next(self, done_title, next_title):
        """Chờ bạn bấm 'Tiếp' (xem / đọc kết quả video vừa xong) rồi mới mở video sau."""
        self.next_ev.clear()
        self.emit("await", waiting=True)
        self.status(f"Xong: {done_title[:50]} – bấm TIẾP để mở video sau: {next_title[:50]}")
        self.say("⏸ Chờ bạn bấm TIẾP để sang video sau.", "warn")
        try:
            while not self.next_ev.is_set():
                self.checkpoint()
                time.sleep(0.25)
            self.checkpoint()
        finally:
            self.emit("await", waiting=False)

    def _open_tab(self, c, i, total):
        self.status(f"Mở tab {i}/{total}: {c['title'][:60]}")
        try:
            pg = self._new_tab(c["url"])
            pg.wait_for_timeout(2500)
            self._pause_video(pg)
            self.tabs[c["video_id"]] = pg
            self.db.update(c["row_id"], status="Đã mở tab")
        except Exception as e:
            self.db.update(c["row_id"], status="Lỗi mở tab", error=str(e)[:300])
            self.say(f"Không mở được {c['url']}: {str(e).splitlines()[0][:120]}", "warn")
        self.emit("row", row_id=c["row_id"])

    def checkpoint(self):
        """Gọi giữa các bước: xử lý lệnh tương tác đang chờ, dừng khi bị tạm dừng / bị STOP."""
        self._drain(block=False)
        while not self.run_ev.is_set() and not self.stop_ev.is_set():
            self._drain(block=False)
            time.sleep(0.25)
        if self.stop_ev.is_set():
            raise Stopped()

    def send(self, *cmd):
        self.cmds.put(cmd)

    # ------------------------------------------------------------ vòng lặp chính
    def run(self):
        try:
            while True:
                cmd = self.cmds.get()
                if cmd[0] == "quit":
                    break
                self._do_cmd(cmd)
        finally:
            self._close_browser()
            self.emit("state", state="closed")

    def _drain(self, block=False):
        while True:
            try:
                cmd = self.cmds.get(block=block, timeout=0.1 if block else None)
            except queue.Empty:
                return
            if cmd[0] == "analyze":   # không chạy chồng 2 lượt
                self.say("Đang có lượt phân tích chạy – bỏ qua lệnh START mới.", "warn")
                continue
            if cmd[0] == "quit":
                self.stop_ev.set()
                self.cmds.put(cmd)
                return
            self._do_cmd(cmd)

    def _do_cmd(self, cmd):
        name = cmd[0]
        try:
            if name == "analyze":
                self._analyze(cmd[1])
            elif name in ("like", "dislike"):
                self._react(cmd[1], name)
            elif name == "open":
                self._open_for_comment(cmd[1])
            elif name == "watch":
                self._watch(cmd[1])
            elif name == "close_tabs":
                self._close_tabs()
        except Stopped:
            self.say("⏹ Đã dừng theo yêu cầu.", "warn")
        except BaseException as e:   # SystemExit từ browser.py (không thấy trình duyệt...) cũng báo ra log
            msg = str(e) or type(e).__name__
            self.say(f"❌ {msg}", "err")
            log.error(traceback.format_exc())
            self.emit("error", msg=msg)

    # ------------------------------------------------------------ trình duyệt
    def _key(self, who):
        return (str((self.cfg or {}).get("_path") or ""), who)

    def _alive(self):
        try:
            br = self.ctx.browser
            return br is None or br.is_connected()
        except Exception:
            return False

    def _context(self, who):
        """Kết nối trình duyệt của ĐÚNG kênh (file kênh) + ĐÚNG tài khoản; đổi kênh/tài khoản thì kết nối lại."""
        if self.ctx is not None and self._cur == self._key(who) and self._alive():
            return self.ctx
        self._close_browser()
        if self.ctx_factory:
            self.ctx = self.ctx_factory(who)
        else:
            from browser import Browsers
            self._browsers = Browsers(self.cfg)
            self._browsers.__enter__()
            self.ctx = self._browsers.context(who)
            # KHÔNG vào Studio / trang kênh để kiểm tra lại: trình duyệt riêng của kênh này đã đăng nhập và chọn đúng
            # kênh từ bước kéo trước -> đi thẳng ra Trang chủ YouTube
            self._browsers._chosen.add(self._browsers._who(who))
            try:
                self._browsers.page(who)   # cửa sổ đang ở ngoài màn hình (chế độ ẩn) -> đưa về để bạn thấy các tab
            except Exception:
                pass
        self._who = who
        self._cur = self._key(who)
        return self.ctx

    def _close_browser(self):
        self.tabs = {}
        if self._browsers is not None:
            try:
                self._browsers.__exit__(None, None, None)   # chỉ ngắt kết nối, cửa sổ trình duyệt vẫn mở
            except Exception:
                pass
        self._browsers = None
        self.ctx = None

    def _new_tab(self, url=None):
        pg = self.ctx.new_page()
        try:
            pg.on("dialog", lambda d: d.dismiss())
        except Exception:
            pass
        if url:
            pg.goto(url, wait_until="domcontentloaded", timeout=45000)
        return pg

    @staticmethod
    def _pause_video(pg):
        try:
            pg.evaluate("() => { const v = document.querySelector('video'); if (v) { v.pause(); v.muted = true; } }")
        except Exception:
            pass

    # ------------------------------------------------------------ lượt phân tích
    def _analyze(self, st):
        self.stop_ev.clear()
        self.run_ev.set()
        self.busy = True
        self.emit("state", state="running")
        done_note = ""
        try:
            if st.get("provider") == pt_ai.OLLAMA:
                self.status("Kiểm tra Ollama...")
                why = pt_ai.ollama_ready(st.get("model") or pt_ai.PROVIDERS[pt_ai.OLLAMA], self.say)
                if why:
                    raise RuntimeError(why)
                self.say(f"Ollama sẵn sàng (model {st.get('model') or pt_ai.PROVIDERS[pt_ai.OLLAMA]}).", "ok")
            self.status("Đang mở trình duyệt...")
            self._context(st["account"])
            self.checkpoint()
            kws = list(dict.fromkeys(k.strip().lower() for k in st.get("keywords", []) if k.strip()))
            user_kws = list(kws)
            titles = []
            target_lang = st.get("video_lang", "auto")
            own = _channel_key(st.get("target_url", ""))
            if st.get("target_url"):
                self.status("Đọc chủ đề của kênh mục tiêu...")
                titles = self._target_titles(st["target_url"])
                if titles:
                    auto = pt_ai.keywords_from_titles(titles)
                    if st.get("auto_keywords", True):
                        kws += [k for k in auto if k not in kws]
                    langs = [pt_ai.detect_lang(t) for t in titles]
                    langs = [x for x in langs if x]
                    if target_lang == "auto" and langs:
                        target_lang = max(set(langs), key=langs.count)
                    self.say(f"Kênh mục tiêu: {len(titles)} video · ngôn ngữ chính: "
                             f"{pt_ai.LANG_NAMES.get(target_lang if target_lang != 'auto' else '', '?')} · "
                             f"từ khóa: {', '.join(kws[:15])}")
                else:
                    self.say("Không đọc được danh sách video của kênh mục tiêu – dùng từ khóa bạn điền.", "warn")
            if not kws:
                raise RuntimeError("Chưa có từ khóa chủ đề. Hãy điền Từ khóa chủ đề hoặc link Kênh mục tiêu.")
            if target_lang == "auto":
                target_lang = ""
            st["_kws"], st["_lang"] = kws, target_lang
            st["_prof"] = pt_ai.topic_profile(titles, user_kws)     # hồ sơ chủ đề để lọc CHẶT
            st["_samples"] = titles[:12]
            self.run_id = self.db.new_run(st["account"], st.get("target_url", ""), kws,
                                          {k: v for k, v in st.items() if k != "key" and not k.startswith("_")})
            self.emit("run", run_id=self.run_id)

            cands = self._find_candidates(st, own)
            if not cands:
                raise RuntimeError("Không tìm được video phù hợp trên Trang chủ. Thử thêm từ khóa, hạ 'Độ liên quan "
                                   "tối thiểu', hoặc bật 'Bổ sung bằng tìm kiếm'.")
            rows = []
            for c in cands:
                c["status"] = "Chờ mở tab"
                c["row_id"] = self.db.add_video(self.run_id, c)
                rows.append(c)
                self.emit("row", row_id=c["row_id"])
            total = len(rows)
            self.emit("progress", done=0, total=total * 2)

            step = bool(st.get("step_mode"))
            title_only = bool(st.get("title_only"))
            if not step and not title_only:   # mở mỗi video 1 tab riêng (chế độ từng video: mở lần lượt ở vòng dưới)
                for i, c in enumerate(rows, 1):
                    self.checkpoint()
                    self._open_tab(c, i, total)
                    self.emit("progress", done=i, total=total * 2)

            # lần lượt chuyển tab và phân tích
            prev = self.db.recent_comments()
            ok = 0
            for i, c in enumerate(rows, 1):
                self.checkpoint()
                if step and i > 1:
                    self._wait_next(rows[i - 2]["title"], c["title"])
                if step and not title_only:
                    self._open_tab(c, i, total)
                    self.emit("progress", done=total + i - 1, total=total * 2)
                pg = None if title_only else self.tabs.get(c["video_id"])
                if pg is None and not title_only:
                    continue
                self.status(f"Phân tích {i}/{total}: {c['title'][:60]}")
                self.db.update(c["row_id"], status="Đang phân tích")
                self.emit("row", row_id=c["row_id"])
                try:
                    res = self._analyze_title(c, st, prev) if title_only else self._analyze_tab(pg, c, st, prev)
                    ok += 1
                    prev = (res.get("comments") or []) + prev
                    if res.get("off_topic"):
                        self.say(f"↷ {c['title'][:60]} → AI thấy KHÁC chủ đề kênh – bỏ qua, không đề xuất Like", "warn")
                    else:
                        self.say(f"✅ {c['title'][:60]} → {res['score']}/100 · {res['category']} · đề xuất "
                                 f"{res['recommendation']}", "ok")
                except Stopped:
                    self.db.update(c["row_id"], status="Đã dừng")
                    self.emit("row", row_id=c["row_id"])
                    raise
                except Exception as e:
                    self.db.update(c["row_id"], status="Lỗi phân tích", error=str(e)[:500])
                    self.say(f"❌ {c['title'][:50]}: {e}", "err")
                    log.error(traceback.format_exc())
                self.emit("row", row_id=c["row_id"])
                self.emit("progress", done=total + i, total=total * 2)
            done_note = f"Phân tích xong {ok}/{total} video"
            self.say(f"🏁 {done_note}. Chọn từng dòng để xem lý do, bình luận và xác nhận tương tác.", "ok")
        except Stopped:
            done_note = "Đã dừng"
            self.say("⏹ Đã dừng lượt phân tích.", "warn")
        except BaseException as e:
            done_note = f"Lỗi: {e}"
            self.say(f"❌ {e}", "err")
            log.error(traceback.format_exc())
        finally:
            if self.run_id:
                self.db.finish_run(self.run_id, done_note)
            self.busy = False
            self.status(done_note or "Xong.")
            self.emit("state", state="idle")
            self.emit("done", note=done_note)

    # ------------------------------------------------------------ kênh mục tiêu
    _TITLES = {}

    def _target_titles(self, url):
        """Tiêu đề video của kênh mục tiêu – hỏi nền (KHÔNG mở tab trên kênh), nhớ trong phiên làm việc."""
        base = re.sub(r"[?#].*$", "", url.strip()).rstrip("/")
        base = re.sub(r"/(videos|featured|streams|shorts|playlists|community|about)$", "", base)
        if base in Worker._TITLES:
            return Worker._TITLES[base]
        titles = []
        import ytinfo
        for get in (ytinfo._get, lambda u: ytinfo._browser_get(self.ctx.pages[0] if self.ctx.pages else
                                                              self.ctx.new_page(), u)):
            try:
                _st, html = get(base + "/videos")
                titles = _titles_from_html(html)
            except Exception:
                titles = []
            if titles:
                break
        if titles:
            Worker._TITLES[base] = titles
        return titles

    # ------------------------------------------------------------ tìm video
    def _collect(self, pg, rounds=6):
        found = {}
        for _ in range(rounds):
            self.checkpoint()
            for it in pg.evaluate(LIST_JS) or []:
                found.setdefault(it["video_id"], it)
            pg.mouse.wheel(0, 2200)
            pg.wait_for_timeout(1200)
        return list(found.values())

    def _filter(self, items, st, own, taken):
        seen = self.db.seen_ids(int(st.get("skip_days", 30))) if st.get("skip_days", 30) else set()
        out = []
        drop = getattr(self, "_drop", None)
        if drop is None:
            drop = self._drop = {"lang": [], "topic": []}
        for it in items:
            vid = it["video_id"]
            title = it.get("title") or ""
            why = None
            if vid in taken:
                why = "trùng"
            elif vid in seen:
                why = "đã phân tích gần đây"
            elif it.get("live"):
                why = "đang phát trực tiếp"
            elif own and own in (it.get("channel_url") or "").lower():
                why = "video của chính kênh mục tiêu"
            if why:
                continue
            dur = parse_dur(it.get("duration_text"))
            if dur and dur < 60:
                continue   # Shorts / video quá ngắn
            if not dur or re.search(r"24\s*/\s*7|\blive\b|trực tiếp|livestream", title, re.I):
                continue   # đang phát trực tiếp / phát 24/7 / sắp công chiếu: không có nội dung cố định để chấm
            lang = pt_ai.detect_lang(title)
            mixed = pt_ai.foreign_lang(title, st["_lang"])
            if (st["_lang"] and lang and lang != st["_lang"]) or mixed:
                drop["lang"].append(title)
                continue
            ok_topic, _why = pt_ai.topic_match(title, st.get("_prof"))
            if not ok_topic:
                drop["topic"].append(title)
                continue
            rel = pt_ai.relevance(title, st["_kws"], title)
            if lang and st["_lang"] and lang == st["_lang"]:
                rel = min(100.0, rel + 10)
            if rel < float(st.get("min_relevance", 20)):
                continue
            out.append(dict(video_id=vid, url=f"https://www.youtube.com/watch?v={vid}", title=title,
                            channel=it.get("channel", ""), channel_url=it.get("channel_url", ""),
                            duration=dur, views=parse_count(it.get("views_text")), lang=lang, relevance=rel))
        out.sort(key=lambda x: (-x["relevance"], -x["views"]))
        return out

    def _find_candidates(self, st, own):
        want = max(1, min(10, int(st.get("count", 5))))
        taken = {}
        self.status("Mở Trang chủ YouTube và tìm video cùng chủ đề...")
        home = self._new_tab("https://www.youtube.com/")
        try:
            home.wait_for_timeout(4000)
            if home.locator("a[href*='accounts.google.com/ServiceLogin'], ytd-button-renderer a[href*='ServiceLogin']").count():
                self.say("⚠️ Trình duyệt này chưa đăng nhập YouTube – Trang chủ sẽ không theo sở thích của kênh.", "warn")
            items = self._collect(home, rounds=int(st.get("scroll_rounds", 6)))
            self.say(f"Trang chủ: đọc được {len(items)} video.")
            for c in self._filter(items, st, own, taken)[:want]:
                c["source"] = "Trang chủ"
                taken[c["video_id"]] = c
            if len(taken) < want and st.get("search_fallback", True):
                kws = st["_kws"]
                queries = [" ".join(kws[:3]), " ".join(kws[1:4]), " ".join(kws[:2])]
                for q in [q for q in dict.fromkeys(queries) if q.strip()]:
                    if len(taken) >= want:
                        break
                    self.status(f"Trang chủ chưa đủ {want} video – tìm thêm: {q}")
                    home.goto("https://www.youtube.com/results?search_query=" + _q(q) + "&sp=EgIQAQ%253D%253D",
                              wait_until="domcontentloaded")
                    home.wait_for_timeout(3500)
                    for c in self._filter(self._collect(home, rounds=3), st, own, taken)[:want - len(taken)]:
                        c["source"] = f"Tìm kiếm: {q}"
                        taken[c["video_id"]] = c
            found = list(taken.values())
            d = getattr(self, "_drop", None) or {}
            if d.get("lang") or d.get("topic"):
                self.say(f"Đã loại {len(d.get('lang', []))} video khác ngôn ngữ và {len(d.get('topic', []))} video "
                         f"khác chủ đề kênh" + (f" (vd: {(d.get('topic') or d.get('lang'))[0][:50]})"
                                                  if (d.get('topic') or d.get('lang')) else ""), "warn")
            self._drop = None
            self.say(f"Chọn {len(found)} video: " + " | ".join(f"{c['title'][:40]} ({c['relevance']:.0f})"
                                                           for c in found))
            return found
        finally:
            try:
                home.close()
            except Exception:
                pass

    # ------------------------------------------------------------ phân tích 1 tab
    def _analyze_tab(self, pg, c, st, prev):
        try:
            pg.bring_to_front()
        except Exception:
            pass
        pg.wait_for_timeout(1500)
        self._pause_video(pg)
        info = pg.evaluate(INFO_JS) or {}
        for _ in range(6):   # trang chưa tải xong -> chờ thêm (không tải lại trang)
            if info.get("title"):
                break
            pg.wait_for_timeout(1500)
            info = pg.evaluate(INFO_JS) or {}
        info.setdefault("title", c["title"])
        likes = parse_count(re.sub(r"[^\d.,\sA-Za-zÀ-ỹ]", " ", info.get("like_label") or ""))
        dur = int(info.get("duration") or c.get("duration") or 0)
        # khoảng phân tích: từ phút X, dài 6–10 phút (video ngắn hơn -> lùi lại cho vừa)
        win = max(60, int(st.get("win_len", 8)) * 60)
        a = max(0, int(st.get("win_from", 0)) * 60)
        if dur and a + win > dur:
            a = max(0, dur - win)
        b = a + win if not dur else min(dur, a + win)
        self.checkpoint()
        if st.get("title_only"):   # chỉ chấm theo tiêu đề: không đọc lời thoại
            text, source = "", "chỉ tiêu đề"
        else:
            text, source = self._transcript(pg, a, b, st)
        rel = pt_ai.relevance(f"{info.get('title', '')} {info.get('description', '')[:1500]} "
                              f"{' '.join(info.get('keywords') or [])}", st["_kws"], info.get("title", ""))
        data = dict(title=info.get("title"), channel=info.get("channel") or c.get("channel"),
                    description=info.get("description", ""), duration=dur, views=info.get("views") or c.get("views"),
                    likes=likes, transcript=text, source=source, relevance=rel,
                    window_label=f"{a // 60}:{a % 60:02d}–{b // 60}:{b % 60:02d}")
        self.db.update(c["row_id"], title=data["title"], channel=data["channel"], duration=dur,
                       views=int(data["views"] or 0), likes=likes, relevance=rel, window_from=None if st.get("title_only") else a, window_to=None if st.get("title_only") else b,
                       transcript_source=source, transcript_chars=len(text), status="AI đang chấm điểm")
        self.emit("row", row_id=c["row_id"])
        self.checkpoint()
        ai_set = dict(provider=st.get("provider"), model=st.get("model"), key=st.get("key"),
                      comment_lang=st.get("comment_lang", "English"), topic=", ".join(st["_kws"][:10]),
                      samples=st.get("_samples") or [],
                      title_only=bool(st.get("title_only")))
        res = pt_ai.analyze(data, ai_set, prev)
        status = "Khác chủ đề – bỏ qua" if res.get("off_topic") else \
            "Chờ duyệt" if res["recommendation"] in ("Like", "Dislike") else "Đã phân tích"
        self.db.update(c["row_id"], topic=res["topic"], score=res["score"], category=res["category"],
                       recommendation=res["recommendation"], reasons=res["reasons"],
                       dislike_basis=res["dislike_basis"], comments=res["comments"],
                       comment_lang=st.get("comment_lang", "English"), ai_provider=res.get("ai", ""),
                       status=status, analyzed_at=time.strftime("%Y-%m-%d %H:%M:%S"), error="")
        return res

    def _analyze_title(self, c, st, prev):
        """Chỉ chấm theo tiêu đề: dùng tiêu đề / kênh / lượt xem đọc được trên Trang chủ – KHÔNG mở trang video."""
        data = dict(title=c.get("title"), channel=c.get("channel"), description="", duration=c.get("duration") or 0,
                    views=c.get("views") or 0, likes=0, transcript="", source="chỉ tiêu đề",
                    relevance=c.get("relevance", 0), window_label="")
        self.db.update(c["row_id"], transcript_source="chỉ tiêu đề", status="AI đang chấm điểm")
        self.emit("row", row_id=c["row_id"])
        self.checkpoint()
        ai_set = dict(provider=st.get("provider"), model=st.get("model"), key=st.get("key"),
                      comment_lang=st.get("comment_lang", "English"), topic=", ".join(st["_kws"][:10]),
                      samples=st.get("_samples") or [],
                      title_only=True)
        res = pt_ai.analyze(data, ai_set, prev)
        status = "Khác chủ đề – bỏ qua" if res.get("off_topic") else \
            "Chờ duyệt" if res["recommendation"] in ("Like", "Dislike") else "Đã phân tích"
        self.db.update(c["row_id"], topic=res["topic"], score=res["score"], category=res["category"],
                       recommendation=res["recommendation"], reasons=res["reasons"],
                       dislike_basis=res["dislike_basis"], comments=res["comments"],
                       comment_lang=st.get("comment_lang", "English"), ai_provider=res.get("ai", ""),
                       status=status, analyzed_at=time.strftime("%Y-%m-%d %H:%M:%S"), error="")
        return res

    def _transcript(self, pg, a, b, st):
        """Chữ của đoạn [a, b) giây: ưu tiên phụ đề (bản thủ công > tự động), dự phòng bảng 'Bản chép lời'."""
        prefer = [x for x in (st.get("_lang") or "", "en", "tl", "ceb", "ilo", "vi") if x]
        prefer = [{"tl": "fil"}.get(x, x) for x in prefer] + ["tl"]
        try:
            cap = pg.evaluate(CAPTIONS_JS, prefer) or {}
        except Exception as e:
            cap = {"err": str(e)[:120]}
        segs = cap.get("segs") or []
        source = cap.get("kind", "")
        if not segs:
            segs, source = self._transcript_panel(pg), "bản chép lời"
            if not segs:
                why = cap.get("err") or "không có"
                self.say(f"   không lấy được phụ đề ({why}) – AI chấm theo tiêu đề, mô tả", "warn")
                return "", "không có phụ đề"
        ts = lambda x: f"[{int(x['t']) // 60}:{int(x['t']) % 60:02d}] {x['s']}"
        sel = [x for x in segs if a <= x["t"] < b]
        if not sel:   # mốc không khớp (vd video ngắn) -> lấy đoạn đầu cho đủ
            sel = segs[:400]
        part = [x["s"] for x in sel]
        text = "\n".join(ts(x) for x in sel)   # kèm mốc thời gian để AI dẫn đúng đoạn khi nhận xét
        if cap.get("lang"):
            source += f" ({cap['lang']})"
        self.say(f"   {source}: {len(part)} câu trong khoảng {a // 60}:{a % 60:02d}–{b // 60}:{b % 60:02d}")
        return text, source

    def _transcript_panel(self, pg):
        try:
            for sel in ("tp-yt-paper-button#expand", "#description-inline-expander #expand", "#expand"):
                loc = pg.locator(sel)
                if loc.count() and loc.first.is_visible():
                    loc.first.click(timeout=4000)
                    pg.wait_for_timeout(800)
                    break
            btn = pg.locator("ytd-video-description-transcript-section-renderer button").or_(
                pg.get_by_role("button", name=re.compile(r"Hiện bản chép lời|Show transcript|Bản chép lời|Transcript",
                                                         re.I)))
            if not btn.count():
                return []
            btn.first.click(timeout=6000)
            for _ in range(20):
                pg.wait_for_timeout(500)
                rows = pg.evaluate(PANEL_JS) or []
                if rows:
                    return [{"t": _ts(r["ts"]), "s": r["s"]} for r in rows]
        except Exception:
            pass
        return []

    # ------------------------------------------------------------ tương tác (chỉ khi bạn xác nhận)
    def _use_row_account(self, row):
        """Like / Dislike / bình luận bằng ĐÚNG tài khoản của lượt đã phân tích video đó."""
        st = self.db.run_settings(row.get("run_id"))
        who = st.get("account") or self._who or "weak"
        path = st.get("job_path")
        if path and path != (self.cfg or {}).get("_path") and os.path.exists(path):
            import jobs
            self.cfg = dict(jobs.load(path), headless=False)
        if self.ctx is None and not (self.cfg or {}).get("strong_channel") and not self.ctx_factory:
            raise RuntimeError("Chưa biết dùng trình duyệt của kênh nào – hãy bấm START một lượt trước.")
        return who

    def _tab_for(self, row):
        who = self._use_row_account(row)
        if self._cur != self._key(who) or not self._alive():
            self._context(who)
        pg = self.tabs.get(row["video_id"])
        try:
            if pg is not None and not pg.is_closed():
                return pg
        except Exception:
            pass
        pg = self._new_tab(row["url"])
        pg.wait_for_timeout(2000)
        self.tabs[row["video_id"]] = pg
        return pg

    def _react(self, row_id, kind):
        row = self.db.get(row_id)
        if not row:
            return
        label = "Like" if kind == "like" else "Dislike"
        self.status(f"{label}: {row['title'][:60]}")
        pg = self._tab_for(row)
        try:
            pg.bring_to_front()
        except Exception:
            pass
        loc = pg.locator(LIKE_SEL if kind == "like" else DISLIKE_SEL)
        btn = None
        for _ in range(20):
            for i in range(loc.count()):
                if loc.nth(i).is_visible():
                    btn = loc.nth(i)
                    break
            if btn is not None:
                break
            pg.wait_for_timeout(500)
        if btn is None:
            raise RuntimeError(f"Không thấy nút {label} trên trang video.")
        if btn.get_attribute("aria-pressed") == "true":
            self.db.update(row_id, action=f"{label} (đã có sẵn)", action_at=time.strftime("%Y-%m-%d %H:%M:%S"),
                           status=f"Đã {label}")
            self.say(f"✅ Video đã được {label} từ trước: {row['title'][:60]}", "ok")
            self.emit("row", row_id=row_id)
            return
        btn.scroll_into_view_if_needed()
        btn.click(timeout=8000)
        pg.wait_for_timeout(2000)
        if btn.get_attribute("aria-pressed") != "true":
            raise RuntimeError(f"Đã bấm {label} nhưng YouTube chưa ghi nhận (tài khoản trong trình duyệt này có thể "
                               f"chưa đăng nhập).")
        self.db.update(row_id, action=label, action_at=time.strftime("%Y-%m-%d %H:%M:%S"), status=f"Đã {label}")
        self.say(f"✅ Đã {label}: {row['title'][:60]}", "ok")
        self.emit("row", row_id=row_id)

    def _watch(self, row_id):
        """Nút 'Xem video này': mở / đưa tab video lên trước để BẠN tự xem (tool không điều khiển video)."""
        row = self.db.get(row_id)
        if not row:
            return
        try:
            pg = self._tab_for(row)
        except RuntimeError:
            import webbrowser
            webbrowser.open(row["url"])
            self.say("Đã mở video bằng trình duyệt mặc định.", "warn")
            return
        try:
            pg.bring_to_front()
        except Exception:
            pass
        self.say(f"▶ Đã mở video để bạn xem: {row['title'][:60]}", "ok")

    def _open_for_comment(self, row_id):
        """Đưa tab video lên trước và mở ô viết bình luận – bạn tự dán (Ctrl+V) và bấm Bình luận."""
        row = self.db.get(row_id)
        if not row:
            return
        try:
            pg = self._tab_for(row)
        except RuntimeError:
            import webbrowser
            webbrowser.open(row["url"])
            self.say("Trình duyệt của tool chưa mở – đã mở video bằng trình duyệt mặc định.", "warn")
            return
        try:
            pg.bring_to_front()
        except Exception:
            pass
        for _ in range(8):
            pg.mouse.wheel(0, 900)
            pg.wait_for_timeout(700)
            ph = pg.locator("ytd-comments #simplebox-placeholder, #simplebox-placeholder")
            if ph.count() and ph.first.is_visible():
                ph.first.scroll_into_view_if_needed()
                ph.first.click(timeout=5000)
                self.say("✍ Đã mở ô bình luận trên tab video – dán (Ctrl+V) bình luận đã sao chép rồi tự bấm Bình luận.",
                         "ok")
                return
        self.say("Đã mở tab video – kéo xuống phần bình luận để dán bình luận.", "warn")

    def _close_tabs(self):
        for pg in list(self.tabs.values()):
            try:
                pg.close()
            except Exception:
                pass
        self.tabs = {}
        self.say("Đã đóng các tab video của lượt phân tích.")


def _titles_from_html(html):
    """Tiêu đề video trong dữ liệu ytInitialData của trang kênh (không cần mở trình duyệt)."""
    import json
    m = re.search(r"ytInitialData\s*=\s*\{", html or "")
    if not m:
        return []
    try:
        data = json.JSONDecoder().raw_decode(html, m.end() - 1)[0]
    except ValueError:
        return []
    out = []

    def walk(o):
        if isinstance(o, dict):
            for k in ("videoRenderer", "gridVideoRenderer", "lockupViewModel"):
                if k in o and isinstance(o[k], dict):
                    v = o[k]
                    t = v.get("title") or {}
                    txt = (t.get("simpleText") or "".join(r.get("text", "") for r in t.get("runs", []))) \
                        if isinstance(t, dict) else ""
                    if not txt:
                        md = (v.get("metadata") or {}).get("lockupMetadataViewModel") or {}
                        txt = ((md.get("title") or {}).get("content")) or ""
                    if txt:
                        out.append(txt.strip())
            for val in o.values():
                walk(val)
        elif isinstance(o, list):
            for val in o:
                walk(val)
    walk(data)
    return list(dict.fromkeys(out))


def _q(text):
    import urllib.parse
    return urllib.parse.quote_plus(text)
