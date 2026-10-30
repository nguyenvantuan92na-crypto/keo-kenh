"""
Trang "Phân tích video" trong giao diện tool (tkinter, cùng phong cách & bảng màu với các trang khác).
Bật/tắt ở thanh bên (mục MODULE). Toàn bộ thao tác trình duyệt chạy ở luồng nền (pt_worker) –
giao diện không bị treo; mọi kết quả lưu SQLite (phan_tich.db).
"""
import json
import os
import queue
import tkinter as tk
import tkinter.font as tkfont
from tkinter import filedialog, messagebox, ttk

import pt_ai
import pt_db

BASE = os.path.dirname(os.path.abspath(__file__))
import paths   # noqa: E402
SETTINGS_FILE = os.path.join(paths.DATA, "pt_settings.json")   # có khóa API – chỉ nằm trên máy bạn

ACCOUNTS = {"Kênh cần kéo": "weak", "Kênh mạnh": "strong"}
VIDEO_LANGS = {"Tự nhận theo kênh mục tiêu": "auto", "Bất kỳ": "", "English": "en", "Tagalog": "tl",
               "Ilocano": "ilo", "Bisaya": "ceb", "Vietnamese": "vi"}
DEFAULTS = dict(account="Kênh cần kéo", target_url="", keywords="", video_lang="Tự nhận theo kênh mục tiêu",
                count=5, win_from=1, win_len=8, comment_lang="English", provider=pt_ai.OLLAMA,
                model=pt_ai.PROVIDERS[pt_ai.OLLAMA], key="", auto_keywords=True, search_fallback=True,
                skip_days=True, min_relevance=20, view="Lượt này", step_mode=True, title_only=True)
REC_TAG = {"Like": "like", "Dislike": "dislike", "Bỏ qua": "skip"}


def load_settings():
    d = dict(DEFAULTS)
    try:
        with open(SETTINGS_FILE, encoding="utf-8") as f:
            d.update(json.load(f))
    except Exception:
        pass
    d["provider"] = pt_ai.OLD_NAMES.get(d.get("provider"), d.get("provider"))
    if d.get("provider") not in pt_ai.PROVIDERS:
        d["provider"] = pt_ai.OLLAMA        # cách "dán tay" đã bỏ -> dùng Ollama (tự động)
        d["model"] = pt_ai.PROVIDERS[pt_ai.OLLAMA]
    return d


def save_settings(d):
    try:
        tmp = SETTINGS_FILE + ".tmp"
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(d, f, ensure_ascii=False, indent=1)
        os.replace(tmp, SETTINGS_FILE)
    except Exception:
        pass


class State:
    """Dữ liệu của module – sống suốt phiên (không mất khi đổi giao diện Sáng/Tối)."""

    def __init__(self):
        self.db = pt_db.DB()
        self.events = queue.Queue()
        self.worker = None
        self.settings = load_settings()
        self.run_id = None
        self.state = "idle"
        self.progress = (0, 1)
        self.status = "Sẵn sàng. Điền cấu hình rồi bấm START."
        self.log = []
        self.sel = None
        self.waiting = False

    def ensure_worker(self, cfg, switch=True):
        import pt_worker
        if self.worker is None or not self.worker.is_alive():
            self.worker = pt_worker.Worker(cfg, self.events, self.db)
            self.worker.start()
        elif switch and not self.worker.busy:
            self.worker.cfg = cfg
        return self.worker

    def shutdown(self):
        if self.worker is not None and self.worker.is_alive():
            self.worker.stop()
            self.worker.send("quit")


# ====================================================================== giao diện
class Page:
    def __init__(self, app, G):
        self.app, self.G, self.S = app, G, app.pt
        self.w = {}
        self.frame = self._build()
        self._load_rows()
        self._apply_state()
        for text, level in self.S.log[-400:]:
            self._log_insert(text, level)

    # ------------------------------------------------------------------ dựng
    def _build(self):
        G, s = self.G, self.S.settings
        try:   # tỉ lệ phóng to màn hình Windows (100% = 1.0)
            self.scale = max(1.0, min(2.5, self.app.winfo_fpixels("1i") / 96.0))
        except Exception:
            self.scale = 1.0
        page = tk.Frame(self.app.container, bg=G.BG)
        h = self.app._header(page, "Phân tích video",
                             "Tìm video cùng chủ đề trên Trang chủ, AI chấm điểm & viết bình luận – bạn duyệt rồi mới tương tác.",
                             icon="search_trend", color=G.VIOLET)
        self.chip = tk.Label(h, text="", font=G.F_SB, padx=12, pady=7)
        self.chip.pack(side="right")

        body = tk.Frame(page, bg=G.BG)
        body.pack(fill="both", expand=True, padx=28, pady=(0, 18))

        # ---------------- cấu hình (trên): chỉ các ô có tác dụng; ô phụ thuộc lựa chọn tự ẩn / hiện
        o = tk.Frame(body, bg=G.CARD, highlightthickness=1, highlightbackground=G.BORDER)
        o.pack(fill="x")
        cf = tk.Frame(o, bg=G.CARD)
        cf.pack(fill="x", padx=18, pady=(10, 12))
        for c in range(4):
            cf.grid_columnconfigure(c, weight=1, uniform="cfg")
        self.v = {}
        self.blocks = {}

        def block(key, r, c, label, hint="", colspan=1):
            f = tk.Frame(cf, bg=G.CARD)
            f.grid(row=r, column=c, columnspan=colspan, sticky="nwe", padx=(0 if c == 0 else 14, 0), pady=5)
            tk.Label(f, text=label, font=G.F_SB, bg=G.CARD, fg=G.LABEL, anchor="w").pack(fill="x", pady=(0, 4))
            if hint:
                f._hint = tk.Label(f, text=hint, font=G.F_S, bg=G.CARD, fg=G.SOFT, anchor="w")
            self.blocks[key] = f
            return f

        def var_of(key, kind=tk.StringVar):
            var = kind(value=s.get(key, DEFAULTS.get(key, "")))
            self.v[key] = var
            var.trace_add("write", lambda *_: self._save())
            return var

        def combo(f, key, values):
            cb = ttk.Combobox(f, textvariable=var_of(key), values=list(values), state="readonly", font=G.F)
            cb.pack(fill="x", ipady=3)
            return cb

        def ent(f, key, show=None):
            e = G.entry(f, var_of(key))
            if show:
                e.configure(show=show)
            e.pack(fill="x", ipady=6, ipadx=4)
            return e

        def spin(parent, key, lo, hi, width=4):
            sp = ttk.Spinbox(parent, from_=lo, to=hi, textvariable=var_of(key), width=width, font=G.F)
            return sp

        f = block("target", 0, 0, "Kênh mục tiêu", colspan=2)
        ent(f, "target_url")
        tk.Label(f, text="Để trống = tự lấy kênh cần kéo của kênh đang chọn", font=G.F_S, bg=G.CARD,
                 fg=G.SOFT, anchor="w").pack(fill="x", pady=(3, 0))
        f = block("keywords", 0, 2, "Từ khóa chủ đề (không bắt buộc)")
        ent(f, "keywords")
        tk.Label(f, text="vd: radio drama, love story", font=G.F_S, bg=G.CARD, fg=G.SOFT, anchor="w").pack(
            fill="x", pady=(3, 0))
        f = block("account", 0, 3, "Tài khoản để Like / bình luận")
        combo(f, "account", ACCOUNTS)

        f = block("count", 1, 0, "Số video mỗi lượt")
        spin(f, "count", 1, 10, 6).pack(fill="x", ipady=3)
        f = block("video_lang", 1, 1, "Ngôn ngữ video")
        combo(f, "video_lang", VIDEO_LANGS)
        f = block("comment_lang", 1, 2, "Bình luận bằng")
        combo(f, "comment_lang", pt_ai.COMMENT_LANGS)
        f = block("provider", 1, 3, "AI chấm điểm & viết bình luận")
        combo(f, "provider", pt_ai.PROVIDERS).bind("<<ComboboxSelected>>", lambda e: self._on_provider(True))

        f = block("model", 2, 0, "Model AI")
        self.e_model = ent(f, "model")
        f = block("ollama", 2, 1, "Ollama trên máy này", colspan=2)
        orow = tk.Frame(f, bg=G.CARD)
        orow.pack(fill="x")
        self.b_ollama = G.Btn(orow, "Cài / kiểm tra Ollama", self.setup_ollama, kind="solid", color=G.VIOLET,
                              icon="package", icon_size=14, padx=12, pady=6, font=G.F_SB)
        self.b_ollama.pack(side="left")
        self.ollama_lbl = tk.Label(orow, text="", font=G.F_S, bg=G.CARD, fg=G.MUTED, anchor="w", justify="left")
        self.ollama_lbl.pack(side="left", padx=10, fill="x", expand=True)
        f = block("key", 2, 1, "Khóa API")
        self.e_key = ent(f, "key", show="•")
        f = block("window", 2, 3, "Đoạn lời thoại để phân tích")
        row = tk.Frame(f, bg=G.CARD)
        row.pack(fill="x")
        tk.Label(row, text="Từ phút", font=G.F_S, bg=G.CARD, fg=G.MUTED).pack(side="left")
        spin(row, "win_from", 0, 120, 5).pack(side="left", padx=(6, 14), ipady=3)
        tk.Label(row, text="dài", font=G.F_S, bg=G.CARD, fg=G.MUTED).pack(side="left")
        spin(row, "win_len", 6, 10, 4).pack(side="left", padx=(6, 6), ipady=3)
        tk.Label(row, text="phút", font=G.F_S, bg=G.CARD, fg=G.MUTED).pack(side="left")

        # ---------------- 1 hàng ngang: tùy chọn (trái) · thao tác với video đang chọn (phải)
        tk.Frame(cf, bg=G.BORDER, height=1).grid(row=3, column=0, columnspan=4, sticky="we", pady=(10, 8))
        line = tk.Frame(cf, bg=G.CARD)
        line.grid(row=4, column=0, columnspan=4, sticky="we")
        opts = tk.Frame(line, bg=G.CARD)
        opts.pack(side="left")
        for key, text in (("title_only", "Chấm theo tiêu đề"), ("step_mode", "Duyệt từng video")):
            var = var_of(key, tk.BooleanVar)
            var.set(bool(s.get(key, True)))
            ttk.Checkbutton(opts, text="  " + text, variable=var, style="Card.TCheckbutton",
                            command=self._apply_visibility).pack(side="left", padx=(0, 22))
        tk.Frame(line, bg=G.BORDER, width=1, height=26).pack(side="left", padx=(0, 18))
        acts = tk.Frame(line, bg=G.CARD)
        acts.pack(side="left")
        tk.Label(acts, text="Video đang chọn:", font=G.F_SB, bg=G.CARD, fg=G.INK).pack(side="left", padx=(0, 10))

        def abtn(text, cmd, color, icon):
            b = G.Btn(acts, text, cmd, kind="vivid", color=color, icon=icon, icon_size=15, padx=14, pady=7,
                      font=G.F_SB)
            b.pack(side="left", padx=(0, 8))
            return b
        # màu chuẩn, đậm, chữ trắng – rõ ở cả giao diện Sáng và Tối
        self.b_like = abtn("Like", lambda: self.react("like"), G.GREEN, "check")
        self.b_dislike = abtn("Dislike", lambda: self.react("dislike"), G.RED, "x_circle")
        self.b_watch = abtn("Xem video", self.watch_video, G.BLUE, "play")
        self.b_skip = abtn("Bỏ qua", self.skip, G.ORANGE, "list_x")
        self.b_cmt = abtn("Bình luận", self.open_video, G.VIOLET, "comment_pin")

        # ---------------- thanh điều khiển
        bar = tk.Frame(body, bg=G.BG)
        bar.pack(fill="x", pady=(12, 10))
        left = tk.Frame(bar, bg=G.BG)
        left.pack(side="left")
        self.b_start = G.Btn(left, "START", self.start, icon="play", pady=8, padx=18)
        self.b_start.grid(row=0, column=0)
        self.b_pause = G.Btn(left, "PAUSE", self.pause_resume, kind="vivid", color=G.AMBER, icon="history",
                             icon_size=14, pady=8, padx=14)
        self.b_pause.grid(row=0, column=1, padx=(8, 0))
        self.b_stop = G.Btn(left, "STOP", self.stop, kind="soft", color=G.RED, icon="stop", icon_size=13, pady=8,
                            padx=14)
        self.b_stop.grid(row=0, column=2, padx=(8, 0))
        self.b_next = G.Btn(left, "TIẾP", self.next_video, kind="vivid", color=G.GREEN, icon="play_all",
                            icon_size=14, pady=8, padx=14)
        self.b_next.grid(row=0, column=3, padx=(8, 0))
        G.Btn(bar, "Xuất báo cáo", self.export, kind="vivid", color=G.TEAL, icon="table", icon_size=14,
              padx=12, pady=6, font=G.F_SB).pack(side="right")
        G.Btn(bar, "Đóng tab", self.close_tabs, kind="secondary", color=G.MUTED, icon="x_circle", icon_size=14, padx=10, pady=6,
              font=G.F_SB).pack(side="right", padx=(0, 6))
        self.v["view"] = tk.StringVar(value=s.get("view", "Lượt này"))
        vb = ttk.Combobox(bar, textvariable=self.v["view"], values=["Lượt này", "Toàn bộ lịch sử"], state="readonly",
                          width=15, font=G.F)
        vb.pack(side="right", padx=(0, 10))
        vb.bind("<<ComboboxSelected>>", lambda e: (self._save(), self._load_rows()))

        pf = tk.Frame(body, bg=G.BG)            # tiến trình: 1 hàng riêng, luôn đủ rộng
        pf.pack(fill="x", pady=(0, 10))
        st = ttk.Style(self.app)
        st.configure("PT.Horizontal.TProgressbar", troughcolor=G.CARD2, background=G.VIOLET,
                     bordercolor=G.BORDER, lightcolor=G.VIOLET, darkcolor=G.VIOLET, thickness=10)
        self.pb = ttk.Progressbar(pf, style="PT.Horizontal.TProgressbar", mode="determinate")
        self.pb.pack(fill="x")
        self.status_lbl = tk.Label(pf, text="", font=G.F_S, bg=G.BG, fg=G.MUTED, anchor="w")
        self.status_lbl.pack(fill="x", pady=(4, 0))
        # ---------------- nhật ký (dưới)
        lo = tk.Frame(body, bg=G.CONSOLE, highlightthickness=1, highlightbackground=G.BORDER)
        lo.pack(fill="x", side="bottom", pady=(12, 0))
        top = tk.Frame(lo, bg=G.CONSOLE_BAR)
        top.pack(fill="x")
        tk.Label(top, text="  Nhật ký hoạt động", font=G.F_SB, bg=G.CONSOLE_BAR, fg=G.CONSOLE_TXT,
                 image=G.art.icon("terminal", 15, G.GOLD) or "", compound="left").pack(side="left", padx=10, pady=5)
        tk.Button(top, text="Xóa", font=G.F_S, bg=G.CONSOLE_BAR, fg=G.CONSOLE_TXT, relief="flat", bd=0,
                  activebackground=G.CONSOLE, activeforeground="white", cursor="hand2",
                  command=self._clear_log).pack(side="right", padx=10)
        self.logbox = tk.Text(lo, height=4, font=G.F_MONO, bg=G.CONSOLE, fg=G.CONSOLE_TXT, relief="flat", bd=0,
                              wrap="word", state="disabled", padx=12, pady=6, highlightthickness=0)
        self.logbox.pack(fill="x")
        for tag, col in (("ok", "#6FE08A"), ("err", "#FF8A8C"), ("warn", "#FFD166"), ("info", G.CONSOLE_TXT)):
            self.logbox.tag_configure(tag, foreground=col)
        # ---------------- giữa: bảng + chi tiết
        mid = tk.Frame(body, bg=G.BG)
        mid.pack(fill="both", expand=True)
        mid.grid_columnconfigure(0, weight=1)
        mid.grid_rowconfigure(0, weight=1)
        tf = tk.Frame(mid, bg=G.CARD, highlightthickness=1, highlightbackground=G.BORDER)
        tf.grid(row=0, column=0, sticky="nsew", padx=(0, 14))
        cols = pt_db.COLUMNS
        self.tree = ttk.Treeview(tf, columns=cols, show="headings", selectmode="browse")
        widths = {"STT": 40, "Video": 200, "Chủ đề": 96, "Điểm": 50, "Đề xuất": 70, "Trạng thái": 112}
        # màn hình phóng to (125%, 150%...): độ rộng theo cỡ chữ thật, không để tiêu đề cột bị cắt
        hfont = tkfont.Font(font=G.F_SB)
        bfont = tkfont.Font(font=G.F)
        for c in widths:
            sample = {"Đề xuất": "Dislike", "Trạng thái": "Đang phân tích", "Chủ đề": "Radio Drama",
                      "Điểm": "100", "STT": "99"}.get(c, "")
            widths[c] = max(int(widths[c] * self.scale), hfont.measure(c) + 30, bfont.measure(sample) + 24)
        for c in cols:
            self.tree.heading(c, text=c)
            self.tree.column(c, width=widths[c], minwidth=widths[c] if c != "Video" else int(100 * self.scale),
                             anchor="w" if c in ("Video", "Chủ đề", "Trạng thái") else "center", stretch=c == "Video")
        ys = ttk.Scrollbar(tf, command=self.tree.yview)
        self.tree.configure(yscrollcommand=ys.set)
        self.tree.pack(side="left", fill="both", expand=True)
        ys.pack(side="right", fill="y")
        self.tree.tag_configure("like", foreground=G.OK)
        self.tree.tag_configure("dislike", foreground=G.ERR)
        self.tree.tag_configure("skip", foreground=G.MUTED)
        self.tree.tag_configure("err", foreground=G.ERR)
        self.tree.bind("<<TreeviewSelect>>", lambda e: self._on_select())
        self.tree.bind("<Double-1>", lambda e: self.watch_video())

        # chi tiết
        dw = int(350 * self.scale)
        dp = tk.Frame(mid, bg=G.CARD, highlightthickness=1, highlightbackground=G.BORDER, width=dw)
        dp.grid(row=0, column=1, sticky="nsew")
        dp.grid_propagate(False)
        dp.pack_propagate(False)
        cv = tk.Canvas(dp, bg=G.CARD, highlightthickness=0, bd=0)
        dsb = ttk.Scrollbar(dp, orient="vertical", command=cv.yview)
        cv.configure(yscrollcommand=dsb.set)
        dsb.pack(side="right", fill="y")
        cv.pack(side="left", fill="both", expand=True)
        d = tk.Frame(cv, bg=G.CARD)
        win = cv.create_window((14, 10), window=d, anchor="nw")
        d.bind("<Configure>", lambda e: cv.configure(scrollregion=(0, 0, e.width, e.height + 20)))
        cv.bind("<Configure>", lambda e: cv.itemconfigure(win, width=max(200, e.width - 28)))
        self.d_canvas = cv
        self.d_title = tk.Label(d, text="Chọn 1 video trong bảng", font=G.F_B, bg=G.CARD, fg=G.INK, anchor="w",
                                justify="left", wraplength=dw - int(60 * self.scale))
        self.d_title.pack(fill="x")
        self.d_meta = tk.Label(d, text="", font=G.F_S, bg=G.CARD, fg=G.MUTED, anchor="w", justify="left",
                               wraplength=dw - int(60 * self.scale))
        self.d_meta.pack(fill="x", pady=(2, 6))
        self.d_reasons = tk.Text(d, height=9, font=G.F_S, bg=G.FIELD, fg=G.INK, relief="flat", wrap="word",
                                 highlightthickness=1, highlightbackground=G.BORDER, padx=8, pady=6, state="disabled")
        self.d_reasons.pack(fill="x")
        head = tk.Frame(d, bg=G.CARD)
        head.pack(fill="x", pady=(10, 2))
        tk.Label(head, text="Bình luận gợi ý", font=G.F_SB, bg=G.CARD, fg=G.LABEL).pack(side="left")
        self.d_clang = tk.Label(head, text="", font=G.F_S, bg=G.CARD, fg=G.SOFT)
        self.d_clang.pack(side="left", padx=6)
        self.c_boxes = []
        for i in range(3):
            fr = tk.Frame(d, bg=G.CARD)
            fr.pack(fill="x", pady=2)
            t = tk.Text(fr, height=3, font=G.F_S, bg=G.FIELD, fg=G.INK, relief="flat", wrap="word",
                        insertbackground=G.INK, highlightthickness=1, highlightbackground=G.BORDER,
                        highlightcolor=G.GOLD, padx=6, pady=4)
            t.pack(side="left", fill="x", expand=True)
            t.bind("<KeyRelease>", lambda e: self._autosave_comments())
            G.Btn(fr, "", lambda i=i: self.copy(i), kind="soft", color=G.BLUE, icon="copy", icon_size=14, padx=6,
                  pady=6).pack(side="left", padx=(6, 0), anchor="n")
            self.c_boxes.append(t)
        tk.Label(d, text="Sửa bình luận là tự lưu · Like / Dislike luôn hỏi lại trước khi làm.", font=G.F_S,
                 bg=G.CARD, fg=G.SOFT, anchor="w", justify="left", wraplength=dw - int(60 * self.scale)).pack(
            fill="x", pady=(6, 0))

        self._set_detail(None)
        self._on_provider()
        return page

    # ------------------------------------------------------------------ cấu hình
    def _on_provider(self, changed=False):
        p = self.v["provider"].get()
        if changed:
            self.v["model"].set(pt_ai.PROVIDERS.get(p, ""))
        self._apply_visibility()
        if p == pt_ai.OLLAMA:
            self._ollama_status()

    def setup_ollama(self):
        """Cài Ollama + tải model ngay trong tool (chạy nền, tiến trình hiện ở thanh tiến trình & nhật ký)."""
        if getattr(self.S, "installing", False):
            return
        if self.S.state in ("running", "paused"):
            messagebox.showinfo("Ollama", "Đang chạy phân tích – chờ xong rồi hãy cài.")
            return
        model = (self.v["model"].get() or pt_ai.PROVIDERS[pt_ai.OLLAMA]).strip()
        if not pt_ai.ollama_exe() and not messagebox.askyesno(
                "Cài Ollama", "Tool sẽ tải bộ cài Ollama chính thức từ ollama.com (khoảng 1 GB) rồi mở bộ cài – "
                              f"bạn bấm Install. Sau đó tool tự tải model {model} (khoảng 4–5 GB).\n\n"
                              "Máy nên có RAM 16 GB và còn trống khoảng 10 GB ổ đĩa.\n\nBắt đầu?"):
            return
        import threading
        self.S.installing = True
        ev = self.S.events
        self.ollama_lbl.config(text="Đang cài / kiểm tra... (xem nhật ký bên dưới)")

        def job():
            try:
                ok = pt_ai.install_ollama(model, log=lambda m: ev.put(("log", dict(msg=m, level="ok" if m.startswith("✅")
                                                                                   else "err" if m.startswith("❌") else "info"))),
                                          progress=lambda d, t: ev.put(("progress", dict(done=d, total=max(1, t)))))
            except Exception as e:
                ok = False
                ev.put(("log", dict(msg=f"❌ Lỗi khi cài Ollama: {e}", level="err")))
            ev.put(("ollama", dict(ok=ok)))
        threading.Thread(target=job, daemon=True).start()

    def _ollama_status(self):
        import threading
        model = (self.v["model"].get() or pt_ai.PROVIDERS[pt_ai.OLLAMA]).strip()
        ev = self.S.events

        def job():
            if not pt_ai.ollama_exe():
                txt, ok = "Chưa cài – bấm nút để tool tự tải & cài", False
            else:
                try:
                    names = pt_ai.ollama_models()
                    ok = any(n in (model, model + ":latest") for n in names)
                    txt = f"✅ Sẵn sàng (model {model})" if ok else f"Đã cài, chưa có model {model} – bấm nút để tải"
                except Exception:
                    txt, ok = "Đã cài nhưng chưa mở – bấm nút để mở & kiểm tra", False
            ev.put(("ollama_status", dict(text=txt, ok=ok)))
        threading.Thread(target=job, daemon=True).start()

    def _apply_visibility(self):
        """Chỉ hiện ô có tác dụng với lựa chọn hiện tại."""
        p = self.v["provider"].get()
        show = {"model": p in (pt_ai.OLLAMA,) or pt_ai.needs_key(p), "key": pt_ai.needs_key(p),
                "ollama": p == pt_ai.OLLAMA,
                "window": not self.v["title_only"].get()}
        for k, on in show.items():
            (self.blocks[k].grid if on else self.blocks[k].grid_remove)()
        (self.b_next.grid if self.v["step_mode"].get() else self.b_next.grid_remove)()
        self._save()

    def on_wheel(self, e):
        try:
            w = self.app.winfo_containing(e.x_root, e.y_root)
        except Exception:
            w = None
        x = w
        while x is not None:
            if x is self.d_canvas:
                self.d_canvas.yview_scroll(int(-e.delta / 120) or (-1 if e.delta > 0 else 1), "units")
                return
            x = getattr(x, "master", None)

    def _save(self):
        s = self.S.settings
        for k, var in self.v.items():
            try:
                val = var.get()
            except Exception:
                continue
            if k in ("count", "win_from", "win_len", "min_relevance"):
                try:
                    val = int(float(val))
                except Exception:
                    continue
            s[k] = val
        save_settings(s)

    def settings_for_job(self, cfg):
        """Cấu hình phân tích cho 1 kênh khi chạy cùng lượt Kéo kênh: kênh mục tiêu = kênh cần kéo của kênh đó."""
        st = self._collect()
        w = (cfg or {}).get("weak_channel", {}) or {}
        if w.get("url"):
            st["target_url"] = w["url"]
        st["job_path"] = (cfg or {}).get("_path", "")
        st["job_name"] = (cfg or {}).get("job_name", "")
        return st

    def _collect(self):
        self._save()
        s = dict(self.S.settings)
        kws = [k.strip() for k in s.get("keywords", "").replace(";", ",").split(",") if k.strip()]
        lang = VIDEO_LANGS.get(s.get("video_lang"), "auto")
        target = s.get("target_url", "").strip() or \
            str(((getattr(self.app, "cfg", {}) or {}).get("weak_channel", {}) or {}).get("url") or "").strip()
        return dict(account=ACCOUNTS.get(s.get("account"), "weak"), target_url=target,
                    keywords=kws, auto_keywords=True, video_lang=lang,
                    count=max(1, min(10, int(s.get("count", 5) or 1))), win_from=max(0, int(s.get("win_from", 1))),
                    win_len=max(6, min(10, int(s.get("win_len", 8)))), comment_lang=s.get("comment_lang", "English"),
                    provider=s.get("provider", ""), model=s.get("model", "").strip(), key=s.get("key", "").strip(),
                    search_fallback=True, step_mode=bool(s.get("step_mode", True)),
                    title_only=bool(s.get("title_only", True)), skip_days=30,
                    min_relevance=int(s.get("min_relevance", 20)),
                    job_path=str((getattr(self.app, "cfg", {}) or {}).get("_path", "")))

    # ------------------------------------------------------------------ điều khiển
    def start(self):
        st = self._collect()
        if not st["target_url"] and not st["keywords"]:
            messagebox.showwarning("Phân tích video", "Kênh đang chọn chưa có link kênh cần kéo. Hãy điền Kênh mục "
                                                      "tiêu (link kênh) hoặc Từ khóa chủ đề.")
            return
        if pt_ai.needs_key(st["provider"]) and not st["key"]:
            if not messagebox.askyesno("Phân tích video", "Chưa nhập Khóa API – tool chỉ chấm điểm sơ bộ theo số liệu "
                                       "và KHÔNG viết bình luận.\n\nVẫn chạy?"):
                return
        app = self.app
        if app.proc and app.proc.poll() is None:
            if not messagebox.askyesno("Phân tích video", "Tool đang chạy kéo kênh trên cùng trình duyệt. Chạy phân "
                                       "tích song song có thể làm 2 việc chen nhau.\n\nVẫn chạy?"):
                return
        cfg = getattr(app, "cfg", None)
        if not cfg:
            messagebox.showwarning("Phân tích video", "Chưa có kênh nào ở trang Thông tin kênh.")
            return
        cfg = dict(cfg)
        cfg["headless"] = False   # cần thấy các tab video
        w = self.S.ensure_worker(cfg)
        self.S.run_id = None
        self.S.state = "running"
        mode = "chấm theo tiêu đề" if st["title_only"] else f"phân tích {st['win_len']} phút từ phút {st['win_from']}"
        ai = st["provider"] if pt_ai.uses_ai(st["provider"], st["key"]) else "không (chấm sơ bộ)"
        self._log_add(f"▶ START · tài khoản: {self.S.settings.get('account')} · {st['count']} video · {mode} · AI: {ai}",
                      "info")
        self._apply_state()
        w.send("analyze", st)

    def pause_resume(self):
        w = self.S.worker
        if not w or not w.is_alive():
            return
        if self.S.state == "paused":
            w.resume()
        elif self.S.state == "running":
            w.pause()

    def next_video(self):
        w = self.S.worker
        if w and w.is_alive():
            w.next()

    def stop(self):
        w = self.S.worker
        if w and w.is_alive():
            w.stop()
            self._log_add("⏹ Đang dừng – chờ bước hiện tại xong...", "warn")

    def close_tabs(self):
        if self.S.worker and self.S.worker.is_alive():
            self.S.worker.send("close_tabs")

    # ------------------------------------------------------------------ sự kiện từ luồng nền
    def handle(self, kind, data):
        if kind == "log":
            self._log_add(data["msg"], data.get("level", "info"))
        elif kind == "status":
            self.S.status = data["text"]
            self.status_lbl.config(text=data["text"])
        elif kind == "progress":
            self.S.progress = (data["done"], max(1, data["total"]))
            self._apply_progress()
        elif kind == "run":
            self.S.run_id = data["run_id"]
            if self.v["view"].get() == "Lượt này":
                self._load_rows()
        elif kind == "row":
            self._refresh_row(data["row_id"])
        elif kind == "state":
            self.S.state = {"closed": "idle"}.get(data["state"], data["state"])
            self._apply_state()
        elif kind == "done":
            self.app.pt_toast("Phân tích: " + (data.get("note") or "xong"))
        elif kind == "ollama":
            self.S.installing = False
            self._ollama_status()
            if data.get("ok"):
                self.app.pt_toast("Ollama đã sẵn sàng – bấm START để phân tích.")
        elif kind == "ollama_status":
            self.ollama_lbl.config(text=data.get("text", ""), fg=self.G.OK if data.get("ok") else self.G.MUTED)
        elif kind == "await":
            self.S.waiting = bool(data.get("waiting"))
            self._apply_state()
            if self.S.waiting:
                self.app.bell()
        elif kind == "error":
            pass

    def _apply_progress(self):
        d, t = self.S.progress
        self.pb.configure(maximum=t, value=d)

    def _apply_state(self):
        G, st = self.G, self.S.state
        running = st in ("running", "paused")
        self.b_start.set_enabled(not running)
        self.b_pause.set_enabled(running)
        self.b_stop.set_enabled(running)
        self.b_next.set_enabled(running and getattr(self.S, "waiting", False))
        self.b_pause.config(text=("  RESUME" if st == "paused" else "  PAUSE"))
        label, col = {"running": ("● Đang chạy", G.GREEN), "paused": ("❚❚ Tạm dừng", G.AMBER)}.get(
            st, ("● Sẵn sàng", G.BLUE))
        self.chip.config(text=label, bg=G.tint(col, 0.8), fg=G.on_tint(col))
        self.status_lbl.config(text=self.S.status)
        self._apply_progress()

    # ------------------------------------------------------------------ bảng
    def _rows(self):
        if self.v["view"].get() == "Toàn bộ lịch sử":
            return list(reversed(self.S.db.rows()))
        rid = self.S.run_id
        if rid is None:   # mở tool lại: hiện lượt gần nhất
            rows = self.S.db.rows(limit=1)
            rid = rows[0]["run_id"] if rows else None
        return self.S.db.rows(rid) if rid else []

    def _values(self, i, r):
        score = "" if r.get("score") is None else r["score"]
        return (i, r.get("title") or r.get("url"), r.get("topic") or "", score, r.get("recommendation") or "",
                r.get("status") or "")

    def _tag(self, r):
        if (r.get("status") or "").startswith("Lỗi"):
            return ("err",)
        return (REC_TAG.get(r.get("recommendation") or "", ""),)

    def _load_rows(self):
        self.tree.delete(*self.tree.get_children())
        for i, r in enumerate(self._rows(), 1):
            self.tree.insert("", "end", iid=str(r["id"]), values=self._values(i, r), tags=self._tag(r))
        if self.S.sel and self.tree.exists(str(self.S.sel)):
            self.tree.selection_set(str(self.S.sel))
            self.tree.see(str(self.S.sel))

    def _refresh_row(self, row_id):
        r = self.S.db.get(row_id)
        if not r:
            return
        iid = str(row_id)
        if self.tree.exists(iid):
            idx = self.tree.index(iid) + 1
            self.tree.item(iid, values=self._values(idx, r), tags=self._tag(r))
        elif self.v["view"].get() == "Lượt này" and r.get("run_id") == self.S.run_id:
            n = len(self.tree.get_children()) + 1
            self.tree.insert("", "end", iid=iid, values=self._values(n, r), tags=self._tag(r))
        if self.S.sel == row_id:
            self._set_detail(r, keep_comments=True)

    def _on_select(self):
        sel = self.tree.selection()
        self.S.sel = int(sel[0]) if sel else None
        self._set_detail(self.S.db.get(self.S.sel) if self.S.sel else None)

    def _set_detail(self, r, keep_comments=False):
        on = r is not None and r.get("score") is not None
        self.d_reasons.config(state="normal")
        self.d_reasons.delete("1.0", "end")
        if r is None:
            self.d_title.config(text="Chọn 1 video trong bảng để xem lý do & bình luận")
            self.d_meta.config(text="")
            self.d_clang.config(text="")
            for t in self.c_boxes:
                t.delete("1.0", "end")
            self.d_reasons.config(state="disabled")
            return
        self.d_title.config(text=r.get("title") or r.get("url"))
        win = pt_db._window(r)
        meta = [r.get("channel") or "", f"{r['score']}/100 · {r.get('category')}" if on else (r.get("status") or ""),
                f"đề xuất: {r.get('recommendation')}" if on else "", f"phân tích {win}" if win else "",
                r.get("transcript_source") or "", r.get("action") and f"đã làm: {r['action']}" or ""]
        self.d_meta.config(text=" · ".join(x for x in meta if x))
        lines = [f"• {x}" for x in (r.get("reasons") or [])]
        if r.get("dislike_basis"):
            lines.append(f"Căn cứ Dislike: {r['dislike_basis']}")
        if r.get("error"):
            lines.append(f"Lỗi: {r['error']}")
        if r.get("ai_provider"):
            lines.append(f"(chấm bởi: {r['ai_provider']})")
        if r.get("status") == "Chờ AI (dán tay)":
            lines.append("Đã đọc nội dung video – bấm nút 'AI dán tay' để lấy điểm, lý do và bình luận.")
        self.d_reasons.insert("1.0", "\n".join(lines) or "Chưa phân tích.")
        self.d_reasons.config(state="disabled")
        self.d_clang.config(text=f"· {r.get('comment_lang') or ''}")
        if not keep_comments or not any(t.get("1.0", "end-1c").strip() for t in self.c_boxes):
            cm = (r.get("comments") or []) + ["", "", ""]
            for t, c in zip(self.c_boxes, cm):
                t.delete("1.0", "end")
                t.insert("1.0", c)

    # ------------------------------------------------------------------ hành động trên 1 dòng
    def _cur(self):
        return self.S.db.get(self.S.sel) if self.S.sel else None

    def _need(self, scored=False):
        """Video đang chọn; chưa chọn (hoặc chưa chấm xong khi cần) -> nhắc, trả None."""
        r = self._cur()
        if not r:
            messagebox.showinfo("Chưa chọn video", "Hãy bấm chọn 1 video trong bảng trước.")
            return None
        if scored and r.get("score") is None:
            messagebox.showinfo("Chưa chấm xong", "Video này chưa được chấm điểm xong – chờ một chút rồi bấm lại.")
            return None
        return r

    def react(self, kind):
        r = self._need(scored=True)
        if not r:
            return
        label = "Like" if kind == "like" else "Dislike"
        rec = r.get("recommendation")
        warn = ""
        if kind == "dislike" and rec != "Dislike":
            warn = "\n\n⚠️ AI KHÔNG đề xuất Dislike cho video này" + (f" (đề xuất: {rec})" if rec else "") + "."
        if kind == "like" and rec != "Like":
            warn = "\n\n⚠️ AI không đề xuất Like cho video này" + (f" (đề xuất: {rec})" if rec else "") + "."
        if not messagebox.askyesno(f"Xác nhận {label}",
                                   f"Bấm {label} cho video:\n{r.get('title')}\n\nbằng tài khoản "
                                   f"'{self.S.settings.get('account')}'?{warn}"):
            return
        w = self.S.ensure_worker(dict(getattr(self.app, "cfg", {}) or {}, headless=False))
        w.send(kind, r["id"])

    def skip(self):
        r = self._need(scored=True)
        if r:
            self.S.db.update(r["id"], status="Bỏ qua", action="Bỏ qua")
            self._refresh_row(r["id"])

    def copy(self, i):
        text = self.c_boxes[i].get("1.0", "end-1c").strip()
        if not text:
            return
        self.app.clipboard_clear()
        self.app.clipboard_append(text)
        self.app.pt_toast(f"Đã sao chép bình luận {i + 1}")

    def _autosave_comments(self):
        r = self._cur()
        if not r:
            return
        cm = [t.get("1.0", "end-1c").strip() for t in self.c_boxes]
        self.S.db.update(r["id"], comments=[c for c in cm if c])

    def watch_video(self):
        """Mở tab video để BẠN tự xem (bấm đúp vào dòng cũng được)."""
        r = self._need()
        if not r:
            return
        self.S.ensure_worker(dict(getattr(self.app, "cfg", {}) or {}, headless=False)).send("watch", r["id"])

    def open_video(self):
        r = self._need()
        if not r:
            return
        self.S.ensure_worker(dict(getattr(self.app, "cfg", {}) or {}, headless=False)).send("open", r["id"])

    def export(self):
        rows = self._rows()
        if not rows:
            messagebox.showinfo("Xuất báo cáo", "Chưa có dữ liệu để xuất.")
            return
        path = filedialog.asksaveasfilename(defaultextension=".xlsx", initialdir=paths.DATA,
                                            initialfile="phan_tich_video.xlsx",
                                            filetypes=[("Excel", "*.xlsx"), ("CSV", "*.csv")])
        if not path:
            return
        try:
            self.S.db.export(path, rows)
            self.app.pt_toast(f"Đã xuất {len(rows)} dòng: {os.path.basename(path)}")
        except Exception as e:
            messagebox.showerror("Xuất báo cáo", f"Không xuất được: {e}\n(File có đang mở trong Excel không?)")

    # ------------------------------------------------------------------ nhật ký
    def _log_add(self, text, level="info"):
        self.S.log.append((text, level))
        self.S.log = self.S.log[-1000:]
        self._log_insert(text, level)

    def _log_insert(self, text, level):
        self.logbox.config(state="normal")
        self.logbox.insert("end", text + "\n", level if level in ("ok", "err", "warn") else "info")
        self.logbox.see("end")
        self.logbox.config(state="disabled")

    def _clear_log(self):
        self.S.log = []
        self.logbox.config(state="normal")
        self.logbox.delete("1.0", "end")
        self.logbox.config(state="disabled")
