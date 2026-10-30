"""
Danh sách phát của kênh cần kéo – dùng cho Màn hình kết thúc và Thẻ.

· Ô "Danh sách phát" (phần ② Kênh cần kéo) có link -> dùng ĐÚNG link đó.
· Ô trống -> tool tự chọn danh sách phát CÔNG KHAI có nhiều video nhất của kênh cần kéo
  (đọc nền trang /playlists của kênh + nguồn RSS của từng danh sách – không mở tab nào).
Mọi thông tin đọc từ YouTube, không đoán: không đọc được thì báo rõ và bỏ phần danh sách phát.
"""
import re
import urllib.request

ID_RE = re.compile(r"(?:[?&]list=)?((?:PL|OL|UU|FL|LL)[\w-]{10,})")


def pid_of(url):
    m = re.search(r"[?&]list=([\w-]{10,})", str(url or "")) or re.fullmatch(r"\s*((?:PL|OL|UU)[\w-]{10,})\s*",
                                                                             str(url or ""))
    return m.group(1) if m else ""


def url_of(pid):
    return f"https://www.youtube.com/playlist?list={pid}" if pid else ""


def _get(page, url):
    """Tải nền (dùng phiên trình duyệt nếu có, không mở tab); trả về chữ hoặc ''."""
    try:
        if page is not None:
            r = page.context.request.get(url, timeout=20000, headers={"Accept-Language": "vi-VN,vi;q=0.9"})
            return r.text() if r.ok else ""
    except Exception:
        pass
    try:
        req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0", "Accept-Language": "vi-VN,vi"})
        with urllib.request.urlopen(req, timeout=20) as f:
            return f.read().decode("utf-8", "replace")
    except Exception:
        return ""


def feed_info(page, pid):
    """(số video đọc được – tối đa 15, tên danh sách phát) từ nguồn RSS công khai. (0, '') = không đọc được /
    danh sách riêng tư / trống."""
    xml = _get(page, f"https://www.youtube.com/feeds/videos.xml?playlist_id={pid}")
    if "<feed" not in xml:
        return 0, ""
    m = re.search(r"<title>([^<]*)</title>", xml)
    import html
    return xml.count("<entry>"), html.unescape(m.group(1)).strip() if m else ""


def channel_playlist_ids(page, cid):
    html_ = _get(page, f"https://www.youtube.com/channel/{cid}/playlists?view=1&hl=vi")
    ids = re.findall(r'"playlistId":"((?:PL|OL)[\w-]{10,})"', html_) or \
        re.findall(r"list=((?:PL|OL)[\w-]{10,})", html_)
    return list(dict.fromkeys(ids))


def choose(page, weak, log=print):
    """{'id','url','title','count','auto'} hoặc None. Không có danh sách phát công khai nào -> None (có báo lý do)."""
    given = pid_of(weak.get("playlist"))
    if given:
        n, title = feed_info(page, given)
        if not n:
            log(f"   ⚠️ Danh sách phát bạn dán ({given}) không đọc được video nào – có thể đang riêng tư / trống. "
                f"Vẫn thử gắn đúng link này.")
        return {"id": given, "url": url_of(given), "title": title, "count": n, "auto": False}
    cid = str(weak.get("channel_id") or "")
    if not cid.startswith("UC"):
        log("   ⚠️ Chưa có ID kênh cần kéo – không tự tìm được danh sách phát.")
        return None
    best = None
    for pid in channel_playlist_ids(page, cid)[:8]:
        n, title = feed_info(page, pid)
        if n and (best is None or n > best["count"]):
            best = {"id": pid, "url": url_of(pid), "title": title, "count": n, "auto": True}
    if best:
        log(f"   · danh sách phát tự chọn: '{best['title']}' ({best['id']}) – {best['count']}"
            f"{'+' if best['count'] >= 15 else ''} video")
        return best
    log("   ⚠️ Kênh cần kéo chưa có danh sách phát CÔNG KHAI nào – bỏ phần danh sách phát. "
        "(Tạo 1 danh sách phát công khai trên kênh, hoặc dán link vào ô Danh sách phát.)")
    return None
