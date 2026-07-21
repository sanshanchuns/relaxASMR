"""跨平台打开 Reaper 工程 (.rpp)。"""

from __future__ import annotations

import os
import shutil
import subprocess
import sys
import threading
import time
from collections.abc import Callable
from pathlib import Path


def format_hms(seconds: float) -> str:
    s = max(0, int(seconds))
    return f"{s // 3600:02d}:{s % 3600 // 60:02d}:{s % 60:02d}"


def format_job_progress(
    elapsed: float,
    pct: int,
    *,
    tail: bool = False,
    done: bool = False,
) -> str:
    """长任务进度文案；tail=True 表示收尾阶段（faststart / WAV 头写入等）。"""
    if done:
        pct_text = "100%"
        remain_text = "00:00:00"
    elif tail or pct >= 99:
        pct_text = "99%+"
        remain_text = "…"
    elif pct > 0:
        remain = elapsed * (100 - pct) / pct
        pct_text = f"{pct}%"
        remain_text = format_hms(remain)
    else:
        pct_text = "…"
        remain_text = "…"
    return f"Elapsed: {format_hms(elapsed)}  Remaining: ~{remain_text}  ({pct_text})"


def _estimate_wav_data_bytes(duration_sec: float) -> int:
    """48 kHz · stereo · 24-bit PCM 粗估。"""
    return int(duration_sec * 48000 * 2 * 3)


def _poll_render_progress(
    proc: subprocess.Popen,
    *,
    output_wav: Path | None,
    duration_hours: float | None,
    on_progress: Callable[[str], None] | None = None,
    on_pct: Callable[[int], None] | None = None,
    on_tail: Callable[[bool], None] | None = None,
) -> None:
    start = time.monotonic()
    total_sec = float(duration_hours or 0) * 3600
    expected_data = _estimate_wav_data_bytes(total_sec) if total_sec > 0 else 0

    while proc.poll() is None:
        elapsed = time.monotonic() - start
        pct = 0
        tail = False

        if output_wav and output_wav.is_file() and expected_data > 0:
            size = max(0, output_wav.stat().st_size - 44)
            raw_pct = int(size * 100 / expected_data)
            tail = raw_pct >= 99
            pct = min(raw_pct, 100)

        if on_tail:
            on_tail(tail)
        if on_pct:
            on_pct(pct)
        elif on_progress:
            if pct > 0 or (output_wav and output_wav.is_file()):
                on_progress(format_job_progress(elapsed, pct, tail=tail))
            else:
                on_progress(format_job_progress(elapsed, 0))
        time.sleep(1)


def is_wsl() -> bool:
    return bool(os.environ.get("WSL_DISTRO_NAME"))


def wsl_to_windows_path(linux_path: Path) -> str:
    proc = subprocess.run(
        ["wslpath", "-w", str(linux_path.resolve())],
        capture_output=True,
        text=True,
        check=True,
    )
    return proc.stdout.strip()


def windows_cmd_exe() -> Path:
    for candidate in (
        Path("/mnt/c/Windows/System32/cmd.exe"),
        Path(shutil.which("cmd.exe") or ""),
    ):
        if candidate.is_file():
            return candidate
    raise FileNotFoundError("找不到 Windows cmd.exe（WSL 互操作未启用？）")


def windows_explorer_exe() -> Path:
    for candidate in (
        Path("/mnt/c/Windows/explorer.exe"),
        Path(shutil.which("explorer.exe") or ""),
    ):
        if candidate.is_file():
            return candidate
    raise FileNotFoundError("找不到 Windows explorer.exe")


# WSL 下常见 Windows Reaper 安装位置（/mnt/<盘符>/...）
WSL_REAPER_MOUNT_CANDIDATES = (
    "/mnt/d/Program Files/REAPER (x64)/reaper.exe",
    "/mnt/d/Program Files/REAPER/reaper.exe",
    "/mnt/c/Program Files/REAPER (x64)/reaper.exe",
    "/mnt/c/Program Files/REAPER/reaper.exe",
    "/mnt/c/Program Files/Steinberg/Reaper/reaper.exe",
    "/mnt/c/Program Files (x86)/REAPER/reaper.exe",
)


def default_windows_reaper_from_wsl() -> str | None:
    """在 /mnt/<盘符> 下查找 Windows 版 Reaper，返回 Windows 路径。"""
    for w in WSL_REAPER_MOUNT_CANDIDATES:
        p = Path(w)
        if p.is_file():
            return wsl_to_windows_path(p)
    return None


def default_reaper_candidates() -> list[Path]:
    candidates: list[Path] = []
    if is_wsl():
        for w in WSL_REAPER_MOUNT_CANDIDATES:
            p = Path(w)
            if p.is_file():
                candidates.append(p)
        return candidates
    if sys.platform == "darwin":
        candidates.extend(
            [
                Path("/Applications/REAPER.app/Contents/MacOS/REAPER"),
                Path("/Applications/Reaper.app/Contents/MacOS/REAPER"),
            ]
        )
    elif sys.platform == "win32":
        for env in ("ProgramFiles", "ProgramFiles(x86)"):
            base = os.environ.get(env)
            if base:
                candidates.append(Path(base) / "REAPER" / "reaper.exe")
                candidates.append(Path(base) / "Reaper (x64)" / "reaper.exe")
    else:
        for name in ("reaper", "REAPER"):
            found = shutil.which(name)
            if found:
                candidates.append(Path(found))
        candidates.extend(
            [
                Path.home() / "opt" / "REAPER" / "reaper",
                Path("/opt/REAPER/reaper"),
            ]
        )
    return [p for p in candidates if p.is_file()]


def resolve_reaper_exe(explicit: str | None = None) -> Path | str | None:
    if explicit:
        text = explicit.strip()
        if not text:
            pass
        elif is_wsl() and len(text) >= 2 and text[1] == ":":
            return text.replace("/", "\\")
        elif is_wsl() and text.startswith("\\\\"):
            return text
        else:
            p = Path(text).expanduser()
            if p.is_file():
                return p.resolve() if not is_wsl() else wsl_to_windows_path(p)
            if is_wsl() and len(text) >= 2 and text[1] == ":":
                return text.replace("/", "\\")
    if is_wsl():
        return default_windows_reaper_from_wsl()
    found = default_reaper_candidates()
    return found[0] if found else None


def _resolve_linux_reaper_mount(exe: Path | str | None) -> tuple[Path | str, Path | None]:
    """返回 (win 或 path 给 cmd, WSL 下 linux_exe 或 None)。"""
    if not is_wsl():
        if isinstance(exe, Path):
            return exe, exe
        resolved = resolve_reaper_exe(exe if isinstance(exe, str) else None)
        if isinstance(resolved, Path):
            return resolved, resolved
        if resolved:
            return resolved, None
        raise FileNotFoundError("找不到 Reaper 可执行文件")

    win_exe = resolve_reaper_exe(exe if isinstance(exe, str) else None)
    if not win_exe:
        raise FileNotFoundError(
            "找不到 Windows Reaper。请在 GUI 设置中填写 reaper_exe，"
            "或安装到默认路径（如 D:\\Program Files\\REAPER (x64)）。"
        )
    linux_exe: Path | None = None
    if isinstance(exe, Path):
        linux_exe = exe
    else:
        win_text = str(win_exe).lower()
        for mount in WSL_REAPER_MOUNT_CANDIDATES:
            p = Path(mount)
            if p.is_file() and wsl_to_windows_path(p).lower() == win_text:
                linux_exe = p
                break
        if linux_exe is None:
            for mount in WSL_REAPER_MOUNT_CANDIDATES:
                p = Path(mount)
                if p.is_file():
                    linux_exe = p
                    break
    return win_exe, linux_exe


def run_reaper_lua(
    lua: Path,
    *,
    reaper_exe: str | None = None,
    nosplash: bool = True,
) -> None:
    """在单个 Reaper 进程中执行 ReaScript（批量 open + render）。

    Reaper CLI：reaper.exe script.lua（非 -runlua）
    """
    lua = lua.resolve()
    if not lua.is_file():
        raise FileNotFoundError(f"找不到 Lua 脚本：{lua}")

    prefix = ["-nosplash"] if nosplash else []
    win_exe, linux_exe = _resolve_linux_reaper_mount(reaper_exe)
    if is_wsl():
        win_lua = wsl_to_windows_path(lua)
        if linux_exe is None:
            win_exe_str = win_exe if isinstance(win_exe, str) else wsl_to_windows_path(win_exe)
            cmd = " ".join(f'"{x}"' for x in [win_exe_str, *prefix, win_lua])
            proc = subprocess.Popen([str(windows_cmd_exe()), "/c", cmd])
        else:
            proc = subprocess.Popen([str(linux_exe), *prefix, win_lua])
    elif isinstance(win_exe, Path):
        proc = subprocess.Popen([str(win_exe), *prefix, str(lua)])
    else:
        proc = subprocess.Popen([str(win_exe), *prefix, str(lua)])

    rc = proc.wait()
    if rc != 0:
        raise subprocess.CalledProcessError(rc, proc.args)


def _ensure_rpp_full_project_render(rpp: Path, duration_hours: float | None) -> None:
    """渲染前写入 Entire Project，避免工程内 Time Selection 被 -renderproject 采用。"""
    repo = Path(__file__).resolve().parents[1]
    scripts = repo / "Reaper" / "scripts"
    if str(scripts) not in sys.path:
        sys.path.insert(0, str(scripts))
    from generate_subproject import ensure_rpp_full_project_render

    ensure_rpp_full_project_render(rpp, duration_hours=duration_hours)


def render_reaper_project(
    rpp: Path,
    *,
    reaper_exe: str | None = None,
    output_wav: Path | None = None,
    duration_hours: float | None = None,
    on_progress: Callable[[str], None] | None = None,
    on_pct: Callable[[int], None] | None = None,
    on_tail: Callable[[bool], None] | None = None,
) -> None:
    """Headless 渲染 .rpp（WSL 下调用 Windows Reaper）。"""
    rpp = rpp.resolve()
    if not rpp.is_file():
        raise FileNotFoundError(f"找不到工程文件：{rpp}")

    _ensure_rpp_full_project_render(rpp, duration_hours)

    proc: subprocess.Popen | None = None

    if is_wsl():
        win_exe, linux_exe = _resolve_linux_reaper_mount(reaper_exe)
        win_rpp = wsl_to_windows_path(rpp)
        if linux_exe is None:
            win_exe_str = win_exe if isinstance(win_exe, str) else wsl_to_windows_path(win_exe)
            proc = subprocess.Popen(
                [str(windows_cmd_exe()), "/c", f'"{win_exe_str}" -renderproject "{win_rpp}"'],
            )
        else:
            proc = subprocess.Popen([str(linux_exe), "-renderproject", win_rpp])
    else:
        win_exe, linux_exe = _resolve_linux_reaper_mount(reaper_exe)
        if isinstance(win_exe, Path):
            proc = subprocess.Popen([str(win_exe), "-renderproject", str(rpp)])
        elif linux_exe:
            proc = subprocess.Popen([str(linux_exe), "-renderproject", str(rpp)])
        else:
            proc = subprocess.Popen([str(win_exe), "-renderproject", str(rpp)])

    assert proc is not None
    if on_progress or on_pct:
        threading.Thread(
            target=_poll_render_progress,
            args=(proc,),
            kwargs={
                "output_wav": output_wav,
                "duration_hours": duration_hours,
                "on_progress": on_progress,
                "on_pct": on_pct,
                "on_tail": on_tail,
            },
            daemon=True,
        ).start()

    rc = proc.wait()
    if rc != 0:
        raise subprocess.CalledProcessError(rc, proc.args)


def open_reaper_project(rpp: Path, *, reaper_exe: str | None = None) -> None:
    """用 Reaper 打开 .rpp。WSL 下通过 Windows Reaper + UNC 路径，避免 xdg-open 误关联。"""
    rpp = rpp.resolve()
    if not rpp.is_file():
        raise FileNotFoundError(f"找不到工程文件：{rpp}")

    if is_wsl():
        _open_reaper_from_wsl(rpp, reaper_exe)
        return

    exe = resolve_reaper_exe(reaper_exe)
    if isinstance(exe, Path):
        subprocess.Popen([str(exe), str(rpp)], start_new_session=True)
        return

    if sys.platform == "darwin":
        subprocess.Popen(["open", "-a", "REAPER", str(rpp)], start_new_session=True)
    elif sys.platform == "win32":
        os.startfile(str(rpp))  # noqa: S606
    else:
        subprocess.Popen(["xdg-open", str(rpp)], start_new_session=True)


def _open_reaper_from_wsl(rpp: Path, reaper_exe: str | None) -> None:
    win_rpp = wsl_to_windows_path(rpp)
    # Use explorer.exe to open the file. This ensures the process is launched
    # by the Windows Shell at Medium Integrity, preventing Reaper from running
    # as Administrator even if WSL is elevated. This allows drag-and-drop to work.
    explorer = windows_explorer_exe()
    subprocess.Popen(
        [str(explorer), win_rpp],
        start_new_session=True,
        cwd="/mnt/c",
    )
