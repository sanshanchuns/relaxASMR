#!/usr/bin/env python3
"""Generate YouTube metadata (.md) and thumbnail for export_mp4 outputs."""

from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
from pathlib import Path

try:
    from PIL import Image, ImageDraw, ImageFont
except ImportError:
    print("Error: Pillow required. Install with: pip install pillow", file=sys.stderr)
    sys.exit(1)

SCRIPT_DIR = Path(__file__).resolve().parent
REPO_ROOT = SCRIPT_DIR.parent.parent
PRESETS_PATH = SCRIPT_DIR / "youtube_presets.json"
BADGE_4K_PATH = SCRIPT_DIR / "assets" / "4k.png"
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
    subprocess.run(
        [
            "ffmpeg", "-y", "-ss", str(t), "-i", str(video),
            "-vframes", "1", "-q:v", "2", str(out_png),
        ],
        check=True,
        capture_output=True,
    )


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
    draw.text((cx, cy), title_en, font=font, fill=(255, 255, 255, TITLE_ALPHA), anchor="mt")

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

    draw.text((BL_MARGIN_LEFT, title_y), title_en, font=font_title, fill=(255, 255, 255, 255))
    cy = sub_y
    for line in sub_lines:
        draw.text((BL_MARGIN_LEFT, cy), line, font=font_sub, fill=(255, 255, 255, 255))
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
) -> str:
    title_zh = preset.get("title_zh", video.stem)
    title_en = preset.get("title_en", video.stem)
    sub_zh = preset.get("subtitle_zh", "")
    sub_en = preset.get("subtitle_en", "")
    tags = preset.get("tags", [])

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

    encoder_note = ""
    enc = parsed.get("encoder", "")
    if enc in ("gpu", "nvenc"):
        encoder_note = " · NVENC GPU encode"
    elif enc == "cpu":
        encoder_note = " · libx264 CPU encode"

    layout = preset.get("layout", "center")
    if layout == "bottom-left":
        thumb_layout = (
            f"左下角三行：4K 角标 · `{preset.get('thumb_title_en', title_en)}` "
            f"({BL_TITLE_SIZE}px) · 副标题 ({BL_SUB_SIZE}px)；"
            f"间距 4K↔标题 {BL_GAP_BADGE_TITLE}px · 标题↔副标题 {BL_GAP_TITLE_SUB}px"
        )
        badge_note = preset.get("badge_path", "scripts/video_export/assets/4k.png")
    else:
        thumb_layout = (
            f"英文标题水平居中、距顶 {TITLE_TOP_Y}px · 4K 角标左下 · 无时长标签"
        )
        badge_note = "scripts/video_export/assets/4k.png"

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
        "",
        "## 中文说明",
        "",
        desc_zh,
        "",
    ]
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
        "- [ ] 标题（中文或英文，按频道语言）",
        "- [ ] 说明（中 + 英，或合并）",
        "- [ ] 缩略图",
        "- [ ] 标签",
        "- [ ] 分类：Music / Entertainment / Howto（按频道定）",
        "- [ ] 非儿童内容声明",
        "",
    ])
    return "\n".join(lines)


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
    args = parser.parse_args()

    video = args.video.resolve()
    if not video.is_file():
        print(f"Error: video not found: {video}", file=sys.stderr)
        sys.exit(1)

    stem = video.stem
    parsed = parse_basename(stem)
    preset_key = args.preset or parsed.get("project", stem)
    preset = load_preset(preset_key)
    if args.preset and not preset:
        print(f"Error: unknown preset '{args.preset}'", file=sys.stderr)
        sys.exit(1)
    meta = ffprobe_video(video)

    out_dir = args.output_dir or (video.parent / "material" / stem)
    out_dir.mkdir(parents=True, exist_ok=True)

    title_zh = args.title_zh or preset.get("title_zh", stem)
    title_en = args.title_en or preset.get("title_en", stem)
    thumb_title = preset.get("thumb_title_en") or args.title_en or title_en
    thumb_subtitle = preset.get("thumb_subtitle_en", "")
    layout = args.layout or preset.get("layout", "center")
    thumb_time = args.thumb_time if args.thumb_time != 8.0 else preset.get("thumb_time", args.thumb_time)
    badge_path = resolve_badge_path(preset)
    show_4k = not args.no_4k_badge and ("4k" in stem.lower() or meta["width"] >= 3840)

    frame_png = out_dir / "_frame.png"
    thumb_jpg = out_dir / "thumbnail.jpg"
    md_path = out_dir / "youtube.md"

    print(f"==> Extracting frame at {thumb_time}s ...")
    extract_frame(video, frame_png, float(thumb_time))

    print(f"==> Compositing thumbnail ({layout}) ...")
    if layout == "bottom-left":
        make_thumbnail_bottom_left(
            frame_png,
            thumb_jpg,
            thumb_title,
            thumb_subtitle,
            show_4k=show_4k,
            badge_path=badge_path,
        )
    else:
        make_thumbnail(frame_png, thumb_jpg, thumb_title, show_4k=show_4k, badge_path=badge_path)
    frame_png.unlink(missing_ok=True)

    md_path.write_text(
        render_markdown(video, meta, parsed, preset, "thumbnail.jpg"),
        encoding="utf-8",
    )

    print(f"==> Done: {out_dir}/")
    print(f"    youtube.md")
    print(f"    thumbnail.jpg")


if __name__ == "__main__":
    main()
