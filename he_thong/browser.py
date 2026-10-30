"""
Mở trình duyệt (Cốc Cốc hoặc Chrome) với phiên đăng nhập riêng cho từng kênh.

Trình duyệt được mở như một cửa sổ BÌNH THƯỜNG (không bật cờ tự động hóa,
không --no-sandbox), sau đó tool mới kết nối vào qua cổng gỡ lỗi. Nhờ vậy
Google không coi là bot khi bạn đăng nhập.
"""
import json
import os
import random
import subprocess
import time
import urllib.request

from playwright.sync_api import sync_playwright

SAME_SITE = {"no_restriction": "None", "unspecified": "Lax", "lax": "Lax",
             "strict": "Strict", "none": "None"}

_LOCAL = os.environ.get("LOCALAPPDATA", "")
_PF = os.environ.get("ProgramFiles", r"C:\Program Files")
_PF86 = os.environ.get("ProgramFiles(x86)", r"C:\Program Files (x86)")
CANDIDATES = {
    "coccoc": [
        os.path.join(_LOCAL, r"CocCoc\Browser\Application\browser.exe"),
        os.path.join(_PF, r"CocCoc\Browser\Application\browser.exe"),
        os.path.join(_PF86, r"CocCoc\Browser\Application\browser.exe"),
    ],
    "chrome": [
        os.path.join(_PF, r"Google\Chrome\Application\chrome.exe"),
        os.path.join(_PF86, r"Google\Chrome\Application\chrome.exe"),
        os.path.join(_LOCAL, r"Google\Chrome\Application\chrome.exe"),
    ],
}
NAMES = {"coccoc": "Cốc Cốc", "chrome": "Chrome"}


def human_delay(cfg):
    lo, hi = cfg.get("delay_range_sec", [2, 5])
    time.sleep(random.uniform(lo, hi))


def _side(cfg, who):
    if cfg.get("mode") == "self":
        who = "strong"
    return cfg.get("strong_channel" if who == "strong" else "weak_channel") or {}


def kind_of(cfg, who=None):
    """Trình duyệt của RIÊNG kênh này (ô 'Trình duyệt đăng nhập'); chưa chọn -> trình duyệt chung ở Tùy chọn."""
    k = str(_side(cfg, who).get("browser") or "").strip() if who else ""
    return k if k in ("coccoc", "chrome") else cfg.get("browser", "coccoc")


def is_anon(cfg, who):
    """Kênh này đăng nhập kiểu ẨN DANH: hồ sơ tạm, chạy xong tool xóa sạch (không lưu gì)."""
    return bool(_side(cfg, who).get("incognito")) and not gpm_id(cfg, who)


def find_browser(cfg, who=None):
    """Trả về (đường dẫn .exe, tên trình duyệt)."""
    custom = (cfg.get("browser_path") or "").strip().strip('"')
    kind = kind_of(cfg, who)
    if custom and who and _side(cfg, who).get("browser") and kind != cfg.get("browser", "coccoc"):
        custom = ""          # kênh này chọn trình duyệt khác với đường dẫn chung -> tự tìm trình duyệt đã chọn
    if custom:
        if os.path.exists(custom):
            return custom, NAMES.get(kind, "trình duyệt")
        raise SystemExit(f"❌ Không thấy trình duyệt tại: {custom}")
    for path in CANDIDATES.get(kind, []):
        if path and os.path.exists(path):
            return path, NAMES[kind]
    raise SystemExit(f"❌ Không tìm thấy {NAMES.get(kind, kind)} trên máy. Hãy cài {NAMES.get(kind, kind)}, "
                     f"hoặc điền đường dẫn file .exe vào ô 'Đường dẫn trình duyệt' trong phần Tùy chọn.")


def _port_alive(port):
    try:
        with urllib.request.urlopen(f"http://127.0.0.1:{port}/json/version", timeout=1) as r:
            return r.status == 200
    except Exception:
        return False


def _load_cookies(path):
    """Đọc cookies .json (định dạng của extension Cookie-Editor / EditThisCookie)."""
    with open(path, encoding="utf-8") as f:
        raw = json.load(f)
    out = []
    for c in raw:
        ck = {"name": c["name"], "value": c["value"], "domain": c["domain"],
              "path": c.get("path", "/"), "secure": c.get("secure", True),
              "httpOnly": c.get("httpOnly", False)}
        exp = c.get("expires", c.get("expirationDate"))
        if exp and exp > 0:
            ck["expires"] = int(exp)
        ck["sameSite"] = SAME_SITE.get(str(c.get("sameSite", "Lax")).lower(), "Lax")
        out.append(ck)
    return out


def _profile(cfg, who, create=True):
    if cfg.get("mode") == "self":
        who = "strong"   # kéo cho chính kênh: 1 kênh = 1 trình duyệt duy nhất
    ch = cfg["strong_channel" if who == "strong" else "weak_channel"]
    other = cfg["weak_channel" if who == "strong" else "strong_channel"]
    gid = str(ch.get("gpm_profile_id") or "").strip()
    if gid:   # profile GPM-Login: dữ liệu trình duyệt do GPM giữ; thư mục này chỉ lưu dấu "đã đăng nhập"
        path = os.path.abspath(os.path.join("profiles", "gpm_" + "".join(c for c in gid if c.isalnum() or c in "-_")))
        if create:
            os.makedirs(path, exist_ok=True)
        return path
    if not ch.get("profile_dir") or (who == "weak" and ch.get("profile_dir") == other.get("profile_dir")):
        # an toàn: kênh mạnh và kênh cần kéo KHÔNG BAO GIỜ dùng chung 1 trình duyệt
        stem = os.path.splitext(os.path.basename(cfg.get("_path", "kenh")))[0]
        ch["profile_dir"] = f"profiles/kenh_{ch['channel_id']}" if ch.get("channel_id") else f"profiles/{stem}_{who}"
    path = os.path.abspath(ch["profile_dir"]) + ("_andanh_" if is_anon(cfg, who) else "_") + kind_of(cfg, who)
    if create:
        os.makedirs(path, exist_ok=True)
    return path


MARK = "keo_dang_nhap.json"   # kết quả kiểm tra đăng nhập THẬT gần nhất (trên Studio) của trình duyệt này


def mark_login(path, ok):
    try:
        import json
        import time
        with open(os.path.join(path, MARK), "w", encoding="utf-8") as f:
            json.dump({"ok": bool(ok), "time": time.strftime("%Y-%m-%d %H:%M:%S")}, f)
    except Exception:
        pass


def _marked(path):
    try:
        import json
        with open(os.path.join(path, MARK), encoding="utf-8") as f:
            return bool(json.load(f).get("ok"))
    except Exception:
        return None


def gpm_id(cfg, who):
    if cfg.get("mode") == "self":
        who = "strong"
    return str((cfg.get("strong_channel" if who == "strong" else "weak_channel") or {}).get("gpm_profile_id") or "").strip()


def login_saved(cfg, who):
    """Hồ sơ trình duyệt của kênh đã lưu đăng nhập YouTube chưa (đọc cookie, KHÔNG mở trình duyệt).
    True = đã lưu · False = chưa · None = chưa có hồ sơ / không đọc được."""
    if gpm_id(cfg, who):   # profile GPM-Login: dùng kết quả kiểm tra thật lần gần nhất trên Studio
        try:
            return _marked(_profile(cfg, who, create=False))
        except Exception:
            return None
    import shutil
    import sqlite3
    import tempfile
    import copy
    try:   # đúng thư mục trình duyệt tool dùng khi chạy (kể cả kéo cho chính kênh / file kênh chưa ghi profile_dir)
        base = _profile(copy.deepcopy({k: v for k, v in cfg.items()}), who, create=False)
    except Exception:
        return None
    for sub in (("Default", "Network", "Cookies"), ("Default", "Cookies")):
        f = os.path.join(base, *sub)
        if not os.path.exists(f):
            continue
        tmp = os.path.join(tempfile.gettempdir(), f"keo_ck_{os.getpid()}_{who}.db")
        try:
            shutil.copyfile(f, tmp)   # trình duyệt đang mở vẫn đọc được bản sao
            con = sqlite3.connect(tmp)
            n = con.execute("SELECT COUNT(*) FROM cookies WHERE host_key LIKE '%youtube.com' AND name IN "
                            "('LOGIN_INFO','SAPISID','__Secure-3PAPISID','__Secure-1PSID','SID')").fetchone()[0]
            con.close()
            return n > 0
        except Exception:
            # trình duyệt của tool còn mở -> Windows khóa file cookie: dùng kết quả kiểm tra thật lần gần nhất
            return _marked(base)
        finally:
            try:
                os.remove(tmp)
            except Exception:
                pass
    return _marked(base) if os.path.isdir(base) and _marked(base) else False


def port_for(cfg, who):
    """Mỗi hồ sơ đăng nhập (mỗi tài khoản) có 1 cổng điều khiển RIÊNG, cố định theo đường dẫn hồ sơ.
    Nhờ vậy khi kéo nhiều kênh, phiên đăng nhập của kênh này không bao giờ lẫn sang kênh khác."""
    import zlib
    return 9300 + zlib.crc32(_profile(cfg, who).lower().encode("utf-8")) % 600


# chạy ổn định khi cửa sổ bị ẩn / ở ngoài màn hình (Windows không "đóng băng" trang)
STEADY_FLAGS = ["--disable-features=CalculateNativeWinOcclusion",
                "--disable-backgrounding-occluded-windows", "--disable-renderer-backgrounding",
                "--disable-background-timer-throttling"]
# luôn chạy tiếng Việt: giao diện trình duyệt + ngôn ngữ ưu tiên gửi tới Google/YouTube
LANG_FLAGS = ["--lang=vi", "--accept-lang=vi-VN,vi"]
HIDDEN_POS = (-3200, -3200)


def _force_profile_vi(profile):
    """Ghi ngôn ngữ ưu tiên tiếng Việt vào hồ sơ trình duyệt (chỉ khi trình duyệt của hồ sơ này đang tắt)."""
    import json
    path = os.path.join(profile, "Default", "Preferences")
    try:
        if not os.path.exists(path):
            return
        with open(path, encoding="utf-8") as f:
            data = json.load(f)
        intl = data.setdefault("intl", {})
        if intl.get("accept_languages") == "vi-VN,vi" and intl.get("selected_languages") == "vi-VN,vi":
            return
        intl["accept_languages"] = "vi-VN,vi"
        intl["selected_languages"] = "vi-VN,vi"
        tmp = path + ".keo"
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False)
        os.replace(tmp, path)
    except Exception:
        pass


def _pref_vi(value):
    """Cookie PREF của YouTube với hl=vi (giữ nguyên các thiết lập khác trong cookie)."""
    parts = [x for x in str(value or "").split("&") if x and not x.startswith(("hl=",))]
    return "&".join(parts + ["hl=vi"])


def force_vi_cookies(ctx):
    """Đặt ngôn ngữ YouTube / YouTube Studio = Tiếng Việt cho mọi trang trong trình duyệt này."""
    try:
        old = next((c["value"] for c in ctx.cookies(["https://www.youtube.com", "https://studio.youtube.com"])
                    if c["name"] == "PREF"), "")
        ctx.add_cookies([{"name": "PREF", "value": _pref_vi(old), "domain": ".youtube.com", "path": "/",
                          "expires": time.time() + 2 * 365 * 86400, "secure": True, "sameSite": "Lax"}])
    except Exception:
        pass


STUDIO_LANG_JS = "() => (document.documentElement.lang || '').toLowerCase()"


def ensure_vi_studio(page):
    """Kiểm tra YouTube Studio đang hiện tiếng Việt; chưa phải thì đặt cookie hl=vi, tải lại,
    rồi (nếu vẫn chưa) chọn Tiếng Việt trong menu tài khoản của Studio. Trả về True nếu đã là tiếng Việt."""
    def is_vi():
        try:
            return page.evaluate(STUDIO_LANG_JS).startswith("vi")
        except Exception:
            return False
    if is_vi():
        return True
    print("Studio đang không phải tiếng Việt – chuyển sang Tiếng Việt...", flush=True)
    force_vi_cookies(page.context)
    page.reload(wait_until="domcontentloaded")
    page.wait_for_timeout(5000)
    if is_vi():
        print("✅ Đã chuyển YouTube Studio sang Tiếng Việt.", flush=True)
        return True
    try:  # menu tài khoản Studio -> Ngôn ngữ / Language -> Tiếng Việt
        import re
        page.locator("#avatar-btn, ytcp-topbar-menu-button-renderer #avatar-btn, button#avatar-btn").first.click(timeout=8000)
        page.wait_for_timeout(1500)
        page.get_by_text(re.compile(r"^\s*(Language|Ngôn ngữ)\s*:", re.I)).first.click(timeout=6000)
        page.wait_for_timeout(1500)
        page.get_by_text(re.compile(r"^\s*Tiếng Việt\s*$")).first.click(timeout=6000)
        page.wait_for_timeout(6000)
    except Exception:
        pass
    if is_vi():
        print("✅ Đã chuyển YouTube Studio sang Tiếng Việt.", flush=True)
        return True
    print("⚠️ Chưa chuyển được Studio sang Tiếng Việt – tool vẫn chạy được (nhận cả nhãn tiếng Anh), "
          "nhưng nên tự đổi: YouTube Studio → ảnh đại diện → Ngôn ngữ → Tiếng Việt.", flush=True)
    return False
WINDOW_SIZE = (1600, 1000)


def close_debug_instance(cfg, who, pw=None):
    """Đóng cửa sổ trình duyệt mà tool đã mở (có cổng điều khiển) của tài khoản này, nếu còn mở.
    Không bao giờ treo: đóng nhẹ nhàng tối đa ~12 giây, quá thời gian thì đóng hẳn các tiến trình của hồ sơ này.
    `pw`: kết nối Playwright đang chạy (không được mở kết nối thứ hai lồng bên trong)."""
    import threading
    gid = gpm_id(cfg, who)
    if gid:   # profile GPM-Login: nhờ GPM đóng đúng profile đó
        import gpm
        return gpm.close(gid)
    port = port_for(cfg, who)
    if not _port_alive(port):
        return False

    def _close(p):
        br = p.chromium.connect_over_cdp(f"http://127.0.0.1:{port}", timeout=8000)
        br.new_browser_cdp_session().send("Browser.close")

    def job():
        try:
            if pw is not None:
                _close(pw)
            else:
                with sync_playwright() as p:
                    _close(p)
        except Exception:
            pass
    if pw is not None:
        job()
    else:
        t = threading.Thread(target=job, daemon=True)
        t.start()
        t.join(12)
    for _ in range(20):
        if not _port_alive(port):
            break
        time.sleep(0.5)
    else:
        kill_profile(_profile(cfg, who))
    time.sleep(2)  # chờ trình duyệt ghi xong dữ liệu đăng nhập
    return True


def wait_closed(profile, seconds=15):
    """Sau khi bạn đóng cửa sổ đăng nhập: chờ trình duyệt tự thoát hẳn (để kịp lưu đăng nhập),
    quá thời gian (Cốc Cốc hay chạy ngầm) thì đóng hẳn."""
    for _ in range(int(seconds * 2)):
        if not profile_in_use(profile):
            return True
        time.sleep(0.5)
    kill_profile(profile)
    return False


def kill_profile(profile):
    """Đóng hẳn mọi tiến trình trình duyệt đang dùng hồ sơ `profile` (cửa sổ ẩn / treo của lần chạy trước)."""
    prof = os.path.abspath(profile)
    try:
        if os.name == "nt":
            safe = prof.replace("'", "''")
            ps = ("Get-CimInstance Win32_Process | Where-Object { $_.CommandLine -and "
                  f"$_.CommandLine.Contains('{safe}') }} | ForEach-Object {{ Stop-Process -Id $_.ProcessId -Force "
                  "-ErrorAction SilentlyContinue }")
            subprocess.run(["powershell", "-NoProfile", "-NonInteractive", "-Command", ps], timeout=25,
                           stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                           creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
        else:
            subprocess.run(["pkill", "-f", f"--user-data-dir={prof}"], timeout=10,
                           stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        time.sleep(1.5)
    except Exception:
        pass


def wipe_profile(cfg, who):
    """Xóa sạch trình duyệt (hồ sơ) của RIÊNG kênh này để đăng nhập lại từ đầu. Trả về đường dẫn hồ sơ."""
    import shutil
    close_debug_instance(cfg, who)
    prof = _profile(cfg, who)
    kill_profile(prof)
    for _ in range(3):
        shutil.rmtree(prof, ignore_errors=True)
        if not os.path.exists(prof):
            break
        time.sleep(1.5)
    os.makedirs(prof, exist_ok=True)
    return prof


def wipe_anon(cfg, who, pw=None):
    """Ẩn danh: đóng trình duyệt của kênh này rồi xóa sạch hồ sơ tạm (đăng nhập, cookie, lịch sử)."""
    import shutil
    if not is_anon(cfg, who):
        return False
    try:
        close_debug_instance(cfg, who, pw)
    except Exception:
        pass
    prof = _profile(cfg, who, create=False)
    kill_profile(prof)
    for _ in range(3):
        shutil.rmtree(prof, ignore_errors=True)
        if not os.path.exists(prof):
            print(f"🧹 Ẩn danh: đã đóng trình duyệt và xóa sạch dữ liệu đăng nhập của kênh "
                  f"{'mạnh' if who == 'strong' else 'cần kéo'} (lần sau đăng nhập lại).", flush=True)
            return True
        time.sleep(1.5)
    print(f"⚠️ Ẩn danh: chưa xóa hết được {prof} (trình duyệt còn giữ file) – tool sẽ xóa ở lần chạy sau.",
          flush=True)
    return False


def profile_in_use(profile):
    """Hồ sơ đang bị 1 trình duyệt khác giữ (file khóa của Chrome / Cốc Cốc)."""
    for name in ("lockfile", "SingletonLock"):
        f = os.path.join(profile, name)
        if os.path.lexists(f):
            if name == "lockfile":
                try:
                    os.remove(f)      # xóa được = không ai giữ
                    return False
                except Exception:
                    return True
            return True
    return False


def _login_urls(cfg, who):
    """Cửa sổ đăng nhập mở thẳng vào ĐÚNG kênh của file kênh (Studio của kênh đó)."""
    ch = cfg["strong_channel" if who == "strong" else "weak_channel"]
    cid = str(ch.get("channel_id") or "")
    if cid.startswith("UC"):
        return [f"https://studio.youtube.com/channel/{cid}?hl=vi"]
    if _handle_of(ch.get("url")):   # chưa có mã kênh: mở đúng trang @kênh để bạn thấy kênh nào
        return [f"https://www.youtube.com/{_handle_of(ch.get('url'))}?hl=vi"]
    return ["https://studio.youtube.com/?hl=vi"]


def open_for_login(cfg, who):
    """
    Mở trình duyệt HOÀN TOÀN BÌNH THƯỜNG để đăng nhập: không cổng điều khiển,
    không kết nối tool, luôn HIỆN cửa sổ (kể cả khi đang bật ẩn trình duyệt).
    """
    close_debug_instance(cfg, who)
    exe, name = find_browser(cfg, who)
    prof = _profile(cfg, who)
    if profile_in_use(prof):
        # còn 1 cửa sổ cũ (có thể đang ẩn) giữ hồ sơ này -> cửa sổ đăng nhập sẽ "chui" vào đó, không hiện ra
        print("      · đóng cửa sổ trình duyệt cũ của tài khoản này (đang ẩn / treo)...", flush=True)
        kill_profile(prof)
    _force_profile_vi(prof)
    proc = subprocess.Popen([exe, f"--user-data-dir={_profile(cfg, who)}", "--no-first-run",
                             "--no-default-browser-check", "--start-maximized", *LANG_FLAGS,
                             *_login_urls(cfg, who)],
                            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    return proc, name


# ============================================================ chọn đúng kênh
OWNER_JS = r"""() => {
  // đang xem trang kênh VỚI TƯ CÁCH CHỦ KÊNH: có nút "Tùy chỉnh kênh" / "Quản lý video"
  const re = /^(Tùy chỉnh kênh|Quản lý video|Customize channel|Manage videos)$/i;
  return [...document.querySelectorAll('a, button, yt-button-shape, ytd-button-renderer')]
    .some(e => re.test((e.innerText || e.getAttribute('aria-label') || '').trim())); }"""

SWITCH_JS = r"""(keys) => {
  // trang Chuyển đổi kênh: bấm vào đúng ô kênh (khớp tên / @handle / mã kênh)
  keys = keys.filter(Boolean).map(k => k.toLowerCase());
  const items = [...document.querySelectorAll('ytd-account-item-renderer, ytd-channel-switcher-page-renderer a, ' +
                                              'ytd-account-item-section-renderer ytd-account-item-renderer, ' +
                                              'a[href*="channel_switcher"], tp-yt-paper-icon-item, [role=menuitem], ' +
                                              'ytd-compact-link-renderer')];
  for (const it of items) {
    const t = ((it.innerText || '') + ' ' + (it.getAttribute('href') || '') + ' ' + (it.outerHTML.match(/UC[\w-]{22}/) || [''])[0]).toLowerCase();
    if (keys.some(k => t.includes(k))) {
      const c = it.closest('a, button, ytd-account-item-renderer, tp-yt-paper-icon-item') || it;
      c.setAttribute('data-keo-switch', '1');
      return (it.innerText || '').trim().split('\n')[0];
    }
  }
  return ''; }"""


def _handle_of(url):
    import re as _re
    m = _re.search(r"/(@[\w.\-%]+)", str(url or ""))
    return m.group(1) if m else ""


def resolve_channel_id(page, handle):
    """Mã kênh UC... của 1 link @kênh (đọc trên trang kênh)."""
    import re as _re
    try:
        page.goto(f"https://www.youtube.com/{handle}", wait_until="domcontentloaded")
        page.wait_for_timeout(2500)
        html = page.evaluate("() => (document.querySelector('link[rel=canonical]') || {}).href + ' ' + "
                             "((document.querySelector('meta[itemprop=channelId], meta[itemprop=identifier]') "
                             "|| {}).content || '')")
        m = _re.search(r"(UC[\w-]{22})", html or "") or _re.search(r'"(?:channelId|externalId)":"(UC[\w-]{22})"',
                                                                  page.content())
        return m.group(1) if m else ""
    except Exception:
        return ""


def studio_channel(page):
    """Mã kênh Studio ĐANG dùng (nơi sửa màn hình kết thúc / thẻ): hỏi nền, không mở tab. "" = không đọc được."""
    import re as _re
    try:
        r = page.context.request.get("https://studio.youtube.com/", timeout=20000)
        m = _re.search(r"/channel/(UC[\w-]{22})", r.url or "") or \
            _re.search(r'"(?:CHANNEL_ID|channelId)"\s*:\s*"(UC[\w-]{22})"', r.text() or "")
        return m.group(1) if m else ""
    except Exception:
        return ""


def _human_wait(page, a=3.5, b=6.5):
    """Chờ ngẫu nhiên như người thật đọc trang (không thao tác dồn dập)."""
    page.wait_for_timeout(int(random.uniform(a, b) * 1000))


def _owner_bg(page, cid):
    """Trang kênh tải bằng yêu cầu nền có nút của CHỦ KÊNH (Tùy chỉnh kênh / Quản lý video) -> đúng tài khoản."""
    import re as _re
    try:
        r = page.context.request.get(f"https://www.youtube.com/channel/{cid}", timeout=20000,
                                     headers={"Accept-Language": "vi-VN,vi;q=0.9"})
        html = r.text() or ""
    except Exception:
        return False
    return bool(_re.search(rf"studio\.youtube\.com/channel/{cid}/editing|Tùy chỉnh kênh|Customize channel|"
                           r"Quản lý video|Manage videos", html))


def select_channel(page, ch, log=print):
    """Đưa trình duyệt về ĐÚNG kênh đã lưu trong file kênh (1 tài khoản Google có thể có nhiều kênh).
    Trả True khi đã xác nhận đang dùng đúng kênh."""
    cid = str(ch.get("channel_id") or "")
    name = str(ch.get("name") or "").strip()
    handle = _handle_of(ch.get("url"))
    if not cid.startswith("UC") and handle:   # file kênh chưa có mã kênh -> đọc từ trang @kênh
        cid = resolve_channel_id(page, handle) or ""
        if cid:
            ch["channel_id"] = cid
            log(f"      · mã kênh của {handle}: {cid}")
    if not cid.startswith("UC"):
        log(f"❌ File kênh chưa có mã kênh (UC...) hoặc link @kênh của {name or 'kênh này'} – hãy điền ở trang "
            f"Thông tin kênh để tool biết mở đúng kênh nào.")
        return False
    label = name or cid
    # 1) kiểm tra bằng YÊU CẦU NỀN (không mở trang nào): Studio đang ở đúng kênh + YouTube nhận là chủ kênh
    try:
        if studio_channel(page) == cid and _owner_bg(page, cid):
            log(f"✔ Đang dùng đúng kênh {label} (kiểm tra nền, không mở thêm trang).")
            page._keo_channel_ok = cid
            return True
    except Exception:
        pass

    def is_owner():
        """ĐÚNG kênh = cả 2 phía khớp mã kênh:
        - YouTube (đăng / ghim bình luận): trang kênh hiện nút chủ kênh (Tùy chỉnh kênh / Quản lý video);
        - Studio (màn hình kết thúc, thẻ, cộng tác): Studio đang mở đúng /channel/<mã kênh>."""
        try:
            page.goto(f"https://www.youtube.com/channel/{cid}", wait_until="domcontentloaded")
            _human_wait(page)
            if not page.evaluate(OWNER_JS):
                return False
        except Exception:
            return False
        sc = studio_channel(page)
        if sc and sc != cid:
            log(f"      · YouTube đúng kênh nhưng Studio đang ở kênh {sc} – chuyển Studio sang {cid}")
            try:
                page.goto(f"https://studio.youtube.com/channel/{cid}", wait_until="domcontentloaded")
                _human_wait(page)
            except Exception:
                return False
            sc = studio_channel(page)
            if sc and sc != cid:
                return False
        return True
    try:
        # Studio: vào thẳng đúng kênh (bước kiểm tra đăng nhập vừa mở đúng trang này -> không mở lại)
        if not str(page.url or "").startswith(f"https://studio.youtube.com/channel/{cid}"):
            page.goto(f"https://studio.youtube.com/channel/{cid}", wait_until="domcontentloaded")
            _human_wait(page)
        if is_owner():
            log(f"✔ Đang dùng đúng kênh {label}.")
            page._keo_channel_ok = cid
            return True
        # YouTube đang ở kênh khác của cùng tài khoản -> trang Chuyển đổi kênh, bấm đúng kênh
        page.goto("https://www.youtube.com/channel_switcher?next=%2Fchannel%2F" + cid, wait_until="domcontentloaded")
        _human_wait(page)
        got = page.evaluate(SWITCH_JS, [cid, handle, name])
        if got:
            log(f"      · chuyển sang kênh {got}")
            page.locator("[data-keo-switch='1']").first.click(timeout=8000)
            _human_wait(page)
            if is_owner():
                log(f"✔ Đã chuyển sang đúng kênh {label}.")
                page._keo_channel_ok = cid
                return True
    except Exception:
        pass
    log(f"❌ Tài khoản đang đăng nhập không mở được kênh {label} ({cid}). Hãy bấm Đăng nhập lại và đăng nhập "
        f"đúng tài khoản Google có kênh này.")
    return False


class Browsers:
    """Dùng: with Browsers(cfg) as b: page = b.page('strong')"""

    def __init__(self, cfg):
        self.cfg = cfg
        self.hidden = bool(cfg.get("headless"))
        self._pw = None
        self._ctx = {}
        self._browsers = []
        self._chosen = set()
        self._login_ok = {}     # kết quả kiểm tra đăng nhập trong lượt chạy (không mở Studio lần 2 để hỏi lại)
        self._channel_ok = {}   # đã chuyển được sang ĐÚNG kênh chưa (False = đang ở kênh khác -> dừng)

    def __enter__(self):
        self._pw = sync_playwright().start()
        return self

    def __exit__(self, *a):
        # Chỉ ngắt kết nối; cửa sổ trình duyệt vẫn mở (trừ khi được yêu cầu đóng sau mỗi kênh).
        for br in self._browsers:
            try:
                br.close()
            except Exception:
                pass
        # kênh đăng nhập ẨN DANH: đóng trình duyệt và XÓA SẠCH hồ sơ tạm (không để lại đăng nhập / lịch sử)
        for who in ("strong", "weak"):
            if who in getattr(self, "_used", set()) and is_anon(self.cfg, who) and not getattr(self, "keep_anon", False):
                wipe_anon(self.cfg, who, self._pw)
        self._pw.stop()

    def _launch(self, who):
        self._used = getattr(self, "_used", set()) | {who}
        port = port_for(self.cfg, who)
        label = "mạnh" if who == "strong" else "cần kéo"
        if _port_alive(port):
            if not self.hidden:
                return port  # đang mở sẵn -> dùng lại
            # chế độ ẩn cần các cờ chạy-ổn-định lúc khởi động -> mở lại trình duyệt cho chắc
            print(f"Mở lại trình duyệt của kênh {label} ở chế độ ẩn...", flush=True)
            close_debug_instance(self.cfg, who, self._pw)
        exe, name = find_browser(self.cfg, who)
        profile = _profile(self.cfg, who)
        if profile_in_use(profile):
            # Cốc Cốc / Chrome còn chạy ngầm với hồ sơ này (cửa sổ đăng nhập đã đóng nhưng tiến trình chưa thoát)
            # -> mở mới sẽ "chui" vào tiến trình đó và không bao giờ kết nối được -> đóng hẳn trước
            kill_profile(profile)
        _force_profile_vi(profile)
        args = [exe, f"--remote-debugging-port={port}", f"--user-data-dir={profile}",
                "--no-first-run", "--no-default-browser-check", *STEADY_FLAGS, *LANG_FLAGS]
        if self.hidden:  # trình duyệt THẬT, chỉ đặt cửa sổ ra ngoài màn hình (không dùng headless)
            args += [f"--window-position={HIDDEN_POS[0]},{HIDDEN_POS[1]}",
                     f"--window-size={WINDOW_SIZE[0]},{WINDOW_SIZE[1]}"]
        else:
            args.append("--start-maximized")
        print(f"Đang mở {name} cho kênh {label}" + (" (ẩn)" if self.hidden else "") + "...", flush=True)
        for attempt in range(2):
            subprocess.Popen(args, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            for _ in range(40):
                if _port_alive(port):
                    return port
                time.sleep(0.5)
            if attempt == 0:   # kẹt -> đóng hẳn tiến trình của hồ sơ này rồi mở lại 1 lần
                print(f"      · trình duyệt chưa phản hồi – đóng hẳn rồi mở lại...", flush=True)
                kill_profile(profile)
        raise SystemExit(f"❌ Mở được {name} nhưng không kết nối được. Có thể cửa sổ đăng nhập "
                         f"của kênh này vẫn đang mở – hãy đóng nó rồi thử lại.")

    def _place_window(self, page):
        """Ẩn: đưa cửa sổ ra ngoài màn hình (giữ kích thước 1600x1000 để Studio hiển thị đủ).
        Hiện: nếu cửa sổ đang ở ngoài màn hình thì đưa về và phóng to."""
        try:
            cdp = page.context.new_cdp_session(page)
            win = cdp.send("Browser.getWindowForTarget")
            wid, bounds = win["windowId"], win.get("bounds", {})
            if self.hidden:
                cdp.send("Browser.setWindowBounds", {"windowId": wid, "bounds": {"windowState": "normal"}})
                cdp.send("Browser.setWindowBounds", {"windowId": wid, "bounds": {
                    "left": HIDDEN_POS[0], "top": HIDDEN_POS[1],
                    "width": WINDOW_SIZE[0], "height": WINDOW_SIZE[1]}})
            elif bounds.get("left", 0) < -1000 or bounds.get("top", 0) < -1000:
                cdp.send("Browser.setWindowBounds", {"windowId": wid, "bounds": {
                    "left": 0, "top": 0, "width": WINDOW_SIZE[0], "height": WINDOW_SIZE[1]}})
                cdp.send("Browser.setWindowBounds", {"windowId": wid, "bounds": {"windowState": "maximized"}})
            cdp.detach()
        except Exception:
            pass

    def close_all(self):
        """Đóng hẳn các trình duyệt mà lần chạy này đã dùng (dùng khi chạy lần lượt nhiều kênh)."""
        for who in list(self._ctx):
            close_debug_instance(self.cfg, who, self._pw)
        self._ctx.clear()

    def _who(self, who):
        return "strong" if self.cfg.get("mode") == "self" else who   # 1 kênh: "kênh cần kéo" = chính kênh

    def context(self, who: str):
        who = self._who(who)
        if who in self._ctx:
            return self._ctx[who]
        gid = gpm_id(self.cfg, who)
        if gid:   # mở THẲNG profile có sẵn trong GPM-Login rồi kết nối vào
            import gpm
            label = "mạnh" if who == "strong" else "cần kéo"
            ch0 = self.cfg["strong_channel" if who == "strong" else "weak_channel"]
            print(f"Mở profile GPM-Login '{ch0.get('gpm_profile_name') or gid}' cho kênh {label}...", flush=True)
            br, last = None, ""
            for attempt in range(2):
                try:
                    addr = gpm.start(gid)
                except gpm.GPMError as e:
                    raise SystemExit(f"❌ {e}")
                print(f"      · chờ trình duyệt GPM sẵn sàng ({addr})...", flush=True)
                if gpm.wait_ready(addr, 45):
                    try:
                        br = self._pw.chromium.connect_over_cdp(addr, timeout=30000,
                                                                slow_mo=self.cfg.get("slow_mo_ms", 200))
                        break
                    except Exception as e:
                        last = str(e).splitlines()[0][:120]
                else:
                    last = "trình duyệt GPM không nhận điều khiển sau 45 giây"
                if attempt == 0:   # profile kẹt / còn mở từ lần trước -> nhờ GPM đóng rồi mở lại 1 lần
                    print(f"      · chưa kết nối được ({last}) – đóng profile GPM rồi mở lại...", flush=True)
                    gpm.close(gid)
                    time.sleep(5)
            if br is None:
                raise SystemExit(f"❌ Chưa kết nối được profile GPM '{ch0.get('gpm_profile_name') or gid}' ({last}). "
                                 f"Hãy đóng cửa sổ trình duyệt của profile này bên GPM-Login rồi bấm Đọc lại kênh.")
            print(f"      · đã kết nối profile GPM ({addr})", flush=True)
        else:
            port = self._launch(who)
            br = self._pw.chromium.connect_over_cdp(f"http://127.0.0.1:{port}",
                                                    slow_mo=self.cfg.get("slow_mo_ms", 200))
        self._browsers.append(br)
        ctx = br.contexts[0] if br.contexts else br.new_context()
        # chấm đỏ hiển thị vị trí chuột của tool trên mọi trang
        from human import CURSOR_JS
        try:
            ctx.add_init_script(CURSOR_JS)
            for pg in ctx.pages:
                pg.evaluate(CURSOR_JS)
        except Exception:
            pass
        try:
            ctx.grant_permissions(["clipboard-read", "clipboard-write"])
        except Exception:
            pass
        ch = self.cfg["strong_channel" if who == "strong" else "weak_channel"]
        if ch.get("cookies_file"):
            ctx.add_cookies(_load_cookies(ch["cookies_file"]))
        force_vi_cookies(ctx)   # YouTube / Studio luôn hiện tiếng Việt
        self._ctx[who] = ctx
        return ctx

    def page(self, who: str):
        who = self._who(who)
        ctx = self.context(who)
        p = ctx.pages[0] if ctx.pages else ctx.new_page()
        if not getattr(p, "_keo_dialog", False):
            p.on("dialog", lambda d: d.accept())  # hộp "Rời khỏi trang?" -> đồng ý
            p._keo_dialog = True
            # 1 thao tác (bấm, đọc vị trí, gõ) chờ tối đa 12 giây rồi tool tự xử lý tiếp – không đứng 30 giây
            p.set_default_timeout(12000)
            p.set_default_navigation_timeout(45000)
        if not getattr(p, "_keo_placed", False):
            self._place_window(p)
            p._keo_placed = True
        if who not in self._chosen and not getattr(self, "_checking", False):
            self._chosen.add(who)   # mỗi lượt chạy chỉ chọn kênh 1 lần
            try:
                self._checking = True
                if self.is_logged_in(who):
                    self._channel_ok[who] = select_channel(
                        p, self.cfg["strong_channel" if who == "strong" else "weak_channel"],
                        log=lambda m: print(m, flush=True))
            finally:
                self._checking = False
        if not self.hidden:
            try:
                p.bring_to_front()  # đưa cửa sổ lên trước để bạn thấy tool đang làm gì
            except Exception:
                pass
        return p

    def is_logged_in(self, who: str) -> bool:
        """Mở Studio 1 lần (thẳng trang của đúng kênh) để biết đã đăng nhập chưa; kết quả nhớ cho cả lượt chạy."""
        who = self._who(who)
        if who in self._login_ok:
            return self._login_ok[who]
        p = self.page(who)
        if who in self._login_ok:          # page() vừa kiểm tra xong
            return self._login_ok[who]
        cid = str(self.cfg["strong_channel" if who == "strong" else "weak_channel"].get("channel_id") or "")
        p.goto(f"https://studio.youtube.com/channel/{cid}" if cid.startswith("UC") else "https://studio.youtube.com/",
               wait_until="domcontentloaded")
        _human_wait(p, 4, 7)
        ok = "accounts.google.com" not in p.url
        if ok:
            ensure_vi_studio(p)
        self._login_ok[who] = ok
        mark_login(_profile(self.cfg, who), ok)
        return ok
