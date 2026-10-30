"""
Giao diện cửa sổ cho Tool kéo kênh YouTube.
Mở bằng cách nhấp đúp file "Mo_Tool.bat" (hoặc: python gui.py).
"""
import os
import re
import queue
import subprocess
import sys
import threading
import tkinter as tk
from tkinter import filedialog, messagebox, ttk

import yaml

import art
import jobs

# Chữ sắc nét trên màn hình Windows có phóng to (125%, 150%...)
if os.name == "nt":
    try:
        import ctypes
        ctypes.windll.shcore.SetProcessDpiAwareness(1)
    except Exception:
        pass

import paths   # noqa: E402 – bố cục thư mục: he_thong\ (mã) · du_lieu\ (dữ liệu)
MOVE_NOTES = paths.setup()
BASE = paths.APP          # mã chạy tool
DATA = paths.DATA         # dữ liệu của bạn
CONFIG = os.path.join(DATA, "config.yaml")
EXAMPLE = os.path.join(BASE, "config.example.yaml")
VIDEO_LIST = os.path.join(DATA, "videos_to_pull.txt")
SHOT_DIR = os.path.join(DATA, "logs", "screenshots")

# ============================== BẢNG MÀU ==============================
SETTINGS = os.path.join(DATA, "ui_settings.json")
# Token lấy NGUYÊN từ giao-dien-mau.css (:root = nền tối, :root[data-theme="light"] = nền sáng).
# Tên biến bên trái là tên cũ của tool (để mọi trang dùng chung), giá trị = đúng token của mẫu.
_T = {
    "dark": {"bg-main": "#070E17", "bg-sidebar": "#0A121D", "bg-panel": "#0E1A27", "bg-panel-secondary": "#13212F",
             "bg-panel-hover": "#17283A", "bg-inset": "#0A1420", "border": "#22344A", "border-light": "#2F4763",
             "text-primary": "#F2F7FC", "text-secondary": "#A7B6C6", "text-muted": "#6D7F92",
             "blue": "#3182F6", "blue-soft": "#7EB1FF", "green": "#34C759", "green-soft": "#6FE08A",
             "yellow": "#F0B429", "yellow-soft": "#FFD166", "red": "#F0474A", "red-soft": "#FF8A8C",
             "violet": "#8B7CF6", "teal": "#21C7C7", "orange": "#F78A3B", "pink": "#EC5F8C", "youtube": "#FF0033"},
    "light": {"bg-main": "#EDF1F6", "bg-sidebar": "#F8FAFC", "bg-panel": "#FFFFFF", "bg-panel-secondary": "#F1F4F8",
              "bg-panel-hover": "#E7EDF4", "bg-inset": "#F4F7FA", "border": "#D6DEE8", "border-light": "#BFCBDA",
              "text-primary": "#132030", "text-secondary": "#46566A", "text-muted": "#7A8899",
              "blue": "#2F6FE0", "blue-soft": "#1D57BC", "green": "#1F9D4A", "green-soft": "#17803B",
              "yellow": "#C98A0B", "yellow-soft": "#8A5E00", "red": "#D93B3E", "red-soft": "#B42328",
              "violet": "#6E5BDF", "teal": "#11A0A0", "orange": "#DB6E1E", "pink": "#D24A78", "youtube": "#FF0033"},
}


def _mix(a, b, t):
    """Pha màu a với nền b: t = phần của a (0..1) – thay cho color-mix / rgba(.., 0.14) của CSS."""
    ca = [int(a[i:i + 2], 16) for i in (1, 3, 5)]
    cb = [int(b[i:i + 2], 16) for i in (1, 3, 5)]
    return "#" + "".join(f"{round(x * t + y * (1 - t)):02X}" for x, y in zip(ca, cb))


def _palette(name):
    t = _T[name]
    light = name == "light"
    P, S = t["bg-panel"], t["bg-sidebar"]
    return dict(
        LIGHT=light,
        # menu trái + thanh tiêu đề + thanh trạng thái: --bg-sidebar
        SB_TOP=S, SB_BOT=S, SB_TXT=t["text-secondary"], SB_HEAD=t["text-muted"], SB_ON=t["text-primary"],
        SB_HOVER=P, SB_LINE=t["border"], SWITCH_TRACK=t["bg-panel-secondary"],
        SWITCH_ON=(("#FFD66B", "#F59E0B") if light else ("#4B5FA8", "#26315C")),
        BAN_TOP=S, BAN_BOT=S,
        # nền / panel / ô nhập
        BG=t["bg-main"], CARD=P, CARD2=t["bg-panel-secondary"], BORDER=t["border"], BEVEL=t["border-light"],
        FIELD=t["bg-panel-secondary"], HOVER=t["bg-panel-hover"], INSET=t["bg-inset"],
        INK=t["text-primary"], LABEL=t["text-secondary"], MUTED=t["text-secondary"], SOFT=t["text-muted"],
        THUMB=t["border"], SELECT=_mix(t["blue"], P, 0.16),
        # nút chính = xanh dương (btn.primary)
        ACCENT=t["blue"], ACCENT_H=("#3B8AF9" if not light else "#2763CC"), ACCENT_SOFT=_mix(t["blue"], P, 0.14),
        ACCENT_SOFT_H=_mix(t["blue"], P, 0.22), ACCENT_SOFT_TXT=t["blue-soft"], ACCENT_OFF=_mix(t["blue"], P, 0.40),
        # trạng thái: nền màu 14%, chữ "-soft"
        OK=t["green"], OK_SOFT=_mix(t["green"], P, 0.14), WARN=t["yellow"], WARN_SOFT=_mix(t["yellow"], P, 0.14),
        ERR=t["red"], ERR_SOFT=_mix(t["red"], P, 0.14),
        OK_TXT=t["green-soft"], WARN_TXT=t["yellow-soft"], ERR_TXT=t["red-soft"], BLUE_TXT=t["blue-soft"],
        # khung nhật ký (dạng cửa sổ lệnh): luôn nền tối --bg-inset của nền tối để chữ màu đọc rõ ở cả 2 giao diện
        CONSOLE="#0A1420", CONSOLE_BAR="#0E1A27", CONSOLE_TXT="#A7B6C6",
        BLUE=t["blue"], GREEN=t["green"], AMBER=t["yellow"], VIOLET=t["violet"], PINK=t["pink"], CYAN=t["teal"],
        RED=t["red"], ORANGE=t["orange"], TEAL=t["teal"], GOLD=t["blue-soft"], YT=t["youtube"])


PALETTES = {"light": _palette("light"), "dark": _palette("dark")}


def apply_palette(name):
    globals().update(PALETTES.get(name, PALETTES["dark"]))


def _settings():
    try:
        import json
        with open(SETTINGS, encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return {}


def get_setting(key, default=None):
    return _settings().get(key, default)


def set_setting(key, value):
    try:
        import json
        d = _settings()
        d[key] = value
        with open(SETTINGS, "w", encoding="utf-8") as f:
            json.dump(d, f, ensure_ascii=False)
    except Exception:
        pass


def pt_enabled():
    """Module Phân tích video bật / tắt (mặc định: bật)."""
    return bool(get_setting("mod_phan_tich", True))


def load_theme():
    return get_setting("theme", "dark")     # mặc định nền tối


def save_theme(name):
    set_setting("theme", name)


apply_palette(load_theme())

UI = "Segoe UI" if os.name == "nt" else os.environ.get("KEO_FONT", "DejaVu Sans")
UI_SEMI = "Segoe UI Semibold" if os.name == "nt" else UI
F = (UI, 10)
F_B = (UI, 10, "bold")
F_S = (UI, 9)
F_SB = (UI, 9, "bold")
F_H1 = (UI_SEMI, 19, "bold")
F_H2 = (UI_SEMI, 12, "bold")
F_NUM = ("Segoe UI Variable" if os.name == "nt" else UI_SEMI, 17, "bold")   # --font-num, 22px
F_PANEL = (UI, 9, "bold")       # tiêu đề panel: CHỮ HOA 11.5px đậm
F_TOP = (UI_SEMI, 10, "bold")   # tên trang trên thanh tiêu đề: CHỮ HOA 13px
F_HINT = (UI, 8)                # .hint 10.5px
F_CAP = (UI, 8, "bold")
F_MONO = ("Consolas" if os.name == "nt" else "Courier", 10)


# ============================== THÀNH PHẦN ==============================
def tint(color, amount=0.84):
    """Màu nền nhạt của một màu nhấn, hòa vào nền thẻ."""
    return art.mix(color, CARD, amount)


def on_tint(color):
    """Màu chữ đặt trên nền nhạt của chính màu đó – đúng các màu "-soft" của mẫu (nền tối: sáng hơn, nền sáng:
    đậm hơn); màu khác thì tự làm đậm / sáng tương ứng."""
    soft = {GREEN: OK_TXT, AMBER: WARN_TXT, RED: ERR_TXT, BLUE: BLUE_TXT}
    if color in soft:
        return soft[color]
    return art.shade(color, -0.28) if LIGHT else art.shade(color, 0.25)


class Btn(tk.Label):
    """Nút phẳng có icon + hiệu ứng rê chuột.
    kind: primary (đỏ YouTube) | solid (nền màu `color`) | secondary (viền mảnh) | soft (nền nhạt màu `color`)."""

    def kinds(self, color):
        c = color or ACCENT
        return {
            # .btn.primary: nền xanh dương, chữ trắng
            "primary": dict(bg=ACCENT, hover=ACCENT_H, fg="#FFFFFF", border=art.shade(ACCENT, -0.18),
                            off_bg=ACCENT_OFF, off_fg="#FFFFFF", ic="#FFFFFF"),
            # nút màu riêng (vd Đăng nhập, Chạy...): đúng màu token, chữ trắng; .btn.success khi màu xanh lá
            "solid": dict(bg=c, hover=art.shade(c, 0.10) if not LIGHT else art.shade(c, -0.10),
                          fg="#04220E" if c == GREEN and not LIGHT else "#FFFFFF", border=art.shade(c, -0.2),
                          off_bg=_mix(c, CARD, 0.35), off_fg="#FFFFFF", ic="#04220E" if c == GREEN and not LIGHT
                          else "#FFFFFF"),
            "vivid": dict(bg=c, hover=art.shade(c, 0.10) if not LIGHT else art.shade(c, -0.10),
                          fg="#04220E" if c == GREEN and not LIGHT else "#FFFFFF", border=art.shade(c, -0.2),
                          off_bg=_mix(c, CARD, 0.35), off_fg="#FFFFFF",
                          ic="#04220E" if c == GREEN and not LIGHT else "#FFFFFF"),
            # .btn mặc định: nền --bg-panel-secondary, viền --border, hover --bg-panel-hover
            "secondary": dict(bg=CARD2, hover=HOVER, fg=INK, border=BORDER, off_bg=CARD2, off_fg=SOFT,
                              ic=color or MUTED),
            # .btn.danger kiểu nhạt: nền màu 8%, viền màu ~45%, chữ màu "-soft"
            "soft": dict(bg=_mix(c, CARD, 0.08), hover=_mix(c, CARD, 0.16), fg=on_tint(c),
                         border=_mix(c, CARD, 0.45), off_bg=CARD2, off_fg=SOFT, ic=on_tint(c)),
            "ghost": dict(bg=CARD, hover=HOVER, fg=INK, border=CARD, off_bg=CARD, off_fg=SOFT, ic=color or MUTED),
        }

    def __init__(self, parent, text, command=None, kind="primary", padx=16, pady=8, font=F_B, icon=None,
                 color=None, icon_size=16, **kw):
        # chỉ dùng đúng các loại nút của mẫu: primary (xanh dương), success (xanh lá), danger (đỏ nhạt),
        # mặc định (nền --bg-panel-secondary, icon mang màu riêng) – màu khác không làm nền chữ trắng khó đọc
        if kind == "solid":
            kind = "primary" if color in (None, BLUE, ACCENT) else "solid" if color == GREEN else \
                "soft" if color in (RED, ERR) else "secondary"
        self.k = self.kinds(color)[kind]
        self.command = command
        self.enabled = True
        self._icon = art.icon(icon, icon_size, self.k["ic"]) if icon else None
        self._icon_off = art.icon(icon, icon_size, SOFT) if icon else None
        extra = {}
        if self._icon:
            extra = dict(image=self._icon, compound="left")
            text = ("  " + text) if text else ""
        super().__init__(parent, text=text, bg=self.k["bg"], fg=self.k["fg"], font=font, padx=padx, pady=pady,
                         cursor="hand2", highlightthickness=1, highlightbackground=self.k["border"], **extra, **kw)
        self.bind("<Enter>", lambda e: self.enabled and self.config(bg=self.k["hover"],
                                                                        highlightbackground=BEVEL
                                                                        if self.k["border"] == BORDER else self.k["border"]))
        self.bind("<Leave>", lambda e: self.enabled and self.config(bg=self.k["bg"], highlightbackground=self.k["border"]))
        self.bind("<ButtonRelease-1>", self._click)

    def _click(self, _e):
        if self.enabled and self.command:
            self.command()

    def set_enabled(self, on):
        self.enabled = on
        self.config(bg=self.k["bg"] if on else self.k["off_bg"], fg=self.k["fg"] if on else self.k["off_fg"],
                    cursor="hand2" if on else "arrow")
        if self._icon:
            self.config(image=self._icon if on else self._icon_off)


def icon_label(parent, name, size, color, bg, **kw):
    """Ô icon có nền nhạt bo góc. Không có Pillow -> trả về khung trống nhỏ."""
    img = art.badge(name, size, color)
    if img is None:
        return tk.Frame(parent, bg=bg, width=1, height=1)
    lb = tk.Label(parent, image=img, bg=bg, bd=0, **kw)
    lb.image = img
    return lb


def card(parent, title=None, subtitle=None, pad=20, icon=None, color=None):
    """Panel theo mẫu: nền --bg-panel, viền --border; đầu panel = chấm màu (--panel-hue) có quầng + tiêu đề
    CHỮ HOA đậm, gạch dưới --border. Trả về (khung ngoài, phần thân)."""
    color = color or BLUE
    outer = tk.Frame(parent, bg=CARD, highlightthickness=1, highlightbackground=BORDER)
    if title:
        head = tk.Frame(outer, bg=CARD)
        head.pack(fill="x", padx=14, pady=(10, 9))
        dot = tk.Canvas(head, width=14, height=14, bg=CARD, highlightthickness=0, bd=0)
        dot.create_oval(1, 1, 13, 13, fill=_mix(color, CARD, 0.22), outline="")   # quầng 20%
        dot.create_oval(4, 4, 10, 10, fill=color, outline="")
        dot.pack(side="left", padx=(0, 8))
        tt = tk.Frame(head, bg=CARD)
        tt.pack(side="left", fill="x", expand=True)
        outer._title = tk.Label(tt, text=title.upper(), font=F_PANEL, bg=CARD, fg=INK)
        outer._title.pack(anchor="w")
        if subtitle:
            outer._sub = tk.Label(tt, text=subtitle, font=F_HINT, bg=CARD, fg=SOFT, justify="left")
            outer._sub.pack(anchor="w", pady=(1, 0))
        outer._head = head
        tk.Frame(outer, bg=BORDER, height=1).pack(fill="x")
    body = tk.Frame(outer, bg=CARD)
    body.pack(fill="both", expand=True, padx=max(11, pad - 6), pady=(max(9, pad - 8), max(11, pad - 6)))
    return outer, body


def head_dot(parent, text, hue=None, bg=None, font=None):
    """Tiêu đề kiểu đầu panel: chấm màu có quầng + CHỮ HOA đậm. Trả về khung chứa."""
    hue, bg = hue or BLUE, bg or CARD
    f = tk.Frame(parent, bg=bg)
    dot = tk.Canvas(f, width=14, height=14, bg=bg, highlightthickness=0, bd=0)
    dot.create_oval(1, 1, 13, 13, fill=_mix(hue, bg, 0.22), outline="")
    dot.create_oval(4, 4, 10, 10, fill=hue, outline="")
    dot.pack(side="left", padx=(0, 7))
    tk.Label(f, text=text.upper(), font=font or F_PANEL, bg=bg, fg=INK).pack(side="left")
    return f


def entry(parent, var):
    return tk.Entry(parent, textvariable=var, font=F, relief="flat", bd=0, bg=FIELD, fg=INK,
                    insertbackground=INK, highlightthickness=1, highlightbackground=BORDER, highlightcolor=BLUE,
                    disabledforeground=SOFT, disabledbackground=FIELD)


def textbox(parent, height, mono=False):
    return tk.Text(parent, height=height, font=F_MONO if mono else F, relief="flat", bd=0, bg=FIELD, fg=INK,
                   insertbackground=INK, highlightthickness=1, highlightbackground=BORDER, highlightcolor=BLUE,
                   wrap="word" if not mono else "none", padx=10, pady=8)


def _inside(widget, ancestor):
    w = widget
    while w is not None:
        if w is ancestor:
            return True
        w = getattr(w, "master", None)
    return False


class ScrollPage(tk.Frame):
    """Trang cuộn được, nội dung tự giãn theo chiều ngang cửa sổ."""

    def __init__(self, parent):
        super().__init__(parent, bg=BG)
        self.canvas = tk.Canvas(self, bg=BG, highlightthickness=0)
        sb = ttk.Scrollbar(self, orient="vertical", command=self.canvas.yview)
        self.inner = tk.Frame(self.canvas, bg=BG)
        win = self.canvas.create_window((0, 0), window=self.inner, anchor="nw")
        self.inner.bind("<Configure>", lambda e: self.canvas.configure(scrollregion=self.canvas.bbox("all")))
        self.canvas.bind("<Configure>", lambda e: self.canvas.itemconfigure(win, width=e.width))
        self.canvas.configure(yscrollcommand=sb.set)
        self.canvas.pack(side="left", fill="both", expand=True)
        sb.pack(side="right", fill="y")

    def scroll(self, e):
        self.canvas.yview_scroll(int(-e.delta / 120) or (-1 if e.delta > 0 else 1), "units")


# ============================== ỨNG DỤNG ==============================
ICON_DIR = os.path.join(BASE, "icon")
ICON_ICO = os.path.join(ICON_DIR, "keo_kenh.ico")
ICON_PNG = os.path.join(ICON_DIR, "keo_kenh.png")
APP_ID = "KeoKenh.YouTubeToolkit"


def _windows_app_id():
    """Windows: tool là 1 ứng dụng riêng (không gộp chung biểu tượng Python) -> taskbar hiện đúng icon của tool."""
    if os.name != "nt":
        return
    try:
        import ctypes
        ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID(APP_ID)
    except Exception:
        pass


def make_desktop_shortcut(force=False):
    """Tạo lối tắt 'Kéo Kênh' ngoài màn hình Desktop (có icon của tool). Chạy nền, lỗi thì bỏ qua."""
    if os.name != "nt" or not os.path.exists(ICON_ICO):
        return
    try:
        import subprocess
        exe = sys.executable
        if exe.lower().endswith("python.exe") and os.path.exists(exe[:-10] + "pythonw.exe"):
            exe = exe[:-10] + "pythonw.exe"           # mở tool không kèm cửa sổ đen
        target = os.path.abspath(__file__)
        q = lambda p: p.replace("'", "''")
        ps = ("$d=[Environment]::GetFolderPath('Desktop');"
              "$p=Join-Path $d 'Kéo Kênh.lnk';"
              + ("" if force else "if(Test-Path $p){exit};") +
              "$s=(New-Object -ComObject WScript.Shell).CreateShortcut($p);"
              f"$s.TargetPath='{q(exe)}';$s.Arguments='\"{q(target)}\"';"
              f"$s.WorkingDirectory='{q(os.path.dirname(target))}';$s.IconLocation='{q(ICON_ICO)},0';"
              "$s.Description='Kéo Kênh – YouTube Toolkit';$s.Save()")
        subprocess.Popen(["powershell", "-NoProfile", "-ExecutionPolicy", "Bypass", "-Command", ps],
                         creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
    except Exception:
        pass


class App(tk.Tk):
    def __init__(self):
        _windows_app_id()
        super().__init__()
        self._set_icon()
        self.title("Kéo Kênh – YouTube Toolkit")
        self.geometry("1280x820")
        self.minsize(1100, 700)
        if os.name == "nt":
            try:
                self.state("zoomed")
            except tk.TclError:
                pass
        self.proc = None
        self._on_done = None
        self.q = queue.Queue()
        self.waiting = False
        self.log_history = []
        self.theme = load_theme()
        self.current = "cfg"
        self.pt = None          # module Phân tích video (tạo khi bật)
        self.pt_ui = None
        self._pt_chain = None   # bước phân tích đang chạy trong lượt Kéo kênh -> việc làm tiếp khi xong
        try:   # mỗi kênh 1 trình duyệt riêng: tách các hồ sơ đang dùng chung (bản cũ)
            self._split_note = jobs.fix_profiles()
        except Exception:
            self._split_note = []
        self._build_ui()

        # cuộn chuột cho trang Thông tin kênh
        self.bind_all("<MouseWheel>", self._on_wheel)

        self.load_config()
        self.load_videos()
        self.load_results()
        self.show("cfg")
        for n in MOVE_NOTES:
            self.write("Dữ liệu: " + n, "warn" if "chưa" in n or "thiếu" in n else "ok")
        self.write(f"Dữ liệu của bạn lưu cố định tại: {DATA}  (cập nhật tool giải nén ở đâu cũng giữ nguyên)", None)
        if self._split_note:
            self.write("Đã tách trình duyệt riêng cho từng kênh (trước đây dùng chung): "
                       + "; ".join(self._split_note) + ". Các kênh này cần Đăng nhập lại 1 lần.", "warn")
        self.after(100, self._poll)
        self.after(200, self._pt_poll)
        self.protocol("WM_DELETE_WINDOW", self.on_close)

    def _set_icon(self):
        """Icon của tool: góc cửa sổ, thanh taskbar, Alt+Tab."""
        try:
            if os.name == "nt" and os.path.exists(ICON_ICO):
                self.iconbitmap(default=ICON_ICO)
            # mỗi cỡ vẽ riêng cho sắc nét (Windows / Alt+Tab tự chọn cỡ hợp nhất)
            try:
                import app_icon
                from PIL import ImageTk
                self._icon_imgs = [ImageTk.PhotoImage(app_icon.render(sz)) for sz in (256, 128, 64, 48, 32, 24, 16)]
                self.iconphoto(True, *self._icon_imgs)
            except Exception:
                if os.path.exists(ICON_PNG):
                    self._icon_img = tk.PhotoImage(file=ICON_PNG)
                    self.iconphoto(True, self._icon_img)
        except Exception:
            pass
        # lối tắt ngoài Desktop luôn trỏ đúng thư mục tool đang dùng (giải nén bản mới chỗ khác cũng tự cập nhật)
        if get_setting("shortcut_dir") != BASE:
            make_desktop_shortcut(force=True)
            set_setting("shortcut_dir", BASE)

    def _titlebar(self):
        """Thanh tiêu đề Windows tối/sáng theo giao diện (Windows 10 1809+ / 11)."""
        if os.name != "nt":
            return
        try:
            import ctypes
            self.update_idletasks()
            hwnd = ctypes.windll.user32.GetParent(self.winfo_id())
            val = ctypes.c_int(0 if LIGHT else 1)
            for attr in (20, 19):
                if ctypes.windll.dwmapi.DwmSetWindowAttribute(hwnd, attr, ctypes.byref(val), 4) == 0:
                    break
            cap = ctypes.c_int(0x00100C0A if not LIGHT else 0x00F4F2F0)  # màu thanh tiêu đề (Windows 11)
            ctypes.windll.dwmapi.DwmSetWindowAttribute(hwnd, 35, ctypes.byref(cap), 4)
        except Exception:
            pass

    def _build_ui(self):
        self.configure(bg=BG)
        self._titlebar()
        self.v = {}
        self._style()
        self._build_sidebar()
        self.main = tk.Frame(self, bg=BG)
        self.main.pack(side="left", fill="both", expand=True)
        self._build_topbar(self.main)
        self._build_statusbar(self.main)
        self.container = tk.Frame(self.main, bg=BG)
        self.container.pack(side="top", fill="both", expand=True)
        self.container.grid_rowconfigure(0, weight=1)
        self.container.grid_columnconfigure(0, weight=1)

        self.pages = {}
        self.pages["cfg"] = self._build_config_page()
        self.pages["run"] = self._build_run_page()
        self.pages["res"] = self._build_result_page()
        self.rp_ui = None
        try:
            import rp_page
            self.rp_ui = rp_page.Page(self, sys.modules[__name__])
            self.pages["rep"] = self.rp_ui.frame
        except Exception as e:   # trang mới lỗi -> các chức năng cũ vẫn chạy bình thường
            print(f"Không mở được trang Trả lời bình luận: {e}", file=sys.stderr)
        self.pt_ui = None
        if pt_enabled():
            try:
                import pt_page
                if self.pt is None:
                    self.pt = pt_page.State()
                self.pt_ui = pt_page.Page(self, sys.modules[__name__])
                self.pages["pt"] = self.pt_ui.frame
            except Exception as e:   # module mới lỗi -> các chức năng cũ vẫn chạy bình thường
                self.pt_ui = None
                print(f"Không mở được module Phân tích video: {e}", file=sys.stderr)
        if self.current not in self.pages:
            self.current = "cfg"
        for p in self.pages.values():
            p.grid(row=0, column=0, sticky="nsew")

    # ------------------------------------------------------------ sáng / tối
    def set_theme(self, name, force=False):
        if name == self.theme and not force:
            return
        # ghi nhớ những gì đang hiển thị để dựng lại y nguyên
        snap = {k: v.get() for k, v in self.v.items()}
        comment = self.comment.get("1.0", "end-1c")
        wvids = self.wvideos.get("1.0", "end-1c")
        videos = self.videos.get("1.0", "end-1c")
        posts = (self.post_videos.get("1.0", "end-1c"), self.post_text.get("1.0", "end-1c"))
        sp = {k: v.get() for k, v in self.sp.items()}
        with_setup = self.with_setup.get()
        with_pt = self.with_pt.get()
        flags = (self.b_clear.get(), self.b_collab.get(), self.hidden_var.get())
        saved_snap = getattr(self, "_saved_snap", None)
        job_enabled = self.job_enabled.get()
        chk = {k: v.get() for k, v in self.chk.items()}
        force = self.force.get()
        replace = self.replace.get()
        auto_clear = self.auto_clear.get()
        status = self.status.cget("text")
        side = self._side_state
        side_kind = {OK: "ok", ERR: "err", WARN: "warn"}.get(side[1], "run")
        page = self.current

        self.theme = name
        save_theme(name)
        apply_palette(name)
        for w in self.winfo_children():
            w.destroy()
        self._build_ui()

        for k, val in snap.items():
            if k in self.v:
                self.v[k].set(val)
        self._render_mode_seg()
        self._apply_mode_ui()
        self.comment.insert("1.0", comment)
        self.wvideos.insert("1.0", wvids)
        self._count_wvideos()
        self.videos.insert("1.0", videos)
        self._count_videos()
        self.post_videos.insert("1.0", posts[0])
        self.post_text.insert("1.0", posts[1])
        for k, val in sp.items():
            self.sp[k].set(val)
        self.with_setup.set(with_setup)
        self.with_pt.set(with_pt and pt_enabled())
        self.b_clear.set(flags[0])
        self.b_collab.set(flags[1])
        self.hidden_var.set(flags[2])
        self.job_enabled.set(job_enabled)
        self._refresh_job_bar()
        self._saved_snap = saved_snap
        for k, val in chk.items():
            self.chk[k].set(val)
        self.force.set(force)
        self.replace.set(replace)
        self.auto_clear.set(auto_clear)
        self.log.configure(state="normal")
        for text, tag in self.log_history:
            self.log.insert("end", text + "\n", tag)
        self.log.see("end")
        self.log.configure(state="disabled")
        if getattr(self, "_rp_mirror", None) is not None:   # đang chạy Trả lời bình luận: hiện cả ở trang đó
            self._rp_mirror.mirror(text, tag)
        self.status.config(text=status)
        self.load_results()
        self.show(page)
        if self.proc and self.proc.poll() is None:
            self._busy(True)
            self.status.config(text=status)
            if self.waiting:
                self.btn_continue.set_enabled(True)
                self._set_side("Đang chờ bạn", WARN)
        else:
            self._set_side(side[0], {"ok": OK, "err": ERR, "warn": WARN}.get(side_kind, BLUE))

    # ------------------------------------------------------------------ style
    def _style(self):
        s = ttk.Style(self)
        try:
            s.theme_use("clam")
        except tk.TclError:
            pass
        s.configure(".", font=F, background=CARD, foreground=INK)
        s.configure("Card.TCheckbutton", background=CARD, foreground=INK, font=F,
                    indicatorbackground=FIELD, indicatorforeground="white", indicatormargin=(0, 0, 10, 0),
                    upperbordercolor=BEVEL, lowerbordercolor=BEVEL, padding=(0, 3))
        s.map("Card.TCheckbutton", background=[("active", CARD)],
              indicatorbackground=[("selected", BLUE), ("active", HOVER)],     # accent-color: var(--blue)
              upperbordercolor=[("selected", BLUE)], lowerbordercolor=[("selected", BLUE)])
        for w in ("TCombobox", "TSpinbox"):
            s.configure(w, fieldbackground=FIELD, background=FIELD, foreground=INK, bordercolor=BORDER,
                        insertcolor=INK, selectbackground=SELECT, selectforeground=INK,
                        lightcolor=FIELD, darkcolor=FIELD, arrowcolor=MUTED, padding=6, relief="flat")
            s.map(w, bordercolor=[("focus", BLUE), ("hover", BEVEL)], fieldbackground=[("readonly", FIELD)],
                  foreground=[("disabled", SOFT)])
        for sb in ("Vertical.TScrollbar", "Horizontal.TScrollbar"):   # thanh cuộn: nền trong, tay cầm --border
            s.configure(sb, troughcolor=BG, background=BORDER, bordercolor=BG,
                        lightcolor=BORDER, darkcolor=BORDER, arrowcolor=SOFT, relief="flat", gripcount=0)
            s.map(sb, background=[("active", BEVEL)])
        s.configure("TCombobox", arrowsize=14)
        # table.data: đầu bảng --bg-panel-secondary, chữ phụ; hàng có viền dưới, chọn = xanh mờ
        s.configure("Treeview", background=CARD, fieldbackground=CARD, foreground=INK, rowheight=32,
                    bordercolor=BORDER, lightcolor=CARD, darkcolor=CARD, borderwidth=0, font=F)
        s.map("Treeview", background=[("selected", SELECT)], foreground=[("selected", INK)])
        s.configure("Treeview.Heading", background=CARD2, foreground=MUTED, font=(UI, 8, "bold"),
                    relief="flat", bordercolor=BORDER, lightcolor=CARD2, darkcolor=CARD2, padding=(8, 8))
        s.map("Treeview.Heading", background=[("active", HOVER)])
        self.option_add("*TCombobox*Listbox.background", CARD)
        self.option_add("*TCombobox*Listbox.foreground", INK)
        self.option_add("*TCombobox*Listbox.selectBackground", BLUE)
        self.option_add("*TCombobox*Listbox.selectForeground", "white")

    # ---------------------------------------------------------------- sidebar
    # mỗi mục 1 màu riêng (--nav-hue theo thứ tự mẫu: blue, violet, yellow, teal, orange, green, ...)
    NAV = (("cfg", "id_card", "Thông tin kênh", "BLUE"),
           ("run", "rocket", "Chạy tool", "VIOLET"),
           ("res", "chart", "Kết quả", "AMBER"),
           ("rep", "reply", "Trả lời bình luận", "TEAL"))
    NAV_PT = ("pt", "search_trend", "Phân tích video", "ORANGE")
    TITLES = {"cfg": "Thông tin kênh", "run": "Chạy tool", "res": "Kết quả", "rep": "Trả lời bình luận",
              "pt": "Phân tích video"}

    def _nav_items(self):
        return self.NAV + ((self.NAV_PT,) if pt_enabled() else ())
    SB_W = 214     # --sidebar-w

    def _build_sidebar(self):
        """Menu trái theo mẫu: nền --bg-sidebar, viền phải --border; vẽ trên 1 canvas."""
        self.sb = tk.Canvas(self, width=self.SB_W, highlightthickness=0, bd=0, bg=SB_BOT)
        self.sb.pack(side="left", fill="y")
        tk.Frame(self, bg=SB_LINE, width=1).pack(side="left", fill="y")
        self._sb_h = 0
        self._hover = None
        if not hasattr(self, "_side_state"):
            self._side_state = ("Hoạt động tốt", OK)
        self.sb.bind("<Configure>", self._draw_sidebar)
        self.sb.bind("<Motion>", self._sb_motion)
        self.sb.bind("<Leave>", lambda e: self._sb_set_hover(None))
        self.sb.bind("<Button-1>", self._sb_click)

    def _draw_sidebar(self, e=None):
        c = self.sb
        h = e.height if e else c.winfo_height()
        if h < 50 or (e is not None and h == self._sb_h):
            return
        self._sb_h = h
        c.delete("all")
        W = self.SB_W
        # thương hiệu: logo vuông gradient xanh -> tím + tên tool chữ hoa đậm
        mk = art.app_logo(28) or art.brand_mark(24, BLUE, VIOLET, radius=6)
        if mk:
            c.create_image(16, 30, image=mk, anchor="w")
        else:
            c.create_rectangle(16, 18, 40, 42, fill=BLUE, outline="")
        c.create_text(50, 24, text="KÉO KÊNH", font=(UI, 10, "bold"), fill=SB_ON, anchor="w")
        c.create_text(50, 39, text="YouTube Toolkit", font=F_HINT, fill=SB_HEAD, anchor="w")
        # mục điều hướng
        self._nav_rows = {}
        for i, (key, ic, label, col) in enumerate(self._nav_items()):
            y0 = 62 + i * 37
            color = globals()[col]
            ids = {
                "pill": c.create_image(9, y0, anchor="nw"),
                "bar": c.create_rectangle(9, y0 + 7, 12, y0 + 27, fill=color, outline="", state="hidden"),
                "icon": c.create_image(30, y0 + 17, anchor="center"),
                "text": c.create_text(48, y0 + 17, text=label, font=F, anchor="w"),
            }
            self._nav_rows[key] = dict(ids=ids, y0=y0, color=color, icon=ic)
        # ô người dùng (dưới cùng): kênh đang chọn + cách kéo
        uy = h - 64
        box = art.rounded(W - 18, 48, CARD, BORDER, radius=7)
        if box:
            c.create_image(9, uy, image=box, anchor="nw")
        else:
            c.create_rectangle(9, uy, W - 9, uy + 48, fill=CARD, outline=BORDER)
        av = art.brand_mark(28, TEAL, BLUE, radius=14)
        if av:
            c.create_image(18, uy + 24, image=av, anchor="w")
        self._user_name = c.create_text(54, uy + 16, text="", font=F_SB, fill=SB_ON, anchor="w")
        self._user_plan = c.create_text(54, uy + 32, text="", font=F_HINT, fill=SB_HEAD, anchor="w")
        # bật / tắt module Phân tích video
        ym = uy - 44
        on = pt_enabled()
        c.create_text(16, ym + 12, text="Phân tích video (AI)", font=F_S, fill=SB_TXT, anchor="w")
        x0 = W - 16 - 38
        sw = art.pill(38, 20, GREEN if on else SWITCH_TRACK, GREEN if on else SWITCH_TRACK, radius=10)
        if sw:
            c.create_image(x0, ym + 2, image=sw, anchor="nw")
        else:
            c.create_rectangle(x0, ym + 2, x0 + 38, ym + 22, fill=GREEN if on else SWITCH_TRACK, outline="")
        kx = x0 + (28 if on else 10)
        c.create_oval(kx - 7, ym + 5, kx + 7, ym + 19, fill="#FFFFFF", outline="")
        self._mod_switch = (9, ym - 4, W - 9, ym + 28)
        c.create_line(16, ym - 10, W - 16, ym - 10, fill=SB_LINE)
        c.create_text(16, ym - 24, text="MODULE", font=F_CAP, fill=SB_HEAD, anchor="w")
        self._paint_nav()
        self._sb_user_refresh()

    def _sb_user_refresh(self):
        if not getattr(self, "_user_name", None) or not self.sb.winfo_exists():
            return
        cfg = getattr(self, "cfg", None) or {}
        name = str(cfg.get("job_name") or "Chưa chọn kênh")
        if len(name) > 24:
            name = name[:23] + "…"
        plan = "Kéo cho chính kênh" if cfg.get("mode") == "self" else "Kéo cho kênh khác"
        self.sb.itemconfig(self._user_name, text=name)
        self.sb.itemconfig(self._user_plan, text=plan)

    def _paint_nav(self):
        if not getattr(self, "_nav_rows", None):
            return
        c = self.sb
        for key, row in self._nav_rows.items():
            ids, color = row["ids"], row["color"]
            active, hover = key == self.current, key == self._hover
            if active:   # nền màu của mục 30% mờ dần sang phải + vạch màu 2.5px bên trái
                img = art.hgrad(self.SB_W - 18, 34, _mix(color, SB_BOT, 0.30), SB_BOT, radius=6)
            elif hover:
                img = art.rounded(self.SB_W - 18, 34, CARD, None, radius=6)
            else:
                img = None
            c.itemconfig(ids["pill"], image=img or "", state="normal" if img else "hidden")
            c.itemconfig(ids["bar"], state="normal" if active else "hidden")
            c.itemconfig(ids["icon"], image=art.icon(row["icon"], 16, color) or "")
            c.itemconfig(ids["text"], fill=SB_ON if (active or hover) else SB_TXT,
                         font=(UI, 10, "bold") if active else F)

    def _sb_hit(self, x, y):
        for key, row in getattr(self, "_nav_rows", {}).items():
            if 9 <= x <= self.SB_W - 9 and row["y0"] <= y <= row["y0"] + 34:
                return ("nav", key)
        ms = getattr(self, "_mod_switch", None)
        if ms and ms[0] <= x <= ms[2] and ms[1] <= y <= ms[3]:
            return ("module", "pt")
        return None

    def _sb_motion(self, e):
        hit = self._sb_hit(e.x, e.y)
        self.sb.config(cursor="hand2" if hit else "")
        self._sb_set_hover(hit[1] if hit and hit[0] == "nav" else None)

    def _sb_set_hover(self, key):
        if key != self._hover:
            self._hover = key
            self._paint_nav()

    def _sb_click(self, e):
        hit = self._sb_hit(e.x, e.y)
        if not hit:
            return
        if hit[0] == "nav":
            self.show(hit[1])
        elif hit[0] == "module":
            self.after(10, self.toggle_pt)

    # ------------------------------------------------------- thanh tiêu đề / trạng thái
    def _build_topbar(self, parent):
        """Thanh tiêu đề: vạch gradient xanh -> tím + TÊN TRANG; bên phải: công tắc sáng/tối, nút chính,
        thu nhỏ, đóng."""
        bar = tk.Frame(parent, bg=SB_TOP)
        bar.pack(side="top", fill="x")
        tk.Frame(parent, bg=BORDER, height=1).pack(side="top", fill="x")
        row = tk.Frame(bar, bg=SB_TOP)
        row.pack(fill="x", padx=13, pady=9)
        mark = tk.Canvas(row, width=3, height=14, bg=SB_TOP, highlightthickness=0, bd=0)
        for i in range(14):
            mark.create_line(0, i, 3, i, fill=art.mix(VIOLET, BLUE, i / 13))
        mark.pack(side="left", padx=(0, 8))
        self.top_title = tk.Label(row, text="", font=F_TOP, bg=SB_TOP, fg=INK)
        self.top_title.pack(side="left")
        # bên phải: đóng, thu nhỏ, nút chính, công tắc (pack từ phải sang)
        for ic, cmd in (("x", self.on_close), ("minus", self.iconify)):
            img = art.icon(ic, 12, MUTED)
            b = tk.Label(row, image=img or "", text="" if img else ("✕" if ic == "x" else "–"), bg=CARD, fg=MUTED,
                         width=23 if img else 2, height=23 if img else 1, cursor="hand2",
                         highlightthickness=1, highlightbackground=BORDER)
            b.image = img
            b.bind("<Enter>", lambda e, w=b: w.config(bg=HOVER, highlightbackground=BEVEL))
            b.bind("<Leave>", lambda e, w=b: w.config(bg=CARD, highlightbackground=BORDER))
            b.bind("<ButtonRelease-1>", lambda e, c=cmd: c())
            b.pack(side="right", padx=(6, 0))
        self.top_action = Btn(row, "Kéo kênh đang chọn", lambda: (self.show("run"), self.run_pull()),
                              kind="primary", icon="play", icon_size=12, padx=11, pady=4, font=F_SB)
        self.top_action.pack(side="right", padx=(8, 2))
        self._theme_switch(row).pack(side="right", padx=(0, 4))
        # nút Cập nhật: tự kiểm tra nền khi mở tool; có bản mới thì đổi màu cam "Có bản mới"
        upd = getattr(self, "_upd_state", None)
        self.upd_btn = Btn(row, "Có bản mới" if upd and upd[0] else "Cập nhật", self.do_update,
                           kind="solid" if upd and upd[0] else "secondary",
                           color=ORANGE if upd and upd[0] else BLUE, icon="refresh", icon_size=12,
                           padx=10, pady=4, font=F_SB)
        self.upd_btn.pack(side="right", padx=(0, 8))
        if not getattr(self, "_upd_checked", False):
            self._upd_checked = True
            self.after(4000, lambda: self._check_update(quiet=True))

    def _theme_switch(self, parent):
        """Công tắc viên thuốc 54×26: mặt trăng trái / mặt trời phải, nút tròn trượt sang chế độ đang bật."""
        cv = tk.Canvas(parent, width=54, height=26, bg=SB_TOP, highlightthickness=0, bd=0, cursor="hand2")
        tr = art.rounded(54, 26, CARD2, BEVEL, radius=13)
        if tr:
            cv.create_image(0, 0, image=tr, anchor="nw")
        else:
            cv.create_rectangle(0, 0, 54, 26, fill=CARD2, outline=BEVEL)
        dark = not LIGHT
        tx = 3 if dark else 31            # nút tròn: tím than (tối) / nắng vàng (sáng)
        cv.create_oval(tx - 1, 2, tx + 21, 24, fill=("#7EB1FF" if dark else "#F59E0B"), outline="")
        cv.create_oval(tx, 3, tx + 20, 23, fill=("#26315C" if dark else "#FFD66B"), outline="")
        thumb = None
        moon = art.icon("moon", 12, "#E8EEFF" if dark else SOFT)
        sun = art.icon("sun", 12, "#7A4300" if not dark else SOFT)
        if moon:
            cv.create_image(13, 13, image=moon)
        if sun:
            cv.create_image(41, 13, image=sun)
        cv._imgs = (tr, thumb, moon, sun)
        cv.bind("<Button-1>", lambda e: self.after(10, lambda: self.set_theme("light" if dark else "dark")))
        return cv

    def _build_statusbar(self, parent):
        """Thanh trạng thái dưới cùng: chấm màu + trạng thái, số phiên bản bên phải."""
        bar = tk.Frame(parent, bg=SB_TOP)
        bar.pack(side="bottom", fill="x")
        tk.Frame(parent, bg=BORDER, height=1).pack(side="bottom", fill="x")
        self._sdot = tk.Canvas(bar, width=7, height=7, bg=SB_TOP, highlightthickness=0, bd=0)
        self._sdot_id = self._sdot.create_oval(0, 0, 7, 7, fill=OK, outline="")
        self._sdot.pack(side="left", padx=(13, 7), pady=7)
        self._stext = tk.Label(bar, text="Hoạt động tốt", font=F_S, bg=SB_TOP, fg=MUTED)
        self._stext.pack(side="left")
        try:
            import updater as _up
            ver = _up.local_version().get("version", "")
        except Exception:
            ver = ""
        tk.Label(bar, text=f"bản {ver}" if ver else "v2.0", font=F_S, bg=SB_TOP, fg=SOFT).pack(side="right", padx=13)
        self._set_side(*getattr(self, "_side_state", ("Hoạt động tốt", OK)))

    # ------------------------------------------------------------------ cập nhật tool từ GitHub
    def _check_update(self, quiet=False, then=None):
        """Hỏi GitHub (chạy nền) xem có bản mới không."""
        box = {}

        def work():
            try:
                import updater
                box["r"] = updater.check()
            except Exception as e:
                box["e"] = str(e)

        def poll():
            if "r" not in box and "e" not in box:
                return self.after(300, poll)
            if "e" in box:
                if not quiet:
                    messagebox.showwarning("Cập nhật", box["e"])
                return
            newer, loc, rem = box["r"]
            self._upd_state = (newer, loc, rem)
            try:
                if newer:      # đổi nút thành màu cam "Có bản mới" (không vẽ lại cả giao diện)
                    old_b = self.upd_btn
                    self.upd_btn = Btn(old_b.master, "Có bản mới", self.do_update, kind="solid", color=ORANGE,
                                       icon="refresh", icon_size=12, padx=10, pady=4, font=F_SB)
                    self.upd_btn.pack(side="right", padx=(0, 8), before=old_b)
                    old_b.destroy()
                    self.status.config(text=f"Có bản mới {rem.get('version')} – bấm 'Có bản mới' ở góc trên "
                                            f"để cập nhật.")
            except Exception:
                pass
            if then:
                then(newer, loc, rem)
        threading.Thread(target=work, daemon=True).start()
        self.after(300, poll)

    def do_update(self):
        if self.proc and self.proc.poll() is None:
            messagebox.showinfo("Cập nhật", "Tool đang chạy một việc – chờ xong (hoặc bấm Dừng) rồi hãy cập nhật.")
            return
        self.status.config(text="Đang kiểm tra bản mới trên GitHub…")
        self._check_update(quiet=False, then=self._ask_update)

    def _ask_update(self, newer, loc, rem):
        if not newer:
            self.status.config(text=f"Tool đang là bản mới nhất ({loc.get('version')}).")
            messagebox.showinfo("Cập nhật", f"Tool đang là bản mới nhất ({loc.get('version')}).")
            return
        notes = rem.get("notes") or []
        msg = (f"Có bản mới: {rem.get('version')}   (đang dùng: {loc.get('version')})\n\n"
               + ("Thay đổi:\n" + "\n".join("• " + str(n) for n in notes[:12]) + "\n\n" if notes else "")
               + "Kênh, đăng nhập, Excel, mã API của bạn GIỮ NGUYÊN. Tool tự sao lưu bản đang dùng trước khi "
                 "cập nhật, cập nhật xong tự mở lại.\n\nCập nhật ngay?")
        if not messagebox.askyesno("Cập nhật tool", msg):
            return
        self.status.config(text="Đang cập nhật – đừng tắt tool…")
        self.write("\n── Cập nhật tool " + "─" * 30, "head")
        box = {"log": []}

        def work():
            try:
                import updater
                box["ver"] = updater.apply(log=lambda m: box["log"].append(m))
            except Exception as e:
                box["err"] = str(e)

        def poll():
            while box["log"]:
                self.write("   " + box["log"].pop(0))
            if "ver" not in box and "err" not in box:
                return self.after(300, poll)
            if "err" in box:
                self.status.config(text="Cập nhật chưa xong – bản đang dùng giữ nguyên.")
                messagebox.showwarning("Cập nhật", box["err"] + "\n\nBản đang dùng vẫn giữ nguyên.")
                return
            messagebox.showinfo("Cập nhật", f"Đã cập nhật lên bản {box['ver']}.\n\nBấm OK – tool tự mở lại.")
            try:
                import updater
                updater.restart()
            except Exception as e:
                messagebox.showwarning("Cập nhật", f"Đã cập nhật nhưng chưa tự mở lại được ({e}). "
                                                   f"Hãy tắt tool rồi mở Mo_Tool.bat.")
                return
            self.destroy()
        threading.Thread(target=work, daemon=True).start()
        self.after(300, poll)

    def toggle_pt(self):
        on = not pt_enabled()
        if not on and self.pt is not None and self.pt.state in ("running", "paused"):
            if not messagebox.askyesno("Tắt module", "Module Phân tích video đang chạy. Dừng và tắt?"):
                return
        if not on and self.pt is not None:
            self.pt.shutdown()
            self.pt = None
        set_setting("mod_phan_tich", on)
        if not on and self.current == "pt":
            self.current = "cfg"
        self.set_theme(self.theme, force=True)
        if on:
            self.show("pt")

    def _pt_poll(self):
        try:
            if self.pt is not None:
                for _ in range(200):
                    try:
                        kind, data = self.pt.events.get_nowait()
                    except queue.Empty:
                        break
                    if self.pt_ui is not None:
                        self.pt_ui.handle(kind, data)
                    elif kind == "state":
                        self.pt.state = {"closed": "idle"}.get(data["state"], data["state"])
                    chain = getattr(self, "_pt_chain", None)
                    if chain is not None and kind == "log":
                        lv = data.get("level")
                        self.write("   " + data["msg"], lv if lv in ("ok", "err", "warn") else None)
                    elif chain is not None and kind == "await":
                        self.btn_continue.set_enabled(bool(data.get("waiting")))
                        if data.get("waiting"):
                            self.status.config(text="Phân tích video: xem xong video này thì bấm Tiếp tục để mở video sau.")
                            self._set_side("Đang chờ bạn", WARN)
                    elif chain is not None and kind == "done":
                        self._pt_chain = None
                        self._busy(False)
                        self.write("   → Kết quả ở trang Phân tích video: chọn từng dòng để duyệt Like / Dislike và lấy bình luận.", "ask")
                        self.after(300, chain)
        except Exception as e:
            print(f"Phân tích video: {e}", file=sys.stderr)
        self.after(150, self._pt_poll)

    def _pt_on(self):
        return bool(pt_enabled() and getattr(self, "with_pt", None) is not None and self.with_pt.get()
                    and self.pt is not None and self.pt_ui is not None)

    def _pt_step(self, path, then=None):
        """Bước 'Phân tích video' trong lượt Kéo kênh: chạy sau khi kéo xong kênh `path`, xong thì gọi `then`."""
        then = then or (lambda: None)
        if getattr(self, "_stopped", False):
            return
        if not self._pt_on():
            return then()
        if self.pt.state in ("running", "paused"):
            self.write("⚠ Module Phân tích video đang chạy lượt khác – bỏ qua bước phân tích của kênh này.", "warn")
            return then()
        try:
            cfg = dict(jobs.load(path), headless=False)
        except Exception as e:
            self.write(f"⚠ Không đọc được file kênh để phân tích: {e}", "warn")
            return then()
        st = self.pt_ui.settings_for_job(cfg)
        if not st["target_url"] and not st["keywords"]:
            self.write("⚠ Kênh này chưa có link kênh cần kéo / từ khóa – bỏ qua phân tích video.", "warn")
            return then()
        self.write(f"\n── Phân tích video cùng chủ đề (AI): {cfg.get('job_name')} " + "─" * 20, "head")
        import pt_ai
        if not pt_ai.uses_ai(st["provider"], st["key"]):
            self.write("   (chưa chọn cách dùng AI ở trang Phân tích video – chỉ chấm sơ bộ, không viết bình luận)", "warn")
        self._pt_chain = then
        self._busy(True)
        self.pt.state = "running"
        self.pt.run_id = None
        self.pt_ui._apply_state()
        self.pt.ensure_worker(cfg).send("analyze", st)

    def pt_toast(self, msg):
        if self.pt_ui is not None:
            self.pt_ui._log_add(msg, "ok")

    def _on_wheel(self, e):
        if self.current == "cfg":
            self.pages["cfg"].scroll(e)
        elif self.current == "pt" and self.pt_ui is not None:
            self.pt_ui.on_wheel(e)
        elif self.current == "run" and getattr(self, "run_left", None) is not None:
            try:
                w = self.winfo_containing(e.x_root, e.y_root)
            except Exception:
                w = None
            if w is not None and _inside(w, self.run_left):
                self.run_left.scroll(e)

    def show(self, key):
        self.current = key
        self._paint_nav()
        if getattr(self, "top_title", None) is not None:
            self.top_title.config(text=self.TITLES.get(key, "").upper())
        self.pages[key].tkraise()
        if key == "res":
            self.load_results()
        if key == "rep" and getattr(self, "rp_ui", None):
            self.rp_ui.load()

    def _header(self, parent, title, sub, icon=None, color=None):
        """Dòng mô tả đầu trang (tên trang đã nằm trên thanh tiêu đề). Trả về khung bên phải để đặt nút."""
        wrap = tk.Frame(parent, bg=BG)
        wrap.pack(fill="x", padx=13, pady=(10, 10))
        tk.Label(wrap, text=sub, font=F_S, bg=BG, fg=MUTED, anchor="w", justify="left",
                 wraplength=760).pack(side="left", fill="x", expand=True)
        right = tk.Frame(wrap, bg=BG)
        right.pack(side="right")
        return right

    # ----------------------------------------------------------- trang cấu hình
    def _fold(self, parent, title, sub, icon, color, key):
        """Thẻ thu gọn được: đầu thẻ có nút Mở rộng / Thu gọn (nhớ lựa chọn của bạn)."""
        o, b = card(parent, title, sub, icon=icon, color=color, pad=16)
        opts = b.pack_info()
        state = {"open": bool(get_setting(key, False))}
        btn = Btn(o._head, "", lambda: toggle(), kind="secondary", color=color, padx=12, pady=5, font=F_SB)
        btn.pack(side="right")

        def show():
            if state["open"]:
                b.pack(**{k: v for k, v in opts.items() if k != "in"})
            else:
                b.pack_forget()
            try:
                btn.set_text("Thu gọn ▲" if state["open"] else "Mở rộng ▼")
            except Exception:
                btn.config(text="Thu gọn ▲" if state["open"] else "Mở rộng ▼")

        def toggle():
            state["open"] = not state["open"]
            set_setting(key, state["open"])
            show()
        show()
        return o, b

    def _field(self, parent, r, c, label, key, hint="", colspan=1):
        f = tk.Frame(parent, bg=CARD)
        f.grid(row=r, column=c, columnspan=colspan, sticky="nwe", padx=(0 if c == 0 else 8, 0 if c else 8), pady=5)
        tk.Label(f, text=label, font=F_SB, bg=CARD, fg=LABEL).pack(anchor="w", pady=(0, 4))
        var = tk.StringVar()
        entry(f, var).pack(fill="x", ipady=5, ipadx=6)
        if hint:
            tk.Label(f, text=hint, font=F_S, bg=CARD, fg=SOFT).pack(anchor="w", pady=(3, 0))
        self.v[key] = var
        return f

    GPM_NONE = "(Không dùng – trình duyệt riêng của tool)"

    def _gpm_field(self, parent, key, grid=None, status_parent=None, table_h=6):
        """Ô chọn profile GPM-Login cho kênh (key = 's_gpm' / 'w_gpm')."""
        f = tk.Frame(parent, bg=CARD)
        if grid:
            f.grid(**grid)
        else:
            f.pack(fill="x", pady=(12, 0))
        tk.Label(f, text="Trình duyệt đăng nhập", font=F_SB, bg=CARD, fg=LABEL).pack(anchor="w", pady=(0, 4))
        brk = key + "_br"
        self.v[brk] = tk.StringVar(value=self.BR_OPTS[1])
        bcb = ttk.Combobox(f, textvariable=self.v[brk], state="readonly", values=self.BR_OPTS, width=44)
        bcb.pack(fill="x")
        bcb.bind("<<ComboboxSelected>>", lambda e, k=key: self._br_pick(k))
        tk.Frame(f, bg=CARD, height=8).pack()
        tk.Label(f, text="Profile GPM-Login (không bắt buộc)", font=F_SB, bg=CARD, fg=LABEL).pack(anchor="w", pady=(0, 4))
        row = tk.Frame(f, bg=CARD)
        row.pack(fill="x")
        self.v[key] = tk.StringVar(value=self.GPM_NONE)
        cb = ttk.Combobox(row, textvariable=self.v[key], state="readonly", width=44, values=[self.GPM_NONE])
        cb.pack(side="left", fill="x", expand=True)
        cb.bind("<<ComboboxSelected>>", lambda e: self._gpm_pick(key))
        # bấm vào ô / mũi tên -> hiện bảng profile (tên · ghi chú · đang dùng cho) ngay dưới ô; chọn xong tự đóng
        cb.bind("<Button-1>", lambda e, k=key: (self._gpm_popup(k), "break")[1])
        cb.bind("<Down>", lambda e, k=key: (self._gpm_popup(k), "break")[1])
        Btn(row, "Làm mới GPM-Login", lambda: self._gpm_load(show=True), kind="secondary", icon="refresh",
            color=BLUE, padx=10, pady=5, font=F_SB).pack(side="left", padx=(8, 0))
        # bảng các profile GPM: nằm trong cửa sổ nhỏ bật ra dưới ô chọn (ẩn khi không chọn – gọn giao diện)
        pop = tk.Toplevel(self)
        pop.withdraw()
        pop.overrideredirect(True)
        pop.configure(bg=BORDER)
        tw = tk.Frame(pop, bg=CARD)
        tw.pack(fill="both", expand=True, padx=1, pady=1)
        tv = ttk.Treeview(tw, columns=("name", "note", "use"), show="headings", height=8, selectmode="browse")
        for c, h, w in (("name", "Tên profile", 170), ("note", "Ghi chú", 190), ("use", "Đang dùng cho", 150)):
            tv.heading(c, text=h, anchor="w")
            tv.column(c, width=w, minwidth=80, anchor="w", stretch=True)
        ys = ttk.Scrollbar(tw, command=tv.yview)
        tv.configure(yscrollcommand=ys.set)
        tv.pack(side="left", fill="x", expand=True)
        ys.pack(side="right", fill="y")
        tv.tag_configure("me", background=_mix(BLUE, CARD, 0.28))
        tv.tag_configure("other", foreground=MUTED)
        tv.insert("", "end", values=("(đang tải danh sách từ GPM-Login…)", "", ""))
        tv.bind("<<TreeviewSelect>>", lambda e: self._gpm_table_pick(key))
        for w_ in (pop, tv):
            w_.bind("<Escape>", lambda e, k=key: self._gpm_popdown(k))
        pop.bind("<FocusOut>", lambda e, k=key: self.after(150, lambda: self._gpm_popdown(k, only_if_away=True)))
        self._gpm_pops = getattr(self, "_gpm_pops", {})
        self._gpm_pops[key] = (pop, cb)
        if not getattr(self, "_gpm_pop_bound", False):   # bấm / cuộn ra chỗ khác -> đóng bảng profile
            self._gpm_pop_bound = True
            self.bind_all("<Button-1>", self._gpm_click_away, add="+")
            self.bind_all("<MouseWheel>", self._gpm_click_away, add="+")
            self.bind("<Configure>", lambda e: e.widget is self and self._gpm_close_all(), add="+")

        # khung tóm tắt: profile đã chọn -> kênh đọc được -> trạng thái (nhìn là hiểu ngay)
        sb = tk.Frame(status_parent or f, bg=_mix(BLUE, CARD, 0.10), highlightthickness=1,
                      highlightbackground=_mix(BLUE, CARD, 0.45))
        sb.pack(fill="x", pady=(8 if status_parent is None else 0, 0))
        self._gpm_status_lbl = getattr(self, "_gpm_status_lbl", {})
        rows = {}
        # khung tóm tắt GỌN: dòng 1 = trình duyệt/profile · kênh, dòng 2 = trạng thái; nút nằm bên phải
        top = tk.Frame(sb, bg=sb["bg"])
        top.pack(fill="x", padx=10, pady=6)
        br = tk.Frame(top, bg=sb["bg"])
        br.pack(side="right", anchor="center", padx=(8, 0))
        txt = tk.Frame(top, bg=sb["bg"])
        txt.pack(side="left", fill="x", expand=True)
        l1 = tk.Frame(txt, bg=sb["bg"])
        l1.pack(fill="x")
        rows["p"] = tk.Label(l1, text="", font=F_S, bg=sb["bg"], fg=INK, anchor="w")
        rows["p"].pack(side="left")
        tk.Label(l1, text="  ·  ", font=F_S, bg=sb["bg"], fg=MUTED).pack(side="left")
        rows["c"] = tk.Label(l1, text="", font=F_SB, bg=sb["bg"], fg=INK, anchor="w")
        rows["c"].pack(side="left")
        rows["s"] = tk.Label(txt, text="", font=F_S, bg=sb["bg"], fg=MUTED, anchor="w", justify="left",
                             wraplength=420)
        rows["s"].pack(fill="x", pady=(1, 0))
        txt.bind("<Configure>", lambda e, lb=rows["s"]: lb.config(wraplength=max(200, e.width - 4)))
        chs = tk.Frame(sb, bg=sb["bg"])
        tk.Label(chs, text="Chọn kênh", font=F_SB, bg=sb["bg"], fg=AMBER).pack(side="left", padx=(0, 6))
        rows["choose_var"] = tk.StringVar()
        rows["choose_cb"] = ttk.Combobox(chs, textvariable=rows["choose_var"], state="readonly", width=34)
        rows["choose_cb"].pack(side="left", fill="x", expand=True)
        Btn(chs, "Dùng kênh này", lambda k=key: self._gpm_use_channel(k), kind="solid", color=GREEN, padx=8, pady=3,
            font=F_S).pack(side="left", padx=(6, 0))
        rows["choose"] = chs
        rows["br"] = br
        rows["cont"] = Btn(br, "Tiếp tục", self.send_enter, kind="solid", color=GREEN, icon="play", padx=10, pady=3,
                           font=F_S)
        rows["retry"] = Btn(br, "Đọc lại", lambda k=key: self._gpm_detect(k), kind="secondary", icon="refresh",
                            color=BLUE, padx=8, pady=3, font=F_S)
        rows["retry"].pack(side="right")
        self._gpm_status_lbl[key] = rows
        self._gpm_tables = getattr(self, "_gpm_tables", {})
        self._gpm_tables[key] = tv
        self._gpm_boxes = getattr(self, "_gpm_boxes", {})
        self._gpm_boxes[key] = cb
        self._gpm_sel = getattr(self, "_gpm_sel", {})
        self._gpm_sel.setdefault(key, ("", ""))
        return f

    BR_OPTS = ["GPM-Login (chọn profile ở bảng dưới)",
               "Cốc Cốc – hồ sơ riêng (giữ đăng nhập)", "Chrome – hồ sơ riêng (giữ đăng nhập)",
               "Cốc Cốc – ẩn danh (chạy xong xóa sạch)", "Chrome – ẩn danh (chạy xong xóa sạch)"]

    def _br_label(self, ch, gid=""):
        if gid:
            return self.BR_OPTS[0]
        kind = str(ch.get("browser") or (self.cfg or {}).get("browser") or "coccoc")
        anon = bool(ch.get("incognito"))
        return self.BR_OPTS[(3 if anon else 1) + (1 if kind == "chrome" else 0)]

    def _br_pick(self, key):
        """Đổi trình duyệt đăng nhập của RIÊNG kênh này: GPM / Cốc Cốc / Chrome · hồ sơ riêng / ẩn danh."""
        lab = self.v[key + "_br"].get()
        if lab == self.BR_OPTS[0]:
            if not (getattr(self, "_gpm_sel", {}) or {}).get(key, ("",))[0]:
                rows = (getattr(self, "_gpm_status_lbl", {}) or {}).get(key)
                if rows:
                    rows["s"].config(text="Bấm 1 dòng trong bảng profile GPM bên dưới để chọn profile cho kênh này.",
                                     fg=AMBER)
            return
        kind = "chrome" if lab.startswith("Chrome") else "coccoc"
        anon = "ẩn danh" in lab
        if (getattr(self, "_gpm_sel", {}) or {}).get(key, ("",))[0]:   # bỏ profile GPM đang chọn
            self.v[key].set(self.GPM_NONE)
            self._gpm_pick(key)
        try:
            data = jobs.load(self.cfg_path)
            ch = data.setdefault("strong_channel" if key == "s_gpm" else "weak_channel", {})
            ch["browser"], ch["incognito"] = kind, anon
            jobs.save(self.cfg_path, data)
            self.cfg = jobs.load(self.cfg_path)
            self._saved_snap = self._form_snapshot()
        except Exception as e:
            messagebox.showwarning("Chưa lưu được", str(e))
        self._gpm_status(key)

    def _compose_post(self):
        """Nút 'Tool tự soạn': soạn chữ bài đăng (đúng ngôn ngữ + chủ đề kênh mạnh, nhắc tên video sẽ đăng),
        điền vào ô để bạn xem / sửa. Không tự đăng – bạn bấm Lưu rồi chạy như bình thường."""
        sid = self.v["s_id"].get().strip()
        if not sid.startswith("UC"):
            messagebox.showinfo("Tool tự soạn", "Cần ID kênh mạnh (bắt đầu bằng UC) để đọc ngôn ngữ và chủ đề kênh.")
            return
        links = [l.strip() for l in self.post_videos.get("1.0", "end").splitlines() if l.strip()]
        link = links[0] if self.v["post_source"].get() == "Theo các link bên dưới" and links else ""
        if self.post_text.get("1.0", "end").strip() and not messagebox.askyesno(
                "Tool tự soạn", "Ô nội dung đang có chữ. Thay bằng bài tool soạn mới?"):
            return
        self.post_ai_note.config(text="⏳ Đang đọc kênh và soạn bài…", fg=AMBER)

        box = {}

        def work():
            try:
                import post_writer
                box["r"] = post_writer.compose(sid, link)
            except Exception as e:
                box["r"] = ("", f"Lỗi: {e}")

        def poll():
            if "r" in box:
                done(*box["r"])
            else:
                self.after(300, poll)

        def done(text, how):
            if not text:
                self.post_ai_note.config(text="✗ " + how, fg=ERR)
                return
            self.post_text.delete("1.0", "end")
            self.post_text.insert("1.0", text)
            self.post_ai_note.config(text=f"✓ Đã soạn ({how}). Đọc / sửa rồi bấm LƯU – tool chỉ đăng đúng chữ "
                                          f"trong ô.", fg=OK)
        threading.Thread(target=work, daemon=True).start()
        self.after(300, poll)

    def _gpm_label(self, it):
        return f"{it['name']}" + (f"  ·  {it['note']}" if it.get("note") else "")

    def _gpm_used(self):
        """{mã profile GPM: tên kênh đang dùng nó} – từ các file kênh đã lưu."""
        out = {}
        try:
            for j in jobs.list_jobs():
                for ck in ("strong_channel", "weak_channel"):
                    gid = str((j.get(ck) or {}).get("gpm_profile_id") or "")
                    if gid and gid not in out:
                        out[gid] = j.get("job_name") or (j.get(ck) or {}).get("name") or "?"
        except Exception:
            pass
        return out

    def _gpm_table_fill(self, msg=None):
        items = sorted((getattr(self, "_gpm_items", {}) or {}).values(), key=lambda it: it["name"].lower())
        used = self._gpm_used()
        cur_job = self.cfg_path and os.path.basename(self.cfg_path)
        for key, tv in getattr(self, "_gpm_tables", {}).items():
            tv.delete(*tv.get_children())
            if msg:
                tv.insert("", "end", values=(msg, "", ""))
                continue
            gid = self._gpm_sel.get(key, ("", ""))[0]
            tv.insert("", "end", iid="__none__", values=(self.GPM_NONE, "", ""), tags=("me",) if not gid else ())
            for it in items:
                u = used.get(it["id"], "")
                if it["id"] == gid:
                    u = "✓ kênh này"
                tv.insert("", "end", iid=it["id"], values=(it["name"], it.get("note", ""), u),
                          tags=("me",) if it["id"] == gid else (("other",) if u else ()))
            if gid and tv.exists(gid):
                tv.see(gid)

    def _gpm_popup(self, key):
        """Hiện bảng profile GPM ngay dưới ô chọn (bấm lại = đóng)."""
        pop, cb = (getattr(self, "_gpm_pops", {}) or {}).get(key, (None, None))
        if pop is None:
            return
        if pop.winfo_viewable():
            return self._gpm_popdown(key)
        for k in self._gpm_pops:
            if k != key:
                self._gpm_popdown(k)
        cb.update_idletasks()
        w = max(cb.winfo_width() + 140, 560)
        pop.geometry(f"{w}x260+{cb.winfo_rootx()}+{cb.winfo_rooty() + cb.winfo_height() + 2}")
        pop.deiconify()
        pop.lift()
        tv = self._gpm_tables.get(key)
        try:
            tv.focus_set()
            if tv.selection():
                tv.see(tv.selection()[0])
        except Exception:
            pass

    def _gpm_close_all(self):
        for k in list((getattr(self, "_gpm_pops", {}) or {})):
            self._gpm_popdown(k)

    def _gpm_click_away(self, e):
        try:
            w = str(e.widget)
        except Exception:
            return
        for k, (pop, cb) in list((getattr(self, "_gpm_pops", {}) or {}).items()):
            try:
                if pop.winfo_exists() and pop.winfo_viewable() and not w.startswith(str(pop)) and w != str(cb):
                    pop.withdraw()
            except Exception:
                pass

    def _gpm_popdown(self, key, only_if_away=False):
        pop, _cb = (getattr(self, "_gpm_pops", {}) or {}).get(key, (None, None))
        if pop is None or not pop.winfo_exists():
            return
        if only_if_away:
            f = self.focus_get()
            if f is not None and str(f).startswith(str(pop)):
                return
        pop.withdraw()

    def _gpm_table_pick(self, key):
        if getattr(self, "_gpm_filling", False):
            return
        self.after(120, lambda: self._gpm_popdown(key))
        tv = self._gpm_tables.get(key)
        sel = tv.selection() if tv else ()
        if not sel:
            return
        iid = sel[0]
        if iid == "__none__":
            self.v[key].set(self.GPM_NONE)
        else:
            it = next((x for x in (getattr(self, "_gpm_items", {}) or {}).values() if x["id"] == iid), None)
            if not it:
                return
            self.v[key].set(self._gpm_label(it))
        self._gpm_pick(key)

    def _gpm_auto_load(self):
        """Tự tải danh sách profile GPM khi mở tool (chạy nền, không làm đứng giao diện)."""
        import threading
        box = {}

        def work():
            import gpm
            try:
                box["items"] = gpm.list_profiles()
            except Exception as e:
                box["err"] = str(e)

        def poll():
            if "items" in box:
                self._gpm_apply(box["items"])
            elif "err" in box:
                self._gpm_table_fill("Chưa kết nối được GPM-Login – mở GPM-Login rồi bấm 'Làm mới GPM-Login'")
            else:
                self.after(300, poll)
        threading.Thread(target=work, daemon=True).start()
        self.after(300, poll)

    def _gpm_load(self, show=False):
        import gpm
        try:
            items = gpm.list_profiles()
        except gpm.GPMError as e:
            self._gpm_table_fill("Chưa kết nối được GPM-Login – mở GPM-Login rồi bấm 'Làm mới GPM-Login'")
            if show:
                messagebox.showwarning("GPM-Login", str(e))
            return False
        self._gpm_apply(items)
        if show:
            messagebox.showinfo("GPM-Login", f"Đã làm mới: {len(items)} profile từ GPM-Login ({gpm.api_base()}).")
        return True

    def _gpm_apply(self, items):
        self._gpm_items = {self._gpm_label(it): it for it in items}
        vals = [self.GPM_NONE] + sorted(self._gpm_items, key=str.lower)
        for key, cb in getattr(self, "_gpm_boxes", {}).items():
            cb.configure(values=vals)
            gid = self._gpm_sel.get(key, ("", ""))[0]
            hit = next((lab for lab, it in self._gpm_items.items() if it["id"] == gid), None)
            if hit:
                self.v[key].set(hit)
        self._gpm_filling = True
        try:
            self._gpm_table_fill()
        finally:
            self._gpm_filling = False
        for key in ("s_gpm", "w_gpm"):
            self._gpm_status(key)

    def _gpm_pick(self, key):
        lab = self.v[key].get()
        it = (getattr(self, "_gpm_items", {}) or {}).get(lab)
        other = "w_gpm" if key == "s_gpm" else "s_gpm"
        if it and self.v["mode"].get() == "pair" and (getattr(self, "_gpm_sel", {}) or {}).get(other, ("",))[0] == it["id"]:
            messagebox.showwarning("Trùng profile GPM",
                                   f"Profile '{it['name']}' đang dùng cho {'kênh cần kéo' if key == 's_gpm' else 'kênh mạnh'}.\n\n"
                                   "Kéo 2 kênh cần 2 profile GPM KHÁC nhau – dùng chung 1 profile thì đổi kênh bên này "
                                   "sẽ làm lệch kênh bên kia. Hãy chọn profile khác.")
            gid0 = self._gpm_sel.get(key, ("", ""))[0]
            self.v[key].set(next((l for l, x in self._gpm_items.items() if x["id"] == gid0), self.GPM_NONE))
            self._gpm_filling = True
            try:
                self._gpm_table_fill()
            finally:
                self._gpm_filling = False
            return
        self._gpm_sel[key] = (it["id"], it["name"]) if it else ("", "")
        # lưu ngay vào file kênh (để bấm Đăng nhập là dùng được profile GPM vừa chọn)
        try:
            data = jobs.load(self.cfg_path)
            ch = data.setdefault("strong_channel" if key == "s_gpm" else "weak_channel", {})
            changed = str(ch.get("gpm_profile_id") or "") != self._gpm_sel[key][0]
            ch["gpm_profile_id"], ch["gpm_profile_name"] = self._gpm_sel[key]
            ch["gpm_profile_note"] = (it or {}).get("note", "") if it else ""
            if changed and self._gpm_sel[key][0]:   # đổi profile: bỏ tên + ID cũ, tool đọc lại đúng kênh của profile mới
                ch["name"], ch["channel_id"] = "", ""
                ch.pop("gpm_channels", None)
                if key == "w_gpm":
                    ch["url"] = ""
                pre = "s_" if key == "s_gpm" else "w_"
                for f_ in ("name", "id") + (("url",) if key == "w_gpm" else ()):
                    if pre + f_ in self.v:
                        self.v[pre + f_].set("")
            jobs.save(self.cfg_path, data)
            self.cfg = jobs.load(self.cfg_path)
            self._saved_snap = self._form_snapshot()
        except Exception:
            pass
        if getattr(self, "_gpm_items", None):
            self._gpm_filling = True
            try:
                self._gpm_table_fill()
            finally:
                self._gpm_filling = False
        if self._gpm_sel[key][0] and key + "_br" in self.v:
            self.v[key + "_br"].set(self.BR_OPTS[0])
        self._gpm_status(key)
        if self._gpm_sel[key][0]:
            self._gpm_detect(key)

    def _gpm_status(self, key, reading=False):
        rows = (getattr(self, "_gpm_status_lbl", {}) or {}).get(key)
        if not rows:
            return
        gid, gname = (getattr(self, "_gpm_sel", {}) or {}).get(key, ("", ""))
        ch = (self.cfg or {}).get("strong_channel" if key == "s_gpm" else "weak_channel") or {}
        if not gid:
            if key + "_br" in self.v:
                self.v[key + "_br"].set(self._br_label(ch))
            anon = bool(ch.get("incognito"))
            br = "Chrome" if str(ch.get("browser") or (self.cfg or {}).get("browser")) == "chrome" else "Cốc Cốc"
            rows["p"].config(text=f"{br} " + ("ẩn danh" if anon else "hồ sơ riêng"), fg=MUTED)
            name_, cid_ = str(ch.get("name") or "").strip(), str(ch.get("channel_id") or "").strip()
            rows["c"].config(text=f"{name_ or '(chưa có tên)'}  ({cid_})" if cid_.startswith("UC") else "chưa có kênh",
                             fg=INK if cid_ else MUTED)
            rows["s"].config(text=("Mỗi lần chạy: đăng nhập lại, chạy xong xóa sạch."
                                   if anon else "Đăng nhập 1 lần ở trang Chạy tool – tool nhớ."),
                             fg=MUTED)
            return
        it = next((x for x in (getattr(self, "_gpm_items", {}) or {}).values() if x["id"] == gid), None)
        rows["p"].config(text="GPM: " + ((it or {}).get("name") or gname or gid), fg=MUTED)
        name, cid = str(ch.get("name") or "").strip(), str(ch.get("channel_id") or "").strip()
        chans = [c for c in (ch.get("gpm_channels") or []) if str(c.get("id") or "").startswith("UC")]
        if len(chans) > 1 and not reading:   # tài khoản có nhiều kênh: cho bạn chọn đúng kênh
            labs = [f"{c['name']}  ·  {c.get('handle') or ''}  ·  {c['id']}" for c in chans]
            rows["choose_cb"].configure(values=labs)
            cur = next((l for l, c in zip(labs, chans) if c["id"] == cid), "")
            rows["choose_var"].set(cur)
            rows["_chans"] = chans
            rows["choose"].pack(fill="x", padx=10, pady=(0, 6))
        else:
            rows["choose"].pack_forget()
        other = "w_gpm" if key == "s_gpm" else "s_gpm"
        if self.v["mode"].get() == "pair" and (getattr(self, "_gpm_sel", {}) or {}).get(other, ("",))[0] == gid:
            rows["c"].config(text="—", fg=MUTED)
            rows["s"].config(text="✗ Trùng profile với kênh bên kia – hãy chọn profile khác.", fg=RED)
            rows["choose"].pack_forget()
            return
        if reading:
            rows["c"].config(text="đang mở profile…", fg=AMBER)
            rows["s"].config(text="⏳ Trên cửa sổ GPM: bấm chọn đúng kênh (khung xanh) rồi bấm Tiếp tục.", fg=AMBER)
        elif cid.startswith("UC"):
            rows["c"].config(text=f"{name or '(chưa có tên)'}  ({cid})", fg=INK)
            rows["s"].config(text="✓ Sẵn sàng", fg=GREEN)
        elif len(chans) > 1:
            rows["c"].config(text=f"tài khoản trong profile có {len(chans)} kênh", fg=AMBER)
            rows["s"].config(text="Chọn đúng kênh ở ô 'Chọn kênh' rồi bấm Dùng kênh này.", fg=AMBER)
        else:
            rows["c"].config(text="chưa đọc được kênh", fg=MUTED)
            rows["s"].config(text="Bấm Đọc lại để tool đọc tên + ID kênh.", fg=AMBER)

    def _gpm_kick(self):
        """Đọc lần lượt các kênh đang chờ (mỗi lúc chỉ 1 profile – không lẫn khung trạng thái)."""
        q = getattr(self, "_gpm_queue", [])
        if not q or getattr(self, "_gpm_live", None):
            return
        if getattr(self, "proc", None) is not None and self.proc.poll() is None:
            self.after(2000, self._gpm_kick)   # tool đang chạy việc khác: chờ xong rồi đọc
            return
        self._gpm_detect(q.pop(0))

    def _gpm_detect(self, key):
        """Vừa chọn profile GPM -> tự mở profile, đọc kênh YouTube trong đó, điền Tên + ID kênh."""
        who = "strong" if key == "s_gpm" else "weak"
        busy = getattr(self, "_gpm_live", None) or (getattr(self, "proc", None) is not None
                                                    and self.proc.poll() is None)
        if busy:   # đang đọc bên kia / đang chạy việc khác -> xếp hàng, đọc sau
            self._gpm_queue = [k for k in getattr(self, "_gpm_queue", []) if k != key] + [key]
            rows_q = self._gpm_status_lbl.get(key) or {}
            if rows_q:
                self._gpm_status(key)
                rows_q["c"].config(text="⏳ chờ lượt – tool đang đọc kênh bên kia / đang chạy việc khác", fg=AMBER)
                rows_q["s"].config(text="Tool sẽ tự đọc kênh này ngay khi xong, không cần bấm lại.", fg=AMBER)
            self.after(2000, self._gpm_kick)
            return
        try:   # ghi chú của profile GPM (vd tên kênh bạn ghi trong GPM) -> tool dùng để chọn đúng kênh
            gid = self._gpm_sel.get(key, ("", ""))[0]
            it = next((x for x in (getattr(self, "_gpm_items", {}) or {}).values() if x["id"] == gid), None)
            if it is not None:
                data = jobs.load(self.cfg_path)
                data.setdefault("strong_channel" if key == "s_gpm" else "weak_channel", {})["gpm_profile_note"] = \
                    it.get("note", "")
                jobs.save(self.cfg_path, data)
        except Exception:
            pass
        self._gpm_status(key, reading=True)
        self._gpm_live, self._gpm_lines = key, []

        def done():
            self._gpm_live = None
            rows_ = self._gpm_status_lbl.get(key) or {}
            if rows_.get("cont"):
                rows_["cont"].pack_forget()
            self._after_login()
            try:   # profile GPM quyết định kênh: luôn hiện đúng tên + ID vừa đọc được (kể cả khi đổi profile)
                ch = jobs.load(self.cfg_path).get("strong_channel" if who == "strong" else "weak_channel") or {}
                pre = "s_" if who == "strong" else "w_"
                if str(ch.get("channel_id") or "").startswith("UC"):
                    self.v[pre + "id"].set(ch["channel_id"])
                    if ch.get("name"):
                        self.v[pre + "name"].set(ch["name"])
                    if who == "weak" and ch.get("url") and "w_url" in self.v:
                        self.v["w_url"].set(ch["url"])
                    self.cfg.setdefault("strong_channel" if who == "strong" else "weak_channel", {}).update(
                        name=ch.get("name") or "", channel_id=ch["channel_id"])
            except Exception:
                pass
            self._gpm_status(key)
            res = next((l for l in reversed(self._gpm_lines) if l.lstrip().startswith(("✅", "❌"))), "")
            if res.lstrip().startswith("❌") and rows_:
                rows_["s"].config(text=res.strip(), fg=RED)
            elif not res and rows_ and not any(l.startswith("❓") for l in self._gpm_lines) and \
                    not str((self.cfg.get("strong_channel" if who == "strong" else "weak_channel")
                                                 or {}).get("channel_id") or "").startswith("UC"):
                last = next((l for l in reversed(self._gpm_lines) if l.strip()), "không có thông báo")
                rows_["s"].config(text=f"✗ Chưa đọc được kênh. Thông báo cuối: {last.strip()[:220]}", fg=RED)
            self.after(800, self._gpm_kick)   # còn kênh đang chờ đọc -> đọc tiếp
        try:
            self.run(["login", who, "--detect"], need_config=False, on_done=done, save_list=False)
        except Exception as e:
            self._gpm_live = None
            (self._gpm_status_lbl.get(key) or {}).get("s").config(text=f"✗ {e}", fg=RED)
            return
        if self.proc is None or self.proc.poll() is not None:   # run() từ chối / không chạy -> không treo khung
            self._gpm_live = None
            self._gpm_status(key)

    def _gpm_use_channel(self, key):
        rows = (self._gpm_status_lbl.get(key) or {})
        lab = rows.get("choose_var").get() if rows.get("choose_var") else ""
        chans = rows.get("_chans") or []
        c = next((c for c in chans if lab.endswith(c["id"])), None)
        if not c:
            messagebox.showwarning("Chọn kênh", "Hãy chọn 1 kênh trong danh sách trước.")
            return
        ck = "strong_channel" if key == "s_gpm" else "weak_channel"
        try:
            data = jobs.load(self.cfg_path)
            ch = data.setdefault(ck, {})
            ch["name"], ch["channel_id"] = c["name"], c["id"]
            ch["url"] = f"https://www.youtube.com/{c['handle']}" if c.get("handle") else \
                f"https://www.youtube.com/channel/{c['id']}"
            jobs.save(self.cfg_path, data)
            self.cfg = jobs.load(self.cfg_path)
        except Exception as e:
            messagebox.showwarning("Chọn kênh", str(e))
            return
        pre = "s_" if key == "s_gpm" else "w_"
        self.v[pre + "name"].set(c["name"])
        self.v[pre + "id"].set(c["id"])
        if key == "w_gpm" and "w_url" in self.v:
            self.v["w_url"].set(self.cfg[ck]["url"])
        self._saved_snap = self._form_snapshot()
        self._gpm_status(key)
        self._refresh_job_bar()

    def _gpm_on_line(self, line):
        """Hiện từng bước đọc kênh ngay trong khung tóm tắt (không phải sang trang Chạy tool)."""
        key = self._gpm_live
        rows = (getattr(self, "_gpm_status_lbl", {}) or {}).get(key) or {}
        t = line.strip()
        if not t or not rows:
            return
        self._gpm_lines.append(t)
        if "👉" in t:
            rows["s"].config(text=t.replace("👉", "").strip(), fg=AMBER)
            rows["cont"].pack(side="right", padx=(0, 6))
        elif t.startswith(("❌", "✅")):
            rows["s"].config(text=t, fg=GREEN if t.startswith("✅") else RED)
        elif t.startswith("❓"):
            rows["s"].config(text=t.lstrip("❓ ").strip(), fg=AMBER)
        else:
            rows["c"].config(text=t.lstrip("· ").strip()[:160], fg=AMBER)

    def _gpm_fill(self):
        for key, ck in (("s_gpm", "strong_channel"), ("w_gpm", "weak_channel")):
            if key not in self.v:
                continue
            ch = self.cfg.get(ck) or {}
            gid, gname = str(ch.get("gpm_profile_id") or ""), str(ch.get("gpm_profile_name") or "")
            self._gpm_sel[key] = (gid, gname)
            lab = next((l for l, it in (getattr(self, "_gpm_items", {}) or {}).items() if it["id"] == gid), None)
            self.v[key].set(lab or (gname or gid) if gid else self.GPM_NONE)
            if key + "_br" in self.v:
                self.v[key + "_br"].set(self._br_label(ch, gid))
        if getattr(self, "_gpm_items", None):
            self._gpm_filling = True
            try:
                self._gpm_table_fill()
            finally:
                self._gpm_filling = False
        elif not getattr(self, "_gpm_auto_started", False):
            self._gpm_auto_started = True
            self.after(800, self._gpm_auto_load)
        for key in ("s_gpm", "w_gpm"):
            self._gpm_status(key)

    def _build_config_page(self):
        page = ScrollPage(self.container)
        root = page.inner
        self._header(root, "Thông tin kênh", "Mỗi kênh cần kéo là 1 bộ thông tin riêng. Chọn kênh, điền thông tin rồi bấm Lưu.",
                     icon="id_card", color=BLUE)
        self._build_job_bar(root)
        self._build_form_bar(root)
        self._build_mode_bar(root)

        body = tk.Frame(root, bg=BG)
        body.pack(fill="both", expand=True, padx=28)
        body.grid_columnconfigure(0, weight=1)

        def hint(parent, text, **kw):
            return tk.Label(parent, text=text, font=F_S, bg=CARD, fg=SOFT, justify="left", **kw)

        # ① KÊNH: trái = tên + ID + khung trạng thái GPM · phải = bảng profile GPM
        o, b = card(body, "① Kênh mạnh", "Kênh đang có nhiều view, dùng để kéo.", icon="bolt", color=AMBER, pad=16)
        self.card_strong = o
        o.grid(row=0, column=0, sticky="nsew", pady=(0, 14))
        b.grid_columnconfigure(0, weight=5, uniform="k1")
        b.grid_columnconfigure(1, weight=6, uniform="k1")
        left = tk.Frame(b, bg=CARD)
        left.grid(row=0, column=0, sticky="nsew", padx=(0, 18))
        left.grid_columnconfigure(0, weight=1)
        self._field(left, 0, 0, "Tên kênh", "s_name")
        self._field(left, 1, 0, "ID kênh", "s_id", "Tự điền khi chọn profile GPM hoặc bấm Đăng nhập")
        st_box = tk.Frame(left, bg=CARD)
        st_box.grid(row=2, column=0, sticky="we", pady=(6, 0))
        right = tk.Frame(b, bg=CARD)
        right.grid(row=0, column=1, sticky="nsew")
        self._gpm_field(right, "s_gpm", status_parent=st_box)

        # ② KÊNH CẦN KÉO (2 kênh) / VIDEO CẦN ĐẨY VIEW (1 kênh)
        o, b = card(body, "② Kênh cần kéo", "Kênh mới sẽ được quảng bá trên kênh mạnh.", icon="target", color=PINK,
                    pad=16)
        o.grid(row=1, column=0, sticky="nsew", pady=(0, 14))
        self.card_weak = o
        g = tk.Frame(b, bg=CARD)
        g.pack(fill="x")
        for c in range(3):
            g.grid_columnconfigure(c, weight=1, uniform="k2")
        self.weak_id_fields = [self._field(g, 0, 0, "Link kênh", "w_url", "https://www.youtube.com/@…"),
                               self._field(g, 0, 1, "Tên kênh", "w_name"),
                               self._field(g, 0, 2, "ID kênh", "w_id", "Bắt đầu bằng UC")]
        self.weak_id_fields.append(self._gpm_field(g, "w_gpm", grid=dict(row=1, column=0, columnspan=3, sticky="we",
                                                                          pady=(4, 8)), table_h=4))
        self.weak_grid = g
        two = tk.Frame(b, bg=CARD)
        two.pack(fill="x", pady=(6, 0))
        self.weak_two = two
        two.grid_columnconfigure(0, weight=1, uniform="k3")
        two.grid_columnconfigure(1, weight=1, uniform="k3")
        vf = tk.Frame(two, bg=CARD)
        vf.grid(row=0, column=0, sticky="nsew", padx=(0, 12))
        import selfmode as _sm
        self.self_src = tk.Frame(vf, bg=CARD)
        tk.Label(self.self_src, text="Video cần đẩy view lấy từ", font=F_SB, bg=CARD, fg=LABEL).pack(
            anchor="w", pady=(0, 4))
        self.v["self_target"] = tk.StringVar(value=_sm.TARGET_LABELS[_sm.TARGET_LINKS])
        cb = ttk.Combobox(self.self_src, textvariable=self.v["self_target"], state="readonly", width=40,
                          values=list(_sm.TARGET_LABELS.values()))
        cb.pack(anchor="w")
        cb.bind("<<ComboboxSelected>>", lambda e: self._apply_mode_ui())
        vh = tk.Frame(vf, bg=CARD)
        vh.pack(fill="x", pady=(0, 4))
        self.wvh = vh
        self.wvid_title = tk.Label(vh, text="Video cần kéo view", font=F_SB, bg=CARD, fg=LABEL)
        self.wvid_title.pack(side="left")
        self.wvid_count = tk.Label(vh, text="", font=F_S, bg=CARD, fg=MUTED)
        self.wvid_count.pack(side="right")
        self.wvideos = textbox(vf, 4, mono=True)
        self.wvideos.pack(fill="x")
        self.wvideos.bind("<KeyRelease>", lambda e: self._count_wvideos())
        self.wvid_hint = hint(vf, "", wraplength=560)
        self.wvid_hint.pack(anchor="w", pady=(3, 0))
        cf = tk.Frame(two, bg=CARD)
        cf.grid(row=0, column=1, sticky="nsew")
        self.cmt_title = tk.Label(cf, text="Bình luận ghim", font=F_SB, bg=CARD, fg=LABEL)
        self.cmt_title.pack(anchor="w", pady=(0, 4))
        self.comment = textbox(cf, 4)
        self.comment.pack(fill="x")
        hint(cf, "Để trống = tool tự soạn theo nội dung từng video, mỗi video 1 câu khác nhau.",
             wraplength=560).pack(anchor="w", pady=(3, 0))
        plf = tk.Frame(b, bg=CARD)
        plf.pack(fill="x", pady=(4, 0))
        plf.grid_columnconfigure(0, weight=1)
        self.pl_field = self._field(plf, 0, 0, "Danh sách phát (không bắt buộc)", "w_pl",
                                    "https://www.youtube.com/playlist?list=…")

        # ③ TÙY CHỈNH KÊNH – thu gọn mặc định
        o, b = self._fold(body, "③ Tùy chỉnh kênh  ·  Hồ sơ · Trang chủ · Bài đăng",
                          "Ô để trống = tool tự chọn. Bấm Mở rộng để xem / sửa.", "wand", VIOLET, "fold_setup")
        o.grid(row=2, column=0, sticky="nsew", pady=(0, 14))
        g2 = tk.Frame(b, bg=CARD)
        g2.pack(fill="x")
        g2.grid_columnconfigure(0, weight=1, uniform="k4")
        g2.grid_columnconfigure(1, weight=1, uniform="k4")
        self.f_ltitle = self._field(g2, 0, 0, "Hồ sơ → Đường liên kết: Tiêu đề", "sp_link_title",
                                    "Trống = tên kênh cần kéo")
        self.f_lurl = self._field(g2, 0, 1, "Hồ sơ → Đường liên kết: URL", "sp_link_url",
                                  "Dán link video cần kéo. Trống = link kênh cần kéo")
        self.f_trailer = self._field(g2, 1, 0, "Video giới thiệu kênh (người chưa đăng ký)", "sp_trailer",
                                     "Dán link video – Thẻ Trang chủ")
        self.f_featured = self._field(g2, 1, 1, "Video nổi bật (người đăng ký cũ)", "sp_featured",
                                      "Dán link video cần kéo – tool đặt ĐÚNG video này")
        pf = tk.Frame(b, bg=CARD)
        pf.pack(fill="x", pady=(6, 0))
        pf.grid_columnconfigure(0, weight=1, uniform="k5")
        pf.grid_columnconfigure(1, weight=1, uniform="k5")
        l1 = tk.Frame(pf, bg=CARD)
        l1.grid(row=0, column=0, sticky="nwe", padx=(0, 10))
        tk.Label(l1, text="Video đăng lên Bài đăng", font=F_SB, bg=CARD, fg=LABEL).pack(anchor="w", pady=(0, 4))
        self.v["post_source"] = tk.StringVar(value="Video mới nhất của kênh mạnh")
        ttk.Combobox(l1, textvariable=self.v["post_source"], state="readonly", width=34,
                     values=["Video mới nhất của kênh mạnh", "Theo các link bên dưới"]).pack(anchor="w", pady=(0, 6))
        self.post_videos = textbox(l1, 2, mono=True)
        self.post_videos.pack(fill="x")
        hint(l1, "Chỉ dùng khi chọn 'Theo các link bên dưới' – mỗi dòng 1 link.").pack(anchor="w", pady=(3, 0))
        l2 = tk.Frame(pf, bg=CARD)
        l2.grid(row=0, column=1, sticky="nwe", padx=(10, 0))
        tk.Label(l2, text="Nội dung chữ của bài đăng (không bắt buộc)", font=F_SB, bg=CARD,
                 fg=LABEL).pack(anchor="w", pady=(0, 4))
        self.post_text = textbox(l2, 3)
        self.post_text.pack(fill="x")
        pw = tk.Frame(l2, bg=CARD)
        pw.pack(fill="x", pady=(6, 0))
        self.post_ai_btn = Btn(pw, "Tool tự soạn", self._compose_post, kind="secondary", icon="wand", color=VIOLET,
                               padx=10, pady=4, font=F_SB)
        self.post_ai_btn.pack(side="left")
        self.post_ai_note = tk.Label(pw, text="Soạn theo ngôn ngữ + chủ đề kênh mạnh, kèm video sẽ đăng. "
                                              "Xem / sửa rồi bấm Lưu.", font=F_S, bg=CARD, fg=SOFT,
                                     justify="left", wraplength=330)
        self.post_ai_note.pack(side="left", padx=(8, 0))
        ck = tk.Frame(b, bg=CARD)
        ck.pack(fill="x", pady=(10, 0))
        tk.Label(ck, text="Làm những phần:", font=F_SB, bg=CARD, fg=LABEL).grid(row=0, column=0, columnspan=3,
                                                                              sticky="w", pady=(0, 2))
        self.sp = {}
        for i, (key, text) in enumerate((("do_profile_link", "Đường liên kết Hồ sơ"),
                                         ("do_trailer", "Video giới thiệu (người chưa ĐK)"),
                                         ("do_featured", "Video nổi bật (người ĐK cũ)"),
                                         ("do_playlist", "Danh sách phát đơn"),
                                         ("do_featured_channel", "Kênh nổi bật"),
                                         ("do_posts", "Bài đăng có video"))):
            self.sp[key] = tk.BooleanVar(value=True)
            w_ = ttk.Checkbutton(ck, text=text, variable=self.sp[key], style="Card.TCheckbutton")
            w_.grid(row=1 + i // 3, column=i % 3, sticky="w", padx=(0, 24), pady=2)
            if key == "do_featured_channel":
                self.sp_featch = w_

        # ④ CÀI ĐẶT NÂNG CAO – thu gọn mặc định, ô nhỏ xếp 3 cột
        o, b = self._fold(body, "④ Cài đặt nâng cao",
                          "Trình duyệt, GPM, số thẻ, tốc độ… – thường giữ nguyên mặc định.", "sliders", BLUE,
                          "fold_adv")
        o.grid(row=3, column=0, sticky="nsew", pady=(0, 14))
        adv = tk.Frame(b, bg=CARD)
        adv.pack(fill="x")
        for c in range(3):
            adv.grid_columnconfigure(c, weight=1, uniform="k6")
        self._adv_n = 0

        def opt(label, widget_fn, unit=""):
            i = self._adv_n
            self._adv_n += 1
            f = tk.Frame(adv, bg=CARD)
            f.grid(row=i // 3, column=i % 3, sticky="we", padx=(0, 16), pady=5)
            tk.Label(f, text=label, font=F_SB, bg=CARD, fg=LABEL).pack(anchor="w", pady=(0, 3))
            r = tk.Frame(f, bg=CARD)
            r.pack(fill="x")
            w_ = widget_fn(r)
            w_.pack(side="left", fill="x" if isinstance(w_, tk.Entry) else None,
                    expand=isinstance(w_, tk.Entry), ipady=4 if isinstance(w_, tk.Entry) else 0)
            if unit:
                tk.Label(r, text="  " + unit, font=F_S, bg=CARD, fg=SOFT).pack(side="left")
            return f

        self.v["lang"] = tk.StringVar(value="vi")
        self.v["min_views"] = tk.StringVar(value="20")
        self.v["interval"] = tk.StringVar(value="5")
        self.v["browser"] = tk.StringVar(value="Cốc Cốc")
        self.v["browser_path"] = tk.StringVar()
        self.v["source"] = tk.StringVar(value="Video của kênh cần kéo")
        self.v["es_count"] = tk.StringVar(value="2")
        self.v["card_count"] = tk.StringVar(value="3")
        self.v["start_min"] = tk.StringVar(value="0")
        self.v["delay_lo"] = tk.StringVar(value="2")
        self.v["delay_hi"] = tk.StringVar(value="5")
        self.v["speed"] = tk.StringVar(value="Vừa")
        self.v["max_videos"] = tk.StringVar(value="0")
        self.gpm_api = tk.StringVar(value=get_setting("gpm_api", "") or "http://127.0.0.1:19995")
        self.gpm_api.trace_add("write", lambda *_: set_setting("gpm_api", self.gpm_api.get().strip()))
        self.gpm_key = tk.StringVar(value=get_setting("gpm_key", "") or "")
        self.gpm_key.trace_add("write", lambda *_: set_setting("gpm_key", self.gpm_key.get().strip()))

        def delay_row(f):
            r = tk.Frame(f, bg=CARD)
            ttk.Spinbox(r, from_=0, to=120, textvariable=self.v["delay_lo"], width=4).pack(side="left")
            tk.Label(r, text=" – ", font=F_S, bg=CARD, fg=MUTED).pack(side="left")
            ttk.Spinbox(r, from_=0, to=300, textvariable=self.v["delay_hi"], width=4).pack(side="left")
            return r
        sb = lambda var, a, b_, w=6: (lambda f: ttk.Spinbox(f, from_=a, to=b_, textvariable=self.v[var], width=w))
        cbx = lambda var, vals, w=10: (lambda f: ttk.Combobox(f, textvariable=self.v[var], values=vals, width=w,
                                                               state="readonly"))
        opt("Trình duyệt riêng", cbx("browser", ["Cốc Cốc", "Chrome"]), "khi không dùng GPM")
        opt("Địa chỉ API GPM-Login", lambda f: entry(f, self.gpm_api))
        opt("Mã kết nối GPM (máy khác)", lambda f: entry(f, self.gpm_key))
        opt("Đường dẫn trình duyệt", lambda f: entry(f, self.v["browser_path"]))
        opt("Ngôn ngữ YouTube Studio", cbx("lang", ["vi", "en"], 6))
        opt("Tốc độ chuột & gõ phím", cbx("speed", ["Nhanh", "Vừa", "Chậm"]))
        self.opt_source = opt("Video gắn màn hình kết thúc & thẻ", cbx(
            "source", ["Video của kênh cần kéo", "Video mới nhất của kênh mạnh"], 26))
        self.opt_es = opt("Số video ở màn hình kết thúc", sb("es_count", 1, 2), "1–2")
        opt("Số thẻ video", sb("card_count", 1, 5), "1–5")
        opt("Thẻ đầu tiên ở phút", sb("start_min", 0, 600), "phút")
        opt("Khoảng cách giữa các thẻ", sb("interval", 1, 60), "phút")
        opt("Nghỉ giữa các thao tác", delay_row, "giây")
        opt("Số video kéo tối đa mỗi lần", sb("max_videos", 0, 500), "0 = hết")
        opt("Ngưỡng lọc video", sb("min_views", 1, 10000, 7), "view / 60 phút")
        self.b_clear = tk.BooleanVar(value=False)
        self.b_collab = tk.BooleanVar(value=True)
        cof = tk.Frame(adv, bg=CARD)
        i = self._adv_n
        cof.grid(row=i // 3, column=i % 3, sticky="w", pady=(22, 5))
        self.collab_opt = ttk.Checkbutton(cof, text="Bật tính năng cộng tác", variable=self.b_collab,
                                          style="Card.TCheckbutton")
        self.collab_opt.pack(anchor="w")
        self.v["es_pl"] = tk.StringVar(value="0")
        self.v["cd_pl"] = tk.StringVar(value="0")
        plf = tk.Frame(adv, bg=CARD)
        plf.grid(row=i // 3 + 1, column=0, columnspan=3, sticky="w", pady=(10, 2))
        tk.Label(plf, text="Danh sách phát", font=F_SB, bg=CARD, fg=LABEL).pack(anchor="w")
        ttk.Checkbutton(plf, text="Màn hình kết thúc: 1 video + 1 danh sách phát", variable=self.v["es_pl"],
                        onvalue="1", offvalue="0", style="Card.TCheckbutton").pack(anchor="w")
        ttk.Checkbutton(plf, text="Thẻ: thêm 1 thẻ danh sách phát (sau các thẻ video)", variable=self.v["cd_pl"],
                        onvalue="1", offvalue="0", style="Card.TCheckbutton").pack(anchor="w")
        tk.Label(plf, text="Ô 'Danh sách phát' ở phần ② trống = tool tự chọn danh sách phát công khai nhiều video "
                           "nhất của kênh cần kéo.", font=F_S, bg=CARD, fg=SOFT).pack(anchor="w")

        # thanh lưu
        foot = tk.Frame(body, bg=BG)
        foot.grid(row=4, column=0, sticky="we", pady=(0, 28))
        Btn(foot, "Lưu thông tin", self.save_config, kind="solid", color=BLUE, icon="save", padx=26,
            pady=10).pack(side="right")
        self.save_note = tk.Label(foot, text="", font=F_S, bg=BG, fg=OK)
        self.save_note.pack(side="right", padx=14)
        return page

    # ---------------------------------------------------------- cách kéo: 2 kênh / chính kênh
    MODE_TEXT = {
        "pair": "Kênh mạnh (nhiều view) đẩy người xem sang 1 kênh KHÁC. Cần đăng nhập cả 2 kênh.",
        "self": "1 kênh tự đẩy view: video đang nhiều view gắn màn hình kết thúc, thẻ, bình luận ghim trỏ sang "
                "video cần đẩy của CHÍNH kênh. Chỉ cần đăng nhập 1 lần. Tool tự bỏ Cộng tác và Kênh nổi bật.",
    }

    def _build_mode_bar(self, root):
        o = tk.Frame(root, bg=CARD, highlightthickness=1, highlightbackground=BORDER)
        o.pack(fill="x", padx=28, pady=(0, 14))
        b = tk.Frame(o, bg=CARD)
        b.pack(fill="x", padx=20, pady=10)
        head_dot(b, "Cách kéo", PINK).pack(anchor="w")
        self.mode_seg = tk.Frame(b, bg=CARD)
        self.mode_seg.pack(anchor="w", pady=(8, 6))
        self.mode_hint = tk.Label(b, text="", font=F_S, bg=CARD, fg=MUTED, justify="left", wraplength=980)
        self.mode_hint.pack(anchor="w")
        self.v["mode"] = tk.StringVar(value="pair")
        self._render_mode_seg()

    def _render_mode_seg(self):
        for w_ in self.mode_seg.winfo_children():
            w_.destroy()
        cur = self.v["mode"].get()
        for key, label, ic, col in (("pair", "Kéo cho kênh khác  ·  2 kênh", "target", PINK),
                                    ("self", "Kéo cho chính kênh  ·  1 kênh", "bolt", ORANGE)):
            Btn(self.mode_seg, label, lambda k=key: self._set_mode(k), kind="vivid" if cur == key else "secondary",
                color=col, icon=ic, padx=16, pady=8, font=F_B).pack(side="left", padx=(0, 10))
        self.mode_hint.config(text=self.MODE_TEXT[cur])

    def _set_mode(self, mode):
        if self.v["mode"].get() == mode:
            return
        self.v["mode"].set(mode)
        self._render_mode_seg()
        self._apply_mode_ui()

    def _self_target(self):
        import selfmode as _sm
        lab = self.v["self_target"].get()
        return next((k for k, v in _sm.TARGET_LABELS.items() if v == lab), _sm.TARGET_LINKS)

    def _apply_mode_ui(self):
        """Hiện / ẩn đúng các ô theo cách kéo đang chọn – không ô nào thừa."""
        import selfmode as _sm
        one = self.v["mode"].get() == "self"
        tgt = self._self_target()
        self.card_strong._title.config(text="① KÊNH CỦA BẠN" if one else "① KÊNH MẠNH")
        self.card_strong._sub.config(text="Kênh tự đẩy view cho video của chính nó." if one
                                     else "Kênh đang có nhiều view, dùng để kéo.")
        self.card_weak._title.config(text="② VIDEO CẦN ĐẨY VIEW & BÌNH LUẬN" if one else "② KÊNH CẦN KÉO")
        self.card_weak._sub.config(text="Video của chính kênh sẽ được các video nhiều view giới thiệu." if one
                                   else "Kênh mới sẽ được quảng bá trên kênh mạnh.")
        for f in self.weak_id_fields:
            f.grid_remove() if one else f.grid()
        if one:   # 1 kênh: bỏ hẳn khung thông tin kênh cần kéo (không để lại khoảng trống)
            self.weak_grid.pack_forget()
        elif not self.weak_grid.winfo_manager():
            self.weak_grid.pack(fill="x", before=self.weak_two)
        if one:
            self.self_src.pack(fill="x", pady=(0, 12), before=self.wvh)
        else:
            self.self_src.pack_forget()
        need_links = (not one) or tgt == _sm.TARGET_LINKS
        self.wvid_title.config(text=("Link video cần đẩy view" if one else "Video cần kéo view")
                               + ("" if need_links else "  – không cần điền"))
        self.wvid_hint.config(text=(
            "Mỗi dòng 1 link. Dòng đầu được gắn trước. Tool không bao giờ gắn 1 video vào chính nó."
            if one and need_links else
            "Tool tự lấy video MỚI NHẤT của kênh mỗi lần chạy." if one and tgt == _sm.TARGET_NEWEST else
            "Mỗi lần chạy tool tự chọn các video ÍT VIEW NHẤT trong 20 video mới nhất của kênh." if one else
            "Mỗi dòng 1 link, điền bao nhiêu video cũng được: video mới, hoặc các video đang ít view cần đẩy. "
            "Video ở dòng đầu được ưu tiên gắn trước. Không cần điền nếu chọn \"Video mới nhất của kênh mạnh\" "
            "ở Tùy chọn."))
        self.cmt_title.config(text="Bình luận ghim")
        for f, auto, manual in ((self.f_trailer, "Để trống = TỰ ĐỘNG lấy video MỚI NHẤT của kênh mỗi lần chạy",
                                 "Dán link video – Thẻ Trang chủ"),
                                (self.f_featured, "Để trống = TỰ ĐỘNG lấy video NHIỀU VIEW NHẤT trong 7 ngày gần nhất",
                                 "Dán link video cần kéo – tool đặt ĐÚNG video này")):
            f.winfo_children()[-1].config(text=auto if one else manual, fg=OK if one else SOFT)
        self.f_ltitle.winfo_children()[-1].config(
            text="Trống = tên kênh. Nên ghi câu mời bấm, vd: ▶ Nghe truyện mới nhất" if one else "Trống = tên kênh cần kéo")
        self.f_lurl.winfo_children()[-1].config(
            text="Dán link video muốn khách bấm vào. Trống = video cần đẩy đầu tiên (không có thì bỏ qua)" if one
            else "Dán link video cần kéo. Trống = link kênh cần kéo")
        if one:
            self.opt_source.grid_remove()
            self.collab_opt.pack_forget()
            self.sp_featch.grid_remove()
        else:
            self.opt_source.grid()
            self.collab_opt.pack(anchor="w")
            self.sp_featch.grid()
        self._apply_mode_run()

    def _apply_mode_run(self):
        """Trang Chạy tool: chế độ 1 kênh ẩn bước 2 (đăng nhập kênh cần kéo) và ô Cộng tác."""
        one = (getattr(self, "cfg", None) or {}).get("mode") == "self"   # theo file kênh ĐÃ LƯU
        rows = getattr(self, "step_rows", {})
        if rows.get(2) is not None:
            if one:
                rows[2].pack_forget()
            else:
                rows[2].pack(fill="x", pady=(0, 14), before=rows[3])
        cc = getattr(self, "collab_check", None)
        if cc is not None:
            cc.grid_remove() if one else cc.grid()
        if rows.get(1) is not None:
            self.step_title[1].config(text="1. Đăng nhập kênh" if one else "1. Đăng nhập kênh mạnh")

    # ---------------------------------------------------------- biểu mẫu .txt
    def _build_form_bar(self, root):
        o = tk.Frame(root, bg=CARD, highlightthickness=1, highlightbackground=BORDER)
        o.pack(fill="x", padx=28, pady=(0, 14))
        b = tk.Frame(o, bg=CARD)
        b.pack(fill="x", padx=20, pady=10)
        t = tk.Frame(b, bg=CARD)
        t.pack(side="left", fill="x", expand=True)
        head_dot(t, "Biểu mẫu Notepad (không bắt buộc)", VIOLET).pack(anchor="w", pady=(0, 2))
        tk.Label(t, text="Điền nhanh bằng file .txt rồi bấm Nạp biểu mẫu.", font=F_S, bg=CARD, fg=MUTED,
                 justify="left").pack(anchor="w")
        r = tk.Frame(b, bg=CARD)
        r.pack(side="right")
        Btn(r, "Mở thư mục biểu mẫu", self.form_open_dir, kind="secondary", color=GOLD, icon="folder", padx=12,
            pady=6, font=F_SB).pack(side="left")
        Btn(r, "Nạp biểu mẫu", self.form_load, kind="solid", color=GREEN, icon="arrow_down", padx=12, pady=6,
            font=F_SB).pack(side="left", padx=(8, 0))
        Btn(r, "Xuất kênh ra biểu mẫu", self.form_export, kind="secondary", color=CYAN, icon="arrow_up",
            padx=12, pady=6, font=F_SB).pack(side="left", padx=(8, 0))

    def form_open_dir(self):
        import bieu_mau
        path = bieu_mau.write_folder()
        try:
            os.startfile(path)  # Windows: mở thư mục bằng File Explorer
        except Exception:
            messagebox.showinfo("Thư mục biểu mẫu", f"Thư mục biểu mẫu nằm ở:\n{path}")

    def _form_values(self):
        g = lambda k: self.v[k].get().strip()
        return dict(
            job_name=g("job_name"), s_name=g("s_name"), s_id=g("s_id"), w_url=g("w_url"), w_name=g("w_name"),
            w_id=g("w_id"), w_pl=g("w_pl"), comment=self.comment.get("1.0", "end").strip(),
            wvideos=self.wvideos.get("1.0", "end").strip(), videos=self.videos.get("1.0", "end").strip(),
            sp_link_title=g("sp_link_title"), sp_link_url=g("sp_link_url"), sp_trailer=g("sp_trailer"),
            sp_featured=g("sp_featured"), post_videos=self.post_videos.get("1.0", "end").strip(),
            post_text=self.post_text.get("1.0", "end").strip(), do={k: v.get() for k, v in self.sp.items()},
            post_source=g("post_source"),
            browser=g("browser"), source=g("source"), es_count=g("es_count"), card_count=g("card_count"),
            start_min=g("start_min"), interval=g("interval"), delay=f"{g('delay_lo')} – {g('delay_hi')}",
            speed=g("speed"), max_videos=g("max_videos"), min_views=g("min_views"),
            collab="Có" if self.b_collab.get() else "Không", replace="Có" if self.b_clear.get() else "Không",
            mode=self.v["mode"].get(), self_target=self._self_target())

    def form_export(self):
        import bieu_mau
        bieu_mau.write_folder()
        safe = re.sub(r"[^\w\- ]+", "", self.v["job_name"].get().strip() or "Kenh").strip().replace(" ", "_") or "Kenh"
        path = filedialog.asksaveasfilename(title="Lưu biểu mẫu của kênh đang chọn", initialdir=bieu_mau.FORM_DIR,
                                            initialfile=f"{safe}.txt", defaultextension=".txt",
                                            filetypes=[("Biểu mẫu", "*.txt")])
        if not path:
            return
        with open(path, "w", encoding="utf-8-sig", newline="\r\n") as f:
            f.write(bieu_mau.build(self._form_values(), self.v["mode"].get()))
        self.save_note.config(text=f"✓ Đã xuất biểu mẫu: {os.path.basename(path)}")
        try:
            os.startfile(path)
        except Exception:
            pass

    def form_load(self):
        import bieu_mau
        bieu_mau.write_folder()
        path = filedialog.askopenfilename(title="Chọn file biểu mẫu đã điền", initialdir=bieu_mau.FORM_DIR,
                                          filetypes=[("Biểu mẫu", "*.txt"), ("Tất cả", "*.*")])
        if not path:
            return
        try:
            with open(path, encoding="utf-8-sig") as f:
                text = f.read()
        except UnicodeDecodeError:
            with open(path, encoding="cp1258", errors="replace") as f:
                text = f.read()
        d, warn = bieu_mau.parse(text)
        if not any(d.get(k) for k in ("s_id", "s_name", "w_url", "w_name", "wvideos", "sp_trailer", "sp_featured")):
            messagebox.showwarning("Biểu mẫu trống", "File này chưa có thông tin nào – hãy điền rồi lưu file (Ctrl+S).")
            return
        self._apply_form(d, warn)

    def _apply_form(self, d, warn):
        import re as _re
        import selfmode as _sm
        if d.get("mode") in ("pair", "self"):          # biểu mẫu nào thì chuyển đúng CÁCH KÉO đó
            self._set_mode(d["mode"])
        if d.get("self_target") in _sm.TARGET_LABELS:
            self.v["self_target"].set(_sm.TARGET_LABELS[d["self_target"]])
            try:
                self._apply_mode_ui()
            except Exception:
                pass
        for k in ("job_name", "s_name", "s_id", "w_url", "w_name", "w_id", "w_pl",
                  "sp_link_title", "sp_link_url", "sp_trailer", "sp_featured"):
            # tên / ID / link kênh để trống trong biểu mẫu -> giữ cái đang có (đăng nhập sẽ tự điền)
            if k in d and (d[k] or k not in ("job_name", "s_name", "s_id", "w_url", "w_name", "w_id")):
                self.v[k].set(d[k])
        for k, box in (("comment", self.comment), ("wvideos", self.wvideos), ("videos", self.videos),
                       ("post_videos", self.post_videos), ("post_text", self.post_text)):
            if d.get(k):          # mục để trống trong biểu mẫu -> giữ nội dung đang có
                box.delete("1.0", "end")
                box.insert("1.0", d[k])
        for k, val in (d.get("do") or {}).items():
            if k in self.sp:
                self.sp[k].set(val)
        opt = lambda k: str(d.get(k) or "").strip()
        if opt("post_source"):
            self.v["post_source"].set("Theo các link bên dưới" if "link" in opt("post_source").lower()
                                      else "Video mới nhất của kênh mạnh")
        if opt("browser"):
            self.v["browser"].set("Chrome" if "chrome" in opt("browser").lower() else "Cốc Cốc")
        if opt("source"):
            self.v["source"].set("Video mới nhất của kênh mạnh" if "mạnh" in opt("source").lower()
                                 else "Video của kênh cần kéo")
        for k in ("es_count", "card_count", "start_min", "interval", "max_videos", "min_views"):
            m = _re.search(r"\d+", opt(k))
            if m:
                self.v[k].set(m.group(0))
        nums = _re.findall(r"\d+", opt("delay"))
        if len(nums) >= 2:
            self.v["delay_lo"].set(nums[0])
            self.v["delay_hi"].set(nums[1])
        if opt("speed"):
            sp = opt("speed").lower()
            self.v["speed"].set("Nhanh" if "nhanh" in sp else "Chậm" if "chậm" in sp else "Vừa")
        for k, var in (("collab", self.b_collab), ("replace", self.b_clear)):
            if opt(k):
                var.set(opt(k).lower().startswith(("c", "y", "x", "1", "bật")))
        self._count_wvideos()
        self._count_videos()
        errs = self._validate()
        msg = "Đã nạp biểu mẫu vào các ô.\n\nKiểm tra lại rồi bấm 'Lưu thông tin' để lưu."
        if warn:
            msg += "\n\nLưu ý:\n• " + "\n• ".join(warn)
        if errs:
            msg += "\n\nCần sửa trước khi Lưu:\n• " + "\n• ".join(errs)
            if any("UC" in e for e in errs):
                msg += ("\n\nChưa có ID kênh? Vào Chạy tool → bấm Đăng nhập kênh đó: đăng nhập xong tool "
                        "TỰ ĐIỀN tên + ID kênh.")
            messagebox.showwarning("Nạp biểu mẫu", msg)
        else:
            messagebox.showinfo("Nạp biểu mẫu", msg)

    # ---------------------------------------------------------- danh sách kênh
    def _build_job_bar(self, root):
        o = tk.Frame(root, bg=CARD, highlightthickness=1, highlightbackground=BORDER)
        o.pack(fill="x", padx=28, pady=(0, 20))
        hd = tk.Frame(o, bg=CARD)
        hd.pack(fill="x", padx=14, pady=(10, 9))
        head_dot(hd, "Danh sách kênh đã lưu", BLUE).pack(side="left")
        tk.Label(hd, text="mỗi kênh 1 file riêng", font=F_HINT, bg=CARD, fg=SOFT).pack(side="left", padx=(8, 0))
        tk.Frame(o, bg=BORDER, height=1).pack(fill="x")
        b = tk.Frame(o, bg=CARD)
        b.pack(fill="x", padx=14, pady=12)
        left = tk.Frame(b, bg=CARD)
        left.pack(side="left", fill="x", expand=True)
        row = tk.Frame(left, bg=CARD)
        row.pack(anchor="w", pady=(6, 0))
        self.job_combo = ttk.Combobox(row, state="readonly", width=50, font=F_B)
        self.job_combo.pack(side="left", ipady=3)
        self.job_combo.bind("<<ComboboxSelected>>", self._on_job_selected)
        self.job_enabled = tk.BooleanVar(value=True)
        ttk.Checkbutton(row, text="Bật khi chạy tất cả kênh", variable=self.job_enabled,
                        style="Card.TCheckbutton", command=self._toggle_job_enabled).pack(side="left", padx=(16, 0))
        nm = tk.Frame(left, bg=CARD)
        nm.pack(anchor="w", fill="x", pady=(10, 0))
        tk.Label(nm, text="Tên hiển thị trong tool", font=F_SB, bg=CARD, fg=LABEL).pack(side="left")
        self.v["job_name"] = tk.StringVar()
        entry(nm, self.v["job_name"]).pack(side="left", padx=(10, 0), ipady=5, ipadx=6)
        self.job_count = tk.Label(nm, text="", font=F_S, bg=CARD, fg=MUTED)
        self.job_count.pack(side="left", padx=(16, 0))

        right = tk.Frame(b, bg=CARD)
        right.pack(side="right", anchor="n")
        Btn(right, "Thêm kênh mới", self.job_add, kind="solid", color=GREEN, icon="plus", padx=12, pady=6,
            font=F_SB).pack(side="left")
        Btn(right, "Thêm kênh mạnh", self.job_add_strong, kind="solid", color=AMBER, icon="bolt", padx=12, pady=6,
            font=F_SB).pack(side="left", padx=(8, 0))
        Btn(right, "Nhân bản", self.job_duplicate, kind="secondary", color=CYAN, icon="copy", padx=12, pady=6,
            font=F_SB).pack(side="left", padx=(8, 0))
        Btn(right, "", lambda: self.job_move(-1), kind="secondary", color=BLUE, icon="arrow_up", padx=8, pady=6,
            font=F_SB).pack(side="left", padx=(8, 0))
        Btn(right, "", lambda: self.job_move(1), kind="secondary", color=BLUE, icon="arrow_down", padx=8, pady=6,
            font=F_SB).pack(side="left", padx=(4, 0))
        Btn(right, "Xóa kênh", self.job_delete, kind="soft", color=RED, icon="trash", padx=12, pady=6,
            font=F_SB).pack(side="left", padx=(8, 0))

    def login(self, who):
        """Đăng nhập kênh bằng trình duyệt RIÊNG của kênh đó. Chưa đăng nhập -> luôn tạo trình duyệt SẠCH.
        Đã đăng nhập -> hỏi: dùng tiếp, hay xóa sạch để đăng nhập lại từ đầu."""
        import browser as _b
        ch = (self.cfg or {}).get("strong_channel" if who == "strong" else "weak_channel", {}) or {}
        label = ch.get("name") or ("kênh mạnh" if who == "strong" else "kênh cần kéo")
        args = ["login", who]
        try:
            st = None if _b.gpm_id(self.cfg or {}, who) else _b.login_saved(self.cfg or {}, who)
        except Exception:
            st = None
        if st:
            ans = messagebox.askyesnocancel(
                "Đăng nhập", f"Trình duyệt của {label} ĐÃ đăng nhập.\n\n"
                             f"• Có: xóa sạch trình duyệt của kênh này, đăng nhập lại từ đầu\n"
                             f"• Không: mở trình duyệt đang có để kiểm tra / đổi kênh")
            if ans is None:
                return
            if ans:
                args.append("--fresh")
        # chưa đăng nhập: mở trình duyệt RIÊNG của kênh này (không tự xóa gì – tránh mất đăng nhập vừa làm)
        # kênh chưa có ID: vẫn cho đăng nhập – tool tự đọc tên + ID kênh vừa đăng nhập và tự điền vào file kênh
        self.run(args, need_config=False, on_done=self._after_login)

    def _after_login(self):
        """Đăng nhập xong: tool có thể vừa tự điền tên + ID kênh vào file kênh -> hiện lên form."""
        try:
            data = jobs.load(self.cfg_path)
        except Exception:
            data = None
        if data:
            changed = any(str((data.get(k) or {}).get("channel_id") or "") !=
                          str((self.cfg.get(k) or {}).get("channel_id") or "")
                          for k in ("strong_channel", "weak_channel")) or \
                data.get("job_name") != self.cfg.get("job_name")
            if changed:
                if self._dirty():   # đang sửa dở: chỉ điền các ô kênh, giữ phần bạn đang gõ
                    s_, w_ = data.get("strong_channel", {}) or {}, data.get("weak_channel", {}) or {}
                    for key, val in (("s_name", s_.get("name")), ("s_id", s_.get("channel_id")),
                                     ("w_name", w_.get("name")), ("w_id", w_.get("channel_id")),
                                     ("w_url", w_.get("url")), ("job_name", data.get("job_name"))):
                        if val and key in self.v and not self.v[key].get().strip():
                            self.v[key].set(val)
                    for k in ("strong_channel", "weak_channel"):
                        self.cfg.setdefault(k, {}).update({x: (data.get(k) or {}).get(x) for x in
                                                           ("channel_id", "profile_dir") if (data.get(k) or {}).get(x)})
                else:
                    self._load_job(jobs.load(self.cfg_path))
                self._refresh_job_bar()
        self._refresh_login()

    def _refresh_login(self):
        """Hiện 'ĐÃ ĐĂNG NHẬP' / 'CHƯA ĐĂNG NHẬP' cạnh bước 1–2 theo hồ sơ trình duyệt đã lưu của kênh đang chọn."""
        import browser as _b
        for who, lb in (getattr(self, "login_badge", {}) or {}).items():
            try:
                if not lb.winfo_exists():
                    continue
                st = _b.login_saved(self.cfg or {}, who)
            except Exception:
                st = None
            if st:
                lb.config(text="✓ ĐÃ ĐĂNG NHẬP", bg=tint(GREEN, 0.82), fg=on_tint(GREEN))
            elif st is False:
                lb.config(text="CHƯA ĐĂNG NHẬP", bg=tint(AMBER, 0.82), fg=on_tint(AMBER))
            else:   # trình duyệt của tool đang mở, chưa đọc được – không báo nhầm là chưa đăng nhập
                lb.config(text="TRÌNH DUYỆT ĐANG MỞ", bg=tint(BLUE, 0.82), fg=on_tint(BLUE))

    @staticmethod
    def _auto_name(j):
        """Tên dễ nhận ra cho file kênh: 'Kênh mạnh → Kênh cần kéo' hoặc 'Tên kênh · kéo cho chính kênh'."""
        s_ = str((j.get("strong_channel") or {}).get("name") or "").strip()
        w_ = str((j.get("weak_channel") or {}).get("name") or "").strip()
        if j.get("mode") == "self":
            return f"{s_} · kéo cho chính kênh" if s_ else ""
        if s_ and w_:
            return f"{s_} → {w_}"
        return s_ or (f"? → {w_}" if w_ else "")

    def _rename_default_jobs(self):
        """File kênh còn tên mặc định ('Kênh 1', 'Kênh 2 (bản sao)'...) -> tự đặt tên theo tên kênh."""
        import re as _re
        for j in self.jobs:
            name = str(j.get("job_name") or "").strip()
            if name and not _re.fullmatch(r"(Kênh|Kenh) ?\d*( \(bản sao\))?|Kênh mới", name):
                continue
            new = self._auto_name(j)
            if new and new != name:
                try:
                    data = jobs.load(j["_path"])
                    data["job_name"] = new
                    jobs.save(j["_path"], data)
                    j["job_name"] = new
                    if j["_path"] == self.cfg_path:
                        clean = not self._dirty()
                        self.cfg["job_name"] = new
                        self.v["job_name"].set(new)
                        if clean and getattr(self, "_saved_snap", None) is not None:
                            self._saved_snap = self._form_snapshot()
                except Exception:
                    pass

    def _refresh_job_bar(self):
        self.jobs = jobs.list_jobs()
        self._rename_default_jobs()
        import browser as _b

        def mark(j):
            try:
                st = _b.login_saved(dict(j), "strong")
            except Exception:
                st = None
            return "  ✓" if st else "  · chưa đăng nhập"
        names = [f"{i}. {j['job_name']}" + mark(j) + ("" if j.get("enabled", True) else "   (đang tắt)")
                 for i, j in enumerate(self.jobs, 1)]
        self.job_combo["values"] = names
        idx = next((i for i, j in enumerate(self.jobs) if j["_path"] == self.cfg_path), 0)
        if names:
            self.job_combo.current(idx)
        on = sum(1 for j in self.jobs if j.get("enabled", True))
        self.job_count.config(text=f"{len(self.jobs)} kênh · {on} đang bật")
        self._update_run_label()

    def _update_run_label(self):
        self._sb_user_refresh()
        if hasattr(self, "run_job_label") and getattr(self, "cfg", None):
            self.run_job_label.config(text=f"Kênh đang chọn:  {self.cfg.get('job_name', '')}")
            self.after(50, self._refresh_login)

    def _form_snapshot(self):
        return (tuple(sorted((k, v.get()) for k, v in self.v.items())),
                self.comment.get("1.0", "end").strip(), self.wvideos.get("1.0", "end").strip(),
                self.post_videos.get("1.0", "end").strip(), self.post_text.get("1.0", "end").strip(),
                tuple(v.get() for v in self.sp.values()),
                self.b_clear.get(), self.b_collab.get())

    def _dirty(self):
        return getattr(self, "_saved_snap", None) is not None and self._form_snapshot() != self._saved_snap

    def _confirm_leave(self):
        """Có thay đổi chưa lưu -> hỏi lưu. Trả về False nếu người dùng bấm Hủy."""
        if not self._dirty():
            return True
        ans = messagebox.askyesnocancel("Chưa lưu", f"Kênh '{self.cfg.get('job_name')}' có thay đổi chưa lưu.\n"
                                                    "Lưu lại trước khi chuyển?")
        if ans is None:
            return False
        if ans:
            return self.save_config(quiet=True)
        return True

    def _on_job_selected(self, _e=None):
        idx = self.job_combo.current()
        if idx < 0 or idx >= len(self.jobs) or self.jobs[idx]["_path"] == self.cfg_path:
            return
        if not self._confirm_leave():
            self._refresh_job_bar()
            return
        self._load_job(self.jobs[idx])

    def _toggle_job_enabled(self):
        data = jobs.load(self.cfg_path)
        data["enabled"] = self.job_enabled.get()
        jobs.save(self.cfg_path, data)
        self.cfg["enabled"] = data["enabled"]
        self._refresh_job_bar()

    def job_add(self):
        if not self._confirm_leave():
            return
        j = jobs.create(f"Kênh {len(self.jobs) + 1}")
        self._load_job(j)
        if messagebox.askyesno(
                "Thêm kênh mới",
                "Đã tạo 1 file kênh mới (các kênh cũ giữ nguyên, vẫn gỡ được bất cứ lúc nào).\n\n"
                "Đăng nhập kênh mạnh của file này NGAY BÂY GIỜ?\n"
                "Tool mở 1 trình duyệt riêng – bạn đăng nhập, chọn đúng kênh, đóng cửa sổ rồi bấm Tiếp tục: "
                "tool TỰ ĐIỀN tên + ID kênh, không cần gõ tay.\n\n"
                "• Có: đăng nhập ngay\n• Không: tự điền tay sau"):
            self.show("run")
            self.login("strong")

    def job_add_strong(self):
        """Thêm 1 kênh mạnh nữa cùng kéo cho kênh cần kéo đang chọn: giữ nguyên thông tin kênh cần kéo,
        để trống kênh mạnh & danh sách video kênh mạnh để điền mới."""
        if not self._confirm_leave():
            return
        weak = self.cfg.get("weak_channel", {}).get("name") or "kênh cần kéo"
        n = 1 + sum(1 for j in jobs.list_jobs()
                    if j.get("weak_channel", {}).get("channel_id") == self.cfg.get("weak_channel", {}).get("channel_id"))
        j = jobs.create(f"{weak} ← kênh mạnh {n}", copy_from=self.cfg)
        data = jobs.load(j["_path"])
        data["strong_channel"].update(name="", channel_id="", profile_dir="")
        data["pull_videos"] = []
        jobs.save(j["_path"], data)
        self._load_job(jobs.load(j["_path"]))
        messagebox.showinfo("Thêm kênh mạnh",
                            f"Đã tạo bộ mới kéo cho kênh \"{weak}\".\n\nHãy điền Tên + ID của kênh mạnh mới rồi bấm "
                            "Lưu thông tin, sau đó đăng nhập kênh mạnh mới (Chạy tool → bước 1).\n\n"
                            "Bấm \"Chạy tất cả kênh\" để mọi kênh mạnh lần lượt kéo cho kênh này.")

    def job_duplicate(self):
        if not self._confirm_leave():
            return
        j = jobs.create(self.cfg.get("job_name", "Kênh") + " (bản sao)", copy_from=self.cfg)
        self._load_job(j)

    def job_move(self, step):
        jobs.move(self.cfg, step)
        self._refresh_job_bar()

    def job_delete(self):
        if len(self.jobs) <= 1:
            messagebox.showinfo("Không xóa được", "Phải còn ít nhất 1 kênh.")
            return
        if not messagebox.askyesno("Xóa kênh", f"Xóa kênh '{self.cfg.get('job_name')}' khỏi tool?\n\n"
                                                "(Không ảnh hưởng gì tới kênh YouTube, chỉ xóa bộ thông tin trong tool.)"):
            return
        jobs.delete(self.cfg)
        self._saved_snap = None
        self._load_job(jobs.list_jobs()[0])

    def _load_job(self, job):
        self.cfg = jobs.load(job["_path"])
        self.cfg_path = job["_path"]
        set_setting("current_job", os.path.basename(self.cfg_path))
        self._fill_form()
        self.v["job_name"].set(self.cfg.get("job_name", ""))
        self.job_enabled.set(bool(self.cfg.get("enabled", True)))
        self._refresh_job_bar()
        self.load_videos()
        self._saved_snap = self._form_snapshot()
        if hasattr(self, "save_note"):
            self.save_note.config(text="")

    def load_config(self):
        self.jobs = jobs.list_jobs()
        if not self.jobs:
            self.jobs = [jobs.create("Kênh 1")]
        cur = get_setting("current_job")
        job = next((j for j in self.jobs if os.path.basename(j["_path"]) == cur), self.jobs[0])
        self._load_job(job)

    def _fill_form(self):
        c, s, w = self.cfg, self.cfg["strong_channel"], self.cfg["weak_channel"]
        sample = lambda x: "" if any(t in str(x) for t in ("xxxx", "yyyy", "VIDEO_", "tenkenhyeu",
                                                            "Tên kênh yếu", "Kênh mạnh của tôi")) else x
        self.v["s_name"].set(sample(s.get("name", "")))
        self.v["s_id"].set(sample(s.get("channel_id", "")))
        self.v["w_url"].set(sample(w.get("url", "")))
        self.v["w_name"].set(sample(w.get("name", "")))
        self.v["w_id"].set(sample(w.get("channel_id", "")))
        self._gpm_fill()
        self.wvideos.delete("1.0", "end")
        self.wvideos.insert("1.0", "\n".join(sample(str(v)) for v in (w.get("videos") or []) if v and sample(str(v))))
        self._count_wvideos()
        self.v["w_pl"].set(sample(w.get("playlist", "")))
        import selfmode as _sm
        self.v["mode"].set("self" if c.get("mode") == "self" else "pair")
        self.v["self_target"].set(_sm.TARGET_LABELS.get(c.get("self_target") or _sm.TARGET_LINKS,
                                                         _sm.TARGET_LABELS[_sm.TARGET_LINKS]))
        self._render_mode_seg()
        self.comment.delete("1.0", "end")
        self.comment.insert("1.0", sample((w.get("pin_comment") or "").strip()))
        self.v["lang"].set(c.get("ui_language", "vi"))
        self.v["browser"].set("Chrome" if c.get("browser") == "chrome" else "Cốc Cốc")
        self.v["source"].set("Video mới nhất của kênh mạnh" if c.get("video_source") == "own_newest"
                             else "Video của kênh cần kéo")
        self.v["browser_path"].set(c.get("browser_path", "") or "")
        self.v["min_views"].set(str(c.get("scan", {}).get("min_views_per_hour", 20)))
        self.v["interval"].set(str(c.get("cards", {}).get("interval_minutes", 5)))
        self.v["es_count"].set(str(c.get("end_screen", {}).get("count", 2)))
        self.v["card_count"].set(str(c.get("cards", {}).get("count", 3)))
        self.v["start_min"].set(str(c.get("cards", {}).get("start_minute", 0)))
        dl = c.get("delay_range_sec", [2, 5]) or [2, 5]
        self.v["delay_lo"].set(str(dl[0]))
        self.v["delay_hi"].set(str(dl[1] if len(dl) > 1 else dl[0]))
        self.v["speed"].set({"fast": "Nhanh", "slow": "Chậm"}.get(c.get("mouse_speed"), "Vừa"))
        self.v["max_videos"].set(str(c.get("max_videos_per_run", 0) or 0))
        self.b_clear.set(c.get("end_screen", {}).get("replace_existing", False))
        self.b_collab.set(c.get("collab", {}).get("enabled", True))
        self.v["es_pl"].set("1" if c.get("end_screen", {}).get("playlist") else "0")
        self.v["cd_pl"].set("1" if c.get("cards", {}).get("playlist") else "0")
        o = c.get("strong_setup") or {}
        self.v["sp_link_title"].set(o.get("profile_link_title", "") or "")
        self.v["sp_link_url"].set(o.get("profile_link_url", "") or "")
        self.v["sp_trailer"].set(o.get("trailer_video", "") or "")
        self.v["sp_featured"].set(o.get("featured_video", "") or "")
        self.v["post_source"].set("Theo các link bên dưới" if o.get("post_source") == "links"
                                  else "Video mới nhất của kênh mạnh")
        self.post_videos.delete("1.0", "end")
        self.post_videos.insert("1.0", "\n".join(str(x) for x in (o.get("post_videos") or []) if str(x).strip()))
        self.post_text.delete("1.0", "end")
        self.post_text.insert("1.0", (o.get("post_text") or "").strip())
        for k, var in self.sp.items():
            var.set(bool(o.get(k, True)))
        self._apply_mode_ui()

    def _validate(self):
        import selfmode as _sm
        g = lambda k: self.v[k].get().strip()
        errs = []
        one = self.v["mode"].get() == "self"
        if not g("s_id").startswith("UC"):
            errs.append(("ID kênh" if one else "ID kênh mạnh") + " phải bắt đầu bằng UC")
        if not one:
            if not g("w_id").startswith("UC"):
                errs.append("ID kênh cần kéo phải bắt đầu bằng UC")
            elif g("w_id") == g("s_id"):
                errs.append("Kênh cần kéo đang trùng kênh mạnh – muốn kéo cho chính kênh thì chọn "
                            "\"Kéo cho chính kênh\" ở mục CÁCH KÉO")
            if not g("w_url").startswith("http"):
                errs.append("Link kênh cần kéo chưa đúng")
            if not g("w_name"):
                errs.append("Chưa có tên kênh cần kéo")
        vids = self._wvideo_lines()
        for i, link in enumerate(vids, 1):
            if not any(t in link for t in ("watch?v=", "youtu.be/", "/shorts/")):
                errs.append(f"Dòng video {i} không phải link video: {link[:50]}")
        if one:
            if not vids and self._self_target() == _sm.TARGET_LINKS:
                errs.append("Chưa có link video cần đẩy view – dán ít nhất 1 link, hoặc chọn "
                            "\"Video mới nhất của kênh\" / \"Tự chọn video ít view nhất\"")
        elif not vids and g("source") != "Video mới nhất của kênh mạnh":
            errs.append("Chưa có video nào của kênh cần kéo (cần ít nhất 1 link), "
                        "hoặc chọn \"Video mới nhất của kênh mạnh\" ở Tùy chọn")
        import re as _re
        m = _re.search(r"[?&]list=([\w-]+)", g("w_pl"))
        if one and not g("w_pl"):
            pass   # 1 kênh: danh sách phát không bắt buộc
        elif not m:
            errs.append("Link danh sách phát chưa đúng (phải có 'list=')")
        elif len(m.group(1)) < 10:
            errs.append(f"Mã danh sách phát '{m.group(1)}' quá ngắn – có thể link bị cắt khi copy")
        if not one and not self.comment.get("1.0", "end").strip():
            errs.append("Chưa có nội dung bình luận ghim")
        is_vid = lambda x: bool(_re.search(r"(?:v=|youtu\.be/|/shorts/|/live/)[\w-]{11}", x))
        for key, name in (("sp_trailer", "Video giới thiệu kênh cho người chưa đăng ký"),
                          ("sp_featured", "Video nổi bật dành cho người đăng ký cũ")):
            if g(key) and not is_vid(g(key)):
                errs.append(f"Ô '{name}' phải là link video (watch?v=… hoặc youtu.be/…)")
        if g("sp_link_url") and not g("sp_link_url").startswith("http"):
            errs.append("URL đường liên kết Hồ sơ phải bắt đầu bằng http")
        for i, l in enumerate(self.post_videos.get("1.0", "end").splitlines(), 1):
            if l.strip() and not is_vid(l.strip()):
                errs.append(f"Bài đăng – dòng {i} không phải link video: {l.strip()[:50]}")
        nums = ("min_views", "interval", "es_count", "card_count", "start_min", "delay_lo", "delay_hi", "max_videos")
        if not all(g(k).isdigit() for k in nums):
            errs.append("Các ô số trong Tùy chọn phải là số nguyên (không để trống)")
        else:
            if int(g("delay_lo")) > int(g("delay_hi")):
                errs.append("Thời gian nghỉ: số đầu phải nhỏ hơn hoặc bằng số sau")
            if not 1 <= int(g("es_count")) <= 2:
                errs.append("Số video ở màn hình kết thúc chỉ được 1 hoặc 2")
            if not 1 <= int(g("card_count")) <= 5:
                errs.append("Số thẻ video từ 1 đến 5 (YouTube cho tối đa 5 thẻ)")
        return errs

    def _wvideo_lines(self):
        return [l.split("#")[0].strip() for l in self.wvideos.get("1.0", "end").splitlines() if l.split("#")[0].strip()]

    def _count_wvideos(self):
        n = len(self._wvideo_lines())
        self.wvid_count.config(text=f"{n} video" if n else "chưa có video")

    @staticmethod
    def _playlist_url(url):
        import re as _re
        m = _re.search(r"[?&]list=([\w-]+)", url)
        return f"https://www.youtube.com/playlist?list={m.group(1)}" if m else url

    def save_config(self, quiet=False):
        errs = self._validate()
        if errs:
            messagebox.showwarning("Thông tin chưa đủ", "Cần sửa:\n\n• " + "\n• ".join(errs))
            return False
        g = lambda k: self.v[k].get().strip()
        c = self.cfg
        c["ui_language"] = g("lang")
        c["browser"] = "chrome" if g("browser") == "Chrome" else "coccoc"
        c["video_source"] = "own_newest" if g("source") == "Video mới nhất của kênh mạnh" else "weak"
        c["browser_path"] = g("browser_path").strip('"')
        one = self.v["mode"].get() == "self"
        c["mode"] = "self" if one else "pair"
        c["job_name"] = g("job_name") or (g("s_name") if one else g("w_name")) or "Kênh"
        c["strong_channel"].update(name=g("s_name") or ("Kênh của tôi" if one else "Kênh mạnh"), channel_id=g("s_id"))
        for key_, ck_ in (("s_gpm", "strong_channel"), ("w_gpm", "weak_channel")):
            gid_, gname_ = (getattr(self, "_gpm_sel", {}) or {}).get(key_, ("", ""))
            if one and key_ == "w_gpm":
                gid_, gname_ = "", ""
            c[ck_]["gpm_profile_id"], c[ck_]["gpm_profile_name"] = gid_, gname_
        if one:   # 1 kênh: "kênh cần kéo" chính là kênh này
            c["self_target"] = self._self_target()
            c["video_source"] = "own_newest" if c["self_target"] == "newest" else "weak"
            c.setdefault("collab", {})["enabled"] = False
            c["weak_channel"].update(url=f"https://www.youtube.com/channel/{g('s_id')}", name=g("s_name"),
                                     channel_id=g("s_id"), videos=self._wvideo_lines(),
                                     playlist=self._playlist_url(g("w_pl")) if g("w_pl") else "",
                                     pin_comment=(self.comment.get("1.0", "end").strip() + "\n")
                                     if self.comment.get("1.0", "end").strip() else "")
        else:
            c["weak_channel"].update(url=g("w_url"), name=g("w_name"), channel_id=g("w_id"),
                                     videos=self._wvideo_lines(), playlist=self._playlist_url(g("w_pl")),
                                     pin_comment=self.comment.get("1.0", "end").strip() + "\n")
        c.setdefault("scan", {})["min_views_per_hour"] = int(g("min_views"))
        c.setdefault("cards", {})["interval_minutes"] = int(g("interval"))
        c["cards"]["count"] = int(g("card_count"))
        c["cards"]["start_minute"] = int(g("start_min"))
        c["delay_range_sec"] = [int(g("delay_lo")), int(g("delay_hi"))]
        c["mouse_speed"] = {"Nhanh": "fast", "Chậm": "slow"}.get(g("speed"), "normal")
        c["max_videos_per_run"] = int(g("max_videos"))
        c.setdefault("end_screen", {})["count"] = int(g("es_count"))
        # thay thế chỉ bật theo ô "Thay thế cái cũ" ở trang Chạy tool (không lưu cố định trong file kênh)
        c["cards"]["replace_existing"] = False
        c.setdefault("end_screen", {})["replace_existing"] = False
        c["cards"].pop("clear_existing", None)
        c["end_screen"].pop("clear_existing", None)
        c.setdefault("collab", {})["enabled"] = False if one else self.b_collab.get()
        c.setdefault("end_screen", {})["playlist"] = self.v["es_pl"].get() == "1"
        c.setdefault("cards", {})["playlist"] = self.v["cd_pl"].get() == "1"
        c["strong_setup"] = dict(
            profile_link_title=g("sp_link_title"), profile_link_url=g("sp_link_url"),
            trailer_video=g("sp_trailer"), featured_video=g("sp_featured"),
            post_videos=[l.strip() for l in self.post_videos.get("1.0", "end").splitlines() if l.strip()],
            post_text=self.post_text.get("1.0", "end").strip(),
            post_source="links" if g("post_source") == "Theo các link bên dưới" else "newest",
            **{k: v.get() for k, v in self.sp.items()})
        # hồ sơ đăng nhập theo TÀI KHOẢN: đổi ID kênh -> hồ sơ khác; trùng kênh với kênh khác -> dùng chung
        old = jobs.load(self.cfg_path) if os.path.exists(self.cfg_path) else {}
        all_jobs = jobs.list_jobs()
        for who, key, new_id in (("strong", "strong_channel", g("s_id")), ("weak", "weak_channel", g("w_id"))):
            ch = c[key]
            if one and who == "weak":
                ch["profile_dir"] = c["strong_channel"]["profile_dir"]   # 1 kênh = 1 trình duyệt
                continue
            if not ch.get("profile_dir") or old.get(key, {}).get("channel_id") != new_id:
                ch["profile_dir"] = jobs.profile_dir_for(new_id, who, all_jobs, self.cfg_path)
        c["pull_videos"] = [l for l in self.videos.get("1.0", "end").splitlines() if l.strip()]
        jobs.save(self.cfg_path, c)
        try:
            jobs.fix_profiles()   # giữ nguyên tắc: mỗi kênh 1 trình duyệt riêng
        except Exception:
            pass
        self.cfg = jobs.load(self.cfg_path)
        self._saved_snap = self._form_snapshot()
        self._apply_mode_run()
        self._refresh_job_bar()
        self.save_note.config(text=f"✓ Đã lưu kênh '{c['job_name']}'")
        if not quiet:
            self.after(1500, lambda: self.show("run"))
        return True

    # -------------------------------------------------------------- trang chạy
    def _step(self, parent, num, title, hint, cmd, last=False, icon=None, color=None, badge=None):
        color = color or BLUE
        row = tk.Frame(parent, bg=CARD)
        row.pack(fill="x", pady=(0, 0 if last else 14))
        icon_label(row, icon, 40, color, CARD).pack(side="left", anchor="n")
        b = Btn(row, "Chạy", cmd, kind="soft", color=color, icon="play", icon_size=12, padx=12, pady=5, font=F_SB)
        b.pack(side="right", anchor="n")   # đặt nút trước: luôn đủ chỗ, không bị chữ che
        self.step_buttons.append(b)
        txt = tk.Frame(row, bg=CARD)
        txt.pack(side="left", fill="x", expand=True, padx=12)
        tl = tk.Label(txt, text=f"{num}. {title}", font=F_B, bg=CARD, fg=INK, anchor="w")
        tl.pack(anchor="w")
        if not hasattr(self, "step_rows"):
            self.step_rows, self.step_title = {}, {}
        self.step_rows[num], self.step_title[num] = row, tl
        tk.Label(txt, text=hint, font=F_S, bg=CARD, fg=MUTED, anchor="w", justify="left",
                 wraplength=300).pack(anchor="w")
        if badge:   # trạng thái đăng nhập đã lưu của kênh – dòng riêng, không chiếm chỗ nút Chạy
            lb = tk.Label(txt, text="", font=F_CAP, padx=8, pady=2)
            lb.pack(anchor="w", pady=(5, 0))
            self.login_badge[badge] = lb

    def _build_run_page(self):
        page = tk.Frame(self.container, bg=BG)
        h = self._header(page, "Chạy tool",
                         "Làm lần lượt các bước bên trái. Khi tool đang thao tác, đừng bấm vào cửa sổ trình duyệt.",
                         icon="rocket", color=GREEN)
        self.run_job_label = tk.Label(h, text="", font=F_B, bg=tint(CYAN, 0.8), fg=on_tint(CYAN), padx=14, pady=8,
                                      cursor="hand2", image=art.icon("layers", 16, on_tint(CYAN)) or "",
                                      compound="left", highlightthickness=1, highlightbackground=tint(CYAN, 0.55))
        self.run_job_label.pack(side="right")
        self.run_job_label.bind("<Button-1>", lambda e: self.show("cfg"))

        body = tk.Frame(page, bg=BG)
        body.pack(fill="both", expand=True, padx=28, pady=(0, 24))
        body.grid_columnconfigure(0, minsize=420)
        body.grid_columnconfigure(1, weight=1)
        body.grid_rowconfigure(1, weight=1)
        self.step_buttons = []

        # cột trái cuộn được: màn hình thấp vẫn thấy đủ mọi nút (lăn chuột để xem phần dưới)
        self.run_left = ScrollPage(body)
        self.run_left.canvas.configure(width=520)
        self.run_left.grid(row=0, column=0, rowspan=2, sticky="nsew", padx=(0, 20))
        left = self.run_left.inner

        # cột trái: chuẩn bị
        self.login_badge = {}
        o, b = card(left, "Chuẩn bị", "Đăng nhập 1 lần – tool nhớ mãi.", icon="checklist", color=BLUE)
        o.pack(fill="x", pady=(0, 16), padx=(0, 6))
        self._step(b, 1, "Đăng nhập kênh mạnh", "Đăng nhập xong thì đóng trình duyệt, rồi bấm Tiếp tục.", lambda: self.login("strong"),
                   icon="key", color=AMBER, badge="strong")
        self._step(b, 2, "Đăng nhập kênh cần kéo", "Làm giống bước 1, cho kênh cần kéo.", lambda: self.login("weak"),
                   icon="user_plus", color=PINK, badge="weak")
        self._step(b, 3, "Tùy chỉnh kênh mạnh", "Hồ sơ, Thẻ Trang chủ và Bài đăng video.",
                   lambda: self.run(["setup-channel"] + (["--renew-setup"] if getattr(self, "renew_setup", None) is not None
                                                          and self.renew_setup.get() else [])),
                   icon="wand", color=VIOLET)
        self._step(b, 4, "Tìm video đang có view", "Tự điền danh sách video bên phải.", self.run_scan, last=True,
                   icon="search_trend", color=CYAN)

        # cột trái: kéo – 3 nhóm ngắn gọn, mỗi nhóm 2 cột
        o, b = card(left, "Kéo kênh", "Tích việc cần làm rồi bấm chạy.", icon="magnet", color=RED)
        o.pack(fill="x", padx=(0, 6), pady=(0, 4))

        def group(title, first=False):
            tk.Label(b, text=title.upper(), font=F_CAP, bg=CARD, fg=GOLD if not LIGHT else MUTED).pack(
                anchor="w", pady=((0 if first else 12), 4))
            g = tk.Frame(b, bg=CARD)
            g.pack(fill="x")
            g.grid_columnconfigure(0, weight=1, uniform="k")
            g.grid_columnconfigure(1, weight=1, uniform="k")
            return g

        def check(g, i, text, var, ic, col, cmd=None, span=1):
            cw = ttk.Checkbutton(g, text="  " + text, variable=var, style="Card.TCheckbutton", command=cmd,
                                 image=art.icon(ic, 18, col) or "", compound="left")
            cw.grid(row=i // 2, column=i % 2, columnspan=span, sticky="w", pady=3, padx=(0, 10))
            return cw

        grid = group("Trên từng video", first=True)
        self.chk = {}
        save_steps = lambda: set_setting("steps", {k: v.get() for k, v in self.chk.items()})
        for i, (key, label, ic, col) in enumerate([("comment", "Ghim bình luận", "comment_pin", TEAL),
                                                   ("endscreen", "Màn hình kết thúc", "endscreen", BLUE),
                                                   ("cards", "Thẻ", "info_card", VIOLET),
                                                   ("collab", "Cộng tác", "collab", PINK)]):
            self.chk[key] = tk.BooleanVar(value=bool((get_setting("steps", {}) or {}).get(key, True)))
            cw = check(grid, i, label, self.chk[key], ic, col, save_steps)
            if key == "collab":
                self.collab_check = cw

        g2 = group("Trên kênh")
        self.with_setup = tk.BooleanVar(value=bool(get_setting("with_setup", True)))
        check(g2, 0, "Hồ sơ · Trang chủ · Bài đăng", self.with_setup, "wand", VIOLET,
              lambda: set_setting("with_setup", self.with_setup.get()), span=2)   # 1 dòng riêng: đủ chữ
        self.with_reply = tk.BooleanVar(value=bool(get_setting("with_reply", False)))
        check(g2, 2, "Trả lời bình luận", self.with_reply, "reply", TEAL,
              lambda: set_setting("with_reply", self.with_reply.get()))
        self.with_community = tk.BooleanVar(value=bool(get_setting("with_community", False)))
        check(g2, 3, "Cộng đồng (Studio)", self.with_community, "collab", ORANGE,
              lambda: set_setting("with_community", self.with_community.get()))
        self.with_pt = tk.BooleanVar(value=bool(get_setting("with_pt", False)) and pt_enabled())
        if pt_enabled():
            check(g2, 4, "Phân tích video (AI)", self.with_pt, "search_trend", VIOLET,
                  lambda: set_setting("with_pt", self.with_pt.get()))

        g3 = group("Tùy chọn")
        self.replace = tk.BooleanVar(value=bool(get_setting("replace", False)))   # nhớ lựa chọn của bạn
        # MỘT ô thay thế cho tất cả: tích = xóa cái cũ, gắn cái mới, làm lại cả video đã làm
        check(g3, 0, "Thay thế cái cũ", self.replace, "swap", ORANGE,
              lambda: set_setting("replace", self.replace.get()))
        self.force = self.replace          # thay thế = làm lại cả những video đã làm
        self.renew_setup = self.replace    # thay thế = làm mới Hồ sơ, Trang chủ, Bài đăng
        self.hidden_var = tk.BooleanVar(value=bool(get_setting("hidden", False)))
        check(g3, 1, "Ẩn trình duyệt", self.hidden_var, "eye_off", SOFT if not LIGHT else MUTED,
              lambda: set_setting("hidden", self.hidden_var.get()))
        row = tk.Frame(b, bg=CARD)
        row.pack(fill="x", pady=(14, 0))
        pull = Btn(row, "Kéo kênh đang chọn", self.run_pull, icon="play", pady=11)
        pull.pack(side="left", fill="x", expand=True, padx=(0, 8))
        allb = Btn(row, "Chạy tất cả kênh", self.run_all, kind="solid", color=VIOLET, icon="play_all", pady=11)
        allb.pack(side="left", fill="x", expand=True)
        self.step_buttons += [pull, allb]


        # cột phải: danh sách video
        o, b = card(body, "Danh sách video", "Video của kênh mạnh dùng để kéo – mỗi dòng 1 link.", pad=18,
                    icon="list_video", color=GREEN)
        o.grid(row=0, column=1, sticky="nsew", pady=(0, 20))
        self.videos = textbox(b, 5, mono=True)
        self.videos.pack(fill="x")
        self.videos.bind("<KeyRelease>", lambda e: self._count_videos())
        vb = tk.Frame(b, bg=CARD)
        vb.pack(fill="x", pady=(10, 0))
        self.video_count = tk.Label(vb, text="", font=F_S, bg=CARD, fg=MUTED)
        self.video_count.pack(side="left")
        Btn(vb, "Lưu danh sách", self.save_videos, kind="soft", color=GREEN, icon="save", padx=12, pady=5,
            font=F_SB).pack(side="right")

        # cột phải: tiến trình
        o = tk.Frame(body, bg=CONSOLE, highlightthickness=1, highlightbackground=BORDER)
        o.grid(row=1, column=1, sticky="nsew")
        top = tk.Frame(o, bg=CONSOLE_BAR)     # đầu panel: chấm màu có quầng + tiêu đề CHỮ HOA
        top.pack(fill="x")
        dot = tk.Canvas(top, width=14, height=14, bg=CONSOLE_BAR, highlightthickness=0, bd=0)
        dot.create_oval(1, 1, 13, 13, fill=_mix("#21C7C7", CONSOLE_BAR, 0.22), outline="")
        dot.create_oval(4, 4, 10, 10, fill="#21C7C7", outline="")
        dot.pack(side="left", padx=(12, 6), pady=9)
        tk.Label(top, text="TIẾN TRÌNH", font=F_PANEL, bg=CONSOLE_BAR, fg="#F2F7FC").pack(side="left")
        tk.Frame(o, bg="#22344A", height=1).pack(fill="x")
        lw = tk.Frame(o, bg=CONSOLE)
        lw.pack(fill="both", expand=True)
        self.log = tk.Text(lw, font=F_MONO, bg=CONSOLE, fg=CONSOLE_TXT, insertbackground="white", relief="flat",
                           bd=0, highlightthickness=0, wrap="word", state="disabled", padx=14, pady=10, height=8)
        ls = ttk.Scrollbar(lw, command=self.log.yview)
        self.log.configure(yscrollcommand=ls.set)
        self.log.pack(side="left", fill="both", expand=True)
        ls.pack(side="right", fill="y")
        # nhật ký nền tối: chữ màu "-soft" của nền tối (đọc rõ trên nền --bg-inset)
        for tag, color in (("ok", "#6FE08A"), ("err", "#FF8A8C"), ("warn", "#FFD166"), ("ask", "#7EB1FF"),
                           ("head", "#6D7F92")):
            self.log.tag_configure(tag, foreground=color)

        # thanh dưới: dòng trạng thái riêng 1 hàng, nút bấm 1 hàng (nút đặt trước để không bao giờ bị bóp/che)
        bar = tk.Frame(o, bg=CONSOLE_BAR)
        bar.pack(fill="x", side="bottom", before=lw)      # đóng gói trước khung log -> luôn hiện đủ
        sbar = tk.Frame(o, bg=CONSOLE_BAR)
        sbar.pack(fill="x", side="bottom", before=lw)
        self.status = tk.Label(sbar, text="Sẵn sàng.", font=F_S, bg=CONSOLE_BAR, fg=CONSOLE_TXT, anchor="w",
                               justify="left")
        self.status.pack(side="left", fill="x", expand=True, padx=14, pady=(8, 0))
        sbar.bind("<Configure>", lambda e: self.status.configure(wraplength=max(200, e.width - 30)))
        self.btn_stop = Btn(bar, "Dừng", self.stop, kind="solid", color=RED, icon="stop", icon_size=13, padx=12,
                            pady=5, font=F_SB)
        self.btn_stop.pack(side="right", padx=(6, 12), pady=8)
        self.btn_continue = Btn(bar, "Tiếp tục", self.send_enter, kind="solid", color=GREEN, icon="play",
                                icon_size=13, padx=14, pady=5, font=F_SB)
        self.btn_continue.pack(side="right", pady=8)
        Btn(bar, "Xóa log", self._clear_log, kind="soft", color=AMBER, icon="eraser", icon_size=14, padx=12,
            pady=5, font=F_SB).pack(side="right", padx=(0, 8), pady=8)
        self.auto_clear = tk.BooleanVar(value=False)
        tk.Checkbutton(bar, text="Tự xóa log", variable=self.auto_clear, font=F_S,
                       bg=CONSOLE_BAR, fg=CONSOLE_TXT, selectcolor=CONSOLE, activebackground=CONSOLE_BAR,
                       activeforeground="white", bd=0, highlightthickness=0, cursor="hand2").pack(
            side="left", padx=(12, 0))
        self.btn_stop.set_enabled(False)
        self.btn_continue.set_enabled(False)
        return page

    def load_videos(self):
        self.videos.delete("1.0", "end")
        self.videos.insert("1.0", "\n".join(str(x) for x in (self.cfg.get("pull_videos") or [])))
        self._count_videos()

    def _reload_videos_from_file(self):
        """Sau khi tool tự tìm video: đọc lại danh sách đã ghi vào file kênh."""
        try:
            self.cfg["pull_videos"] = jobs.load(self.cfg_path).get("pull_videos", [])
        except Exception:
            pass
        self.load_videos()

    def _video_lines(self):
        return [l.split("#")[0].strip() for l in self.videos.get("1.0", "end").splitlines()
                if l.split("#")[0].strip().startswith("http")]

    def _count_videos(self):
        self.video_count.config(text=f"{len(self._video_lines())} video trong danh sách")

    def save_videos(self, quiet=False):
        lines = [l for l in self.videos.get("1.0", "end").splitlines() if l.strip()]
        try:
            data = jobs.load(self.cfg_path)
            data["pull_videos"] = lines
            jobs.save(self.cfg_path, data)
            self.cfg["pull_videos"] = lines
        except Exception as e:
            self.status.config(text=f"Không lưu được danh sách video: {e}")
            return
        self._count_videos()
        if not quiet:
            self.status.config(text="Đã lưu danh sách video.")

    # ------------------------------------------------------------- tiến trình
    def write(self, text, tag=None):
        try:   # nhật ký lần chạy -> logs/nhat_ky_chay.txt (đi kèm gói chẩn đoán để dò lỗi đúng chỗ)
            lp = os.path.join(DATA, "logs", "nhat_ky_chay.txt")
            os.makedirs(os.path.dirname(lp), exist_ok=True)
            if os.path.exists(lp) and os.path.getsize(lp) > 3_000_000:
                os.replace(lp, lp + ".cu")
            with open(lp, "a", encoding="utf-8") as f:
                f.write(text + "\n")
        except Exception:
            pass
        self.log_history.append((text, tag))
        if len(self.log_history) > 3000:
            self.log_history = self.log_history[-2000:]
        self.log.configure(state="normal")
        self.log.insert("end", text + "\n", tag)
        self.log.see("end")
        self.log.configure(state="disabled")

    def _clear_log(self):
        self.log.configure(state="normal")
        self.log.delete("1.0", "end")
        self.log.configure(state="disabled")
        self.log_history = []

    @staticmethod
    def _tag_for(line):
        if "✅" in line:
            return "ok"
        st = line.lstrip()
        if st.startswith(("…", "·")):   # tool đang tự kiểm tra lại / bước phụ -> không tô đỏ
            return None
        if "❌" in line or st.startswith("Traceback") or (st.split(":")[0].endswith("Error") and " " not in st.split(":")[0]):
            return "err"
        if "⚠" in line:
            return "warn"
        if "👉" in line:
            return "ask"
        return None

    def _set_side(self, text, color):
        if text == "Sẵn sàng":
            text = "Hoạt động tốt"
        self._side_state = (text, color)
        try:
            if getattr(self, "_sdot", None) is not None and self._sdot.winfo_exists():
                self._sdot.itemconfig(self._sdot_id, fill=color)
                self._stext.config(text=text)
        except tk.TclError:
            pass

    def run(self, args, need_config=True, on_done=None, stdin_text=None, save_list=True):
        if self.proc and self.proc.poll() is None:
            messagebox.showinfo("Đang chạy", "Tool đang chạy một việc khác, chờ xong hoặc bấm Dừng.")
            return
        if "--config" not in args:
            if need_config and not str(jobs.load(self.cfg_path).get("strong_channel", {})
                                       .get("channel_id", "")).startswith("UC"):
                messagebox.showwarning("Chưa có thông tin", "Kênh này chưa lưu đủ thông tin. "
                                                            "Hãy điền và bấm Lưu ở trang Thông tin kênh.")
                self.show("cfg")
                return
            if save_list:
                self.save_videos(quiet=True)
            args = list(args) + ["--config", self.cfg_path]
        if args and args[0] in ("pull", "revert", "setup-channel") and not self._excel_free():
            return
        if args and args[0] in ("pull", "scan", "setup-channel", "reply") and self.hidden_var.get() \
                and "--hidden" not in args:
            args = list(args) + ["--hidden"]
        if getattr(self, "auto_clear", None) is not None and self.auto_clear.get():
            self._clear_log()
        env = dict(os.environ, PYTHONIOENCODING="utf-8", PYTHONUTF8="1")
        flags = subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0
        exe = sys.executable.replace("pythonw.exe", "python.exe")
        shown = [a for a in args if a != "--config" and not a.endswith(".yaml")]
        self.write(f"\n── {' '.join(shown)} " + "─" * 30, "head")
        try:
            self.proc = subprocess.Popen([exe, "-u", os.path.join(BASE, "main.py")] + args, cwd=DATA,
                                         stdin=subprocess.PIPE, stdout=subprocess.PIPE,
                                         stderr=subprocess.STDOUT, text=True, encoding="utf-8",
                                         errors="replace", env=env, creationflags=flags)
        except Exception as e:
            self.write(f"❌ Không chạy được tool: {e}", "err")
            return
        if stdin_text:
            self.proc.stdin.write(stdin_text)
            self.proc.stdin.flush()
        self._on_done = on_done
        self._busy(True)
        threading.Thread(target=self._reader, args=(self.proc,), daemon=True).start()

    def _excel_free(self):
        """Trước khi chạy việc có ghi nhật ký: file Excel kết quả đang mở trong Excel / WPS -> nhắc đóng."""
        import excel_view
        path = self._excel_path()
        while excel_view.is_locked(path):
            ans = messagebox.askyesnocancel(
                "Đóng file Excel kết quả",
                "File Excel kết quả đang MỞ trong Excel / WPS – tool không ghi đè được.\n\n"
                "• Bấm CÓ sau khi đã đóng file (khuyên dùng).\n"
                "• Bấm KHÔNG để vẫn chạy: kết quả được lưu tạm sang file phụ, đóng WPS là tool tự gộp lại.\n"
                "• Bấm HỦY để không chạy.")
            if ans is None:
                return False
            if ans is False:
                return True
        return True

    def _reader(self, proc):
        for line in proc.stdout:
            self.q.put(("line", line.rstrip()))
        proc.wait()
        self.q.put(("done", proc.returncode))

    def _poll(self):
        try:
            while True:
                kind, val = self.q.get_nowait()
                if kind == "line":
                    self.write(val, self._tag_for(val))
                    if getattr(self, "_gpm_live", None):
                        self._gpm_on_line(val)
                    if "👉" in val:
                        self.waiting = True
                        self.btn_continue.set_enabled(True)
                        self.status.config(text="Đang chờ bạn: làm theo hướng dẫn rồi bấm Tiếp tục.")
                        self._set_side("Đang chờ bạn", WARN)
                        self.bell()
                else:
                    self.waiting = False
                    self._busy(False)
                    done = val == 0
                    self.status.config(text="Xong." if done else "Đã dừng hoặc có lỗi – xem tiến trình.")
                    self._set_side("Sẵn sàng" if done else "Có lỗi", OK if done else ERR)
                    self.load_results()
                    if self._on_done:
                        self._on_done()
        except queue.Empty:
            pass
        self.after(100, self._poll)

    def _busy(self, busy):
        for b in self.step_buttons:
            b.set_enabled(not busy)
        self.btn_stop.set_enabled(busy)
        self.btn_continue.set_enabled(False)
        if busy:
            self.status.config(text="Đang chạy…")
            self._set_side("Đang chạy", BLUE)
        else:   # xong việc (cả bước Phân tích video chạy trong tool) -> không để kẹt chữ "Đang chạy…"
            self.status.config(text="Xong.")
            self._set_side("Sẵn sàng", OK)

    def send_enter(self):
        if getattr(self, "_pt_chain", None) is not None and self.pt is not None and self.pt.worker:
            self.pt.worker.next()   # bước Phân tích video: sang video sau
            self.btn_continue.set_enabled(False)
            return
        if self.proc and self.proc.poll() is None:
            self.proc.stdin.write("\n")
            self.proc.stdin.flush()
        self.waiting = False
        self.btn_continue.set_enabled(False)
        self.status.config(text="Đang chạy…")
        self._set_side("Đang chạy", BLUE)

    def _reply_on(self):
        return (getattr(self, "with_reply", None) is not None and self.with_reply.get()) or \
            (getattr(self, "with_community", None) is not None and self.with_community.get())

    def _reply_step(self, path, then=None):
        """Bước 'Trả lời bình luận' trong lượt Kéo kênh (kênh `path`), xong thì gọi `then`."""
        then = then or (lambda: None)
        if getattr(self, "_stopped", False):
            return
        if not self._reply_on() or getattr(self, "rp_ui", None) is None:
            return then()
        base = [x for x in self.rp_ui.args(False) if x not in ("--community",)]
        if "--max-comments" in base:
            k = base.index("--max-comments")
            del base[k:k + 2]
        runs = []
        if self.with_reply.get():        # ô "Trả lời bình luận": từng video
            runs.append(base)
        if getattr(self, "with_community", None) is not None and self.with_community.get():   # ô "Cộng đồng"
            runs.append(base + ["--community", "--max-comments",
                                str(max(10, int(self.rp_ui.opts.get("max_comments") or 100)))])
        self.rp_ui.begin()

        def step(i=0):
            if i >= len(runs) or getattr(self, "_stopped", False):
                self.rp_ui.finish()
                return then()
            self.run(runs[i] + ["--config", path], on_done=lambda: step(i + 1), save_list=False)
        step()

    def _steps_selected(self):
        steps = [k for k, v in self.chk.items() if v.get()]
        if not steps and not self.with_setup.get():
            if (self.with_pt.get() and pt_enabled()) or self._reply_on():
                return ["__pt_only__"]
            messagebox.showwarning("Chưa chọn bước", "Hãy tích ít nhất 1 việc cần làm.")
        return steps or (["__setup_only__"] if self.with_setup.get() else [])

    def run_all(self):
        steps = self._steps_selected()
        if not steps:
            return
        if not self._confirm_leave():
            return
        self.save_videos(quiet=True)
        lst = [j for j in jobs.list_jobs() if j.get("enabled", True)]
        bad = [j["job_name"] for j in lst
               if not str(j.get("strong_channel", {}).get("channel_id", "")).startswith("UC")]
        if bad:
            messagebox.showwarning("Kênh chưa đủ thông tin", "Các kênh sau chưa lưu đủ thông tin, hãy điền hoặc tắt:\n\n• "
                                   + "\n• ".join(bad))
            return
        if not lst:
            messagebox.showwarning("Không có kênh", "Chưa có kênh nào được bật.")
            return
        lines = []
        for i, j in enumerate(lst, 1):
            n = len([u for u in j.get("pull_videos", []) if str(u).split("#")[0].strip().startswith("http")])
            lines.append(f"{i}. {j['job_name']} — " + (f"{n} video" if n else "chưa có video → tự tìm video đang có view"))
        names = {"comment": "ghim bình luận", "endscreen": "màn hình kết thúc", "cards": "thẻ", "collab": "cộng tác"}
        msg = ("Tool sẽ chạy LẦN LƯỢT từng kênh theo thứ tự, xong kênh này mới sang kênh sau:\n\n"
               + "\n".join(lines) + "\n\nCác bước: "
               + ", ".join((["tùy chỉnh kênh mạnh (bước 3)"] if self.with_setup.get() else [])
                           + [names[x] for x in steps if x in names]
                           + (["trả lời bình luận khen"] if self._reply_on() else [])
                           + (["phân tích video cùng chủ đề (AI, chờ bạn duyệt)"] if self._pt_on() else [])))
        if self.replace.get():
            msg += ("\n\n⚠ THAY THẾ CÁI CŨ: XÓA màn hình kết thúc, thẻ, bình luận ghim cũ trên mọi video rồi gắn mới; "
                    "làm mới Hồ sơ, Trang chủ, Bài đăng.")
        if self.hidden_var.get():
            msg += "\n\nTrình duyệt sẽ chạy ẩn."
        if not messagebox.askyesno("Chạy tất cả kênh", msg + "\n\nBắt đầu?"):
            return
        self._stopped = False
        self._queue = list(lst)
        self._queue_total = len(lst)
        self._queue_steps = steps
        self._next_job()

    def _next_job(self):
        if not getattr(self, "_queue", None):
            if getattr(self, "_queue_total", 0):
                self.write(f"\n✅ Đã chạy xong {self._queue_total} kênh.", "ok")
                self.status.config(text=f"Đã chạy xong {self._queue_total} kênh.")
                self._queue_total = 0
                self._reload_videos_from_file()
                self.load_results()
            return
        job = self._queue.pop(0)
        n = self._queue_total - len(self._queue)
        path = job["_path"]
        self.write(f"\n▶▶ KÊNH {n}/{self._queue_total}: {job['job_name']}", "ask")
        steps = [x for x in self._queue_steps if x not in ("__setup_only__", "__pt_only__")]
        then = lambda: self._reply_step(path, lambda: self._pt_step(path, self._next_job))
        pull = (["pull", "--only"] + steps + (["--force"] if self.force.get() else [])
                + (["--replace"] if self.replace.get() else []) + ["--close-after", "--config", path])
        has_videos = any(str(u).split("#")[0].strip().startswith("http") for u in job.get("pull_videos", []))

        def do_pull():
            if not getattr(self, "_queue_total", 0):  # đã bấm Dừng
                return
            if not steps:
                return then()
            self.run(pull, on_done=then, save_list=False)

        def do_scan_pull():
            if not getattr(self, "_queue_total", 0):
                return
            if has_videos or not steps:
                do_pull()
            else:
                self.run(["scan", "--config", path], on_done=do_pull, save_list=False)
        if self._queue_steps == ["__pt_only__"]:
            then()
        elif self.with_setup.get():
            self.run(["setup-channel", "--config", path] + (["--renew-setup"] if self.renew_setup.get() else []),
                     on_done=do_scan_pull, save_list=False)
        else:
            do_scan_pull()

    def stop(self):
        self._stopped = True
        self._queue = []
        self._queue_total = 0
        if getattr(self, "_pt_chain", None) is not None and self.pt is not None and self.pt.worker:
            self.pt.worker.stop()
            self._pt_chain = None
            self._busy(False)
            self.write("■ Đã dừng phân tích video.", "warn")
        if self.proc and self.proc.poll() is None:
            self.proc.terminate()
            self.write("■ Đã dừng theo yêu cầu.", "warn")

    def run_scan(self):
        self.run(["scan"], on_done=self._reload_videos_from_file)

    def run_pull(self):
        steps = self._steps_selected()
        if not steps:
            return
        self._stopped = False
        if steps == ["__pt_only__"]:
            return self._reply_step(self.cfg_path, lambda: self._pt_step(self.cfg_path))
        setup = self.with_setup.get()
        steps = [x for x in steps if x not in ("__setup_only__", "__pt_only__")]
        n = len(self._video_lines())   # 0 = danh sách trống: tool tự tìm video đang có view rồi kéo luôn
        names = {"comment": "ghim bình luận", "endscreen": "màn hình kết thúc", "cards": "thẻ", "collab": "cộng tác"}
        msg = f"Kênh: {self.cfg.get('job_name')}\n"
        if setup:
            msg += "1) Tùy chỉnh kênh mạnh (bước 3): Hồ sơ, Thẻ Trang chủ, Bài đăng"
            msg += "\n"
        if steps:
            msg += (f"{'2) ' if setup else ''}Kéo trên "
                    + (f"{n} video" if n else "video đang có view (danh sách trống – tool tự tìm và tự điền)")
                    + " với các bước: "
                    f"{', '.join(names[s] for s in steps)}")
        if self._reply_on():
            msg += ("\nSau đó: trả lời cảm ơn bình luận khen của khán giả" +
                    (" ở trang Cộng đồng (Studio)" if self.with_community.get() else "") +
                    " – tim HOẶC thích tùy nội dung")
        if self._pt_on():
            msg += "\nSau đó: phân tích video cùng chủ đề (AI) – Like/Dislike chỉ làm khi bạn duyệt"
        if self.replace.get():
            msg += (f"\n\n⚠ THAY THẾ CÁI CŨ: trên {n} video, tool XÓA màn hình kết thúc, thẻ và bình luận ghim "
                    f"đang có rồi gắn cái mới; Hồ sơ, Trang chủ, Bài đăng cũng được làm mới.")
        elif set(steps) & {"endscreen", "cards"}:
            msg += ("\n\nLưu ý: video nào ĐÃ CÓ SẴN màn hình kết thúc / thẻ khác sẽ được giữ nguyên (không gắn). "
                    "Muốn thay hết bằng video cần kéo: bấm Không, tích 'Thay thế cái cũ' rồi chạy lại.")
        if not messagebox.askyesno("Bắt đầu kéo", msg + "\n\nTiếp tục?"):
            return
        pull = (["pull", "--only"] + steps + (["--force"] if self.force.get() else [])
                + (["--replace"] if self.replace.get() else []))
        self._stopped = False
        setup_cmd = ["setup-channel"] + (["--renew-setup"] if self.renew_setup.get() else [])
        after = lambda: (self._reload_videos_from_file(),
                         self._reply_step(self.cfg_path, lambda: self._pt_step(self.cfg_path)))
        if setup and steps:
            self.run(setup_cmd, on_done=lambda: (not self._stopped) and self.run(pull, on_done=after))
        elif setup:
            self.run(setup_cmd, on_done=after)
        else:
            self.run(pull, on_done=after)

    def run_test(self):
        urls = self._video_lines()
        if not urls:
            messagebox.showwarning("Chưa có video", "Hãy dán ít nhất 1 link video của kênh mạnh vào Danh sách video.")
            return
        if messagebox.askyesno(
                "Chạy thử: xóa & làm lại",
                f"Tool sẽ chạy trên 1 video:\n{urls[0]}\n\n"
                "1. Màn hình kết thúc: XÓA thành phần cũ → gắn 2 video mới → Lưu\n"
                "2. Thẻ: XÓA thẻ cũ → gắn 3 thẻ video (phút 0, 5, 10) → Lưu\n\n"
                "Bạn hãy xem trên cửa sổ Cốc Cốc để kiểm tra tool làm đúng chưa.\n\nBắt đầu?"):
            self.run(["pull", "--only", "endscreen", "cards", "--replace", "--force", "--first"])

    def run_record(self):
        if messagebox.askyesno(
                "Ghi thao tác mẫu",
                "Tool sẽ tự mở video ĐẦU TIÊN trong Danh sách video và mở sẵn trình chỉnh sửa.\n\n"
                "Chặng 1 – Màn hình kết thúc: bạn tự tay thêm 2 video cụ thể, bấm Lưu,\n"
                "   rồi bấm 'Tiếp tục' trong tool.\n"
                "Chặng 2 – Thẻ: tool mở sẵn trình chỉnh sửa Thẻ, bạn thêm 3 thẻ video\n"
                "   (phút 0, 5, 10), bấm Lưu, rồi bấm 'Tiếp tục'.\n\n"
                "Tool sẽ tạo 1 file chan_doan_....zip để bạn gửi đi.\n\nBắt đầu?"):
            self.run(["record"], on_done=lambda: self._open(DATA))

    # ------------------------------------------------------------ gỡ theo hạng mục / gỡ sạch
    REVERT_TASKS = (("Bình luận ghim", "Bình luận ghim"), ("Màn hình kết thúc", "Màn hình kết thúc"),
                    ("Thẻ (cards)", "Thẻ"), ("Tính năng cộng tác", "Cộng tác"),
                    ("Hồ sơ: đường liên kết", "Hồ sơ – đường liên kết"), ("Thẻ Trang chủ", "Thẻ Trang chủ"),
                    ("Bài đăng video", "Bài đăng video"))

    def _pending(self, strong=None):
        """Các dòng tool đã kéo và CHƯA gỡ (lọc theo kênh mạnh nếu có)."""
        out = []
        for r in getattr(self, "_rows", []):
            if r["tag"] not in ("ok", "check") or r["removal"] not in ("Chưa gỡ", "❌ Lỗi khi gỡ", "⚠️ Gỡ thủ công"):
                continue
            if "đã có sẵn" in str(r["detail"]) or "đã đúng sẵn trên kênh" in str(r["detail"]):
                continue
            if not r["file"] or not r["strong"] or r["strong"] == "(không rõ)":
                continue   # dòng cũ không rõ kênh mạnh -> không gỡ tự động
            if strong and r["strong"] != strong:
                continue
            out.append(r)
        return out

    def _orphans(self):
        """Dòng cũ (bản tool cũ) không ghi kênh mạnh / file kênh, chưa gỡ."""
        return [r for r in getattr(self, "_rows", [])
                if r["tag"] in ("ok", "check") and r["removal"] in ("Chưa gỡ", "❌ Lỗi khi gỡ", "⚠️ Gỡ thủ công")
                and (not r["file"] or not r["strong"] or r["strong"] == "(không rõ)")
                and "đã có sẵn" not in str(r["detail"]) and "đã đúng sẵn trên kênh" not in str(r["detail"])]

    def _mark_rows(self, rows, value, note):
        """Ghi tình trạng gỡ cho các dòng (không thao tác gì trên YouTube)."""
        from openpyxl import load_workbook
        path = self._excel_path()
        try:
            import excel_view as _xv
            wb = load_workbook(_xv.latest(path))
            import excel_view
            ws = excel_view.log_sheet(wb)
            head = [c.value for c in ws[1]]
            ci = head.index("Tình trạng gỡ") + 1
            ce = head.index("Lỗi") + 1
            for r in rows:
                ws.cell(r["row"], ci, value)
                old = ws.cell(r["row"], ce).value or ""
                ws.cell(r["row"], ce, (str(old) + " | " + note).strip(" |"))
            try:
                excel_view.build_view(wb)
            except Exception:
                pass
            wb.save(path)
            _xv.drop_pending(path)
            return True
        except PermissionError:
            messagebox.showwarning("Đang mở Excel", "Hãy đóng file nhật ký Excel rồi thử lại.")
        except Exception as e:
            messagebox.showwarning("Không ghi được", str(e))
        return False

    def revert_by_category(self, all_ticked=False):
        """Hộp 'Gỡ khỏi kênh mạnh': chọn ĐÚNG 1 kênh mạnh (tên + mã kênh + file kênh) rồi chọn hạng mục cần gỡ."""
        if self.proc and self.proc.poll() is None:
            messagebox.showinfo("Đang chạy", "Chờ tool chạy xong rồi hãy gỡ.")
            return
        self.load_results()
        pend = self._pending()
        orph = self._orphans()
        chans, names = {}, {}
        for r in pend:
            # gom theo MÃ kênh + file kênh (kênh đổi tên vẫn là 1 kênh -> không hiện 2 dòng, gỡ 1 lần là sạch cả)
            m = re.search(r"UC[\w-]{22}", str(r["strong"]))
            key = (m.group(0) if m else r["strong"], r["file"])
            chans.setdefault(key, []).append(r)
            names[key] = r["strong"]       # tên mới nhất (nhật ký ghi theo thời gian)
        for key in names:
            j = next((x for x in jobs.list_jobs() if os.path.basename(x["_path"]) == key[1]), None)
            sc = (j or {}).get("strong_channel", {})
            if sc.get("channel_id") == key[0] and sc.get("name"):
                names[key] = f"{sc['name']} ({key[0]})"
        if not chans and not orph:
            messagebox.showinfo("Gỡ khỏi kênh mạnh", "Không còn mục nào tool đã kéo mà chưa gỡ.")
            return
        win = tk.Toplevel(self)
        win.title("Gỡ khỏi kênh mạnh")
        win.configure(bg=CARD)
        win.transient(self)
        win.grab_set()
        body = tk.Frame(win, bg=CARD)
        body.pack(fill="both", expand=True, padx=22, pady=18)
        tk.Label(body, text="1. Chọn kênh mạnh cần gỡ", font=F_H2, bg=CARD, fg=INK).pack(anchor="w")
        tk.Label(body, text="Tool chỉ thao tác trên ĐÚNG kênh này (kiểm tra mã kênh trước khi gỡ, không tự chuyển "
                            "sang kênh khác).", font=F_S, bg=CARD, fg=MUTED).pack(anchor="w", pady=(2, 8))
        keys = sorted(chans, key=lambda k: -len(chans[k]))
        sel = tk.StringVar(value="0" if keys else "")
        for n, key in enumerate(keys):
            strong, fname = names[key], key[1]
            j = next((x for x in jobs.list_jobs() if os.path.basename(x["_path"]) == fname), None)
            jn = f" · kênh trong tool: {j.get('job_name')}" if j else " · ⚠ không còn file kênh này trong tool"
            ttk.Radiobutton(body, text=f"  {strong}  –  {len(chans[key])} mục chưa gỡ{jn}  ({fname})",
                            variable=sel, value=str(n), style="Card.TCheckbutton",
                            command=lambda: counts()).pack(anchor="w", pady=1)
        if not keys:
            tk.Label(body, text="(không có kênh mạnh nào còn mục cần gỡ)", font=F_S, bg=CARD, fg=SOFT).pack(anchor="w")
        tk.Frame(body, bg=BORDER, height=1).pack(fill="x", pady=12)
        tk.Label(body, text="2. Chọn hạng mục", font=F_H2, bg=CARD, fg=INK).pack(anchor="w", pady=(0, 6))
        box = tk.Frame(body, bg=CARD)
        box.pack(fill="x")
        vars_, labels = {}, {}
        for task, name in self.REVERT_TASKS:
            vars_[task] = tk.BooleanVar(value=all_ticked)
            labels[task] = ttk.Checkbutton(box, text=name, variable=vars_[task], style="Card.TCheckbutton")
            labels[task].pack(anchor="w", pady=1)

        def cur_rows():
            if not keys or not sel.get():
                return []
            return chans[keys[int(sel.get())]]

        def counts(*_):
            rs = cur_rows()
            for task, name in self.REVERT_TASKS:
                n = len({(r["target"] if task not in ("Hồ sơ: đường liên kết", "Thẻ Trang chủ", "Bài đăng video")
                          else r["row"]) for r in rs if r["task"] == task})
                labels[task].configure(text=f"  {name}  ({n})", state="normal" if n else "disabled")
                if not n:
                    vars_[task].set(False)
                elif all_ticked:
                    vars_[task].set(True)
        counts()
        row = tk.Frame(body, bg=CARD)
        row.pack(fill="x", pady=(14, 0))

        def go(clean_all=False):
            rs = cur_rows()
            if not rs:
                return
            tasks = {t for t, _n in self.REVERT_TASKS} if clean_all else {t for t, v in vars_.items() if v.get()}
            todo = [r for r in rs if r["task"] in tasks]
            if not todo:
                messagebox.showinfo("Gỡ khỏi kênh mạnh", "Hãy tích ít nhất 1 hạng mục.", parent=win)
                return
            strong = names[keys[int(sel.get())]]
            if clean_all:
                from tkinter import simpledialog
                ans = simpledialog.askstring("GỠ SẠCH", f"GỠ SẠCH mọi thứ tool đã kéo trên kênh mạnh:\n{strong}\n"
                                             f"({len(todo)} mục)\n\nGõ chữ XOA (viết hoa) để xác nhận:", parent=win)
                if (ans or "").strip() != "XOA":
                    return
            win.destroy()
            self._revert_rows(todo, f"Gỡ khỏi kênh mạnh {strong}", confirm=not clean_all)
        Btn(row, "Gỡ hạng mục đã tích", lambda: go(False), kind="solid", color=ORANGE, icon="undo", padx=14,
            pady=6, font=F_SB).pack(side="left")
        Btn(row, "GỠ SẠCH kênh này", lambda: go(True), kind="solid", color=RED, icon="trash", padx=14, pady=6,
            font=F_SB).pack(side="left", padx=(8, 0))
        if orph:
            tk.Frame(body, bg=BORDER, height=1).pack(fill="x", pady=12)
            tk.Label(body, text=f"Dòng cũ không rõ kênh mạnh: {len(orph)} dòng (từ bản tool cũ, không ghi kênh mạnh / "
                                f"file kênh)", font=F_SB, bg=CARD, fg=WARN).pack(anchor="w")
            tk.Label(body, text="Tool KHÔNG tự gỡ các dòng này (không biết chắc kênh nào). Bấm nút dưới để bỏ chúng "
                                "khỏi danh sách cần gỡ.", font=F_S, bg=CARD, fg=MUTED).pack(anchor="w", pady=(2, 6))

            def drop():
                if self._mark_rows(orph, "⏭ Bỏ qua – không thuộc kênh mạnh",
                                   "Dòng cũ không rõ kênh mạnh – bỏ khỏi danh sách gỡ"):
                    win.destroy()
                    self.load_results()
                    messagebox.showinfo("Đã bỏ", f"Đã bỏ {len(orph)} dòng cũ khỏi danh sách cần gỡ.")
            Btn(body, f"Bỏ {len(orph)} dòng cũ khỏi danh sách gỡ", drop, kind="secondary", icon="list_x", padx=12,
                pady=6, font=F_SB).pack(anchor="w")
        win.update_idletasks()   # đặt hộp giữa cửa sổ tool
        x = self.winfo_rootx() + (self.winfo_width() - win.winfo_reqwidth()) // 2
        y = self.winfo_rooty() + (self.winfo_height() - win.winfo_reqheight()) // 3
        win.geometry(f"+{max(0, x)}+{max(0, y)}")

    def revert_all(self):
        """GỠ SẠCH: mở hộp gỡ với mọi hạng mục đã tích sẵn – vẫn phải chọn ĐÚNG kênh mạnh."""
        self.revert_by_category(all_ticked=True)

    # ------------------------------------------------------------ trang kết quả
    def _stat(self, parent, col, label, color, soft, icon=None):
        """.stat-card: vạch màu 2px mép trên, vệt màu 13% tỏa từ trái, icon trong ô vuông, nhãn CHỮ HOA nhỏ,
        số to màu của thẻ."""
        o = tk.Frame(parent, bg=CARD, highlightthickness=1, highlightbackground=BORDER)
        o.grid(row=0, column=col, sticky="we", padx=(0 if col == 0 else 5, 5))
        tk.Frame(o, bg=color, height=2).pack(fill="x")
        cv = tk.Canvas(o, height=62, bg=CARD, highlightthickness=0, bd=0)
        cv.pack(fill="x")
        num_id = {}

        def draw(e=None):
            w = max(cv.winfo_width(), 120)
            cv.delete("all")
            g = art.hgrad(w, 62, _mix(color, CARD, 0.13), CARD, radius=0, fade_at=0.46)
            if g:
                cv.create_image(0, 0, image=g, anchor="nw")
                cv._g = g
            b = art.badge(icon, 34, color, radius=7) if icon else None
            if b:
                cv.create_image(14, 31, image=b, anchor="w")
                cv._b = b
            cv.create_text(60, 18, text=label.upper(), font=(UI, 7, "bold"), fill=MUTED, anchor="w")
            num_id["id"] = cv.create_text(60, 40, text=num_id.get("v", "0"), font=F_NUM, fill=color, anchor="w")
        cv.bind("<Configure>", draw)

        class _Num:   # giữ cách dùng cũ: num.config(text=...)
            def config(self, text="", **_k):
                num_id["v"] = str(text)
                if "id" in num_id:
                    cv.itemconfig(num_id["id"], text=str(text))
            configure = config
        return _Num()

    def _build_result_page(self):
        page = tk.Frame(self.container, bg=BG)
        self._header(page, "Kết quả", "Nhật ký mọi thao tác kéo. Nhấp đúp vào dòng lỗi để xem ảnh chụp màn hình.",
                     icon="chart", color=AMBER)

        # ---- thanh công cụ: 3 nhóm có nhãn, tự xuống hàng khi màn hình hẹp
        bar = tk.Frame(page, bg=CARD, highlightthickness=1, highlightbackground=BORDER)
        bar.pack(fill="x", padx=28, pady=(0, 18))
        flow = tk.Frame(bar, bg=CARD)
        flow.pack(fill="x", padx=16, pady=12)

        def group(title):
            g = tk.Frame(flow, bg=CARD)
            tk.Label(g, text=title.upper(), font=F_CAP, bg=CARD, fg=GOLD if not LIGHT else MUTED).pack(
                anchor="w", pady=(0, 6))
            row = tk.Frame(g, bg=CARD)
            row.pack(anchor="w")
            return g, row

        def tbtn(row, text, cmd, kind="secondary", track=False, icon=None, color=None):
            b = Btn(row, text, cmd, kind=kind, padx=12, pady=6, font=F_SB, icon=icon, color=color)
            b.pack(side="left", padx=(0, 8))
            if track:
                self.step_buttons.append(b)
            return b

        g1, r1 = group("Dữ liệu")
        tbtn(r1, "Dọn bảng", self.clean_table, kind="solid", icon="eraser", color=TEAL)
        tbtn(r1, "Làm mới", self.load_results, icon="refresh", color=BLUE)
        tbtn(r1, "Xuất file đối soát", self.export_reconcile, kind="solid", icon="checklist", color=GREEN)
        tbtn(r1, "Mở nhật ký Excel", self._open_excel, icon="table", color=GREEN)
        tbtn(r1, "Thư mục ảnh lỗi", lambda: self._open(SHOT_DIR), icon="folder", color=AMBER)
        tbtn(r1, "Thư mục dữ liệu", lambda: self._open(DATA), icon="folder", color=TEAL)

        g2, r2 = group("Gỡ khỏi kênh mạnh")
        tbtn(r2, "Gỡ theo hạng mục", self.revert_by_category, kind="solid", track=True, icon="checklist",
             color=ORANGE)
        tbtn(r2, "Gỡ dòng đã chọn", self.revert_selected, track=True, icon="undo", color=ORANGE)
        tbtn(r2, "GỠ SẠCH TẤT CẢ", self.revert_all, kind="solid", track=True, icon="trash", color=RED)
        tbtn(r2, "Xóa dòng lỗi", self.clear_history, track=True, icon="list_x", color=SOFT)
        tbtn(r2, "Xóa sạch nhật ký", self.wipe_log, track=True, icon="trash", color=RED)

        g3, r3 = group("Hỗ trợ khi YouTube đổi giao diện")
        tbtn(r3, "Ghi thao tác mẫu", self.run_record, track=True, icon="record", color=PINK)
        tbtn(r3, "Tạo gói chẩn đoán",
             lambda: self.run(["pack"], need_config=False, on_done=lambda: self._open(DATA)), kind="soft",
             icon="package", color=VIOLET)

        groups = [g1, g2, g3]
        seps = [tk.Frame(flow, bg=BORDER, width=1) for _ in range(len(groups) - 1)]

        last = {"w": 0}

        def relayout(_e=None):
            width = flow.winfo_width()
            if width <= 1 or width == last["w"]:
                return  # chỉ sắp lại khi chiều rộng thật sự thay đổi
            last["w"] = width
            for w in groups + seps:
                w.grid_forget()
            row, col, used = 0, 0, 0
            for i, g in enumerate(groups):
                need = g.winfo_reqwidth() + (33 if col else 0)
                if col and used + need > width:  # không đủ chỗ -> xuống hàng
                    row, col, used = row + 1, 0, 0
                if col:
                    seps[i - 1].grid(row=row, column=col, sticky="ns", padx=16, pady=(2, 2))
                    col += 1
                g.grid(row=row, column=col, sticky="w", pady=(0 if row == 0 else 12, 0))
                col += 1
                used += need
        flow.bind("<Configure>", relayout)

        body = tk.Frame(page, bg=BG)
        body.pack(fill="both", expand=True, padx=28, pady=(0, 24))
        stats = tk.Frame(body, bg=BG)
        stats.pack(fill="x", pady=(0, 20))
        for i in range(3):
            stats.grid_columnconfigure(i, weight=1, uniform="s")
        self.stat_ok = self._stat(stats, 0, "Đã hoàn thành", OK, OK_SOFT, icon="check_circle")
        self.stat_chk = self._stat(stats, 1, "Cần kiểm tra", WARN, WARN_SOFT, icon="warn")
        self.stat_err = self._stat(stats, 2, "Lỗi", ERR, ERR_SOFT, icon="x_circle")

        o = tk.Frame(body, bg=CARD, highlightthickness=1, highlightbackground=BORDER)
        o.pack(fill="both", expand=True)
        fl = tk.Frame(o, bg=CARD)
        fl.pack(side="top", fill="x", padx=14, pady=(12, 10))
        tk.Label(fl, image=art.icon("search_trend", 16, GOLD) or "", bg=CARD).pack(side="left", padx=(0, 8))
        self.f_strong = tk.StringVar(value="Tất cả kênh mạnh")
        self.f_weak = tk.StringVar(value="Tất cả kênh cần kéo")
        self.f_text = tk.StringVar()
        self.f_open = tk.BooleanVar(value=False)
        self.cb_strong = ttk.Combobox(fl, textvariable=self.f_strong, state="readonly", width=26)
        self.cb_strong.pack(side="left")
        self.cb_weak = ttk.Combobox(fl, textvariable=self.f_weak, state="readonly", width=26)
        self.cb_weak.pack(side="left", padx=(8, 0))
        for cb in (self.cb_strong, self.cb_weak):
            cb.bind("<<ComboboxSelected>>", lambda e: self._render_results())
        tk.Label(fl, text="  Tìm:", font=F_S, bg=CARD, fg=MUTED).pack(side="left", padx=(8, 4))
        fe = entry(fl, self.f_text)
        fe.pack(side="left", ipady=4, ipadx=4)
        fe.bind("<KeyRelease>", lambda e: self._render_results())
        ttk.Checkbutton(fl, text="Chỉ dòng chưa gỡ", variable=self.f_open, style="Card.TCheckbutton",
                        command=self._render_results).pack(side="left", padx=(12, 0))
        nl = tk.Frame(o, bg=CARD)
        nl.pack(side="top", fill="x", pady=(0, 6))   # hàng riêng: không đè lên bộ lọc
        self.sel_note = tk.Label(nl, text="", font=F_S, bg=CARD, fg=MUTED, anchor="w")
        self.sel_note.pack(side="left", padx=16)
        self.unhide_lbl = tk.Label(nl, text="", font=F_S, bg=CARD, fg=BLUE, cursor="hand2")
        self.unhide_lbl.bind("<Button-1>", self.unhide_table)
        tw = tk.Frame(o, bg=CARD)
        tw.pack(side="top", fill="both", expand=True)
        cols = ("time", "strong", "weak", "target", "task", "status", "att", "removal")
        heads = ("Thời gian", "Kênh mạnh (dùng để kéo)", "Kênh cần kéo", "Video kênh mạnh đã dùng", "Hạng mục",
                 "Trạng thái", "Video đã gắn / Ghi chú", "Tình trạng gỡ")
        widths = (140, 175, 160, 270, 130, 120, 260, 110)
        self.tree = ttk.Treeview(tw, columns=cols, show="headings", selectmode="extended")
        for c, hd, w in zip(cols, heads, widths):
            self.tree.heading(c, text=hd, anchor="w")
            self.tree.column(c, width=w, minwidth=80, anchor="w", stretch=c in ("target", "att"))
        ys = ttk.Scrollbar(tw, command=self.tree.yview)
        xs = ttk.Scrollbar(tw, orient="horizontal", command=self.tree.xview)
        self.tree.configure(yscrollcommand=ys.set, xscrollcommand=xs.set)
        xs.pack(side="bottom", fill="x")
        self.tree.pack(side="left", fill="both", expand=True, padx=1, pady=1)
        ys.pack(side="right", fill="y")
        self.tree.bind("<<TreeviewSelect>>", lambda e: self._sel_changed())
        o = tw
        self.tree.tag_configure("ok", background=OK_SOFT)
        self.tree.tag_configure("check", background=WARN_SOFT)
        self.tree.tag_configure("err", background=ERR_SOFT)
        self.tree.bind("<Double-1>", self._open_shot)
        self.empty = tk.Label(o, text="Chưa có kết quả nào.\nVào mục Chạy tool để bắt đầu.", font=F, bg=CARD,
                              fg=SOFT, justify="center")
        self._shots = {}
        return page

    def _excel_path(self):
        name = (getattr(self, "cfg", {}) or {}).get("tracker", {}).get("excel_file", "ket_qua_keo_kenh.xlsx")
        return os.path.join(DATA, name)

    def _upgrade_excel(self, warn=False):
        """File kết quả cũ -> thêm trang 'Kết quả' gọn, dễ đọc (không cần chờ lần chạy sau)."""
        if self.proc and self.proc.poll() is None:
            return "running"
        try:
            import excel_view
            excel_view.merge_pending(self._excel_path())   # kết quả ghi tạm lúc file đang mở -> gộp vào file chính
            res = excel_view.upgrade_file(self._excel_path())
        except Exception as e:
            res = "error"
            print("upgrade excel:", e)
        try:   # file đối soát dạng cũ (trang 'Đối soát chi tiết') -> làm lại theo dạng gọn mới
            import report
            ds = os.path.join(os.path.dirname(self._excel_path()), report.OUT_NAME)
            if os.path.exists(ds):
                from openpyxl import load_workbook
                w = load_workbook(ds, read_only=True)
                old = "Đối soát chi tiết" in w.sheetnames
                w.close()
                if old:
                    report.build(self._excel_path(), ds)
        except Exception:
            pass
        if res == "busy" and warn:
            messagebox.showwarning("File đang mở",
                                   "File Excel kết quả đang mở trong Excel / WPS.\n\n"
                                   "Hãy ĐÓNG file đó rồi bấm lại 'Mở nhật ký Excel' để tool sắp xếp lại cho gọn.")
        return res

    def _open_excel(self):
        if self._upgrade_excel(warn=True) == "busy":
            return
        self._open(self._excel_path())

    def load_results(self):
        path = self._excel_path()
        self._upgrade_excel()
        rows = []
        if os.path.exists(path):
            try:
                from openpyxl import load_workbook
                import excel_view as _xv
                wb = load_workbook(_xv.latest(path), read_only=True)
                import excel_view
                rows = list(excel_view.log_sheet(wb).iter_rows(min_row=2, values_only=True))
                wb.close()  # đóng ngay để không khóa file khi tool đang ghi
            except Exception as e:
                self.status.config(text=f"Không đọc được file kết quả (có thể đang mở trong Excel): {e}")
        self._rows = []
        for i, r in enumerate(rows):
            r = list(r) + [""] * 13
            t, target, task, detail, status, err, shot, removal, job, strong, weak, att, jfile = r[:13]
            status = status or ""
            tag = "ok" if "DONE" in status else "check" if "KIỂM" in status else "err" if "LỖI" in status else ""
            self._rows.append(dict(row=i + 2, time=t or "", target=target or "", task=task or "",
                                   detail=detail or "", status=status, err=err or "", shot=shot or "",
                                   removal=removal or "", job=job or "", strong=strong or (job and "(không rõ)") or "",
                                   weak=weak or job or "", att=att or "", file=jfile or "", tag=tag))
        n = {"ok": 0, "check": 0, "err": 0}
        for r in self._visible_rows():
            if r["tag"]:
                n[r["tag"]] += 1
        self.stat_ok.config(text=str(n["ok"]))
        self.stat_chk.config(text=str(n["check"]))
        self.stat_err.config(text=str(n["err"]))
        strongs = sorted({r["strong"] for r in self._rows if r["strong"]})
        weaks = sorted({r["weak"] for r in self._rows if r["weak"]})
        self.cb_strong["values"] = ["Tất cả kênh mạnh"] + strongs
        self.cb_weak["values"] = ["Tất cả kênh cần kéo"] + weaks
        if self.f_strong.get() not in self.cb_strong["values"]:
            self.f_strong.set("Tất cả kênh mạnh")
        if self.f_weak.get() not in self.cb_weak["values"]:
            self.f_weak.set("Tất cả kênh cần kéo")
        self._render_results()

    def _render_results(self):
        self.tree.delete(*self.tree.get_children())
        self._shots = {}
        fs, fw = self.f_strong.get(), self.f_weak.get()
        q = self.f_text.get().strip().lower()
        shown = 0
        for r in reversed(self._visible_rows()):
            if not fs.startswith("Tất cả") and r["strong"] != fs:
                continue
            if not fw.startswith("Tất cả") and r["weak"] != fw:
                continue
            if self.f_open.get() and not (r["tag"] in ("ok", "check") and r["removal"] in ("Chưa gỡ", "❌ Lỗi khi gỡ", "⚠️ Gỡ thủ công")):
                continue
            if q and q not in " ".join(str(v) for v in r.values()).lower():
                continue
            note = r["att"] or r["err"] or r["detail"]
            iid = str(r["row"])
            self.tree.insert("", "end", iid=iid, values=(r["time"], r["strong"], r["weak"], r["target"], r["task"],
                                                         r["status"], note, r["removal"]), tags=(r["tag"],))
            if r["shot"]:
                self._shots[iid] = r["shot"]
            shown += 1
        if self._visible_rows():
            self.empty.place_forget()
        else:
            self.empty.config(text="Bảng đang trống." + ("\nDữ liệu cũ vẫn lưu đủ trong Excel – bấm 'Hiện lại' "
                                                          "nếu cần xem." if self._hidden_count() else
                                                          "\nVào mục Chạy tool để bắt đầu."))
            self.empty.place(relx=0.5, rely=0.45, anchor="center")
        self._sel_changed(shown)
        hid = self._hidden_count()
        if hid:
            self.unhide_lbl.config(text=f"   Đã dọn {hid} dòng cũ khỏi bảng · Hiện lại")
            self.unhide_lbl.pack(side="right", padx=16)
        else:
            self.unhide_lbl.pack_forget()

    # ------------------------------------------------------------ dọn bảng (chỉ ẩn – dữ liệu vẫn nằm trong Excel)
    def _hide_mark(self):
        return (get_setting("res_hidden", {}) or {}).get(os.path.basename(self._excel_path()))

    def _is_hidden(self, r, mark):
        return bool(mark) and r["row"] <= mark.get("row", 0) and str(r["time"]) <= str(mark.get("time", ""))

    def _visible_rows(self):
        mark = self._hide_mark()
        return [r for r in getattr(self, "_rows", []) if not self._is_hidden(r, mark)]

    def _hidden_count(self):
        return len(getattr(self, "_rows", [])) - len(self._visible_rows())

    def clean_table(self):
        rows = getattr(self, "_rows", [])
        if not self._visible_rows():
            return
        last = max(rows, key=lambda r: r["row"])
        d = get_setting("res_hidden", {}) or {}
        d[os.path.basename(self._excel_path())] = {"row": last["row"], "time": str(last["time"])}
        set_setting("res_hidden", d)
        self.load_results()
        self.status.config(text="Đã dọn bảng (lịch sử vẫn lưu, gỡ vẫn đủ).")

    def unhide_table(self, _e=None):
        d = get_setting("res_hidden", {}) or {}
        d.pop(os.path.basename(self._excel_path()), None)
        set_setting("res_hidden", d)
        self.load_results()

    def _sel_changed(self, shown=None):
        n = len(self.tree.selection())
        total = len(self.tree.get_children()) if shown is None else shown
        self.sel_note.config(text=f"{total} dòng" + (f" · đã chọn {n}" if n else " · Ctrl/Shift + bấm để chọn nhiều dòng"))

    # ------------------------------------------------------------ gỡ chính xác
    def _job_for_row(self, r):
        """File kênh dùng để gỡ 1 dòng: phải khớp CẢ file đã kéo lẫn mã kênh mạnh ghi trên dòng; không thì không gỡ."""
        all_jobs = jobs.list_jobs()
        if not r["file"]:
            return None   # dòng cũ không ghi file kênh -> KHÔNG đoán (tránh gỡ nhầm sang kênh khác)
        j = next((j for j in all_jobs if os.path.basename(j["_path"]) == r["file"]), None)
        if j is None:
            return None
        sid = str(j.get("strong_channel", {}).get("channel_id", ""))
        if not sid or sid not in str(r["strong"] or ""):
            return None   # dòng không ghi đúng mã kênh mạnh của file này -> không gỡ theo file này
        return j

    def _revert_rows(self, rows, title, confirm=True):
        todo = [r for r in rows if r["tag"] in ("ok", "check") and r["removal"] in ("Chưa gỡ", "❌ Lỗi khi gỡ", "⚠️ Gỡ thủ công")
                and "đã có sẵn" not in str(r["detail"]) and "đã đúng sẵn trên kênh" not in str(r["detail"])]
        if not todo:
            messagebox.showinfo(title, "Không có dòng nào cần gỡ (chỉ gỡ được dòng đã làm xong và chưa gỡ).")
            return
        groups = {}
        for r in todo:
            j = self._job_for_row(r)
            if not j:
                messagebox.showwarning(title, f"Dòng {r['row']} ({r['strong'] or 'không rõ kênh mạnh'}) không khớp file kênh nào "
                                              "trong tool – tool KHÔNG gỡ để tránh gỡ nhầm kênh. Dòng cũ không rõ kênh: "
                                              "dùng nút 'Gỡ theo hạng mục' → 'Bỏ các dòng cũ'.")
                return
            groups.setdefault(j["_path"], (j, []))[1].append(r)
        lines = []
        for j, rs in groups.values():
            s = j.get("strong_channel", {})
            vids = sorted({r["target"].split("v=")[-1][:11] for r in rs})
            lines.append(f"• Kênh mạnh {s.get('name')} ({s.get('channel_id')}): {len(rs)} mục trên {len(vids)} video")
        if confirm and not messagebox.askyesno(title, "Tool sẽ gỡ ĐÚNG các mục sau, đăng nhập đúng kênh mạnh của từng mục:\n\n"
                                   + "\n".join(lines) +
                                   "\n\nTrước khi xóa, tool đối chiếu với nhật ký (nội dung bình luận, mã video, số thẻ, "
                                   "số ô màn hình kết thúc, link). Thứ đang có khác với thứ tool gắn -> không xóa, "
                                   "đánh dấu 'Gỡ thủ công'. Gỡ xong tool mở lại từng chỗ kiểm tra cho sạch."
                                   "\n\nTiếp tục?"):
            return
        self._rq = [(path, ",".join(str(r["row"]) for r in rs)) for path, (j, rs) in groups.items()]
        self._rv_watch = [(j, {r["row"] for r in rs}) for path, (j, rs) in groups.items()]
        self._next_revert()

    def _next_revert(self):
        if not getattr(self, "_rq", None):
            self.load_results()
            self._revert_summary()
            return
        path, rows = self._rq.pop(0)
        self.run(["revert", "--rows", rows, "--config", path], stdin_text="GO\n", on_done=self._next_revert,
                 save_list=False)

    def _revert_summary(self):
        """Gỡ xong: đọc LẠI nhật ký và báo rõ từng kênh – đã gỡ hết, hay còn những mục nào chưa gỡ."""
        watch = getattr(self, "_rv_watch", None)
        self._rv_watch = None
        if not watch:
            return
        import excel_view
        by_row = {r["row"]: r for r in getattr(self, "_rows", [])}
        lines, left_all = [], 0
        for j, rows in watch:
            s = j.get("strong_channel", {})
            sid = str(s.get("channel_id") or "")
            fname = os.path.basename(j["_path"])
            left = [r for r in self._pending() if r["file"] == fname and sid and sid in str(r["strong"])]
            done = sum(1 for n in rows if "Đã gỡ" in str(by_row.get(n, {}).get("removal", "")))
            lines.append(f"{'✅' if not left else '⚠️'} {s.get('name')} ({fname}): đã gỡ {done}/{len(rows)} mục"
                         + (" – KÊNH ĐÃ SẠCH." if not left else f" – còn {len(left)} mục chưa gỡ:"))
            cnt = {}
            for r in left:
                cnt[r["task"]] = cnt.get(r["task"], 0) + 1
            lines += [f"      · {t}: {n} ({'gỡ tay' if any('thủ công' in str(x['removal']) for x in left if x['task'] == t) else 'chưa gỡ / lỗi'})"
                      for t, n in cnt.items()]
            left_all += len(left)
        if os.path.exists(excel_view.pending_path(self._excel_path())):
            lines.append("\n⚠️ File Excel kết quả đang mở trong Excel / WPS: kết quả đã lưu tạm ở file phụ "
                         "và hiện đúng trong tool. Đóng file Excel / WPS để tool gộp vào file chính.")
        title = "Gỡ xong – đã sạch" if not left_all else "Gỡ xong – còn mục chưa gỡ"
        self.status.config(text=lines[0] if len(watch) == 1 else title)
        messagebox.showinfo(title, "\n".join(lines))

    def export_reconcile(self):
        """Tạo file Excel đối soát: video kênh mạnh nào kéo cho video nào, vị trí nào, đã gỡ chưa."""
        try:
            import report
            import excel_view as _xv
            path = report.build(_xv.latest(self._excel_path()),
                                os.path.join(os.path.dirname(self._excel_path()), report.OUT_NAME))
        except Exception as e:
            messagebox.showwarning("Không tạo được file đối soát", str(e))
            return
        if not path:
            messagebox.showinfo("Chưa có dữ liệu", "Chưa có nhật ký kéo nào để đối soát.")
            return
        self.status.config(text=f"Đã tạo file đối soát: {os.path.basename(path)}")
        self._open(path)

    def revert_selected(self):
        sel = set(self.tree.selection())
        if not sel:
            messagebox.showinfo("Gỡ các dòng đã chọn", "Hãy chọn dòng cần gỡ trong bảng (giữ Ctrl hoặc Shift để chọn "
                                                       "nhiều dòng). Có thể dùng bộ lọc kênh để lọc trước.")
            return
        self._revert_rows([r for r in self._rows if str(r["row"]) in sel], "Gỡ các dòng đã chọn")

    def clear_history(self):
        """Xóa các dòng ❌ LỖI trong bảng Kết quả. Giữ nguyên các dòng đã làm xong (✅ / ⚠️),
        vì tool dùng chúng để nhớ video nào đã kéo và để gỡ khi cần."""
        if self.proc and self.proc.poll() is None:
            messagebox.showinfo("Đang chạy", "Chờ tool chạy xong rồi hãy xóa.")
            return
        path = self._excel_path()
        if not os.path.exists(path):
            messagebox.showinfo("Trống", "Chưa có kết quả nào.")
            return
        try:
            from openpyxl import load_workbook
            import excel_view as _xv
            wb = load_workbook(_xv.latest(path))
            import excel_view
            ws = excel_view.log_sheet(wb)
            err_rows = [r for r in range(2, ws.max_row + 1) if "LỖI" in str(ws.cell(r, 5).value or "")]
            if not err_rows:
                messagebox.showinfo("Không có lỗi", "Bảng kết quả không có dòng lỗi nào.")
                return
            if not messagebox.askyesno("Xóa dòng lỗi",
                                       f"Xóa {len(err_rows)} dòng ❌ LỖI khỏi bảng kết quả?\n\n"
                                       "Các dòng đã làm xong (✅) vẫn được giữ nguyên."):
                return
            for r in reversed(err_rows):  # xóa từ dưới lên để không lệch số dòng
                ws.delete_rows(r, 1)
            try:
                excel_view.build_view(wb)
            except Exception:
                pass
            wb.save(path)
            _xv.drop_pending(path)
        except PermissionError:
            messagebox.showwarning("Không xóa được", "File Excel kết quả đang mở – hãy đóng Excel rồi thử lại.")
            return
        except Exception as e:
            messagebox.showwarning("Không xóa được", str(e))
            return
        self.load_results()
        self.status.config(text=f"Đã xóa {len(err_rows)} dòng lỗi.")

    def wipe_log(self):
        """Xóa SẠCH mọi dòng nhật ký trong file Excel kết quả (+ làm mới file đối soát). Trước khi xóa tool tự
        sao lưu file cũ vào thư mục dữ liệu/sao_luu_nhat_ky – lỡ tay vẫn lấy lại được."""
        if self.proc and self.proc.poll() is None:
            messagebox.showinfo("Đang chạy", "Chờ tool chạy xong rồi hãy xóa.")
            return
        path = self._excel_path()
        if not os.path.exists(path):
            messagebox.showinfo("Trống", "Nhật ký đang trống, không có gì để xóa.")
            return
        import shutil
        from datetime import datetime as _dt
        try:
            from openpyxl import load_workbook
            import excel_view
            import excel_view as _xv
            wb = load_workbook(_xv.latest(path))
            ws = excel_view.log_sheet(wb)
            total = max(ws.max_row - 1, 0)
            self.load_results()
            on = len(self._pending()) if hasattr(self, "_pending") else 0
            if not total:
                messagebox.showinfo("Trống", "Nhật ký đang trống, không có gì để xóa.")
                return
            warn = (f"\n\n⚠️ Còn {on} mục ĐANG KÉO chưa gỡ. Xóa nhật ký xong, tool KHÔNG còn biết các mục đó "
                    "để bấm Gỡ tự động nữa (vẫn nằm trên YouTube). Muốn gỡ thì bấm 'Gỡ sạch tất cả' TRƯỚC."
                    if on else "")
            if not messagebox.askyesno("Xóa sạch nhật ký",
                                       f"Xóa SẠCH {total} dòng nhật ký trong file Excel kết quả?{warn}\n\n"
                                       "Tool tự lưu 1 bản sao trước khi xóa (thư mục dữ liệu → sao_luu_nhat_ky)."):
                return
            bdir = os.path.join(DATA, "sao_luu_nhat_ky")
            os.makedirs(bdir, exist_ok=True)
            backup = os.path.join(bdir, f"ket_qua_keo_kenh_{_dt.now():%Y%m%d_%H%M%S}.xlsx")
            shutil.copy2(_xv.latest(path), backup)
            if ws.max_row > 1:
                ws.delete_rows(2, ws.max_row - 1)
            excel_view.build_view(wb)
            wb.save(path)
            _xv.drop_pending(path)
        except PermissionError:
            messagebox.showwarning("Không xóa được", "File Excel kết quả đang mở trong Excel / WPS – hãy đóng file "
                                                     "rồi bấm lại.")
            return
        except Exception as e:
            messagebox.showwarning("Không xóa được", str(e))
            return
        try:
            import report
            report.build(path)          # file đối soát cũng về trống theo
        except Exception:
            pass
        d = get_setting("res_hidden", {}) or {}
        if d.pop(os.path.basename(path), None) is not None:
            set_setting("res_hidden", d)
        self.load_results()
        self.status.config(text=f"✓ Đã xóa sạch {total} dòng nhật ký. Bản sao: {os.path.basename(backup)}")

    def _open_shot(self, _e):
        sel = self.tree.selection()
        if sel and sel[0] in self._shots:
            p = self._shots[sel[0]]
            self._open(p if os.path.isabs(p) else os.path.join(DATA, p))

    def _open(self, path):
        if not os.path.exists(path):
            messagebox.showinfo("Chưa có", "Chưa có file hoặc thư mục này.")
            return
        if os.name == "nt":
            os.startfile(path)
        else:
            subprocess.Popen(["open" if sys.platform == "darwin" else "xdg-open", path])

    def on_close(self):
        if self.proc and self.proc.poll() is None:
            if not messagebox.askyesno("Thoát", "Tool đang chạy. Dừng và thoát?"):
                return
            self.proc.terminate()
        if self.pt is not None:
            if self.pt.state in ("running", "paused") and \
                    not messagebox.askyesno("Thoát", "Module Phân tích video đang chạy. Dừng và thoát?"):
                return
            self.pt.shutdown()
        self.destroy()


if __name__ == "__main__":
    App().mainloop()
