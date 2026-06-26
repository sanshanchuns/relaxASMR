"""Rain 子工程：从 loop 视频创建配方 + 脚手架。"""

from __future__ import annotations

import json
import re
import shutil
import subprocess
import tempfile
from datetime import date
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
RAIN_ROOT = REPO_ROOT / "Reaper" / "Projects" / "Rain"
SUBPROJECTS = RAIN_ROOT / "subprojects"
SCENES = RAIN_ROOT / "scripts" / "scenes"
SOUND_ROOT = REPO_ROOT / "assets" / "sound_effect" / "rain_sound"
VIDEO_ROOT = REPO_ROOT / "assets" / "loop_video" / "rain_video"
TEMPLATE_DOC = SUBPROJECTS / "_template" / "video_analysis.md"
SCAFFOLD_SRC = RAIN_ROOT / "scripts"  # lua + fx 模板

SCENE_ID_RE = re.compile(r"(MVI_\d+)", re.I)

# 默认素材目录（相对 sound_effect/rain_sound）
DEFAULT_ASSET_DIRS = {
    "1_base": "1_base/air_tone",
    "2_rain": "2_rain/light_rain",
    "3_impact": "3_impact/rain_on_leaves",
    "5_env": "5_env/forest_rain",
    "7_comfort": "3_impact/rain_on_umbrella",
    "6_life": "../elevenlabs_sound/bird",  # 相对 repo
}

BIRD_FALLBACK = "assets/sound_effect/elevenlabs_sound/bird/api_mvi6918_bird_distant.mp3"


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
    """若视频不在 assets 下，复制到标准目录。返回 (绝对路径, repo 相对路径)。"""
    video = video.resolve()
    try:
        rel = video.relative_to(REPO_ROOT)
        if str(rel).startswith("assets/loop_video/rain_video/"):
            return video, rel.as_posix()
    except ValueError:
        pass
    dest_dir = VIDEO_ROOT / scene_id
    dest_dir.mkdir(parents=True, exist_ok=True)
    dest = dest_dir / video.name
    if not dest.exists() or dest.stat().st_size != video.stat().st_size:
        shutil.copy2(video, dest)
    rel = dest.relative_to(REPO_ROOT).as_posix()
    return dest, rel


def analyze_embedded_audio(video: Path) -> dict | None:
    if not probe_video(video)["has_audio"]:
        return None
    from analyze_video_audio import analyze_wav, extract_audio, layer_scores, load_samples

    with tempfile.TemporaryDirectory() as tmp:
        wav = Path(tmp) / "audio.wav"
        try:
            extract_audio(video, wav)
        except subprocess.CalledProcessError:
            return None
        samples, sr = load_samples(wav)
        stats = analyze_wav(samples, sr)
        layers = layer_scores(stats)
    return {"stats": stats, "layers": layers}


def analyze_visual_heuristic(video: Path) -> dict:
    """首帧 RGB 粗分析 + 文件名线索（无视觉模型）。"""
    hints: dict = {"filename": video.name}
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
    return hints


def pick_first_mp3(rel_dir: str) -> str | None:
    if rel_dir.startswith("../"):
        base = (REPO_ROOT / "assets" / "sound_effect" / rel_dir.replace("../", "")).resolve()
        prefix = f"assets/sound_effect/{rel_dir.replace('../', '')}"
    else:
        base = SOUND_ROOT / rel_dir
        prefix = f"assets/sound_effect/rain_sound/{rel_dir}"
    if not base.is_dir():
        return None
    for p in sorted(base.glob("*.mp3")):
        return f"{prefix}/{p.name}"
    return None


def build_asmr_config(
    scene_id: str,
    video_rel: str,
    *,
    duration_hours: float = 3,
    audio_layers: dict | None = None,
    visual: dict | None = None,
) -> dict:
    paths: dict[str, str] = {}
    for key, rel in DEFAULT_ASSET_DIRS.items():
        if key == "6_life":
            bird = REPO_ROOT / BIRD_FALLBACK
            paths[key] = BIRD_FALLBACK if bird.is_file() else pick_first_mp3(rel) or BIRD_FALLBACK
        else:
            picked = pick_first_mp3(rel)
            if picked:
                paths[key] = picked

    # 音频启发：强雨层保持 light_rain；生物层弱则仍可保留稀疏鸟鸣（睡眠系列惯例）
    rain_vol = 1.0
    life_vol = 0.3
    if audio_layers:
        lv = audio_layers.get("2_rain", {}).get("level", "")
        if lv == "强":
            paths["2_rain"] = pick_first_mp3("2_rain/moderate_rain") or paths.get("2_rain")
        if audio_layers.get("6_life", {}).get("level") in ("无/极弱", "弱"):
            life_vol = 0.25

    # 视觉启发：高绿 → 林间环境
    if visual and visual.get("green_dominant"):
        paths["5_env"] = pick_first_mp3("5_env/forest_rain") or paths.get("5_env", "")

    comfort_note = "伞面水滴"
    if visual and "umbrella" in video_rel.lower():
        comfort_note = "伞面水滴（文件名线索）"

    cfg = {
        "scene_id": scene_id,
        "project_name": f"Rain · {scene_id}",
        "series": "rain_sleep",
        "duration_hours": duration_hours,
        "video": {
            "track": 8,
            "name": f"Video · {scene_id} loop",
            "path": video_rel,
            "render_only": True,
        },
        "loop_layers": [
            {
                "track": 1,
                "id": "1_base",
                "name": "空气底噪",
                "vol": 0.28,
                "paths": [paths["1_base"]],
            },
            {
                "track": 2,
                "id": "2_rain",
                "name": "小雨主雨势",
                "vol": rain_vol,
                "paths": [paths["2_rain"]],
                "vol_envelope": {
                    "shape": "single_wave",
                    "depth": 0.08,
                    "peak_at": "center",
                },
            },
            {
                "track": 5,
                "id": "5_env",
                "name": "林间雨环境",
                "vol": 0.22,
                "paths": [paths["5_env"]],
            },
            {
                "track": 7,
                "id": "7_comfort",
                "name": comfort_note,
                "vol": 0.45,
                "paths": [paths["7_comfort"]],
            },
        ],
        "scatter_layers": [
            {
                "track": 3,
                "id": "3_impact",
                "name": "雨打树叶",
                "vol": 0.5,
                "paths": [paths["3_impact"]],
                "min_gap_min": 3,
                "max_gap_min": 8,
                "randomness": 0.6,
                "clear_existing": True,
            },
            {
                "track": 6,
                "id": "6_life",
                "name": "远处鸟鸣",
                "vol": life_vol,
                "paths": [paths["6_life"]],
                "min_gap_min": 12,
                "max_gap_min": 28,
                "randomness": 0.55,
                "clear_existing": True,
            },
        ],
        "fade_sec": 0.08,
    }
    return cfg


def lua_quote(s: str) -> str:
    return '"' + s.replace("\\", "\\\\").replace('"', '\\"') + '"'


def config_to_lua(cfg: dict) -> str:
    lines = [
        f"-- 场景配方 · 见 subprojects/{cfg['scene_id']}/video_analysis.md §三",
        f"-- 由 create_rain_subproject.py 自动生成",
        "",
        "return {",
        f"  scene_id = {lua_quote(cfg['scene_id'])},",
        f"  project_name = {lua_quote(cfg['project_name'])},",
        f"  series = {lua_quote(cfg['series'])},",
        f"  duration_hours = {cfg['duration_hours']},",
        "",
        "  video = {",
        f"    track = {cfg['video']['track']},",
        f"    name = {lua_quote(cfg['video']['name'])},",
        f"    path = {lua_quote(cfg['video']['path'])},",
        "    render_only = true,",
        "  },",
        "",
        "  loop_layers = {",
    ]
    for layer in cfg["loop_layers"]:
        lines.append("    {")
        lines.append(f"      track = {layer['track']},")
        lines.append(f"      id = {lua_quote(layer['id'])},")
        lines.append(f"      name = {lua_quote(layer['name'])},")
        lines.append(f"      vol = {layer['vol']},")
        lines.append("      paths = {")
        for p in layer["paths"]:
            lines.append(f"        {lua_quote(p)},")
        lines.append("      },")
        if layer.get("vol_envelope"):
            ve = layer["vol_envelope"]
            lines.append("      vol_envelope = {")
            lines.append(f"        shape = {lua_quote(ve['shape'])},")
            lines.append(f"        depth = {ve['depth']},")
            lines.append(f"        peak_at = {lua_quote(ve['peak_at'])},")
            lines.append("      },")
        lines.append("    },")
    lines.append("  },")
    lines.append("")
    lines.append("  scatter_layers = {")
    for layer in cfg["scatter_layers"]:
        lines.append("    {")
        lines.append(f"      track = {layer['track']},")
        lines.append(f"      id = {lua_quote(layer['id'])},")
        lines.append(f"      name = {lua_quote(layer['name'])},")
        lines.append(f"      vol = {layer['vol']},")
        lines.append("      paths = {")
        for p in layer["paths"]:
            lines.append(f"        {lua_quote(p)},")
        lines.append("      },")
        lines.append(f"      min_gap_min = {layer['min_gap_min']},")
        lines.append(f"      max_gap_min = {layer['max_gap_min']},")
        lines.append(f"      randomness = {layer['randomness']},")
        lines.append(f"      clear_existing = {str(layer['clear_existing']).lower()},")
        lines.append("    },")
    lines.append("  },")
    lines.append("")
    lines.append(f"  fade_sec = {cfg['fade_sec']},")
    lines.append("}")
    lines.append("")
    return "\n".join(lines)


def write_video_analysis(
    path: Path,
    scene_id: str,
    video_rel: str,
    probe: dict,
    visual: dict,
    audio: dict | None,
) -> None:
    from analyze_video_audio import LAYER_ROWS, build_markdown

    res = f"{probe['width']}×{probe['height']}" if probe["width"] else "—"
    today = date.today().isoformat()
    green_note = ""
    if visual.get("green_dominant"):
        green_note = "首帧 **绿色偏多** → 倾向林间/草地雨景（启发式）。"

    header = [
        f"# 视频分析 · {scene_id}",
        "",
        f"> 子工程：`subprojects/{scene_id}`",
        f"> 视频：`{video_rel}`",
        f"> 分析日期：{today}",
        "> 状态：**Looper 首帧代表全片**（`create_rain_subproject.py` 自动生成，§一 请人工核对）",
        "> 系列：**Rain 睡眠**",
        f"> 成片时长：**{3} h**",
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
        f"| 内嵌音轨 | {'有' if probe['has_audio'] else '**无**'} |",
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
    ]

    if audio:
        video_abs = REPO_ROOT / video_rel
        section = build_markdown(video_abs, audio["stats"], audio["layers"])
        body = "\n".join(header) + section + "\n---\n\n# 三、七层配方（自动初版）\n\n见 `scripts/asmr_config.lua` · 生成：`create_rain_subproject.py`\n\n打开工程后运行 **`asmr_apply_recipe.lua`**（轨 2 长时包络 + 循环/稀疏）。\n"
    else:
        no_audio = [
            "# 二、视频原声拆解",
            "",
            "> 本文件 **无内嵌音轨**，配方依据画面启发 + 睡眠系列默认模板。",
            "",
            "---",
            "",
            "# 三、七层配方（自动初版）",
            "",
            "见 `scripts/asmr_config.lua` · `create_rain_subproject.py`",
            "",
            "打开工程后运行 **`asmr_apply_recipe.lua`**。",
            "",
        ]
        body = "\n".join(header) + "\n".join(no_audio)

    path.write_text(body, encoding="utf-8")


def scaffold_subproject(scene_id: str) -> Path:
    dest = SUBPROJECTS / scene_id
    scripts = dest / "scripts"
    scripts.mkdir(parents=True, exist_ok=True)
    for name in ("rain_bootstrap.lua", "rain_paths.lua", "rain_setup_project.lua"):
        src = SCAFFOLD_SRC / name
        dst = scripts / name
        if src.is_file() and src.resolve() != dst.resolve():
            shutil.copy2(src, dst)
    fx_src = SCAFFOLD_SRC / "fx"
    fx_dest = scripts / "fx"
    if fx_src.is_dir():
        fx_dest.mkdir(parents=True, exist_ok=True)
        for f in fx_src.glob("*"):
            shutil.copy2(f, fx_dest / f.name)
    return dest


def create_from_video(
    video: Path,
    *,
    scene_id: str | None = None,
    duration_hours: float = 3,
    media_mode: str = "wsl_unc",
    skip_generate: bool = False,
) -> Path:
    scene_id = derive_scene_id(video, scene_id)
    video_abs, video_rel = ensure_video_in_assets(video, scene_id)
    probe = probe_video(video_abs)
    visual = analyze_visual_heuristic(video_abs)
    audio = analyze_embedded_audio(video_abs) if probe["has_audio"] else None
    audio_layers = audio["layers"] if audio else None

    cfg = build_asmr_config(
        scene_id,
        video_rel,
        duration_hours=duration_hours,
        audio_layers=audio_layers,
        visual=visual,
    )

    sub_dir = scaffold_subproject(scene_id)
    lua = config_to_lua(cfg)
    (sub_dir / "scripts" / "asmr_config.lua").write_text(lua, encoding="utf-8")
    SCENES.mkdir(parents=True, exist_ok=True)
    (SCENES / f"{scene_id}.lua").write_text(lua, encoding="utf-8")
    write_video_analysis(
        sub_dir / "video_analysis.md",
        scene_id,
        video_rel,
        probe,
        visual,
        audio,
    )

    if not skip_generate:
        from generate_subproject import build_rpp, load_config, stage_rain_fx_assets

        config_path = sub_dir / "scripts" / "asmr_config.lua"
        loaded = load_config(config_path)
        stage_rain_fx_assets(sub_dir)
        rpp_path = sub_dir / f"{scene_id}.rpp"
        rpp_path.write_text(
            build_rpp(loaded, REPO_ROOT, sub_dir, media_mode),
            encoding="utf-8",
        )

    return sub_dir
