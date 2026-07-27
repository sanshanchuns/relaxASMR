"""Reaper .rpp 媒体路径：按运行环境自动选择 absolute / wsl_unc。"""

from __future__ import annotations

import os
import re
import sys
from pathlib import Path

_REMOTE_FS = frozenset({"cifs", "smb3", "smb", "nfs", "nfs4"})


def resolve_media_mode(media_mode: str, repo_root: Path | None = None) -> str:
    """auto 检测规则（可用环境变量 RELAXASMR_MEDIA_MODE 覆盖）：

    - macOS                    → absolute
    - Linux 原生（非 WSL）      → absolute
    - WSL 内跑 Python          → wsl_unc（给 Windows Reaper 读）
    - Windows + 仓库在 WSL UNC → wsl_unc
    - Windows + 仓库在本机盘符 → absolute
    """
    env_override = os.environ.get("RELAXASMR_MEDIA_MODE", "").strip()
    if media_mode == "auto" and env_override:
        return env_override
    if media_mode != "auto":
        return media_mode

    if sys.platform == "darwin":
        return "absolute"

    if sys.platform == "win32":
        if repo_root is not None:
            root = str(repo_root.resolve())
            if root.startswith("\\\\wsl.localhost") or root.startswith("\\\\wsl$"):
                return "wsl_unc"
            if re.match(r"^[A-Za-z]:[\\/]", root):
                return "absolute"
        return "wsl_unc"

    if os.environ.get("WSL_DISTRO_NAME"):
        return "wsl_unc"

    return "absolute"


def _cifs_windows_unc(posix: str) -> str | None:
    """若路径落在 CIFS/SMB/NFS 挂载下，返回 Windows UNC（\\\\server\\share\\...）。

    协作机常见：``/mnt/e`` → ``//192.168.3.128/e``（cifs），不能写成 ``E:\\``，
    因为 Windows Reaper 侧往往没有同名盘符。
    """
    try:
        mounts_text = Path("/proc/mounts").read_text(encoding="utf-8")
    except OSError:
        return None

    best_len = -1
    best: tuple[str, str] | None = None  # (mount_point, //server/share)
    for line in mounts_text.splitlines():
        parts = line.split()
        if len(parts) < 3:
            continue
        src = parts[0].replace("\\040", " ")
        mnt = parts[1].replace("\\040", " ")
        fstype = parts[2].lower()
        if fstype not in _REMOTE_FS:
            continue
        if not (posix == mnt or posix.startswith(mnt.rstrip("/") + "/")):
            continue
        if not src.startswith("//"):
            continue
        if len(mnt) > best_len:
            best_len = len(mnt)
            best = (mnt, src)

    if best is None:
        return None
    mnt, src = best
    unc_root = "\\\\" + src[2:].replace("/", "\\")
    rel = posix[len(mnt) :].lstrip("/")
    if not rel:
        return unc_root
    return unc_root + "\\" + rel.replace("/", "\\")


def wsl_unc_path(path: Path) -> str:
    """WSL 绝对路径 → Windows Reaper 可读路径。

    - ``/mnt/x/...`` 且为 **drvfs/9p 本机盘** → ``X:\\...``（主机最稳）
    - ``/mnt/x/...`` 且为 **CIFS/NAS** → ``\\\\server\\share\\...``（协作机）
    - 其余（如 ``/home/...`` 仓库）→ ``\\\\wsl.localhost\\<distro>\\...``

    强制全走 WSL UNC：``RELAXASMR_MEDIA_WIN_DRIVE=0``。
    """
    distro = os.environ.get("WSL_DISTRO_NAME", "Ubuntu")
    try:
        posix = path.resolve().as_posix()
    except OSError:
        posix = path.as_posix()

    force_unc = os.environ.get("RELAXASMR_MEDIA_WIN_DRIVE", "").strip().lower() in {
        "0",
        "false",
        "no",
    }

    # NAS/CIFS：优先写成局域网 UNC，避免误用协作机上不存在的 E:
    if not force_unc:
        nas_unc = _cifs_windows_unc(posix)
        if nas_unc is not None:
            return nas_unc

    m = re.match(r"^/mnt/([a-zA-Z])/(.*)", posix)
    if m and not force_unc:
        drive = m.group(1).upper()
        rest = m.group(2).replace("/", "\\")
        return f"{drive}:\\{rest}"

    if posix.startswith("/"):
        rest = posix[1:].replace("/", "\\")
        return f"\\\\wsl.localhost\\{distro}\\{rest}"
    return posix.replace("/", "\\")


def media_path_for_rpp(asset: Path, rpp_dir: Path, path_mode: str, repo_root: Path | None = None) -> str:
    """RPP 内 FILE 路径。"""
    asset = asset.resolve()
    rpp_dir = rpp_dir.resolve()
    mode = resolve_media_mode(path_mode, repo_root)

    if mode == "wsl_unc":
        return wsl_unc_path(asset)
    if mode == "absolute":
        return asset.as_posix()
    # relative
    return os.path.relpath(asset, rpp_dir).replace("/", "\\")


def describe_media_mode(media_mode: str, repo_root: Path | None = None) -> str:
    resolved = resolve_media_mode(media_mode, repo_root)
    if media_mode == "auto":
        return f"{resolved} (auto)"
    return resolved
