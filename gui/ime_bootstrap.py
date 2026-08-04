"""GUI 启动前配置输入法环境。

WSLg 下 GUI 走 Windows 系统输入法（含微信输入法），由 WSLg 转发；
若误设 ``GTK_IM_MODULE=fcitx`` 会导致中文无法上屏。原生 Linux 才默认 fcitx。
"""

from __future__ import annotations

import os
import sys

_IME_KEYS = ("GTK_IM_MODULE", "XMODIFIERS", "QT_IM_MODULE", "SDL_IM_MODULE")


def is_wsl() -> bool:
    return bool(os.environ.get("WSL_DISTRO_NAME"))


def bootstrap_ime() -> None:
    """须在 ``import tkinter`` 之前调用。"""
    if sys.platform != "linux":
        return
    if is_wsl():
        for key in _IME_KEYS:
            os.environ.pop(key, None)
        return
    os.environ.setdefault("GTK_IM_MODULE", "fcitx")
    os.environ.setdefault("XMODIFIERS", "@im=fcitx")
    os.environ.setdefault("QT_IM_MODULE", "fcitx")
