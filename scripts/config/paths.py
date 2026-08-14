"""统一路径管理器（Path Manager）。

代码仓库（REPO_ROOT）仅含脚本与 Reaper 工程模板；
所有媒体素材位于 baseURL（同一 NAS 共享，WSL 默认 /mnt/e，亦兼容 /mnt/z，Mac 为 /Volumes/192.168.3.128/...）。
"""

from __future__ import annotations

import json
import os
import re
import shutil
import sys
from pathlib import Path
from typing import Callable

REPO_ROOT = Path(__file__).resolve().parents[2]

# 同一 NAS 共享目录在各平台的挂载路径（运行时选用第一个存在的）
_BASE_SUFFIX = "/自然之声/to_youtube"
BASE_URL_VARIANTS: tuple[str, ...] = (
    f"/mnt/e{_BASE_SUFFIX}",
    f"/mnt/z{_BASE_SUFFIX}",
    f"/Volumes/192.168.3.128{_BASE_SUFFIX}",
)

# 各平台首选默认（无挂载命中时的回退值）
DEFAULT_BASE_URL_WSL = Path(BASE_URL_VARIANTS[0])
DEFAULT_BASE_URL_MAC = Path(BASE_URL_VARIANTS[2])

RAIN_FX_FILENAME = "footagecrate-real-medium-rain-1.mp4"
RAIN_FX_PNG = "rain_fx.png"


def is_mac() -> bool:
    return sys.platform == "darwin"


def default_base_url_for_platform() -> Path:
    if is_mac():
        return DEFAULT_BASE_URL_MAC
    return DEFAULT_BASE_URL_WSL


def alternate_base_url() -> Path:
    """本机另一平台的默认 baseURL（供 base_url 候选列表使用）。"""
    if is_mac():
        return DEFAULT_BASE_URL_WSL
    return DEFAULT_BASE_URL_MAC


def _base_url_suffix_for(raw: str) -> str | None:
    for prefix in BASE_URL_VARIANTS:
        if raw.startswith(prefix):
            return raw[len(prefix) :]
    return None


def remap_storage_path(path: Path | str) -> Path:
    """将另一台机器上的 baseURL 绝对路径映射到本机可用路径（e/z/Mac 互认）。"""
    p = Path(path)
    if not p.is_absolute():
        return p
    raw = p.as_posix()
    suffix = _base_url_suffix_for(raw)
    if suffix is None:
        return p

    current = base_url().as_posix()
    if raw.startswith(current):
        return p

    for prefix in (current, *BASE_URL_VARIANTS):
        alt = Path(prefix + suffix)
        try:
            if alt.exists():
                return alt.resolve()
        except OSError:
            continue
    return p


def _posix_from_any_stored(raw: str) -> Path:
    """user_config / RPP 中可能出现的 Windows、WSL UNC、posix 路径 → posix Path。"""
    text = raw.strip()
    if not text:
        return Path(text)
    normalized = text.replace("\\", "/")
    m = re.match(r"^([A-Za-z]):/(.*)$", normalized)
    if m:
        return Path(f"/mnt/{m.group(1).lower()}/{m.group(2)}")
    m = re.match(r"^//wsl\.localhost/[^/]+/(.+)$", normalized, re.I)
    if m:
        return Path("/" + m.group(1))
    return Path(text)


def migrate_stored_path(path: Path | str) -> Path:
    """将历史 z/e/盘符/WSL UNC 路径统一到当前 baseURL 下可用路径。"""
    p = _posix_from_any_stored(str(path))
    if not str(path).strip():
        return p
    return remap_storage_path(p)


def base_url() -> Path:
    """素材根目录 baseURL，优先级：环境变量 > user_config > 平台默认 > 其他已知挂载点。"""
    candidates: list[Path] = []
    seen: set[str] = set()

    def add(p: Path | str) -> None:
        key = str(p)
        if key not in seen:
            seen.add(key)
            candidates.append(Path(p))

    env = os.environ.get("RELAXASMR_BASE_URL", "").strip()
    if env:
        add(env)
    cfg_path = REPO_ROOT / "gui" / "user_config.json"
    if cfg_path.is_file():
        try:
            data = json.loads(cfg_path.read_text(encoding="utf-8"))
            bu = (data.get("base_url") or "").strip()
            if bu:
                add(bu)
        except (json.JSONDecodeError, OSError):
            pass
    add(default_base_url_for_platform())
    add(alternate_base_url())
    for variant in BASE_URL_VARIANTS:
        add(variant)

    for c in candidates:
        try:
            if c.is_dir():
                return c.resolve()
        except OSError:
            continue
    return default_base_url_for_platform()


def material_dir() -> Path:
    return base_url() / "material"


def audio_dir() -> Path:
    return base_url() / "audio"


def fx_dir() -> Path:
    return base_url() / "fx"


def export_dir() -> Path:
    return base_url() / "export"


# AIGC 产物根（仓库内 aigc/，避免写外盘性能问题）


def aigc_dir() -> Path:
    """AIGC 根目录：仓库内 ``aigc/``；可用 ``RELAXASMR_AIGC_DIR`` 覆盖。"""
    env = os.environ.get("RELAXASMR_AIGC_DIR", "").strip()
    if env:
        p = Path(env)
        p.mkdir(parents=True, exist_ok=True)
        return p.resolve()
    p = REPO_ROOT / "aigc"
    p.mkdir(parents=True, exist_ok=True)
    return p.resolve()


def t2v_lab_dir() -> Path:
    """文生视频实验台：``aigc/t2v_lab/``。"""
    p = aigc_dir() / "t2v_lab"
    p.mkdir(parents=True, exist_ok=True)
    return p.resolve()


def t2v_runs_dir() -> Path:
    p = t2v_lab_dir() / "runs"
    p.mkdir(parents=True, exist_ok=True)
    return p.resolve()


def agent_t2v_lab_dir() -> Path:
    """AIGC「文生视频」子 Tab：Jimeng Agent × Gemini 管线。"""
    p = aigc_dir() / "agent_t2v_lab"
    p.mkdir(parents=True, exist_ok=True)
    return p.resolve()


def agent_t2v_runs_dir() -> Path:
    p = agent_t2v_lab_dir() / "runs"
    p.mkdir(parents=True, exist_ok=True)
    return p.resolve()


def agent_i2v_lab_dir() -> Path:
    """AIGC「图生视频」子 Tab：截图 + 雨型 → Agent × Gemini。"""
    p = aigc_dir() / "agent_i2v_lab"
    p.mkdir(parents=True, exist_ok=True)
    return p.resolve()


def agent_i2v_runs_dir() -> Path:
    p = agent_i2v_lab_dir() / "runs"
    p.mkdir(parents=True, exist_ok=True)
    return p.resolve()


DEFAULT_DURATION_MINUTES = 90


def cfg_duration_minutes(cfg: dict) -> float:
    """从场景/GUI 配置读取成片时长（分钟），兼容旧 duration_hours。"""
    if "duration_minutes" in cfg:
        return float(cfg["duration_minutes"])
    if "duration_hours" in cfg:
        return float(cfg["duration_hours"]) * 60
    return float(DEFAULT_DURATION_MINUTES)


def duration_render_suffix(minutes: float) -> str:
    """成片时长后缀，如 100 → '100min'，90.5 → '90.5min'。"""
    m = float(minutes)
    if m == int(m):
        return f"{int(m)}min"
    return f"{m:g}min"


def export_wav_basename(scene_id: str, minutes: float) -> str:
    """导出混音文件名（无扩展名），如 MVI_6989_100min。"""
    return f"{scene_id}_{duration_render_suffix(minutes)}"


def export_wav_name(scene_id: str, minutes: float) -> str:
    return f"{export_wav_basename(scene_id, minutes)}.wav"


# 四层音频架构（baseURL/audio/）
AUDIO_LAYER_IDS = ("1_rain", "2_impact", "3_random", "4_wildlife")


def ensure_base_url_dirs() -> None:
    """确保 baseURL 与仓库内 AIGC 标准子目录存在。"""
    for d in (material_dir(), fx_dir(), export_dir()):
        d.mkdir(parents=True, exist_ok=True)
    aigc_dir()
    for layer_id in AUDIO_LAYER_IDS:
        audio_layer_dir(layer_id).mkdir(parents=True, exist_ok=True)
        audio_booms_dir(layer_id).mkdir(parents=True, exist_ok=True)


def rain_fx_video() -> Path:
    return fx_dir() / RAIN_FX_FILENAME


def rain_fx_png() -> Path:
    return fx_dir() / RAIN_FX_PNG


def ensure_rain_fx_png() -> Path:
    """雨效 overlay PNG：位于 baseURL/fx/rain_fx.png。"""
    ensure_base_url_dirs()
    target = rain_fx_png()
    if not target.is_file():
        raise FileNotFoundError(f"雨效 PNG 不存在: {target}")
    return target


# Reaper 工程（仍在代码仓库内）
REAPER_DIR = REPO_ROOT / "Reaper"
PROJECTS_DIR = REAPER_DIR / "Projects"
RAIN_PROJECT_DIR = PROJECTS_DIR / "Rain"
RAIN_SCRIPTS_DIR = RAIN_PROJECT_DIR / "scripts"
RAIN_SCENES_DIR = RAIN_SCRIPTS_DIR / "scenes"
# 旧布局（仅兼容读取）
SUBPROJECTS_DIR = RAIN_PROJECT_DIR / "subprojects"


def ensure_rain_fx_video() -> Path:
    """雨效 overlay 视频：优先 baseURL/fx，若缺失则从仓库 legacy 拷贝。"""
    ensure_base_url_dirs()
    target = rain_fx_video()
    if not target.is_file():
        legacy = REPO_ROOT / "assets" / "fx" / RAIN_FX_FILENAME
        if legacy.is_file():
            shutil.copy2(legacy, target)
    return target


def is_under_base(path: Path | str) -> bool:
    try:
        Path(path).resolve().relative_to(base_url().resolve())
        return True
    except ValueError:
        return False


def path_for_config(path: Path | str) -> str:
    """场景配方中的路径：本机 baseURL 下的绝对路径（posix，Reaper Mac/Win 均可读）。"""
    p = Path(path).resolve()
    mapped = remap_storage_path(p)
    if mapped.exists():
        p = mapped
    return p.as_posix()


def resolve_media_asset(path_str: str) -> Path:
    """将配置中的路径解析为绝对路径（支持 base 相对路径与旧 assets/ 前缀）。"""
    if not path_str or not str(path_str).strip():
        raise ValueError("媒体路径为空")

    raw = str(path_str).strip()
    p = Path(raw)
    if p.is_absolute():
        resolved = p.resolve()
        if resolved.is_file():
            return resolved
        remapped = remap_storage_path(resolved)
        if remapped.is_file():
            return remapped.resolve()
        return resolved

    bu = base_url()

    # base 相对：video.mp4 / audio/1_rain/...
    direct = (bu / raw).resolve()
    if direct.is_file():
        return direct

    # 旧仓库相对路径 assets/...
    if raw.startswith("assets/"):
        rest = raw.removeprefix("assets/")
        if rest.startswith("loop_video/"):
            fname = Path(rest).name
            flat = bu / fname
            if flat.is_file():
                return flat.resolve()
            # MVI_6918/foo.mp4
            parts = Path(rest).parts
            if len(parts) >= 3 and parts[0] == "loop_video":
                nested = bu.joinpath(*parts[2:])
                if nested.is_file():
                    return nested.resolve()
        if rest.startswith("sound_effect/rain_sound/"):
            parts = Path(rest).parts
            if len(parts) >= 3 and parts[1] == "rain_sound":
                layer = parts[2]
                fname = parts[-1]
                for candidate in (
                    bu / "audio" / layer / "sounds" / fname,
                    bu / "audio" / layer / fname,
                ):
                    if candidate.is_file():
                        return candidate.resolve()
        mapped = (bu / rest).resolve()
        if mapped.is_file():
            return mapped.resolve()

    legacy = (REPO_ROOT / raw).resolve()
    if legacy.is_file():
        return legacy

    return direct


def normalize_video(video: Path, scene_id: str | None = None) -> tuple[Path, str]:
    """规范化 loop 视频路径：已在 baseURL 则直接使用，否则复制到 baseURL 根目录。"""
    video = video.resolve()
    bu = base_url()
    if is_under_base(video):
        return video, path_for_config(video)

    bu.mkdir(parents=True, exist_ok=True)
    dest = bu / video.name
    if not dest.exists() or dest.stat().st_size != video.stat().st_size:
        shutil.copy2(video, dest)
    return dest, path_for_config(dest)


def get_scene_id_from_path(path: Path | str) -> str:
    path_obj = Path(path)
    return path_obj.stem


def get_scene_number(scene_id: str) -> str:
    match = re.search(r"\d+", scene_id)
    return match.group() if match else scene_id


def get_rain_project_dir() -> Path:
    """Rain 工程根目录（.rpp 直接位于此目录）。"""
    return RAIN_PROJECT_DIR


def get_scene_rpp_path(scene_id: str) -> Path:
    return RAIN_PROJECT_DIR / f"{scene_id}.rpp"


def get_scene_config_path(scene_id: str) -> Path:
    """场景工程配置：Rain/scripts/scenes/<scene_id>.json"""
    return RAIN_SCENES_DIR / f"{scene_id}.json"


def resolve_scene_config_path(scene_id: str) -> Path | None:
    """优先 JSON，回退 scenes/*.lua 与旧 subprojects/*/asmr_config.lua。"""
    p = get_scene_config_path(scene_id)
    if p.is_file():
        return p
    lua_p = RAIN_SCENES_DIR / f"{scene_id}.lua"
    if lua_p.is_file():
        return lua_p
    legacy = SUBPROJECTS_DIR / scene_id / "scripts" / "asmr_config.lua"
    return legacy if legacy.is_file() else None


def get_subproject_dir(scene_id: str) -> Path:
    """兼容旧名：Rain 工程根目录（非 per-scene 子目录）。"""
    return RAIN_PROJECT_DIR


def get_subproject_scripts_dir(_scene_id: str | None = None) -> Path:
    """共用脚本目录 Rain/scripts/。"""
    return RAIN_SCRIPTS_DIR


def get_material_dir(scene_id: str, video_path: Path | None = None) -> Path:
    """分析物料目录：统一为 baseURL/material/。"""
    return material_dir()


def get_snapshot_raw_path(scene_id: str, video_path: Path | None = None) -> Path:
    return material_dir() / f"{scene_id}_snapshot_raw.jpg"


def get_thumbnail_path(scene_id: str, video_path: Path | None = None) -> Path:
    return material_dir() / f"{scene_id}_thumbnail.jpg"


# 兼容旧调用
def get_snapshot_path(scene_id: str, video_path: Path | None = None) -> Path:
    return get_thumbnail_path(scene_id, video_path)


def clip_matches_path(scene_id: str) -> Path:
    return material_dir() / f"{scene_id}_clip_matches.json"


def vlm_matches_path(scene_id: str) -> Path:
    return material_dir() / f"{scene_id}_vlm_matches.json"


def material_md_path(scene_id: str) -> Path:
    """Legacy 物料 Markdown 路径（只读兼容）。"""
    return material_dir() / f"{scene_id}_material.md"


def material_json_path(scene_id: str) -> Path:
    return material_dir() / f"{scene_id}_material.json"


def material_metadata_path(scene_id: str) -> Path | None:
    """优先 JSON，其次 legacy MD。"""
    json_path = material_json_path(scene_id)
    if json_path.is_file():
        return json_path
    md_path = material_md_path(scene_id)
    if md_path.is_file():
        return md_path
    return None


def visual_scene_path(scene_id: str) -> Path:
    return material_dir() / f"{scene_id}_visual_scene.json"


def scene_material_paths(scene_id: str) -> dict[str, Path]:
    """单场景在 material/ 下的主要产物路径。"""
    return {
        "snapshot_raw": get_snapshot_raw_path(scene_id),
        "thumbnail": get_thumbnail_path(scene_id),
        "material_json": material_json_path(scene_id),
        "material_md": material_md_path(scene_id),
        "clip_matches": clip_matches_path(scene_id),
        "vlm_matches": vlm_matches_path(scene_id),
        "visual_scene": visual_scene_path(scene_id),
    }


def clear_scene_material(
    scene_id: str,
    *,
    on_progress: Callable[[str], None] | None = None,
) -> None:
    """删除场景物料缓存，供「覆盖物料」全量重生成。"""
    paths = list(scene_material_paths(scene_id).values())
    paths.append(material_dir() / f"{scene_id}_snapshot.jpg")
    for path in paths:
        if path.is_file():
            path.unlink()
            if on_progress is not None:
                on_progress(f"已删除: {path.name}")


def audio_layer_dir(layer_id: str) -> Path:
    """声音库 WAV 候选目录，如 baseURL/audio/1_rain/sounds。"""
    sounds = audio_dir() / layer_id / "sounds"
    if sounds.is_dir():
        return sounds
    return audio_dir() / layer_id


def audio_rain_booms_dir() -> Path:
    """Rain boom 声源目录：baseURL/audio/1_rain/booms/。"""
    return audio_booms_dir("1_rain")


def audio_booms_dir(layer_id: str) -> Path:
    """Boom 声源目录，如 baseURL/audio/3_random/booms。"""
    return audio_dir() / layer_id / "booms"


def audio_booms_16bit_dir(layer_id: str) -> Path:
    """Boom 16-bit 试听缓存：baseURL/audio/<layer>/booms_16bit/（与 booms/ 同名镜像）。"""
    return audio_dir() / layer_id / "booms_16bit"


def _extra_bin_dirs() -> list[Path]:
    """GUI/.app 启动时常缺失的常用可执行文件目录。"""
    dirs: list[Path] = []
    if is_mac():
        dirs.extend([Path("/opt/homebrew/bin"), Path("/usr/local/bin")])
    extra = os.environ.get("RELAXASMR_BIN_PATH", "").strip()
    if extra:
        for part in extra.split(os.pathsep):
            if part:
                dirs.append(Path(part))
    return dirs


def ensure_gui_path() -> None:
    """补全 PATH，避免 macOS 双击 .app 时找不到 Homebrew 安装的 ffmpeg 等工具。"""
    existing = os.environ.get("PATH", "")
    parts = existing.split(os.pathsep) if existing else []
    seen = set(parts)
    prepend: list[str] = []
    for directory in _extra_bin_dirs():
        text = str(directory)
        if text not in seen and directory.is_dir():
            prepend.append(text)
            seen.add(text)
    if prepend:
        os.environ["PATH"] = os.pathsep.join(prepend + parts)


def ensure_cli_path() -> None:
    """把 ``cli/`` 放进 ``sys.path``，使 ``import agy`` / ``import jimeng_web`` /
    ``import elevenlabs_http`` / ``import elevenlabs_web`` / ``import shared`` 可用。

    包在 ``cli/agy``、``cli/jimeng_web``、``cli/elevenlabs_http``、
    ``cli/elevenlabs_web``、``cli/shared``（故意不用 ``elevenlabs`` 包名，避免盖掉
    官方 SDK）。调用方在入口执行一次即可（GUI ``app.py`` 已调用）。脚本直跑::

        from scripts.config.paths import ensure_cli_path; ensure_cli_path()
    """
    import sys

    cli_root = REPO_ROOT / "cli"
    text = str(cli_root)
    if cli_root.is_dir() and text not in sys.path:
        sys.path.insert(0, text)


def find_executable(name: str) -> Path | None:
    """查找可执行文件：先 PATH，再常见安装目录。"""
    found = shutil.which(name)
    if found:
        return Path(found)
    for directory in _extra_bin_dirs():
        candidate = directory / name
        if candidate.is_file() and os.access(candidate, os.X_OK):
            return candidate
    return None


def ffmpeg_exe() -> Path:
    exe = find_executable("ffmpeg")
    if exe is not None:
        return exe
    raise RuntimeError("ffmpeg 未安装或不在 PATH 中（Mac 可运行: brew install ffmpeg）")


def ffprobe_exe() -> Path:
    exe = find_executable("ffprobe")
    if exe is not None:
        return exe
    raise RuntimeError("ffprobe 未安装或不在 PATH 中（Mac 可运行: brew install ffmpeg）")
