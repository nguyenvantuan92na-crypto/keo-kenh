"""
TOOL KÉO KÊNH YOUTUBE
=====================
  python main.py login strong        Đăng nhập kênh mạnh (lưu phiên)
  python main.py login weak          Đăng nhập kênh yếu
  python main.py setup-channel       Tùy chỉnh kênh mạnh (liên kết hồ sơ + thẻ Trang chủ)
  python main.py scan                Lọc video đang có view -> videos_to_pull.txt
  python main.py pull                Kéo trên các video trong videos_to_pull.txt
  python main.py revert              Gỡ toàn bộ phần đã kéo (theo file báo cáo)
  python main.py report              Xem tổng kết
"""
import argparse
import os
import re
import sys
from datetime import datetime

import yaml

import editors
import studio
from browser import Browsers, human_delay
from labels import set_language
from studio import NeedsCheck, StepError
from tracker import (REMOVE_DONE, REMOVE_ERROR, REMOVE_MANUAL, REMOVE_SKIP, STATUS_CHECK,
                     STATUS_DONE, STATUS_ERROR, Tracker)

VIDEO_LIST = "videos_to_pull.txt"
SHOT_DIR = "logs/screenshots"

T_PROFILE = "Hồ sơ: đường liên kết"
T_HOME = "Thẻ Trang chủ"
T_COMMENT = "Bình luận ghim"
T_END = "Màn hình kết thúc"
T_CARDS = "Thẻ (cards)"
T_COLLAB = "Tính năng cộng tác"


def ask(msg):
    """In câu hỏi (kèm xuống dòng để giao diện hiển thị ngay) rồi chờ trả lời."""
    print(msg, flush=True)
    return input()


def load_cfg(path, validate=True):
    if not os.path.exists(path):
        sys.exit(f"Không thấy {path}. Hãy copy config.example.yaml thành config.yaml và điền thông tin.")
    with open(path, encoding="utf-8") as f:
        cfg = yaml.safe_load(f)
    cfg["_path"] = path
    try:  # tốc độ thao tác chuột/bàn phím
        import human
        human.set_speed({"fast": 0.6, "normal": 1.0, "slow": 1.6}.get(cfg.get("mouse_speed", "normal"), 1.0))
    except Exception:
        pass
    w = cfg["weak_channel"]
    w["videos"] = [v for v in (w.get("videos") or []) if v]
    import selfmode
    selfmode.apply(cfg)   # chế độ "Kéo cho chính kênh": 1 kênh, 1 trình duyệt, bỏ bước không hợp lệ
    if selfmode.is_self(cfg):
        if validate and cfg.get("self_target") == selfmode.TARGET_LINKS and not w["videos"]:
            sys.exit("Chưa có video cần đẩy view – hãy dán link ở trang Thông tin kênh, hoặc chọn "
                     "\"Video mới nhất của kênh\" / \"Tự chọn video ít view nhất\".")
    elif validate and not w["videos"] and cfg.get("video_source", "weak") != "own_newest":
        sys.exit("Kênh cần kéo chưa có video nào (cần ít nhất 1 link), hoặc chọn "
                 "\"Video mới nhất của kênh mạnh\" ở Tùy chọn.")
    set_language(cfg.get("ui_language", "vi"))
    return cfg


DUMP_JS = r"""
() => {
  const seen = new Set(), out = [];
  const vis = el => { const r = el.getBoundingClientRect(); const s = getComputedStyle(el);
                      return r.width > 0 && r.height > 0 && s.visibility !== 'hidden' && s.display !== 'none'; };
  const sel = 'button, a, [role=button], [role=tab], [role=menuitem], [role=option], input, textarea, ' +
              '[contenteditable=true], ytcp-button, tp-yt-paper-item, label, h1, h2, h3';
  document.querySelectorAll(sel).forEach(el => {
    if (!vis(el)) return;
    const txt = (el.innerText || '').trim().replace(/\s+/g, ' ').slice(0, 80);
    const aria = el.getAttribute('aria-label') || '';
    const ph = el.getAttribute('placeholder') || '';
    const id = el.id ? '#' + el.id : '';
    const line = `<${el.tagName.toLowerCase()}${id}> text="${txt}" aria="${aria}" placeholder="${ph}"`;
    if (!seen.has(line) && (txt || aria || ph)) { seen.add(line); out.push(line); }
  });
  return out.slice(0, 600);
}"""


def screenshot(page, tag):
    """Chụp màn hình + ghi danh sách nút/ô trên trang (file .txt cùng tên) để hiệu chỉnh."""
    os.makedirs(SHOT_DIR, exist_ok=True)
    base = os.path.join(SHOT_DIR, f"{datetime.now():%Y%m%d_%H%M%S}_{tag}")
    path = base + ".png"
    try:
        page.screenshot(path=path, full_page=False)
    except Exception:
        path = ""
    try:
        html = page.evaluate("""() => { const v = e => e.getBoundingClientRect().width > 0;
            const d = [...document.querySelectorAll('tp-yt-paper-dialog, ytcp-dialog, [role=dialog], ytve-modal-host')]
                .filter(v); return (d.length ? d[d.length - 1] : document.body).outerHTML.slice(0, 400000); }""")
        with open(base + ".html", "w", encoding="utf-8") as f:
            f.write(html)
    except Exception:
        pass
    try:
        lines = page.evaluate(DUMP_JS)
        with open(base + ".txt", "w", encoding="utf-8") as f:
            f.write(f"URL: {page.url}\n\n" + "\n".join(lines))
        print(f"      (đã lưu chẩn đoán: {base}.txt)", flush=True)
    except Exception:
        pass
    return path


def _attached_json():
    """Video vừa gắn ở bước trước (vị trí, mốc, mã, tiêu đề đầy đủ) -> JSON để ghi nhật ký đối soát."""
    import json
    if not editors.LAST:
        return ""
    return json.dumps(editors.LAST, ensure_ascii=False)


def _items(*items):
    import json
    return json.dumps([dict(i, saved=True) for i in items if i], ensure_ascii=False)


def _comment_items(w):
    """Các link nằm trong bình luận ghim (để đối soát bình luận trỏ tới video / danh sách phát nào)."""
    import re
    out = []
    for line in str(w.get("pin_comment") or "").splitlines():
        for u in re.findall(r"https?://\S+", line):
            vid = studio.video_id(u) if re.search(r"(v=|youtu\.be/|/shorts/)", u) else ""
            out.append(dict(slot="Bình luận ghim", time="", id=vid, url=u,
                            title=line.replace(u, "").strip(" :-–|") or "(link trong bình luận)", owner="weak"))
    if not out:
        out.append(dict(slot="Bình luận ghim", time="", id="", url="",
                        title=str(w.get("pin_comment") or "").strip()[:200], owner="weak"))
    return out


def _shot(page, tag, task, target, msg):
    """Chụp ảnh lỗi và ghi kèm NỘI DUNG LỖI vào đầu file .txt (để gói chẩn đoán tự giải thích)."""
    path = screenshot(page, tag)
    try:
        txt = os.path.splitext(path)[0] + ".txt" if path else ""
        if txt and os.path.exists(txt):
            with open(txt, encoding="utf-8") as f:
                body = f.read()
            with open(txt, "w", encoding="utf-8") as f:
                f.write(f"BƯỚC: {task}\nVIDEO/KÊNH: {target}\nLỖI: {msg}\n\n{body}")
    except Exception:
        pass
    return path


class _NoRevisit(Exception):
    """Bước kiểm tra lại cần mở lại 1 tab đã làm xong -> không mở."""


def _verify(page, verify):
    """Bước vừa báo lỗi/cần kiểm tra: mở lại YouTube xem kết quả THỰC TẾ. Đã đúng như yêu cầu -> trả câu mô tả."""
    if verify is None:
        return ""
    # CHỈ xem trên trang đang mở – KHÔNG mở lại / tải lại tab đó trên kênh (mỗi tab chỉ vào 1 lần)
    print("      · xem lại ngay trên trang đang mở xem kênh đã đúng như yêu cầu chưa...", flush=True)
    orig_goto, orig_reload = page.goto, page.reload

    def goto(url, *a, **k):
        if studio.on_page(page, url):
            return None                    # đang ở đúng trang -> dùng luôn, không tải lại
        raise _NoRevisit(url)

    page.goto, page.reload = goto, (lambda *a, **k: None)
    try:
        return verify() or ""
    except _NoRevisit:
        return ""                          # muốn xem phải mở lại tab -> không làm, giữ kết quả thật đã ghi
    except Exception as e:
        print(f"      · không xem lại được ({type(e).__name__}) – giữ kết quả cũ", flush=True)
        return ""
    finally:
        page.goto, page.reload = orig_goto, orig_reload


studio.WEAK_SNAPSHOT = lambda pg, tag: screenshot(pg, tag)
CURRENT_CFG = {}


def browser_channel(page):
    """Mã kênh Studio trình duyệt ĐANG dùng (hỏi nền, không mở tab)."""
    import browser as _br
    return _br.studio_channel(page)


def channel_report(page, vid=""):
    """Ghi rõ 3 mã kênh (số liệu thật, không đoán) ra nhật ký + file chẩn đoán."""
    import time as _t
    import ytinfo
    ch = (CURRENT_CFG or {}).get("strong_channel") or {}
    want = str(ch.get("channel_id") or "")
    cur = browser_channel(page)
    owner = ""
    if vid:
        try:
            owner = ytinfo.info(vid, page).get("owner") or ""
        except Exception:
            owner = ""
    lines = [f"Kênh trình duyệt đang dùng : {cur or '(không đọc được)'}",
             f"Kênh sở hữu video {vid or ''}: {owner or '(không đọc được)'}",
             f"ID kênh trong file kênh     : {want or '(trống)'}  ({ch.get('name') or ''})"]
    if cur and want and cur != want:
        lines.append("=> LỆCH: trình duyệt đang ở kênh khác với ID trong file kênh.")
    if owner and want and owner != want:
        lines.append("=> LỆCH: video này KHÔNG thuộc kênh ghi trong file kênh.")
    if cur and owner and cur == owner == want:
        lines.append("=> Ba mã trùng nhau: kênh đúng – lỗi do Studio, không phải do chọn sai kênh.")
    for ln in lines:
        print("      · " + ln, flush=True)
    try:
        os.makedirs(os.path.join("logs", "screenshots"), exist_ok=True)
        with open(os.path.join("logs", "screenshots", _t.strftime("%Y%m%d_%H%M%S") + "_kenh.txt"), "w",
                  encoding="utf-8") as f:
            f.write("\n".join(lines) + "\n")
    except Exception:
        pass
    return cur, owner, want


def _fix_channel(page, vid=""):
    """Studio báo 'Rất tiếc, đã xảy ra lỗi' giữa chừng: ghi rõ 3 mã kênh; trình duyệt lệch kênh -> chọn lại đúng kênh."""
    import browser as _br
    ch = (CURRENT_CFG or {}).get("strong_channel") or {}
    if not ch.get("channel_id"):
        return False
    cur, owner, want = channel_report(page, vid)
    if owner and owner != want:
        print("      · Video không thuộc kênh này – không chuyển kênh, bỏ qua video.", flush=True)
        return False
    if cur and cur == want and (not owner or owner == want):
        print("      · Kênh đúng – Studio lỗi tạm thời: tải lại trang 1 lần.", flush=True)
        return True    # mở lại trang 1 lần (đã giới hạn 1 lần mỗi lượt)
    print(f"      · Studio báo lỗi – có thể trình duyệt đang ở kênh khác: chuyển lại đúng kênh "
          f"{ch.get('name') or ch.get('channel_id')}", flush=True)
    return _br.select_channel(page, ch, log=lambda m: print(m, flush=True))


studio.ON_WRONG_CHANNEL = _fix_channel


SKIPPED_EXISTING = []   # (hạng mục, video) có sẵn màn hình kết thúc / thẻ khác – tool không gắn


def run_step(tracker, page, target, task, fn, detail="", attached=None, verify=None):
    """Chạy 1 bước, ghi DONE / CẦN KIỂM TRA / LỖI vào báo cáo. Trả về kết quả của fn.
    verify: hàm xem lại kết quả thật trên YouTube khi bước báo lỗi – kênh đã đúng sẵn như bạn điền
    thì ghi ✅ hoàn thành và chạy tiếp, KHÔNG báo lỗi."""
    editors.LAST = None
    try:
        res = fn()
        extra = (" ".join(res) if isinstance(res, list) else res) if isinstance(res, (list, str)) and res else ""
        if isinstance(res, str) and "đã có sẵn – giữ nguyên" in res:
            # video đang có màn hình kết thúc / thẻ KHÁC (không phải video cần kéo): tool KHÔNG gắn gì
            # -> không được báo là xong; ghi rõ để bạn biết và bật "Thay thế cái cũ" nếu muốn thay
            msg = (f"CHƯA gắn – video đang có sẵn {task.lower()} khác (không phải video cần kéo), tool giữ nguyên. "
                   f"Muốn thay: tích 'Thay thế cái cũ' ở trang Chạy tool rồi kéo lại.")
            print(f"  ⚠️ {task}: {msg}", flush=True)
            SKIPPED_EXISTING.append((task, target))
            tracker.log(target, task, "đã có sẵn – " + msg, STATUS_CHECK, msg)
            return res
        tracker.log(target, task, extra or detail, STATUS_DONE, data=attached or _attached_json())
        return res
    except NeedsCheck as e:
        status, msg, kind = STATUS_CHECK, str(e), "check"
    except studio.StudioVideoError as e:   # lỗi phía YouTube với riêng video này: ghi rõ, không thử lại
        msg = str(e)
        tracker.log(target, task, detail, STATUS_CHECK, msg, _shot(page, "check", task, target, msg))
        return None
    except StepError as e:
        status, msg, kind = STATUS_ERROR, str(e), "error"
    except Exception as e:
        status, msg, kind = STATUS_ERROR, f"{type(e).__name__}: {str(e).splitlines()[0][:200]}", "error"
    shot = _shot(page, kind, task, target, msg)   # chụp NGAY lúc lỗi (trước khi kiểm tra lại)
    ok = _verify(page, verify)
    if ok:
        tracker.log(target, task, studio.already_ok(ok) + f" (lúc chạy có báo: {msg[:120]})", STATUS_DONE)
        return ok
    if status == STATUS_CHECK:
        tracker.log(target, task, detail, status, msg, shot, data=attached or _attached_json())
    else:
        tracker.log(target, task, detail, status, msg, shot)
    return None


# ------------------------------ lệnh ------------------------------

ACCOUNTS_JS = r"""() => {
  // trang Chuyển đổi kênh: mọi kênh của tài khoản Google đang đăng nhập (tên + @handle)
  const T = e => ((e && (e.innerText || e.textContent)) || '').replace(/\s+/g, ' ').trim();
  const out = [], seen = new Set();
  for (const it of document.querySelectorAll('ytd-account-item-renderer')) {
    const name = T(it.querySelector('#channel-title, #account-name, yt-formatted-string#channel-title'));
    let handle = T(it.querySelector('#channel-handle, #account-byline, yt-formatted-string#channel-handle'));
    const all = (it.innerText || '').split('\n').map(x => x.trim()).filter(Boolean);
    if (!/^@/.test(handle)) handle = all.find(x => /^@[\w.\-]+$/.test(x)) || '';
    const n = name || all[0] || '';
    const id = ((it.outerHTML.match(/UC[\w-]{22}/) || [''])[0]);
    const key = (handle || n).toLowerCase();
    if (!n || seen.has(key)) continue;
    seen.add(key);
    out.push({name: n, handle, id});
  }
  return out; }"""


def _pause(page, a=2.5, b=5.5):
    """Nghỉ ngẫu nhiên như người thật đọc trang."""
    import random
    page.wait_for_timeout(int(random.uniform(a, b) * 1000))
    try:   # thỉnh thoảng cuộn nhẹ trang như người đang xem
        if random.random() < 0.6:
            page.mouse.wheel(0, random.randint(120, 480))
            page.wait_for_timeout(int(random.uniform(0.6, 1.4) * 1000))
            page.mouse.wheel(0, -random.randint(80, 400))
    except Exception:
        pass


def _norm_name(t):
    import unicodedata as _u
    t = _u.normalize("NFD", str(t or "").lower())
    t = "".join(c for c in t if _u.category(c) != "Mn").replace("đ", "d")
    return re.sub(r"[^a-z0-9]+", "", t)


def account_channels(page, log=print):
    """[{name, handle, id}] – mọi kênh YouTube của tài khoản Google trong trình duyệt này."""
    import ytinfo
    page.goto("https://www.youtube.com/channel_switcher", wait_until="domcontentloaded")
    _pause(page, 3, 6)
    chans = page.evaluate(ACCOUNTS_JS) or []
    for c in chans:
        if not str(c.get("id") or "").startswith("UC") and c.get("handle"):
            try:   # đọc mã kênh bằng yêu cầu nền (không mở thêm tab)
                _st, html = ytinfo._browser_get(page, f"https://www.youtube.com/{c['handle']}")
                m = re.search(r'<link rel="canonical" href="https://www\.youtube\.com/channel/(UC[\w-]{22})"', html or "") \
                    or re.search(r'"(?:channelId|externalId)":"(UC[\w-]{22})"', html or "")
                c["id"] = m.group(1) if m else ""
            except Exception:
                c["id"] = ""
            page.wait_for_timeout(1200)
    return [c for c in chans if str(c.get("id") or "").startswith("UC")]


def match_channel(chans, hints):
    """Kênh khớp ghi chú / tên profile GPM. Trả về (kênh, lý do) – không chắc chắn thì (None, lý do)."""
    hs = [_norm_name(h) for h in hints if _norm_name(h) and len(_norm_name(h)) >= 3]
    hits = []
    for c in chans:
        cn, ch = _norm_name(c.get("name")), _norm_name(c.get("handle"))
        for h in hs:
            if h in (cn, ch) or (len(h) >= 5 and (h in cn or cn in h and len(cn) >= 5)) or (ch and len(h) >= 5 and h in ch):
                hits.append(c)
                break
    if len(hits) == 1:
        return hits[0], "khớp ghi chú / tên profile GPM"
    if not hits and len(chans) == 1:
        return chans[0], "tài khoản chỉ có 1 kênh"
    return None, ("nhiều kênh cùng khớp" if hits else "không kênh nào khớp ghi chú GPM")


HILITE_JS = r"""(name) => {
  // tô khung xanh kênh GỢI Ý (khớp ghi chú GPM) – chỉ để bạn dễ thấy, tool KHÔNG bấm
  const T = e => ((e && (e.innerText || e.textContent)) || '').replace(/\s+/g, ' ').trim().toLowerCase();
  for (const it of document.querySelectorAll('ytd-account-item-renderer')) {
    if (name && T(it).includes(name.toLowerCase())) {
      it.style.outline = '3px solid #34C759'; it.style.outlineOffset = '2px'; it.style.borderRadius = '8px';
      it.scrollIntoView({block: 'center'});
      return true;
    }
  }
  return false; }"""


def _channel_name(page, cid):
    """Tên kênh đọc bằng yêu cầu nền (không mở thêm trang)."""
    import html as _html
    import ytinfo
    try:
        _st, body = ytinfo._browser_get(page, f"https://www.youtube.com/channel/{cid}")
        m = re.search(r'<meta property="og:title" content="([^"]*)"', body or "")
        return _html.unescape(m.group(1)).strip() if m else ""
    except Exception:
        return ""


def cmd_login_gpm(cfg, who, gid, detect=False):
    """Đăng nhập / đọc kênh qua profile GPM-Login – mở ĐÚNG 1 trang (Chuyển đổi kênh của YouTube), DỪNG lại để
    BẠN bấm chọn đúng kênh, rồi tool đọc kênh vừa chọn bằng yêu cầu nền (không mở thêm trang nào)."""
    import browser as _br
    label = "kênh mạnh" if who == "strong" else "kênh cần kéo"
    ch = cfg["strong_channel" if who == "strong" else "weak_channel"]
    cname, cid = str(ch.get("name") or "").strip(), str(ch.get("channel_id") or "")
    pname = ch.get("gpm_profile_name") or gid
    note = str(ch.get("gpm_profile_note") or "").strip()
    cfg["headless"] = False
    with Browsers(cfg) as b:
        b._chosen.add(who)
        p = b.page(who)
        _pause(p, 2, 4)
        print("      · mở trang Chuyển đổi kênh của profile (1 trang duy nhất)...", flush=True)
        p.goto("https://www.youtube.com/channel_switcher", wait_until="domcontentloaded")
        _pause(p, 3, 5)
        if "accounts.google.com" in (p.url or ""):
            ask(f"👉 Profile GPM '{pname}' chưa đăng nhập YouTube. Trên cửa sổ GPM: đăng nhập tài khoản Google có "
                f"{label}, rồi bấm Tiếp tục.")
            if "channel_switcher" not in (p.url or ""):
                p.goto("https://www.youtube.com/channel_switcher", wait_until="domcontentloaded")
                _pause(p, 3, 5)
        if "accounts.google.com" in (p.url or ""):
            b._login_ok[who] = False
            _br.mark_login(_br._profile(cfg, who), False)
            print("❌ Profile GPM vẫn chưa đăng nhập YouTube – đăng nhập trong cửa sổ GPM rồi bấm Đọc lại kênh.", flush=True)
            return
        chans = []
        try:
            chans = p.evaluate(ACCOUNTS_JS) or []
        except Exception:
            pass
        if chans:
            print(f"      · tài khoản trong profile có {len(chans)} kênh:", flush=True)
            for c in chans:
                print(f"        - {c['name']} {c.get('handle') or ''}", flush=True)
        want = cname if (cid.startswith("UC") and not detect) else ""
        sug, _why = match_channel([dict(c, id="UC") for c in chans], [want or note, pname]) if chans else (None, "")
        if sug:
            try:
                p.evaluate(HILITE_JS, sug["name"])
            except Exception:
                pass
        hint = f" Gợi ý theo ghi chú GPM: '{sug['name']}' (khung xanh)." if sug else ""
        ask(f"👉 Trên cửa sổ GPM '{pname}' (trang Chuyển đổi kênh): BẤM CHỌN đúng kênh dùng làm {label}."
            f"{hint} Chọn xong thì bấm Tiếp tục.")
        _pause(p, 2, 3)
        cur = _br.studio_channel(p)          # kênh bạn vừa chọn – yêu cầu nền, không mở trang
        b._login_ok[who] = bool(cur)
        _br.mark_login(_br._profile(cfg, who), bool(cur))
        if not cur:
            print("❌ Chưa đọc được kênh vừa chọn – hãy chắc đã bấm chọn 1 kênh trên trang Chuyển đổi kênh, "
                  "rồi bấm Đọc lại kênh.", flush=True)
            return
        name = _channel_name(p, cur) or next((c["name"] for c in chans if c.get("id") == cur), "")
        p._keo_channel_ok = cur
        if cid.startswith("UC") and not detect:
            print(f"✅ Profile GPM đang dùng đúng {label} {cname} ({cid})." if cur == cid else
                  f"❌ Kênh vừa chọn là {name or cur} ({cur}), KHÁC {label} đã lưu {cname} ({cid}). "
                  f"Hãy chọn lại đúng kênh, hoặc bấm Đọc lại kênh để dùng kênh vừa chọn.", flush=True)
            return
    fill_channel(cfg, who, {"channel_id": cur, "name": name}, _br._profile(cfg, who), overwrite=True)
    print(f"✅ Đã điền {label} theo kênh bạn chọn: {name or '(chưa đọc được tên)'} – ID {cur}.", flush=True)


def _save_choices(cfg, who, chans):
    """Ghi danh sách kênh của tài khoản vào file kênh (khung trạng thái hiện để bạn chọn khi cần)."""
    try:
        import jobs
        data = jobs.load(cfg["_path"])
        k = "strong_channel" if (who == "strong" or data.get("mode") == "self") else "weak_channel"
        data.setdefault(k, {})["gpm_channels"] = [dict(name=c["name"], handle=c.get("handle") or "", id=c["id"])
                                                  for c in chans]
        jobs.save(cfg["_path"], data)
    except Exception:
        pass


def cmd_login(cfg, who, fresh=False, detect=False):
    import time
    from browser import open_for_login
    import browser as _bg
    gid = _bg.gpm_id(cfg, who)
    if gid:
        for attempt in range(2):
            try:
                return cmd_login_gpm(cfg, who, gid, detect=detect)
            except SystemExit:
                raise
            except Exception as e:
                msg = str(e).splitlines()[0][:160]
                closed = "closed" in msg.lower() or "Target" in type(e).__name__
                if attempt == 0 and closed:
                    print("      · cửa sổ profile GPM vừa bị đóng giữa chừng – mở lại và đọc lại 1 lần...", flush=True)
                    time.sleep(4)
                    continue
                print(("❌ Cửa sổ profile GPM bị đóng giữa chừng – đừng đóng cửa sổ GPM khi tool đang đọc kênh, "
                       "rồi bấm Đọc lại kênh." if closed else
                       f"❌ Chưa đọc được kênh từ profile GPM: {msg}. Bấm Đọc lại kênh để thử lại."), flush=True)
                return
    label = "MẠNH" if who == "strong" else "CẦN KÉO"
    print(f"Đang mở trình duyệt để đăng nhập kênh {label.lower()}...", flush=True)
    if fresh:
        import browser as _b0
        prof = _b0.wipe_profile(cfg, who)
        print(f"      · đã tạo trình duyệt SẠCH riêng cho kênh này ({os.path.basename(prof)})", flush=True)
    proc, name = open_for_login(cfg, who)
    print(f"Đã mở {name} ở chế độ bình thường (tool KHÔNG điều khiển cửa sổ này).", flush=True)
    ch = cfg["strong_channel" if who == "strong" else "weak_channel"]
    cname, cid = str(ch.get("name") or "").strip(), str(ch.get("channel_id") or "")
    target = f"kênh \"{cname}\"" + (f" ({cid})" if cid else "") if cname or cid else f"kênh {label.lower()}"
    ask(f"👉 Trên cửa sổ {name} vừa mở: đăng nhập tài khoản Google CÓ {target}. Nếu YouTube hỏi chọn kênh, "
        f"bấm đúng {target}. Đăng nhập xong hãy ĐÓNG cửa sổ {name} đó, rồi bấm 'Tiếp tục'. "
        f"(Tool tự nhớ – lần sau mở là vào thẳng đúng kênh này.)")
    for _ in range(40):
        if proc.poll() is not None:
            break
        time.sleep(0.5)
    else:
        ask(f"👉 Cửa sổ {name} vẫn còn mở. Hãy đóng nó (bấm dấu X) rồi bấm 'Tiếp tục'.")
        for _ in range(40):
            if proc.poll() is not None:
                break
            time.sleep(0.5)
    time.sleep(2)
    print("Đang kiểm tra đăng nhập...", flush=True)
    import browser as _br
    _br.wait_closed(_br._profile(cfg, who))   # Cốc Cốc chạy ngầm sau khi đóng cửa sổ -> chờ / đóng hẳn
    saved = _br.login_saved(cfg, who)
    if saved is False:
        print(f"❌ Chưa thấy đăng nhập YouTube trong trình duyệt của kênh {label.lower()} – hãy bấm Đăng nhập lại.",
              flush=True)
        return
    known = cid.startswith("UC") or bool(_br._handle_of(ch.get("url")))
    found = {}
    with Browsers(cfg) as b:
        b.keep_anon = True          # Bước đăng nhập: giữ hồ sơ ẩn danh cho lần chạy kế tiếp
        b._chosen.add(who)          # tự kiểm tra kênh ở dưới, không chọn 2 lần
        ok = b.is_logged_in(who)
        if ok and not known:        # kênh mới: tool tự đọc tên + ID của kênh vừa đăng nhập
            found = detect_channel(b.page(who))
        right = ok and _br.select_channel(b.page(who), ch, log=lambda m: print(m, flush=True)) \
            if known else ok
    if ok and not known:
        if found.get("channel_id"):
            fill_channel(cfg, who, found, _br._profile(cfg, who))
            print(f"✅ Tool đã tự điền {'kênh mạnh' if who == 'strong' else 'kênh cần kéo'}: "
                  f"{found.get('name') or '(chưa đọc được tên)'} – ID {found['channel_id']}. "
                  f"Đã lưu vào file kênh, lần sau tool tự mở đúng kênh này.", flush=True)
        else:
            print("❌ Đã đăng nhập nhưng tool chưa đọc được kênh – có thể tài khoản này chưa có kênh YouTube, "
                  "hoặc YouTube hỏi chọn kênh mà chưa chọn. Hãy bấm Đăng nhập lại và chọn đúng kênh.", flush=True)
        return
    if ok and right and _br.is_anon(cfg, who):
        print(f"✅ Đã đăng nhập {target} (ẨN DANH): dùng cho LẦN CHẠY KẾ TIẾP, chạy xong tool xóa sạch – "
              f"các lần sau tool sẽ mở trình duyệt sạch để bạn đăng nhập lại.", flush=True)
    elif ok and right:
        print(f"✅ Đã lưu đăng nhập {target}. Lần sau tool tự mở đúng kênh này.", flush=True)
    elif ok:
        print(f"❌ Đã đăng nhập nhưng tài khoản này KHÔNG có {target} – hãy bấm Đăng nhập lại và chọn "
              f"đúng tài khoản Google có kênh đó.", flush=True)
    else:
        print(f"❌ Kênh {label.lower()} chưa đăng nhập được – hãy bấm Đăng nhập lại.", flush=True)


def auto_video_list(p, cfg, w, sid, sname):
    """Danh sách video trống: tìm video đang có view của kênh (Analytics 60 phút); không có thì lấy các video
    CÔNG KHAI nhiều view nhất trong 20 video mới nhất (bỏ video cần đẩy). Ghi lại vào ô Danh sách video."""
    import selfmode
    n = int(cfg.get("max_videos_per_run") or 0) or int(cfg.get("auto_videos", 3) or 3)
    print(f"🔎 Chọn {n} video NHIỀU LƯỢT XEM NHẤT 48 giờ qua của kênh {sname} (Studio → Số liệu phân tích → "
          f"Hiệu suất theo thời gian thực), từ trên xuống"
          + ("" if REPLACE_RUN else f", bỏ video đã kéo {PULLED_WHAT[0]}") + "...", flush=True)
    skip0 = {selfmode.vid_of(v) for v in (w.get("videos") or [])}
    found = analytics_pick(p, sid, n, skip0, log=lambda m: print(m, flush=True))
    rows = [f"{u}    # {v} view / 48 giờ" for u, v in found]
    if not found:
        skip = {selfmode.vid_of(v) for v in (w.get("videos") or [])}
        items = [it for it in selfmode._channel_items(p, sid, want=20)
                 if it["id"] not in skip and selfmode.parse_views(it["meta"]) is not None]
        items.sort(key=lambda it: -selfmode.parse_views(it["meta"]))
        pick = selfmode._first_public(p, items, 5, log=lambda m: print(m, flush=True))
        rows = [f"https://www.youtube.com/watch?v={it['id']}    # {selfmode.parse_views(it['meta'])} view"
                for it in pick]
        if rows:
            print(f"   Chưa có video đạt ngưỡng – lấy {len(rows)} video công khai nhiều view nhất trong 20 video "
                  f"mới nhất.", flush=True)
    if rows:
        save_video_list(cfg, rows)
        print(f"✅ Đã điền {len(rows)} video vào ô Danh sách video:", flush=True)
        for r in rows:
            print(f"   · {r}", flush=True)
    return [r.split()[0] for r in rows]


def detect_channel(page):
    """Kênh đang dùng trong trình duyệt vừa đăng nhập: Studio tự chuyển tới /channel/UC... của kênh đó.
    Tên kênh hỏi nền (không mở thêm tab)."""
    import re as _re
    cid = ""
    for _ in range(20):
        m = _re.search(r"/channel/(UC[\w-]{22})", page.url or "")
        if m:
            cid = m.group(1)
            break
        page.wait_for_timeout(500)
    if not cid:
        try:
            m = _re.search(r'"(?:channelId|externalChannelId)":"(UC[\w-]{22})"', page.content())
            cid = m.group(1) if m else ""
        except Exception:
            cid = ""
    if not cid:
        return {}
    name = ""
    try:
        import html as _html
        import ytinfo
        try:
            _st, body = ytinfo._get(f"https://www.youtube.com/channel/{cid}")
        except Exception:
            _st, body = ytinfo._browser_get(page, f"https://www.youtube.com/channel/{cid}")
        m = _re.search(r'<meta property="og:title" content="([^"]*)"', body or "")
        name = _html.unescape(m.group(1)).strip() if m else ""
    except Exception:
        name = ""
    return {"channel_id": cid, "name": name}


def fill_channel(cfg, who, found, profile_path, overwrite=False):
    """Ghi tên + ID kênh vừa đọc được vào file kênh; giữ đúng trình duyệt vừa đăng nhập cho kênh đó;
    file kênh còn tên mặc định ('Kênh 3') -> đổi theo tên kênh."""
    import re as _re
    import jobs
    path = cfg["_path"]
    data = jobs.load(path)
    k = "strong_channel" if (who == "strong" or data.get("mode") == "self") else "weak_channel"
    ch = data.setdefault(k, {})
    cid = found["channel_id"]
    ch["channel_id"] = cid
    if found.get("name") and (overwrite or not str(ch.get("name") or "").strip()):
        ch["name"] = found["name"]
    if overwrite or not str(ch.get("url") or "").strip():
        ch["url"] = f"https://www.youtube.com/channel/{cid}"
    rel = os.path.relpath(profile_path, os.getcwd()).replace("\\", "/")
    m_ = _re.match(r"^(.*?)_(?:andanh_)?(?:coccoc|chrome)$", rel)
    if m_:
        ch["profile_dir"] = m_.group(1)
    name = str(data.get("job_name") or "")
    if not name.strip() or _re.fullmatch(r"(Kênh|Kenh) ?\d*( \(bản sao\))?|Kênh mới", name.strip()):
        s_, w_ = data.get("strong_channel", {}) or {}, data.get("weak_channel", {}) or {}
        if data.get("mode") == "self" or not w_.get("name"):
            data["job_name"] = s_.get("name") or name
        else:
            data["job_name"] = f"{s_.get('name') or '?'} → {w_.get('name')}"
    jobs.save(path, data)


def anon_login(cfg, who):
    """Kênh ĐĂNG NHẬP ẨN DANH: mỗi lượt chạy mở 1 trình duyệt sạch (hồ sơ tạm) để bạn đăng nhập – cửa sổ bình
    thường, tool không điều khiển. Chạy xong tool đóng và xóa sạch hồ sơ tạm đó."""
    import time
    import browser as _br
    label = "mạnh" if who == "strong" else "cần kéo"
    if _br.login_saved(cfg, who) is True:
        return
    ch = cfg["strong_channel" if who == "strong" else "weak_channel"]
    target = str(ch.get("name") or "").strip() or f"kênh {label}"
    proc, name = _br.open_for_login(cfg, who)
    ask(f"👉 ẨN DANH – kênh {label}: trên cửa sổ {name} vừa mở (trình duyệt sạch, không lưu gì), đăng nhập "
        f"tài khoản Google có kênh \"{target}\". Đăng nhập xong ĐÓNG cửa sổ đó rồi bấm 'Tiếp tục'. "
        f"(Chạy xong tool xóa sạch đăng nhập này.)")
    for _ in range(40):
        if proc.poll() is not None:
            break
        time.sleep(0.5)
    _br.wait_closed(_br._profile(cfg, who))


def ensure_login(b, who):
    import browser as _br
    if _br.is_anon(b.cfg, who) and who not in b._login_ok:
        anon_login(b.cfg, who)
    if not b.is_logged_in(who):
        sys.exit(f"❌ Kênh {'mạnh' if who == 'strong' else 'cần kéo'} chưa đăng nhập (hoặc phiên đăng nhập đã hết hạn). "
                 f"Hãy bấm bước {'1 – Đăng nhập kênh mạnh' if who == 'strong' else '2 – Đăng nhập kênh cần kéo'} "
                 f"ở trang Chạy tool rồi chạy lại.")
    key = b._who(who)
    if b._channel_ok.get(key) is False:
        # trình duyệt đang dùng KÊNH KHÁC (vd cùng tài khoản Google có nhiều kênh) -> không làm gì sai chỗ
        ch = b.cfg["strong_channel" if who == "strong" else "weak_channel"]
        sys.exit(f"❌ Trình duyệt đang ở kênh khác, không chuyển được sang kênh "
                 f"\"{ch.get('name') or ch.get('channel_id')}\" ({ch.get('channel_id')}). Tool DỪNG, không thao tác gì "
                 f"(nếu làm tiếp, Studio sẽ báo 'Rất tiếc, đã xảy ra lỗi' và bình luận không ghim được).\n"
                 f"   Cách sửa: trang Chạy tool → bấm Đăng nhập kênh đó → trên cửa sổ vừa mở bấm ảnh đại diện → "
                 f"Chuyển đổi tài khoản → chọn đúng kênh này → đóng cửa sổ → Tiếp tục, rồi chạy lại.")


def home_parts_done(t, weak_url):
    """Các phần Trang chủ đã làm cho kênh cần kéo này (đọc từ file kết quả)."""
    import re
    done = set()
    for r in t.active_rows():
        if r["task"] != T_HOME or r["target"] != weak_url:
            continue
        for m in re.finditer(r"(?:Đã làm|Đã có sẵn): ([^.|]+)", r["note"]):
            for name in m.group(1).split(","):
                if name.strip() in studio.HOME_PARTS:
                    done.add(name.strip())
    return done


T_POST = "Bài đăng video"


def _prev_home(t, weak_url):
    """Giá trị (link) lần trước tool đã gắn cho từng phần Trang chủ: {slot: url}."""
    import json
    from tracker import COL
    out = {}
    for r in range(2, t.ws.max_row + 1):
        if t.ws.cell(r, COL["Hạng mục"]).value != T_HOME or t.ws.cell(r, COL["Link video / Kênh"]).value != weak_url:
            continue
        try:
            for it in json.loads(t.ws.cell(r, COL["Dữ liệu gắn (JSON)"]).value or "[]"):
                out[it.get("slot", "")] = it.get("url", "")
        except Exception:
            pass
    return out


def cmd_setup(cfg, t, renew=False):
    """Bước 3 – Tùy chỉnh kênh mạnh: đường liên kết Hồ sơ, Thẻ Trang chủ (video giới thiệu cho người chưa ĐK,
    video nổi bật cho người ĐK cũ, danh sách phát đơn, kênh nổi bật) và Bài đăng có video."""
    s, w = cfg["strong_channel"], cfg["weak_channel"]
    o = cfg.get("strong_setup") or {}
    already = home_parts_done(t, w.get("url", ""))
    notes = []
    if renew:  # làm mới: phần làm-1-lần chỉ làm lại khi link đã đổi so với lần trước
        prev = _prev_home(t, w.get("url", ""))
        old_pl = prev.get("Trang chủ – Danh sách phát đơn", "")
        new_pl = studio.playlist_url(w.get("playlist", ""))
        stale = []   # THAY THẾ: phần cũ tool đã thêm mà nay đã đổi -> xóa phần cũ rồi thêm phần mới
        if old_pl and new_pl and old_pl != new_pl:
            already = already - {"Danh sách phát đơn"}
            stale.append(dict(slot="Trang chủ – Danh sách phát đơn", url=old_pl))
        old_ch = prev.get("Trang chủ – Kênh nổi bật", "")
        if old_ch and w.get("url") and old_ch != w.get("url"):
            already = already - {"Kênh nổi bật"}
            stale.append(dict(slot="Trang chủ – Kênh nổi bật", url=old_ch))
        print("Chế độ LÀM MỚI Hồ sơ, Trang chủ, Bài đăng: thay phần tool đã gắn lần trước.", flush=True)
    once = already & set(studio.HOME_ONCE)
    if once:
        print(f"↷ Trang chủ đã làm từ lần trước: {', '.join(sorted(once))} – sẽ bỏ qua.", flush=True)
    with Browsers(cfg) as b:
        ensure_login(b, "strong")
        p = b.page("strong")
        link = str(o.get("profile_link_url") or w.get("url") or "").strip()
        had = [r for r in t.active_rows() if r["task"] == T_PROFILE and r["status"] == STATUS_DONE
               and link and link in (r["note"] or "")]
        import re as _re
        old_rows = [r for r in t.rows_to_revert() if r["task"] == T_PROFILE] if renew else []
        old_urls = []
        for r in old_rows:
            m = _re.search(r"Đã thêm đường liên kết: .* – (https?://\S+)\s*$", r["detail"] or "")
            if m and m.group(1) != link:
                old_urls.append(m.group(1))
        if o.get("do_profile_link", True) and had and not old_urls:
            print(f"↷ Đường liên kết Hồ sơ {link} đã thêm từ trước (nhật ký) – bỏ qua.", flush=True)
        elif o.get("do_profile_link", True):
            print(f"\n▶ Hồ sơ – đường liên kết: {link}", flush=True)
            res = run_step(t, p, w.get("url", ""), T_PROFILE,
                     lambda: studio.add_profile_link(p, s["channel_id"], w, o.get("profile_link_title", ""), link,
                                                     remove_urls=old_urls),
                     attached=_items(dict(slot="Hồ sơ – đường liên kết", time="",
                                          id=_safe_vid(link), url=link,
                                          title=o.get("profile_link_title") or w.get("name", ""), owner="weak")),
                     verify=lambda: studio.check_profile_link(p, s["channel_id"], link))
            p._keo_profile_dirty = res is None   # bước Hồ sơ lỗi -> bước Trang chủ mở trang mới (bỏ thay đổi dở)
            if isinstance(res, str) and "Đã xóa đường liên kết cũ" in res:
                from tracker import REMOVE_DONE as _RD
                for r in old_rows:
                    if any(u in (r["detail"] or "") for u in old_urls):
                        t.set_removal(r["row"], _RD)
            human_delay(cfg)
        print("\n▶ Thẻ Trang chủ", flush=True)
        import selfmode
        if selfmode.is_self(cfg) and ((o.get("do_trailer", True) and not str(o.get("trailer_video") or "").strip())
                                      or (o.get("do_featured", True) and not str(o.get("featured_video") or "").strip())):
            # kéo cho chính kênh + ô để trống -> tool tự chọn video mỗi lần chạy
            print("Tự chọn video cho Trang chủ (ô để trống):", flush=True)
            auto_tr, auto_ft = selfmode.home_auto(p, s["channel_id"], log=lambda m: print(m, flush=True))
            o = dict(o)
            if o.get("do_trailer", True) and not str(o.get("trailer_video") or "").strip() and auto_tr:
                o["trailer_video"] = auto_tr
            if o.get("do_featured", True) and not str(o.get("featured_video") or "").strip() and auto_ft:
                o["featured_video"] = auto_ft

        if renew and stale:
            import remover
            print("  · THAY THẾ: xóa phần Trang chủ cũ tool đã thêm (" +
                  ", ".join(f"{x['slot'].split('– ')[-1]}: {x['url']}" for x in stale) + ")", flush=True)
            try:
                r_ = remover.home(p, s["channel_id"], stale, w)
                notes.append(f"Đã xóa phần cũ: {r_}" if r_ else "Đã xóa phần Trang chủ cũ")
            except Exception as e:
                notes.append(f"Chưa xóa được phần Trang chủ cũ ({str(e).splitlines()[0][:100]}) – hãy xóa tay: "
                             + ", ".join(x["url"] for x in stale))
            p._keo_profile_dirty = True    # Trang chủ vừa Xuất bản -> bước sau tải trang mới

        def home():
            res = studio.setup_home_tab(p, s["channel_id"], w, already, o, notes)
            return res
        studio.HOME_LAST = []
        run_step(t, p, w.get("url", ""), T_HOME, home, detail="Thẻ Trang chủ",
                 attached=None)
        # ghi chi tiết từng video/phần đã gắn vào dòng vừa ghi (đối soát)
        _patch_last_data(t, studio.HOME_LAST)
        human_delay(cfg)
        posts = [x for x in (o.get("post_videos") or []) if str(x).strip()]
        newest = o.get("post_source", "newest") == "newest"
        if o.get("do_posts", True) and (newest or posts):
            import re as _re
            done_ids = set()
            for r in ([] if renew else t.active_rows()):   # làm mới: được đăng bài mới cả với video đã đăng
                if r["task"] == T_POST:
                    done_ids.update(_re.findall(r"\(([\w-]{11})\)", r["note"] or ""))
            todo = [None] if newest else posts
            for link in todo:
                vid = _safe_vid(link) if link else ""
                if vid and vid in done_ids:
                    print(f"  ↷ Đã đăng bài video {vid} từ trước – bỏ qua", flush=True)
                    continue
                print("\n▶ Bài đăng video: " + (link or "video MỚI NHẤT của kênh mạnh"), flush=True)
                run_step(t, p, f"https://www.youtube.com/channel/{s['channel_id']}/posts", T_POST,
                         lambda link=link: studio.post_video(p, s["channel_id"], link, o.get("post_text", ""),
                                                             skip_ids=done_ids, replace=renew),
                         detail="Bài đăng video",
                         attached=None,
                         verify=lambda: studio.check_post(p, s["channel_id"], studio.POST_LAST_ID))
                _patch_post_data(t, o.get("post_text", ""))
                human_delay(cfg)
    t.sync_google_sheet()
    make_report(t)


def _safe_vid(link):
    try:
        return studio._vid_of(link)
    except Exception:
        return ""


def _patch_post_data(t, text):
    """Ghi video vừa đăng bài (đọc mã từ dòng nhật ký cuối) vào cột đối soát."""
    import re
    from tracker import COL
    try:
        r = t.ws.max_row
        note = str(t.ws.cell(r, COL["Chi tiết"]).value or "")
        m = re.search(r"\(([\w-]{11})\)", note)
        if m and "đã có sẵn" not in note and studio.ALREADY_OK not in note:
            _patch_last_data(t, [dict(slot="Bài đăng – video", time="", id=m.group(1),
                                      url=f"https://www.youtube.com/watch?v={m.group(1)}",
                                      title=(text or "")[:80], owner="strong")])
    except Exception:
        pass


def _patch_last_data(t, items):
    """Ghi danh sách mục đã gắn (JSON) vào dòng nhật ký cuối cùng."""
    import json
    from tracker import COL
    if not items:
        return
    try:
        r = t.ws.max_row
        t.ws.cell(r, COL["Dữ liệu gắn (JSON)"], json.dumps([dict(i, saved=True) for i in items], ensure_ascii=False))
        t.ws.cell(r, COL["Video đã gắn"], ", ".join(dict.fromkeys(i["id"] for i in items if i.get("id"))))
        t.save()
    except Exception:
        pass


def cmd_scan(cfg):
    s = cfg["strong_channel"]
    with Browsers(cfg) as b:
        ensure_login(b, "strong")
        found = studio.scan_realtime(b.page("strong"), s["channel_id"], cfg["scan"]["min_views_per_hour"])
    if not found:
        print("Không đọc được video nào đạt ngưỡng. Bạn có thể tự điền link vào", VIDEO_LIST)
        return
    save_video_list(cfg, [f"{url}    # {v} view" for url, v in found])
    print(f"✅ {len(found)} video đạt ≥ {cfg['scan']['min_views_per_hour']} view/60 phút")
    for url, v in found:
        print(f"   {v:>6}  {url}")
    print("✅ Đã điền vào ô Danh sách video. Xem lại (xóa dòng không muốn kéo) rồi bấm Bắt đầu kéo.")


def read_video_list(cfg=None):
    """Danh sách video dùng để kéo: của riêng kênh (pull_videos trong file kênh) hoặc videos_to_pull.txt cũ."""
    if cfg is not None and "pull_videos" in cfg:
        return [str(u).split("#")[0].strip() for u in (cfg.get("pull_videos") or [])
                if str(u).split("#")[0].strip().startswith("http")]
    if not os.path.exists(VIDEO_LIST):
        sys.exit(f"Chưa có {VIDEO_LIST}. Chạy 'python main.py scan' hoặc tự tạo file, mỗi dòng 1 link.")
    urls = []
    with open(VIDEO_LIST, encoding="utf-8") as f:
        for line in f:
            line = line.split("#")[0].strip()
            if line.startswith("http"):
                urls.append(line)
    return urls


def save_video_list(cfg, lines):
    """Ghi danh sách video tìm được vào đúng kênh đang chạy."""
    if "pull_videos" in cfg and cfg.get("_path"):
        import jobs
        data = jobs.load(cfg["_path"])
        data["pull_videos"] = lines
        jobs.save(cfg["_path"], data)
        cfg["pull_videos"] = lines
    else:
        with open(VIDEO_LIST, "w", encoding="utf-8") as f:
            f.write("\n".join(lines) + "\n")


PULLED = set()      # video tool ĐÃ kéo màn hình kết thúc (theo file kết quả) – lượt này không chọn lại
RT48 = {}           # báo cáo 'Hiệu suất theo thời gian thực' đã đọc trong lượt (mỗi kênh đọc 1 lần)
REPLACE_RUN = False
PULLED_WHAT = ["màn hình kết thúc"]


def analytics_pick(p, sid, n, exclude=(), log=print):
    """`n` video nhiều lượt xem nhất 48 GIỜ QUA (Studio – Hiệu suất theo thời gian thực), đọc từ trên xuống:
    bỏ video đã có trong danh sách / đang được đẩy / đã kéo màn hình kết thúc (trừ khi 'Thay thế cái cũ') /
    video lỗi / video chưa công khai. Trả về [(link, view 48 giờ)]."""
    import selfmode
    import studio_bad
    if sid not in RT48:
        try:
            RT48[sid] = studio.realtime_48h(p, sid, log=log)
        except Exception as e:
            log(f"   chưa đọc được báo cáo Thời gian thực ({str(e).splitlines()[0][:100]})")
            RT48[sid] = []
    out = []
    for vid, v48, _v60, title in RT48[sid]:
        if len(out) >= n:
            break
        name = (title or vid)[:55]
        if vid in exclude:
            continue
        if vid in PULLED and not REPLACE_RUN:
            log(f"   ↷ {name} ({v48} view/48 giờ) – đã kéo {PULLED_WHAT[0]} từ trước, lấy video kế tiếp")
            continue
        if studio_bad.is_bad(vid):
            log(f"   ↷ {name} – Studio không mở được video này, bỏ")
            continue
        ok, why = selfmode.video_public(p, vid)
        if ok is False:
            log(f"   ↷ {name} – {why}, bỏ")
            continue
        out.append((f"https://www.youtube.com/watch?v={vid}", v48))
        log(f"   ✔ chọn: {name} – {v48} lượt xem 48 giờ qua")
    return out


def _auto_list(cfg):
    """Danh sách video do TOOL tự chọn (dòng có ghi '# … view') -> được phép thay video lỗi bằng video khác."""
    rows = [str(u) for u in (cfg.get("pull_videos") or []) if str(u).strip()]
    return bool(rows) and all(re.search(r"#.*view", r_) for r_ in rows)


def _substitute(p, cfg, sid, urls, w):
    """1 video CÔNG KHAI khác của kênh (nhiều view nhất trong 20 video mới nhất) để thay video Studio không mở được.
    Bỏ video đã có trong danh sách, video cần đẩy, video Studio đang lỗi. Ghi lại vào ô Danh sách video."""
    import selfmode
    import studio_bad
    say = lambda m: print(m, flush=True)
    in_list = {selfmode.vid_of(u) for u in urls}
    pushed = {selfmode.vid_of(v) for v in (w.get("videos") or [])}
    tried = set()

    def rows_from(items):
        return [(it["id"], selfmode.parse_views(it["meta"])) for it in items]

    def pick(rows, avoid, label):
        cand = {}
        for v, n in rows:
            if v and n is not None and v not in avoid and not studio_bad.is_bad(v):
                cand[v] = max(n, cand.get(v, -1))
        order = sorted(cand.items(), key=lambda r_: -r_[1])
        say(f"    · tìm video thay ({label}): {len(rows)} video đọc được, {len(order)} video dùng được")
        for v, n in order[:15]:
            if v in tried:
                continue
            tried.add(v)
            ok, why = selfmode.video_public(p, v)
            if ok is False:
                say(f"    · bỏ {v} – {why}")
                continue
            return f"https://www.youtube.com/watch?v={v}", f"{n} view"
        return None

    got = analytics_pick(p, sid, 1, in_list | pushed, log=say)   # 0) báo cáo Thời gian thực (48 giờ qua)
    if got:
        return got[0][0], f"{got[0][1]} view / 48 giờ"
    rows = []
    try:
        rows = rows_from(selfmode._channel_items(p, sid, want=20))
    except Exception as e:
        say(f"    · đọc tab Video của kênh chưa được ({str(e).splitlines()[0][:100]})")
    # 1) tab Video (20 video mới nhất)
    got = pick(rows, in_list | pushed, "tab Video")
    if got:
        return got
    # 2) đọc sâu hơn tab Video (tới 60 video) + danh sách video của kênh từ nguồn tin YouTube (hỏi nền)
    try:
        selfmode._ITEMS.pop(sid, None)
        more = rows_from(selfmode._channel_items(p, sid, want=60, rounds=14))
    except Exception:
        more = []
    rows = rows + more + selfmode.feed_items(p, sid)
    got = pick(rows, in_list | pushed, "đọc thêm tới 60 video + nguồn tin của kênh")
    if got:
        return got
    # 3) kênh ít video: cho phép cả video đang được đẩy (tool không bao giờ gắn video vào chính nó)
    got = pick(rows, in_list, "kể cả video đang được đẩy")
    if got:
        return got
    say("    · không còn video công khai nào khác của kênh để thay")
    return None


def _swap_in_list(cfg, old_url, new_line):
    import selfmode
    rows = list(cfg.get("pull_videos") or [])
    ov = selfmode.vid_of(old_url)
    rows = [new_line if selfmode.vid_of(str(r_).split("#")[0]) == ov else r_ for r_ in rows]
    if new_line not in rows:
        rows.append(new_line)
    save_video_list(cfg, rows)


def cmd_pull(cfg, t, only=None, force=False, first=False, close_after=False):
    global CURRENT_CFG
    CURRENT_CFG = cfg
    studio.STRONG_ID = str(cfg.get("strong_channel", {}).get("channel_id") or "")
    w = cfg["weak_channel"]
    print(f"\n========== KÊNH: {cfg.get('job_name') or w.get('name')} ==========", flush=True)
    if cfg.get("headless"):
        print("Trình duyệt chạy ẨN (ngoài màn hình) – vẫn là trình duyệt thật, chỉ không hiện cửa sổ.", flush=True)
    urls = read_video_list(cfg)
    global REPLACE_RUN
    REPLACE_RUN = bool(cfg.get("end_screen", {}).get("replace_existing"))
    PULLED.clear()
    RT48.clear()
    try:
        import selfmode as _sm
        # "đã kéo" = MỌI bước đang tích trong {Màn hình kết thúc, Thẻ} đều đã làm xong trên video đó
        want_tasks = {T_END: "endscreen", T_CARDS: "cards"}
        sel = [k for k, v in want_tasks.items() if not only or v in only] or [T_END]
        done_by = {}
        for r_ in t.active_rows():
            if r_.get("task") in sel and r_.get("status") == STATUS_DONE and r_.get("target"):
                done_by.setdefault(_sm.vid_of(r_["target"]), set()).add(r_["task"])
        PULLED.update(v_ for v_, ks in done_by.items() if set(sel) <= ks)
        PULLED_WHAT[0] = " & ".join(x.lower() for x in sel)
    except Exception:
        pass
    refresh = bool(urls) and _auto_list(cfg)
    auto_find = not urls or refresh   # trống / danh sách do tool tự chọn -> mỗi lượt chọn lại theo lượt xem 48 giờ
    if auto_find:
        print(("Danh sách video do tool tự chọn" if refresh else "Danh sách video đang trống") +
              " – tool chọn video nhiều lượt xem nhất 48 giờ qua của kênh mạnh (báo cáo Thời gian thực).", flush=True)
    if first:
        urls = urls[:1]
        print(f"CHẠY THỬ trên 1 video: {urls[0] if urls else '(trống)'}", flush=True)
    cap = int(cfg.get("max_videos_per_run", 0) or 0)
    if cap and len(urls) > cap:
        print(f"Giới hạn {cap} video mỗi lần chạy (theo Tùy chọn) – kéo {cap}/{len(urls)} video đầu danh sách.",
              flush=True)
        urls = urls[:cap]
    steps = set(only or ["comment", "endscreen", "cards", "collab"])
    if not cfg.get("collab", {}).get("enabled", True):
        steps.discard("collab")
    # bước ghi "đã có sẵn – giữ nguyên" không tính là đã làm (tool chưa gắn gì vào video đó)
    # việc đã làm xong (theo nhật ký) -> bỏ qua. Dòng "đã có sẵn" / "đã đúng sẵn" là tool CHƯA gắn gì -> không tính.
    # Màn hình kết thúc / Thẻ: nhớ cả mã các video tool đã gắn để biết video cần gắn có đổi không.
    done = {}
    if not force:
        for r in t.active_rows():
            if r["status"] == STATUS_DONE and not re.search(r"đã có sẵn|đã đúng sẵn|đúng sẵn trên kênh",
                                                             r["note"] or ""):
                done[(r["target"], r["task"])] = [x.strip() for x in re.split(r"[,\s]+", r.get("attached") or "")
                                                  if re.fullmatch(r"[\w-]{11}", x.strip())]
    renew = set()   # video mà tool tự THAY video do chính tool gắn trước đó (video cần gắn đã đổi)
    if urls:
        print(f"Bắt đầu kéo {len(urls)} video | các bước: {', '.join(sorted(steps))}"
              + ("" if force else " | bỏ qua bước đã xong") + "\n")

    def skip(url, task, want=None):
        if (url, task) not in done:
            return False
        had = done[(url, task)]
        if want is not None and had and sorted(had) != sorted(want):
            # tool đã gắn video khác trước đây; nay video cần gắn đã đổi (vd có video mới công khai) -> thay
            print(f"  ↻ {task}: tool đã gắn {', '.join(had)} – nay cần {', '.join(want)} → thay bằng video mới",
                  flush=True)
            renew.add((url, task))
            return False
        print(f"  ↷ Đã xong từ trước  {task:<28} {url}", flush=True)
        return True

    import selfmode
    one = selfmode.is_self(cfg)
    if one:
        if "collab" in steps:
            print("↷ Kéo cho chính kênh: bỏ bước Cộng tác (YouTube không cho cộng tác với chính kênh mình).",
                  flush=True)
        steps.discard("collab")
    with Browsers(cfg) as b:
        ensure_login(b, "strong")
        if "collab" in steps:
            ensure_login(b, "weak")
        p = b.page("strong")
        # trước khi đăng / sửa gì: kênh trình duyệt đang dùng PHẢI đúng ID trong file kênh (số liệu thật)
        sid0 = str(cfg["strong_channel"].get("channel_id") or "")
        cur0 = browser_channel(p)
        if cur0 and sid0 and cur0 != sid0:
            print(f"⚠️ Trình duyệt đang dùng kênh {cur0}, khác ID trong file kênh {sid0} – chuyển lại đúng kênh...",
                  flush=True)
            import browser as _br
            _br.select_channel(p, cfg["strong_channel"], log=lambda m: print(m, flush=True))
            cur0 = browser_channel(p)
            if cur0 and cur0 != sid0:
                print(f"❌ Vẫn đang ở kênh {cur0}, không phải {sid0} ({cfg['strong_channel'].get('name')}). Tool DỪNG, "
                      f"không đăng / sửa gì. Kiểm tra ô ID kênh ở trang Thông tin kênh có đúng kênh bạn muốn kéo "
                      f"không, hoặc Đăng nhập lại và chọn đúng kênh.", flush=True)
                return
        if cur0:
            print(f"✔ Kênh trình duyệt đang dùng: {cur0} – đúng ID trong file kênh.", flush=True)
        if one:
            print(f"KÉO CHO CHÍNH KÊNH: {cfg['strong_channel'].get('name')} – video nhiều view đẩy sang video "
                  f"cần đẩy của chính kênh.", flush=True)
            if cfg.get("self_target") == selfmode.TARGET_LEAST and steps & {"endscreen", "cards", "comment"}:
                n = max(int(cfg.get("end_screen", {}).get("count", 2) or 2),
                        int(cfg.get("cards", {}).get("count", 3) or 3))
                print(f"Tìm {n} video ít view nhất trong 20 video mới nhất của kênh...", flush=True)
                w["videos"] = selfmode.pick_least_viewed(p, cfg["strong_channel"]["channel_id"], n,
                                                         log=lambda m: print(m, flush=True))
                if not w["videos"]:
                    print("❌ Không đọc được số view trên tab Video của kênh – hãy chọn cách khác ở trang "
                          "Thông tin kênh.", flush=True)
                    return
        # Ô Bình luận ghim để trống -> tool TỰ SOẠN cho từng video theo đúng nội dung (tên truyện, thể loại, ngôn ngữ)
        auto_cmt = "comment" in steps and not str(w.get("pin_comment") or "").strip()
        cmt_targets = []
        if auto_cmt:
            sid_ = str(cfg["strong_channel"].get("channel_id") or "")
            if one and cfg.get("self_target") == selfmode.TARGET_NEWEST:
                cmt_targets = selfmode.public_newest(p, sid_, 3, log=lambda m: print(m, flush=True))
            else:
                cmt_targets = [v for v in (w.get("videos") or []) if selfmode.vid_of(v)]
                if one and not cmt_targets:
                    cmt_targets = selfmode.public_newest(p, sid_, 3, log=lambda m: print(m, flush=True))
            if not cmt_targets and not one and str(w.get("url") or "").startswith("http"):
                cmt_targets = [w["url"]]          # kênh cần kéo chưa có link video: trỏ về kênh
            if cmt_targets:
                print("Bình luận ghim: ô đang trống – tool tự soạn cho TỪNG video theo nội dung (tên truyện, "
                      "thể loại, ngôn ngữ), mỗi video một câu khác nhau.", flush=True)
            else:
                steps.discard("comment")
                print("↷ Không có video nào để giới thiệu trong bình luận ghim – bỏ bước Ghim bình luận.", flush=True)
        # chỉ kéo trên video ĐÚNG là của kênh mạnh (video kênh khác: Studio báo "Rất tiếc, đã xảy ra lỗi",
        # bình luận ghim không có nút Xóa...) -> kiểm tra chủ video trước, bỏ qua video không thuộc kênh
        import remover
        sid = str(cfg["strong_channel"].get("channel_id") or "")
        sname = cfg["strong_channel"].get("name") or sid
        if auto_find:
            old_urls = list(urls)
            urls = auto_video_list(p, cfg, w, sid, sname)
            if not urls and old_urls:
                print("   Không có video mới cần kéo – dùng lại danh sách lần trước.", flush=True)
                urls = old_urls
            if first:
                urls = urls[:1]
            if cap and len(urls) > cap:
                urls = urls[:cap]
            if not urls:
                print(f"❌ Không tìm được video nào của kênh {sname} để kéo – hãy dán link video vào ô Danh sách "
                      f"video ở trang Chạy tool.", flush=True)
                return
            print(f"Bắt đầu kéo {len(urls)} video | các bước: {', '.join(sorted(steps))}\n", flush=True)
        print(f"Kiểm tra {len(urls)} video trong Danh sách video có đúng của kênh {sname} không...", flush=True)
        keep, foreign, gone = [], [], []
        for u in urls:
            try:
                vid_ = studio.video_id(u)
            except StepError:
                keep.append(u)
                continue
            st_, owner_ = remover._public_status(p, vid_)
            if st_ in ("ERROR", "UNPLAYABLE"):
                print(f"  ↷ {u} – video đã bị xóa / không xem được", flush=True)
                gone.append(u)
            elif owner_ and sid and owner_ != sid:
                foreign.append(u)
                print(f"  ↷ {u} – thuộc kênh khác ({owner_}), không phải {sname} – bỏ qua", flush=True)
            else:
                keep.append(u)
        if foreign and keep:
            print(f"↷ Đã bỏ {len(foreign)} video không thuộc kênh {sname}; kéo trên {len(keep)} video đúng kênh.",
                  flush=True)
        if foreign and not keep:
            # cả danh sách là video kênh khác (thường là danh sách cũ còn sót) -> tự tìm video đang có view
            # của ĐÚNG kênh mạnh, ghi lại vào ô Danh sách video rồi kéo tiếp luôn
            mv = int(cfg.get("scan", {}).get("min_views_per_hour", 20) or 20)
            print(f"\n🔎 Tự tìm video đang có view của kênh {sname} (≥ {mv} view / 60 phút)...", flush=True)
            try:
                found = studio.scan_realtime(p, sid, mv)
            except Exception as e:
                found = []
                print(f"   không tìm được ({str(e).splitlines()[0][:120]})", flush=True)
            if found:
                save_video_list(cfg, [f"{u_}    # {v_} view" for u_, v_ in found])
                print(f"✅ Đã thay Danh sách video bằng {len(found)} video đang có view của kênh {sname}.", flush=True)
                keep = [u_ for u_, _v in found]
                if cap and len(keep) > cap:
                    keep = keep[:cap]
        import studio_bad
        studio_steps = steps & {"endscreen", "cards", "collab"}
        urls = keep
        if not urls:
            print(f"Không còn video nào của kênh {sname} để kéo. Video của kênh có thể chưa đạt ngưỡng view – hãy "
                  f"dán link video vào ô Danh sách video, hoặc giảm 'Ngưỡng lọc video' ở trang Thông tin kênh.",
                  flush=True)
            return
        source = cfg.get("video_source", "weak")
        w["_es_count"] = cfg.get("end_screen", {}).get("count", 2)
        # chỉ gắn video CÔNG KHAI đã phát hành: video lên lịch / riêng tư / không công khai gắn vào thẻ sẽ hiện
        # tam giác vàng, vào màn hình kết thúc sẽ báo "Đây là video riêng tư"
        if steps & {"endscreen", "cards"}:
            need = max(int(w["_es_count"] or 2), int(cfg.get("cards", {}).get("count", 3) or 3))
            if source == "own_newest":
                print(f"Tìm {need + 1} video CÔNG KHAI mới phát hành gần nhất của kênh {sname} "
                      f"(bỏ video đang lên lịch / riêng tư / không công khai)...", flush=True)
                w["videos"] = selfmode.public_newest(p, sid, need + 1, log=lambda m: print(m, flush=True))
                w["_owner"] = "strong"
                source = "weak"      # từ đây gắn đúng các link công khai vừa tìm (không bốc trong 'Kênh của tôi')
            else:
                print("Kiểm tra video sẽ gắn vào màn hình kết thúc & thẻ có đang CÔNG KHAI không...", flush=True)
                before = len(w.get("videos") or [])
                w["videos"] = selfmode.filter_public(p, w.get("videos") or [], log=lambda m: print(m, flush=True))
                if len(w["videos"]) < before:
                    print(f"↷ Đã bỏ {before - len(w['videos'])} video chưa công khai; còn {len(w['videos'])} "
                          f"video công khai để gắn.", flush=True)
            if not w["videos"]:
                print("❌ Không có video CÔNG KHAI nào để gắn vào màn hình kết thúc / thẻ – bỏ 2 bước này. "
                      "Hãy chờ video mở công khai, hoặc dán link video công khai ở trang Thông tin kênh.",
                      flush=True)
                steps -= {"endscreen", "cards"}
        replace = cfg.get("end_screen", {}).get("replace_existing", False)
        print("Chế độ: " + ("THAY THẾ – xóa màn hình kết thúc & thẻ cũ rồi gắn video mới" if replace
                            else "GIỮ NGUYÊN – video đã có màn hình kết thúc / thẻ thì bỏ qua"), flush=True)
        es_pl = bool(cfg.get("end_screen", {}).get("playlist")) and "endscreen" in steps
        cd_pl = bool(cfg.get("cards", {}).get("playlist")) and "cards" in steps
        w.pop("_pl", None)
        w["_es_pl"] = es_pl
        if (es_pl or cd_pl) and w.get("_owner") != "strong":
            import playlists
            print("Danh sách phát gắn vào " + " & ".join(x for x, on in (("màn hình kết thúc", es_pl), ("thẻ", cd_pl))
                                                         if on) + ":", flush=True)
            w["_pl"] = playlists.choose(p, w, log=lambda m: print(m, flush=True))
            if w["_pl"]:
                print(f"   → '{w['_pl']['title'] or w['_pl']['id']}' – {w['_pl']['url']}", flush=True)
        elif es_pl or cd_pl:
            print("   (Đang dùng video mới nhất của kênh mạnh – không gắn danh sách phát của kênh cần kéo.)", flush=True)
        if steps & {"endscreen", "cards"}:
            print("Video đưa vào màn hình kết thúc & thẻ: " +
                  (f"{len(editors._weak_ids(w))} video CÔNG KHAI mới nhất của kênh mạnh" if w.get("_owner") == "strong"
                   else f"{len(editors._weak_ids(w))} video của kênh cần kéo (đã điền ở Thông tin kênh) – "
                        f"màn hình kết thúc {min(int(w['_es_count'] or 2), len(editors._weak_ids(w)))} ô, "
                        f"thẻ {min(int(cfg['cards'].get('count', 3) or 3), len(editors._weak_ids(w)))} thẻ"), flush=True)
        for u in gone:   # video đã xóa -> lấy video công khai nhiều view khác của kênh thay vào
            sub = _substitute(p, cfg, sid, urls + gone, w)
            if sub:
                urls.append(sub[0])
                _swap_in_list(cfg, u, f"{sub[0]}    # {sub[1]}")
                print(f"    → thay {u} bằng video nhiều view khác của kênh: {sub[0]} ({sub[1]}) – đã ghi vào ô "
                      f"Danh sách video.", flush=True)
        for u in list(urls):
            v_ = selfmode.vid_of(u)
            if studio_steps and v_ and studio_bad.is_bad(v_):
                print(f"  ↷ {u} – lần chạy trước YouTube Studio không mở được video này (video đã xóa hoặc "
                      f"YouTube lỗi).", flush=True)
                if True:
                    sub = _substitute(p, cfg, sid, urls + gone, w)
                    if sub:
                        urls[urls.index(u)] = sub[0]
                        _swap_in_list(cfg, u, f"{sub[0]}    # {sub[1]}")
                        print(f"    → thay bằng video khác của kênh: {sub[0]} ({sub[1]})", flush=True)
                        continue
                print("    → vẫn ghim bình luận; bỏ Màn hình kết thúc / Thẻ / Cộng tác của video này "
                      f"(tool thử lại sau {studio_bad.DAYS} ngày).", flush=True)
        swapped = set()
        for i, url in enumerate(urls, 1):
            print(f"[{i}/{len(urls)}] {url}")
            try:
                vid = studio.video_id(url)
            except StepError as e:
                t.log(url, "Đọc link", "", STATUS_ERROR, str(e))
                continue
            duration = 0
            wv = selfmode.for_video(cfg, w, vid)   # chế độ 1 kênh: không bao giờ gắn video vào chính nó
            self_skip = selfmode.nothing_to_attach(cfg, wv)
            if self_skip and steps & {"endscreen", "cards"}:
                print("  ↷ Video này chính là video cần đẩy – không gắn màn hình kết thúc / thẻ vào chính nó.",
                      flush=True)
            if auto_cmt and "comment" in steps and cmt_targets:
                import pin_writer
                import ytinfo
                tgt = next((u for u in cmt_targets if selfmode.vid_of(u) != vid), cmt_targets[0])
                tv = selfmode.vid_of(tgt)
                try:
                    cur_t = ytinfo.info(vid, p).get("title") or ""
                    tgt_t = (ytinfo.info(tv, p).get("title") or "") if tv else str(w.get("name") or "")
                except Exception:
                    cur_t, tgt_t = "", ""
                w["pin_comment"] = pin_writer.write(cur_t, tgt_t, tgt, vid, cfg["strong_channel"].get("name") or "")
                print(f"  · bình luận ghim tự soạn: {w['pin_comment'].strip()}", flush=True)
            cmt_self = one and vid and vid in str(w.get("pin_comment") or "")
            if "comment" in steps and cmt_self:
                print("  ↷ Bình luận ghim đang trỏ tới chính video này – bỏ qua.", flush=True)
            if "comment" in steps and not cmt_self and not skip(url, T_COMMENT):
                key = re.sub(r"\s+", " ", re.sub(r"https?://\S+", " ", str(w["pin_comment"]))).strip()[:60] or \
                    next((l.strip() for l in str(w["pin_comment"]).splitlines() if l.strip()), "")[:60]
                old_c = [r_ for r_ in t.rows_to_revert() if r_["task"] == T_COMMENT and r_["target"] == url] \
                    if replace else []
                studio.COMMENT_REPLACED = False
                r = run_step(t, p, url, T_COMMENT,
                             lambda: studio.pin_comment(p, url, w["pin_comment"], replace=replace),
                             f"Bình luận: {key}", attached=_items(*_comment_items(w)),
                             verify=lambda: studio.check_comment(p, url, w["pin_comment"]))
                duration = r if isinstance(r, float) else 0
                if old_c and r is not None and studio.COMMENT_REPLACED:   # bình luận ghim cũ của tool đã bị thay
                    for r_ in old_c:
                        t.set_removal(r_["row"], REMOVE_DONE)
                human_delay(cfg)
            if "cards" in steps and not duration and (url, T_CARDS) not in done:
                try:  # cần độ dài video để tính mốc thẻ – hỏi nền, KHÔNG mở lại trang video
                    import ytinfo
                    duration = float(ytinfo.info(vid, p).get("length") or 0)
                except Exception:
                    duration = 0
            es_want = editors._weak_ids(wv)[:max(1, min(2, int(w.get("_es_count") or 2)))] \
                if source != "own_newest" else None
            cd_want = editors._weak_ids(wv)[:max(1, min(5, int(cfg["cards"].get("count", 3) or 3)))] \
                if source != "own_newest" else None
            if studio_steps and studio_bad.is_bad(vid):
                print("  ↷ Bỏ Màn hình kết thúc / Thẻ / Cộng tác: YouTube Studio không mở được video này "
                      "(lỗi phía YouTube, kênh đúng).", flush=True)
            if "endscreen" in steps and not self_skip and not studio_bad.is_bad(vid) \
                    and not skip(url, T_END, es_want):
                run_step(t, p, url, T_END,
                         lambda: editors.end_screen(p, vid, wv, cfg["end_screen"].get("replace_existing", False)
                                                    or (url, T_END) in renew, source),
                         "2 video mới nhất",
                         verify=lambda: editors.check_end_screen(p, vid, wv, source))
                human_delay(cfg)
            if "cards" in steps and not self_skip and not studio_bad.is_bad(vid) and not skip(url, T_CARDS, cd_want):
                cfg_c = dict(cfg["cards"], replace_existing=cfg["cards"].get("replace_existing", False)
                             or (url, T_CARDS) in renew)
                run_step(t, p, url, T_CARDS, lambda: editors.cards(p, vid, wv, duration, cfg_c, source),
                         "3 thẻ video, mốc:",
                         verify=lambda: editors.check_cards(p, vid, wv, duration, cfg["cards"], source))
                human_delay(cfg)
            if "collab" in steps and not studio_bad.is_bad(vid) and not skip(url, T_COLLAB):
                wp = b.page("weak")
                run_step(t, p, url, T_COLLAB, lambda: studio.collab(p, wp, vid, w, cfg["strong_channel"].get("channel_id", "")),
                         attached=_items(dict(slot="Cộng tác", time="", id="", url=w["url"],
                                              title=w.get("name", ""), owner="weak")),
                         verify=lambda: studio.check_collab(p, vid, w))
                human_delay(cfg)
            if vid in studio_bad.NOW and vid not in swapped:
                swapped.add(vid)
                sub = _substitute(p, cfg, sid, urls + gone, w)
                if sub:
                    urls.append(sub[0])      # kéo luôn video thay thế trong lượt này
                    _swap_in_list(cfg, url, f"{sub[0]}    # {sub[1]}")
                    print(f"  → Thay video này bằng video khác của kênh: {sub[0]} ({sub[1]}) – kéo ngay trong lượt "
                          f"này, đã ghi vào ô Danh sách video.", flush=True)
                else:
                    print(f"  → Không còn video công khai nào khác của kênh để thay. Kiểm tra video: "
                          f"https://studio.youtube.com/video/{vid}/edit (đã xóa / đang bị YouTube hạn chế?).",
                          flush=True)
        if close_after:
            print("Đóng trình duyệt của kênh này trước khi sang kênh tiếp theo...", flush=True)
            b.close_all()
    t.sync_google_sheet()
    make_report(t)
    if SKIPPED_EXISTING:
        n_es = sum(1 for k, _ in SKIPPED_EXISTING if k == T_END)
        n_cd = sum(1 for k, _ in SKIPPED_EXISTING if k == T_CARDS)
        print(f"\n⚠️ CHƯA GẮN vì video đã có sẵn từ trước: {n_es} màn hình kết thúc, {n_cd} thẻ. "
              f"Để tool thay bằng video cần kéo: tích ô 'Thay thế cái cũ' ở trang Chạy tool rồi bấm Kéo lại "
              f"(tool chỉ thay trên các video này, gỡ được như mọi mục khác).", flush=True)
    cmd_report(t, session=True)


REVERT_ORDER = [T_COMMENT, T_END, T_CARDS, T_COLLAB, T_POST, T_PROFILE, T_HOME]


def _json_items(r):
    import json
    try:
        d = json.loads(r.get("data") or "[]")
        return [x for x in d if isinstance(x, dict)]
    except Exception:
        return []


def cmd_revert(cfg, t, rows=None):
    """GỠ SẠCH phần đã kéo trên kênh mạnh. rows: số dòng trong file kết quả (chỉ gỡ các dòng này).
    - Mỗi (video, hạng mục) chỉ gỡ 1 lần dù đã kéo nhiều lần (các lần kéo cũ đều được đánh dấu đã gỡ).
    - Mỗi mục gỡ xong tool mở lại đúng chỗ đó kiểm tra; còn sót -> báo lỗi, không bao giờ báo 'đã gỡ' khi chưa sạch.
    - Thứ đang có trên kênh khác với thứ tool đã gắn -> không đụng, đánh dấu 'Gỡ thủ công'."""
    import re
    import remover
    s, w = cfg["strong_channel"], cfg["weak_channel"]
    me = os.path.basename(cfg.get("_path", ""))
    # CHỈ gỡ dòng của ĐÚNG file kênh này (dòng cũ không rõ kênh không bao giờ bị gán nhầm sang kênh này)
    sid = str(s.get("channel_id") or "")
    todo, other = [], 0
    for r in t.rows_to_revert(set(rows) if rows else None):
        # phải khớp CẢ file kênh lẫn mã kênh mạnh ghi trên dòng -> không bao giờ gỡ nhầm sang kênh khác
        if r["file"] == me and sid and sid in r.get("strong", ""):
            todo.append(r)
        else:
            other += 1
    if other:
        print(f"(Bỏ qua {other} dòng không thuộc kênh mạnh {s.get('name')} / file {me} – không đụng tới.)", flush=True)
    if not todo:
        print("Không có mục nào của kênh mạnh này cần gỡ.")
        return
    # gom: hạng mục theo video -> 1 lần cho mỗi (video, hạng mục); hạng mục cấp kênh -> 1 lần cho cả kênh
    groups = {}
    for r in todo:
        task = r["task"]
        key = (task, r["target"]) if task in (T_COMMENT, T_END, T_CARDS, T_COLLAB) else (task, "kênh")
        groups.setdefault(key, []).append(r)
    order = sorted(groups, key=lambda k: (REVERT_ORDER.index(k[0]) if k[0] in REVERT_ORDER else 99, k[1]))
    print(f"\n========== GỠ – KÊNH MẠNH: {s.get('name')} ({s.get('channel_id')}) ==========", flush=True)
    names = {}
    for k in order:
        names[k[0]] = names.get(k[0], 0) + (1 if k[1] != "kênh" else len(groups[k]))
    print("Sẽ gỡ: " + ", ".join(f"{n} × {task}" for task, n in names.items()), flush=True)
    if ask("Gõ 'GO' để xác nhận:").strip() != "GO":
        return
    ok = bad = manual = skip = 0
    with Browsers(cfg) as b:
        ensure_login(b, "strong")
        p = b.page("strong")
        remover.STRONG_ID = s.get("channel_id", "")
        if not remover.verify_channel(p, remover.STRONG_ID):
            print(f"❌ Trình duyệt của kênh mạnh {s.get('name')} không vào được kênh {remover.STRONG_ID} – tài khoản đang "
                  f"đăng nhập không có kênh này. Tool DỪNG, không gỡ gì. Hãy làm lại Bước 1 (đăng nhập kênh mạnh) "
                  f"cho đúng kênh rồi gỡ lại.", flush=True)
            return
        print(f"✔ Đang ở đúng kênh mạnh {s.get('name')} ({remover.STRONG_ID}) – chỉ thao tác trên kênh này.",
              flush=True)
        for k in order:
            task, target = k
            rs = groups[k]
            label = f"{task} — {target if target != 'kênh' else s.get('name')}"
            print(f"\n▶ Gỡ {label}", flush=True)
            def run_one(task=task, target=target, rs=rs):
                if task == T_COMMENT:
                    keys = [re.sub(r"^Bình luận:\s*", "", r.get("detail") or "") for r in rs
                            if str(r.get("detail") or "").startswith("Bình luận:")]
                    if not keys:
                        keys = [str(w.get("pin_comment") or "").strip().splitlines()[0][:60]] \
                            if str(w.get("pin_comment") or "").strip() else []
                    return remover.comment(p, target, keys[-1] if keys else "")
                elif task == T_END:
                    n = len([x for x in str(rs[-1].get("attached") or "").split(",") if x.strip()]) or None
                    return remover.end_screen(p, target, n)
                elif task == T_CARDS:
                    n = len([x for x in str(rs[-1].get("attached") or "").split(",") if x.strip()]) or None
                    return remover.cards(p, target, n)
                elif task == T_COLLAB:
                    from report import _split_channel
                    wn, wid = _split_channel(rs[-1].get("weak") or "")
                    ww = dict(w)
                    if wid and wid != w.get("channel_id"):   # dòng ghi kênh cần kéo khác cấu hình hiện tại
                        ww = {"name": wn, "channel_id": wid, "url": f"https://www.youtube.com/channel/{wid}"}
                    return remover.collab(p, target, ww)
                elif task == T_PROFILE:
                    urls = []
                    for r in rs:
                        urls += [x.get("url") for x in _json_items(r) if x.get("url")]
                        m = re.search(r"Đã thêm đường liên kết: .* – (https?://\S+)", r.get("detail") or "")
                        if m:
                            urls.append(m.group(1))
                    return remover.profile_links(p, s["channel_id"], list(dict.fromkeys(urls)))
                elif task == T_HOME:
                    items = [x for r in rs for x in _json_items(r)]
                    if not items:
                        raise NeedsCheck("Nhật ký không ghi chi tiết phần Trang chủ đã làm – hãy gỡ tay.")
                    return remover.home(p, s["channel_id"], items, w)
                elif task == T_POST:
                    vt = []
                    for r in rs:
                        ids = [x.get("id") for x in _json_items(r) if x.get("id")] or \
                            re.findall(r"\(([\w-]{11})\)", r.get("detail") or "")
                        vt += [(v, "") for v in ids]
                    if not vt:
                        raise NeedsCheck("Nhật ký không ghi mã video của bài đăng – hãy gỡ tay.")
                    return remover.posts(p, s["channel_id"], list(dict.fromkeys(vt)))
                else:
                    raise NeedsCheck("Hạng mục này chưa hỗ trợ gỡ tự động – hãy gỡ tay.")
            try:
                # làm 1 lần duy nhất: mỗi mục đã tự kiểm tra ngay trên trang đang mở, không quay lại xem lần 2
                res = run_one()
                for r in rs:
                    t.set_removal(r["row"], REMOVE_DONE, "" if "đã sạch" not in res else res)
                ok += 1
                print(f"  ✅ Đã gỡ: {label} – {res}", flush=True)
            except remover.NotOurs as e:
                skip += 1
                for r in rs:
                    t.set_removal(r["row"], REMOVE_SKIP, str(e))
                print(f"  ⏭ Bỏ qua: {label} – {e}", flush=True)
            except NeedsCheck as e:
                manual += 1
                for r in rs:
                    t.set_removal(r["row"], REMOVE_MANUAL, str(e))
                _shot(p, "go_thu_cong", task, target, str(e))
                print(f"  ⚠️ Gỡ thủ công: {label}: {e}", flush=True)
            except Exception as e:
                bad += 1
                msg = str(e).splitlines()[0][:200]
                for r in rs:
                    t.set_removal(r["row"], REMOVE_ERROR, msg)
                _shot(p, "go_loi", task, target, msg)
                print(f"  ❌ Lỗi gỡ {label}: {msg}", flush=True)
            human_delay(cfg)
    print(f"\n🏁 Gỡ xong: {ok} mục sạch" + (f" · {skip} mục bỏ qua (không thuộc kênh mạnh này)" if skip else "")
          + f" · {manual} mục cần gỡ tay · {bad} mục lỗi"
          + (" – bấm lại 'Gỡ' để thử lại các mục lỗi." if bad else ""), flush=True)
    t.sync_google_sheet()
    make_report(t)


def cmd_record(cfg):
    import recorder
    urls = read_video_list(cfg)
    if not urls:
        sys.exit("❌ Danh sách video đang trống – hãy dán 1 link video của kênh mạnh vào ô Danh sách video.")
    print(f"Ghi thao tác mẫu trên video: {urls[0]}", flush=True)
    with Browsers(cfg) as b:
        ensure_login(b, "strong")
        recorder.record(b, "strong", ask, urls[0])
    recorder.pack()


def cmd_reply(cfg, a):
    """Trả lời bình luận khen của khán giả trên video kênh mạnh (cảm ơn đúng ngôn ngữ, tim, thích)."""
    import json
    import replier
    s = cfg["strong_channel"]
    sid = str(s.get("channel_id") or "")
    if not sid.startswith("UC"):
        sys.exit("❌ Kênh này chưa có mã kênh mạnh (UC...). Hãy điền ở trang Thông tin kênh.")
    ai = None
    if a.ai:
        try:
            import pt_ai
            import paths
            with open(os.path.join(paths.DATA, "pt_settings.json"),
                      encoding="utf-8") as f:
                st = json.load(f)
            prov = st.get("provider") or pt_ai.OLLAMA
            if prov != pt_ai.NO_AI and pt_ai.uses_ai(prov, st.get("key", "")):
                ai = (prov, st.get("model") or pt_ai.PROVIDERS.get(prov, ""), st.get("key", ""))
        except Exception:
            ai = None
        if ai and ai[0] == pt_ai.OLLAMA and pt_ai.ollama_ready(ai[1], log=lambda *x: None):   # "" = sẵn sàng
            print("(AI trên máy – Ollama – chưa chạy: tool tự phân loại, không dùng AI kiểm tra lại.)", flush=True)
            ai = None
        print("AI kiểm tra lại từng bình luận khen: " + (f"BẬT ({ai[0].split(' –')[0]})" if ai else "TẮT"),
              flush=True)
    opts = dict(videos=a.videos, max_per_video=a.max_per_video, max_replies=a.max_replies,
                reply=not a.no_reply, heart=not a.no_heart, like=not a.no_like, scope=a.scope,
                preview=a.preview, default_lang=a.lang, ai=ai, max_comments=a.max_comments)
    print(f"\n========== TRẢ LỜI BÌNH LUẬN – KÊNH MẠNH: {s.get('name')} ({sid}) ==========", flush=True)
    print("Chỉ bình luận KHEN mới được trả lời cảm ơn (đúng ngôn ngữ người viết). Câu hỏi, chê, góp ý, quảng cáo: "
          "tool KHÔNG trả lời – để bạn tự xem.", flush=True)
    with Browsers(cfg) as b:
        ensure_login(b, "strong")
        p = b.page("strong")
        import remover
        if not remover.verify_channel(p, sid):
            print(f"❌ Trình duyệt kênh mạnh không vào được kênh {sid} – tài khoản đang đăng nhập không có kênh này. "
                  f"Tool DỪNG, không trả lời gì.", flush=True)
            return
        print(f"✔ Đang dùng đúng kênh {s.get('name')} ({sid}) để trả lời.", flush=True)
        try:
            if a.community:
                import browser as _br
                cur = _br.studio_channel(p)
                if cur and cur != sid:
                    print(f"   · Studio đang ở kênh {cur} – chuyển về {sid}...", flush=True)
                    _br.select_channel(p, s, log=lambda m: print(m, flush=True))
                    cur = _br.studio_channel(p)
                if cur and cur != sid:
                    print(f"❌ Studio vẫn đang ở kênh {cur}, không phải {sid}. Tool DỪNG – không tương tác nhầm kênh.",
                          flush=True)
                    return
                import community
                print("\n----- CỘNG ĐỒNG (Studio): trả lời bình luận khen · tim HOẶC thích -----", flush=True)
                community.run(p, cfg, opts, log=lambda m: print(m, flush=True))
            else:
                replier.run(p, cfg, opts, log=lambda m: print(m, flush=True))
        except StepError as e:
            print(f"❌ {e}", flush=True)


def cmd_pack():
    import recorder
    recorder.pack()


def make_report(t):
    """Tạo lại file Excel đối soát (video kênh mạnh -> video được kéo, vị trí, trạng thái gỡ)."""
    try:
        import report
        path = report.build(t.saved_to, os.path.join(os.path.dirname(os.path.abspath(t.path)), report.OUT_NAME))
        if t.saved_to != t.path:
            print(f"⚠️ Nhật ký đang lưu tạm ở {os.path.basename(t.saved_to)} vì file Excel kết quả đang mở – đóng "
                  f"Excel / WPS để tool gộp lại (trang Kết quả của tool vẫn hiện đúng).", flush=True)
        if path:
            print(f"📑 File đối soát: {os.path.abspath(path)}", flush=True)
    except Exception as e:
        print(f"⚠️ Không tạo được file đối soát: {e}", flush=True)


def cmd_report(t, session=False):
    c = t.session if session else t.summary()
    print("\n===== TỔNG KẾT " + ("LẦN CHẠY NÀY" if session else "TẤT CẢ CÁC LẦN CHẠY") + " =====")
    for k in (STATUS_DONE, STATUS_CHECK, STATUS_ERROR):
        if k == STATUS_DONE or c.get(k, 0):   # dòng CẦN KIỂM TRA / LỖI chỉ hiện khi thật sự có
            print(f"  {k:<18} {c.get(k, 0)}")
    print(f"  Chi tiết: {t.path}")


def main():
    import paths
    paths.setup()   # làm việc trong du_lieu\ (kênh, đăng nhập, nhật ký...)
    ap = argparse.ArgumentParser(description="Tool kéo kênh YouTube")
    ap.add_argument("command", choices=["login", "setup-channel", "scan", "pull", "revert", "report",
                                        "record", "pack", "reply"])
    ap.add_argument("who", nargs="?", choices=["strong", "weak"], help="dùng với lệnh login")
    ap.add_argument("--only", nargs="+", choices=["comment", "endscreen", "cards", "collab"],
                    help="chỉ chạy một số bước khi pull")
    ap.add_argument("--force", action="store_true", help="làm lại cả những bước đã xong")
    ap.add_argument("--first", action="store_true", help="chỉ chạy trên video đầu tiên trong danh sách")
    ap.add_argument("--renew-setup", action="store_true",
                    help="bước 3: làm mới Hồ sơ, Trang chủ, Bài đăng (thay phần tool đã gắn lần trước)")
    ap.add_argument("--replace", action="store_true",
                    help="xóa màn hình kết thúc / thẻ cũ rồi gắn video mới")
    ap.add_argument("--hidden", action="store_true", help="ẩn trình duyệt khi chạy")
    ap.add_argument("--rows", default="", help="revert: chỉ gỡ các dòng này trong file kết quả, vd 5,8,9")
    ap.add_argument("--close-after", action="store_true", help="đóng trình duyệt sau khi xong (chạy nhiều kênh)")
    ap.add_argument("--config", default="config.yaml")
    ap.add_argument("--fresh", action="store_true", help="login: xóa sạch trình duyệt của kênh rồi đăng nhập lại")
    ap.add_argument("--detect", action="store_true", help="login: đọc lại tên + ID kênh từ profile GPM vừa chọn (ghi đè)")
    # reply: trả lời bình luận
    ap.add_argument("--videos", type=int, default=4, help="reply: số video (mới nhất, có bình luận mới) xử lý mỗi lượt")
    ap.add_argument("--max-per-video", type=int, default=0, help="reply: tối đa số bình luận đọc mỗi video (0 = hết)")
    ap.add_argument("--max-replies", type=int, default=0, help="reply: tối đa số câu trả lời mỗi lượt (0 = không giới hạn)")
    ap.add_argument("--no-reply", action="store_true")
    ap.add_argument("--no-heart", action="store_true")
    ap.add_argument("--no-like", action="store_true")
    ap.add_argument("--scope", choices=["praise", "all_ok"], default="praise",
                    help="tim/thích: chỉ bình luận khen, hoặc mọi bình luận không chê / không quảng cáo")
    ap.add_argument("--preview", action="store_true", help="reply: chỉ đọc và xếp loại, không làm gì trên YouTube")
    ap.add_argument("--lang", default="en", help="reply: ngôn ngữ trả lời khi không nhận ra (mã: en, vi, tl...)")
    ap.add_argument("--ai", action="store_true", help="reply: dùng AI (trang Phân tích video) kiểm tra lại")
    ap.add_argument("--community", action="store_true",
                    help="reply: làm ở trang Cộng đồng của Studio (bình luận của mọi video trên 1 trang)")
    ap.add_argument("--max-comments", type=int, default=100, help="reply --community: số bình luận mới nhất đọc mỗi lượt")
    a = ap.parse_args()

    cfg = load_cfg(a.config, validate=a.command == "pull")
    if a.hidden and a.command not in ("login",):
        cfg["headless"] = True
    elif a.command in ("login", "record"):
        cfg["headless"] = False  # đăng nhập & ghi thao tác luôn hiện cửa sổ
    # thay thế CHỈ khi bấm chạy có tích "Thay thế cái cũ" (bỏ qua giá trị cũ còn lưu trong file kênh)
    cfg.setdefault("end_screen", {})["replace_existing"] = False
    cfg.setdefault("cards", {})["replace_existing"] = False
    if a.replace:   # THAY THẾ CÁI CŨ: thay màn hình kết thúc, thẻ, bình luận ghim; làm lại cả bước đã xong
        cfg.setdefault("end_screen", {})["replace_existing"] = True
        cfg.setdefault("cards", {})["replace_existing"] = True
        a.force = True
        a.renew_setup = True
    if a.command == "login":
        if not a.who:
            sys.exit("Dùng: python main.py login strong|weak")
        return cmd_login(cfg, a.who, fresh=a.fresh, detect=a.detect)
    if a.command == "scan":
        return cmd_scan(cfg)
    if a.command == "record":
        return cmd_record(cfg)
    if a.command == "pack":
        return cmd_pack()
    if a.command == "reply":
        return cmd_reply(cfg, a)
    t = Tracker(cfg)
    {"setup-channel": lambda: cmd_setup(cfg, t, a.renew_setup),
     "pull": lambda: cmd_pull(cfg, t, a.only, a.force, a.first, a.close_after),
     "revert": lambda: cmd_revert(cfg, t, [int(x) for x in a.rows.split(",") if x.strip().isdigit()]
                                  if a.rows else None),
     "report": lambda: cmd_report(t)}[a.command]()


if __name__ == "__main__":
    main()
