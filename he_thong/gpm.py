"""
Kết nối GPM-Login: tool mở THẲNG profile trình duyệt có sẵn trong GPM-Login (đúng dấu vân tay + proxy của profile
đó) rồi điều khiển qua cổng gỡ lỗi mà GPM trả về.

API cục bộ của GPM-Login (mặc định http://127.0.0.1:19995, đổi được trong Cài đặt của GPM và trong tool):
  · mở profile  : GET /api/v3/profiles/start/{id}  -> data.remote_debugging_address ("127.0.0.1:cổng")
  · danh sách   : GET /api/v3/profiles?page=1&per_page=…  (dự phòng /api/v1/profiles)
  · đóng profile: GET /api/v3/profiles/close/{id}            (dự phòng /api/v1/profiles/stop/{id})
Mỗi lời gọi có đường dự phòng và đọc kết quả linh hoạt; tool KHÔNG dùng / gửi mật khẩu gì cả.
"""
import json
import os
import urllib.error
import urllib.parse
import urllib.request

import paths

DEFAULT_API = "http://127.0.0.1:19995"


def api_base():
    try:
        with open(os.path.join(paths.DATA, "ui_settings.json"), encoding="utf-8") as f:
            v = str(json.load(f).get("gpm_api") or "").strip()
    except Exception:
        v = ""
    v = v or DEFAULT_API
    if not v.startswith("http"):
        v = "http://" + v
    return v.rstrip("/")


def api_key():
    """Mã kết nối của CẦU NỐI GPM (khi GPM-Login nằm ở máy khác). Trống = GPM trên chính máy này."""
    try:
        with open(os.path.join(paths.DATA, "ui_settings.json"), encoding="utf-8") as f:
            return str(json.load(f).get("gpm_key") or "").strip()
    except Exception:
        return ""


def _get(path, base=None, timeout=60):
    url = (base or api_base()) + path
    head = {"Accept": "application/json"}
    if api_key():
        head["X-Keo-Key"] = api_key()
    req = urllib.request.Request(url, headers=head)
    try:
        r = urllib.request.urlopen(req, timeout=timeout)
    except urllib.error.HTTPError as e:
        if e.code == 403:
            raise GPMError("Sai MÃ KẾT NỐI cầu nối GPM – xem lại mã hiện trên cửa sổ Cầu nối ở máy có GPM-Login.")
        raise
    with r:
        body = r.read().decode("utf-8", "replace")
    try:
        return json.loads(body)
    except ValueError:
        return {"_raw": body}


class GPMError(Exception):
    pass


def _ok(res):
    return isinstance(res, dict) and res.get("success") is not False and "_raw" not in res


def _items(res):
    """Danh sách profile trong kết quả (data là list, hoặc data.data / data.items / data.profiles)."""
    d = res.get("data") if isinstance(res, dict) else None
    if isinstance(d, dict):
        for k in ("data", "items", "profiles", "list"):
            if isinstance(d.get(k), list):
                return d[k]
    return d if isinstance(d, list) else []


def ping(base=None):
    """(True, số profile) nếu GPM-Login đang mở và trả lời; (False, lý do) nếu không."""
    try:
        return True, len(list_profiles(base))
    except GPMError as e:
        return False, str(e)


def list_profiles(base=None):
    """[{id, name, note, group}] – mọi profile trong GPM-Login (đọc hết các trang)."""
    errs = []
    for path in ("/api/v3/profiles?page={p}&per_page=200&sort=0", "/api/v1/profiles?page={p}&page_size=200"):
        out, ok = [], False
        try:
            for page in range(1, 51):
                res = _get(path.format(p=page), base)
                if not _ok(res):
                    errs.append(f"{path.split('?')[0]}: {str(res.get('message') or res)[:80]}")
                    break
                ok = True
                items = _items(res)
                for it in items:
                    pid = str(it.get("id") or it.get("profile_id") or "")
                    if pid:
                        out.append({"id": pid, "name": str(it.get("name") or it.get("profile_name") or pid),
                                    "note": str(it.get("note") or ""),
                                    "group": str(it.get("group_name") or it.get("group_id") or "")})
                if len(items) < 200:
                    break
        except GPMError:
            raise
        except Exception as e:
            errs.append(f"{path.split('?')[0]}: {str(e)[:80]}")
            continue
        if ok:
            seen, uniq = set(), []
            for it in out:
                if it["id"] not in seen:
                    seen.add(it["id"])
                    uniq.append(it)
            return uniq
    raise GPMError("Không kết nối được GPM-Login tại " + (base or api_base()) +
                   " – hãy mở phần mềm GPM-Login (và kiểm tra cổng API trong Cài đặt của GPM). Chi tiết: "
                   + " | ".join(errs)[:200])


def start(pid, base=None):
    """Mở profile GPM `pid`, trả về địa chỉ điều khiển 'http://127.0.0.1:cổng'."""
    errs = []
    for path in (f"/api/v3/profiles/start/{urllib.parse.quote(pid)}",
                 f"/api/v1/profiles/start/{urllib.parse.quote(pid)}"):
        try:
            res = _get(path, base, timeout=120)
        except GPMError:
            raise
        except Exception as e:
            errs.append(f"{path}: {str(e)[:80]}")
            continue
        d = res.get("data") if isinstance(res, dict) else None
        if not _ok(res) or not isinstance(d, dict):
            errs.append(f"{path}: {str((res or {}).get('message') or res)[:100]}")
            continue
        addr = str(d.get("remote_debugging_address") or "").strip()
        if not addr and d.get("remote_debugging_port"):
            addr = f"127.0.0.1:{d['remote_debugging_port']}"
        if not addr and d.get("websocket_debugging_url"):
            u = urllib.parse.urlparse(str(d["websocket_debugging_url"]))
            addr = u.netloc
        if addr:
            return addr if addr.startswith("http") else "http://" + addr
        errs.append(f"{path}: GPM không trả địa chỉ điều khiển")
    raise GPMError("GPM-Login chưa mở được profile " + pid + ": " + " | ".join(errs)[:250])


def wait_ready(addr, seconds=45):
    """Chờ trình duyệt GPM vừa mở thật sự nhận điều khiển (trang /json/version trả về). True = sẵn sàng."""
    import time
    url = addr.rstrip("/") + "/json/version"
    end = time.time() + seconds
    while time.time() < end:
        try:
            with urllib.request.urlopen(urllib.request.Request(url), timeout=5) as r:
                if r.status == 200 and b"webSocketDebuggerUrl" in r.read():
                    return True
        except Exception:
            pass
        time.sleep(1)
    return False


def close(pid, base=None):
    for path in (f"/api/v3/profiles/close/{urllib.parse.quote(pid)}",
                 f"/api/v1/profiles/stop/{urllib.parse.quote(pid)}"):
        try:
            if _ok(_get(path, base, timeout=30)):
                return True
        except Exception:
            continue
    return False


def profile_of(ch):
    """Mã profile GPM gắn với kênh (ô 'Profile GPM-Login' ở trang Thông tin kênh), '' nếu dùng trình duyệt riêng."""
    return str((ch or {}).get("gpm_profile_id") or "").strip()
