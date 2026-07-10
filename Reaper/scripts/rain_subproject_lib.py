"""Rain 子工程：从 loop 视频创建配方 + 脚手架。"""

from __future__ import annotations

import json
import re
import shutil
import subprocess
import tempfile
from collections.abc import Callable
from datetime import date
from pathlib import Path

_REPO = Path(__file__).resolve().parents[2]
import sys

if str(_REPO) not in sys.path:
    sys.path.insert(0, str(_REPO))

from scripts.config.paths import (
    AUDIO_LAYER_IDS,
    RAIN_PROJECT_DIR,
    RAIN_SCENES_DIR,
    REPO_ROOT,
    audio_layer_dir,
    base_url,
    material_dir,
    normalize_video,
    path_for_config,
    resolve_media_asset,
)

RAIN_ROOT = RAIN_PROJECT_DIR
SCENES = RAIN_SCENES_DIR
VIDEO_ROOT = base_url()
TEMPLATE_DOC = RAIN_ROOT / "scripts" / "scenes" / "_template_video_analysis.md"
SCAFFOLD_SRC = RAIN_ROOT / "scripts"  # lua + fx 模板
REAPER_SCRIPTS = Path(__file__).resolve().parent  # Reaper/scripts（共享 ReaScript）
SHARED_REAPER_LUA = (
    "asmr_paths.lua",
    "asmr_vol_envelope.lua",
    "asmr_scatter_track.lua",
    "asmr_loop_track.lua",
)

SCENE_ID_RE = re.compile(r"(MVI_\d+)", re.I)

DEFAULT_MAPPINGS = {
    "1_rain": "1_rain",
    "2_impact": "2_impact",
    "3_random": "3_random",
    "4_wildlife": "4_wildlife",
}


def pick_first_audio(layer_id: str) -> tuple[str | None, str]:
    """从 baseURL/audio/<layer_id>/ 选取首个 wav 或 mp3。"""
    base = audio_layer_dir(layer_id)
    if not base.is_dir():
        return None, f"目录不存在：audio/{layer_id}"
    for pattern in ("*.wav", "*.mp3"):
        for p in sorted(base.rglob(pattern)):
            return path_for_config(p), f"从 audio/{layer_id} 选取 `{p.name}`"
    return None, f"audio/{layer_id} 下未找到 wav/mp3"


def derive_scene_id(video: Path, explicit: str | None = None) -> str:
    if explicit:
        return explicit.strip()
    for part in reversed(video.resolve().parts):
        m = SCENE_ID_RE.search(part)
        if m:
            return m.group(1).upper().replace("mvi", "MVI")
    stem = video.stem
    m = SCENE_ID_RE.search(stem)
    if m:
        return m.group(1).upper().replace("mvi", "MVI")
    raise ValueError(f"无法从路径推断场景 ID（期望 MVI_xxxx）：{video}")


def probe_video(video: Path) -> dict:
    proc = subprocess.run(
        [
            "ffprobe",
            "-v",
            "error",
            "-show_entries",
            "stream=codec_type,width,height,duration,codec_name",
            "-of",
            "json",
            str(video),
        ],
        capture_output=True,
        text=True,
        check=True,
    )
    data = json.loads(proc.stdout)
    streams = data.get("streams", [])
    video_s = next((s for s in streams if s.get("codec_type") == "video"), None)
    audio_s = next((s for s in streams if s.get("codec_type") == "audio"), None)
    return {
        "width": int(video_s.get("width", 0)) if video_s else 0,
        "height": int(video_s.get("height", 0)) if video_s else 0,
        "duration": float(video_s.get("duration", 0)) if video_s else 0.0,
        "codec": video_s.get("codec_name", "") if video_s else "",
        "has_audio": audio_s is not None,
    }


def ensure_video_in_assets(video: Path, scene_id: str) -> tuple[Path, str]:
    """规范化 loop 视频到 baseURL，返回 (绝对路径, 配置用绝对路径字符串)。"""
    return normalize_video(video, scene_id)



def analyze_visual_heuristic(video: Path) -> dict:
    """首帧 RGB 粗分析 + 文件名线索（无视觉模型）。"""
    hints: dict = {"filename": video.name}
    meta = probe_video(video)
    hints["width"] = meta.get("width", 0)
    hints["height"] = meta.get("height", 0)
    m_loop = re.search(r"loop_(\d+)", video.name, re.I)
    m_fade = re.search(r"fade_(\d+(?:\.\d+)?)", video.name, re.I)
    if m_loop:
        hints["loop_segments"] = int(m_loop.group(1))
    if m_fade:
        hints["fade_sec"] = float(m_fade.group(1))

    with tempfile.TemporaryDirectory() as tmp:
        frame = Path(tmp) / "frame.rgb"
        subprocess.run(
            [
                "ffmpeg",
                "-y",
                "-i",
                str(video),
                "-vf",
                "select=eq(n\\,0)",
                "-vframes",
                "1",
                "-f",
                "rawvideo",
                "-pix_fmt",
                "rgb24",
                str(frame),
            ],
            capture_output=True,
            check=False,
        )
        if frame.is_file() and frame.stat().st_size > 0:
            raw = frame.read_bytes()
            n = len(raw) // 3
            if n > 0:
                r = sum(raw[i] for i in range(0, len(raw), 3)) / n
                g = sum(raw[i + 1] for i in range(0, len(raw), 3)) / n
                b = sum(raw[i + 2] for i in range(0, len(raw), 3)) / n
                brightness = (r + g + b) / 3
                hints["mean_rgb"] = (round(r), round(g), round(b))
                hints["brightness"] = round(brightness, 1)
                hints["green_dominant"] = g > r * 1.05 and g > b * 1.05
                w, h = hints.get("width", 0), hints.get("height", 0)
                if w > 0 and h > 0:
                    row_bytes = w * 3
                    bottom = raw[(h // 2) * row_bytes :]
                    if bottom:
                        nb = len(bottom) // 3
                        br = sum(bottom[i] for i in range(0, len(bottom), 3)) / nb
                        bg = sum(bottom[i + 1] for i in range(0, len(bottom), 3)) / nb
                        bb = sum(bottom[i + 2] for i in range(0, len(bottom), 3)) / nb
                        hints["water_dominant"] = bb > br + 6 and bb > bg - 5
    return hints



def build_asmr_config(
    scene_id: str,
    video_rel: str,
    *,
    duration_hours: float = 3,
    visual: dict | None = None,
) -> tuple[dict, dict[str, str]]:
    cfg = {
        "scene_id": scene_id,
        "project_name": f"Rain · {scene_id}",
        "series": "rain_sleep",
        "duration_hours": duration_hours,
        "video": {
            "track": 5,
            "name": f"Video · {scene_id} loop",
            "path": video_rel,
            "render_only": True,
        },
        "loop_layers": [
            {
                "track": 1,
                "id": "1_rain",
                "name": "主雨势",
                "vol": 1.0,
                "paths": [],
            },
        ],
        "scatter_layers": [
            {
                "track": 2,
                "id": "2_impact",
                "name": "雨打树叶",
                "vol": 0.5,
                "paths": [],
                "min_gap_min": 3,
                "max_gap_min": 8,
                "randomness": 0.6,
                "clear_existing": True,
            },
            {
                "track": 3,
                "id": "3_random",
                "name": "随机散音",
                "vol": 0.35,
                "paths": [],
                "min_gap_min": 5,
                "max_gap_min": 15,
                "randomness": 0.6,
                "clear_existing": True,
            },
            {
                "track": 4,
                "id": "4_wildlife",
                "name": "野生生态",
                "vol": 0.28,
                "paths": [],
                "min_gap_min": 12,
                "max_gap_min": 28,
                "randomness": 0.55,
                "clear_existing": True,
            },
        ],
        "fade_sec": 0.08,
    }
    return cfg, {}


def build_scene_config_from_gui(
    video: Path,
    *,
    scene_id: str | None = None,
    duration_hours: float = 3,
    selected_tracks: dict[str, Path] | None = None,
    log_fn: Callable[[str], None] | None = None,
) -> dict:
    """从 GUI 选音构建工程配置 dict，供 generate_subproject.build_rpp 直接使用。"""
    from scripts.config.paths import path_for_config
    from scripts.new_reaper_project.audio_loudness import adjust_1_rain_layer_vol

    scene_id = derive_scene_id(video, scene_id)
    _, video_rel = ensure_video_in_assets(video, scene_id)
    cfg, _ = build_asmr_config(
        scene_id,
        video_rel,
        duration_hours=duration_hours,
    )

    for layer in cfg.get("loop_layers", []) + cfg.get("scatter_layers", []):
        lid = layer.get("id")
        if not lid:
            continue
        sel = (selected_tracks or {}).get(lid)
        if sel:
            layer["paths"] = [path_for_config(sel)]

    adjust_1_rain_layer_vol(cfg, log=log_fn)
    return cfg


def _layer_paths_from_cfg(cfg: dict) -> dict[str, str]:
    out: dict[str, str] = {}
    for layer in cfg.get("loop_layers", []) + cfg.get("scatter_layers", []):
        lid = layer.get("id", "")
        paths = [p for p in layer.get("paths", []) if p]
        if lid and paths:
            out[lid] = paths[0]
    return out


def recipe_section_md(cfg: dict, rationales: dict[str, str] | None = None) -> str:
    """§三 配方总览（Rain Sound Design 四层 + video）。"""
    lines = [
        "# 三、四层配方（自动初版）",
        "> 架构：[rain_sound_design.md](../../../../design/rain_series/rain_sound_design.md)",
        "> 轨 1 = 循环素材层 · 轨 2–4 = 散布层 · 轨 5 = 视频 · `1_rain` 长时包络请手动运行 `asmr_vol_envelope.lua`",
        "",
        "## 3.1 配方总览",
        "",
        "| 轨 | layer_id | 名称 | 模式 | 音量 |",
        "|----|----------|------|------|------|",
    ]
    for layer in cfg.get("loop_layers", []):
        lines.append(
            f"| {layer['track']} | `{layer['id']}` | {layer.get('name', '')} | loop | {layer.get('vol', 1)} |"
        )
    for layer in cfg.get("scatter_layers", []):
        lines.append(
            f"| {layer['track']} | `{layer['id']}` | {layer.get('name', '')} | scatter（手动散布） | {layer.get('vol', 1)} |"
        )
    video = cfg.get("video", {})
    if video:
        lines.append(
            f"| {video.get('track', 5)} | video | {video.get('name', 'loop')} | render_only | mute |"
        )
    lines.extend([
        "",
        "详细路径见 `scripts/scenes/<scene_id>.json` · 生成：`create_rain_subproject.py` / GUI",
        "",
    ])
    if rationales:
        layer_paths = _layer_paths_from_cfg(cfg)
        lines.extend([
            "## 3.2 声源选取理由",
            "",
            "| layer_id | 素材 | 选取理由 |",
            "|----------|------|----------|",
        ])
        for lid in AUDIO_LAYER_IDS:
            path = layer_paths.get(lid, "—")
            reason = rationales.get(lid, "—")
            short = f"`{Path(path).name}`" if path and path != "—" else "—"
            lines.append(f"| `{lid}` | {short} | {reason} |")
        lines.append("")
    lines.extend([
        "打开工程后：`asmr_loop_track.lua` 铺循环 → `asmr_vol_envelope.lua` 写 **`1_rain` 包络** → 逐轨 **`asmr_scatter_track.lua`** 散布稀疏层。",
        "",
    ])
    return "\n".join(lines)


def write_video_analysis(
    path: Path,
    scene_id: str,
    video_rel: str,
    probe: dict,
    visual: dict,
    cfg: dict,
    rationales: dict[str, str] | None = None,
) -> None:
    res = f"{probe['width']}×{probe['height']}" if probe["width"] else "—"
    today = date.today().isoformat()
    green_note = ""
    if visual.get("green_dominant"):
        green_note = "首帧 **绿色偏多** → 倾向林间/草地雨景（启发式）。"

    header = [
        f"# 视频分析 · {scene_id}",
        "",
        f"> 工程：`Reaper/Projects/Rain/{scene_id}.rpp`",
        f"> 视频：`{video_rel}`",
        f"> 分析日期：{today}",
        "> 状态：**Looper 首帧代表全片**（`create_rain_subproject.py` 自动生成，§一 请人工核对）",
        "> 系列：**Rain 睡眠**",
        f"> 成片时长：**{cfg.get('duration_hours', 3)} h**",
        "",
        "---",
        "",
        "# 一、视频画面拆解",
        "",
        "## 1.1 技术摘要",
        "",
        "| 项 | 值 |",
        "|----|-----|",
        f"| 分辨率 | {res}（{probe.get('codec', '')}） |",
        f"| 时长 | {probe['duration']:.2f} s |",
        f"| 文件名线索 | loop={visual.get('loop_segments', '?')} fade={visual.get('fade_sec', '?')} |",
        "",
        "## 1.2 画面描述",
        "",
        f"**自动启发**：{green_note or '（待人工补）'}",
        "",
        "**是**：（待补）",
        "**不是**：（待补）",
        "",
        "---",
        "",
        "# 二、音频配方",
        "",
        "> 主雨轨（1_rain）由 GUI 首帧 CLIP/VLM 分析匹配，不再拆解视频内嵌音轨。",
        "",
        "---",
        "",
    ]
    body = "\n".join(header) + recipe_section_md(cfg, rationales)
    path.write_text(body, encoding="utf-8")


def ensure_shared_scripts() -> Path:
    """确保 Rain/scripts 含全部共用 lua + fx（各场景不再复制一份）。"""
    scripts = RAIN_ROOT / "scripts"
    scripts.mkdir(parents=True, exist_ok=True)
    SCENES.mkdir(parents=True, exist_ok=True)
    for name in ("layer_template.lua",):
        src = SCAFFOLD_SRC / name
        dst = scripts / name
        if src.is_file() and src.resolve() != dst.resolve():
            shutil.copy2(src, dst)
    for name in SHARED_REAPER_LUA:
        src = REAPER_SCRIPTS / name
        dst = scripts / name
        if src.is_file() and src.resolve() != dst.resolve():
            shutil.copy2(src, dst)
    fx_src = SCAFFOLD_SRC / "fx"
    fx_dest = scripts / "fx"
    if fx_src.is_dir():
        fx_dest.mkdir(parents=True, exist_ok=True)
        for f in fx_src.glob("*"):
            if not (fx_dest / f.name).exists():
                shutil.copy2(f, fx_dest / f.name)
    return scripts


def scaffold_subproject(scene_id: str) -> Path:
    """兼容旧名：仅确保共用 scripts，返回 Rain 根目录。"""
    ensure_shared_scripts()
    return RAIN_ROOT


def scene_video_analysis_path(scene_id: str) -> Path:
    return material_dir() / f"{scene_id}_video_analysis.md"


def create_from_video(
    video: Path,
    *,
    scene_id: str | None = None,
    duration_hours: float = 3,
    media_mode: str = "auto",
    skip_generate: bool = False,
    on_progress: Callable[[str], None] | None = None,
) -> Path:
    def log(msg: str) -> None:
        if on_progress:
            on_progress(msg)
        else:
            print(msg)

    scene_id = derive_scene_id(video, scene_id)
    log(f"场景 ID: {scene_id}")
    video_abs, video_rel = ensure_video_in_assets(video, scene_id)
    log(f"视频: {video_rel}")

    log("探测视频元数据…")
    probe = probe_video(video_abs)
    log("分析首帧画面启发…")
    visual = analyze_visual_heuristic(video_abs)

    log("生成空白 4 轨音频 + 视频配方…")
    cfg, rationales = build_asmr_config(
        scene_id,
        video_rel,
        duration_hours=duration_hours,
        visual=visual,
    )

    log("写入场景配置…")
    rain_dir = scaffold_subproject(scene_id)
    from scene_config import save_scene_config

    config_path = save_scene_config(cfg)
    write_video_analysis(
        scene_video_analysis_path(scene_id),
        scene_id,
        video_rel,
        probe,
        visual,
        cfg,
        rationales,
    )

    if not skip_generate:
        from generate_subproject import build_rpp, stage_rain_fx_assets
        from media_paths import describe_media_mode

        log("生成 Reaper 工程 (.rpp)…")
        stage_rain_fx_assets(rain_dir)
        rpp_path = rain_dir / f"{scene_id}.rpp"
        log(f"媒体路径: {describe_media_mode(media_mode, REPO_ROOT)}")
        rpp_path.write_text(
            build_rpp(cfg, REPO_ROOT, rain_dir, media_mode),
            encoding="utf-8",
        )
        log(f"工程: {rpp_path.relative_to(REPO_ROOT)}")
    else:
        log(f"配置: {config_path.relative_to(REPO_ROOT)}")

    log("完成")
    return rain_dir
