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
_ACTIVE_PROCS: set[subprocess.Popen] = set()
_PROC_STDINS: dict[int, object] = {}
_FFMPEG_HELPERS: dict[int, subprocess.Popen] = {}
_S16_CACHE: dict[str, Path] = {}

_POWERSHELL = "/mnt/c/Windows/System32/WindowsPowerShell/v1.0/powershell.exe"
_PROC_WAIT_S = 0.25
_WSL_STOP_GAP_S = 0.02
_FFPLAY_STOP_GAP_S = 0.06
_PREVIEW_CLIP_CACHE: dict[str, Path] = {}
DEFAULT_PREVIEW_CLIP_SEC = 30.0
# 超过此大小（约 3min 立体声 48k/16bit）试听只截取片段，避免 3h 成片卡死
_PREVIEW_CLIP_MIN_BYTES = 48_000 * 2 * 2 * 180


def _register_proc(proc: subprocess.Popen, *, stdin: object | None = None) -> None:
    global _ACTIVE_PROC, _ACTIVE_STDIN
    _ACTIVE_PROCS.add(proc)
    _ACTIVE_PROC = proc
    if stdin is not None:
        _PROC_STDINS[proc.pid] = stdin
        _ACTIVE_STDIN = stdin
    else:
        _ACTIVE_STDIN = None


def _unregister_proc(proc: subprocess.Popen) -> None:
    global _ACTIVE_PROC, _ACTIVE_STDIN
    _ACTIVE_PROCS.discard(proc)
    _PROC_STDINS.pop(proc.pid, None)
    if _ACTIVE_PROC is proc:
        _ACTIVE_PROC = next(iter(_ACTIVE_PROCS), None)
        _ACTIVE_STDIN = _PROC_STDINS.get(_ACTIVE_PROC.pid) if _ACTIVE_PROC else None


def _spawn_playback(cmd: list[str], *, pipe_stdin: bool = False) -> subprocess.Popen:
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
    _register_proc(proc, stdin=proc.stdin if pipe_stdin else None)
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


def _stop_pipe_helper(ffplay_proc: subprocess.Popen) -> None:
    helper = _FFMPEG_HELPERS.pop(ffplay_proc.pid, None)
    if helper is not None and helper.poll() is None:
        _kill_proc(helper)
        _wait_proc(helper, timeout=0.12)


def _stop_one_unlocked(proc: subprocess.Popen) -> None:
    """在已持有 _PLAY_LOCK 时停止单路播放。"""
    _stop_pipe_helper(proc)
    stdin = _PROC_STDINS.pop(proc.pid, None)
    _unregister_proc(proc)
    if proc.poll() is None:
        if stdin is not None:
            try:
                stdin.write(b"q")
                stdin.flush()
            except (OSError, BrokenPipeError, ValueError):
                pass
        _wait_proc(proc)


def _stop_all_unlocked() -> None:
    """在已持有 _PLAY_LOCK 时停止全部播放。"""
    global _ACTIVE_PROC, _ACTIVE_STDIN
    procs = list(_ACTIVE_PROCS)
    stdins = dict(_PROC_STDINS)
    helpers = list(_FFMPEG_HELPERS.values())
    _ACTIVE_PROCS.clear()
    _PROC_STDINS.clear()
    _FFMPEG_HELPERS.clear()
    _ACTIVE_PROC = None
    _ACTIVE_STDIN = None
    for proc in procs:
        if proc.poll() is None:
            stdin = stdins.get(proc.pid)
            if stdin is not None:
                try:
                    stdin.write(b"q")
                    stdin.flush()
                except (OSError, BrokenPipeError, ValueError):
                    pass
            _wait_proc(proc)
    for helper in helpers:
        if helper.poll() is None:
            _kill_proc(helper)
            _wait_proc(helper, timeout=0.12)
    if sys.platform == "win32":
        import winsound

        winsound.PlaySound(None, winsound.SND_PURGE)


def _stop_unlocked(proc: subprocess.Popen | None = None) -> None:
    """在已持有 _PLAY_LOCK 时调用。仅停止指定 proc，proc=None 时不做任何事。"""
    if proc is None:
        return
    if proc in _ACTIVE_PROCS:
        _stop_one_unlocked(proc)


def stop_all_wav_playback() -> None:
    """停止全部并发试听（应用退出或显式清空时调用）。"""
    with _PLAY_LOCK:
        _stop_all_unlocked()


def stop_wav_playback(proc: subprocess.Popen | None = None) -> None:
    """停止指定试听进程。"""
    with _PLAY_LOCK:
        _stop_unlocked(proc)


def force_stop_all_playback() -> None:
    """应用退出时强制清理全部并发播放。"""
    stop_all_wav_playback()
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
        subprocess.run(
            ["pkill", "-f", "ffmpeg.*stream_loop"],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            check=False,
        )


def _wav_bits_per_sample(wav_path: Path) -> int:
    from scripts.audio.booms_16bit import wav_bits_per_sample

    return wav_bits_per_sample(wav_path)


def _wav_for_legacy_player(wav_path: Path) -> Path:
    """SoundPlayer / winsound 仅可靠支持 16-bit PCM。"""
    from scripts.audio.booms_16bit import (
        booms_16bit_path_for,
        is_booms_16bit_fresh,
        transcode_wav_to_s16le,
    )

    wav_path = wav_path.resolve()
    if _wav_bits_per_sample(wav_path) <= 16:
        return wav_path
    st = wav_path.stat()
    cache_key = f"{wav_path}:{st.st_mtime_ns}"
    cached = _S16_CACHE.get(cache_key)
    if cached and cached.is_file():
        return cached

    l2 = booms_16bit_path_for(wav_path)
    if l2 is not None:
        if is_booms_16bit_fresh(wav_path, l2):
            _S16_CACHE[cache_key] = l2
            return l2
        if not which("ffmpeg"):
            return wav_path
        try:
            transcode_wav_to_s16le(wav_path, l2)
        except (OSError, subprocess.CalledProcessError):
            pass
        else:
            if l2.is_file():
                _S16_CACHE[cache_key] = l2
                return l2

    if not which("ffmpeg"):
        return wav_path
    digest = hashlib.md5(cache_key.encode()).hexdigest()[:12]
    tmp = Path(tempfile.gettempdir()) / f"relaxasmr_prev_{digest}.wav"
    transcode_wav_to_s16le(wav_path, tmp)
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


def _is_large_wav(wav_path: Path) -> bool:
    """超过约 3 分钟 16-bit 立体声体积的 WAV。"""
    try:
        return wav_path.stat().st_size > _PREVIEW_CLIP_MIN_BYTES
    except OSError:
        return False


def _probe_wav_pcm(wav_path: Path) -> tuple[int, int]:
    """读取 WAV 采样率与声道数，供 raw PCM 管道播放使用。"""
    import wave

    try:
        with wave.open(str(wav_path), "rb") as wf:
            return wf.getframerate(), wf.getnchannels()
    except wave.Error:
        pass
    ffprobe = which("ffprobe")
    if not ffprobe:
        return 48_000, 2
    try:
        out = subprocess.check_output(
            [
                ffprobe,
                "-v",
                "error",
                "-select_streams",
                "a:0",
                "-show_entries",
                "stream=sample_rate,channels",
                "-of",
                "csv=p=0:s=x",
                str(wav_path),
            ],
            stderr=subprocess.DEVNULL,
            text=True,
        ).strip()
        rate_s, ch_s = out.split("x", 1)
        return int(rate_s), int(ch_s)
    except (OSError, subprocess.CalledProcessError, ValueError):
        return 48_000, 2


def _start_ffplay_pipe(
    wav_path: Path,
    *,
    loop: bool,
) -> subprocess.Popen | None:
    """大 WAV：ffmpeg 解码 raw PCM → ffplay，读盘与播放解耦，适合 NAS 巨型混音文件。"""
    ffmpeg_bin = which("ffmpeg")
    ffplay_bin = which("ffplay")
    if not ffmpeg_bin or not ffplay_bin:
        return None

    sample_rate, channels = _probe_wav_pcm(wav_path)
    ff_cmd = [
        ffmpeg_bin,
        "-nostdin",
        "-hide_banner",
        "-loglevel",
        "error",
        "-thread_queue_size",
        "8192",
        "-i",
        str(wav_path.resolve()),
        "-f",
        "s16le",
        "-acodec",
        "pcm_s16le",
        "pipe:1",
    ]
    if loop:
        i_idx = ff_cmd.index("-i")
        ff_cmd[i_idx:i_idx] = ["-stream_loop", "-1"]
    play_cmd = [
        ffplay_bin,
        "-nodisp",
        "-loglevel",
        "quiet",
        "-f",
        "s16le",
        "-ar",
        str(sample_rate),
        "-ac",
        str(channels),
        "-i",
        "pipe:0",
        "-sync",
        "audio",
        "-af",
        "aresample=async=1:first_pts=0",
    ]
    if not loop:
        play_cmd.append("-autoexit")
    kwargs: dict = {"stderr": subprocess.DEVNULL, "start_new_session": True}
    if sys.platform == "win32":
        kwargs["creationflags"] = subprocess.CREATE_NEW_PROCESS_GROUP  # type: ignore[attr-defined]

    ffmpeg_proc = subprocess.Popen(ff_cmd, stdout=subprocess.PIPE, **kwargs)
    play_kwargs = {
        "stdin": ffmpeg_proc.stdout,
        "stdout": subprocess.DEVNULL,
        "stderr": subprocess.DEVNULL,
        "start_new_session": True,
    }
    if sys.platform == "win32":
        play_kwargs["creationflags"] = subprocess.CREATE_NEW_PROCESS_GROUP  # type: ignore[attr-defined]
    ffplay_proc = subprocess.Popen(play_cmd, **play_kwargs)
    if ffmpeg_proc.stdout is not None:
        ffmpeg_proc.stdout.close()
    _register_proc(ffplay_proc)
    _FFMPEG_HELPERS[ffplay_proc.pid] = ffmpeg_proc
    return ffplay_proc


def _start_ffplay(wav_path: Path, *, loop: bool) -> subprocess.Popen | None:
    if not which("ffplay"):
        return None
    args = ["ffplay", "-nodisp", "-loglevel", "quiet"]
    if loop:
        args.extend(["-loop", "0", "-sync", "audio"])
    else:
        args.extend(["-autoexit", "-sync", "audio"])
    args.append(str(wav_path))
    try:
        return _spawn_playback(args, pipe_stdin=True)
    except FileNotFoundError:
        return None


def _start_large_wav(wav_path: Path, *, loop: bool) -> subprocess.Popen | None:
    """大 WAV：优先 ffmpeg 管道流式（NAS 友好），失败时回退 ffplay 直读。"""
    proc = _start_ffplay_pipe(wav_path, loop=loop)
    if proc is not None:
        return proc
    return _start_ffplay(wav_path, loop=loop)


def _launch_wav_legacy(wav_path: Path, *, loop: bool) -> subprocess.Popen | None:
    """WSL SoundPlayer / winsound / afplay，不经过 ffplay（混音片段循环试听）。"""
    wav_path = Path(wav_path).resolve()
    from gui.reaper_launch import is_wsl

    if is_wsl():
        return _play_wsl_soundplayer(wav_path, loop=loop)

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

    raise FileNotFoundError("未找到 SoundPlayer / winsound / afplay，无法试听混音片段")


def _start_locked_legacy(wav_path: Path, *, loop: bool) -> subprocess.Popen | None:
    with _PLAY_LOCK:
        return _launch_wav_legacy(wav_path, loop=loop)


def _launch_wav(wav_path: Path, *, loop: bool) -> subprocess.Popen | None:
    wav_path = Path(wav_path).resolve()
    from gui.reaper_launch import is_wsl

    # 大体积 WAV 走 ffmpeg→ffplay 管道，避免 ffplay 直读 NAS 巨型文件约 1min 后卡顿
    if _is_large_wav(wav_path):
        proc = _start_large_wav(wav_path, loop=loop)
        if proc is not None:
            return proc
        raise FileNotFoundError("大体积 WAV 需要 ffplay（ffmpeg）流式播放，请安装后重试")

    if is_wsl():
        return _play_wsl_soundplayer(wav_path, loop=loop)

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


def _play_locked(wav_path: Path, *, loop: bool) -> subprocess.Popen | None:
    from gui.reaper_launch import is_wsl

    with _PLAY_LOCK:
        _stop_all_unlocked()
        if is_wsl():
            time.sleep(_WSL_STOP_GAP_S)
        else:
            time.sleep(_FFPLAY_STOP_GAP_S)
        return _launch_wav(wav_path, loop=loop)


def _start_locked(wav_path: Path, *, loop: bool) -> subprocess.Popen | None:
    """启动播放，不中断其他正在播放的流。"""
    with _PLAY_LOCK:
        return _launch_wav(wav_path, loop=loop)


def start_wav_once(wav_path: Path) -> subprocess.Popen | None:
    """单次播放 WAV，与其他并发流叠加。"""
    return _start_locked(wav_path, loop=False)


def play_wav_once(wav_path: Path) -> subprocess.Popen | None:
    """单次播放 WAV。"""
    return _play_locked(wav_path, loop=False)


def play_wav_loop(wav_path: Path) -> subprocess.Popen | None:
    """循环播放 WAV（独占，会先停止其他试听）。"""
    return _play_locked(wav_path, loop=True)


def start_wav_loop(wav_path: Path) -> subprocess.Popen | None:
    """循环播放 WAV，与其他并发流叠加。"""
    return _start_locked(wav_path, loop=True)


def start_wav_clip_loop(
    wav_path: Path,
    *,
    max_seconds: float,
) -> subprocess.Popen | None:
    """截取开头片段并循环播放（SoundPlayer 路径，不走 ffplay）。"""
    src = wav_preview_clip(wav_path, max_seconds=max_seconds)
    return _start_locked_legacy(src, loop=True)


def play_wav_preview(
    wav_path: Path,
    *,
    max_seconds: float | None = None,
    loop: bool = False,
) -> subprocess.Popen | None:
    """悬停试听。大文件可只播开头片段；loop=True 时循环该片段。"""
    src = wav_path
    if max_seconds is not None:
        src = wav_preview_clip(wav_path, max_seconds=max_seconds)
    return _play_locked(src, loop=loop)


def start_wav_preview_loop(
    wav_path: Path,
    *,
    max_seconds: float | None = None,
) -> subprocess.Popen | None:
    """悬停循环试听，与其他并发流叠加。"""
    src = wav_path
    if max_seconds is not None:
        src = wav_preview_clip(wav_path, max_seconds=max_seconds)
    return _start_locked(src, loop=True)


def start_media_audio_loop(media_path: Path) -> subprocess.Popen | None:
    """循环播放视频/音频文件的音轨（无画面）。

    供 OpenCV 画布预览旁路出声；``-vn`` 跳过视频解码以省 CPU。
    需要系统有 ``ffplay``；找不到则静默返回 None。
    """
    path = Path(media_path).resolve()
    if not path.is_file() or not which("ffplay"):
        return None
    args = [
        "ffplay",
        "-nodisp",
        "-vn",
        "-loglevel",
        "quiet",
        "-loop",
        "0",
        "-sync",
        "audio",
        str(path),
    ]
    try:
        with _PLAY_LOCK:
            return _spawn_playback(args, pipe_stdin=True)
    except FileNotFoundError:
        return None
