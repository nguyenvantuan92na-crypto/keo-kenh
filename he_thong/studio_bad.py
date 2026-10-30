"""
Ghi nhớ video mà YouTube Studio KHÔNG mở được trang "Chi tiết video" (Studio tự báo "Rất tiếc, đã xảy ra lỗi"
dù kênh đúng). Đây là lỗi phía YouTube với riêng video đó – không phải tool chọn sai kênh.

- Trong lượt chạy: video đã lỗi thì không mở lại cho Thẻ / Cộng tác (tránh báo lỗi lặp lại, mất thời gian).
- Giữa các lượt: nhớ 3 ngày (studio_loi.json) -> danh sách video do tool tự chọn sẽ lấy video khác thay.
  Sau 3 ngày tool thử lại video đó (YouTube có thể đã sửa).
"""
import json
import os
import time

import paths

DAYS = 3
NOW = set()   # video lỗi Studio trong lượt chạy này


def _file():
    return os.path.join(paths.DATA, "studio_loi.json")


def _load():
    try:
        with open(_file(), encoding="utf-8") as f:
            return json.load(f) or {}
    except Exception:
        return {}


def mark(vid, channel=""):
    NOW.add(vid)
    d = _load()
    e = d.get(vid) or {"n": 0}
    e.update(n=int(e.get("n", 0)) + 1, at=time.time(), ch=channel)
    d[vid] = e
    try:
        with open(_file(), "w", encoding="utf-8") as f:
            json.dump(d, f, ensure_ascii=False, indent=1)
    except Exception:
        pass


def is_bad(vid):
    """True: Studio không mở được video này trong lượt này, hoặc trong 3 ngày gần đây."""
    if vid in NOW:
        return True
    e = _load().get(vid)
    return bool(e) and time.time() - float(e.get("at", 0)) < DAYS * 86400


def forget(vid):
    NOW.discard(vid)
    d = _load()
    if d.pop(vid, None) is not None:
        try:
            with open(_file(), "w", encoding="utf-8") as f:
                json.dump(d, f, ensure_ascii=False, indent=1)
        except Exception:
            pass
