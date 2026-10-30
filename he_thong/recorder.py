"""
Ghi lại thao tác làm tay của người dùng (mỗi cú bấm, ô đã gõ) + ảnh chụp sau mỗi lần bấm,
và đóng gói thành 1 file zip chẩn đoán để hiệu chỉnh tool chính xác.
"""
import glob
import json
import os
import threading
import zipfile
from datetime import datetime

REC_DIR = os.path.join("logs", "record")

REC_JS = r"""
(() => {
  if (window.__keoRecOn) return;
  window.__keoRecOn = true;
  const desc = el => {
    if (!el || !el.tagName) return '';
    let s = el.tagName.toLowerCase();
    if (el.id) s += '#' + el.id;
    const c = (typeof el.className === 'string') ? el.className.trim().split(/\s+/).slice(0, 4).join('.') : '';
    if (c) s += '.' + c;
    for (const a of ['role', 'aria-label', 'aria-checked', 'name', 'type', 'placeholder', 'test-id']) {
      const v = el.getAttribute && el.getAttribute(a);
      if (v) s += `[${a}="${v.slice(0, 60)}"]`;
    }
    return s;
  };
  const chain = el => {
    const out = []; let e = el;
    for (let i = 0; i < 14 && e; i++) {
      if (e.tagName) out.push(desc(e));
      e = e.parentElement || (e.getRootNode && e.getRootNode().host);
    }
    return out;
  };
  const info = (type, ev) => {
    const t = ev.composedPath ? ev.composedPath()[0] : ev.target;
    const el = (t && t.nodeType === 1) ? t : (t && t.parentElement);
    if (!el) return null;
    const r = el.getBoundingClientRect();
    const box = el.closest && el.closest(
      'tp-yt-paper-dialog, ytcp-dialog, [role=dialog], ytve-modal-host, ytcp-video-pick-dialog');
    return {
      type, time: new Date().toISOString(), url: location.href,
      target: desc(el), chain: chain(el),
      text: (el.innerText || '').trim().slice(0, 200),
      value: (el.value || '').slice(0, 200),
      html: (el.outerHTML || '').slice(0, 3000),
      rect: {x: Math.round(r.left), y: Math.round(r.top), w: Math.round(r.width), h: Math.round(r.height)},
      mouse: {x: ev.clientX, y: ev.clientY},
      container: box ? box.outerHTML.slice(0, 150000) : ''
    };
  };
  const send = (type, ev) => { try { const d = info(type, ev); if (d && window.__keoLog) window.__keoLog(d); } catch (e) {} };
  document.addEventListener('click', e => send('click', e), true);
  document.addEventListener('change', e => send('change', e), true);
  document.addEventListener('keydown', e => { if (e.key === 'Enter') send('enter', e); }, true);
})();
"""


def record(b, who, ask, video_url):
    """Đưa người dùng tới đúng trình chỉnh sửa Màn hình kết thúc, rồi Thẻ, của `video_url`,
    và ghi lại mọi cú bấm làm tay ở mỗi chặng."""
    import studio
    os.makedirs(REC_DIR, exist_ok=True)
    for f in glob.glob(os.path.join(REC_DIR, "*")):
        os.remove(f)
    ctx = b.context(who)
    page = b.page(who)
    queue = []
    state = {"on": False, "n": 0, "stage": ""}

    def on_event(source, data):
        if state["on"]:  # chỉ ghi khi người dùng tự làm, không ghi thao tác tool tự mở trang
            data["stage"] = state["stage"]
            queue.append(data)

    ctx.expose_binding("__keoLog", on_event)
    ctx.add_init_script(REC_JS)
    vid = studio.video_id(video_url)
    log_path = os.path.join(REC_DIR, "thao_tac.jsonl")

    stages = [
        ("man_hinh_ket_thuc", "end_screen",
         "👉 ĐANG GHI – MÀN HÌNH KẾT THÚC. Trình chỉnh sửa đã mở sẵn trên Cốc Cốc. Hãy TỰ TAY: "
         "+ Thành phần → Video → Chọn một video cụ thể → chọn video 1; làm lại với video 2; bấm Lưu. "
         "Xong bấm 'Tiếp tục'."),
        ("the", "cards",
         "👉 ĐANG GHI – THẺ. Trình chỉnh sửa Thẻ đã mở sẵn. Hãy TỰ TAY thêm 3 thẻ video: kéo thanh trượt "
         "tới phút 0 → + Thẻ → Video + → chọn video 1; phút 5 → video 2; phút 10 → video 3; bấm Lưu. "
         "Xong bấm 'Tiếp tục'."),
    ]
    with open(log_path, "a", encoding="utf-8") as log:
        for stage, editor_key, msg in stages:
            state["on"] = False
            print(f"Đang mở trình chỉnh sửa cho chặng '{stage}'...", flush=True)
            try:
                studio.open_editor_panel(page, vid, editor_key)
                page.evaluate(REC_JS)
            except Exception as e:
                print(f"⚠️ Không tự mở được trình chỉnh sửa ({str(e).splitlines()[0][:120]}). "
                      f"Bạn hãy tự mở nó trên Cốc Cốc rồi làm tiếp.", flush=True)
                try:
                    page.evaluate(REC_JS)
                except Exception:
                    pass
            try:
                page.screenshot(path=os.path.join(REC_DIR, f"{stage}_000_bat_dau.png"))
            except Exception:
                pass
            state["stage"] = stage
            state["on"] = True
            done = threading.Event()
            threading.Thread(target=lambda m=msg: (ask(m), done.set()), daemon=True).start()
            _process(page, ctx, queue, done, log, state)
            state["on"] = False
    print(f"✅ Đã ghi {state['n']} thao tác.", flush=True)
    return state["n"]


def _process(page, ctx, queue, done, log, state):
    while not done.is_set() or queue:
        page.wait_for_timeout(400)  # giữ kết nối hoạt động & nhận sự kiện
        while queue:
            ev = queue.pop(0)
            state["n"] += 1
            base = os.path.join(REC_DIR, f"{ev.get('stage', '')}_{state['n']:03d}_{ev['type']}")
            container = ev.pop("container", "")
            if container:
                with open(base + ".html", "w", encoding="utf-8") as f:
                    f.write(container)
                ev["container_file"] = os.path.basename(base + ".html")
            log.write(json.dumps(ev, ensure_ascii=False) + "\n")
            log.flush()
            page.wait_for_timeout(700)  # chụp sau khi trang đã phản hồi cú bấm
            try:
                page.screenshot(path=base + ".png")
            except Exception:
                pass
            print(f"   ● {state['n']:03d} {ev['type']:<6} {ev['text'][:50] or ev['target'][:50]}", flush=True)


def pack():
    """Gom bản ghi + ảnh lỗi gần nhất thành 1 file zip để gửi đi."""
    name = f"chan_doan_{datetime.now():%Y%m%d_%H%M}.zip"
    files = sorted(glob.glob(os.path.join(REC_DIR, "*")))
    shots = sorted(glob.glob(os.path.join("logs", "screenshots", "*")), key=os.path.getmtime)[-40:]
    shots += sorted(glob.glob(os.path.join("logs", "tra_loi_loi_*.html")), key=os.path.getmtime)[-10:]
    with zipfile.ZipFile(name, "w", zipfile.ZIP_DEFLATED) as z:
        for f in files + shots:
            z.write(f)
        for f in sorted(glob.glob(os.path.join("kenh", "*.yaml"))):   # file kênh: tên + ID (không có mật khẩu / cookie)
            z.write(f)
        for f in ("ket_qua_keo_kenh.xlsx", os.path.join("logs", "phan_tich.log"),
                  os.path.join("logs", "nhat_ky_chay.txt")):   # nhật ký lỗi từng bước
            if os.path.exists(f):
                z.write(f)
    size = os.path.getsize(name) / 1024 / 1024
    print(f"📦 Đã tạo gói chẩn đoán: {os.path.abspath(name)} ({size:.1f} MB)", flush=True)
    return os.path.abspath(name)
