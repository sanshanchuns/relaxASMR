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


def wav_matches_target_hours(
    path: Path,
    hours: float,
    *,
    tolerance_s: float = DEFAULT_TOLERANCE_S,
) -> bool:
    dur = wav_duration_seconds(path)
    if dur is None:
        return False
    expected = float(hours) * 3600.0
    return abs(dur - expected) <= tolerance_s


def expected_export_wav_path(scene_id: str, hours: float) -> Path:
    from scripts.config.paths import export_dir

    return export_dir() / export_wav_name(scene_id, hours)


def format_duration_short(seconds: float) -> str:
    s = max(0, int(round(seconds)))
    h, rem = divmod(s, 3600)
    m, sec = divmod(rem, 60)
    if h:
        return f"{h}h{m}m" if m else f"{h}h"
    if m:
        return f"{m}m{sec}s" if sec else f"{m}m"
    return f"{sec}s"
