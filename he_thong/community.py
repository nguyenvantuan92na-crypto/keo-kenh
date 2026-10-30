"""
Tương tác bình luận ở trang CỘNG ĐỒNG của YouTube Studio (Studio → Cộng đồng → Bình luận).

Một trang duy nhất có bình luận của MỌI video trên kênh -> không phải mở từng video.
Với mỗi bình luận của khán giả:
  1. Xếp loại (cmt_lang): CHỈ bình luận KHEN / tích cực mới được tương tác.
     Câu hỏi, góp ý, chê, quảng cáo, bình luận không rõ ý -> KHÔNG đụng tới (ghi lại để bạn tự xem).
  2. Kênh đã trả lời rồi (đọc phần phản hồi) hoặc tool đã làm (binh_luan.db) -> bỏ qua, không trả lời trùng.
  3. Trả lời bằng câu cảm ơn đúng ngôn ngữ người viết, nhắc đúng ý họ khen, KHÔNG lặp lại câu đã dùng.
  4. Bấm THÍCH hoặc THẢ TIM – chỉ 1 trong 2, chọn theo nội dung (cmt_lang.react).
  5. Đọc lại đúng bình luận đó để xác nhận câu trả lời đã hiện / nút đã bật rồi mới ghi ✅.
"""
import random
import re

import cmt_lang
import thanks_bank
from replier import (DB, S_DONE_BEFORE, S_FAIL, S_HEARTED, S_PREVIEW, S_SENT, S_SKIP, _now, _norm, _words)
from studio import StepError

INBOX = "https://studio.youtube.com/channel/{cid}/comments/inbox"

# ---------------------------------------------------------------------------------------------- đọc trang
READ_JS = r"""(me) => {
  const vis = e => { if (!e) return false; const r = e.getBoundingClientRect(), s = getComputedStyle(e);
    return r.width > 0 && r.height > 0 && s.visibility !== 'hidden' && s.display !== 'none'; };
  const T = e => ((e && (e.innerText || e.textContent)) || '').replace(/\s+/g, ' ').trim();
  const lab = e => ((e && (e.getAttribute('aria-label') || e.getAttribute('title') || '')) || '').trim();
  const norm = s => (s || '').toLowerCase().replace(/^@/, '').replace(/\s+/g, ' ').trim();
  const mine = (me || []).map(norm).filter(Boolean);
  let threads = [...document.querySelectorAll('ytcp-comment-thread')];
  if (!threads.length)   // dự phòng: mỗi bình luận gốc (không nằm trong phần phản hồi)
    threads = [...document.querySelectorAll('ytcp-comment')].filter(c => !c.parentElement.closest('ytcp-comment'));
  const out = [];
  threads.forEach((th, i) => {
    th.setAttribute('data-keo-c', String(i));
    const top = th.matches('ytcp-comment') ? th : (th.querySelector('ytcp-comment') || th);
    const inTop = e => { const c = e.closest('ytcp-comment'); return !c || c === top; };
    const nameEl = [...top.querySelectorAll('#name, #author-text, .author-name, a#name, #author-name')].find(inTop);
    const author = T(nameEl).replace(/^@/, '@');
    const textEl = [...top.querySelectorAll('#content-text, .content-text')].find(inTop);
    const text = T(textEl);
    // video của bình luận (cột "Nội dung" bên phải)
    let vid = '', vtitle = '';
    for (const a of th.querySelectorAll('a[href]')) {
      const h = a.getAttribute('href') || '';
      const m = h.match(/\/video\/([\w-]{11})/) || h.match(/[?&]v=([\w-]{11})/) || h.match(/youtu\.be\/([\w-]{11})/);
      if (m) { vid = m[1]; if (!vtitle) vtitle = T(a); }
    }
    if (!vid) for (const im of th.querySelectorAll('img[src*="/vi/"]')) {
      const m = (im.getAttribute('src') || '').match(/\/vi\/([\w-]{11})\//); if (m) { vid = m[1]; break; } }
    const vt = th.querySelector('ytcp-comment-video-thumbnail #video-title, #video-title, .video-title');
    if (vt && T(vt)) vtitle = T(vt);
    let lc = '';
    for (const a of top.querySelectorAll('a[href*="lc="]')) {
      const m = (a.getAttribute('href') || '').match(/[?&]lc=([\w.-]+)/); if (m && inTop(a)) { lc = m[1]; break; } }
    // nút của BÌNH LUẬN GỐC (không lấy nút trong phần phản hồi)
    const btns = [...top.querySelectorAll('button, [role="button"], ytcp-icon-button, tp-yt-paper-icon-button, ' +
                                          'yt-icon-button, ytcp-button, ytcp-comment-button')]
                 .filter(b => inTop(b) && !b.parentElement.closest('[data-keo-btn]'));
    const idOf = b => (b.id || (b.closest('[id]') || {}).id || '').toLowerCase();
    let like = null, heart = null, reply = null;
    for (const b of btns) {
      const l = lab(b).toLowerCase(), t = T(b).toLowerCase(), id = idOf(b);
      if (!like && (id === 'like-button' || /^(thích|like|tôi thích|i like)\b/.test(l)) && !/không thích|dislike/.test(l + id))
        like = b;
      else if (!heart && (/heart/.test(id) || /tim|heart/.test(l)))
        heart = b;
      else if (!reply && (id === 'reply-button' || /^(phản hồi|trả lời|reply)$/.test(t) || /^(phản hồi|trả lời|reply)$/.test(l)))
        reply = b;
    }
    const mark = (b, k) => { if (b) b.setAttribute('data-keo-btn', k + '-' + i); };
    mark(like, 'like'); mark(heart, 'heart'); mark(reply, 'reply');
    const pressed = b => !!b && (b.getAttribute('aria-pressed') === 'true' ||
        !!b.closest('[aria-pressed="true"]') || /(^|\s)(active|iron-selected|style-default-active)(\s|$)/.test(b.className || ''));
    const liked = pressed(like) || /bỏ thích|unlike|đã thích/i.test(lab(like));
    const heartBox = top.querySelector('ytcp-comment-creator-heart, #creator-heart');
    const hearted = /bỏ|remove|un-?heart|đã thả/i.test(lab(heart)) || pressed(heart) ||
        !!(heartBox && heartBox.querySelector('[hearted], #hearted:not([hidden]), .hearted, img'));
    // phản hồi: "0 phản hồi" / "3 phản hồi" / "3 replies"
    let nRep = null;
    for (const e of th.querySelectorAll('button, [role="button"], ytcp-button, span, div')) {
      if (e.children.length > 3) continue;
      const m = T(e).match(/^(\d+)\s*(phản hồi|câu trả lời|replies|reply)$/i);
      if (m) { nRep = parseInt(m[1], 10); e.setAttribute('data-keo-rep', String(i)); break; }
    }
    const reps = [...th.querySelectorAll('ytcp-comment')].filter(c => c !== top);
    let ownerReplied = false;
    for (const r of reps) {
      const n = r.querySelector('#name, #author-text, .author-name, #author-name');
      const badge = r.querySelector('ytcp-author-comment-badge, #creator-badge, [is-creator], .creator');
      if ((n && mine.includes(norm(T(n)))) || (badge && vis(badge))) ownerReplied = true;
    }
    const topBadge = top.querySelector('ytcp-author-comment-badge, #creator-badge, [is-creator]');
    const isOwner = mine.includes(norm(author)) || (!!topBadge && vis(topBadge) && !!T(topBadge));
    out.push({i, author, text, vid, vtitle, lc, owner: isOwner, nRep, nLoaded: reps.length, ownerReplied,
              liked, hearted, hasLike: !!like, hasHeart: !!heart, hasReply: !!reply});
  });
  return out; }"""

ME_JS = r"""() => {
  const T = e => ((e && (e.innerText || e.textContent)) || '').replace(/\s+/g, ' ').trim();
  const out = [];
  for (const s of ['ytcp-navigation-drawer #entity-name', '#entity-name', 'ytcp-navigation-drawer .entity-name',
                   '#channel-title', 'ytcp-navigation-drawer #title'])
    { const e = document.querySelector(s); if (e && T(e)) { out.push(T(e)); break; } }
  return out; }"""


def _thread(page, i):
    return page.locator(f"[data-keo-c='{i}']").first


def _btn(page, kind, i):
    return page.locator(f"[data-keo-btn='{kind}-{i}']").first


def open_inbox(page, cid):
    page.goto(INBOX.format(cid=cid), wait_until="domcontentloaded")
    for _ in range(40):
        page.wait_for_timeout(500)
        if f"/channel/{cid}" not in (page.url or "") and "studio.youtube.com" in (page.url or ""):
            if re.search(r"/channel/UC[\w-]{22}", page.url or ""):
                raise StepError(f"Studio đang mở kênh khác ({page.url}) – tool DỪNG, không tương tác nhầm kênh.")
        if page.locator("ytcp-comment-thread, ytcp-comment").count():
            return True
        try:
            body = page.inner_text("body")[:4000]
        except Exception:
            body = ""
        if re.search(r"Không có bình luận|No comments|chưa có bình luận", body, re.I):
            return False
    if re.search(r"Rất tiếc|Oops|something went wrong", page.inner_text("body")[:4000], re.I):
        raise StepError("Studio báo lỗi khi mở trang Cộng đồng (thường do trình duyệt đang ở kênh khác).")
    return bool(page.locator("ytcp-comment-thread, ytcp-comment").count())


def load_more(page, want):
    """Cuộn danh sách bình luận tới khi đủ `want` bình luận (0 = hết) hoặc không tải thêm được."""
    last, same = -1, 0
    for _ in range(120):
        n = page.locator("ytcp-comment-thread").count() or page.locator("ytcp-comment").count()
        if want and n >= want:
            break
        if n == last:
            same += 1
            if same >= 3:
                break
        else:
            same = 0
        last = n
        try:
            page.locator("ytcp-comment-thread, ytcp-comment").last.scroll_into_view_if_needed(timeout=4000)
        except Exception:
            pass
        page.mouse.wheel(0, 3000)
        page.wait_for_timeout(1500)


def _expand_replies(page, i):
    """Mở phần phản hồi của 1 bình luận (để biết kênh đã trả lời chưa)."""
    b = page.locator(f"[data-keo-rep='{i}']").first
    try:
        if b.count() and b.is_visible():
            b.scroll_into_view_if_needed()
            b.click(timeout=5000)
            page.wait_for_timeout(2500)
            return True
    except Exception:
        pass
    return False


def _toggle(page, i, kind):
    """Bật THÍCH ('like') hoặc TIM ('heart') của bình luận gốc số i; đọc lại để xác nhận đã bật."""
    b = _btn(page, kind, i)
    if not b.count():
        raise StepError("không thấy nút " + ("Thích" if kind == "like" else "Thả tim"))
    b.scroll_into_view_if_needed()
    b.click(timeout=6000)
    for _ in range(10):
        page.wait_for_timeout(500)
        it = _read_one(page, i)
        if it and it["liked" if kind == "like" else "hearted"]:
            return True
    raise StepError("đã bấm " + ("Thích" if kind == "like" else "Thả tim") + " nhưng YouTube chưa ghi nhận")


def _read_one(page, i, me=None):
    try:
        for it in page.evaluate(READ_JS, me or []):
            if it["i"] == i:
                return it
    except Exception:
        pass
    return None


EDITOR_JS = r"""(i) => {
  // tìm ô viết câu trả lời đang mở trong đúng bình luận i + nút gửi của chính ô đó
  const vis = e => { if (!e) return false; const r = e.getBoundingClientRect(), s = getComputedStyle(e);
    return r.width > 0 && r.height > 0 && s.visibility !== 'hidden' && s.display !== 'none'; };
  const th = document.querySelector(`[data-keo-c='${i}']`);
  if (!th) return false;
  const ed = [...th.querySelectorAll('#contenteditable-textarea, [contenteditable="true"], textarea')].find(vis);
  if (!ed) return false;
  ed.setAttribute('data-keo-ed', String(i));
  let box = ed.closest('ytcp-commentbox') || ed.parentElement, sub = null;
  for (let k = 0; k < 8 && box && !sub; k++, box = box.parentElement) {
    sub = [...box.querySelectorAll('#submit-button, ytcp-button, button')].find(b => vis(b) &&
          !b.closest('[data-keo-btn]') && !b.hasAttribute('data-keo-btn') &&
          (b.id === 'submit-button' || /^(phản hồi|trả lời|reply|gửi|bình luận|comment)$/i.test(
            ((b.innerText || b.getAttribute('aria-label') || '') + '').trim())));
  }
  if (sub) sub.setAttribute('data-keo-sub', String(i));
  return !!sub; }"""


def _reply(page, i, text):
    """Bấm Phản hồi của đúng bình luận i → gõ câu cảm ơn → gửi → đọc lại xác nhận."""
    rb = _btn(page, "reply", i)
    if not rb.count():
        raise StepError("không thấy nút Phản hồi của bình luận")
    rb.scroll_into_view_if_needed()
    rb.click(timeout=6000)
    ok = False
    for _ in range(16):
        page.wait_for_timeout(500)
        if page.evaluate(EDITOR_JS, i):
            ok = True
            break
    if not ok:
        raise StepError("bấm Phản hồi nhưng không thấy ô viết câu trả lời / nút gửi")
    ed = page.locator(f"[data-keo-ed='{i}']").first
    ed.click()
    page.wait_for_timeout(300)
    page.keyboard.press("Control+A")
    page.keyboard.press("Delete")
    page.keyboard.insert_text(text)
    page.wait_for_timeout(500)
    got = ed.input_value() if ed.evaluate("e => e.tagName") == "TEXTAREA" else ed.inner_text()
    if _words(text)[:12] not in _words(got):
        ed.fill("")
        ed.press_sequentially(text, delay=25)
        page.wait_for_timeout(400)
    sub = page.locator(f"[data-keo-sub='{i}']").first
    for _ in range(12):   # chờ nút gửi hết bị khóa
        try:
            if sub.get_attribute("aria-disabled") != "true" and sub.get_attribute("disabled") is None:
                break
        except Exception:
            break
        page.wait_for_timeout(300)
    inner = sub.locator("button")
    (inner.first if inner.count() else sub).click(timeout=6000)
    key = _words(text)[:24]
    th = _thread(page, i)

    def seen():
        try:
            return bool(key) and th.evaluate(
                "(t, k) => [...t.querySelectorAll('ytcp-comment')].slice(1).some(c => "
                "(c.innerText || '').toLowerCase().replace(/[^\\p{L}\\p{N}_]+/gu, ' ').trim().includes(k))", key)
        except Exception:
            return False

    def box_open():
        try:
            return ed.is_visible() and bool(_words(ed.input_value() if ed.evaluate("e => e.tagName") == "TEXTAREA"
                                                   else ed.inner_text()))
        except Exception:
            return False
    for _ in range(24):
        page.wait_for_timeout(500)
        if seen():
            return True
        if not box_open():
            break
    if seen():
        return True
    if not box_open():
        _expand_replies(page, i)
        for _ in range(6):
            if seen():
                return True
            page.wait_for_timeout(500)
        return "sent"
    raise StepError("YouTube chưa nhận câu trả lời (ô viết vẫn mở sau khi bấm gửi)")


# ---------------------------------------------------------------------------------------------- chạy
def run(page, cfg, opts, db=None, log=print):
    """opts: max_comments (số bình luận đọc, mặc định 100), max_replies, reply, heart, like, preview,
    default_lang, ai, delay."""
    db = db or DB()
    s = cfg["strong_channel"]
    sid = str(s.get("channel_id") or "")
    want = int(opts.get("max_comments") or 100)
    max_total = int(opts.get("max_replies") or 0)
    prev = [r["reply"] for r in db.rows(400, sid) if r.get("reply") and r.get("status") == S_SENT]
    used = set(prev)
    thanks_bank.remember(prev[::-1])
    log(f"Mở Studio → Cộng đồng → Bình luận của kênh {s.get('name')} (đọc tối đa {want} bình luận mới nhất)."
        + (" CHẾ ĐỘ XEM TRƯỚC – chỉ đọc, không làm gì." if opts.get("preview") else ""))
    if not open_inbox(page, sid):
        log("Trang Cộng đồng chưa có bình luận nào.")
        return {}
    load_more(page, want)
    me = page.evaluate(ME_JS) + [s.get("name") or ""]
    m = re.search(r"/(@[\w.\-%]+)", str(s.get("url") or ""))
    if m:
        me.append(m.group(1))
    items = page.evaluate(READ_JS, [x for x in me if x])[:want]
    log(f"Đọc được {len(items)} bình luận.")
    total = dict(sent=0, liked=0, hearted=0, skip=0, before=0, fail=0, praise=0)
    sent_now = set()
    for it in items:
        if it["owner"] or not it["text"]:
            continue
        key = it["lc"] or f"{it['vid']}:{_norm(it['author'])}:{_norm(it['text'])[:80]}"
        old = db.get(key)
        if old and old.get("status") in (S_SENT, S_DONE_BEFORE, S_HEARTED, S_SKIP) and not opts.get("preview"):
            continue   # đã xử lý ở lần trước (trả lời / tim / thích / đã xếp không phải khen)
        a = cmt_lang.analyze(it["text"], False, opts.get("default_lang", "en"))
        if a["kind"] == cmt_lang.PRAISE and opts.get("ai"):
            ai = cmt_lang.ai_check(it["text"], *opts["ai"])
            if ai and ai["kind"] != cmt_lang.PRAISE:   # tool VÀ AI cùng thấy là khen mới tương tác
                a["kind"], a["why"] = ai["kind"], f"AI không chắc là khen ({ai['kind']})"
            elif ai and ai["lang"]:
                a["lang"], a["lang_name"] = ai["lang"], cmt_lang.lang_name(ai["lang"])
        short = it["text"].replace("\n", " ")[:70]
        vt = it["vtitle"] or it["vid"]
        row = dict(cid=key, channel_id=sid, video_id=it["vid"], video_title=vt, author=it["author"], author_url="",
                   text=it["text"], lang=a["lang"], kind=a["kind"], why=a["why"], reply="")
        if a["kind"] != cmt_lang.PRAISE:
            total["skip"] += 1
            db.save(dict(row, status=S_SKIP, note=a["why"]))
            log(f"   ↷ {it['author']}: \"{short}\" – {a['kind'].lower()} ({a['why']}) → không tương tác")
            continue
        total["praise"] += 1
        reply_txt = thanks_bank.pick(a["lang"] if a["lang"] in cmt_lang.THANKS else opts.get("default_lang", "en"),
                                     it["text"], cmt_lang.THANKS.get(a["lang"], cmt_lang.THANKS["en"])[1],
                                     avoid=used | sent_now)
        act, why_act = cmt_lang.choose_react(it["text"], opts.get("like", True), opts.get("heart", True))
        row["reply"] = reply_txt if opts.get("reply", True) else ""
        plan = ([f"trả lời: {reply_txt}"] if opts.get("reply", True) else []) + \
               ([("❤ tim" if act == "heart" else "👍 thích") + f" ({why_act})"] if act else [])
        if opts.get("preview"):
            db.save(dict(row, status=S_PREVIEW, note="xem trước – chưa làm"))
            log(f"   • {it['author']} [{a['lang_name']}] \"{short}\" → sẽ " + " · ".join(plan))
            continue
        done, note = [], ""
        try:
            want_reply = opts.get("reply", True)
            if want_reply and (it["nRep"] or 0) > 0 and not it["ownerReplied"]:
                _expand_replies(page, it["i"])
                it2 = _read_one(page, it["i"], me)
                if it2 is None or it2["nLoaded"] == 0:
                    want_reply = False
                    note = "không mở được phần phản hồi để biết kênh đã trả lời chưa – để bạn tự xem"
                else:
                    it["ownerReplied"] = it2["ownerReplied"]
            if it["ownerReplied"]:
                want_reply = False
                note = "kênh đã trả lời bình luận này từ trước"
                total["before"] += 1
            if act == "like" and not it["liked"] and not it["hearted"]:
                _toggle(page, it["i"], "like")
                done.append("👍 thích")
                total["liked"] += 1
            elif act == "heart" and not it["hearted"] and not it["liked"]:
                _toggle(page, it["i"], "heart")
                done.append("❤ tim")
                total["hearted"] += 1
            if want_reply:
                if max_total and total["sent"] >= max_total:
                    note = f"đã đủ {max_total} câu trả lời cho lượt này – để lần sau"
                else:
                    _reply(page, it["i"], reply_txt)
                    done.append("💬 trả lời")
                    total["sent"] += 1
                    sent_now.add(reply_txt)
            status = S_SENT if "💬 trả lời" in done else S_DONE_BEFORE if "từ trước" in note else \
                S_HEARTED if done else S_SKIP
            db.save(dict(row, status=status, actions=", ".join(done), note=note or why_act, done_at=_now()))
            if done:
                reacted = "👍 thích" in done or "❤ tim" in done
                log(f"   ✅ {it['author']} [{a['lang_name']}] \"{short}\" ({vt[:40]}) → " + " · ".join(done)
                    + (f" [{why_act}]" if reacted else "") + (f": {reply_txt}" if "💬 trả lời" in done else ""))
            elif note:
                log(f"   ↷ {it['author']}: {note}")
        except Exception as e:
            msg = str(e).splitlines()[0][:150]
            total["fail"] += 1
            db.save(dict(row, status=S_FAIL, actions=", ".join(done), note=msg, done_at=_now()))
            log(f"   ⚠️ {it['author']}: chưa làm được ({msg})")
            try:
                page.keyboard.press("Escape")
            except Exception:
                pass
        page.wait_for_timeout(int(1000 * random.uniform(*opts.get("delay", (2.5, 5.0)))))
    log(f"\n🏁 Cộng đồng: {total['praise']} bình luận khen → {total['sent']} câu trả lời · {total['hearted']} tim · "
        f"{total['liked']} thích · {total['before']} kênh đã trả lời trước · "
        f"{total['skip']} bình luận không phải khen (không đụng tới)"
        + (f" · {total['fail']} chưa làm được" if total["fail"] else ""))
    return total
