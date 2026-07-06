#!/usr/bin/env python3
"""分析循环视频首帧，输出 BOOM Library RAIN VST 插件参数建议。

工作流:
  1. ffmpeg 提取首帧 → MVI_xxxx.png
  2. OpenCV 分析亮度、色彩分布、纹理、区域特征、水面检测
  3. 规则匹配场景类型 → 映射到 RAIN VST 三层预设 + 五组参数
  4. 输出 MVI_xxxx.md 报告

用法:
  python3 scripts/rain_vst_analyze.py <video_path> [--output-dir <dir>]
"""

from __future__ import annotations

import argparse
import re
import subprocess
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable

# ---------------------------------------------------------------------------
# Preset dictionaries
# ---------------------------------------------------------------------------

DISTANT_PRESETS: dict[int, tuple[str, str]] = {
    1: ("Harmonic Mist", "和谐细雾"),
    2: ("Ethereal Currents", "空灵气流"),
    3: ("Aura of Drizzle", "微雨灵韵"),
    4: ("Cloud Dance", "云之舞"),
    5: ("Mellow Shower", "柔和阵雨"),
    6: ("Zephyr Rainfall", "和风细雨"),
    7: ("Chilly Pouring", "寒流雨声"),
    8: ("Heavy Cascade", "倾盆大雨"),
    9: ("Distant Veil", "远方雨幕"),
    10: ("Reverberant Torrent", "回荡急流"),
    11: ("Windswept Showers", "风雨交加"),
    12: ("Turbulent Downpour", "湍急暴雨"),
    13: ("Forest Whisper", "森林低语"),
    14: ("Raindrop Canopy", "雨落树冠"),
    15: ("Immersive Curtain", "沉浸雨幕"),
    16: ("Cascade Whisper", "缓瀑雨声"),
    17: ("Drenching Storm", "浸透风暴"),
    18: ("Torrential Fury", "暴怒骤雨"),
    19: ("Urban Resonance", "都市回响"),
}

SPACE_PRESETS: dict[int, tuple[str, str]] = {
    1: ("Metal Shelter", "金属遮蔽"),
    2: ("Concrete Archway", "混凝土拱道"),
    3: ("Plastic Roofing", "塑料棚顶"),
    4: ("Car Interior", "车内空间"),
    5: ("Tree Canopy", "树冠"),
    6: ("Foliage Dense", "茂密树林"),
    7: ("Zen Garden", "禅意庭院"),
    8: ("Metal Roof", "金属屋顶"),
    9: ("Urban Canyon", "城市峡谷"),
    10: ("Open Parking", "露天停车场"),
    11: ("Country Road", "乡间小路"),
    12: ("Narrow Alley", "窄巷"),
    13: ("Concrete Wall", "混凝土墙"),
    14: ("Wooden Veranda", "木质长廊"),
}

CLOSE_PRESETS: dict[int, tuple[str, str]] = {
    1: ("Metal Surface", "金属表面"),
    2: ("Concrete", "混凝土"),
    3: ("Concrete Diffuse", "混凝土漫射"),
    4: ("Dense Foliage", "茂密植被"),
    5: ("Sparse Foliage", "稀疏植被"),
    6: ("Glass", "玻璃"),
    7: ("Car Body", "车身"),
    8: ("Fabric/Tent", "布料/帐篷"),
    9: ("Stone", "石头"),
    10: ("Gravel", "砾石"),
    11: ("Metal Resonant", "金属共鸣"),
    12: ("Tile", "瓷砖"),
    13: ("Metal Sheet", "金属薄板"),
    14: ("Plastic", "塑料"),
    15: ("Canvas", "帆布"),
    16: ("Mud", "泥地"),
    17: ("Water", "水面"),
    18: ("Wooden Roof", "木屋顶"),
    19: ("Bark", "树皮"),
}

# ---------------------------------------------------------------------------
# Scene presets: (distant, space, close, density/intensity, wetness/distance,
#                 mass/intensity, strength/intensity, presence/intensity)
# ---------------------------------------------------------------------------

@dataclass
class ScenePreset:
    """A named scene with default RAIN VST parameters."""

    name_cn: str
    name_en: str
    distant: int
    space: int
    close: int
    density: int
    intensity_d: int
    wetness: int
    distance: int
    mass: int
    intensity_m: int
    strength: int
    intensity_s: int
    presence: int
    intensity_p: int


SCENE_PRESETS: dict[str, ScenePreset] = {
    "forest": ScenePreset(
        "森林细雨", "Deep Forest Drizzle",
        13, 6, 4,
        40, 15, 30, 70, 75, 55, 50, 30, 60, 55,
    ),
    "lake": ScenePreset(
        "湖畔轻雨", "Lake Light Rain",
        7, 6, 17,
        45, 25, 35, 70, 78, 55, 65, 45, 55, 55,
    ),
    "garden": ScenePreset(
        "花园雨景", "English Garden Rain",
        14, 6, 4,
        50, 40, 35, 65, 70, 55, 52, 38, 68, 60,
    ),
    "bamboo": ScenePreset(
        "竹林雨声", "Bamboo Grove Rain",
        2, 6, 5,
        45, 35, 25, 65, 65, 50, 45, 35, 70, 65,
    ),
    "night": ScenePreset(
        "夜间雨林", "Conifer Night Rain",
        15, 5, 4,
        55, 35, 50, 60, 85, 55, 70, 50, 55, 45,
    ),
    "stream": ScenePreset(
        "溪流雨声", "Forest Stream Rain",
        9, 6, 17,
        40, 20, 40, 65, 70, 50, 55, 35, 60, 55,
    ),
    "path": ScenePreset(
        "林间小径", "Woodland Path Rain",
        6, 11, 10,
        45, 30, 35, 60, 72, 50, 48, 35, 65, 55,
    ),
    "canopy": ScenePreset(
        "密林树冠", "Dense Canopy Rain",
        14, 5, 19,
        50, 30, 40, 75, 80, 60, 55, 40, 50, 45,
    ),
    "open": ScenePreset(
        "开阔雨景", "Open Field Rain",
        5, 10, 16,
        55, 45, 30, 50, 65, 50, 60, 45, 70, 60,
    ),
    "default": ScenePreset(
        "自然雨景", "Natural Rain",
        13, 6, 4,
        45, 25, 35, 65, 72, 52, 50, 35, 60, 55,
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
        "ffmpeg", "-i", str(video_path),
        "-vf", "select=eq(n\\,0)",
        "-vframes", "1",
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
        raise RuntimeError("ffmpeg 未安装或不在 PATH 中") from None
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
      2. Forest / canopy    (green + dark)
      3. Garden             (green + bright)
      4. Night              (very dark overall)
      5. Path               (brown + green)
      6. Open               (sky dominant)
      7. Default
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

    # --- 2. Forest / canopy (green dominant + not too bright) ---
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

    # --- 3. Garden (green + bright) ---
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

    # --- 4. Night scene (very dark) ---
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

    # --- 5. Path (brown + green) ---
    elif a.brown_pct > 10 and a.green_pct > 10:
        a.scene_type = "path"
        a.scene_description = "林间小径，棕色（泥土/落叶）与绿色共存"
        a.rain_level = "medium"
        a.rain_level_reason = "开放路径，雨水直接落地"
        a.distance_level = "medium"
        a.distance_reason = "两侧树木提供适度遮挡"
        a.wetness_desc = "泥泞湿润"
        a.wetness_reason = "地面泥土吸水，砾石溅射"
        a.tonality_desc = "中频温暖"
        a.tonality_reason = "泥土和落叶衰减高频"

    # --- 6. Open / bright scene ---
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

    # --- 7. Default ---
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


def _clamp(value: float, lo: float = 0.0, hi: float = 100.0) -> int:
    """Clamp *value* to [lo, hi] and round to int."""
    return int(round(max(lo, min(hi, value))))


@dataclass
class VSTParams:
    """Final RAIN VST parameter set."""

    scene_cn: str
    scene_en: str
    distant: int
    distant_name: str
    space: int
    space_name: str
    close: int
    close_name: str
    density: int
    intensity_d: int
    wetness: int
    distance: int
    mass: int
    intensity_m: int
    strength: int
    intensity_s: int
    presence: int
    intensity_p: int

    # Reasoning for each parameter
    reasons: dict[str, str] = field(default_factory=dict)


def map_to_vst_params(analysis: FrameAnalysis) -> VSTParams:
    """Map frame analysis to RAIN VST parameters with fine-tuning."""
    a = analysis
    scene = SCENE_PRESETS.get(a.scene_type, SCENE_PRESETS["default"])

    # Start with base preset values
    density = float(scene.density)
    intensity_d = float(scene.intensity_d)
    wetness = float(scene.wetness)
    distance = float(scene.distance)
    mass = float(scene.mass)
    intensity_m = float(scene.intensity_m)
    strength = float(scene.strength)
    intensity_s = float(scene.intensity_s)
    presence = float(scene.presence)
    intensity_p = float(scene.intensity_p)

    reasons: dict[str, str] = {}

    # --- Fine-tune based on actual frame analysis ---

    # Water ripples → higher Density, lower Distance
    if a.water_detected:
        ripple_boost = min(a.water_score * 0.3, 15)
        density += ripple_boost
        distance -= ripple_boost * 0.5
        reasons["Density"] = (
            f"水面波纹检测 (score={a.water_score:.1f})，"
            f"提升密度 +{ripple_boost:.0f}"
        )
        reasons["Distance(wetness)"] = (
            f"水面近景感强，距离降低 -{ripple_boost * 0.5:.0f}"
        )

    # Denser canopy (no sky visible) → higher Distance (rain filtered)
    if a.sky_pct < 10:
        canopy_boost = (10 - a.sky_pct) * 1.0
        distance += canopy_boost
        reasons["Distance(canopy)"] = (
            f"天空可见度极低 ({a.sky_pct:.1f}%)，"
            f"树冠过滤雨声，距离感增加 +{canopy_boost:.0f}"
        )
    elif a.sky_pct > 40:
        sky_reduce = (a.sky_pct - 40) * 0.3
        distance -= sky_reduce
        reasons["Distance(sky)"] = (
            f"开阔天空 ({a.sky_pct:.1f}%)，距离感降低 -{sky_reduce:.0f}"
        )

    # More tree trunks (brown %) → higher Mass
    if a.brown_pct > 10:
        mass_boost = (a.brown_pct - 10) * 0.8
        mass += mass_boost
        reasons["Mass(trunk)"] = (
            f"棕色占比高 ({a.brown_pct:.1f}%)，"
            f"树干增加厚重感 +{mass_boost:.0f}"
        )

    # Darker overall → warmer tonality (higher Mass, lower Presence)
    if a.brightness < 80:
        dark_factor = (80 - a.brightness) / 80
        mass += dark_factor * 10
        presence -= dark_factor * 10
        reasons["Mass(dark)"] = (
            f"整体偏暗 (brightness={a.brightness:.1f})，"
            f"增加质感 +{dark_factor * 10:.0f}"
        )
        reasons["Presence(dark)"] = (
            f"暗部场景降低存在感/高频 -{dark_factor * 10:.0f}"
        )

    # Foliage density adjustments
    if a.foliage_density > 35:
        foliage_factor = (a.foliage_density - 35) * 0.2
        intensity_d -= foliage_factor
        strength += foliage_factor * 0.5
        reasons["Intensity(foliage)"] = (
            f"植被密度高 ({a.foliage_density:.1f}%)，"
            f"降低直接雨声强度 -{foliage_factor:.0f}"
        )

    # Brightness → Presence fine-tune
    if a.brightness > 130:
        bright_boost = (a.brightness - 130) * 0.1
        presence += bright_boost
        intensity_p += bright_boost * 0.5
        reasons["Presence(bright)"] = (
            f"高亮度场景 ({a.brightness:.1f})，"
            f"提升存在感/清晰度 +{bright_boost:.0f}"
        )

    # Vertical lines (bamboo) → adjust Strength
    if a.vertical_lines > 30:
        vert_boost = (a.vertical_lines - 30) * 0.2
        strength += vert_boost
        reasons["Strength(vert)"] = (
            f"垂直结构明显 ({a.vertical_lines:.1f})，"
            f"增加敲击力度 +{vert_boost:.0f}"
        )

    # Build preset names
    d_num = scene.distant
    s_num = scene.space
    c_num = scene.close
    d_en, d_cn = DISTANT_PRESETS[d_num]
    s_en, s_cn = SPACE_PRESETS[s_num]
    c_en, c_cn = CLOSE_PRESETS[c_num]

    # Base reasons for params that didn't get fine-tuned
    reasons.setdefault(
        "Density",
        f"场景基准密度 {scene.density}，{a.scene_type} 类型默认值",
    )
    reasons.setdefault(
        "Intensity(density)",
        f"雨声强度基准 {scene.intensity_d}",
    )
    reasons.setdefault(
        "Wetness",
        f"湿润度基准 {scene.wetness}，{a.wetness_desc}",
    )
    reasons.setdefault(
        "Distance(wetness)",
        f"距离感基准 {scene.distance}，{a.distance_reason}",
    )
    reasons.setdefault(
        "Mass",
        f"质感基准 {scene.mass}，{a.scene_type} 类型默认值",
    )
    reasons.setdefault(
        "Intensity(mass)",
        f"质感强度基准 {scene.intensity_m}",
    )
    reasons.setdefault(
        "Strength",
        f"力度基准 {scene.strength}",
    )
    reasons.setdefault(
        "Intensity(strength)",
        f"力度强度基准 {scene.intensity_s}",
    )
    reasons.setdefault(
        "Presence",
        f"存在感基准 {scene.presence}，{a.tonality_desc}",
    )
    reasons.setdefault(
        "Intensity(presence)",
        f"存在感强度基准 {scene.intensity_p}",
    )

    return VSTParams(
        scene_cn=scene.name_cn,
        scene_en=scene.name_en,
        distant=d_num,
        distant_name=f"{d_cn} {d_en}",
        space=s_num,
        space_name=f"{s_cn} {s_en}",
        close=c_num,
        close_name=f"{c_cn} {c_en}",
        density=_clamp(density),
        intensity_d=_clamp(intensity_d),
        wetness=_clamp(wetness),
        distance=_clamp(distance),
        mass=_clamp(mass),
        intensity_m=_clamp(intensity_m),
        strength=_clamp(strength),
        intensity_s=_clamp(intensity_s),
        presence=_clamp(presence),
        intensity_p=_clamp(intensity_p),
        reasons=reasons,
    )


# ---------------------------------------------------------------------------
# Step 4: Generate markdown report
# ---------------------------------------------------------------------------

def _preset_label(num: int, presets: dict[int, tuple[str, str]]) -> str:
    """Format a preset as ``name_en(number)``."""
    en, _cn = presets[num]
    return f"{en}({num:02d})"


def generate_report(
    video_id: str,
    analysis: FrameAnalysis,
    params: VSTParams,
) -> str:
    """Render the full markdown report."""
    a = analysis
    p = params

    # Distant / Space / Close reasoning
    d_label = _preset_label(p.distant, DISTANT_PRESETS)
    s_label = _preset_label(p.space, SPACE_PRESETS)
    c_label = _preset_label(p.close, CLOSE_PRESETS)

    d_reason = _distant_reason(a)
    s_reason = _space_reason(a)
    c_reason = _close_reason(a)

    water_desc = (
        f"检测到水面 (score={a.water_score:.1f})" if a.water_detected
        else f"未检测到明显水面 (score={a.water_score:.1f})"
    )

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
| **水面检测** | {water_desc} |

## 声场推理

| 维度 | 判断 | 依据 |
|------|------|------|
| **远景** | {d_label} | {d_reason} |
| **空间** | {s_label} | {s_reason} |
| **近景** | {c_label} | {c_reason} |
| **雨势** | {a.rain_level} | {a.rain_level_reason} |
| **距离** | {a.distance_level} | {a.distance_reason} |
| **湿度** | {a.wetness_desc} | {a.wetness_reason} |
| **Tonality** | {a.tonality_desc} | {a.tonality_reason} |

## RAIN VST 推荐参数

```
场景名：{p.scene_cn}   {p.scene_en}

远景 Distant:  {p.distant:02d} ({p.distant_name})
空间 Space:    {p.space:02d} ({p.space_name})
近景 Close:    {p.close:02d} ({p.close_name})

Density/Intensity:    {p.density}/{p.intensity_d}
Wetness/Distance:     {p.wetness}/{p.distance}
MASS/Intensity:       {p.mass}/{p.intensity_m}
STRENGTH/Intensity:   {p.strength}/{p.intensity_s}
PRESENCE/Intensity:   {p.presence}/{p.intensity_p}
```

## 参数设计理由

| 参数 | 值 | 理由 |
|------|-----|------|
| **Density** | {p.density} | {p.reasons.get('Density', '')} |
| **Intensity (Density)** | {p.intensity_d} | {p.reasons.get('Intensity(density)', '')} |
| **Wetness** | {p.wetness} | {p.reasons.get('Wetness', '')} |
| **Distance** | {p.distance} | {p.reasons.get('Distance(wetness)', '')} |
| **MASS** | {p.mass} | {p.reasons.get('Mass', p.reasons.get('Mass(trunk)', p.reasons.get('Mass(dark)', '')))} |
| **Intensity (MASS)** | {p.intensity_m} | {p.reasons.get('Intensity(mass)', '')} |
| **STRENGTH** | {p.strength} | {p.reasons.get('Strength', p.reasons.get('Strength(vert)', ''))} |
| **Intensity (STRENGTH)** | {p.intensity_s} | {p.reasons.get('Intensity(strength)', '')} |
| **PRESENCE** | {p.presence} | {p.reasons.get('Presence', p.reasons.get('Presence(dark)', p.reasons.get('Presence(bright)', '')))} |
| **Intensity (PRESENCE)** | {p.intensity_p} | {p.reasons.get('Intensity(presence)', '')} |
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
) -> Path:
    """Analyze a loop video's first frame and output RAIN VST parameters.

    Args:
        video_path: Path to the input video file.
        output_dir: Directory to write the output PNG and MD files.
        on_progress: Optional callback receiving status message strings.

    Returns:
        The output directory path containing the generated files.
    """
    video_path = Path(video_path)
    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    if not video_path.is_file():
        raise FileNotFoundError(f"视频文件不存在: {video_path}")

    video_id = extract_video_id(video_path)
    _notify(on_progress, f"开始分析: {video_id}")

    # Step 1: Extract first frame
    frame_path = output_dir / f"{video_id}.png"
    extract_first_frame(video_path, frame_path, on_progress)

    # Step 2: Analyze frame
    analysis = analyze_frame(frame_path, on_progress)

    # Step 3: Map to VST params
    _notify(on_progress, "正在映射 VST 参数")
    params = map_to_vst_params(analysis)

    # Step 4: Generate markdown report
    _notify(on_progress, "正在生成报告")
    report = generate_report(video_id, analysis, params)
    report_path = output_dir / f"{video_id}.md"
    report_path.write_text(report, encoding="utf-8")
    _notify(on_progress, f"报告已保存: {report_path.name}")

    return output_dir


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def main() -> None:
    """CLI entry point for standalone execution."""
    parser = argparse.ArgumentParser(
        description="分析循环视频首帧，输出 RAIN VST 参数建议",
    )
    parser.add_argument(
        "video",
        type=Path,
        help="输入视频文件路径",
    )
    parser.add_argument(
        "--output-dir", "-o",
        type=Path,
        default=None,
        help="输出目录（默认: 视频同级目录）",
    )
    args = parser.parse_args()

    video_path: Path = args.video.resolve()
    if not video_path.is_file():
        print(f"错误: 视频文件不存在: {video_path}", file=sys.stderr)
        sys.exit(1)

    output_dir: Path = args.output_dir or video_path.parent
    output_dir = output_dir.resolve()

    def progress(msg: str) -> None:
        print(f"  → {msg}")

    try:
        result_dir = analyze_video(video_path, output_dir, on_progress=progress)
        video_id = extract_video_id(video_path)
        print(f"\n完成! 输出目录: {result_dir}")
        print(f"  报告: {result_dir / f'{video_id}.md'}")
        print(f"  首帧: {result_dir / f'{video_id}.png'}")
    except RuntimeError as exc:
        print(f"错误: {exc}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
