"""
Chế độ "Kéo cho chính kênh": 1 kênh tự đẩy view cho video của chính nó.

- Video đang có view của kênh (Danh sách video) = nơi gắn.
- Video cần đẩy view = (a) các link bạn dán, (b) video mới nhất của kênh, hoặc
  (c) tự chọn video ÍT VIEW NHẤT trong 20 video mới nhất.
- Không bao giờ gắn 1 video vào chính nó (màn hình kết thúc, thẻ, bình luận ghim).
- Bỏ các bước không hợp lệ khi chỉ có 1 kênh: Cộng tác, Kênh nổi bật.
- Chỉ 1 kênh, 1 trình duyệt, đăng nhập 1 lần ("kênh cần kéo" dùng chung với kênh mạnh).
"""
import re

SELF = "self"
TARGET_LINKS, TARGET_NEWEST, TARGET_LEAST = "links", "newest", "least_views"
TARGET_LABELS = {TARGET_LINKS: "Video tôi dán link bên dưới",
                 TARGET_NEWEST: "Video mới nhất của kênh",
                 TARGET_LEAST: "Tự chọn video ít view nhất (trong 20 video mới nhất)"}


def is_self(cfg):
    return (cfg or {}).get("mode") == SELF


def vid_of(link):
    m = re.search(r"(?:v=|youtu\.be/|/shorts/|/live/)([\w-]{11})", str(link or ""))
    return m.group(1) if m else ""


def apply(cfg):
    """Chuẩn hóa cấu hình chế độ 1 kênh (gọi khi đọc file kênh). Không đổi gì ở chế độ 2 kênh."""
    if not is_self(cfg):
        return cfg
    s = cfg.setdefault("strong_channel", {})
    w = cfg.setdefault("weak_channel", {})
    cid = str(s.get("channel_id") or "")
    w["name"] = s.get("name") or w.get("name") or ""
    w["channel_id"] = cid
    w["url"] = f"https://www.youtube.com/channel/{cid}" if cid else (w.get("url") or "")
    if s.get("profile_dir"):
        w["profile_dir"] = s["profile_dir"]          # 1 kênh = 1 trình duyệt
    target = cfg.get("self_target") or TARGET_LINKS
    cfg["self_target"] = target
    cfg["video_source"] = "own_newest" if target == TARGET_NEWEST else "weak"
    cfg.setdefault("collab", {})["enabled"] = False   # không thể cộng tác với chính mình
    st = cfg.setdefault("strong_setup", {})
    st["do_featured_channel"] = False                 # kênh nổi bật = chính mình: vô nghĩa
    if not str(st.get("profile_link_url") or "").strip():
        first = "" if target == TARGET_NEWEST else next((v for v in (w.get("videos") or []) if vid_of(v)), "")
        if first:
            st["profile_link_url"] = first            # Hồ sơ trỏ tới video cần đẩy
        else:
            st["do_profile_link"] = False             # không có video cụ thể -> bỏ (trỏ về chính kênh là thừa)
    return cfg


def for_video(cfg, w, vid):
    """Bản sao thông tin 'kênh cần kéo' dùng cho 1 video: bỏ chính video đó khỏi danh sách cần đẩy."""
    if not is_self(cfg) and w.get("_owner") != "strong":
        return w
    wv = dict(w)
    wv["videos"] = [v for v in (w.get("videos") or []) if vid_of(v) and vid_of(v) != vid]
    return wv


def nothing_to_attach(cfg, wv):
    """Chế độ 1 kênh, đẩy theo link: video đang xét chính là video cần đẩy duy nhất -> không còn gì để gắn."""
    return (is_self(cfg) or wv.get("_owner") == "strong") and not wv.get("videos")


# ------------------------------------------------------------------ tự chọn video ít view nhất
VIEWS_JS = r"""() => {
  const out = [], seen = new Set();
  const items = document.querySelectorAll('ytd-rich-item-renderer, ytd-grid-video-renderer, yt-lockup-view-model');
  for (const it of items) {
    const a = it.querySelector('a#video-title-link, a#video-title, a[href*="watch?v="]');
    const m = ((a && a.getAttribute('href')) || '').match(/[?&]v=([\w-]{11})/);
    if (!m || seen.has(m[1])) continue;
    seen.add(m[1]);
    const t = it.querySelector('#video-title, h3, [title]');
    // chỉ đọc dòng thông tin (lượt xem · ngày đăng), không đọc tiêu đề (tránh lẫn số trong tiêu đề)
    const spans = [...it.querySelectorAll('#metadata-line span, .inline-metadata-item, ' +
                   'yt-content-metadata-view-model span, .yt-content-metadata-view-model-wiz__metadata-text')]
                   .map(e => (e.innerText || e.textContent || '').trim()).filter(Boolean);
    const title = ((t && (t.getAttribute('title') || t.textContent)) || '').trim();
    let meta = spans.join(' | ');
    if (!meta) meta = (it.innerText || '').replace(title, ' ');
    out.push({id: m[1], title, meta: meta.replace(/\s+/g, ' ')});
  }
  return out; }"""


def parse_views(text):
    """'1,2 N lượt xem' / '3,4 Tr lượt xem' / '987 lượt xem' / '1.2K views' / 'No views' -> số view (hoặc None)."""
    t = str(text or "")
    if re.search(r"(Chưa có lượt xem|No views)", t, re.I):
        return 0
    m = re.search(r"(\d{1,3}(?:[.,\s]\d{3})+|\d+(?:[.,]\d+)?)\s*(N|K|Tr|M|B|tỷ)?\s*(?:lượt xem|views?)", t, re.I)
    if not m:
        return None
    num, unit = m.group(1).strip(), (m.group(2) or "").lower()
    if unit:
        try:
            val = float(num.replace(" ", "").replace(",", "."))
        except ValueError:
            return None
        return int(val * {"n": 1e3, "k": 1e3, "tr": 1e6, "m": 1e6, "b": 1e9, "tỷ": 1e9}[unit])
    digits = re.sub(r"[.,\s]", "", num)
    return int(digits) if digits.isdigit() else None


def pick_least_viewed(page, channel_id, n=3, newest=20, log=print):
    """Trong `newest` video mới nhất của kênh chọn `n` video CÔNG KHAI ít view nhất. Trả về list link."""
    items = _channel_items(page, channel_id, want=newest, rounds=6)
    rows = []
    for it in items[:newest]:
        v = parse_views(it["meta"])
        if v is not None:
            rows.append((v, it))
    if not rows:
        return []
    rows.sort(key=lambda r: r[0])
    views = {it["id"]: v for v, it in rows}
    pick = _first_public(page, [it for _v, it in rows], max(1, n), log=log)
    for it in pick:
        log(f"   · chọn video ít view: {it['title'][:60]} ({views[it['id']]:,} view) – {it['id']}".replace(",", "."))
    return [f"https://www.youtube.com/watch?v={it['id']}" for it in pick]


_AGE_UNITS = [(r"giây|second", 1 / 86400), (r"phút|minute", 1 / 1440), (r"giờ|hour", 1 / 24), (r"ngày|day", 1),
              (r"tuần|week", 7), (r"tháng|month", 30), (r"năm|year", 365)]


def parse_age_days(text):
    """'3 ngày trước' / '5 giờ trước' / '1 tuần trước' / '2 weeks ago' -> số ngày (hoặc None)."""
    t = str(text or "").lower()
    for rx, mult in _AGE_UNITS:
        m = re.search(r"(\d+)\s*(?:" + rx + r")", t)
        if m:
            return int(m.group(1)) * mult
    return None


def home_auto(page, channel_id, log=print, days=7):
    """Tự chọn video cho Thẻ Trang chủ (chế độ 1 kênh) – CHỈ video công khai đã phát hành:
    - Video giới thiệu (người chưa ĐK) = video công khai MỚI NHẤT của kênh;
    - Video nổi bật (người ĐK cũ) = video công khai NHIỀU VIEW NHẤT trong `days` ngày gần nhất
      (không có video nào trong khoảng đó -> nhiều view nhất trong 20 video mới nhất).
    Trả về (link_giới_thiệu, link_nổi_bật) – "" nếu không đọc được."""
    items = _channel_items(page, channel_id, want=20)
    if not items:
        return "", ""
    link = lambda i: f"https://www.youtube.com/watch?v={i}"
    first = _first_public(page, items, 1, log=log)
    if not first:
        return "", ""
    newest = first[0]
    log(f"   · Video giới thiệu = video công khai mới nhất: {newest['title'][:60]} ({newest['id']})")
    rows = [(parse_views(it["meta"]), parse_age_days(it["meta"]), it) for it in items[:20]]
    recent = [(v, it) for v, age, it in rows if v is not None and age is not None and age <= days]
    pool, why = recent, f"trong {days} ngày gần nhất"
    if not pool:
        pool = [(v, it) for v, _a, it in rows if v is not None]
        why = f"(không có video nào trong {days} ngày – lấy trong 20 video mới nhất)"
    others = [r for r in pool if r[1]["id"] != newest["id"]]
    if others:   # 2 ô Trang chủ không trùng 1 video
        pool = others
    pool = sorted(pool, key=lambda r: -r[0])
    views = {it["id"]: v for v, it in pool}
    top = _first_public(page, [it for _v, it in pool], 1, log=log)
    if not top:
        return link(newest["id"]), ""
    top = top[0]
    log(f"   · Video nổi bật = nhiều view nhất {why}: {top['title'][:60]} ({views[top['id']]:,} view) – {top['id']}"
        .replace(",", "."))
    return link(newest["id"]), link(top["id"])


def newest_video(page, channel_id, log=print):
    """Link video CÔNG KHAI mới nhất của kênh (dùng soạn bình luận ghim tự động)."""
    got = public_newest(page, channel_id, 1, log=log)
    return got[0] if got else ""


def auto_comment(link):
    """Bình luận ghim mặc định khi bạn để trống (chế độ 1 kênh)."""
    return f"▶ Xem tiếp video mới của kênh: {link}\n" if link else ""


# ------------------------------------------------------------------ chỉ lấy video CÔNG KHAI đã phát hành
# Video đang lên lịch / riêng tư / không công khai / công chiếu chưa mở mà gắn vào thẻ -> tam giác vàng,
# vào màn hình kết thúc -> "Đây là video riêng tư". Mọi video tool tự chọn đều phải qua bộ lọc này.
UPCOMING_RX = re.compile(r"(Đã lên lịch|Lên lịch|Scheduled|Công chiếu|Premiere|Sắp ra mắt|Sắp phát|Upcoming|"
                         r"đang chờ|waiting|Riêng tư|Private|Không công khai|Unlisted)", re.I)

def video_public(page, vid):
    """Video có CÔNG KHAI và ĐÃ PHÁT HÀNH không – hỏi nền (không mở tab xem video, không tính view).
    Trả về (True/False/None, lý do). None = không hỏi được -> người gọi tự quyết."""
    import ytinfo
    d = ytinfo.info(vid, page)
    if d.get("ok") is None:
        return None, "không đọc được trạng thái video"
    return (True, "công khai") if d["ok"] else (False, ytinfo.why_not_public(d))


def feed_items(page, channel_id):
    """[(mã video, số view)] của ~15 video mới nhất – đọc nguồn tin (RSS) của kênh bằng yêu cầu nền, KHÔNG mở tab."""
    import ytinfo
    url = f"https://www.youtube.com/feeds/videos.xml?channel_id={channel_id}"
    body = ""
    for way in ((lambda: ytinfo._browser_get(page, url)) if page is not None else None, lambda: ytinfo._get(url)):
        if way is None:
            continue
        try:
            _st, body = way()
            if "<entry" in body:
                break
        except Exception:
            continue
    out = []
    for e in re.findall(r"<entry>([\s\S]*?)</entry>", body or ""):
        v = re.search(r"<yt:videoId>([\w-]{11})</yt:videoId>", e)
        n = re.search(r'<media:statistics views="(\d+)"', e)
        if v:
            out.append((v.group(1), int(n.group(1)) if n else None))
    return out


_ITEMS = {}   # tab Video của kênh đã đọc trong lượt chạy này -> không mở lại tab đó lần nữa


def _channel_items(page, channel_id, want=20, rounds=4):
    """Đọc tab Video của kênh 1 LẦN mỗi lượt chạy (cuộn đủ 20 video rồi nhớ lại)."""
    if channel_id in _ITEMS:
        return list(_ITEMS[channel_id])
    want, rounds = max(want, 20), max(rounds, 6)
    page.goto(f"https://www.youtube.com/channel/{channel_id}/videos", wait_until="domcontentloaded")
    page.wait_for_timeout(5000)
    items = []
    for _ in range(rounds):
        items = page.evaluate(VIEWS_JS)
        if len(items) >= want:
            break
        page.mouse.wheel(0, 3000)
        page.wait_for_timeout(1500)
    # bỏ ngay những video mà dòng thông tin đã ghi rõ là lên lịch / công chiếu / riêng tư
    items = [it for it in items if not UPCOMING_RX.search(it.get("meta") or "")]
    if items:
        _ITEMS[channel_id] = items
    return list(items)


def _first_public(page, items, n, exclude=(), log=print, why=""):
    """Duyệt `items` theo thứ tự, giữ `n` video kiểm tra được là công khai."""
    out = []
    for it in items:
        if len(out) >= n:
            break
        if it["id"] in exclude:
            continue
        ok, reason = video_public(page, it["id"])
        if ok is False:
            log(f"   ↷ bỏ {it['title'][:50]} ({it['id']}) – {reason}")
            continue
        out.append(it)
    return out


def public_newest(page, channel_id, n=3, exclude=(), log=print):
    """`n` video MỚI PHÁT HÀNH gần nhất ở chế độ CÔNG KHAI của kênh (bỏ video lên lịch / riêng tư /
    không công khai / công chiếu chưa mở). Trả về list link."""
    items = _channel_items(page, channel_id, want=n + 6)
    pick = _first_public(page, items, n, exclude, log)
    for it in pick:
        log(f"   · video công khai mới nhất: {it['title'][:60]} – {it['id']}")
    return [f"https://www.youtube.com/watch?v={it['id']}" for it in pick]


def filter_public(page, links, log=print):
    """Lọc các link bạn dán: chỉ giữ video công khai đã phát hành."""
    out = []
    for l in links or []:
        v = vid_of(l) or (str(l).strip() if re.fullmatch(r"[\w-]{11}", str(l).strip()) else "")
        if not v:
            out.append(l)
            continue
        ok, reason = video_public(page, v)
        if ok is False:
            log(f"   ↷ bỏ {l} – {reason} (gắn vào sẽ hiện tam giác vàng / 'video riêng tư')")
            continue
        out.append(l)
    return out
