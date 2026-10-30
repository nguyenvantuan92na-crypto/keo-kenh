"""
Trang "Trả lời bình luận": cài đặt + chạy + bảng kết quả.
G = module gui (lấy bảng màu, nút, thẻ... đang dùng để giao diện đồng bộ khi đổi Sáng / Tối).
"""
import os
import tkinter as tk
import webbrowser
from tkinter import filedialog, messagebox, ttk

import cmt_lang

SCOPES = {"Chỉ bình luận khen": "praise", "Mọi bình luận trừ chê / quảng cáo": "all_ok"}
FILTERS = ("Tất cả", "Đã trả lời", "Cần bạn xem (hỏi, góp ý, chê)", "Chưa làm được", "Xem trước – chưa gửi")
DEFAULTS = dict(videos=4, max_replies=0, reply=True, heart=True, like=True, ai=False,
                scope="Chỉ bình luận khen", lang="English", community=False, max_comments=100)


class Page:
    def __init__(self, app, G):
        self.app, self.G = app, G
        self.opts = dict(DEFAULTS, **(G.get_setting("reply_opts", {}) or {}))
        if int(self.opts.get("videos") or 0) <= 0:   # bản cũ: 0 = tất cả video -> nay mặc định 4 video mới nhất
            self.opts["videos"] = 4
        self.frame = tk.Frame(app.container, bg=G.BG)
        self._build()

    # ------------------------------------------------------------------ dựng giao diện
    def _build(self):
        G, app = self.G, self.app
        right = app._header(self.frame, "Trả lời bình luận",
                            "Cảm ơn khán giả đã khen video của bạn – đúng ngôn ngữ của từng người.",
                            icon="reply", color=G.TEAL)
        self.ch_label = tk.Label(right, text="", font=G.F_SB, bg=G.BG, fg=G.INK)
        self.ch_label.pack(side="right")
        body = tk.Frame(self.frame, bg=G.BG)
        body.pack(fill="both", expand=True, padx=28, pady=(0, 24))
        body.grid_columnconfigure(1, weight=1)
        body.grid_rowconfigure(0, weight=1)

        left = G.ScrollPage(body)
        left.canvas.configure(width=430)
        left.grid(row=0, column=0, sticky="nsew", padx=(0, 20))
        L = left.inner

        # --- cài đặt
        o, b = G.card(L, "Cài đặt", "Áp dụng cho kênh mạnh đang chọn.", icon="sliders", color=G.TEAL)
        o.pack(fill="x", padx=(0, 6), pady=(0, 14))
        self.v = {k: (tk.BooleanVar(value=bool(self.opts[k])) if isinstance(DEFAULTS[k], bool)
                      else tk.StringVar(value=str(self.opts[k]))) for k in DEFAULTS}
        for var in self.v.values():
            var.trace_add("write", lambda *_: self._save())

        def row(label, widget_fn):
            r = tk.Frame(b, bg=G.CARD)
            r.pack(fill="x", pady=4)
            tk.Label(r, text=label, font=G.F_S, bg=G.CARD, fg=G.MUTED, width=26, anchor="w").pack(side="left")
            widget_fn(r).pack(side="left")
        row("Số video xử lý mỗi lượt", lambda f: ttk.Spinbox(f, from_=1, to=50, width=8,
                                                             textvariable=self.v["videos"]))
        tk.Label(b, text="Video mới nhất trước · video đã tương tác hết thì bỏ qua, lấy video kế tiếp",
                 font=G.F_S, bg=G.CARD, fg=G.SOFT, wraplength=360, justify="left").pack(anchor="w")
        row("Tối đa câu trả lời mỗi lượt", lambda f: ttk.Spinbox(f, from_=0, to=5000, width=8,
                                                                 textvariable=self.v["max_replies"]))
        tk.Label(b, text="0 = trả lời hết", font=G.F_S, bg=G.CARD, fg=G.SOFT).pack(anchor="w")
        tk.Frame(b, bg=G.BORDER, height=1).pack(fill="x", pady=(10, 8))

        grid = tk.Frame(b, bg=G.CARD)
        grid.pack(fill="x")
        ttk.Checkbutton(b, text="  Làm ở trang CỘNG ĐỒNG (Studio) – bình luận của mọi video trên 1 trang",
                        variable=self.v["community"], style="Card.TCheckbutton",
                        image=G.art.icon("collab", 16, G.ORANGE) or "", compound="left").pack(anchor="w", pady=(0, 2))
        row("Cộng đồng: số bình luận đọc", lambda f: ttk.Spinbox(f, from_=10, to=2000, width=8,
                                                                textvariable=self.v["max_comments"]))
        tk.Label(b, text="Tích cả Thả tim và Bấm thích: tool chọn 1 trong 2 hợp nội dung (bày tỏ tình cảm / cảm ơn → "
                         "tim; khen ngắn, đánh giá → thích). Chỉ bình luận khen mới được tương tác.",
                 font=G.F_S, bg=G.CARD, fg=G.SOFT, wraplength=360, justify="left").pack(anchor="w", pady=(0, 6))
        for i, (k, label, ic, col) in enumerate([("reply", "Trả lời cảm ơn", "reply", G.TEAL),
                                                 ("heart", "Thả tim", "heart", G.PINK),
                                                 ("like", "Bấm thích", "check_circle", G.BLUE),
                                                 ("ai", "AI kiểm tra lại", "search_trend", G.VIOLET)]):
            ttk.Checkbutton(grid, text="  " + label, variable=self.v[k], style="Card.TCheckbutton",
                            image=G.art.icon(ic, 16, col) or "", compound="left").grid(
                row=i // 2, column=i % 2, sticky="w", pady=3, padx=(0, 22))
        tk.Label(b, text="AI kiểm tra lại: dùng Ollama đã cài ở trang Phân tích video – chỉ trả lời khi "
                         "cả tool và AI đều thấy là lời khen.", font=G.F_S, bg=G.CARD, fg=G.SOFT,
                 wraplength=360, justify="left").pack(anchor="w", pady=(4, 0))
        tk.Frame(b, bg=G.BORDER, height=1).pack(fill="x", pady=(10, 8))
        row("Tim & thích cho", lambda f: ttk.Combobox(f, textvariable=self.v["scope"], state="readonly",
                                                      width=26, values=list(SCOPES)))
        row("Không rõ ngôn ngữ thì dùng", lambda f: ttk.Combobox(
            f, textvariable=self.v["lang"], state="readonly",
            values=[v[0] for v in cmt_lang.THANKS.values()], width=18))

        btns = tk.Frame(b, bg=G.CARD)
        btns.pack(fill="x", pady=(14, 0))
        self.b_go = G.Btn(btns, "BẮT ĐẦU TRẢ LỜI", lambda: self.start(False), kind="primary", color=G.BLUE,
                          icon="play", pady=10)
        self.b_go.pack(fill="x")
        self.b_prev = G.Btn(btns, "Xem trước (chỉ đọc, không gửi)", lambda: self.start(True), kind="secondary",
                            icon="eye_off", pady=7)
        self.b_prev.pack(fill="x", pady=(8, 0))
        self.b_stop = G.Btn(btns, "Dừng", app.stop, kind="soft", icon="stop", color=G.RED, pady=7)
        self.b_stop.pack(fill="x", pady=(8, 0))
        app.step_buttons += [self.b_go, self.b_prev]

        # --- quy tắc (ngắn gọn)
        o, b = G.card(L, "Tool làm gì", None, icon="checklist", color=G.GREEN)
        o.pack(fill="x", padx=(0, 6), pady=(0, 14))
        for t in ("Vào các video MỚI NHẤT, bỏ qua video đã tương tác hết.",
                  "Bình luận KHEN → trả lời cảm ơn đúng ngôn ngữ người viết, tim, thích.",
                  "Câu hỏi, góp ý, chê, quảng cáo → KHÔNG trả lời, để bạn tự xem.",
                  "Bình luận kênh đã trả lời rồi → bỏ qua, không trả lời trùng.",
                  "Gửi xong đọc lại đúng bình luận đó, thấy câu trả lời mới ghi ✅."):
            tk.Label(b, text="•  " + t, font=G.F_S, bg=G.CARD, fg=G.INK, wraplength=360, justify="left").pack(
                anchor="w", pady=2)

        # --- cột phải: tiến trình + bảng
        rcol = tk.Frame(body, bg=G.BG)
        rcol.grid(row=0, column=1, sticky="nsew")
        rcol.grid_rowconfigure(1, weight=1)
        rcol.grid_columnconfigure(0, weight=1)

        o, b = G.card(rcol, None, pad=12, color=G.AMBER)
        o.grid(row=0, column=0, sticky="ew", pady=(0, 14))
        top = tk.Frame(b, bg=G.CARD)
        top.pack(fill="x")
        tk.Label(top, text="Tiến trình", font=G.F_B, bg=G.CARD, fg=G.INK).pack(side="left")
        self.status = tk.Label(top, text="Chưa chạy.", font=G.F_S, bg=G.CARD, fg=G.MUTED)
        self.status.pack(side="right")
        self.logbox = tk.Text(b, height=9, font=G.F_MONO, relief="flat", bd=0, bg=G.LOG_BG if hasattr(G, "LOG_BG")
                              else G.FIELD, fg=G.INK, wrap="word", padx=10, pady=6, state="disabled")
        self.logbox.pack(fill="x", pady=(8, 0))
        for tag, color in (("ok", "#6FE08A"), ("err", "#FF8A8C"), ("warn", "#FFD166"), ("head", "#7EB1FF")):
            self.logbox.tag_configure(tag, foreground=color)

        o, b = G.card(rcol, "Bình luận đã đọc", "Nhấp đúp vào 1 dòng để mở đúng bình luận đó trên YouTube.",
                      pad=14, icon="table", color=G.BLUE)
        o.grid(row=1, column=0, sticky="nsew")
        bar = tk.Frame(b, bg=G.CARD)
        bar.pack(fill="x", pady=(0, 8))
        self.filter = tk.StringVar(value=FILTERS[0])
        cb = ttk.Combobox(bar, textvariable=self.filter, values=FILTERS, state="readonly", width=30)
        cb.pack(side="left")
        cb.bind("<<ComboboxSelected>>", lambda e: self.load())
        self.count = tk.Label(bar, text="", font=G.F_S, bg=G.CARD, fg=G.MUTED)
        self.count.pack(side="left", padx=12)
        G.Btn(bar, "Xuất Excel", self.export, kind="soft", color=G.GREEN, icon="save", padx=10, pady=5,
              font=G.F_SB).pack(side="right")
        G.Btn(bar, "Làm mới", self.load, kind="secondary", icon="refresh", color=G.BLUE, padx=10, pady=5,
              font=G.F_SB).pack(side="right", padx=(0, 8))
        tw = tk.Frame(b, bg=G.CARD)
        tw.pack(fill="both", expand=True)
        cols = ("time", "video", "author", "text", "lang", "kind", "reply", "status")
        heads = ("Thời gian", "Video", "Người bình luận", "Bình luận", "Ngôn ngữ", "Loại", "Câu trả lời / đã làm",
                 "Trạng thái")
        widths = (82, 110, 95, 200, 72, 92, 160, 120)
        self.tree = ttk.Treeview(tw, columns=cols, show="headings", selectmode="browse")
        for c, h, w in zip(cols, heads, widths):
            self.tree.heading(c, text=h, anchor="w")
            self.tree.column(c, width=w, minwidth=60, anchor="w", stretch=c in ("text", "reply"))
        ys = ttk.Scrollbar(tw, command=self.tree.yview)
        xs = ttk.Scrollbar(tw, orient="horizontal", command=self.tree.xview)
        self.tree.configure(yscrollcommand=ys.set, xscrollcommand=xs.set)
        xs.pack(side="bottom", fill="x")
        self.tree.pack(side="left", fill="both", expand=True)
        ys.pack(side="right", fill="y")
        self.tree.tag_configure("ok", background=G.OK_SOFT)
        self.tree.tag_configure("check", background=G.WARN_SOFT)
        self.tree.tag_configure("err", background=G.ERR_SOFT)
        self.tree.bind("<Double-1>", self._open)
        self._rows = {}
        self.refresh_channel()
        self.load()

    # ------------------------------------------------------------------ dữ liệu
    def _save(self):
        d = {}
        for k, var in self.v.items():
            try:
                val = var.get()
            except Exception:
                continue
            if isinstance(DEFAULTS[k], bool):
                d[k] = bool(val)
            elif isinstance(DEFAULTS[k], int):
                try:
                    d[k] = max(0, int(str(val).strip() or 0))
                except ValueError:
                    continue
            else:
                d[k] = val
        self.opts.update(d)
        self.G.set_setting("reply_opts", self.opts)

    def _strong(self):
        cfg = getattr(self.app, "cfg", {}) or {}
        return cfg.get("strong_channel", {}) or {}

    def refresh_channel(self):
        s = self._strong()
        self.ch_label.config(text=f"Kênh mạnh: {s.get('name') or '(chưa chọn)'}" if s else "")

    def args(self, preview=False):
        o = self.opts
        a = ["reply", "--videos", str(max(1, int(o.get("videos") or 4))), "--max-replies", str(int(o.get("max_replies") or 0)),
             "--scope", SCOPES.get(o.get("scope"), "praise"),
             "--lang", cmt_lang.LANG_CHOICES.get(o.get("lang"), "en")]
        if not o.get("reply"):
            a.append("--no-reply")
        if not o.get("heart"):
            a.append("--no-heart")
        if not o.get("like"):
            a.append("--no-like")
        if o.get("ai"):
            a.append("--ai")
        if preview:
            a.append("--preview")
        if o.get("community"):
            a += ["--community", "--max-comments", str(max(10, int(o.get("max_comments") or 100)))]
        return a

    def start(self, preview=False):
        self._save()
        s = self._strong()
        if not str(s.get("channel_id", "")).startswith("UC"):
            messagebox.showwarning("Chưa có kênh", "Kênh đang chọn chưa có mã kênh mạnh (UC...). "
                                                   "Hãy điền ở trang Thông tin kênh.")
            return
        o = self.opts
        if not preview and not (o.get("reply") or o.get("heart") or o.get("like")):
            messagebox.showwarning("Chưa chọn việc", "Hãy tích ít nhất 1 việc: Trả lời cảm ơn, Thả tim hoặc Bấm thích.")
            return
        n = max(1, int(o.get("videos") or 4))
        what = ", ".join(x for x, k in (("trả lời cảm ơn", "reply"), ("thả tim", "heart"), ("bấm thích", "like"))
                         if o.get(k))
        where = (f"Trang Cộng đồng (Studio): đọc {o.get('max_comments')} bình luận mới nhất của mọi video.\n\n"
                 if o.get("community") else
                 f"Xử lý {n} video mới nhất có bình luận mới (video đã tương tác hết sẽ bỏ qua).\n\n")
        msg = (f"Kênh mạnh: {s.get('name')} ({s.get('channel_id')})\n" + where
               + ("XEM TRƯỚC: chỉ đọc và xếp loại, KHÔNG làm gì trên YouTube." if preview else
                  f"Bình luận KHEN: {what} (tim HOẶC thích – chọn theo nội dung).\n"
                  f"Câu hỏi / góp ý / chê / quảng cáo: không đụng tới."))
        if not messagebox.askyesno("Trả lời bình luận", msg + "\n\nBắt đầu?"):
            return
        self.begin()
        self.app.run(self.args(preview), on_done=self.finish)

    def begin(self):
        self.logbox.configure(state="normal")
        self.logbox.delete("1.0", "end")
        self.logbox.configure(state="disabled")
        self.status.config(text="Đang chạy…")
        self.app._rp_mirror = self

    def finish(self):
        self.app._rp_mirror = None
        self.status.config(text="Xong.")
        self.load()

    def mirror(self, text, tag=None):
        try:
            self.logbox.configure(state="normal")
            self.logbox.insert("end", text + "\n", tag)
            self.logbox.see("end")
            self.logbox.configure(state="disabled")
        except Exception:
            pass

    def _db(self):
        import replier
        return replier.DB()

    def _filtered(self):
        import replier
        s = self._strong()
        try:
            rows = self._db().rows(channel_id=s.get("channel_id") or None)
        except Exception:
            rows = []
        f = self.filter.get()
        if f == FILTERS[1]:
            rows = [r for r in rows if r["status"] == replier.S_SENT]
        elif f == FILTERS[2]:
            rows = [r for r in rows if r["kind"] in (cmt_lang.QUESTION, cmt_lang.MIXED, cmt_lang.NEGATIVE)]
        elif f == FILTERS[3]:
            rows = [r for r in rows if r["status"] == replier.S_FAIL]
        elif f == FILTERS[4]:
            rows = [r for r in rows if r["status"] == replier.S_PREVIEW]
        return rows

    def load(self):
        import replier
        self.refresh_channel()
        self.tree.delete(*self.tree.get_children())
        self._rows = {}
        rows = self._filtered()
        for r in rows:
            st = r.get("status") or ""
            tag = "ok" if st.startswith("✅") else "err" if st == replier.S_FAIL else \
                "check" if r.get("kind") in (cmt_lang.QUESTION, cmt_lang.MIXED, cmt_lang.NEGATIVE) else ""
            did = r.get("actions") or ""
            if r.get("reply") and "trả lời" in did:
                did = f"{r['reply']}  ({did})"
            elif r.get("note") and not did:
                did = r["note"]
            iid = self.tree.insert("", "end", values=(
                (r.get("done_at") or r.get("seen_at") or "")[5:16], r.get("video_title") or r.get("video_id"),
                r.get("author"), (r.get("text") or "").replace("\n", " "), cmt_lang.lang_name(r.get("lang")),
                r.get("kind"), did, st), tags=(tag,))
            self._rows[iid] = r
        sent = sum(1 for r in rows if r.get("status") == replier.S_SENT)
        self.count.config(text=f"{len(rows)} bình luận · {sent} đã trả lời")

    def _open(self, _e=None):
        sel = self.tree.selection()
        if not sel:
            return
        r = self._rows.get(sel[0])
        if r:
            cid = r.get("cid") or ""
            webbrowser.open(f"https://www.youtube.com/watch?v={r.get('video_id')}"
                            + (f"&lc={cid}" if cid and ":" not in cid else ""))

    def export(self):
        rows = self._filtered()
        if not rows:
            messagebox.showinfo("Xuất Excel", "Chưa có dòng nào để xuất.")
            return
        path = filedialog.asksaveasfilename(defaultextension=".xlsx", initialfile="tra_loi_binh_luan.xlsx",
                                            filetypes=[("Excel", "*.xlsx"), ("CSV", "*.csv")])
        if path:
            self._db().export(path, rows)
            try:
                os.startfile(path)   # noqa – chỉ có trên Windows
            except Exception:
                pass
