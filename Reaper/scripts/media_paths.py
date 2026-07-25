"""Reaper .rpp 媒体路径：按运行环境自动选择 absolute / wsl_unc。"""

from __future__ import annotations

import os
import re
import sys
from pathlib import Path


def resolve_media_mode(media_mode: str, repo_root: Path | None = None) -> str:
    """auto 检测规则（可用环境变量 RELAXASMR_MEDIA_MODE 覆盖）：

    - macOS                    → absolute
    - Linux 原生（非 WSL）      → absolute
    - WSL 内跑 Python          → wsl_unc（给 Windows Reaper 读 \\wsl.localhost\\...）
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


def wsl_unc_path(path: Path) -> str:
    """WSL 绝对路径 → Windows Reaper 可读路径。

    - ``/mnt/x/...`` → ``X:\\...``（Reaper 对盘符最稳定；4060/5060 主机均适用）
    - 其余（如 ``/home/...`` 仓库）→ ``\\\\wsl.localhost\\<distro>\\...``

    若必须全走 UNC，可设 ``RELAXASMR_MEDIA_WIN_DRIVE=0``。
    """
    distro = os.environ.get("WSL_DISTRO_NAME", "Ubuntu")
    posix = path.resolve().as_posix()

    force_unc = os.environ.get("RELAXASMR_MEDIA_WIN_DRIVE", "").strip().lower() in {
        "0",
        "false",
        "no",
    }
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
