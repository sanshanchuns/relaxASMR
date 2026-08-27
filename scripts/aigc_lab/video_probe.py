"""视频客观测量：抽帧 + 运动量（ffmpeg）。

慢镜头有客观定义：**相邻帧之间变化小**。抽连续帧算平均绝对差即可区分慢放与实时。
AIGC 验收等模块可复用本工具；业务阈值由调用方决定。
"""

from __future__ import annotations

import shutil
import subprocess
import tempfile
from collections.abc import Callable
from dataclasses import dataclass, field
from pathlib import Path

LogFn = Callable[[str], None]

#: 测运动量用的连续帧数量。8 帧够稳，再多只是变慢。
_MOTION_FRAMES = 8

#: 送去评审的均匀抽帧数量。5s 视频取 4 张足够看出意图，多了浪费 token。
_REVIEW_FRAMES = 4

#: 帧差 → 0–100 分的缩放系数（用真实素材标定过）：
#: 无雨空镜 0.5–1.3、轻雨 2.7–5.1、小雨 4.8–9.1、中雨 8–12、大雨 16.8–19.1。
#: 改这个系数会让依赖该刻度的区间失效。
_MOTION_SCALE = 5.0

#: 比较前把帧缩到这个尺寸：压掉传感器噪点和压缩块效应，只留下真正的运动。
_COMPARE_SIZE = (160, 90)


class VideoProbeError(RuntimeError):
    pass


@dataclass
class VideoProbe:
    """一次视频验收的结果。"""

    motion_score: float
    frames: list[Path] = field(default_factory=list)
    duration_sec: float = 0.0
    ok: bool = True
    issues: list[str] = field(default_factory=list)

    @property
    def summary(self) -> str:
        state = "通过" if self.ok else "不通过"
        return f"运动量 {self.motion_score:.1f}/100 · {state}"


def _ffmpeg() -> str:
    exe = shutil.which("ffmpeg")
    if exe is None:
        raise VideoProbeError("未找到 ffmpeg，无法做视频验收")
    return exe


def _ffprobe_duration(video: Path) -> float:
    exe = shutil.which("ffprobe")
    if exe is None:
        return 0.0
    proc = subprocess.run(
        [
            exe, "-v", "error",
            "-show_entries", "format=duration",
            "-of", "default=noprint_wrappers=1:nokey=1",
            str(video),
        ],
        capture_output=True,
        text=True,
    )
    try:
        return float((proc.stdout or "0").strip())
    except ValueError:
        return 0.0


def _extract(video: Path, out_dir: Path, *, args: list[str]) -> list[Path]:
    pattern = out_dir / "f_%03d.png"
    cmd = [_ffmpeg(), "-y", "-loglevel", "error", *args, str(pattern)]
    proc = subprocess.run(cmd, capture_output=True, text=True)
    if proc.returncode != 0:
        raise VideoProbeError(f"抽帧失败：{(proc.stderr or '').strip()[:300]}")
    return sorted(out_dir.glob("f_*.png"))


def extract_review_frames(video: Path, out_dir: Path, *, count: int = _REVIEW_FRAMES) -> list[Path]:
    """全片均匀抽 *count* 帧，用于送 Gemini 评审。"""
    duration = _ffprobe_duration(video) or 5.0
    frames: list[Path] = []
    for i in range(count):
        # 避开首尾各 10%：首帧就是原图，尾帧常带压缩尾巴。
        at = duration * (0.1 + 0.8 * (i / max(1, count - 1)))
        sub = out_dir / f"r{i:02d}"
        sub.mkdir(parents=True, exist_ok=True)
        got = _extract(video, sub, args=["-ss", f"{at:.2f}", "-i", str(video), "-frames:v", "1"])
        frames.extend(got)
    return frames


@dataclass
class Dynamics:
    """一次抽帧同时得到的三个客观量。"""

    motion_score: float
    #: 相邻帧整体亮度均值的平均跳动（0–255 刻度）。稳定空镜应当接近 0。
    flicker: float
    #: 最大帧差 / 中位帧差。远大于 1 说明片中有硬切或跳帧。
    cut_ratio: float


def measure_dynamics(video: Path) -> Dynamics:
    """取中段连续帧，一次算出运动量、亮度闪烁与跳变比。"""
    from PIL import Image, ImageChops, ImageStat

    duration = _ffprobe_duration(video) or 5.0
    start = max(0.0, duration * 0.35)
    with tempfile.TemporaryDirectory(prefix="probe_motion_") as tmp:
        frames = _extract(
            video,
            Path(tmp),
            args=["-ss", f"{start:.2f}", "-i", str(video), "-frames:v", str(_MOTION_FRAMES)],
        )
        if len(frames) < 2:
            raise VideoProbeError(f"抽帧不足（{len(frames)} 帧），无法测运动量")
        grays = [
            Image.open(p).convert("L").resize(_COMPARE_SIZE, Image.BILINEAR)
            for p in frames
        ]
        diffs = [
            ImageStat.Stat(ImageChops.difference(a, b)).mean[0]
            for a, b in zip(grays, grays[1:])
        ]
        means = [ImageStat.Stat(g).mean[0] for g in grays]

    motion = min(100.0, (sum(diffs) / len(diffs)) * _MOTION_SCALE)
    flicker = sum(abs(b - a) for a, b in zip(means, means[1:])) / max(1, len(means) - 1)
    ordered = sorted(diffs)
    median = ordered[len(ordered) // 2] or 1e-6
    return Dynamics(
        motion_score=motion,
        flicker=flicker,
        cut_ratio=max(diffs) / median,
    )


def measure_motion(video: Path) -> float:
    """取中段连续帧，算相邻帧平均绝对差，映射成 0–100 的运动量。"""
    return measure_dynamics(video).motion_score


def probe_video(
    video: Path,
    *,
    motion_range: tuple[float, float] = (0.0, 100.0),
    frames_dir: Path | None = None,
    log_fn: LogFn | None = None,
) -> VideoProbe:
    """测运动量并按子系列区间判定；``frames_dir`` 非空时顺便抽出评审用帧。"""
    log = log_fn or (lambda _m: None)
    if not video.is_file():
        raise VideoProbeError(f"视频不存在：{video}")

    duration = _ffprobe_duration(video)
    score = measure_motion(video)
    lo, hi = motion_range
    issues: list[str] = []
    if score < lo:
        issues.append(
            f"运动量 {score:.1f} 低于本系列下限 {lo:.0f}：画面偏慢或近乎静止，"
            "多半又出了慢镜头"
        )
    elif score > hi:
        issues.append(
            f"运动量 {score:.1f} 高于本系列上限 {hi:.0f}：可能有抖动、转场或镜头运动"
        )

    frames: list[Path] = []
    if frames_dir is not None:
        frames_dir.mkdir(parents=True, exist_ok=True)
        frames = extract_review_frames(video, frames_dir)

    probe = VideoProbe(
        motion_score=score,
        frames=frames,
        duration_sec=duration,
        ok=not issues,
        issues=issues,
    )
    log(f"[视频验收] {video.name} · {probe.summary}")
    for msg in issues:
        log(f"[视频验收] {msg}")
    return probe
