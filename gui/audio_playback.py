"""跨平台 WAV 预览播放（WSL / Windows / macOS / Linux）。

WSL GUI：悬停试听走 Windows SoundPlayer + 16-bit 转码（切换干净，与早期行为一致）。
原生 Linux/macOS：ffplay。
"""

from __future__ import annotations

import hashlib
import os
import signal
import subprocess
import sys
import tempfile
import threading
import time
from pathlib import Path
from shutil import which

_PLAY_LOCK = threading.Lock()
_ACTIVE_PROC: subprocess.Popen | None = None
_ACTIVE_STDIN = None
_S16_CACHE: dict[str, Path] = {}

_POWERSHELL = "/mnt/c/Windows/System32/WindowsPowerShell/v1.0/powershell.exe"
_PROC_WAIT_S = 0.25
_WSL_STOP_GAP_S = 0.02
_FFPLAY_STOP_GAP_S = 0.06
_PREVIEW_CLIP_CACHE: dict[str, Path] = {}
DEFAULT_PREVIEW_CLIP_SEC = 30.0
# 超过此大小（约 3min 立体声 48k/16bit）试听只截取片段，避免 3h 成片卡死
_PREVIEW_CLIP_MIN_BYTES = 48_000 * 2 * 2 * 180


def _spawn_playback(cmd: list[str], *, pipe_stdin: bool = False) -> subprocess.Popen:
    global _ACTIVE_PROC, _ACTIVE_STDIN
    kwargs: dict = {
        "stdout": subprocess.DEVNULL,
        "stderr": subprocess.DEVNULL,
    }
    if pipe_stdin:
        kwargs["stdin"] = subprocess.PIPE
    if sys.platform == "win32":
        kwargs["creationflags"] = subprocess.CREATE_NEW_PROCESS_GROUP  # type: ignore[attr-defined]
    else:
        kwargs["start_new_session"] = True
    proc = subprocess.Popen(cmd, **kwargs)
    _ACTIVE_PROC = proc
    _ACTIVE_STDIN = proc.stdin if pipe_stdin else None
    return proc


def _kill_proc(proc: subprocess.Popen) -> None:
    try:
        if sys.platform == "win32":
            subprocess.run(
                ["taskkill", "/F", "/T", "/PID", str(proc.pid)],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                check=False,
            )
        else:
            os.killpg(os.getpgid(proc.pid), signal.SIGTERM)
    except (OSError, ProcessLookupError, AttributeError):
        try:
            proc.kill()
        except OSError:
            pass


def _wait_proc(proc: subprocess.Popen | None, timeout: float = _PROC_WAIT_S) -> None:
    if proc is None:
        return
    try:
        proc.wait(timeout=timeout)
    except subprocess.TimeoutExpired:
        _kill_proc(proc)
        try:
            proc.wait(timeout=0.12)
        except subprocess.TimeoutExpired:
            pass


def _stop_unlocked(proc: subprocess.Popen | None = None) -> None:
    """在已持有 _PLAY_LOCK 时调用。"""
    global _ACTIVE_PROC, _ACTIVE_STDIN
    target = proc or _ACTIVE_PROC
    _ACTIVE_PROC = None
    stdin = _ACTIVE_STDIN
    _ACTIVE_STDIN = None

    if target is not None and target.poll() is None:
        if stdin is not None:
            try:
                stdin.write(b"q")
                stdin.flush()
            except (OSError, BrokenPipeError, ValueError):
                pass
        _wait_proc(target)

    if sys.platform == "win32":
        import winsound

        winsound.PlaySound(None, winsound.SND_PURGE)


def stop_wav_playback(proc: subprocess.Popen | None = None) -> None:
    """停止当前试听。"""
    with _PLAY_LOCK:
        _stop_unlocked(proc)


def force_stop_all_playback() -> None:
    """应用退出时强制清理。"""
    stop_wav_playback()
    if sys.platform == "darwin":
        return
    if which("ffplay") and (
        sys.platform.startswith("linux") or os.environ.get("WSL_DISTRO_NAME")
    ):
        subprocess.run(
            ["pkill", "-f", "ffplay -nodisp"],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            check=False,
        )


def _wav_bits_per_sample(wav_path: Path) -> int:
    if not which("ffprobe"):
        return 16
    try:
        out = subprocess.check_output(
            [
                "ffprobe",
                "-v",
                "error",
                "-select_streams",
                "a:0",
                "-show_entries",
                "stream=bits_per_sample",
                "-of",
                "default=nw=1:nk=1",
                str(wav_path),
            ],
            text=True,
            stderr=subprocess.DEVNULL,
        ).strip()
        return int(out) if out.isdigit() else 16
    except (subprocess.CalledProcessError, ValueError, OSError):
        return 16


def _wav_for_legacy_player(wav_path: Path) -> Path:
    """SoundPlayer / winsound 仅可靠支持 16-bit PCM。"""
    wav_path = wav_path.resolve()
    if _wav_bits_per_sample(wav_path) <= 16:
        return wav_path
    st = wav_path.stat()
    cache_key = f"{wav_path}:{st.st_mtime_ns}"
    cached = _S16_CACHE.get(cache_key)
    if cached and cached.is_file():
        return cached
    if not which("ffmpeg"):
        return wav_path
    digest = hashlib.md5(cache_key.encode()).hexdigest()[:12]
    tmp = Path(tempfile.gettempdir()) / f"relaxasmr_prev_{digest}.wav"
    subprocess.run(
        [
            "ffmpeg",
            "-y",
            "-loglevel",
            "error",
            "-i",
            str(wav_path),
            "-c:a",
            "pcm_s16le",
            str(tmp),
        ],
        check=True,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    _S16_CACHE[cache_key] = tmp
    return tmp


def wav_preview_clip(
    wav_path: Path,
    max_seconds: float = DEFAULT_PREVIEW_CLIP_SEC,
) -> Path:
    """长混音只截取开头若干秒用于悬停试听（带缓存）。"""
    wav_path = wav_path.resolve()
    if not wav_path.is_file():
        raise FileNotFoundError(wav_path)
    st = wav_path.stat()
    if st.st_size <= _PREVIEW_CLIP_MIN_BYTES:
        return _wav_for_legacy_player(wav_path)

    cache_key = f"{wav_path}:{st.st_mtime_ns}:{max_seconds:.3f}"
    cached = _PREVIEW_CLIP_CACHE.get(cache_key)
    if cached and cached.is_file():
        return cached
    if not which("ffmpeg"):
        return _wav_for_legacy_player(wav_path)

    digest = hashlib.md5(cache_key.encode()).hexdigest()[:12]
    tmp = Path(tempfile.gettempdir()) / f"relaxasmr_clip_{digest}.wav"
    subprocess.run(
        [
            "ffmpeg",
            "-y",
            "-loglevel",
            "error",
            "-ss",
            "0",
            "-t",
            str(max_seconds),
            "-i",
            str(wav_path),
            "-c:a",
            "pcm_s16le",
            str(tmp),
        ],
        check=True,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    _PREVIEW_CLIP_CACHE[cache_key] = tmp
    return tmp


def _play_wsl_soundplayer(wav_path: Path, *, loop: bool) -> subprocess.Popen:
    """WSL：经 Windows SoundPlayer 播放（24-bit 会先转 16-bit）。"""
    from gui.reaper_launch import wsl_to_windows_path

    safe = _wav_for_legacy_player(wav_path)
    win_path = wsl_to_windows_path(safe).replace("'", "''")
    if loop:
        script = (
            f"$p = New-Object System.Media.SoundPlayer '{win_path}'; "
            "$p.PlayLooping(); while($true) { Start-Sleep -Seconds 1 }"
        )
    else:
        script = (
            f"$p = New-Object System.Media.SoundPlayer '{win_path}'; "
            "$p.Play(); while($true) { Start-Sleep -Seconds 1 }"
        )
    return _spawn_playback([_POWERSHELL, "-NoProfile", "-Command", script])


def _start_ffplay(wav_path: Path, *, loop: bool) -> subprocess.Popen | None:
    if not which("ffplay"):
        return None
    if loop:
        args = ["ffplay", "-nodisp", "-loglevel", "quiet", "-loop", "0"]
    else:
        args = ["ffplay", "-nodisp", "-loglevel", "quiet", "-autoexit"]
    args.append(str(wav_path))
    try:
        return _spawn_playback(args, pipe_stdin=True)
    except FileNotFoundError:
        return None


def _play_locked(wav_path: Path, *, loop: bool) -> subprocess.Popen | None:
    wav_path = Path(wav_path).resolve()
    from gui.reaper_launch import is_wsl

    with _PLAY_LOCK:
        _stop_unlocked()

        if is_wsl():
            time.sleep(_WSL_STOP_GAP_S)
            return _play_wsl_soundplayer(wav_path, loop=loop)

        time.sleep(_FFPLAY_STOP_GAP_S)
        proc = _start_ffplay(wav_path, loop=loop)
        if proc is not None:
            return proc

        safe = _wav_for_legacy_player(wav_path)

        if sys.platform == "win32":
            import winsound

            flags = winsound.SND_FILENAME | winsound.SND_ASYNC
            if loop:
                flags |= winsound.SND_LOOP
            winsound.PlaySound(str(safe), flags)
            return None

        if which("afplay"):
            return _spawn_playback(["afplay", str(safe)])

        raise FileNotFoundError("未找到 ffplay 或 afplay，无法试听")


def play_wav_once(wav_path: Path) -> subprocess.Popen | None:
    """单次播放 WAV。"""
    return _play_locked(wav_path, loop=False)


def play_wav_loop(wav_path: Path) -> subprocess.Popen | None:
    """循环播放 WAV。"""
    return _play_locked(wav_path, loop=True)


def play_wav_preview(
    wav_path: Path,
    *,
    max_seconds: float | None = None,
) -> subprocess.Popen | None:
    """悬停试听：播一遍（不循环）。大文件可只播开头片段。"""
    src = wav_path
    if max_seconds is not None:
        src = wav_preview_clip(wav_path, max_seconds=max_seconds)
    return _play_locked(src, loop=False)
