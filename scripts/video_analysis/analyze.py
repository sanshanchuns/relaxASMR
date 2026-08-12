#!/usr/bin/env python3
"""分析循环视频首帧，匹配 baseURL/audio 声音库素材维度。

工作流:
  1. ffmpeg 提取首帧
  2. CLIP / VLM 分析画面特征
  3. 映射到声音库维度标签，匹配 audio/1_rain/sounds/*.wav
  4. 输出分析报告与候选列表

用法:
  python3 -m scripts.video_analysis.analyze <video_path>
"""

from __future__ import annotations

import argparse
import re
import shutil
import subprocess
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable

from scripts.config.common_constants import DISTANT_NAMES, SPACE_NAMES, CLOSE_NAMES
from scripts.config.paths import ffmpeg_exe


def _layer_label(l_val: int, names: dict[int, tuple[str, str]]) -> str:
    """Format a layer as ``中文名 English(l_value)``."""
    if l_val in names:
        en, cn = names[l_val]
        return f"{cn} {en}"
    return f"Unknown({l_val})"


# ---------------------------------------------------------------------------
# Scene presets — complete .rain parameter sets
# ---------------------------------------------------------------------------
# All parameter values are 0.0–1.0 (matching .rain XML format).
# Derived from analysis of 25 official presets' parameter patterns.

@dataclass
class ScenePreset:
    """A named scene with complete RAIN VST parameters."""

    name_cn: str
    name_en: str
    # Layer selection (real internal IDs)
    l1: int       # Distant layer
    l2: int       # Space layer
    l3: int       # Close layer
    adv: int      # Advanced mode (0 or 1)
    # --- Distant layer (bg prefix) ---
    bgwi: float   # Width
    bgpn: float   # Pan (0.5 = center)
    bgeq1x: float  # Mass
    bgeq1y: float  # Strength
    bgeq2x: float  # EQ Band 2
    bgeq2y: float  # Presence
    bgeq3x: float  # EQ Band 3
    bgeq3y: float  # EQ Band 3
    # --- Space layer (sp prefix) ---
    spbl: float   # Blend
    spwi: float   # Width
    sppn: float   # Pan
    # --- Close layer (su prefix) ---
    sucd: float   # Drops
    suwi: float   # Width
    supn: float   # Pan
    # --- Rainfall core (rf prefix) ---
    rfdn: float   # Density
    rfin: float   # Intensity
    rffc: float   # Wetness
    rfch: float   # Distance (higher = closer)
    # --- Rainfall tonality (eq prefix) ---
    eq1x: float   # Mass
    eq1y: float   # Strength
    eq2x: float   # EQ Band 2
    eq2y: float   # Presence
    eq3x: float   # EQ Band 3
    eq3y: float   # EQ Band 3
    # --- Global (gl prefix) ---
    glgn: float   # Volume
    glhp: float   # High Pass
    gllp: float   # Low Pass
    glon: float   # Smart
    gldr: float   # Enable


SCENE_PRESETS: dict[str, ScenePreset] = {
    "forest": ScenePreset(
        "森林细雨", "Deep Forest Drizzle",
        l1=100, l2=530, l3=810, adv=0,
        bgwi=0.80, bgpn=0.5,
        bgeq1x=0.52, bgeq1y=0.42, bgeq2x=0.52, bgeq2y=0.55,
        bgeq3x=0.62, bgeq3y=0.55,
        spbl=0.48, spwi=0.75, sppn=0.5,
        sucd=0.15, suwi=0.50, supn=0.5,
        rfdn=0.42, rfin=0.18, rffc=0.68, rfch=0.15,
        eq1x=0.60, eq1y=0.50, eq2x=0.52, eq2y=0.50,
        eq3x=0.52, eq3y=0.62,
        glgn=0.251, glhp=0.0, gllp=0.04, glon=1.0, gldr=1.0,
    ),
    "lake": ScenePreset(
        "湖畔轻雨", "Lakeside Light Rain",
        l1=230, l2=590, l3=850, adv=0,
        bgwi=0.72, bgpn=0.48,
        bgeq1x=0.58, bgeq1y=0.49, bgeq2x=0.42, bgeq2y=0.62,
        bgeq3x=0.52, bgeq3y=0.38,
        spbl=0.55, spwi=0.65, sppn=0.52,
        sucd=0.18, suwi=0.35, supn=0.52,
        rfdn=0.46, rfin=0.25, rffc=0.65, rfch=0.20,
        eq1x=0.78, eq1y=0.58, eq2x=0.65, eq2y=0.52,
        eq3x=0.55, eq3y=0.62,
        glgn=0.251, glhp=0.05, gllp=0.04, glon=1.0, gldr=1.0,
    ),
    "garden": ScenePreset(
        "花园雨景", "Garden Rain",
        l1=110, l2=590, l3=870, adv=0,
        bgwi=0.75, bgpn=0.5,
        bgeq1x=0.52, bgeq1y=0.42, bgeq2x=0.55, bgeq2y=0.50,
        bgeq3x=0.65, bgeq3y=0.52,
        spbl=0.58, spwi=0.55, sppn=0.5,
        sucd=0.20, suwi=0.45, supn=0.5,
        rfdn=0.50, rfin=0.40, rffc=0.62, rfch=0.25,
        eq1x=0.68, eq1y=0.55, eq2x=0.55, eq2y=0.52,
        eq3x=0.58, eq3y=0.58,
        glgn=0.251, glhp=0.0, gllp=0.05, glon=1.0, gldr=1.0,
    ),
    "bamboo": ScenePreset(
        "竹林雨声", "Bamboo Grove Rain",
        l1=110, l2=590, l3=920, adv=1,
        bgwi=0.65, bgpn=0.5,
        bgeq1x=0.55, bgeq1y=0.35, bgeq2x=0.48, bgeq2y=0.45,
        bgeq3x=0.72, bgeq3y=0.52,
        spbl=0.55, spwi=0.58, sppn=0.5,
        sucd=0.32, suwi=0.42, supn=0.5,
        rfdn=0.48, rfin=0.18, rffc=0.62, rfch=0.38,
        eq1x=0.68, eq1y=0.55, eq2x=0.52, eq2y=0.48,
        eq3x=0.58, eq3y=0.62,
        glgn=0.251, glhp=0.0, gllp=0.05, glon=1.0, gldr=1.0,
    ),
    "night": ScenePreset(
        "夜间雨林", "Night Forest Rain",
        l1=170, l2=530, l3=810, adv=0,
        bgwi=0.85, bgpn=0.5,
        bgeq1x=0.72, bgeq1y=0.62, bgeq2x=0.55, bgeq2y=0.68,
        bgeq3x=0.48, bgeq3y=0.55,
        spbl=0.50, spwi=0.72, sppn=0.5,
        sucd=0.10, suwi=0.45, supn=0.5,
        rfdn=0.55, rfin=0.35, rffc=0.72, rfch=0.12,
        eq1x=0.65, eq1y=0.58, eq2x=0.62, eq2y=0.55,
        eq3x=0.55, eq3y=0.62,
        glgn=0.251, glhp=0.0, gllp=0.08, glon=1.0, gldr=1.0,
    ),
    "stream": ScenePreset(
        "溪流雨声", "Forest Stream Rain",
        l1=150, l2=590, l3=850, adv=0,
        bgwi=0.78, bgpn=0.5,
        bgeq1x=0.62, bgeq1y=0.52, bgeq2x=0.48, bgeq2y=0.58,
        bgeq3x=0.55, bgeq3y=0.45,
        spbl=0.52, spwi=0.68, sppn=0.5,
        sucd=0.22, suwi=0.48, supn=0.5,
        rfdn=0.45, rfin=0.22, rffc=0.65, rfch=0.35,
        eq1x=0.72, eq1y=0.55, eq2x=0.58, eq2y=0.52,
        eq3x=0.52, eq3y=0.58,
        glgn=0.251, glhp=0.0, gllp=0.04, glon=1.0, gldr=1.0,
    ),
    "path": ScenePreset(
        "草地公园小径", "Grass Park Path Rain",
        l1=140, l2=530, l3=870, adv=0,
        bgwi=0.72, bgpn=0.5,
        bgeq1x=0.55, bgeq1y=0.45, bgeq2x=0.55, bgeq2y=0.48,
        bgeq3x=0.58, bgeq3y=0.52,
        spbl=0.52, spwi=0.62, sppn=0.5,
        sucd=0.18, suwi=0.52, supn=0.5,
        rfdn=0.48, rfin=0.30, rffc=0.58, rfch=0.28,
        eq1x=0.65, eq1y=0.52, eq2x=0.55, eq2y=0.50,
        eq3x=0.55, eq3y=0.55,
        glgn=0.251, glhp=0.0, gllp=0.04, glon=1.0, gldr=1.0,
    ),
    "canopy": ScenePreset(
        "密林树冠", "Dense Canopy Rain",
        l1=100, l2=530, l3=900, adv=1,
        bgwi=0.85, bgpn=0.52,
        bgeq1x=0.65, bgeq1y=0.55, bgeq2x=0.55, bgeq2y=0.48,
        bgeq3x=0.72, bgeq3y=0.58,
        spbl=0.78, spwi=0.82, sppn=0.48,
        sucd=0.08, suwi=0.35, supn=0.5,
        rfdn=0.52, rfin=0.32, rffc=0.78, rfch=0.10,
        eq1x=0.75, eq1y=0.58, eq2x=0.62, eq2y=0.55,
        eq3x=0.45, eq3y=0.48,
        glgn=0.251, glhp=0.05, gllp=0.05, glon=1.0, gldr=1.0,
    ),
    "open": ScenePreset(
        "开阔雨景", "Open Field Rain",
        l1=240, l2=590, l3=870, adv=0,
        bgwi=0.92, bgpn=0.5,
        bgeq1x=0.55, bgeq1y=0.50, bgeq2x=0.58, bgeq2y=0.52,
        bgeq3x=0.55, bgeq3y=0.48,
        spbl=0.65, spwi=0.78, sppn=0.5,
        sucd=0.12, suwi=0.55, supn=0.5,
        rfdn=0.55, rfin=0.45, rffc=0.52, rfch=0.15,
        eq1x=0.72, eq1y=0.58, eq2x=0.55, eq2y=0.55,
        eq3x=0.62, eq3y=0.55,
        glgn=0.251, glhp=0.0, gllp=0.0, glon=1.0, gldr=1.0,
    ),
    "shelter": ScenePreset(
        "窗前听雨", "Sheltered Rain",
        l1=230, l2=500, l3=820, adv=1,
        bgwi=0.70, bgpn=0.5,
        bgeq1x=0.50, bgeq1y=0.45, bgeq2x=0.55, bgeq2y=0.50,
        bgeq3x=0.60, bgeq3y=0.50,
        spbl=0.40, spwi=0.60, sppn=0.5,
        sucd=0.15, suwi=0.40, supn=0.5,
        rfdn=0.55, rfin=0.35, rffc=0.50, rfch=0.10,
        eq1x=0.60, eq1y=0.50, eq2x=0.55, eq2y=0.48,
        eq3x=0.58, eq3y=0.55,
        glgn=0.251, glhp=0.10, gllp=0.20, glon=1.0, gldr=1.0,
    ),
    "default": ScenePreset(
        "自然雨景", "Natural Rain",
        l1=100, l2=590, l3=810, adv=0,
        bgwi=0.75, bgpn=0.5,
        bgeq1x=0.52, bgeq1y=0.45, bgeq2x=0.52, bgeq2y=0.52,
        bgeq3x=0.58, bgeq3y=0.52,
        spbl=0.55, spwi=0.65, sppn=0.5,
        sucd=0.15, suwi=0.48, supn=0.5,
        rfdn=0.48, rfin=0.28, rffc=0.65, rfch=0.20,
        eq1x=0.65, eq1y=0.52, eq2x=0.55, eq2y=0.52,
        eq3x=0.55, eq3y=0.55,
        glgn=0.251, glhp=0.0, gllp=0.04, glon=1.0, gldr=1.0,
    ),
}

# ---------------------------------------------------------------------------
# Frame analysis data structures
# ---------------------------------------------------------------------------

@dataclass
class RegionAnalysis:
    """Analysis of a horizontal 1/3 region of the frame."""

    label: str
    brightness: float = 0.0
    green_pct: float = 0.0
    brown_pct: float = 0.0
    blue_pct: float = 0.0
    dark_pct: float = 0.0
    description: str = ""


@dataclass
class FrameAnalysis:
    """Complete analysis of the first frame."""

    brightness: float = 0.0
    green_pct: float = 0.0
    brown_pct: float = 0.0
    blue_pct: float = 0.0
    dark_pct: float = 0.0
    sky_pct: float = 0.0
    vertical_lines: float = 0.0
    horizontal_lines: float = 0.0
    smooth_areas: float = 0.0
    water_detected: bool = False
    water_score: float = 0.0
    foliage_density: float = 0.0
    top: RegionAnalysis = field(default_factory=lambda: RegionAnalysis("上层"))
    mid: RegionAnalysis = field(default_factory=lambda: RegionAnalysis("中层"))
    bot: RegionAnalysis = field(default_factory=lambda: RegionAnalysis("下层"))
    scene_type: str = "default"
    scene_description: str = ""

    # Inferred reasoning fields
    rain_level: str = "medium"
    rain_level_reason: str = ""
    distance_level: str = "medium"
    distance_reason: str = ""
    wetness_desc: str = ""
    wetness_reason: str = ""
    tonality_desc: str = ""
    tonality_reason: str = ""


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

_MVI_RE = re.compile(r"(MVI_\d+)", re.IGNORECASE)


def extract_video_id(video_path: Path) -> str:
    """Extract MVI_xxxx from filenames like ``MVI_6952_loop_0.94_dur_6_fade_0.5_01.mp4``.

    Falls back to the full stem if no MVI pattern is found.
    """
    m = _MVI_RE.search(video_path.stem)
    return m.group(1) if m else video_path.stem


def _notify(on_progress: Callable[[str], None] | None, msg: str) -> None:
    if on_progress is not None:
        on_progress(msg)


# ---------------------------------------------------------------------------
# Step 1: Extract first frame
# ---------------------------------------------------------------------------

def extract_first_frame(
    video_path: Path,
    output_path: Path,
    on_progress: Callable[[str], None] | None = None,
) -> Path:
    """Extract the first frame of *video_path* using ffmpeg and save as PNG."""
    _notify(on_progress, f"正在提取首帧: {video_path.name}")
    output_path.parent.mkdir(parents=True, exist_ok=True)

    cmd = [
        str(ffmpeg_exe()), "-i", str(video_path),
        "-vf", "select=eq(n\\,0),scale=1280:720",
        "-vframes", "1",
        "-q:v", "2",
        "-y", str(output_path),
    ]
    try:
        subprocess.run(
            cmd,
            check=True,
            capture_output=True,
            timeout=30,
        )
    except FileNotFoundError:
        raise RuntimeError("ffmpeg 未安装或不在 PATH 中（Mac 可运行: brew install ffmpeg）") from None
    except subprocess.CalledProcessError as exc:
        raise RuntimeError(
            f"ffmpeg 提取首帧失败: {exc.stderr.decode(errors='replace')}"
        ) from exc

    if not output_path.is_file():
        raise RuntimeError(f"ffmpeg 未能生成输出文件: {output_path}")

    _notify(on_progress, f"首帧已保存: {output_path.name}")
    return output_path


# ---------------------------------------------------------------------------
# Step 2: Analyze frame with OpenCV
# ---------------------------------------------------------------------------

def _import_cv2():
    """Import cv2 with a helpful error message if unavailable."""
    try:
        import cv2  # type: ignore[import-untyped]
        return cv2
    except ImportError:
        raise RuntimeError(
            "OpenCV (cv2) 未安装。请运行: pip install opencv-python-headless"
        ) from None


def _import_numpy():
    """Import numpy with a helpful error message if unavailable."""
    try:
        import numpy as np  # type: ignore[import-untyped]
        return np
    except ImportError:
        raise RuntimeError(
            "NumPy 未安装。请运行: pip install numpy"
        ) from None


def _color_percentages(hsv, np):
    """Compute color distribution percentages from an HSV image array."""
    h, s, v = hsv[:, :, 0], hsv[:, :, 1], hsv[:, :, 2]
    total = float(h.size)

    # Green: H 35-85, S > 40, V > 40
    green_mask = (h >= 35) & (h <= 85) & (s > 40) & (v > 40)
    green_pct = float(np.count_nonzero(green_mask)) / total * 100

    # Brown: H 10-25, S > 30, V 30-180
    brown_mask = (h >= 10) & (h <= 25) & (s > 30) & (v >= 30) & (v <= 180)
    brown_pct = float(np.count_nonzero(brown_mask)) / total * 100

    # Blue: H 90-130, S > 30, V > 40
    blue_mask = (h >= 90) & (h <= 130) & (s > 30) & (v > 40)
    blue_pct = float(np.count_nonzero(blue_mask)) / total * 100

    # Dark: V < 60
    dark_mask = v < 60
    dark_pct = float(np.count_nonzero(dark_mask)) / total * 100

    return green_pct, brown_pct, blue_pct, dark_pct


def _analyze_texture(gray, cv2, np):
    """Analyze texture features: vertical lines, horizontal lines, smooth areas.

    Returns (vertical_score, horizontal_score, smooth_score) each 0-100.
    """
    h, w = gray.shape[:2]
    total = float(h * w)

    # Sobel edge detection
    sobel_x = cv2.Sobel(gray, cv2.CV_64F, 1, 0, ksize=3)
    sobel_y = cv2.Sobel(gray, cv2.CV_64F, 0, 1, ksize=3)

    abs_x = np.abs(sobel_x)
    abs_y = np.abs(sobel_y)

    # Strong vertical edges (high horizontal gradient) suggest bamboo/tree trunks
    vert_thresh = np.percentile(abs_x, 95)
    vert_pixels = float(np.count_nonzero(abs_x > vert_thresh))
    vertical_score = min(vert_pixels / total * 2000, 100.0)

    # Strong horizontal edges suggest horizon, water surface
    horiz_thresh = np.percentile(abs_y, 95)
    horiz_pixels = float(np.count_nonzero(abs_y > horiz_thresh))
    horizontal_score = min(horiz_pixels / total * 2000, 100.0)

    # Smooth areas: low combined gradient
    magnitude = np.sqrt(sobel_x**2 + sobel_y**2)
    smooth_thresh = np.percentile(magnitude, 30)
    smooth_pixels = float(np.count_nonzero(magnitude < smooth_thresh))
    smooth_score = smooth_pixels / total * 100

    return vertical_score, horizontal_score, smooth_score


def _analyze_region(hsv_region, label: str, np) -> RegionAnalysis:
    """Analyze a horizontal region of the frame."""
    v = hsv_region[:, :, 2]
    brightness = float(np.mean(v))
    green_pct, brown_pct, blue_pct, dark_pct = _color_percentages(hsv_region, np)

    parts: list[str] = []
    if green_pct > 30:
        parts.append("茂密绿色植被")
    elif green_pct > 15:
        parts.append("中等绿色植被")
    elif green_pct > 5:
        parts.append("少量绿色")

    if brown_pct > 15:
        parts.append("大量棕色（树干/泥土）")
    elif brown_pct > 5:
        parts.append("部分棕色")

    if blue_pct > 15:
        parts.append("明显蓝色（天空/水面）")
    elif blue_pct > 5:
        parts.append("少量蓝色")

    if dark_pct > 50:
        parts.append("整体偏暗")
    elif dark_pct > 25:
        parts.append("有暗部区域")

    if brightness > 150:
        parts.append("明亮")
    elif brightness < 80:
        parts.append("昏暗")

    description = "、".join(parts) if parts else "无明显特征"

    return RegionAnalysis(
        label=label,
        brightness=brightness,
        green_pct=green_pct,
        brown_pct=brown_pct,
        blue_pct=blue_pct,
        dark_pct=dark_pct,
        description=description,
    )


def _detect_water(hsv_bottom, hsv_mid, gray_bottom, cv2, np) -> tuple[bool, float]:
    """Detect water presence in the bottom region.

    Handles both classic blue-gray water AND dark reflective water (e.g.
    forest ponds reflecting green canopy).  The reflection test compares
    bottom-third vs middle-third colour histograms — a high similarity
    indicates mirror-like water.

    Returns (detected, score) where score is 0-100.
    """
    h, s, v = hsv_bottom[:, :, 0], hsv_bottom[:, :, 1], hsv_bottom[:, :, 2]
    total = float(h.size)

    # --- Classic blue-gray water ---
    blue_gray_mask = (
        ((s < 50) & (v > 80) & (v < 200))  # Gray reflective
        | ((h >= 90) & (h <= 130) & (s > 20))  # Blue tint
    )
    water_ratio = float(np.count_nonzero(blue_gray_mask)) / total * 100

    # Reflective pixels: high brightness with low saturation
    reflective_mask = (v > 160) & (s < 40)
    reflective_ratio = float(np.count_nonzero(reflective_mask)) / total * 100

    # --- Dark reflective water (forest pond / metasequoia) ---
    # Bottom region is smooth (low edge energy) + colour histogram
    # similar to middle region (mirror reflection).
    smooth_score = 0.0
    reflection_score = 0.0

    # Smoothness: low Laplacian variance in bottom region
    lap = cv2.Laplacian(gray_bottom, cv2.CV_64F)
    lap_var = float(np.var(lap))
    # Typical textured forest: var > 500; smooth water: var < 300
    if lap_var < 300:
        smooth_score = max(0, (300 - lap_var) / 300) * 40  # 0-40

    # Reflection: hue histogram similarity between bottom and middle
    hist_bot = cv2.calcHist([hsv_bottom], [0], None, [180], [0, 180])
    hist_mid = cv2.calcHist([hsv_mid], [0], None, [180], [0, 180])
    cv2.normalize(hist_bot, hist_bot)
    cv2.normalize(hist_mid, hist_mid)
    corr = cv2.compareHist(hist_bot, hist_mid, cv2.HISTCMP_CORREL)
    # corr > 0.7 means strong colour match (reflection)
    if corr > 0.5:
        reflection_score = (corr - 0.5) * 80  # 0-40

    classic_score = water_ratio * 0.6 + reflective_ratio * 0.4
    dark_water_score = smooth_score + reflection_score

    score = min(max(classic_score, dark_water_score), 100.0)
    detected = score > 15.0

    return detected, score


def analyze_frame(
    frame_path: Path,
    on_progress: Callable[[str], None] | None = None,
) -> FrameAnalysis:
    """Analyze a single frame image and return structured analysis."""
    cv2 = _import_cv2()
    np = _import_numpy()

    _notify(on_progress, f"正在分析帧: {frame_path.name}")

    img = cv2.imread(str(frame_path))
    if img is None:
        raise RuntimeError(f"无法读取图像: {frame_path}")

    hsv = cv2.cvtColor(img, cv2.COLOR_BGR2HSV)
    gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
    h_img, w_img = img.shape[:2]

    # Overall brightness (mean of V channel)
    brightness = float(np.mean(hsv[:, :, 2]))

    # Color distribution
    green_pct, brown_pct, blue_pct, dark_pct = _color_percentages(hsv, np)

    # Sky percentage: top 1/3 brightness
    top_third_v = hsv[:h_img // 3, :, 2]
    sky_bright_mask = top_third_v > 150
    sky_pct = float(np.count_nonzero(sky_bright_mask)) / float(top_third_v.size) * 100

    # Texture analysis
    vertical_lines, horizontal_lines, smooth_areas = _analyze_texture(gray, cv2, np)

    # Region analysis (top / middle / bottom 1/3)
    h3 = h_img // 3
    top_region = _analyze_region(hsv[:h3, :], "上层", np)
    mid_region = _analyze_region(hsv[h3:2 * h3, :], "中层", np)
    bot_region = _analyze_region(hsv[2 * h3:, :], "下层", np)

    # Water detection in bottom 1/3 (now also checks dark reflective water)
    water_detected, water_score = _detect_water(
        hsv[2 * h3:, :], hsv[h3:2 * h3, :], gray[2 * h3:, :], cv2, np,
    )

    # Foliage density: green pixel concentration
    green_mask = (
        (hsv[:, :, 0] >= 35)
        & (hsv[:, :, 0] <= 85)
        & (hsv[:, :, 1] > 40)
        & (hsv[:, :, 2] > 40)
    )
    foliage_density = float(np.count_nonzero(green_mask)) / float(
        hsv[:, :, 0].size
    ) * 100

    analysis = FrameAnalysis(
        brightness=brightness,
        green_pct=green_pct,
        brown_pct=brown_pct,
        blue_pct=blue_pct,
        dark_pct=dark_pct,
        sky_pct=sky_pct,
        vertical_lines=vertical_lines,
        horizontal_lines=horizontal_lines,
        smooth_areas=smooth_areas,
        water_detected=water_detected,
        water_score=water_score,
        foliage_density=foliage_density,
        top=top_region,
        mid=mid_region,
        bot=bot_region,
    )

    _classify_scene(analysis)
    _notify(on_progress, f"分析完成: {analysis.scene_type} ({analysis.scene_description})")

    return analysis


# ---------------------------------------------------------------------------
# Step 3: Scene classification & parameter mapping
# ---------------------------------------------------------------------------

def _classify_scene(analysis: FrameAnalysis) -> None:
    """Classify the scene type and populate reasoning fields in-place.

    Priority order (highest → lowest):
      1. Water/lake/stream  (water_detected — most distinctive signal)
      2. Bamboo             (vertical lines + green + brown)
      3. Forest / canopy    (green + dark)
      4. Garden             (green + bright)
      5. Night              (very dark overall)
      6. Path               (brown + green)
      7. Open               (sky dominant)
      8. Default
    """
    a = analysis

    # --- 1. Water / lake / stream (highest priority) ---
    if a.water_detected and a.water_score > 15:
        if a.green_pct > 20:
            a.scene_type = "stream"
            a.scene_description = "溪流/水面场景，下方有明显水面反射，周围有绿色植被"
        else:
            a.scene_type = "lake"
            a.scene_description = "湖泊/开阔水面，下方区域检测到水面特征"
        a.rain_level = "medium"
        a.rain_level_reason = "水面波纹显示中等雨量"
        a.distance_level = "far" if a.sky_pct > 30 else "medium"
        a.distance_reason = (
            "开阔水面提供远距离感" if a.sky_pct > 30
            else "水面周围有遮挡，距离感中等"
        )
        a.wetness_desc = "丰富浸润"
        a.wetness_reason = "水面本身增加环境湿润感"
        a.tonality_desc = "柔和清透"
        a.tonality_reason = "水面反射声能，高频略增"

    # --- 2. Bamboo (vertical lines + green + some brown) ---
    elif (a.vertical_lines > 35 and a.horizontal_lines < 60 and a.green_pct > 15
          and a.brown_pct > 5 and a.brightness < 120):
        a.scene_type = "bamboo"
        a.scene_description = (
            "竹林场景，检测到大量垂直线条（竹竿）"
            f"，绿色 {a.green_pct:.0f}%，棕色 {a.brown_pct:.0f}%"
        )
        a.rain_level = "light"
        a.rain_level_reason = "竹叶遮挡部分雨水，形成滴落"
        a.distance_level = "medium"
        a.distance_reason = "竹林密度中等，具有空间纵深"
        a.wetness_desc = "清新适中"
        a.wetness_reason = "竹叶导流雨水，湿度适中"
        a.tonality_desc = "清脆通透"
        a.tonality_reason = "竹竿硬质表面产生清脆敲击声"

    # --- 3. Shelter / Window / Indoor (structural lines + lower green) ---
    elif a.horizontal_lines > 30 and a.vertical_lines > 30 and a.green_pct < 25:
        a.scene_type = "shelter"
        a.scene_description = (
            "窗前/遮蔽场景，检测到明显的水平与垂直结构线条（窗框/屋檐/建筑结构）"
            f"，绿色占比较少 ({a.green_pct:.1f}%)"
        )
        a.rain_level = "medium"
        a.rain_level_reason = "遮蔽环境下，中等雨势"
        a.distance_level = "near"
        a.distance_reason = "靠近遮蔽物/窗户，近景击打感强"
        a.wetness_desc = "隔绝湿润"
        a.wetness_reason = "室内或廊下，环境湿度感适中"
        a.tonality_desc = "温暖偏闷"
        a.tonality_reason = "遮蔽物或窗户阻挡/吸收了部分高频声音"

    # --- 4. Grass Park Path (highly textured, green + brown) ---
    elif a.horizontal_lines > 40 and a.vertical_lines > 40 and a.green_pct > 10 and a.brown_pct > 10:
        a.scene_type = "path"
        a.scene_description = "草地公园小径，棕色（泥土/落叶/石块）与绿色共存"
        a.rain_level = "medium"
        a.rain_level_reason = "开放路径，雨水直接落地"
        a.distance_level = "medium"
        a.distance_reason = "两侧树木提供适度遮挡"
        a.wetness_desc = "泥泞湿润"
        a.wetness_reason = "地面泥土/石板吸水，雨滴溅射"
        a.tonality_desc = "中频温暖"
        a.tonality_reason = "泥土和落叶衰减高频"

    # --- 5. Forest / canopy (green dominant + not too bright) ---
    elif a.green_pct > 25 and a.brightness < 100:
        if a.sky_pct < 10 and a.foliage_density > 35:
            a.scene_type = "canopy"
            a.scene_description = "密林树冠，绿色浓密且天空几乎不可见"
        else:
            a.scene_type = "forest"
            a.scene_description = "森林/树林场景，大面积绿色植被，亮度偏低"
        a.rain_level = "light"
        a.rain_level_reason = "树冠遮挡大部分雨水"
        a.distance_level = "far"
        a.distance_reason = "密集植被过滤声音，增加距离感"
        a.wetness_desc = "潮湿厚重"
        a.wetness_reason = "树冠截留大量水分，空气湿度高"
        a.tonality_desc = "低沉绵密"
        a.tonality_reason = "大量树叶吸收高频，低频占主导"

    # --- 6. Garden (green + bright) ---
    elif a.green_pct > 15 and a.brightness >= 100:
        a.scene_type = "garden"
        a.scene_description = "花园/花草场景，绿色适中，整体明亮"
        a.rain_level = "medium"
        a.rain_level_reason = "植被高度较低，雨水直接打在叶面"
        a.distance_level = "near"
        a.distance_reason = "低矮植被缺少遮挡，声源距离近"
        a.wetness_desc = "清新适中"
        a.wetness_reason = "开放空间，湿度适中"
        a.tonality_desc = "明亮活泼"
        a.tonality_reason = "光线充足场景，高频细节丰富"

    # --- 7. Night scene (very dark) ---
    elif a.brightness < 60:
        a.scene_type = "night"
        a.scene_description = "夜间场景，整体亮度很低"
        a.rain_level = "medium"
        a.rain_level_reason = "夜间雨量中等，视觉辨识度低"
        a.distance_level = "medium"
        a.distance_reason = "夜间缺少远景参照，中等距离感"
        a.wetness_desc = "湿润深沉"
        a.wetness_reason = "暗部像素占比高，整体沉浸感强"
        a.tonality_desc = "低沉温暖"
        a.tonality_reason = "夜景缺少高频视觉信息，声场偏暖"

    # --- 8. Open / bright scene ---
    elif a.sky_pct > 40:
        a.scene_type = "open"
        a.scene_description = "开阔场景，天空占比大"
        a.rain_level = "medium"
        a.rain_level_reason = "无遮挡，雨量直接"
        a.distance_level = "near"
        a.distance_reason = "开阔空间无遮挡"
        a.wetness_desc = "清爽"
        a.wetness_reason = "开放空间水分蒸发快"
        a.tonality_desc = "清亮直接"
        a.tonality_reason = "无障碍物衰减声音"

    # --- 9. Default ---
    else:
        a.scene_description = "自然场景，未匹配特定类型"
        a.rain_level = "medium"
        a.rain_level_reason = "默认中等雨量"
        a.distance_level = "medium"
        a.distance_reason = "默认中等距离"
        a.wetness_desc = "适中"
        a.wetness_reason = "默认湿度"
        a.tonality_desc = "自然均衡"
        a.tonality_reason = "无突出特征，均衡音色"


# ---------------------------------------------------------------------------
# VSTParams & parameter mapping
# ---------------------------------------------------------------------------

def _clampf(value: float, lo: float = 0.0, hi: float = 1.0) -> float:
    """Clamp *value* to [lo, hi]."""
    return max(lo, min(hi, value))


@dataclass
class VSTParams:
    """Complete RAIN VST parameter set — all 29 XML params + layer IDs."""

    scene_cn: str
    scene_en: str
    # Layer selection
    l1: int
    l2: int
    l3: int
    l1_name: str
    l2_name: str
    l3_name: str
    adv: int
    # --- All 29 PARAM values (0.0-1.0) ---
    gldr: float
    bgeq1x: float
    bgeq1y: float
    bgeq2x: float
    bgeq2y: float
    bgeq3x: float
    bgeq3y: float
    bgpn: float
    bgwi: float
    eq1x: float
    eq1y: float
    eq2x: float
    eq2y: float
    eq3x: float
    eq3y: float
    glgn: float
    glhp: float
    gllp: float
    glon: float
    rfch: float
    rfdn: float
    rffc: float
    rfin: float
    spbl: float
    sppn: float
    spwi: float
    sucd: float
    supn: float
    suwi: float
    # Reasoning
    reasons: dict[str, str] = field(default_factory=dict)

    # --- Convenience: 0-100 integer representations for display ---
    @property
    def density_pct(self) -> int:
        return int(round(self.rfdn * 100))

    @property
    def intensity_pct(self) -> int:
        return int(round(self.rfin * 100))

    @property
    def wetness_pct(self) -> int:
        return int(round(self.rffc * 100))

    @property
    def distance_pct(self) -> int:
        return int(round(self.rfch * 100))


def map_to_vst_params(analysis: FrameAnalysis) -> VSTParams:
    """Map frame analysis to complete RAIN VST parameters with fine-tuning."""
    a = analysis
    scene = SCENE_PRESETS.get(a.scene_type, SCENE_PRESETS["default"])

    # Start with base preset values (copy as mutable floats)
    rfdn = scene.rfdn
    rfin = scene.rfin
    rffc = scene.rffc
    rfch = scene.rfch
    bgwi = scene.bgwi
    bgpn = scene.bgpn
    bgeq1x = scene.bgeq1x
    bgeq1y = scene.bgeq1y
    bgeq2x = scene.bgeq2x
    bgeq2y = scene.bgeq2y
    bgeq3x = scene.bgeq3x
    bgeq3y = scene.bgeq3y
    spbl = scene.spbl
    spwi = scene.spwi
    sppn = scene.sppn
    sucd = scene.sucd
    suwi = scene.suwi
    supn = scene.supn
    eq1x = scene.eq1x
    eq1y = scene.eq1y
    eq2x = scene.eq2x
    eq2y = scene.eq2y
    eq3x = scene.eq3x
    eq3y = scene.eq3y
    glhp = scene.glhp
    gllp = scene.gllp

    reasons: dict[str, str] = {}

    # --- Fine-tune based on actual frame analysis ---

    # Water ripples → higher Density, higher Drops, lower Distance(rfch)
    if a.water_detected:
        ripple = min(a.water_score * 0.003, 0.15)
        rfdn += ripple
        rfch -= ripple * 0.5
        sucd += ripple * 0.5
        reasons["rfdn"] = (
            f"水面波纹 (score={a.water_score:.1f})，密度 +{ripple:.2f}"
        )
        reasons["rfch"] = f"水面近景感强，距离 -{ripple * 0.5:.2f}"

    # Dense canopy (no sky) → higher Distance(rfch stays low = far),
    # higher Blend(spbl), wider Space
    if a.sky_pct < 10:
        canopy_boost = (10 - a.sky_pct) * 0.01
        spbl += canopy_boost
        bgwi += canopy_boost * 0.5
        reasons["spbl"] = (
            f"天空不可见 ({a.sky_pct:.1f}%)，Blend +{canopy_boost:.2f}"
        )
    elif a.sky_pct > 40:
        sky_reduce = (a.sky_pct - 40) * 0.003
        rfch += sky_reduce
        bgwi += sky_reduce
        reasons["bgwi"] = f"开阔天空 ({a.sky_pct:.1f}%)，声场加宽 +{sky_reduce:.2f}"

    # Brown (tree trunks / soil) → higher Mass (bgeq1x, eq1x)
    if a.brown_pct > 10:
        mass_boost = (a.brown_pct - 10) * 0.008
        bgeq1x += mass_boost
        eq1x += mass_boost
        reasons["bgeq1x"] = (
            f"棕色占比高 ({a.brown_pct:.1f}%)，质感 +{mass_boost:.2f}"
        )

    # Darker → warmer tonality (higher Mass, lower Presence)
    if a.brightness < 80:
        dark_factor = (80 - a.brightness) / 80
        bgeq1x += dark_factor * 0.10
        eq1x += dark_factor * 0.10
        bgeq2y -= dark_factor * 0.08
        eq2y -= dark_factor * 0.08
        gllp += dark_factor * 0.05
        reasons["eq1x"] = (
            f"偏暗 (brightness={a.brightness:.1f})，质感 +{dark_factor * 0.10:.2f}"
        )

    # Foliage density → adjust rainfall intensity and space width
    if a.foliage_density > 35:
        foliage_f = (a.foliage_density - 35) * 0.002
        rfin -= foliage_f
        spwi += foliage_f * 0.5
        bgeq1y += foliage_f * 0.3
        reasons["rfin"] = (
            f"植被密度高 ({a.foliage_density:.1f}%)，强度 -{foliage_f:.2f}"
        )

    # High brightness → more presence/clarity
    if a.brightness > 130:
        bright_f = (a.brightness - 130) * 0.001
        bgeq2y += bright_f
        eq2y += bright_f
        eq1y += bright_f * 0.5
        reasons["bgeq2y"] = (
            f"高亮度 ({a.brightness:.1f})，存在感 +{bright_f:.2f}"
        )

    # Vertical lines (bamboo/trunks) → adjust strength and Close Drops
    if a.vertical_lines > 30:
        vert_f = (a.vertical_lines - 30) * 0.002
        bgeq1y += vert_f
        eq1y += vert_f
        sucd += vert_f * 0.5
        reasons["bgeq1y"] = (
            f"垂直结构 ({a.vertical_lines:.1f})，力度 +{vert_f:.2f}"
        )

    # Smooth areas (water/sky) → lower Close Drops
    if a.smooth_areas > 40:
        smooth_f = (a.smooth_areas - 40) * 0.002
        sucd -= smooth_f
        reasons["sucd"] = f"平滑区域多 ({a.smooth_areas:.1f})，Drops -{smooth_f:.2f}"

    # Build layer names
    l1_name = _layer_label(scene.l1, DISTANT_NAMES)
    l2_name = _layer_label(scene.l2, SPACE_NAMES)
    l3_name = _layer_label(scene.l3, CLOSE_NAMES)

    # Base reasons for params that didn't get fine-tuned
    reasons.setdefault("rfdn", f"场景基准密度 {scene.rfdn:.2f}")
    reasons.setdefault("rfin", f"场景基准强度 {scene.rfin:.2f}")
    reasons.setdefault("rffc", f"场景基准湿润 {scene.rffc:.2f}，{a.wetness_desc}")
    reasons.setdefault("rfch", f"场景基准距离 {scene.rfch:.2f}，{a.distance_reason}")
    reasons.setdefault("bgeq1x", f"远景质感基准 {scene.bgeq1x:.2f}")
    reasons.setdefault("bgeq1y", f"远景力度基准 {scene.bgeq1y:.2f}")
    reasons.setdefault("bgeq2y", f"远景存在感基准 {scene.bgeq2y:.2f}")
    reasons.setdefault("bgwi", f"远景宽度基准 {scene.bgwi:.2f}")
    reasons.setdefault("spbl", f"空间混合基准 {scene.spbl:.2f}")
    reasons.setdefault("sucd", f"近景 Drops 基准 {scene.sucd:.2f}")
    reasons.setdefault("eq1x", f"降雨质感基准 {scene.eq1x:.2f}")
    reasons.setdefault("eq2y", f"降雨存在感基准 {scene.eq2y:.2f}")

    return VSTParams(
        scene_cn=scene.name_cn,
        scene_en=scene.name_en,
        l1=scene.l3, # Close is l1 now
        l2=scene.l2,
        l3=scene.l1, # Distant is l3 now
        l1_name=l3_name,
        l2_name=l2_name,
        l3_name=l1_name,
        adv=scene.adv,
        gldr=scene.gldr,
        bgeq1x=_clampf(bgeq1x),
        bgeq1y=_clampf(bgeq1y),
        bgeq2x=_clampf(bgeq2x),
        bgeq2y=_clampf(bgeq2y),
        bgeq3x=_clampf(bgeq3x),
        bgeq3y=_clampf(bgeq3y),
        bgpn=_clampf(bgpn),
        bgwi=_clampf(bgwi),
        eq1x=_clampf(eq1x),
        eq1y=_clampf(eq1y),
        eq2x=_clampf(eq2x),
        eq2y=_clampf(eq2y),
        eq3x=_clampf(eq3x),
        eq3y=_clampf(eq3y),
        glgn=scene.glgn,
        glhp=_clampf(glhp),
        gllp=_clampf(gllp),
        glon=scene.glon,
        rfch=_clampf(rfch),
        rfdn=_clampf(rfdn),
        rffc=_clampf(rffc),
        rfin=_clampf(rfin),
        spbl=_clampf(spbl),
        sppn=_clampf(sppn),
        spwi=_clampf(spwi),
        sucd=_clampf(sucd),
        supn=_clampf(supn),
        suwi=_clampf(suwi),
        reasons=reasons,
    )


# ---------------------------------------------------------------------------
# Step 4: Generate .rain XML file
# ---------------------------------------------------------------------------

def generate_rain_file(
    video_id: str,
    params: VSTParams,
    output_dir: Path,
) -> Path:
    """Write a complete .rain XML configuration file.

    The output file is directly loadable by the BOOM Library RAIN VST3 plugin
    via Scene → Right-click → Load from file.
    """
    scene_name = f"{video_id} {params.scene_cn}"
    lines = [
        '<?xml version="1.0" encoding="UTF-8"?>',
        '',
        f'<Rain version="1" lts="0"'
        f' l1="{params.l1}" l2="{params.l2}" l3="{params.l3}"'
        f' adv="{params.adv}" scn="{scene_name}">',
    ]

    # Emit all 29 PARAM elements in the same order as official presets
    param_order = [
        ("gldr", params.gldr),
        ("bgeq1x", params.bgeq1x),
        ("bgeq1y", params.bgeq1y),
        ("bgeq2x", params.bgeq2x),
        ("bgeq2y", params.bgeq2y),
        ("bgeq3x", params.bgeq3x),
        ("bgeq3y", params.bgeq3y),
        ("bgpn", params.bgpn),
        ("bgwi", params.bgwi),
        ("eq1x", params.eq1x),
        ("eq1y", params.eq1y),
        ("eq2x", params.eq2x),
        ("eq2y", params.eq2y),
        ("eq3x", params.eq3x),
        ("eq3y", params.eq3y),
        ("glgn", params.glgn),
        ("glhp", params.glhp),
        ("gllp", params.gllp),
        ("glon", params.glon),
        ("rfch", params.rfch),
        ("rfdn", params.rfdn),
        ("rffc", params.rffc),
        ("rfin", params.rfin),
        ("spbl", params.spbl),
        ("sppn", params.sppn),
        ("spwi", params.spwi),
        ("sucd", params.sucd),
        ("supn", params.supn),
        ("suwi", params.suwi),
    ]

    for pid, val in param_order:
        # Clean decimal formatting — round to avoid floating-point artefacts
        if val == 0.0:
            val_str = "0.0"
        elif val == 1.0:
            val_str = "1.0"
        else:
            # Round to 6 significant digits, strip trailing zeros
            val_str = f"{val:.6f}".rstrip("0").rstrip(".")
        lines.append(f'  <PARAM id="{pid}" value="{val_str}"/>')

    lines.append("</Rain>")
    lines.append("")  # trailing newline

    rain_path = output_dir / f"{video_id}.rain"
    # Write with \r\n line endings to match official preset format
    rain_path.write_text("\r\n".join(lines), encoding="utf-8")
    return rain_path


# ---------------------------------------------------------------------------
# Step 5: Generate markdown report
# ---------------------------------------------------------------------------

def generate_report(
    video_id: str,
    analysis: FrameAnalysis,
    params: VSTParams,
) -> str:
    """Render the full markdown report."""
    a = analysis
    p = params

    d_reason = _distant_reason(a)
    s_reason = _space_reason(a)
    c_reason = _close_reason(a)

    water_desc = (
        f"检测到水面 (score={a.water_score:.1f})" if a.water_detected
        else f"未检测到明显水面 (score={a.water_score:.1f})"
    )

    # Format key reasons
    reason_rows: list[str] = []
    key_params = [
        ("Density (rfdn)", f"{p.rfdn:.2f} ({p.density_pct}%)", p.reasons.get("rfdn", "")),
        ("Intensity (rfin)", f"{p.rfin:.2f} ({p.intensity_pct}%)", p.reasons.get("rfin", "")),
        ("Wetness (rffc)", f"{p.rffc:.2f} ({p.wetness_pct}%)", p.reasons.get("rffc", "")),
        ("Distance (rfch)", f"{p.rfch:.2f} ({p.distance_pct}%)", p.reasons.get("rfch", "")),
        ("Distant Mass (bgeq1x)", f"{p.bgeq1x:.2f}", p.reasons.get("bgeq1x", "")),
        ("Distant Strength (bgeq1y)", f"{p.bgeq1y:.2f}", p.reasons.get("bgeq1y", "")),
        ("Distant Presence (bgeq2y)", f"{p.bgeq2y:.2f}", p.reasons.get("bgeq2y", "")),
        ("Distant Width (bgwi)", f"{p.bgwi:.2f}", p.reasons.get("bgwi", "")),
        ("Space Blend (spbl)", f"{p.spbl:.2f}", p.reasons.get("spbl", "")),
        ("Close Drops (sucd)", f"{p.sucd:.2f}", p.reasons.get("sucd", "")),
        ("Rainfall Mass (eq1x)", f"{p.eq1x:.2f}", p.reasons.get("eq1x", "")),
        ("Rainfall Presence (eq2y)", f"{p.eq2y:.2f}", p.reasons.get("eq2y", "")),
        ("High Pass (glhp)", f"{p.glhp:.2f}", ""),
        ("Low Pass (gllp)", f"{p.gllp:.2f}", ""),
    ]
    for name, val, reason in key_params:
        reason_rows.append(f"| **{name}** | {val} | {reason} |")

    reasons_table = "\n".join(reason_rows)

    md = f"""# {video_id} RAIN VST 参数分析

![首帧]({video_id}.png)

## 画面要素分析

| 要素 | 分析 |
|------|------|
| **场景** | {a.scene_description} |
| **上层 1/3** | {a.top.description} |
| **中层 1/3** | {a.mid.description} |
| **下层 1/3** | {a.bot.description} |
| **整体亮度** | {a.brightness:.1f} |
| **绿色占比** | {a.green_pct:.1f}% |
| **棕色占比** | {a.brown_pct:.1f}% |
| **暗部占比** | {a.dark_pct:.1f}% |
| **垂直纹理** | {a.vertical_lines:.1f} |
| **水面检测** | {water_desc} |

## 声场推理

| 维度 | 判断 | 依据 |
|------|------|------|
| **远景** | {p.l3_name} (l3={p.l3}) | {d_reason} |
| **空间** | {p.l2_name} (l2={p.l2}) | {s_reason} |
| **近景** | {p.l1_name} (l1={p.l1}) | {c_reason} |
| **雨势** | {a.rain_level} | {a.rain_level_reason} |
| **距离** | {a.distance_level} | {a.distance_reason} |
| **湿度** | {a.wetness_desc} | {a.wetness_reason} |
| **Tonality** | {a.tonality_desc} | {a.tonality_reason} |

## RAIN VST 推荐参数

```
场景名：{p.scene_cn}   {p.scene_en}

远景 Distant:  {p.l3_name} (l3={p.l3})
空间 Space:    {p.l2_name} (l2={p.l2})
近景 Close:    {p.l1_name} (l1={p.l1})

Density/Intensity:    {p.rfdn:.2f} / {p.rfin:.2f}
Wetness/Distance:     {p.rffc:.2f} / {p.rfch:.2f}
Distant Width:        {p.bgwi:.2f}
Space Blend/Width:    {p.spbl:.2f} / {p.spwi:.2f}
Close Drops/Width:    {p.sucd:.2f} / {p.suwi:.2f}
High Pass / Low Pass: {p.glhp:.2f} / {p.gllp:.2f}
```

> ✅ 已导出完整配置文件: **{video_id}.rain**
> 可在 RAIN 插件中 右键 Scene → Load from file 直接加载

## 参数设计理由

| 参数 | 值 | 理由 |
|------|-----|------|
{reasons_table}
"""
    return md


def _distant_reason(a: FrameAnalysis) -> str:
    """Generate reasoning for Distant preset selection."""
    reasons: list[str] = []
    if a.scene_type == "forest":
        reasons.append("森林环境需要低沉远景底噪")
    elif a.scene_type == "canopy":
        reasons.append("密林树冠适合雨落树冠的远景")
    elif a.scene_type == "lake":
        reasons.append("湖泊场景适合寒流/远景雨声")
    elif a.scene_type == "stream":
        reasons.append("溪流场景需要柔和远方雨幕")
    elif a.scene_type == "bamboo":
        reasons.append("竹林需要空灵通透的远景")
    elif a.scene_type == "night":
        reasons.append("夜间场景需要沉浸包裹的远景")
    elif a.scene_type == "garden":
        reasons.append("花园需要雨落树冠的轻快远景")
    elif a.scene_type == "path":
        reasons.append("小径需要和风细雨的远景")
    elif a.scene_type == "open":
        reasons.append("开阔场景需要柔和阵雨远景")
    else:
        reasons.append("默认森林低语远景")

    if a.brightness < 80:
        reasons.append(f"低亮度({a.brightness:.0f})加深远景沉浸")
    if a.dark_pct > 40:
        reasons.append(f"暗部占比高({a.dark_pct:.0f}%)增加厚度")

    return "；".join(reasons)


def _space_reason(a: FrameAnalysis) -> str:
    """Generate reasoning for Space preset selection."""
    reasons: list[str] = []
    if a.foliage_density > 30:
        reasons.append(f"植被密度 {a.foliage_density:.0f}% 适合茂密树林空间")
    elif a.foliage_density > 15:
        reasons.append(f"中等植被({a.foliage_density:.0f}%)适合树冠空间")
    else:
        reasons.append("植被稀疏，使用开放空间预设")

    if a.sky_pct < 10:
        reasons.append("天空不可见，封闭空间感")
    elif a.sky_pct > 30:
        reasons.append("大面积天空，开放空间感")

    return "；".join(reasons)


def _close_reason(a: FrameAnalysis) -> str:
    """Generate reasoning for Close preset selection."""
    reasons: list[str] = []
    if a.water_detected:
        reasons.append(f"水面检测 (score={a.water_score:.0f}) 适合水面近景")
    elif a.green_pct > 25:
        reasons.append(f"绿色高占比({a.green_pct:.0f}%)适合茂密植被近景")
    elif a.green_pct > 10:
        reasons.append(f"绿色中占比({a.green_pct:.0f}%)适合稀疏植被近景")
    elif a.brown_pct > 15:
        reasons.append(f"棕色高占比({a.brown_pct:.0f}%)适合砾石/泥地近景")
    else:
        reasons.append("默认茂密植被近景")

    if a.bot.dark_pct > 40:
        reasons.append("底部偏暗，地面湿润质感")

    return "；".join(reasons)


# ---------------------------------------------------------------------------
# Main entry point
# ---------------------------------------------------------------------------

def analyze_video(
    video_path: Path,
    output_dir: Path,
    on_progress: Callable[[str], None] | None = None,
    force_refresh: bool = False,
    *,
    skip_clip: bool = False,
    apply_rain_fx: bool = True,
) -> dict:
    """提取首帧 → CLIP 远景/空间/近景 → 封面（可选雨效）。不分析视频内嵌音轨。"""
    video_path = Path(video_path)
    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    if not video_path.is_file():
        raise FileNotFoundError(f"视频文件不存在: {video_path}")

    video_id = extract_video_id(video_path)
    _notify(on_progress, f"开始分析首帧: {video_id}")

    raw_jpg = output_dir / f"{video_id}_snapshot_raw.jpg"
    thumbnail_jpg = output_dir / f"{video_id}_thumbnail.jpg"
    legacy_snapshot = output_dir / f"{video_id}_snapshot.jpg"

    if force_refresh or not raw_jpg.exists():
        extract_first_frame(video_path, raw_jpg, on_progress)
    else:
        _notify(on_progress, f"首帧已存在，跳过: {raw_jpg.name}")

    if skip_clip:
        _notify(on_progress, "CLIP 结果已存在，跳过分析")
        ai_results: dict = {}
    else:
        from scripts.video_analysis.clip_engine import analyze_and_map_with_clip
        _notify(on_progress, "CLIP 分析首帧（远景 + 空间 + 近景）…")
        _, ai_results = analyze_and_map_with_clip(str(raw_jpg), on_progress)

    if force_refresh or not thumbnail_jpg.exists():
        if apply_rain_fx:
            from scripts.video_analysis.cover_composite import composite_rain_cover

            _notify(on_progress, "正在合成雨效封面 (rain_fx.png)…")
            composite_rain_cover(raw_jpg, thumbnail_jpg)
        else:
            _notify(on_progress, "封面不加雨效，使用原始首帧…")
            shutil.copy2(raw_jpg, thumbnail_jpg)
        _notify(on_progress, f"封面已保存: {thumbnail_jpg.name}")
    else:
        _notify(on_progress, f"封面已存在，跳过: {thumbnail_jpg.name}")

    if legacy_snapshot.is_file():
        legacy_snapshot.unlink()
        _notify(on_progress, f"已删除旧文件: {legacy_snapshot.name}")

    return {
        "video_id": video_id,
        "clip_analysis": ai_results,
        "thumbnail_jpg": thumbnail_jpg,
        "frame_jpg": raw_jpg,
    }


def analyze_vlm_frame(frame_jpg: Path, on_progress: Callable[[str], None] | None = None) -> dict:
    """Gemini VLM 分析首帧，输出远景/空间/近景三层 ID。"""
    from scripts.video_analysis.vlm_engine import analyze_with_vlm
    _notify(on_progress, "Gemini VLM 分析首帧（远景 + 空间 + 近景）…")
    try:
        vlm_results = analyze_with_vlm(frame_jpg, on_progress)
        from scripts.config.common_constants import DISTANT_NAMES, SPACE_NAMES, CLOSE_NAMES
        l3_en, l3_cn = DISTANT_NAMES.get(vlm_results.get("l3_key"), ("Unknown", "未知"))
        l2_en, l2_cn = SPACE_NAMES.get(vlm_results.get("l2_key"), ("Unknown", "未知"))
        l1_en, l1_cn = CLOSE_NAMES.get(vlm_results.get("l1_key"), ("Unknown", "未知"))
        vlm_results["l3_cn"] = l3_cn
        vlm_results["l2_cn"] = l2_cn
        vlm_results["l1_cn"] = l1_cn
        _notify(on_progress, f"VLM 分析完成，输出 [{l3_cn} + {l2_cn} + {l1_cn}]")
    except Exception as e:
        _notify(on_progress, f"VLM 分析失败: {e}")
        vlm_results = {}
    return vlm_results


# 兼容旧调用
def analyze_vlm_only(frame_jpg: Path, on_progress: Callable[[str], None] | None = None) -> dict:
    return analyze_vlm_frame(frame_jpg, on_progress)


# ---------------------------------------------------------------------------
