"""
Biểu mẫu .txt để điền thông tin 1 bộ kênh (mở bằng Notepad), và đọc ngược biểu mẫu đã điền vào tool.
Cùng 1 hàm build() tạo cả biểu mẫu trống, ví dụ đã điền và bản xuất từ kênh đang chọn -> luôn khớp với bộ đọc.
"""
import os
import re

BASE = os.path.dirname(os.path.abspath(__file__))
import paths   # noqa: E402
FORM_DIR = paths.FORMS

# (khóa, nhãn) – nhãn in trong biểu mẫu
TOP = [("job_name", "Tên hiển thị trong tool")]
STRONG = [("s_name", "Tên kênh mạnh"), ("s_id", "ID kênh mạnh (UC...)")]
WEAK = [("w_url", "Link kênh"), ("w_name", "Tên kênh"), ("w_id", "ID kênh (UC...)"),
        ("w_pl", "Link danh sách phát")]
STEP3 = [("sp_link_title", "Hồ sơ → Đường liên kết: Tiêu đề"),
         ("sp_link_url", "Hồ sơ → Đường liên kết: URL"),
         ("sp_trailer", "Video giới thiệu kênh cho người chưa đăng ký (1 link video)"),
         ("sp_featured", "Video nổi bật dành cho người đăng ký cũ (1 link video)"),
         ("post_videos", "Bài đăng có video (mỗi dòng 1 link = 1 bài đăng)"),
         ("post_text", "Nội dung chữ của bài đăng (không bắt buộc)")]
STEP3_DO = [("do_profile_link", "Đường liên kết Hồ sơ"), ("do_trailer", "Video giới thiệu (người chưa ĐK)"),
            ("do_featured", "Video nổi bật (người ĐK cũ)"), ("do_playlist", "Danh sách phát đơn"),
            ("do_featured_channel", "Kênh nổi bật"), ("do_posts", "Bài đăng có video")]
OPTIONS = [("post_source", "Video đăng lên Bài đăng (Video mới nhất của kênh mạnh / Theo các link)"),
           ("browser", "Trình duyệt (Cốc Cốc / Chrome)"),
           ("source", "Video đưa vào màn hình kết thúc & thẻ (Video của kênh cần kéo / Video mới nhất của kênh mạnh)"),
           ("es_count", "Số video ở màn hình kết thúc (1 / 2)"),
           ("card_count", "Số thẻ video (1–5)"),
           ("start_min", "Thẻ đầu tiên ở phút"),
           ("interval", "Khoảng cách giữa các thẻ (phút)"),
           ("delay", "Nghỉ ngẫu nhiên giữa các thao tác (giây, từ – đến)"),
           ("speed", "Tốc độ chuột & gõ phím (Nhanh / Vừa / Chậm)"),
           ("max_videos", "Số video kéo tối đa mỗi lần chạy (0 = tất cả)"),
           ("min_views", "Ngưỡng lọc video (view / 60 phút)"),
           ("collab", "Bật tính năng cộng tác (Có / Không)"),
           ("replace", "Thay thế màn hình kết thúc / thẻ đã có – XÓA cái cũ (Có / Không)")]

H_STRONG = "--- KÊNH MẠNH (dùng để kéo) ---"
H_WEAK = "--- KÊNH CẦN KÉO ---"
H_WVID = "--- VIDEO CẦN KÉO VIEW (của kênh cần kéo – mỗi dòng 1 link, bao nhiêu cũng được) ---"
H_SVID = "--- VIDEO CỦA KÊNH MẠNH DÙNG ĐỂ KÉO (mỗi dòng 1 link, để trống = tool tự tìm ở bước 4) ---"
H_STEP3 = "--- TÙY CHỈNH KÊNH MẠNH (BƯỚC 3) ---"
H_OPT = "--- TÙY CHỌN (để trống = giữ như đang có trong tool) ---"
W = 26  # độ rộng cột nhãn


def _line(label, value="", w=W):
    return f"{label:<{w}}: {value}".rstrip() + ("" if value else " ")


def build_old(d=None):
    """(Mẫu cũ – chỉ giữ để đọc file người dùng đã điền theo mẫu cũ.)"""
    d = d or {}
    g = lambda k, default="": d.get(k, default) or ""
    out = ["===== BIỂU MẪU ĐIỀN 1 BỘ KÊNH – TOOL KÉO KÊNH =====",
           "Cách điền: viết thông tin SAU dấu ':' hoặc SAU dấu '→'. Không xóa / đổi các dòng tiêu đề.",
           "Điền xong: Lưu file (Ctrl+S) → trong tool bấm 'Nạp biểu mẫu' ở trang Thông tin kênh → kiểm tra → Lưu thông tin.",
           ""]
    out += [_line(lb, g(k)) for k, lb in TOP]
    out += ["", H_STRONG] + [_line(lb, g(k)) for k, lb in STRONG]
    out += ["", H_WEAK] + [_line(lb, g(k)) for k, lb in WEAK]
    out += ["Bình luận ghim (viết giữa 2 dòng <<< và >>>, được nhiều dòng):", "<<<"]
    out += [x for x in str(g("comment")).splitlines()] + [">>>"]
    for head, key, n_blank in ((H_WVID, "wvideos", 3), (H_SVID, "videos", 2)):
        vals = [x for x in str(g(key)).splitlines() if x.strip()]
        out += ["", head] + [f"{i}. {v}" for i, v in enumerate(vals, 1)]
        out += [f"{i}." for i in range(len(vals) + 1, max(n_blank, len(vals) + 1) + 1)]
    out += ["", H_STEP3]
    for i, (k, lb) in enumerate(STEP3, 1):
        out.append(f"[{i}] {lb}")
        vals = [x for x in str(g(k)).splitlines() if x.strip()]
        out += [f"    → {v}" for v in vals] or (["    → ", "    → "] if k == "post_videos" else ["    → "])
    out.append(f"[{len(STEP3) + 1}] Bước 3 sẽ làm ([x] = làm, [ ] = bỏ qua)")
    do = d.get("do", {}) or {}
    out += [f"    [{'x' if do.get(k, True) else ' '}] {lb}" for k, lb in STEP3_DO]
    out += ["", H_OPT] + [_line(lb, g(k), 64) for k, lb in OPTIONS]
    return "\n".join(out) + "\n"


def _norm(s):
    return re.sub(r"\s+", " ", str(s or "").strip().lower())


def _section(line):
    u = line.upper()
    if not line.strip().startswith("---"):
        return None
    for key, words in (("wvideos", "VIDEO CẦN KÉO"), ("videos", "VIDEO CỦA KÊNH MẠNH"),
                       ("step3", "TÙY CHỈNH KÊNH MẠNH"), ("opt", "TÙY CHỌN"),
                       ("weak", "KÊNH CẦN KÉO"), ("strong", "KÊNH MẠNH")):
        if words in u:
            return key
    return "?"


def parse_old(text):
    """Đọc biểu mẫu kiểu CŨ. Trả về (dữ liệu, cảnh báo)."""
    text = text.lstrip("\ufeff").replace("\r\n", "\n")
    d, warn = {}, []
    labels = {}
    for k, lb in TOP + STRONG + WEAK + OPTIONS:
        labels[_norm(lb.split(" (")[0])] = k
    sec = "top"
    step3_n = None
    in_comment = None
    lists = {"wvideos": [], "videos": []}
    step3_vals = {}
    do = {}
    for raw in text.split("\n"):
        line = raw.rstrip()
        if in_comment is not None:
            if line.strip() == ">>>":
                d["comment"] = "\n".join(in_comment).strip()
                in_comment = None
            else:
                in_comment.append(line)
            continue
        if line.strip() == "<<<":
            in_comment = []
            continue
        s = _section(line)
        if s:
            sec = s
            step3_n = None
            continue
        if not line.strip() or line.startswith("====="):
            continue
        if sec in ("wvideos", "videos"):
            m = re.match(r"^\s*\d+\s*[.)]\s*(.*)$", line)
            v = (m.group(1) if m else line).split("#")[0].strip()
            if v:
                lists[sec].append(v)
            continue
        if sec == "step3":
            m = re.match(r"^\s*\[(\d+)\]", line)
            if m:
                step3_n = int(m.group(1))
                continue
            m = re.match(r"^\s*\[([xX ])\]\s*(.+)$", line)
            if m:
                for k, lb in STEP3_DO:
                    if _norm(lb) == _norm(m.group(2)):
                        do[k] = m.group(1).lower() == "x"
                continue
            m = re.match(r"^\s*(?:→|->)\s*(.*)$", line)
            if m and step3_n and 1 <= step3_n <= len(STEP3):
                if m.group(1).strip():
                    step3_vals.setdefault(STEP3[step3_n - 1][0], []).append(m.group(1).strip())
                continue
            continue
        if ":" in line:
            lb, val = line.split(":", 1)
            k = labels.get(_norm(lb.split(" (")[0]))
            if k:
                d[k] = val.strip()
            elif _norm(lb).startswith("bình luận ghim"):
                if val.strip() and "<<<" not in val and "dòng <<<" not in lb:
                    d["comment"] = val.strip()   # viết bình luận 1 dòng ngay sau dấu ':'
            elif not line.startswith(("Cách", "Điền")):
                warn.append(f"Không hiểu dòng: {line.strip()[:60]}")
    if in_comment is not None:
        warn.append("Bình luận ghim thiếu dòng >>> ở cuối.")
        d["comment"] = "\n".join(in_comment).strip()
    d["wvideos"] = "\n".join(lists["wvideos"])
    d["videos"] = "\n".join(lists["videos"])
    for k, _lb in STEP3:
        vals = step3_vals.get(k, [])
        d[k] = "\n".join(vals) if k in ("post_videos", "post_text") else (vals[0] if vals else "")
        if k not in ("post_videos", "post_text") and len(vals) > 1:
            warn.append(f"Ô '{_lb}' chỉ nhận 1 dòng – tool lấy dòng đầu: {vals[0][:50]}")
    if do:
        d["do"] = do
    return d, warn


# ======================================================================================
#  BIỂU MẪU MỚI – 2 loại, ngắn gọn: (1) kéo cho kênh khác · (2) kéo cho chính kênh
# ======================================================================================
PAIR, SELF = "pair", "self"
BAR = "=" * 62
T_PAIR = "BIỂU MẪU · KÉO CHO KÊNH KHÁC (2 kênh)"
T_SELF = "BIỂU MẪU · KÉO CHO CHÍNH KÊNH (1 kênh)"
HOW = [" Cách điền: gõ thông tin vào SAU dấu  :  (không sửa chữ phía trước).",
       " Ô có (*) là BẮT BUỘC. Ô khác để trống = tool tự làm hoặc giữ mặc định.",
       " Điền xong: Ctrl+S để lưu → trong tool bấm  Nạp biểu mẫu."]
W2 = 34   # độ rộng cột nhãn

# lựa chọn "video cần đẩy" của chế độ 1 kênh
SELF_CHOICES = [("newest", "Video mới nhất của kênh"),
                ("least_views", "Video ít view nhất (tool tự chọn trong 20 video mới nhất)"),
                ("links", "Các link tôi dán ngay dưới đây")]


def _l(label, value=""):
    return f"{label:<{W2}}: {value}".rstrip() + ("" if value else " ")


def _items(text, blank=3):
    vals = [x.strip() for x in str(text or "").splitlines() if x.strip()]
    return [f"- {v}" for v in vals] + ["- "] * max(1, blank - len(vals))


def build_v2(d=None, mode=PAIR):
    """(mẫu [A][B]… cũ) d = {} -> trống. mode = 'pair' (2 kênh) / 'self' (kéo cho chính kênh)."""
    d = d or {}
    g = lambda k: str(d.get(k) or "").strip()
    one = (d.get("mode") or mode) == SELF
    out = [BAR, " " + (T_SELF if one else T_PAIR), BAR] + HOW + [""]
    out += [_l("Tên hiển thị trong tool", g("job_name")),
            "   ↳ để trống = tool tự đặt theo tên kênh", ""]
    if one:
        out += ["[A] KÊNH CỦA BẠN",
                _l("Tên kênh (*)", g("s_name")),
                _l("ID kênh (*)", g("s_id")),
                "   ↳ ID bắt đầu bằng UC. Không biết ID? Để trống, bấm Đăng nhập trong tool – tool tự điền.", "",
                "[B] VIDEO CẦN ĐẨY VIEW (*) – đánh x vào 1 ô [ ]"]
        tgt = d.get("self_target") or "newest"
        out += [f"[{'x' if k == tgt else ' '}] {i}. {lb}" for i, (k, lb) in enumerate(SELF_CHOICES, 1)]
        out += _items(d.get("wvideos"), 2) + ["   ↳ chỉ cần dán link khi chọn ô 3 – mỗi dòng 1 link video", "",
                                              "[C] BÌNH LUẬN GHIM – để trống = tool tự soạn",
                                              "<<<"] + str(d.get("comment") or "").splitlines() + [">>>", "",
                                              "[D] TRANG CHỦ KÊNH – để trống = tool tự chọn",
                                              _l("Video giới thiệu (người chưa ĐK)", g("sp_trailer")),
                                              "   ↳ trống = video công khai mới nhất",
                                              _l("Video nổi bật (người ĐK cũ)", g("sp_featured")),
                                              "   ↳ trống = video nhiều view nhất 7 ngày qua", "",
                                              "[E] TÙY CHỌN – thường để nguyên"]
    else:
        out += ["[A] KÊNH MẠNH – kênh nhiều view, dùng để kéo",
                _l("Tên kênh mạnh (*)", g("s_name")),
                _l("ID kênh mạnh (*)", g("s_id")),
                "   ↳ ID bắt đầu bằng UC. Không biết ID? Để trống, bấm Đăng nhập trong tool – tool tự điền.", "",
                "[B] KÊNH CẦN KÉO – kênh được đẩy view",
                _l("Link kênh (*)", g("w_url")),
                _l("Tên kênh (*)", g("w_name")),
                _l("ID kênh (*)", g("w_id")),
                _l("Link danh sách phát", g("w_pl")), "",
                "[C] VIDEO CẦN KÉO VIEW (*) – video của kênh cần kéo, mỗi dòng 1 link"]
        out += _items(d.get("wvideos"), 3) + ["",
                "[D] BÌNH LUẬN GHIM – sẽ ghim trên video kênh mạnh",
                "<<<"] + str(d.get("comment") or "").splitlines() + [">>>", "",
                "[E] VIDEO KÊNH MẠNH ĐỂ GẮN – để trống = tool tự tìm video đang có view"]
        out += _items(d.get("videos"), 2) + ["",
                "[F] TRANG KÊNH MẠNH – để trống = bỏ qua / tool tự chọn",
                _l("Link Hồ sơ – chữ hiển thị", g("sp_link_title")),
                _l("Link Hồ sơ – đường dẫn", g("sp_link_url")),
                _l("Video giới thiệu (người chưa ĐK)", g("sp_trailer")),
                _l("Video nổi bật (người ĐK cũ)", g("sp_featured")),
                _l("Chữ của bài đăng", g("post_text")), "",
                "[G] TÙY CHỌN – thường để nguyên"]
    out += [_l("Số video màn hình kết thúc (1 / 2)", g("es_count") or "2"),
            _l("Số thẻ video (1 → 5)", g("card_count") or "3")]
    if not one:
        out.append(_l("Cộng tác (Có / Không)", g("collab") or "Có"))
    return "\r\n".join(out).replace("\r\n", "\n") + "\n"


def _key(label):
    """'Tên kênh mạnh (*)' -> 'tên kênh mạnh'."""
    t = re.sub(r"\(.*?\)", "", str(label)).replace("*", "")
    return re.sub(r"\s+", " ", t).strip().lower()


LABELS = {"tên hiển thị trong tool": "job_name", "tên kênh mạnh": "s_name", "id kênh mạnh": "s_id",
          "link kênh": "w_url", "link danh sách phát": "w_pl",
          "link hồ sơ – chữ hiển thị": "sp_link_title", "link hồ sơ – đường dẫn": "sp_link_url",
          "video giới thiệu": "sp_trailer", "video nổi bật": "sp_featured", "chữ của bài đăng": "post_text",
          "số video màn hình kết thúc": "es_count", "số thẻ video": "card_count", "cộng tác": "collab"}


def parse_v2(text):
    """(Mẫu [A][B]… – vẫn đọc được.) Trả về (dữ liệu, cảnh báo).
    Chỉ có trong dữ liệu những mục có trong file -> mục không có thì tool giữ như đang có."""
    text = text.lstrip("\ufeff").replace("\r\n", "\n")
    up = text.upper()
    one = "KÉO CHO CHÍNH KÊNH" in up and "KÉO CHO KÊNH KHÁC" not in up
    d, warn = {"mode": SELF if one else PAIR}, []
    sec, lists, comment, target = "top", {"wvideos": [], "videos": []}, None, None
    for raw in text.split("\n"):
        line = raw.rstrip()
        st = line.strip()
        if comment is not None:
            if st == ">>>":
                d["comment"] = "\n".join(comment).strip()
                comment = None
            else:
                comment.append(line)
            continue
        if st == "<<<":
            comment = []
            continue
        if not st or st.startswith(("↳", "#", "=")) or st in (T_PAIR, T_SELF) or line in HOW:
            continue
        m = re.match(r"^\[([A-G])\]\s*(.*)$", st)
        if m:
            t = m.group(2).upper()
            sec = ("wvideos" if "VIDEO CẦN" in t else "videos" if "VIDEO KÊNH MẠNH" in t else
                   "comment" if "BÌNH LUẬN" in t else "home" if "TRANG" in t else "opt" if "TÙY CHỌN" in t else
                   "weak" if "KÊNH CẦN KÉO" in t else "strong")
            continue
        if sec in ("wvideos", "videos"):
            m = re.match(r"^\[([xX ])\]\s*(\d)\s*[.)]", st)
            if m:
                if m.group(1).lower() == "x":
                    i = int(m.group(2)) - 1
                    if 0 <= i < len(SELF_CHOICES):
                        target = SELF_CHOICES[i][0]
                continue
            v = re.sub(r"^(?:[-•*]|\d+\s*[.)])\s*", "", st).split("#")[0].strip()
            if v:
                lists[sec].append(v)
            continue
        if ":" in line:
            lb, val = line.split(":", 1)
            k, val = _key(lb), val.strip()
            if k in ("tên kênh", "id kênh"):
                key = ("s_" if sec == "strong" or one else "w_") + ("name" if k == "tên kênh" else "id")
            else:
                key = next((v for lbk, v in LABELS.items() if k == lbk or k.startswith(lbk)), None)
            if key:
                d[key] = val
                continue
        warn.append(f"Không hiểu dòng: {st[:60]}")
    if comment is not None:
        warn.append("Bình luận ghim thiếu dòng >>> ở cuối.")
        d["comment"] = "\n".join(comment).strip()
    d["wvideos"] = "\n".join(lists["wvideos"])
    if not one:
        d["videos"] = "\n".join(lists["videos"])
    if one:
        if target is None:
            target = "links" if lists["wvideos"] else "newest"
        elif target != "links" and lists["wvideos"]:
            warn.append("Có dán link video nhưng chưa đánh x ô 3 – tool vẫn giữ link, dùng cách bạn đã chọn.")
        d["self_target"] = target
    return d, warn


# ---------------------------------------------------------------- mẫu GỌN (đánh số, điền sau dấu =)
SELF_PICK = {"1": "newest", "2": "least_views", "3": "links"}
# (số, khóa, nhãn, kiểu) – kiểu: "=" 1 dòng · "list" nhiều link · "text" nhiều dòng chữ
F_SELF = [("1", "s_name", "Tên kênh", "="), ("2", "s_id", "ID kênh", "="),
          ("3", "self_target", "Đẩy video nào?", "="),
          ("4", "wvideos", "Link video (chỉ khi chọn 3) – mỗi dòng 1 link:", "list"),
          ("5", "comment", "Bình luận ghim (để trống thì tool tự viết):", "text")]
F_PAIR = [("1", "s_name", "Tên kênh mạnh", "="), ("2", "s_id", "ID kênh mạnh", "="),
          ("3", "w_name", "Tên kênh cần kéo", "="), ("4", "w_id", "ID kênh cần kéo", "="),
          ("5", "w_url", "Link kênh cần kéo", "="), ("6", "w_pl", "Link danh sách phát (không bắt buộc)", "="),
          ("7", "wvideos", "Video cần kéo view – mỗi dòng 1 link:", "list"),
          ("8", "comment", "Bình luận ghim:", "text")]
T3_SELF, T3_PAIR = "KÉO CHO CHÍNH KÊNH", "KÉO CHO KÊNH KHÁC"


def build(d=None, mode=PAIR):
    """Biểu mẫu .txt GỌN: d = {} -> trống. mode = 'pair' (2 kênh) / 'self' (kéo cho chính kênh)."""
    d = d or {}
    one = (d.get("mode") or mode) == SELF
    rev = {v: k for k, v in SELF_PICK.items()}
    out = [f"===== {T3_SELF if one else T3_PAIR} =====",
           "Điền sau dấu = , lưu (Ctrl+S), vào tool bấm \"Nạp biểu mẫu\".",
           "Không biết ID kênh? Để trống – đăng nhập trong tool sẽ tự điền.", ""]
    for n, k, lb, kind in (F_SELF if one else F_PAIR):
        if not one and n == "1":
            out.append("KÊNH MẠNH (kênh nhiều view)")
        if not one and n == "3":
            out += ["", "KÊNH CẦN KÉO"]
        if kind == "=":
            val = rev.get(d.get(k) or "newest", "1") if k == "self_target" else str(d.get(k) or "").strip()
            out.append(f"{n}. {lb} = {val}".rstrip() + ("" if val else " "))
            if k == "self_target":
                out.append("   (1 = video mới nhất · 2 = video ít view nhất · 3 = các link ở mục 4)")
        else:
            vals = [x for x in str(d.get(k) or "").splitlines()] if kind == "text" else \
                [x.strip() for x in str(d.get(k) or "").splitlines() if x.strip()]
            out += ["", f"{n}. {lb}"] + (vals or ["", ""])
    while out and not out[-1].strip():
        out.pop()
    return "\n".join(out) + "\n"


def parse(text):
    """Đọc biểu mẫu đã điền – mẫu gọn (mới), mẫu [A][B] và mẫu cũ đều đọc được. Trả về (dữ liệu, cảnh báo).
    Chỉ có trong dữ liệu những mục có trong file; ô để trống không xóa thông tin đang có."""
    text = text.lstrip("﻿").replace("\r\n", "\n")
    if "BIỂU MẪU ĐIỀN 1 BỘ KÊNH" in text or "--- KÊNH MẠNH" in text:
        d, warn = parse_old(text)
        d["mode"] = PAIR
        return d, warn
    if re.search(r"^\[A\]", text, re.M):
        return parse_v2(text)
    head = text.strip().split("\n", 1)[0].upper()
    one = T3_SELF in head
    fields = {n: (k, kind) for n, k, _lb, kind in (F_SELF if one else F_PAIR)}
    d, warn, cur, block = {"mode": SELF if one else PAIR}, [], None, []

    def close():
        if cur:
            k, kind = fields[cur]
            if kind == "list":
                d[k] = "\n".join(re.sub(r"^[-•*]\s*", "", x).strip() for x in block if x.strip())
            else:
                d[k] = "\n".join(block).strip()
    for raw in text.split("\n"):
        line = raw.rstrip()
        m = re.match(r"^\s*(\d)\s*\.\s*([^=:]*?)\s*(=|:)\s*(.*)$", line)
        if m and m.group(1) in fields and not (cur and fields[cur][1] == "text" and fields[m.group(1)][1] != "text"
                                               and int(m.group(1)) < int(cur)):
            close()
            cur, block = None, []
            n, k, kind = m.group(1), *fields[m.group(1)]
            if kind == "=":
                d[k] = m.group(4).strip()
            else:
                cur = n
                if m.group(4).strip():
                    block.append(m.group(4))
            continue
        if cur:
            if fields[cur][1] == "list" and line.strip() and line.strip().split("(")[0].strip().isupper():
                continue
            block.append(line)
            continue
        st = line.strip()
        if st and not st.startswith(("=", "(", "Điền", "Không biết")) and not st.split("(")[0].strip().isupper():
            warn.append(f"Không hiểu dòng: {st[:60]}")
    close()
    if one:
        pick = re.sub(r"\D", "", str(d.get("self_target") or ""))[:1]
        if d.get("wvideos") and not pick:
            pick = "3"
        d["self_target"] = SELF_PICK.get(pick, "newest")
        if pick and pick not in SELF_PICK:
            warn.append("Mục 3 chỉ nhận 1, 2 hoặc 3 – tool dùng 1 (video mới nhất).")
        if d["self_target"] == "links" and not d.get("wvideos"):
            warn.append("Mục 3 chọn 3 nhưng mục 4 chưa có link video nào.")
    return d, warn


EXAMPLE_PAIR = {
    "s_name": "Kênh Mạnh Mẫu", "s_id": "UCzYxWvUtSrQpOnMlKjIhGfE",
    "w_url": "https://www.youtube.com/@KenhCanKeo", "w_name": "Kênh Cần Kéo", "w_id": "UCaBcDeFgHiJkLmNoPqRsTuV",
    "w_pl": "https://www.youtube.com/playlist?list=PLaBcDeFgHiJkLmNoPqRsTuVwXyZ012345",
    "wvideos": "https://www.youtube.com/watch?v=AbCdEfGhIjK\nhttps://youtu.be/QwErTyUiOpA",
    "comment": "🔥 Nghe truyện mới mỗi ngày tại kênh Kênh Cần Kéo:\nhttps://www.youtube.com/@KenhCanKeo",
    "sp_link_title": "Nghe truyện mới mỗi ngày", "sp_link_url": "https://www.youtube.com/@KenhCanKeo",
    "post_text": "Tập mới đã lên, nghe ngay!", "es_count": "2", "card_count": "3", "collab": "Có",
}
EXAMPLE_SELF = {
    "mode": SELF, "s_name": "Kênh Của Tôi", "s_id": "UCqWeRtYuIoPaSdFgHjKlZxC",
    "self_target": "newest", "es_count": "2", "card_count": "3",
}

RULES = """===== CHỌN BIỂU MẪU =====
Kéo view sang 1 kênh KHÁC          → 1_KEO_CHO_KENH_KHAC.txt
Kênh tự đẩy view cho CHÍNH NÓ      → 2_KEO_CHO_CHINH_KENH.txt
Mẫu đã điền sẵn để nhìn theo       → VI_DU_...

===== CÁCH DÙNG =====
1. Copy file trống, đổi tên theo kênh, mở bằng Notepad.
2. Điền sau dấu = , lưu (Ctrl+S).
3. Tool → Thông tin kênh → Thêm kênh mới → Nạp biểu mẫu → Lưu thông tin.

===== LẤY CHO ĐÚNG =====
Link video : mở video trên YouTube → Chia sẻ → Sao chép  (vd: https://youtu.be/AbCdEfGhIjK)
ID kênh    : bắt đầu bằng UC. Không biết thì để trống, đăng nhập trong tool sẽ tự điền.
"""

OLD_UNTOUCHED = {"1_BIEU_MAU_TRONG.txt": "9e1210780f14e05976023c47e209e118090e996f",
                 "2_VI_DU_DA_DIEN.txt": "ca355af4088b073a71eae6007b14204271a06e1e",
                 "3_CACH_DIEN.txt": "324db70eabd9479a90f17d741ed2d072baa73116"}


def write_folder():
    """Tạo thư mục bieu_mau: 2 biểu mẫu trống, 2 ví dụ, 1 file đọc trước (không ghi đè file người dùng).
    Biểu mẫu kiểu cũ CHƯA ai sửa -> bỏ (tránh rối); đã sửa -> giữ nguyên, tool vẫn đọc được."""
    import hashlib
    os.makedirs(FORM_DIR, exist_ok=True)
    for name, sha in OLD_UNTOUCHED.items():
        p = os.path.join(FORM_DIR, name)
        try:
            if os.path.exists(p):
                t = open(p, encoding="utf-8-sig").read().replace("\r\n", "\n").strip()
                if hashlib.sha1(t.encode()).hexdigest() == sha:
                    os.remove(p)
        except Exception:
            pass
    files = {"0_DOC_TRUOC.txt": RULES,
             "1_KEO_CHO_KENH_KHAC.txt": build({}, PAIR),
             "2_KEO_CHO_CHINH_KENH.txt": build({}, SELF),
             "VI_DU_keo_cho_kenh_khac.txt": build(EXAMPLE_PAIR, PAIR),
             "VI_DU_keo_cho_chinh_kenh.txt": build(EXAMPLE_SELF, SELF)}
    for name, content in files.items():
        if os.path.exists(os.path.join(FORM_DIR, name)):
            continue  # KHÔNG ghi đè: có thể bạn đã điền thẳng vào file này
        with open(os.path.join(FORM_DIR, name), "w", encoding="utf-8-sig", newline="\r\n") as f:
            f.write(content)
    return FORM_DIR


if __name__ == "__main__":
    print(write_folder())
