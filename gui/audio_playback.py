"""跨平台 WAV 预览播放（WSL / Windows / macOS / Linux）。"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path


def play_wav_once(wav_path: Path) -> subprocess.Popen | None:
    """单次播放 WAV。"""
    wav_path = Path(wav_path).resolve()
    from gui.reaper_launch import is_wsl, wsl_to_windows_path

    if is_wsl():
        win_path = wsl_to_windows_path(wav_path)
        return subprocess.Popen(
            [
                "/mnt/c/Windows/System32/WindowsPowerShell/v1.0/powershell.exe",
                "-NoProfile",
                "-Command",
                f"(New-Object System.Media.SoundPlayer '{win_path}').PlaySync()",
            ],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )

    if sys.platform == "win32":
        import winsound

        winsound.PlaySound(str(wav_path), winsound.SND_FILENAME | winsound.SND_ASYNC)
        return None

    for cmd in (
        ["ffplay", "-nodisp", "-loglevel", "quiet", "-autoexit", str(wav_path)],
        ["afplay", str(wav_path)],
    ):
        try:
            return subprocess.Popen(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        except FileNotFoundError:
            continue
    raise FileNotFoundError("未找到 ffplay 或 afplay，无法试听")


def play_wav_loop(wav_path: Path) -> subprocess.Popen | None:
    """循环播放 WAV；返回子进程（Windows winsound 时返回 None）。"""
    wav_path = Path(wav_path).resolve()
    from gui.reaper_launch import is_wsl, wsl_to_windows_path

    if is_wsl():
        win_path = wsl_to_windows_path(wav_path)
        script = (
            f"$p = New-Object System.Media.SoundPlayer '{win_path}'; "
            "$p.PlayLooping(); while($true) { Start-Sleep -Seconds 1 }"
        )
        return subprocess.Popen(
            [
                "/mnt/c/Windows/System32/WindowsPowerShell/v1.0/powershell.exe",
                "-NoProfile",
                "-Command",
                script,
            ],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )

    if sys.platform == "win32":
        import winsound

        winsound.PlaySound(str(wav_path), winsound.SND_FILENAME | winsound.SND_ASYNC | winsound.SND_LOOP)
        return None

    for cmd in (
        ["ffplay", "-nodisp", "-loglevel", "quiet", "-loop", "0", str(wav_path)],
        ["afplay", str(wav_path)],
    ):
        try:
            return subprocess.Popen(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        except FileNotFoundError:
            continue
    raise FileNotFoundError("未找到 ffplay 或 afplay，无法试听")


def stop_wav_playback(proc: subprocess.Popen | None) -> None:
    from gui.reaper_launch import is_wsl

    if is_wsl() and proc is not None:
        try:
            proc.kill()
        except OSError:
            pass
        return

    if sys.platform == "win32":
        import winsound

        winsound.PlaySound(None, winsound.SND_PURGE)
        return

    if proc is not None:
        try:
            proc.kill()
        except OSError:
            pass
