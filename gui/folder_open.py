"""在系统文件管理器中打开目录。"""

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

from gui.reaper_launch import is_wsl, windows_cmd_exe, wsl_to_windows_path


def open_folder(path: Path) -> None:
    """打开文件夹。WSL 下用 Windows 资源管理器。"""
    path = path.resolve()
    if not path.is_dir():
        raise FileNotFoundError(f"找不到目录：{path}")

    if is_wsl():
        win_path = wsl_to_windows_path(path)
        cmd = windows_cmd_exe()
        subprocess.Popen(
            ["/init", str(cmd), "/c", "start", "", win_path],
            start_new_session=True,
            cwd="/mnt/c",
        )
        return

    if sys.platform == "darwin":
        subprocess.Popen(["open", str(path)], start_new_session=True)
    elif sys.platform == "win32":
        os.startfile(str(path))  # noqa: S606
    else:
        subprocess.Popen(["xdg-open", str(path)], start_new_session=True)
