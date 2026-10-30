"""
Danh sách kênh cần kéo. Mỗi kênh = 1 file cấu hình riêng trong thư mục kenh/
(cùng mẫu với config.yaml, thêm: job_name, enabled, order, pull_videos).
"""
import copy
import glob
import os
import re

import yaml

import paths
BASE = paths.APP
JOB_DIR = os.path.join(paths.DATA, "kenh")
EXAMPLE = os.path.join(BASE, "config.example.yaml")
OLD_CONFIG = os.path.join(paths.DATA, "config.yaml")
OLD_VIDEOS = os.path.join(paths.DATA, "videos_to_pull.txt")


def _read(path):
    with open(path, encoding="utf-8") as f:
        return yaml.safe_load(f) or {}


def save(path, cfg):
    data = {k: v for k, v in cfg.items() if not k.startswith("_")}
    tmp = path + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        yaml.safe_dump(data, f, allow_unicode=True, sort_keys=False)
    os.replace(tmp, path)  # ghi an toàn: không bao giờ để lại file hỏng nửa chừng


def load(path):
    cfg = _read(path)
    cfg["_path"] = path
    cfg.setdefault("job_name", os.path.splitext(os.path.basename(path))[0])
    cfg.setdefault("enabled", True)
    cfg.setdefault("order", 999)
    cfg.setdefault("pull_videos", [])
    return cfg


def list_jobs():
    """Các kênh, xếp theo thứ tự chạy."""
    migrate()
    jobs = [load(p) for p in glob.glob(os.path.join(JOB_DIR, "*.yaml"))]
    jobs.sort(key=lambda j: (j.get("order", 999), j["job_name"].lower()))
    return jobs


def _new_path():
    os.makedirs(JOB_DIR, exist_ok=True)
    nums = [int(m.group(1)) for p in glob.glob(os.path.join(JOB_DIR, "kenh_*.yaml"))
            if (m := re.search(r"kenh_(\d+)\.yaml$", p))]
    return os.path.join(JOB_DIR, f"kenh_{(max(nums) + 1) if nums else 1:02d}.yaml")


def _clean_template():
    cfg = _read(EXAMPLE)
    # profile_dir để trống: khi bấm Lưu, tool tự gán hồ sơ đăng nhập theo đúng tài khoản (không dùng nhầm của kênh khác)
    cfg["strong_channel"].update(name="", channel_id="", profile_dir="")
    cfg["weak_channel"].update(url="", name="", channel_id="", videos=["", "", ""], playlist="", pin_comment="",
                               profile_dir="")
    return cfg


def create(name="Kênh mới", copy_from=None):
    """Thêm kênh mới (trống, hoặc nhân bản từ `copy_from`)."""
    if copy_from:
        cfg = copy.deepcopy({k: v for k, v in copy_from.items() if not k.startswith("_")})
    else:
        cfg = _clean_template()
    jobs = list_jobs()
    cfg.update(job_name=name, enabled=True, order=(max([j["order"] for j in jobs]) + 1) if jobs else 1,
               pull_videos=list(cfg.get("pull_videos", [])) if copy_from else [])
    path = _new_path()
    save(path, cfg)
    return load(path)


def delete(job):
    os.remove(job["_path"])


def move(job, step):
    """Đổi thứ tự chạy: step = -1 (lên) / +1 (xuống)."""
    jobs = list_jobs()
    idx = next(i for i, j in enumerate(jobs) if j["_path"] == job["_path"])
    new = idx + step
    if not 0 <= new < len(jobs):
        return
    jobs[idx], jobs[new] = jobs[new], jobs[idx]
    for i, j in enumerate(jobs, 1):
        j["order"] = i
        save(j["_path"], j)


GENERIC_PROFILES = {"profiles/strong", "profiles/weak", "profiles/strong_channel", "profiles/weak_channel", ""}


def profile_dir_for(channel_id, who, jobs, current_path=None):
    """Mỗi KÊNH 1 trình duyệt riêng (theo mã kênh). Cùng 1 kênh dùng ở nhiều file kênh -> dùng chung trình duyệt
    của chính kênh đó; 2 kênh khác nhau KHÔNG BAO GIỜ chung trình duyệt."""
    if channel_id:
        for j in jobs:
            if j["_path"] == current_path:
                continue
            for k in ("strong_channel", "weak_channel"):
                ch = j.get(k, {})
                pd = str(ch.get("profile_dir") or "")
                if ch.get("channel_id") == channel_id and pd and pd not in GENERIC_PROFILES:
                    return pd
        return f"profiles/kenh_{channel_id}"
    stem = os.path.splitext(os.path.basename(current_path or "kenh"))[0]
    return f"profiles/{stem}_{who}"


def fix_profiles(log=None):
    """Tách trình duyệt dùng chung: hồ sơ chung chung (profiles/strong, profiles/weak...), hồ sơ bị 2 kênh KHÁC
    nhau cùng dùng, hoặc kênh mạnh và kênh cần kéo chung 1 hồ sơ -> gán hồ sơ riêng cho từng kênh.
    Hồ sơ đã riêng của đúng 1 kênh thì giữ nguyên (không mất đăng nhập)."""
    all_jobs = [load(p) for p in glob.glob(os.path.join(JOB_DIR, "*.yaml"))]
    users = {}   # profile_dir -> các mã kênh đang dùng
    for j in all_jobs:
        for k in (("strong_channel",) if j.get("mode") == "self" else ("strong_channel", "weak_channel")):
            ch = j.get(k, {}) or {}
            pd = str(ch.get("profile_dir") or "")
            users.setdefault(pd, set()).add(ch.get("channel_id") or f"?{j['_path']}:{k}")
    changed = []
    for j in all_jobs:
        dirty = False
        if j.get("mode") == "self":   # kéo cho chính kênh: kênh cần kéo dùng chung trình duyệt của chính kênh đó
            s_, w_ = j.setdefault("strong_channel", {}), j.setdefault("weak_channel", {})
            pd = str(s_.get("profile_dir") or "")
            bad = pd in GENERIC_PROFILES or len(users.get(pd, ())) > 1
            if bad and s_.get("channel_id"):
                s_["profile_dir"] = f"profiles/kenh_{s_['channel_id']}"
                changed.append(f"{j.get('job_name')}: {s_.get('name') or s_['channel_id']} → trình duyệt riêng")
            if w_.get("profile_dir") != s_.get("profile_dir") or w_.get("channel_id") != s_.get("channel_id"):
                w_["profile_dir"], w_["channel_id"] = s_.get("profile_dir"), s_.get("channel_id")
                bad = True
            if bad:
                path = j["_path"]
                save(path, j)
            continue
        for who, k in (("strong", "strong_channel"), ("weak", "weak_channel")):
            ch = j.setdefault(k, {})
            pd = str(ch.get("profile_dir") or "")
            other = j.get("weak_channel" if k == "strong_channel" else "strong_channel", {}) or {}
            bad = (pd in GENERIC_PROFILES or len(users.get(pd, ())) > 1
                   or (pd and pd == str(other.get("profile_dir") or "")))
            if bad:
                cid = ch.get("channel_id") or ""
                newp = f"profiles/kenh_{cid}" if cid else \
                    f"profiles/{os.path.splitext(os.path.basename(j['_path']))[0]}_{who}"
                if newp != pd:
                    ch["profile_dir"] = newp
                    users.setdefault(newp, set()).add(cid or f"?{j['_path']}:{k}")
                    dirty = True
                    changed.append(f"{j.get('job_name')}: {'kênh mạnh' if who == 'strong' else 'kênh cần kéo'} "
                                   f"{ch.get('name') or cid} → trình duyệt riêng")
        if dirty:
            path = j.pop("_path")
            save(path, j)
            j["_path"] = path
    if log and changed:
        log("Đã tách trình duyệt riêng cho: " + "; ".join(changed))
    return changed


def migrate():
    """Lần đầu: chuyển config.yaml + videos_to_pull.txt cũ thành kênh số 1 (giữ nguyên đăng nhập cũ)."""
    if glob.glob(os.path.join(JOB_DIR, "*.yaml")):
        return
    os.makedirs(JOB_DIR, exist_ok=True)
    if not os.path.exists(OLD_CONFIG):
        return
    cfg = _read(OLD_CONFIG)
    vids = []
    if os.path.exists(OLD_VIDEOS):
        with open(OLD_VIDEOS, encoding="utf-8") as f:
            vids = [ln.split("#")[0].strip() for ln in f if ln.split("#")[0].strip().startswith("http")]
    cfg.update(job_name=cfg.get("weak_channel", {}).get("name") or "Kênh 1", enabled=True, order=1,
               pull_videos=vids)
    save(os.path.join(JOB_DIR, "kenh_01.yaml"), cfg)
