"""
File Excel ĐỐI SOÁT: video nào của kênh mạnh nào đã kéo cho video nào của kênh cần kéo,
gắn ở vị trí nào (bình luận ghim / màn hình kết thúc ô 1-2 / thẻ 1-5 + mốc thời gian / cộng tác),
đã gỡ hay chưa, gỡ lúc nào.

Đọc từ nhật ký ket_qua_keo_kenh.xlsx (tool ghi lúc kéo), không suy đoán.
Tạo lại sau mỗi lần kéo / gỡ, hoặc bấm "Xuất file đối soát" ở trang Kết quả.
"""
import json
import os
import re
from datetime import datetime

from openpyxl import Workbook, load_workbook
from openpyxl.styles import Alignment, Border, Font, PatternFill, Side
from openpyxl.utils import get_column_letter

OUT_NAME = "doi_soat_keo_kenh.xlsx"

HEAD_FILL = PatternFill("solid", start_color="1F2430")
HEAD_FONT = Font(name="Arial", bold=True, color="FFFFFF")
GOLD_FONT = Font(name="Arial", bold=True, color="B8872B", size=13)
BODY = Font(name="Arial", size=10)
LINK = Font(name="Arial", size=10, color="1F5FD1", underline="single")
FILL_ON = PatternFill("solid", start_color="E2F5EA")     # đang kéo (chưa gỡ)
FILL_OFF = PatternFill("solid", start_color="ECEEF2")    # đã gỡ
FILL_BAD = PatternFill("solid", start_color="FBE4E4")    # lỗi khi gỡ
FILL_WARN = PatternFill("solid", start_color="FCF1D9")   # cần kiểm tra / gỡ thủ công
THIN = Side(style="thin", color="D9DCE3")
BOX = Border(left=THIN, right=THIN, top=THIN, bottom=THIN)

YT = "https://www.youtube.com/watch?v="


def _vid(url):
    m = re.search(r"(?:v=|youtu\.be/|/shorts/|/video/)([\w-]{11})", str(url or ""))
    return m.group(1) if m else ""


def _split_channel(text):
    """'Tên kênh (UCxxxx)' -> ('Tên kênh', 'UCxxxx')."""
    m = re.match(r"^(.*?)\s*\((UC[\w-]*)\)\s*$", str(text or ""))
    return (m.group(1).strip(), m.group(2)) if m else (str(text or "").strip(), "")


def _state(removal):
    removal = str(removal or "")
    if "Đã gỡ" in removal:
        return "ĐÃ GỠ", FILL_OFF
    if "Lỗi khi gỡ" in removal:
        return "LỖI KHI GỠ – vẫn còn trên video", FILL_BAD
    if "thủ công" in removal:
        return "CẦN GỠ THỦ CÔNG – vẫn còn trên video", FILL_WARN
    return "ĐANG KÉO (chưa gỡ)", FILL_ON


def read_log(log_path):
    """Đọc nhật ký -> danh sách bản ghi đối soát (mỗi vị trí gắn = 1 bản ghi)."""
    wb = load_workbook(log_path, read_only=True)
    import excel_view
    ws = excel_view.log_sheet(wb)
    head = [c.value for c in next(ws.iter_rows(min_row=1, max_row=1))]
    col = {h: i for i, h in enumerate(head) if h}
    out = []
    for n, row in enumerate(ws.iter_rows(min_row=2, values_only=True), 2):
        g = lambda k: row[col[k]] if k in col and col[k] < len(row) else None
        status = str(g("Trạng thái") or "")
        detail = str(g("Chi tiết") or "")
        if "DONE" not in status and "KIỂM" not in status:
            continue  # bước lỗi: không gắn gì
        if "đã có sẵn" in detail or "đã đúng sẵn trên kênh" in detail:
            continue  # video đã có từ trước, tool không gắn gì
        task = str(g("Hạng mục") or "")
        target = str(g("Link video / Kênh") or "")
        s_name, s_id = _split_channel(g("Kênh mạnh (dùng để kéo)") or "")
        w_name, w_id = _split_channel(g("Kênh cần kéo") or "")
        if not s_name:
            s_name = "(nhật ký cũ – không ghi kênh mạnh)"
        if not w_name:
            w_name = str(g("Kênh") or "")
        base = dict(log_row=n, time=g("Thời gian") or "", task=task, s_name=s_name, s_id=s_id,
                    s_url=target if _vid(target) else "", s_vid=_vid(target), w_name=w_name, w_id=w_id,
                    result="CẦN KIỂM TRA" if "KIỂM" in status else "ĐÃ KÉO",
                    removal=g("Tình trạng gỡ") or "", removed_at=g("Thời gian gỡ") or "",
                    note=str(g("Lỗi") or ""), file=g("File kênh") or "")
        items = []
        data = g("Dữ liệu gắn (JSON)")
        if data:
            try:
                items = json.loads(data)
            except Exception:
                items = []
        if items:
            for it in items:
                rec = dict(base, slot=it.get("slot", ""), mark=it.get("time", ""), a_vid=it.get("id", ""),
                           a_url=it.get("url") or (YT + it["id"] if it.get("id") else ""),
                           a_title=it.get("title", ""),
                           owner="Kênh mạnh (video của chính kênh mạnh)" if it.get("owner") == "strong"
                           else "Kênh cần kéo")
                if it.get("old"):
                    rec["note"] = (f"Video cũ trước khi tool đổi: {it['old']} (gỡ = đặt lại video này). "
                                   + rec["note"]).strip()
                if it.get("saved") is False:
                    rec["note"] = ("Video trùng với video đã gắn trước đó – YouTube không thay đổi. " + rec["note"]).strip()
                out.append(rec)
            continue
        # nhật ký cũ / bước không có dữ liệu chi tiết
        ids = [x.strip() for x in str(g("Video đã gắn") or "").split(",") if x.strip()] or \
            list(dict.fromkeys(re.findall(r"\(([\w-]{11})\)", detail)))
        if ids:
            for k, vid in enumerate(ids, 1):
                out.append(dict(base, slot=f"{task} – vị trí {k} (nhật ký cũ, không ghi số ô)", mark="",
                                a_vid=vid, a_url=YT + vid, a_title="", owner="Kênh cần kéo"))
        else:
            out.append(dict(base, slot=task, mark="", a_vid="", a_url="", a_title=detail[:200], owner=""))
    wb.close()
    return out


# ------------------------------------------------------------------ trình bày gọn
STATE = {   # tình trạng gỡ -> (nhãn ngắn, màu chữ, màu nền)
    "on": ("🟢 Đang kéo", "1E7B34", "E3F4E7"),
    "off": ("⚪ Đã gỡ", "5B6675", "EEF1F4"),
    "manual": ("🟡 Gỡ tay", "8A5A00", "FFF1CC"),
    "bad": ("🔴 Lỗi gỡ", "B42318", "FDE4E2"),
    "skip": ("⏭ Không thuộc kênh", "3B5B85", "E6EEF8"),
}


def _st(removal):
    r = str(removal or "")
    if "Đã gỡ" in r:
        return "off"
    if "Lỗi khi gỡ" in r:
        return "bad"
    if "thủ công" in r:
        return "manual"
    if "Bỏ qua" in r:
        return "skip"
    return "on"


def _slot(s):
    s = str(s or "")
    m = re.match(r"^(.*?) – vị trí (\d+)", s)
    if m:
        s = f"{m.group(1)} {m.group(2)}"
    s = s.replace("Thẻ (cards)", "Thẻ").replace("Màn hình kết thúc – ô", "Kết thúc ô")
    s = s.replace("Màn hình kết thúc", "Kết thúc").replace("Trang chủ – ", "Trang chủ: ")
    s = re.sub(r"\s*\((người chưa ĐK|người ĐK cũ)\)", "", s)
    s = s.replace("Hồ sơ – đường liên kết", "Link hồ sơ").replace("Hồ sơ: đường liên kết", "Link hồ sơ")
    s = s.replace("Bài đăng – video", "Bài đăng")
    return s


def _cut(s, n):
    s = re.sub(r"\s+", " ", str(s or "")).strip()
    return s if len(s) <= n else s[:n - 1].rstrip() + "…"


def _when(t):
    try:
        d = datetime.strptime(str(t), "%Y-%m-%d %H:%M:%S")
        return d, d.strftime("%d/%m  %H:%M")
    except Exception:
        return None, str(t or "")


def _table(ws, title, sub, cols, rows, center=(), links=None, state_col=None, days=None):
    """Bảng gọn: tên bảng + 1 dòng ghi chú, tiêu đề cột 1 dòng, không xuống dòng, sọc nhẹ, mã video bấm mở được.
    cols = [(tên, rộng)], rows = list giá trị, links = {chỉ số cột: chỉ số cột chứa link} (tính từ 0)."""
    from excel_view import DAY_LINE, FONT, HEAD_BG, INK, LINE, MUTED, ZEBRA
    links = links or {}
    ws.sheet_view.showGridLines = False
    ws["A1"] = title
    ws["A1"].font = Font(name=FONT, size=15, bold=True, color=INK)
    ws["A2"] = sub
    ws["A2"].font = Font(name=FONT, size=9.5, italic=True, color=MUTED)
    ws.row_dimensions[1].height = 26
    ws.row_dimensions[2].height = 18
    H = 4
    for i, (h, w) in enumerate(cols, 1):
        c = ws.cell(H, i, h)
        c.font = Font(name=FONT, size=10.5, bold=True, color="FFFFFF")
        c.fill = PatternFill("solid", start_color=HEAD_BG)
        c.alignment = Alignment(horizontal="center" if i - 1 in center else "left", vertical="center",
                                indent=0 if i - 1 in center else 1)
        ws.column_dimensions[get_column_letter(i)].width = w
    ws.row_dimensions[H].height = 26
    body = Font(name=FONT, size=10, color=INK)
    prev = None
    for n, row in enumerate(rows):
        rr = H + 1 + n
        top = None
        if days is not None:
            if prev is not None and days[n] != prev:
                top = DAY_LINE
            prev = days[n]
        for i in range(len(cols)):
            v = row[i] if i < len(row) else ""
            c = ws.cell(rr, i + 1, v)
            c.font = body
            c.alignment = Alignment(horizontal="center" if i in center else "left", vertical="center",
                                    indent=0 if i in center else 1)
            c.border = Border(bottom=LINE, top=top) if top else Border(bottom=LINE)
            if n % 2:
                c.fill = ZEBRA
            if i in links and row[links[i]]:
                c.hyperlink = row[links[i]]
                c.font = Font(name=FONT, size=10, color="1F5FBF", underline="single")
        if state_col is not None and row[state_col] in {v[0] for v in STATE.values()}:
            lab = [v for v in STATE.values() if v[0] == row[state_col]][0]
            c = ws.cell(rr, state_col + 1)
            c.font = Font(name=FONT, size=10, bold=True, color=lab[1])
            c.fill = PatternFill("solid", start_color=lab[2])
        ws.row_dimensions[rr].height = 21
    ws.freeze_panes = ws.cell(H + 1, 1)
    if rows:
        ws.auto_filter.ref = f"A{H}:{get_column_letter(len(cols))}{H + len(rows)}"
    ws.sheet_view.zoomScale = 110


def build(log_path, out_path=None):
    """Tạo file đối soát gọn (3 trang). Trả về đường dẫn file đã ghi (hoặc None nếu chưa có nhật ký)."""
    if not os.path.exists(log_path):
        return None
    recs = read_log(log_path)
    out_path = out_path or os.path.join(os.path.dirname(os.path.abspath(log_path)), OUT_NAME)
    wb = Workbook()
    now = f"{datetime.now():%d/%m/%Y %H:%M}"
    for r in recs:
        r["state"] = _st(r["removal"])
        r["s_short"] = _cut(r["s_name"] if not r["s_name"].startswith("(nhật ký cũ") else "(không rõ)", 24)
        r["w_short"] = _cut(r["w_name"], 24)

    # 1) TỔNG QUAN – mỗi cặp kênh 1 dòng
    ws = wb.active
    ws.title = "Tổng quan"
    pair = {}
    for r in recs:
        p = pair.setdefault((r["s_short"], r["w_short"]), dict(sv=set(), wv=set(), on=0, off=0, other=0))
        if r["s_vid"]:
            p["sv"].add(r["s_vid"])
        if r["a_vid"]:
            p["wv"].add(r["a_vid"])
        k = r["state"]
        if k in ("on", "off"):
            p[k] += 1
        elif k in ("manual", "bad"):
            p["other"] += 1
    tot = {k: sum(1 for r in recs if r["state"] == k) for k in STATE}
    rows = [[s, w if w and w != s else "Chính kênh", len(v["sv"]), len(v["wv"]), v["on"], v["off"], v["other"]]
            for (s, w), v in sorted(pair.items(), key=lambda x: -x[1]["on"])]
    _table(ws, "ĐỐI SOÁT KÉO KÊNH",
           f"Tạo lúc {now}   ·   🟢 Đang kéo {tot['on']}   ⚪ Đã gỡ {tot['off']}   "
           f"🟡 Gỡ tay {tot['manual']}   🔴 Lỗi gỡ {tot['bad']}   ·   Mỗi dòng = 1 cặp kênh",
           [("Kênh mạnh", 24), ("Kéo cho kênh", 24), ("Video kênh mạnh", 19), ("Video được kéo", 18),
            ("🟢 Đang kéo", 14), ("⚪ Đã gỡ", 12), ("🟡 Gỡ tay / lỗi", 17)],
           rows, center=(2, 3, 4, 5, 6))

    # 2) CHI TIẾT – mỗi vị trí gắn 1 dòng, mới nhất trên cùng
    ws2 = wb.create_sheet("Chi tiết")
    rows2, days = [], []
    for r in sorted(recs, key=lambda x: (str(x["time"]), x["log_row"]), reverse=True):
        d, when = _when(r["time"])
        target = r["a_vid"] or "—"
        name = _cut(r["a_title"], 42) if r["a_vid"] else _cut(r["a_title"] or r["task"], 42)
        rows2.append([when, r["s_short"], r["s_vid"] or "Trang kênh", _slot(r["slot"]), r["mark"] or "",
                      target, name, STATE[r["state"]][0], r["s_url"], r["a_url"]])
        days.append(d.date() if d else None)
    _table(ws2, "CHI TIẾT – mỗi dòng là 1 vị trí đã gắn",
           "Mới nhất ở trên cùng · Bấm mã video để mở · Lọc cột “Video kênh mạnh” để xem 1 video đang gắn gì",
           [("Lúc", 13), ("Kênh mạnh", 22), ("Video kênh mạnh", 16), ("Vị trí", 22), ("Mốc", 7),
            ("Trỏ tới video", 15), ("Tên video được kéo", 44), ("Trạng thái", 17)],
           rows2, center=(0, 2, 4, 5, 7), links={2: 8, 5: 9}, state_col=7, days=days)

    # 3) THEO VIDEO ĐƯỢC KÉO – mỗi video được kéo 1 dòng
    ws3 = wb.create_sheet("Theo video được kéo")
    by = {}
    for r in recs:
        if not r["a_vid"]:
            continue
        own = r["s_short"] if str(r["owner"]).startswith("Kênh mạnh") else r["w_short"]
        d = by.setdefault(r["a_vid"], dict(url=r["a_url"], title=r["a_title"], w=own, on=[], off=0))
        d["title"] = d["title"] or r["a_title"]
        if r["state"] == "on":
            if r["s_vid"] and r["s_vid"] not in d["on"]:
                d["on"].append(r["s_vid"])
        else:
            d["off"] += 1
    rows3 = [[k, _cut(d["title"], 44), d["w"], len(d["on"]), d["off"], _cut(" · ".join(d["on"]), 62), d["url"]]
             for k, d in sorted(by.items(), key=lambda x: -len(x[1]["on"]))]
    _table(ws3, "THEO VIDEO ĐƯỢC KÉO",
           "Mỗi video được kéo đang được bao nhiêu video kênh mạnh trỏ tới",
           [("Video", 15), ("Tên video", 46), ("Thuộc kênh", 22), ("Đang trỏ tới", 13), ("Đã gỡ", 9),
            ("Từ các video kênh mạnh", 64)],
           rows3, center=(0, 3, 4), links={0: 6})

    try:
        wb.save(out_path)
    except PermissionError:  # file đang mở trong Excel -> lưu bản có giờ
        root, ext = os.path.splitext(out_path)
        out_path = f"{root}_{datetime.now():%Y%m%d_%H%M%S}{ext}"
        wb.save(out_path)
    return out_path
