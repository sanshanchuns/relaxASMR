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

REPO_ROOT = Path(__file__).resolve().parents[2]
RAIN_ROOT = REPO_ROOT / "Reaper" / "Projects" / "Rain"
SUBPROJECTS = RAIN_ROOT / "subprojects"
SCENES = RAIN_ROOT / "scripts" / "scenes"
SOUND_ROOT = REPO_ROOT / "assets" / "sound_effect" / "rain_sound"
VIDEO_ROOT = REPO_ROOT / "assets" / "loop_video" / "rain_video"
TEMPLATE_DOC = SUBPROJECTS / "_template" / "video_analysis.md"
SCAFFOLD_SRC = RAIN_ROOT / "scripts"  # lua + fx 模板
REAPER_SCRIPTS = Path(__file__).resolve().parent  # Reaper/scripts（共享 ReaScript）
SHARED_REAPER_LUA = (
    "asmr_apply_recipe.lua",
    "asmr_paths.lua",
    "asmr_vol_envelope.lua",
    "asmr_scatter_track.lua",
    "asmr_loop_track.lua",
)

SCENE_ID_RE = re.compile(r"(MVI_\d+)", re.I)

# 默认素材目录（相对 sound_effect/rain_sound · 见 design/rain_series/rain_sound_design.md）
DEFAULT_ASSET_DIRS = {
    "1_rain": "1_rain/intensity/light",
    "2_impact": "2_impact/vegetation/leaves",
    "3_environment": "3_environment/ambience/forest",
    "4_water": "4_water/dripping",
    "5_wildlife": "5_wildlife/birds",
    # 6_human 不自动选素材 — Rain 场景默认轨 6 留白，按画面在 Reaper 中手动选配
}

BIRD_FALLBACK = "assets/sound_effect/elevenlabs_sound/bird/api_mvi6918_bird_distant.mp3"
WATER_LAKE_DIR = "4_water/standing_water"
ENV_LAKE_DIR = "3_environment/ambience/lake"


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


def pick_first_mp3(rel_dir: str) -> tuple[str | None, str]:
    """从声源目录选取首个 mp3，返回 (仓库相对路径, 选取理由)。"""
    if rel_dir.startswith("../"):
        base = (REPO_ROOT / "assets" / "sound_effect" / rel_dir.replace("../", "")).resolve()
        base_desc = rel_dir
    else:
        base = (SOUND_ROOT / rel_dir).resolve()
        base_desc = f"rain_sound/{rel_dir}"
    if not base.is_dir():
        return None, f"目录不存在：`{base_desc}`"
    for p in sorted(base.rglob("*.mp3")):
        try:
            rel = p.relative_to(REPO_ROOT).as_posix()
            return rel, f"从 `{base_desc}` 按字母序选取 `{p.name}`"
        except ValueError:
            continue
    return None, f"`{base_desc}` 下未找到 mp3"


def build_asmr_config(
    scene_id: str,
    video_rel: str,
    *,
    duration_hours: float = 3,
    audio_layers: dict | None = None,
    visual: dict | None = None,
) -> tuple[dict, dict[str, str]]:
    paths: dict[str, str] = {}
    rationales: dict[str, str] = {}

    default_reasons = {
        "1_rain": "Rain 睡眠系列默认轻雨主层",
        "2_impact": "默认雨打树叶（vegetation/leaves）",
        "3_environment": "默认林间环境 ambience",
        "4_water": "默认滴水/细流",
        "5_wildlife": "默认远处鸟鸣 scatter",
    }

    rationales["6_human"] = (
        "Rain 场景默认留白（不自动配篝火/伞）；按画面在 Reaper 轨 6 手动放置素材"
    )

    for key, rel in DEFAULT_ASSET_DIRS.items():
        if key == "5_wildlife":
            picked, reason = pick_first_mp3(rel)
            if picked:
                paths[key] = picked
                rationales[key] = reason
            else:
                bird = REPO_ROOT / BIRD_FALLBACK
                if bird.is_file():
                    paths[key] = BIRD_FALLBACK
                    rationales[key] = f"rain_sound 无可用鸟鸣 → 回退 `{BIRD_FALLBACK}`"
                else:
                    rationales[key] = reason
        else:
            picked, reason = pick_first_mp3(rel)
            if picked:
                paths[key] = picked
                rationales[key] = f"{default_reasons[key]} · {reason}"
            else:
                rationales[key] = reason

    rain_vol = 1.0
    env_vol = 0.26
    water_vol = 0.18
    impact_vol = 0.5
    wild_vol = 0.28

    if audio_layers:
        lv = audio_layers.get("1_rain", {}).get("level", "")
        if lv == "强":
            picked, reason = pick_first_mp3("1_rain/intensity/moderate")
            if picked:
                paths["1_rain"] = picked
            rationales["1_rain"] = f"内嵌音轨 1_rain 判为「强」→ 改用 moderate · {reason}"
        elif lv == "弱":
            picked, reason = pick_first_mp3("1_rain/intensity/drizzle")
            if picked:
                paths["1_rain"] = picked
            rationales["1_rain"] = f"内嵌音轨 1_rain 判为「弱」→ 改用 drizzle · {reason}"

        wild = audio_layers.get("5_wildlife", {})
        wl = wild.get("level", "")
        if wl in ("无/极弱", "弱"):
            wild_vol = 0.22
            rationales["5_wildlife"] = (
                rationales.get("5_wildlife", "")
                + f" · 原声 wildlife「{wl}」→ scatter 音量降至 {wild_vol}"
            ).strip(" ·")
        elif wl == "强":
            wild_vol = 0.35
            rationales["5_wildlife"] = (
                rationales.get("5_wildlife", "")
                + f" · 原声 wildlife「强」→ scatter 音量升至 {wild_vol}"
            ).strip(" ·")

        water = audio_layers.get("4_water", {})
        wlv = water.get("level", "")
        if wlv in ("中", "强"):
            water_vol = 0.24
            picked, reason = pick_first_mp3(WATER_LAKE_DIR)
            if picked:
                paths["4_water"] = picked
            rationales["4_water"] = f"内嵌音轨 4_water 判为「{wlv}」→ 倾向静水/湖面 · {reason}"

    if visual:
        if visual.get("water_dominant"):
            env_picked, env_reason = pick_first_mp3(ENV_LAKE_DIR)
            water_picked, water_reason = pick_first_mp3(WATER_LAKE_DIR)
            if env_picked:
                paths["3_environment"] = env_picked
            if water_picked:
                paths["4_water"] = water_picked
            rationales["3_environment"] = f"首帧下半区偏蓝（水面启发）→ lake ambience · {env_reason}"
            rationales["4_water"] = f"首帧水面启发 + 原声水体线索 → standing_water · {water_reason}"
            env_vol = 0.24
            water_vol = 0.22
        elif visual.get("green_dominant"):
            picked, reason = pick_first_mp3("3_environment/ambience/forest")
            if picked:
                paths["3_environment"] = picked
            rationales["3_environment"] = f"首帧绿色偏多 → 强化林间 ambience · {reason}"

    cfg = {
        "scene_id": scene_id,
        "project_name": f"Rain · {scene_id}",
        "series": "rain_sleep",
        "duration_hours": duration_hours,
        "video": {
            "track": 7,
            "name": f"Video · {scene_id} loop",
            "path": video_rel,
            "render_only": True,
        },
        "loop_layers": [
            {
                "track": 1,
                "id": "1_rain",
                "name": "小雨主雨势",
                "vol": rain_vol,
                "paths": [paths.get("1_rain", "")],
                "vol_envelope": {
                    "shape": "single_wave",
                    "depth": 0.08,
                    "peak_at": "center",
                },
            },
            {
                "track": 3,
                "id": "3_environment",
                "name": "环境空间",
                "vol": env_vol,
                "paths": [paths.get("3_environment", "")],
            },
            {
                "track": 4,
                "id": "4_water",
                "name": "水体/滴水",
                "vol": water_vol,
                "paths": [paths.get("4_water", "")],
            },
            {
                "track": 6,
                "id": "6_human",
                "name": "留白（待选）",
                "vol": 0.0,
                "paths": [],
            },
        ],
        "scatter_layers": [
            {
                "track": 2,
                "id": "2_impact",
                "name": "雨打树叶",
                "vol": impact_vol,
                "paths": [paths.get("2_impact", "")],
                "min_gap_min": 3,
                "max_gap_min": 8,
                "randomness": 0.6,
                "clear_existing": True,
            },
            {
                "track": 5,
                "id": "5_wildlife",
                "name": "远处鸟鸣",
                "vol": wild_vol,
                "paths": [paths.get("5_wildlife", BIRD_FALLBACK)],
                "min_gap_min": 12,
                "max_gap_min": 28,
                "randomness": 0.55,
                "clear_existing": True,
            },
        ],
        "fade_sec": 0.08,
    }
    return cfg, rationales


def _layer_paths_from_cfg(cfg: dict) -> dict[str, str]:
    out: dict[str, str] = {}
    for layer in cfg.get("loop_layers", []) + cfg.get("scatter_layers", []):
        lid = layer.get("id", "")
        paths = [p for p in layer.get("paths", []) if p]
        if lid and paths:
            out[lid] = paths[0]
    return out


def recipe_section_md(cfg: dict, rationales: dict[str, str] | None = None) -> str:
    """§三 配方总览（Rain Sound Design 六层 + Dynamic + video）。"""
    lines = [
        "# 三、六层配方 + Dynamic（自动初版）",
        "",
        "> 架构：[rain_sound_design.md](../../../../design/rain_series/rain_sound_design.md)",
        "> 轨 1–6 = 素材层 · 轨 7 = 视频 · **Dynamic** = `1_rain` 音量包络（无独立轨）",
        "",
        "## 3.1 配方总览",
        "",
        "| 轨 | layer_id | 名称 | 模式 | 音量 |",
        "|----|----------|------|------|------|",
    ]
    for layer in cfg.get("loop_layers", []):
        mode = "loop"
        if layer.get("vol_envelope"):
            mode = "loop + **Dynamic**"
        lines.append(
            f"| {layer['track']} | `{layer['id']}` | {layer.get('name', '')} | {mode} | {layer.get('vol', 1)} |"
        )
    for layer in cfg.get("scatter_layers", []):
        gap = f"{layer.get('min_gap_min', '?')}–{layer.get('max_gap_min', '?')} min"
        lines.append(
            f"| {layer['track']} | `{layer['id']}` | {layer.get('name', '')} | scatter ({gap}) | {layer.get('vol', 1)} |"
        )
    video = cfg.get("video", {})
    if video:
        lines.append(
            f"| {video.get('track', 7)} | video | {video.get('name', 'loop')} | render_only | mute |"
        )
    lines.extend([
        "",
        "详细路径见 `scripts/asmr_config.lua` · 生成：`create_rain_subproject.py` / GUI",
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
        for lid in (
            "1_rain",
            "2_impact",
            "3_environment",
            "4_water",
            "5_wildlife",
            "6_human",
        ):
            path = layer_paths.get(lid, "—")
            reason = rationales.get(lid, "—")
            short = f"`{Path(path).name}`" if path and path != "—" else "—"
            lines.append(f"| `{lid}` | {short} | {reason} |")
        lines.append("")
    lines.extend([
        "打开工程后运行 **`asmr_apply_recipe.lua`**（铺循环/稀疏 + **`1_rain` 长时音量包络**）。",
        "",
    ])
    return "\n".join(lines)


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
        for p in layer.get("paths") or []:
            if p:
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
    cfg: dict,
    rationales: dict[str, str] | None = None,
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
        body = "\n".join(header) + section + "\n---\n\n" + recipe_section_md(cfg, rationales)
    else:
        no_audio = [
            "# 二、视频原声拆解",
            "",
            "> 本文件 **无内嵌音轨**，配方依据画面启发 + 睡眠系列默认模板。",
            "",
            "---",
            "",
        ]
        body = "\n".join(header) + "\n".join(no_audio) + recipe_section_md(cfg, rationales)

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
            shutil.copy2(f, fx_dest / f.name)
    return dest


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
    if probe["has_audio"]:
        log("分析内嵌音轨（七层听感）…")
        audio = analyze_embedded_audio(video_abs)
    else:
        log("无内嵌音轨，使用画面启发 + 默认模板")
        audio = None
    audio_layers = audio["layers"] if audio else None

    log("生成配方并挑选声源…")
    cfg, rationales = build_asmr_config(
        scene_id,
        video_rel,
        duration_hours=duration_hours,
        audio_layers=audio_layers,
        visual=visual,
    )

    log("写入脚手架与配方…")
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
        cfg,
        rationales,
    )

    if not skip_generate:
        from generate_subproject import build_rpp, load_config, stage_rain_fx_assets
        from media_paths import describe_media_mode

        log("生成 Reaper 工程 (.rpp)…")
        config_path = sub_dir / "scripts" / "asmr_config.lua"
        loaded = load_config(config_path)
        stage_rain_fx_assets(sub_dir)
        rpp_path = sub_dir / f"{scene_id}.rpp"
        log(f"媒体路径: {describe_media_mode(media_mode, REPO_ROOT)}")
        rpp_path.write_text(
            build_rpp(loaded, REPO_ROOT, sub_dir, media_mode),
            encoding="utf-8",
        )
        log(f"工程: {rpp_path.relative_to(REPO_ROOT)}")

    log("完成")
    return sub_dir
