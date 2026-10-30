r"""
Bố cục thư mục của tool:

    Thư mục tool\  (giải nén ở đâu cũng được)
      Mo_Tool.bat, Cai_dat.bat, README.md
      bieu_mau\     biểu mẫu điền kênh
      he_thong\     mã chạy tool

    C:\Users\<tên máy>\KeoKenh_du_lieu\   DỮ LIỆU CỐ ĐỊNH – không phụ thuộc thư mục tool
      kenh\ (file kênh), profiles\ (đăng nhập), logs\, file Excel, *.db, cài đặt, sao_luu\

Cập nhật tool = giải nén bản mới ở BẤT KỲ đâu: tool luôn đọc đúng dữ liệu cũ (kênh, đăng nhập, cài đặt).

setup() (gọi đầu tiên mỗi lần mở tool / chạy lệnh):
  1. Dữ liệu của bản cũ nằm trong thư mục tool (du_lieu\ hoặc ngoài cùng) -> chuyển vào thư mục dữ liệu cố định.
  2. Thư mục dữ liệu cố định còn trống -> tự tìm bản tool cũ trong Downloads / Desktop / Documents và chép dữ liệu sang.
  3. Dọn file mã cũ nằm ngoài cùng; sao lưu cài đặt mỗi ngày (giữ 14 bản); chdir vào thư mục dữ liệu.
"""
import glob
import os
import shutil
import time

APP = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(APP) if os.path.basename(APP).lower() == "he_thong" else APP
LOCAL_DATA = os.path.join(ROOT, "du_lieu")
HOME_DATA = os.environ.get("KEOKENH_DATA") or os.path.join(os.path.expanduser("~"), "KeoKenh_du_lieu")
DATA = HOME_DATA if ROOT != APP else APP
FORMS = os.path.join(ROOT, "bieu_mau")
BACKUP_DIR = os.path.join(DATA, "sao_luu")

DATA_ITEMS = ["kenh", "profiles", "logs", "config.yaml", "ui_settings.json", "pt_settings.json",
              "videos_to_pull.txt", "phan_tich.db", "binh_luan.db"]
DATA_GLOBS = ["*.xlsx", "chan_doan_*.zip"]
OLD_CODE = ["requirements.txt", "config.example.yaml"]
NOTES = []          # ghi chú lần mở này (giao diện hiện cho bạn biết dữ liệu đã chuyển / tìm thấy ở đâu)


def _move(src, dst, notes):
    """Chuyển src -> dst. Thư mục đã có ở đích thì gộp từng phần (không ghi đè dữ liệu đang có)."""
    try:
        if os.path.isdir(src) and os.path.isdir(dst):
            for name in os.listdir(src):
                _move(os.path.join(src, name), os.path.join(dst, name), notes)
            try:
                os.rmdir(src)
            except OSError:
                pass
        elif not os.path.exists(dst):
            shutil.move(src, dst)
    except Exception as e:
        notes.append(f"chưa chuyển được {os.path.basename(src)} ({e.__class__.__name__}) – hãy tắt Cốc Cốc rồi mở lại tool")


def _has_jobs(d):
    return bool(glob.glob(os.path.join(d, "kenh", "*.yaml")))


def _kill(profiles_dir):
    if os.path.isdir(profiles_dir):
        try:   # trình duyệt cũ còn mở sẽ khóa thư mục đăng nhập -> đóng trước khi chuyển / chép
            import browser
            browser.kill_profile(profiles_dir)
        except Exception:
            pass


def _items_in(base):
    out = [os.path.join(base, n) for n in DATA_ITEMS if os.path.exists(os.path.join(base, n))]
    for g in DATA_GLOBS:
        out += glob.glob(os.path.join(base, g))
    return out


def _find_old_copy():
    """Tìm thư mục dữ liệu của bản tool cũ (chỗ có kenh\\*.yaml) trong Downloads / Desktop / Documents / ổ người dùng.
    Trả về thư mục mới dùng gần nhất, hoặc ""."""
    home = os.path.expanduser("~")
    bases = [(os.path.join(home, n), ("*", "*/*", "*/*/*")) for n in ("Downloads", "Desktop", "Documents", "OneDrive")]
    bases.append((home, ("*",)))   # ngay trong thư mục người dùng: chỉ 1 cấp (tránh quét AppData)
    found = []
    for base, depths in bases:
        if not os.path.isdir(base):
            continue
        for depth in depths:
            for k in glob.glob(os.path.join(base, depth, "kenh")):
                d = os.path.dirname(k)
                if os.path.abspath(d) in (os.path.abspath(HOME_DATA), os.path.abspath(LOCAL_DATA)):
                    continue
                looks_tool = os.path.basename(d).lower() == "du_lieu" or os.path.exists(os.path.join(d, "gui.py"))
                yamls = glob.glob(os.path.join(k, "*.yaml"))
                if looks_tool and yamls:
                    found.append((max(os.path.getmtime(y) for y in yamls), d))
    return max(found)[1] if found else ""


def _copy_from(src, notes):
    _kill(os.path.join(src, "profiles"))
    for item in _items_in(src):
        dst = os.path.join(DATA, os.path.basename(item))
        try:
            if os.path.isdir(item):
                shutil.copytree(item, dst, dirs_exist_ok=True, ignore_dangling_symlinks=True,
                                ignore=shutil.ignore_patterns("Singleton*", "lockfile", "*.lock"))
            elif not os.path.exists(dst):
                shutil.copy2(item, dst)
        except Exception as e:
            notes.append(f"chép thiếu {os.path.basename(item)} ({e.__class__.__name__})")


def backup(keep=14):
    """Sao lưu file kênh + cài đặt + nhật ký Excel mỗi ngày 1 bản (không gồm đăng nhập), giữ `keep` bản mới nhất."""
    import zipfile
    try:
        os.makedirs(BACKUP_DIR, exist_ok=True)
        name = os.path.join(BACKUP_DIR, time.strftime("sao_luu_%Y%m%d.zip"))
        if os.path.exists(name):
            return
        files = glob.glob(os.path.join(DATA, "kenh", "*.yaml")) + glob.glob(os.path.join(DATA, "*.json")) + \
            glob.glob(os.path.join(DATA, "*.xlsx")) + glob.glob(os.path.join(DATA, "*.db"))
        if not files:
            return
        with zipfile.ZipFile(name, "w", zipfile.ZIP_DEFLATED) as z:
            for f in files:
                z.write(f, os.path.relpath(f, DATA))
        for old in sorted(glob.glob(os.path.join(BACKUP_DIR, "sao_luu_*.zip")))[:-keep]:
            os.remove(old)
    except Exception:
        pass


def setup():
    """Gọi đầu tiên khi mở tool / chạy lệnh. Trả về danh sách ghi chú (thường rỗng)."""
    notes = NOTES
    if ROOT == APP:          # chạy kiểu cũ (mọi thứ chung 1 thư mục) -> giữ nguyên
        os.chdir(APP)
        return notes
    first = not _has_jobs(DATA)
    os.makedirs(DATA, exist_ok=True)
    # 1) dữ liệu nằm trong thư mục tool (bản cũ) -> chuyển vào thư mục dữ liệu cố định
    for base in (LOCAL_DATA, ROOT):
        olds = _items_in(base) if os.path.isdir(base) else []
        if olds:
            _kill(os.path.join(base, "profiles"))
            for src in olds:
                _move(src, os.path.join(DATA, os.path.basename(src)), notes)
            if first and _has_jobs(DATA):
                notes.append(f"đã chuyển dữ liệu từ {base}")
    try:
        os.rmdir(LOCAL_DATA)          # du_lieu\ trong thư mục tool đã trống -> bỏ
    except OSError:
        pass
    # 2) vẫn chưa có dữ liệu -> tìm bản tool cũ ở chỗ khác trên máy và chép sang (giữ nguyên bản cũ)
    if not _has_jobs(DATA):
        old = _find_old_copy()
        if old:
            _copy_from(old, notes)
            notes.append(f"đã tìm thấy và chép dữ liệu của bản tool cũ: {old}")
    # 3) dọn file mã cũ nằm ngoài cùng (giải nén đè), sao lưu, làm việc trong thư mục dữ liệu
    for f in glob.glob(os.path.join(ROOT, "*.py")):
        if os.path.exists(os.path.join(APP, os.path.basename(f))):
            try:
                os.remove(f)
            except Exception:
                pass
    for n in OLD_CODE:
        f = os.path.join(ROOT, n)
        if os.path.isfile(f) and os.path.exists(os.path.join(APP, n)):
            try:
                os.remove(f)
            except Exception:
                pass
    shutil.rmtree(os.path.join(ROOT, "__pycache__"), ignore_errors=True)
    os.chdir(DATA)
    backup()
    return notes
