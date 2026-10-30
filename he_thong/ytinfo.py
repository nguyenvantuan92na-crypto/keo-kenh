"""
Đọc thông tin 1 video (công khai / riêng tư / lên lịch / chủ kênh / độ dài) KHÔNG cần mở tab trên kênh.

Tool hỏi thẳng YouTube như một người xem ẩn danh (không đăng nhập, không phát video, không tính view),
nên không phải mở trang xem video hay trang Studio thêm lần nào chỉ để kiểm tra.
Kết quả được nhớ trong lượt chạy: mỗi video chỉ hỏi 1 lần.
"""
import json
import re
import urllib.error
import urllib.request

_CACHE = {}
_UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) "
       "Chrome/124.0 Safari/537.36")
_HEAD = {"User-Agent": _UA, "Accept-Language": "vi-VN,vi;q=0.9,en;q=0.8",
         "Cookie": "CONSENT=YES+1; SOCS=CAI; PREF=hl=vi"}


def _get(url, timeout=20):
    req = urllib.request.Request(url, headers=_HEAD)
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return r.status, r.read().decode("utf-8", "replace")


def _player(html):
    m = re.search(r"ytInitialPlayerResponse\s*=\s*\{", html or "")
    if not m:
        return None
    try:
        return json.JSONDecoder().raw_decode(html, m.end() - 1)[0]
    except ValueError:
        return None


def _browser_get(page, url):
    """Dự phòng khi máy không hỏi thẳng được: gửi yêu cầu nền qua trình duyệt (KHÔNG mở tab, không phát video)."""
    r = page.context.request.get(url, headers={"Accept-Language": "vi-VN,vi;q=0.9"}, timeout=20000)
    return r.status, r.text()


def _parse(html):
    """Đọc trạng thái từ trang xem video. Trả về dict, hoặc None nếu không có dữ liệu trình phát."""
    p = _player(html)
    if not p:
        return None
    ps, vd = p.get("playabilityStatus") or {}, p.get("videoDetails") or {}
    mf = (p.get("microformat") or {}).get("playerMicroformatRenderer") or {}
    d = dict(status=ps.get("status") or "", reason=(ps.get("reason") or "").strip(),
             owner=vd.get("channelId") or mf.get("externalChannelId") or "",
             private=bool(vd.get("isPrivate")), upcoming=bool(vd.get("isUpcoming")),
             unlisted=bool(mf.get("isUnlisted")), title=vd.get("title") or "", length=0.0)
    try:
        d["length"] = float(vd.get("lengthSeconds") or mf.get("lengthSeconds") or 0)
    except ValueError:
        pass
    if d["private"] or d["upcoming"] or d["unlisted"]:
        d["ok"] = False                       # chắc chắn: YouTube ghi rõ riêng tư / lên lịch / không công khai
    elif d["status"] == "OK":
        d["ok"] = True
    elif re.search(r"private|riêng tư", d["reason"], re.I):
        d["ok"], d["private"] = False, True
    elif d["status"] in ("ERROR", "UNPLAYABLE") and re.search(
            r"unavailable|not available|no longer|isn't available|does not exist|removed|deleted|"
            r"không có sẵn|không còn|không tồn tại|đã bị xóa|đã bị xoá|đã xóa|đã xoá|bị gỡ", d["reason"], re.I):
        d["ok"] = False
    else:
        d["ok"] = None                        # vd "Đăng nhập để xác nhận bạn không phải là bot" -> CHƯA biết
    return d


def info(vid, page=None):
    """{'ok': True/False/None, 'status', 'owner', 'private', 'upcoming', 'unlisted', 'length', 'title', 'reason'}
    Hỏi nền (KHÔNG mở tab): ưu tiên qua phiên đăng nhập của trình duyệt kênh (YouTube trả lời chính xác),
    rồi mới hỏi ẩn danh. ok=None: chưa biết chắc -> người gọi GIỮ video, không loại oan."""
    if vid in _CACHE:
        return _CACHE[vid]
    d = dict(ok=None, status="", owner="", private=False, upcoming=False, unlisted=False, length=0.0,
             title="", reason="")
    url = f"https://www.youtube.com/watch?v={vid}&hl=vi&has_verified=1"
    ways = ([lambda: _browser_get(page, url)] if page is not None else []) + [lambda: _get(url)]
    for way in ways:
        try:
            _st, html = way()
        except Exception:
            continue
        r = _parse(html)
        if r is None:
            continue
        if not d["owner"] and r.get("owner"):
            d["owner"] = r["owner"]
        if r["ok"] is not None:
            d.update(r)
            break
        if not d["status"]:
            d.update({k: v for k, v in r.items() if k != "owner" or v})
    if d["ok"] is None:
        o = _oembed(vid)
        if o.get("ok"):
            d.update(o)
    if d["ok"] is not None:
        _CACHE[vid] = d
    return d


def _oembed(vid):
    """Dự phòng: oEmbed trả 200 khi video xem được công khai. Lỗi khác -> không kết luận (có thể chỉ là chặn nhúng)."""
    try:
        _st, body = _get("https://www.youtube.com/oembed?format=json&url=https://www.youtube.com/watch?v=" + vid)
        return dict(ok=True, status="OK", title=(json.loads(body).get("title") or ""))
    except Exception:
        return {}


def why_not_public(d):
    if d.get("upcoming"):
        return "đang lên lịch / công chiếu chưa mở"
    if d.get("private"):
        return "riêng tư (hoặc đã lên lịch, chưa công khai)"
    if d.get("unlisted"):
        return "không công khai"
    return (d.get("reason") or d.get("status") or "không xem được")[:60]


def public_status(vid, page=None):
    """(trạng thái, mã chủ kênh) giống cách cũ: 'OK' / 'ERROR' / 'UNPLAYABLE' / 'LOGIN_REQUIRED' / ''."""
    d = info(vid, page)
    return d.get("status") or "", d.get("owner") or ""


def clear():
    _CACHE.clear()
