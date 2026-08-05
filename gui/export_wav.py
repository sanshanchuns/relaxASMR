"""导出混音 WAV 时长校验（步骤 4）。"""

from __future__ import annotations

import subprocess
from pathlib import Path

from scripts.config.paths import export_wav_name
from scripts.video_analysis.rain_sound_loop import ffprobe_duration

# 与目标成片时长允许偏差（秒）
DEFAULT_TOLERANCE_S = 30.0


def wav_duration_seconds(path: Path) -> float | None:
    if not path.is_file():
        return None
    try:
        return ffprobe_duration(path)
    except (OSError, ValueError, subprocess.CalledProcessError):
        return None


def wav_matches_target_minutes(
    path: Path,
    minutes: float,
    *,
    tolerance_s: float = DEFAULT_TOLERANCE_S,
) -> bool:
    dur = wav_duration_seconds(path)
    if dur is None:
        return False
    expected = float(minutes) * 60.0
    return abs(dur - expected) <= tolerance_s


def expected_export_wav_path(scene_id: str, minutes: float) -> Path:
    from scripts.config.paths import export_dir

    return export_dir() / export_wav_name(scene_id, minutes)


def export_mp4_belongs_to_scene(
    path: Path,
    scene_id: str,
    *,
    minutes: float | None = None,
) -> bool:
    """成片 MP4 须属于当前场景序号，且文件名含目标时长标记（如 100min）。"""
    if not path.is_file():
        return False
    if scene_id not in path.name:
        return False
    if minutes is not None:
        from scripts.config.paths import duration_render_suffix

        if duration_render_suffix(minutes) not in path.stem:
            return False
    return True


def find_export_mp4_for_scene(
    scene_id: str,
    *,
    minutes: float | None = None,
    export_root: Path | None = None,
) -> Path | None:
    """在 export 目录查找同序号、含目标时长标记的成片 MP4。"""
    import re

    from scripts.config.paths import duration_render_suffix, export_dir

    root = export_root or export_dir()
    if not root.is_dir():
        return None
    match = re.search(r"\d+", scene_id)
    num = match.group() if match else scene_id
    duration_token = duration_render_suffix(minutes) if minutes is not None else None
    candidates: list[Path] = []
    for path in root.glob(f"*{num}*.mp4"):
        if not export_mp4_belongs_to_scene(path, scene_id, minutes=minutes):
            continue
        if duration_token and duration_token not in path.stem:
            continue
        candidates.append(path)
    if not candidates:
        return None
    return max(candidates, key=lambda p: p.stat().st_mtime)


def format_duration_short(seconds: float) -> str:
    s = max(0, int(round(seconds)))
    h, rem = divmod(s, 3600)
    m, sec = divmod(rem, 60)
    if h:
        return f"{h}h{m}m" if m else f"{h}h"
    if m:
        return f"{m}m{sec}s" if sec else f"{m}m"
    return f"{sec}s"


def probe_format_bitrate_bps(path: Path) -> int | None:
    """容器平均码率（含音视频），单位 bps。"""
    if not path.is_file():
        return None
    try:
        proc = subprocess.run(
            [
                "ffprobe",
                "-v",
                "error",
                "-show_entries",
                "format=bit_rate",
                "-of",
                "default=nw=1:nk=1",
                str(path),
            ],
            capture_output=True,
            text=True,
            check=False,
        )
    except OSError:
        return None
    raw = (proc.stdout or "").strip()
    if proc.returncode != 0 or not raw.isdigit():
        return None
    return int(raw)


def format_size_compact_bytes(size: int) -> str:
    if size <= 0:
        return "0"
    gb = size / (1024**3)
    if gb >= 10:
        return f"{int(round(gb))}G"
    if gb >= 1:
        return f"{gb:.1f}G"
    mb = size / (1024**2)
    if mb >= 100:
        return f"{int(round(mb))}M"
    return f"{mb:.0f}M"


def format_mp4_export_stats_suffix(path: Path) -> str:
    """成片状态后缀，如 ' · 6.2 Mbps · 10G'。"""
    if not path.is_file():
        return ""
    parts: list[str] = []
    bps = probe_format_bitrate_bps(path)
    if bps and bps > 0:
        parts.append(f"{bps / 1_000_000:.1f} Mbps")
    size = path.stat().st_size
    if size > 0:
        parts.append(format_size_compact_bytes(size))
    if not parts:
        return ""
    return " · " + " · ".join(parts)
