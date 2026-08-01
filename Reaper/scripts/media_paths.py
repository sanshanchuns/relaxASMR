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


def _mnt_is_remote_fs(posix: str) -> bool:
    """路径是否落在 CIFS/SMB/NFS 等远程挂载上（协作机 /mnt/e 常见）。

    远程挂载不能写成 ``E:\\``（Windows 往往没有该盘符），应走
    ``\\\\wsl.localhost\\<distro>\\mnt\\e\\...``，与 WSL 内 ``/mnt/e`` 一一对应。
    """
    try:
        mounts_text = Path("/proc/mounts").read_text(encoding="utf-8")
    except OSError:
        return False

    best_len = -1
    best_remote = False
    for line in mounts_text.splitlines():
        parts = line.split()
        if len(parts) < 3:
            continue
        mnt = parts[1].replace("\\040", " ")
        fstype = parts[2].lower()
        if not (posix == mnt or posix.startswith(mnt.rstrip("/") + "/")):
            continue
        if len(mnt) < best_len:
            continue
        best_len = len(mnt)
        best_remote = fstype in _REMOTE_FS
    return best_remote


def _to_wsl_localhost_unc(posix: str, distro: str) -> str:
    rest = posix[1:].replace("/", "\\") if posix.startswith("/") else posix.replace("/", "\\")
    return f"\\\\wsl.localhost\\{distro}\\{rest}"


def wsl_unc_path(path: Path) -> str:
    """WSL 绝对路径 → Windows Reaper 可读路径。

    - ``/mnt/x/...`` 且为 **drvfs/9p 本机盘** → ``X:\\...``（主机）
    - ``/mnt/x/...`` 且为 **CIFS/NAS** → ``\\\\wsl.localhost\\<distro>\\mnt\\x\\...``
      （协作机：与 WSL 的 ``/mnt/e`` 同路径，不写死 NAS IP，也不误用 ``E:\\``）
    - 其余（如 ``/home/...``）→ ``\\\\wsl.localhost\\<distro>\\...``

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

    m = re.match(r"^/mnt/([a-zA-Z])/(.*)", posix)
    if m and not force_unc and not _mnt_is_remote_fs(posix):
        drive = m.group(1).upper()
        rest = m.group(2).replace("/", "\\")
        return f"{drive}:\\{rest}"

    if posix.startswith("/"):
        return _to_wsl_localhost_unc(posix, distro)
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
