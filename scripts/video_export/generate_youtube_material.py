#!/usr/bin/env python3
"""Generate YouTube metadata (.md) and thumbnail for export_mp4 outputs."""

from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
from collections.abc import Callable
from pathlib import Path

try:
    from PIL import Image, ImageDraw, ImageFont
except ImportError:
    print("Error: Pillow required. Install with: pip install pillow", file=sys.stderr)
    sys.exit(1)

SCRIPT_DIR = Path(__file__).resolve().parent
REPO_ROOT = SCRIPT_DIR.parent.parent
PRESETS_PATH = SCRIPT_DIR / "youtube_presets.json"
BADGE_4K_PATH = SCRIPT_DIR / "4k.png"
THUMB_W, THUMB_H = 1280, 720
BL_MARGIN_LEFT = 60
BL_MARGIN_RIGHT = 60
BL_MARGIN_BOTTOM = 52
BL_GAP_BADGE_TITLE = 28
BL_GAP_TITLE_SUB = 40
BL_TITLE_SIZE = 75
BL_SUB_SIZE = 36
BL_BADGE_MAX_HEIGHT = 72
THUMB_MARGIN = 20
TITLE_ALPHA = int(255 * 0.80)  # white 80% opacity
TITLE_TOP_Y = 200  # title top edge, px from thumbnail top
TITLE_MAX_WIDTH_RATIO = 0.88
TITLE_FONT_START = 28  # 50% of previous 56
TITLE_FONT_MIN = 14
BADGE_MAX_HEIGHT = 72
BADGE_MARGIN_LEFT = 70   # THUMB_MARGIN + 50
BADGE_MARGIN_BOTTOM = 70
DEFAULT_THUMB_TITLE = "RAIN ASMR"
SUBTITLE_MAX_WORDS = 10
TEXT_SHADOW_OFFSET = (3, 3)
TEXT_SHADOW_COLOR = (0, 0, 0, 20)

FONT_CANDIDATES = [
    Path("/System/Library/Fonts/Supplemental/Arial Bold.ttf"),
    Path("/System/Library/Fonts/Supplemental/Arial.ttf"),
    Path("/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf"),
    Path("/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf"),
    Path.home() / ".local/share/fonts/PingFangSC-Medium.ttf",
    Path("/usr/share/fonts/opentype/noto/NotoSansCJK-Bold.ttc"),
]
FONT_BOLD_CANDIDATES = [
    Path("/System/Library/Fonts/Supplemental/Arial Bold.ttf"),
    Path("/System/Library/Fonts/Supplemental/Helvetica Bold.ttf"),
    Path("/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf"),
]
FONT_REG_CANDIDATES = [
    Path("/System/Library/Fonts/Supplemental/Arial.ttf"),
    Path("/System/Library/Fonts/Supplemental/Helvetica.ttf"),
    Path("/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf"),
]


def load_font(size: int) -> ImageFont.FreeTypeFont | ImageFont.ImageFont:
    for path in FONT_CANDIDATES:
        if path.exists():
            try:
                return ImageFont.truetype(str(path), size=size)
            except OSError:
                continue
    return ImageFont.load_default()


def ffprobe_video(path: Path) -> dict:
    cmd = [
        "ffprobe", "-v", "error",
        "-select_streams", "v:0",
        "-show_entries", "stream=width,height,r_frame_rate,codec_name",
        "-show_entries", "format=duration,size,bit_rate",
        "-of", "json", str(path),
    ]
    out = subprocess.check_output(cmd, text=True)
    data = json.loads(out)
    stream = data["streams"][0]
    fmt = data["format"]
    num, den = stream["r_frame_rate"].split("/")
    fps = round(int(num) / int(den), 2)
    duration_s = float(fmt["duration"])
    h = int(duration_s // 3600)
    m = int((duration_s % 3600) // 60)
    if h:
        duration_human = f"{h}小时{m}分" if m else f"{h}小时"
        duration_en = f"{h}h {m}m" if m else f"{h} hour{'s' if h > 1 else ''}"
    else:
        duration_human = f"{m}分钟"
        duration_en = f"{m} min"
    return {
        "width": stream["width"],
        "height": stream["height"],
        "fps": fps,
        "codec": stream["codec_name"],
        "duration_s": duration_s,
        "duration_human": duration_human,
        "duration_en": duration_en,
        "size_mb": int(fmt["size"]) / (1024 * 1024),
        "bitrate_mbps": int(fmt["bit_rate"]) / 1_000_000,
    }


def parse_basename(stem: str) -> dict:
    """Parse names like stream_heal_3h_4k_gpu."""
    parts = stem.split("_")
    info: dict = {"project": stem, "duration": "", "resolution": "", "encoder": ""}
    if len(parts) >= 2:
        # find duration token (2min, 3h, etc.)
        for i, p in enumerate(parts):
            if re.match(r"^\d+(min|h|hr|hours?)$", p, re.I) or re.match(r"^\d+min$", p):
                info["duration"] = p
                info["project"] = "_".join(parts[:i]) if i else stem
                rest = parts[i + 1:]
                if rest and re.match(r"^4k$", rest[0], re.I):
                    info["resolution"] = rest[0].upper()
                    rest = rest[1:]
                if rest and rest[0].lower() in ("gpu", "nvenc", "cpu"):
                    info["encoder"] = rest[0].lower()
                break
    return info


def load_preset(project: str) -> dict:
    if not PRESETS_PATH.exists():
        return {}
    presets = json.loads(PRESETS_PATH.read_text(encoding="utf-8"))
    return presets.get(project, {})


def resolve_badge_path(preset: dict) -> Path:
    raw = preset.get("badge_path", "")
    if raw:
        p = Path(raw)
        if p.is_file():
            return p
        repo_path = REPO_ROOT / raw
        if repo_path.is_file():
            return repo_path
    if BADGE_4K_PATH.is_file():
        return BADGE_4K_PATH
    return BADGE_4K_PATH


def load_font_from(candidates: list[Path], size: int) -> ImageFont.FreeTypeFont | ImageFont.ImageFont:
    for path in candidates:
        if path.exists():
            try:
                return ImageFont.truetype(str(path), size=size)
            except OSError:
                continue
    return ImageFont.load_default()


def wrap_text(draw: ImageDraw.ImageDraw, text: str, font, max_width: int) -> list[str]:
    words = text.split()
    lines: list[str] = []
    current = ""
    for word in words:
        trial = f"{current} {word}".strip()
        bbox = draw.textbbox((0, 0), trial, font=font)
        if bbox[2] - bbox[0] <= max_width:
            current = trial
        else:
            if current:
                lines.append(current)
            current = word
    if current:
        lines.append(current)
    return lines


def text_block_height(draw: ImageDraw.ImageDraw, lines: list[str], font) -> int:
    if not lines:
        return 0
    heights = [
        draw.textbbox((0, 0), line, font=font)[3] - draw.textbbox((0, 0), line, font=font)[1]
        for line in lines
    ]
    return sum(heights)


def resize_badge(badge_path: Path) -> Image.Image:
    badge = Image.open(badge_path).convert("RGBA")
    if badge.height > BL_BADGE_MAX_HEIGHT:
        ratio = BL_BADGE_MAX_HEIGHT / badge.height
        badge = badge.resize(
            (int(badge.width * ratio), int(badge.height * ratio)),
            Image.Resampling.LANCZOS,
        )
    return badge


def extract_frame(video: Path, out_png: Path, t: float) -> None:
    proc = subprocess.run(
        [
            "ffmpeg", "-y", "-ss", str(t), "-i", str(video),
            "-vframes", "1", "-q:v", "2", str(out_png),
        ],
        capture_output=True,
        text=True,
    )
    if proc.returncode != 0:
        err = (proc.stderr or proc.stdout or "ffmpeg failed").strip()
        raise RuntimeError(f"ffmpeg 截帧失败 @ {t}s：{err}")
    if not out_png.is_file() or out_png.stat().st_size == 0:
        raise RuntimeError(f"ffmpeg 截帧失败 @ {t}s：输出为空（视频可能短于 {t}s）")


def _region_stats(img: Image.Image, box: tuple[int, int, int, int]) -> dict[str, float]:
    crop = img.crop(box).resize((64, 64), Image.Resampling.BILINEAR)
    flat = crop.get_flattened_data() if hasattr(crop, "get_flattened_data") else crop.getdata()
    pixels = list(flat)
    n = len(pixels)
    if n == 0:
        return {"r": 0, "g": 0, "b": 0, "brightness": 0}
    r = sum(p[0] for p in pixels) / n
    g = sum(p[1] for p in pixels) / n
    b = sum(p[2] for p in pixels) / n
    return {"r": r, "g": g, "b": b, "brightness": (r + g + b) / 3}


def limit_words(text: str, max_words: int = SUBTITLE_MAX_WORDS) -> str:
    words = text.split()
    if len(words) <= max_words:
        return text
    return " ".join(words[:max_words])


def analyze_frame_scene(frame_path: Path) -> dict:
    """从缩略图帧启发式推断场景（标题/说明/副标题共用）。"""
    img = Image.open(frame_path).convert("RGB")
    w, h = img.size

    top = _region_stats(img, (0, 0, w, h // 5))
    bg = _region_stats(img, (w // 3, h // 4, 2 * w // 3, h // 2))
    center = _region_stats(img, (w // 4, h // 3, 3 * w // 4, 2 * h // 3))
    bottom_left = _region_stats(img, (0, h // 2, w // 2, h))
    bottom_right = _region_stats(img, (w // 2, h // 2, w, h))

    misty = top["brightness"] > center["brightness"] + 12 or top["b"] > top["r"] + 10
    water = (
        bg["b"] > bg["r"] + 8
        and bg["g"] > bg["r"] + 5
        and bg["brightness"] > 95
    )
    green = center["g"] > center["r"] * 1.06 and center["g"] > center["b"] * 1.02
    grass = bottom_left["g"] > 90 and bottom_left["g"] > bottom_left["r"] * 1.12
    path = (
        abs(bottom_right["r"] - bottom_right["g"]) < 20
        and 55 < bottom_right["brightness"] < 155
        and bottom_right["r"] < center["g"]
    )

    if grass and water and path:
        key = "park_pond_path"
    elif grass and water:
        key = "park_pond"
    elif green and water and path:
        key = "grove_pond_path"
    elif green and water:
        key = "grove_pond"
    elif grass and path:
        key = "park_path"
    elif green and path:
        key = "grove_path"
    elif grass:
        key = "park"
    elif green:
        key = "grove"
    elif water:
        key = "pond"
    else:
        key = "nature"

    scenes = {
        "park_pond_path": {
            "place_zh_short": "公园荷塘",
            "place_en_short": "Park Lotus Pond",
            "place_zh_long": "公园荷塘雨景",
            "place_en_long": "rainy park with lotus pond and stone path",
            "bullet_zh": "🪷 荷塘湿地 · 蜿蜒石径 · 雨后草坪",
            "bullet_en": "🪷 Lotus pond and wetland · winding stone path · rain-soaked lawn",
            "tags_zh": ["公园", "荷塘", "荷花"],
            "tags_en": ["park", "lotus pond", "lotus"],
            "hashtags_zh": "#雨声 #ASMR #白噪音 #4K #助眠 #荷花 #公园",
            "hashtags_en": "#rain #ASMR #whitenoise #4K #sleep #lotus #park",
            "thumb_place": "park with lotus pond and stone path",
        },
        "park_pond": {
            "place_zh_short": "公园荷塘",
            "place_en_short": "Park Lotus Pond",
            "place_zh_long": "公园荷塘雨景",
            "place_en_long": "rainy park beside a lotus pond",
            "bullet_zh": "🪷 荷塘荷花 · 雨后草坪 · 远处林木",
            "bullet_en": "🪷 Lotus pond and flowers · rain-soaked lawn · distant trees",
            "tags_zh": ["公园", "荷塘", "荷花"],
            "tags_en": ["park", "lotus pond", "lotus"],
            "hashtags_zh": "#雨声 #ASMR #白噪音 #4K #助眠 #荷花 #公园",
            "hashtags_en": "#rain #ASMR #whitenoise #4K #sleep #lotus #park",
            "thumb_place": "park beside a lotus pond",
        },
        "grove_pond_path": {
            "place_zh_short": "林间荷塘",
            "place_en_short": "Forest Lotus Grove",
            "place_zh_long": "林间荷塘雨景",
            "place_en_long": "rainy forest grove by a lotus pond path",
            "bullet_zh": "🪷 林间荷塘 · 石径小径 · 雨后绿树",
            "bullet_en": "🪷 Forest lotus pond · stone path · rain-wet green trees",
            "tags_zh": ["林间", "荷塘", "小径"],
            "tags_en": ["forest grove", "lotus pond", "stone path"],
            "hashtags_zh": "#雨声 #ASMR #白噪音 #4K #助眠 #林间 #荷花",
            "hashtags_en": "#rain #ASMR #whitenoise #4K #sleep #forest #lotus",
            "thumb_place": "forest grove by a lotus pond path",
        },
        "grove_pond": {
            "place_zh_short": "林间荷塘",
            "place_en_short": "Misty Lotus Grove",
            "place_zh_long": "林间荷塘雨景",
            "place_en_long": "misty forest grove by a lotus pond",
            "bullet_zh": "🪷 雾气荷塘 · 雨后林木 · 静谧湿地",
            "bullet_en": "🪷 Misty lotus pond · rain-wet forest · quiet wetland",
            "tags_zh": ["林间", "荷塘", "雾气"],
            "tags_en": ["forest grove", "lotus pond", "misty rain"],
            "hashtags_zh": "#雨声 #ASMR #白噪音 #4K #助眠 #林间 #荷花",
            "hashtags_en": "#rain #ASMR #whitenoise #4K #sleep #forest #lotus",
            "thumb_place": "forest grove by a misty lotus pond",
        },
        "park_path": {
            "place_zh_short": "林间公园",
            "place_en_short": "Rainy Forest Park",
            "place_zh_long": "林间公园雨景",
            "place_en_long": "rainy forest park with a winding stone path",
            "bullet_zh": "🌳 绿树草坪 · 蜿蜒石径 · 雨后湿地",
            "bullet_en": "🌳 Green trees and lawn · winding stone path · wet ground after rain",
            "tags_zh": ["公园", "林间", "石径"],
            "tags_en": ["forest park", "rainy park", "stone path"],
            "hashtags_zh": "#雨声 #ASMR #白噪音 #4K #助眠 #公园 #自然音",
            "hashtags_en": "#rain #ASMR #whitenoise #4K #sleep #park #nature",
            "thumb_place": "park with a winding stone path",
        },
        "grove_path": {
            "place_zh_short": "林间小径",
            "place_en_short": "Rainy Forest Path",
            "place_zh_long": "林间小径雨景",
            "place_en_long": "rainy forest grove along a stone path",
            "bullet_zh": "🌳 雨后林木 · 石径蜿蜒 · 静谧林间",
            "bullet_en": "🌳 Rain-wet forest trees · winding stone path · quiet grove",
            "tags_zh": ["林间", "小径", "雨景"],
            "tags_en": ["forest path", "stone path", "rainy forest"],
            "hashtags_zh": "#雨声 #ASMR #白噪音 #4K #助眠 #林间 #自然音",
            "hashtags_en": "#rain #ASMR #whitenoise #4K #sleep #forest #nature",
            "thumb_place": "forest grove along a stone path",
        },
        "park": {
            "place_zh_short": "公园绿地",
            "place_en_short": "Rainy Green Park",
            "place_zh_long": "公园绿地雨景",
            "place_en_long": "green park in the rain",
            "bullet_zh": "🌳 雨后草坪 · 开阔绿地 · 远处林木",
            "bullet_en": "🌳 Rain-soaked lawn · open green park · distant trees",
            "tags_zh": ["公园", "绿地", "雨景"],
            "tags_en": ["green park", "rainy park", "lawn"],
            "hashtags_zh": "#雨声 #ASMR #白噪音 #4K #助眠 #公园 #自然音",
            "hashtags_en": "#rain #ASMR #whitenoise #4K #sleep #park #nature",
            "thumb_place": "green park in the rain",
        },
        "grove": {
            "place_zh_short": "林间雨景",
            "place_en_short": "Lush Rainy Grove",
            "place_zh_long": "林间雨景",
            "place_en_long": "lush forest grove in the rain",
            "bullet_zh": "🌳 雨后林木 · 浓绿树冠 · 静谧氛围",
            "bullet_en": "🌳 Rain-wet trees · lush green canopy · peaceful mood",
            "tags_zh": ["林间", "雨景", "自然"],
            "tags_en": ["forest grove", "rainy forest", "lush green"],
            "hashtags_zh": "#雨声 #ASMR #白噪音 #4K #助眠 #林间 #自然音",
            "hashtags_en": "#rain #ASMR #whitenoise #4K #sleep #forest #nature",
            "thumb_place": "lush forest grove in the rain",
        },
        "pond": {
            "place_zh_short": "荷花池",
            "place_en_short": "Peaceful Lotus Pond",
            "place_zh_long": "荷花池雨景",
            "place_en_long": "peaceful lotus pond in the rain",
            "bullet_zh": "🪷 荷叶荷花 · 雨中湿地 · 静谧水面",
            "bullet_en": "🪷 Lotus leaves and flowers · rainy wetland · calm water",
            "tags_zh": ["荷花池", "荷塘", "荷花"],
            "tags_en": ["lotus pond", "lotus", "pond"],
            "hashtags_zh": "#雨声 #ASMR #白噪音 #4K #助眠 #荷花 #自然音",
            "hashtags_en": "#rain #ASMR #whitenoise #4K #sleep #lotus #nature",
            "thumb_place": "peaceful lotus pond in the rain",
        },
        "nature": {
            "place_zh_short": "自然雨景",
            "place_en_short": "Peaceful Rain Nature",
            "place_zh_long": "自然雨景",
            "place_en_long": "quiet nature scene in the rain",
            "bullet_zh": "🌧 自然雨声 · 静谧氛围 · 无音乐无人声",
            "bullet_en": "🌧 Natural rain ambience · peaceful mood · no music or voice",
            "tags_zh": ["自然", "雨景"],
            "tags_en": ["nature rain", "ambient"],
            "hashtags_zh": "#雨声 #ASMR #白噪音 #4K #助眠 #自然音",
            "hashtags_en": "#rain #ASMR #whitenoise #4K #sleep #nature",
            "thumb_place": "quiet nature scene in the rain",
        },
    }

    scene = dict(scenes[key])
    scene["scene_key"] = key
    scene["misty"] = misty
    mood = "Misty rainy" if misty else "Peaceful rainy"
    scene["thumb_subtitle"] = limit_words(f"{mood} {scene['thumb_place']}")
    return scene


# scripts/video_export/material_ref/forest_rain.md — 爆款标题/描述/Tags/封面叠字模版
FOREST_RAIN_REF = Path(__file__).resolve().parent / "material_ref" / "forest_rain.md"

FOREST_RAIN_THUMB_HEAVY_SCENES = frozenset({
    "grove_path",
    "grove_pond_path",
    "park_path",
    "park_pond_path",
})
FOREST_RAIN_CORE_TAGS = [
    "rain sounds",
    "rain",
    "rain sounds for sleeping",
    "rain and thunder",
    "rain and thunder sounds",
    "heavy rain",
    "sleep",
    "insomnia",
    "white noise",
    "sleep sounds",
    "4k rain loop",
    "rain at night",
]

FOREST_RAIN_SCENE_TAGS = [
    "nature sounds",
    "thunder sounds",
    "thunder",
    "thunderstorm",
    "thunderstorm sounds",
    "relaxing rain",
    "asmr",
    "forest rain",
]

VIRAL_SCENE_RAIN: dict[str, str] = {
    "grove": "Calming Rain on Forest Leaves",
    "grove_path": "Heavy Rain on Forest Path",
    "grove_pond": "Rain on Misty Forest Grove",
    "grove_pond_path": "Rain on Forest Grove Path",
    "park": "Gentle Rain on Green Park",
    "park_path": "Rain on Forest Park Path",
    "park_pond": "Rain Beside a Lotus Pond",
    "park_pond_path": "Rain on Park Lotus Path",
    "pond": "Peaceful Rain on Lotus Pond",
    "nature": "Calming Rain in Nature",
}


def duration_title_en(meta: dict) -> str:
    """3 hour(s) → 3 Hours；用于爆款标题。"""
    s = int(meta["duration_s"])
    h = s // 3600
    m = (s % 3600) // 60
    if h >= 1:
        return f"{h} Hour{'s' if h != 1 else ''}"
    if m >= 1:
        return f"{m} Minutes"
    return f"{s} Seconds"


def viral_format_en(meta: dict, *, show_4k: bool) -> str:
    """三段式「格式」：本系列为循环雨景实景（非黑屏）。"""
    dur = duration_title_en(meta)
    k4 = "4K " if show_4k else ""
    return f"{dur} {k4}Rain Loop ASMR".strip()


def viral_format_zh(meta: dict, *, show_4k: bool) -> str:
    dur = meta["duration_human"]
    k4 = "4K " if show_4k else ""
    return f"{dur}{k4}雨景循环 ASMR"


def forest_rain_benefit_en(scene_key: str, scene_rain: str) -> str:
    if scene_key in FOREST_RAIN_THUMB_HEAVY_SCENES or scene_rain.startswith("Heavy"):
        return "Overcome Stress to Sleep Instantly"
    return "Deep Sleep Instantly"


def build_forest_rain_youtube_copy(scene: dict, meta: dict, *, show_4k: bool = False) -> dict:
    """按 material_ref/forest_rain.md T1：利益 | 场景 | 格式（雨景循环，非黑屏）。"""
    scene_key = scene.get("scene_key", "nature")
    scene_rain = VIRAL_SCENE_RAIN.get(scene_key, f"Calming Rain on {scene['place_en_short']}")
    hear = scene.get("thumb_place", scene["place_en_long"])
    benefit = forest_rain_benefit_en(scene_key, scene_rain)
    fmt_en = viral_format_en(meta, show_4k=show_4k)
    fmt_zh = viral_format_zh(meta, show_4k=show_4k)

    title_en = f"{benefit} | {scene_rain} | {fmt_en}"
    title_zh = f"深度入眠 | {scene['place_zh_short']}雨声 | {fmt_zh}"

    desc_en = (
        f"Fall asleep fast with gentle rain sounds on {hear}.\n\n"
        "✅ Deep sleep & beat insomnia\n"
        "✅ Anxiety / stress / tinnitus relief\n"
        "✅ Perfect for study, meditation, baby sleep\n\n"
        f"What you'll see & hear: seamless {hear} rain loop, soft ambience, distant thunder...\n\n"
        "Subscribe for more relaxing rain sounds 🌧️\n"
        "Like if this helped you sleep!\n\n"
        "#rainsounds #sleepsounds #asmr #whitenoise #insomnia #relaxingrain #forestrain"
    )
    desc_zh = (
        f"伴着{scene['place_zh_long']}的雨声快速入睡。\n\n"
        "✅ 深度睡眠 · 缓解失眠\n"
        "✅ 减轻焦虑、压力与耳鸣\n"
        "✅ 适合学习、冥想、宝宝入睡\n\n"
        f"你将听到：{scene['bullet_zh']}\n\n"
        "订阅获取更多放松雨声 🌧️\n"
        "有帮助请点赞！\n\n"
        "#雨声 #助眠 #ASMR #白噪音 #失眠 #放松雨声 #森林雨"
    )

    tags = list(dict.fromkeys(FOREST_RAIN_CORE_TAGS + FOREST_RAIN_SCENE_TAGS + scene.get("tags_en", [])))

    return {
        "title_zh": title_zh,
        "title_en": title_en,
        "description_zh": desc_zh,
        "description_en": desc_en,
        "tags": tags,
        "subtitle_zh": "睡眠 · 专注 · 冥想 · 减压",
        "subtitle_en": "Sleep · Focus · Meditation · Stress Relief",
    }


def build_forest_rain_thumb_text(scene: dict, meta: dict, *, show_4k: bool = False) -> tuple[str, str]:
    """封面叠字：T1 利益 | 场景 | 格式（雨景循环，非黑屏）。"""
    scene_key = scene.get("scene_key", "nature")
    scene_rain = VIRAL_SCENE_RAIN.get(scene_key, f"Calming Rain on {scene['place_en_short']}")
    benefit = forest_rain_benefit_en(scene_key, scene_rain)
    fmt_en = viral_format_en(meta, show_4k=show_4k)

    thumb_title = "Overcome Stress to Sleep" if benefit.startswith("Overcome") else "Deep Sleep Instantly"
    thumb_subtitle = limit_words(f"{scene_rain} | {fmt_en}", max_words=14)
    return thumb_title, thumb_subtitle


def auto_thumb_subtitle(frame_path: Path) -> str:
    return analyze_frame_scene(frame_path)["thumb_subtitle"]


def build_rain_youtube_copy(scene: dict, meta: dict) -> dict:
    """根据画面场景生成 Rain 系列 YouTube 文案。"""
    duration_zh = meta["duration_human"]
    duration_en = meta["duration_en"]
    res = f"{meta['width']}×{meta['height']}"
    fps = f"{meta['fps']} fps"

    title_zh = f"【4K】{duration_zh}雨声 ASMR · {scene['place_zh_short']}"
    title_en = f"{duration_en.title()} Rain ASMR in 4K | {scene['place_en_short']}"

    desc_zh = (
        f"{duration_zh}{scene['place_zh_long']}，4K 超清画面配合真实雨声，"
        f"适合入睡、专注工作、冥想与减压放松。\n\n"
        f"🌧 纯自然雨声循环，无音乐无人声\n"
        f"{scene['bullet_zh']}\n"
        f"🎧 建议佩戴耳机获得最佳沉浸体验\n"
        f"⏱ 时长：{duration_zh}\n"
        f"📺 分辨率：{res} · {fps}\n\n"
        f"{scene['hashtags_zh']}"
    )
    desc_en = (
        f"{duration_en} of {scene['place_en_long']} — 4K visuals with natural rain sounds "
        f"for sleep, deep focus, meditation, and stress relief.\n\n"
        f"🌧 Pure rain ambience, no music, no voice\n"
        f"{scene['bullet_en']}\n"
        f"🎧 Headphones recommended for full immersion\n"
        f"⏱ Duration: {duration_en}\n"
        f"📺 Resolution: {res} · {fps}\n\n"
        f"{scene['hashtags_en']}"
    )

    base_tags_zh = [
        "雨声", "雨声ASMR", "白噪音", "4K", "ASMR", "自然声音", "助眠", "冥想", "专注",
    ]
    base_tags_en = [
        "rain sounds", "rain ASMR", "white noise", "sleep sounds",
        "nature sounds", "relaxation", "4K nature",
    ]
    tags = base_tags_zh + scene["tags_zh"] + base_tags_en + scene["tags_en"]

    return {
        "title_zh": title_zh,
        "title_en": title_en,
        "description_zh": desc_zh,
        "description_en": desc_en,
        "tags": tags,
    }


def resolve_youtube_copy(
    preset: dict,
    scene: dict | None,
    meta: dict,
    video_stem: str,
    title_zh_arg: str,
    title_en_arg: str,
) -> dict:
    if scene and preset.get("auto_from_scene"):
        copy = build_rain_youtube_copy(scene, meta)
        if title_zh_arg:
            copy["title_zh"] = title_zh_arg
        if title_en_arg:
            copy["title_en"] = title_en_arg
        copy["subtitle_zh"] = preset.get("subtitle_zh", "睡眠 · 专注 · 冥想 · 减压")
        copy["subtitle_en"] = preset.get("subtitle_en", "Sleep · Focus · Meditation · Stress Relief")
        return copy

    title_zh = title_zh_arg or preset.get("title_zh", video_stem)
    title_en = title_en_arg or preset.get("title_en", video_stem)
    desc_zh = preset.get("description_zh", "").format(
        duration=meta["duration_human"],
        resolution=f"{meta['width']}×{meta['height']}",
        fps=f"{meta['fps']} fps",
    )
    desc_en = preset.get("description_en", "").format(
        duration=meta["duration_en"],
        resolution=f"{meta['width']}×{meta['height']}",
        fps=f"{meta['fps']} fps",
    )
    return {
        "title_zh": title_zh,
        "title_en": title_en,
        "description_zh": desc_zh,
        "description_en": desc_en,
        "tags": preset.get("tags", []),
        "subtitle_zh": preset.get("subtitle_zh", ""),
        "subtitle_en": preset.get("subtitle_en", ""),
    }


def resolve_thumb_text(
    scene: dict,
    preset: dict,
    thumb_title_arg: str,
    thumb_subtitle_arg: str,
) -> tuple[str, str]:
    if thumb_title_arg:
        thumb_title = thumb_title_arg
    elif preset.get("thumb_title_en"):
        thumb_title = preset["thumb_title_en"]
    else:
        thumb_title = DEFAULT_THUMB_TITLE

    if thumb_subtitle_arg:
        thumb_subtitle = limit_words(thumb_subtitle_arg)
    elif preset.get("thumb_subtitle_en"):
        thumb_subtitle = limit_words(preset["thumb_subtitle_en"])
    else:
        thumb_subtitle = scene["thumb_subtitle"]

    return thumb_title, thumb_subtitle


def draw_text_with_shadow(
    draw: ImageDraw.ImageDraw,
    xy: tuple[int, int],
    text: str,
    font,
    fill: tuple[int, int, int, int] | tuple[int, int, int],
    *,
    anchor: str | None = None,
) -> None:
    """先画偏移阴影，再画正文。"""
    ox, oy = TEXT_SHADOW_OFFSET
    shadow_xy = (xy[0] + ox, xy[1] + oy)
    if anchor:
        draw.text(shadow_xy, text, font=font, fill=TEXT_SHADOW_COLOR, anchor=anchor)
        draw.text(xy, text, font=font, fill=fill, anchor=anchor)
    else:
        draw.text(shadow_xy, text, font=font, fill=TEXT_SHADOW_COLOR)
        draw.text(xy, text, font=font, fill=fill)


def fit_title_font(draw: ImageDraw.ImageDraw, text: str, max_width: int, start_size: int = TITLE_FONT_START):
    for size in range(start_size, TITLE_FONT_MIN - 1, -2):
        font = load_font(size)
        bbox = draw.textbbox((0, 0), text, font=font)
        if bbox[2] - bbox[0] <= max_width:
            return font, bbox
    font = load_font(TITLE_FONT_MIN)
    return font, draw.textbbox((0, 0), text, font=font)


def paste_4k_badge(overlay: Image.Image, badge_path: Path) -> None:
    badge = Image.open(badge_path).convert("RGBA")
    if badge.height > BADGE_MAX_HEIGHT:
        ratio = BADGE_MAX_HEIGHT / badge.height
        badge = badge.resize(
            (int(badge.width * ratio), int(badge.height * ratio)),
            Image.Resampling.LANCZOS,
        )
    bx = BADGE_MARGIN_LEFT
    by = THUMB_H - badge.height - BADGE_MARGIN_BOTTOM
    overlay.paste(badge, (bx, by), badge)


def make_thumbnail(
    base_png: Path,
    out_jpg: Path,
    title_en: str,
    show_4k: bool = True,
    badge_path: Path = BADGE_4K_PATH,
) -> None:
    """Layout ref: thumbnail_ref.png — center title, 4K bottom-left, no duration badge."""
    img = Image.open(base_png).convert("RGBA")
    img = img.resize((THUMB_W, THUMB_H), Image.Resampling.LANCZOS)
    overlay = Image.new("RGBA", img.size, (0, 0, 0, 0))
    draw = ImageDraw.Draw(overlay)

    max_w = int(THUMB_W * TITLE_MAX_WIDTH_RATIO)
    font, bbox = fit_title_font(draw, title_en, max_w)
    cx = THUMB_W // 2
    cy = TITLE_TOP_Y
    draw_text_with_shadow(
        draw, (cx, cy), title_en, font, (255, 255, 255, TITLE_ALPHA), anchor="mt",
    )

    if show_4k and badge_path.is_file():
        paste_4k_badge(overlay, badge_path)
    elif show_4k:
        print(f"Warning: 4K badge not found: {badge_path}", file=sys.stderr)

    composed = Image.alpha_composite(img, overlay).convert("RGB")
    composed.save(out_jpg, "JPEG", quality=92, optimize=True)


def make_thumbnail_bottom_left(
    base_png: Path,
    out_jpg: Path,
    title_en: str,
    subtitle_en: str,
    *,
    show_4k: bool = True,
    badge_path: Path = BADGE_4K_PATH,
) -> None:
    """Layout: 4K badge + title + subtitle, bottom-left stack."""
    img = Image.open(base_png).convert("RGBA")
    img = img.resize((THUMB_W, THUMB_H), Image.Resampling.LANCZOS)
    overlay = Image.new("RGBA", img.size, (0, 0, 0, 0))
    draw = ImageDraw.Draw(overlay)

    font_title = load_font_from(FONT_BOLD_CANDIDATES, BL_TITLE_SIZE)
    font_sub = load_font_from(FONT_REG_CANDIDATES, BL_SUB_SIZE)
    max_w = THUMB_W - BL_MARGIN_LEFT - BL_MARGIN_RIGHT
    sub_lines = wrap_text(draw, subtitle_en, font_sub, max_w)
    sub_h = text_block_height(draw, sub_lines, font_sub)
    title_h = draw.textbbox((0, 0), title_en, font=font_title)[3] - draw.textbbox(
        (0, 0), title_en, font=font_title
    )[1]

    sub_y = THUMB_H - BL_MARGIN_BOTTOM - sub_h
    title_y = sub_y - BL_GAP_TITLE_SUB - title_h
    badge_y = title_y - BL_GAP_BADGE_TITLE

    draw_text_with_shadow(
        draw, (BL_MARGIN_LEFT, title_y), title_en, font_title, (255, 255, 255, 255),
    )
    cy = sub_y
    for line in sub_lines:
        draw_text_with_shadow(draw, (BL_MARGIN_LEFT, cy), line, font_sub, (255, 255, 255, 255))
        cy += draw.textbbox((0, 0), line, font=font_sub)[3] - draw.textbbox(
            (0, 0), line, font=font_sub
        )[1]

    if show_4k and badge_path.is_file():
        badge = resize_badge(badge_path)
        badge_y -= badge.height
        overlay.paste(badge, (BL_MARGIN_LEFT, badge_y), badge)
    elif show_4k:
        print(f"Warning: 4K badge not found: {badge_path}", file=sys.stderr)

    Image.alpha_composite(img, overlay).convert("RGB").save(out_jpg, "JPEG", quality=92, optimize=True)


def render_markdown(
    video: Path,
    meta: dict,
    parsed: dict,
    preset: dict,
    thumb_name: str,
    thumb_title: str,
    thumb_subtitle: str,
    youtube_copy: dict,
    scene_key: str = "",
) -> str:
    title_zh = youtube_copy["title_zh"]
    title_en = youtube_copy["title_en"]
    sub_zh = youtube_copy.get("subtitle_zh", "")
    sub_en = youtube_copy.get("subtitle_en", "")
    tags = youtube_copy.get("tags", [])
    desc_zh = youtube_copy["description_zh"]
    desc_en = youtube_copy["description_en"]

    encoder_note = ""
    enc = parsed.get("encoder", "")
    if enc in ("gpu", "nvenc"):
        encoder_note = " · NVENC GPU encode"
    elif enc == "cpu":
        encoder_note = " · libx264 CPU encode"

    layout = preset.get("layout", "center")
    if layout == "bottom-left":
        thumb_layout = (
            f"左下角三行：4K 角标 · `{thumb_title}` "
            f"({BL_TITLE_SIZE}px) · 副标题 `{thumb_subtitle}` ({BL_SUB_SIZE}px)；"
            f"间距 4K↔标题 {BL_GAP_BADGE_TITLE}px · 标题↔副标题 {BL_GAP_TITLE_SUB}px"
        )
        badge_note = preset.get("badge_path", "scripts/video_export/4k.png")
    else:
        thumb_layout = (
            f"英文标题水平居中、距顶 {TITLE_TOP_Y}px · 4K 角标左下 · 无时长标签"
        )
        badge_note = "scripts/video_export/4k.png"

    lines = [
        f"# YouTube 物料 · `{video.name}`",
        "",
        "## 中文标题",
        "",
        f"{title_zh}",
        "",
        "## English Title",
        "",
        f"{title_en}",
        "",
        "## 缩略图",
        "",
        f"![thumbnail]({thumb_name})",
        "",
        f"- 文件：`{thumb_name}`",
        f"- 尺寸：1280×720（YouTube 推荐）",
        f"- 布局：{thumb_layout}",
        f"- 4K 角标：`{badge_note}`",
        f"- 缩略图标题：`{thumb_title}`",
        f"- 缩略图副标题：`{thumb_subtitle}`",
    ]
    if scene_key:
        lines.append(f"- 画面推断：`{scene_key}`（auto_from_scene）")
    lines.extend([
        "",
        "## 中文说明",
        "",
        desc_zh,
        "",
    ])
    if sub_zh:
        lines.extend(["", f"**副标题：** {sub_zh}", ""])
    lines.extend([
        "## English Description",
        "",
        desc_en,
        "",
    ])
    if sub_en:
        lines.extend(["", f"**Subtitle:** {sub_en}", ""])
    lines.extend([
        "## 标签 Tags",
        "",
        ", ".join(tags) if tags else "（无预设标签，请补充）",
        "",
        "## 视频信息",
        "",
        f"| 项 | 值 |",
        f"|----|-----|",
        f"| 文件 | `{video.name}` |",
        f"| 时长 | {meta['duration_human']} ({int(meta['duration_s'])}s) |",
        f"| 分辨率 | {meta['width']}×{meta['height']} |",
        f"| 帧率 | {meta['fps']} fps |",
        f"| 编码 | {meta['codec']}{encoder_note} |",
        f"| 体积 | {meta['size_mb']:.0f} MB |",
        f"| 码率 | ~{meta['bitrate_mbps']:.1f} Mbps |",
        "",
        "## 上传清单",
        "",
        "上传 API 自动设置（无需手填）：",
        "",
        "- [x] 分类：旅游与活动（Travel & Events · categoryId 19）",
        "- [x] 视频语言：English（defaultLanguage / defaultAudioLanguage）",
        "- [x] 非儿童内容声明",
        "",
        "需在 YouTube Studio 高级设置手动确认（API 无对应字段）：",
        "",
        "- [ ] 字幕认证：This content has never aired on television in the U.S.",
        "",
        "发布前检查：",
        "",
        "- [ ] 标题（英文，见 English Title）",
        "- [ ] 说明（英文，见 English Description）",
        "- [ ] 缩略图",
        "- [ ] 标签",
        "",
    ])
    return "\n".join(lines)


def generate_material(
    video: Path,
    *,
    output_dir: Path | None = None,
    preset_key: str | None = None,
    copy_style: str = "forest_rain",
    thumb_time: float | None = None,
    title_zh: str = "",
    title_en: str = "",
    thumb_title: str = "",
    thumb_subtitle: str = "",
    thumb_subtitle_place_only: bool = False,
    show_4k_badge: bool | None = None,
    layout: str = "",
    on_progress: Callable[[str], None] | None = None,
) -> Path:
    """生成 YouTube 物料（缩略图 + youtube.md）。返回输出目录。"""

    def log(msg: str) -> None:
        if on_progress:
            on_progress(msg)
        else:
            print(msg)

    video = video.resolve()
    if not video.is_file():
        raise FileNotFoundError(f"找不到视频：{video}")

    stem = video.stem
    parsed = parse_basename(stem)
    key = preset_key or parsed.get("project", stem)
    preset = load_preset(key)
    if not preset and preset_key:
        preset = load_preset("rain_asmr")
    if not preset:
        preset = {"auto_from_scene": True, "layout": "bottom-left", "thumb_time": 120}

    meta = ffprobe_video(video)
    out_dir = output_dir or (video.parent / "material" / stem)
    out_dir.mkdir(parents=True, exist_ok=True)

    use_layout = layout or preset.get("layout", "center")
    use_thumb_time = thumb_time if thumb_time is not None else preset.get("thumb_time", 8.0)
    dur = float(meta["duration_s"])
    if use_thumb_time >= dur:
        use_thumb_time = max(0.5, dur * 0.35)
        log(f"视频时长 {dur:.1f}s，截帧时间调整为 {use_thumb_time:.1f}s")
    badge_path = resolve_badge_path(preset)
    if show_4k_badge is None:
        show_4k = "4k" in stem.lower() or meta["width"] >= 3840
    else:
        show_4k = show_4k_badge

    frame_png = out_dir / "_frame.png"
    thumb_jpg = out_dir / "thumbnail.jpg"
    md_path = out_dir / "youtube.md"

    log(f"截取缩略图帧 @ {use_thumb_time}s …")
    extract_frame(video, frame_png, float(use_thumb_time))

    scene = analyze_frame_scene(frame_png)
    log(f"画面场景：{scene['scene_key']} · {scene['place_en_short']}")

    if copy_style == "forest_rain" and scene:
        youtube_copy = build_forest_rain_youtube_copy(scene, meta, show_4k=show_4k)
        if title_zh:
            youtube_copy["title_zh"] = title_zh
        if title_en:
            youtube_copy["title_en"] = title_en
        viral_title, viral_sub = build_forest_rain_thumb_text(scene, meta, show_4k=show_4k)
        thumb_title_resolved = thumb_title or preset.get("thumb_title_en") or viral_title
        if thumb_subtitle_place_only and scene:
            thumb_subtitle_resolved = scene["place_en_short"]
        else:
            thumb_subtitle_resolved = limit_words(
                thumb_subtitle or preset.get("thumb_subtitle_en") or viral_sub,
                max_words=14,
            )
    else:
        youtube_copy = resolve_youtube_copy(preset, scene, meta, stem, title_zh, title_en)
        thumb_title_resolved, thumb_subtitle_resolved = resolve_thumb_text(
            scene, preset, thumb_title, thumb_subtitle,
        )
        if thumb_subtitle_place_only and scene:
            thumb_subtitle_resolved = scene["place_en_short"]
    log(f"缩略图文案：{thumb_title_resolved!r} / {thumb_subtitle_resolved!r}")

    log(f"合成缩略图（{use_layout}）…")
    if use_layout == "bottom-left":
        make_thumbnail_bottom_left(
            frame_png,
            thumb_jpg,
            thumb_title_resolved,
            thumb_subtitle_resolved,
            show_4k=show_4k,
            badge_path=badge_path,
        )
    else:
        make_thumbnail(frame_png, thumb_jpg, thumb_title_resolved, show_4k=show_4k, badge_path=badge_path)
    frame_png.unlink(missing_ok=True)

    md_path.write_text(
        render_markdown(
            video,
            meta,
            parsed,
            preset,
            "thumbnail.jpg",
            thumb_title_resolved,
            thumb_subtitle_resolved,
            youtube_copy,
            scene_key=scene["scene_key"] if preset.get("auto_from_scene") or copy_style == "forest_rain" else "",
        ),
        encoding="utf-8",
    )
    log(f"已写入：{out_dir / 'youtube.md'}")
    log(f"已写入：{out_dir / 'thumbnail.jpg'}")
    return out_dir


def main() -> None:
    parser = argparse.ArgumentParser(description="Generate YouTube material for exported MP4")
    parser.add_argument("video", type=Path, help="Path to MP4 file")
    parser.add_argument(
        "-o", "--output-dir",
        type=Path,
        default=None,
        help="Material output dir (default: output/material/<stem>/)",
    )
    parser.add_argument("--thumb-time", type=float, default=8.0, help="Frame time for thumbnail (seconds)")
    parser.add_argument("--title-zh", default="", help="Override Chinese title")
    parser.add_argument("--title-en", default="", help="Override English title")
    parser.add_argument(
        "--thumb-title",
        default="",
        help="Thumbnail overlay title (default: RAIN ASMR, or preset thumb_title_en)",
    )
    parser.add_argument(
        "--thumb-subtitle",
        default="",
        help="Thumbnail subtitle — location/scene (default: auto from frame, ≤10 words)",
    )
    parser.add_argument("--no-4k-badge", action="store_true", help="Hide 4K badge on thumbnail")
    parser.add_argument(
        "--preset",
        default="",
        help="Preset key in youtube_presets.json (e.g. rain_asmr)",
    )
    parser.add_argument(
        "--layout",
        choices=("center", "bottom-left"),
        default="",
        help="Thumbnail layout (default from preset or center)",
    )
    parser.add_argument(
        "--style",
        choices=("forest_rain", "classic"),
        default="forest_rain",
        help="文案风格：forest_rain=material_ref/forest_rain.md 爆款模版",
    )
    args = parser.parse_args()

    video = args.video.resolve()
    if not video.is_file():
        print(f"Error: video not found: {video}", file=sys.stderr)
        sys.exit(1)

    out_dir = args.output_dir
    if out_dir is None:
        out_dir = video.parent / "material" / video.stem

    preset_key = args.preset or parse_basename(video.stem).get("project", video.stem)
    if args.preset and not load_preset(preset_key):
        print(f"Error: unknown preset '{args.preset}'", file=sys.stderr)
        sys.exit(1)

    thumb_time = args.thumb_time if args.thumb_time != 8.0 else None
    generate_material(
        video,
        output_dir=out_dir,
        preset_key=preset_key if args.preset else None,
        copy_style=args.style,
        thumb_time=thumb_time,
        title_zh=args.title_zh,
        title_en=args.title_en,
        thumb_title=args.thumb_title,
        thumb_subtitle=args.thumb_subtitle,
        show_4k_badge=False if args.no_4k_badge else None,
        layout=args.layout,
    )
    print(f"==> Done: {out_dir}/")
    print("    youtube.md")
    print("    thumbnail.jpg")


if __name__ == "__main__":
    main()
