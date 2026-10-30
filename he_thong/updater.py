"""
CẬP NHẬT TOOL từ GitHub – bấm nút "Cập nhật" trên tool là xong, không phải chép file sang từng máy.

· Bản mới nằm ở kho GitHub công khai (REPO dưới đây). Tool đọc he_thong/version.json trên kho để biết có bản mới.
· Cập nhật = tải gói mã nguồn của kho -> sao lưu bản đang dùng -> chép đè các file của tool -> mở lại tool.
· KHÔNG đụng tới dữ liệu của bạn (C:\\Users\\<tên máy>\\KeoKenh_du_lieu: kênh, đăng nhập, Excel, mã API)
  và không đụng thư mục python\\ của bản mang đi.
· Thư viện (requirements.txt) đổi -> tự cài thêm bằng chính Python đang chạy tool.
"""
import hashlib
import io
import json
import os
import shutil
import subprocess
import sys
import time
import urllib.request
import zipfile

import paths

REPO = "nguyenvantuan92na-crypto/keo-kenh"
BRANCH = "main"
APP = paths.APP                                     # ...\he_thong
ROOT = paths.ROOT                                   # thư mục tool
VERSION_FILE = os.path.join(APP, "version.json")
SKIP_TOP = {"python", ".git", ".github"}            # không bao giờ chép đè / xóa
SKIP_NAMES = {"__pycache__", "pt_settings.json", "config.yaml"}


class UpdateError(Exception):
    pass


def _get(url, timeout=30):
    req = urllib.request.Request(url, headers={"User-Agent": "KeoKenh-Updater", "Cache-Control": "no-cache"})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return r.read()


def local_version():
    try:
        with open(VERSION_FILE, encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return {"version": "0", "notes": []}


def _key(v):
    out = []
    for p in str(v or "0").replace("-", ".").split("."):
        out.append(int(p) if p.isdigit() else 0)
    return out


def check(timeout=15):
    """(có bản mới?, bản đang dùng, thông tin bản trên mạng). Lỗi mạng -> UpdateError."""
    remote, err = None, None
    for url in (f"https://raw.githubusercontent.com/{REPO}/{BRANCH}/he_thong/version.json?t={int(time.time())}",
                f"https://github.com/{REPO}/raw/{BRANCH}/he_thong/version.json"):
        try:
            remote = json.loads(_get(url, timeout).decode("utf-8"))
            break
        except Exception as e:
            err = e
    if remote is None:
        raise UpdateError(f"Không đọc được thông tin bản mới trên GitHub ({err.__class__.__name__}) – "
                          f"kiểm tra mạng Internet rồi thử lại.")
    loc = local_version()
    return _key(remote.get("version")) > _key(loc.get("version")), loc, remote


def _sha(path):
    try:
        with open(path, "rb") as f:
            return hashlib.sha1(f.read()).hexdigest()
    except Exception:
        return ""


def _backup(log):
    """Sao lưu bản đang dùng (he_thong + file .bat/.html ngoài cùng) vào KeoKenh_du_lieu\\sao_luu\\tool_cu_*.zip."""
    d = os.path.join(paths.DATA, "sao_luu")
    os.makedirs(d, exist_ok=True)
    name = os.path.join(d, f"tool_cu_{local_version().get('version', '0')}_{time.strftime('%Y%m%d_%H%M%S')}.zip")
    with zipfile.ZipFile(name, "w", zipfile.ZIP_DEFLATED) as z:
        for base, dirs, files in os.walk(ROOT):
            rel = os.path.relpath(base, ROOT)
            top = rel.split(os.sep)[0]
            if top in SKIP_TOP or "__pycache__" in rel:
                dirs[:] = []
                continue
            for fn in files:
                z.write(os.path.join(base, fn), os.path.join(rel, fn))
    old = sorted(f for f in os.listdir(d) if f.startswith("tool_cu_"))
    for f in old[:-5]:                                # giữ 5 bản cũ gần nhất
        try:
            os.remove(os.path.join(d, f))
        except OSError:
            pass
    log(f"Đã sao lưu bản đang dùng: {os.path.basename(name)}")
    return name


def apply(log=print):
    """Tải và cài bản mới nhất. Trả về số hiệu bản vừa cài. Lỗi -> UpdateError (bản đang dùng giữ nguyên)."""
    log("Đang tải bản mới từ GitHub…")
    try:
        data = _get(f"https://github.com/{REPO}/archive/refs/heads/{BRANCH}.zip", timeout=120)
        z = zipfile.ZipFile(io.BytesIO(data))
    except Exception as e:
        raise UpdateError(f"Tải bản mới không được ({e.__class__.__name__}) – kiểm tra mạng rồi thử lại.")
    names = z.namelist()
    prefix = names[0].split("/")[0] + "/" if names else ""
    if not any(n == prefix + "he_thong/gui.py" for n in names):
        raise UpdateError("Gói tải về không đúng cấu trúc tool (thiếu he_thong/gui.py) – không cài.")
    try:
        new_ver = json.loads(z.read(prefix + "he_thong/version.json").decode("utf-8")).get("version", "?")
    except Exception:
        new_ver = "?"
    req = os.path.join(APP, "requirements.txt")
    req_before = _sha(req)
    _backup(log)
    n = 0
    for name in names:
        rel = name[len(prefix):]
        if not rel or rel.endswith("/"):
            continue
        parts = rel.split("/")
        if parts[0] in SKIP_TOP or any(p in SKIP_NAMES for p in parts):
            continue
        dst = os.path.join(ROOT, *parts)
        os.makedirs(os.path.dirname(dst), exist_ok=True)
        tmp = dst + ".moi"
        with z.open(name) as src, open(tmp, "wb") as out:
            shutil.copyfileobj(src, out)
        os.replace(tmp, dst)
        n += 1
    shutil.rmtree(os.path.join(APP, "__pycache__"), ignore_errors=True)
    log(f"Đã chép {n} file của bản {new_ver}.")
    if _sha(req) != req_before:
        log("Bản mới cần thêm thư viện – đang cài (cần mạng, 1–3 phút)…")
        exe = sys.executable.replace("pythonw.exe", "python.exe")
        flags = subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0
        r = subprocess.run([exe, "-m", "pip", "install", "-q", "--disable-pip-version-check",
                            "--no-warn-script-location", "-r", req], capture_output=True, text=True,
                           creationflags=flags)
        if r.returncode != 0:
            log("⚠️ Cài thư viện chưa xong – nếu tool báo lỗi, nhấp đúp Sua_loi_thu_vien.bat.")
    return new_ver


def restart():
    """Mở lại tool (cửa sổ mới) – gọi xong thì đóng cửa sổ hiện tại."""
    exe = sys.executable
    if os.name == "nt" and exe.lower().endswith("python.exe") and os.path.exists(exe[:-10] + "pythonw.exe"):
        exe = exe[:-10] + "pythonw.exe"
    subprocess.Popen([exe, os.path.join(APP, "gui.py")], cwd=ROOT, close_fds=True)
