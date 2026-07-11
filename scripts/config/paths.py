"""统一路径管理器（Path Manager）。

代码仓库（REPO_ROOT）仅含脚本与 Reaper 工程模板；
所有媒体素材位于 baseURL（WSL 默认 /mnt/e/...，Mac 默认 /Volumes/192.168.3.128/...）。
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

# 各平台默认 baseURL（局域网 NAS 同一共享目录）
DEFAULT_BASE_URL_WSL = Path("/mnt/e/自然之声/to_youtube")
DEFAULT_BASE_URL_MAC = Path("/Volumes/192.168.3.128/自然之声/to_youtube")

# WSL ↔ Mac 路径互转（相对 baseURL 的同一素材树）
_CROSS_BASE_PREFIXES: tuple[tuple[str, str], ...] = (
    ("/mnt/e/自然之声/to_youtube", "/Volumes/192.168.3.128/自然之声/to_youtube"),
)

RAIN_FX_FILENAME = "footagecrate-real-medium-rain-1.mp4"
RAIN_FX_PNG = "rain_fx.png"


def is_mac() -> bool:
    return sys.platform == "darwin"


def default_base_url_for_platform() -> Path:
    if is_mac():
        return DEFAULT_BASE_URL_MAC
    return DEFAULT_BASE_URL_WSL


def alternate_base_url() -> Path:
    if is_mac():
        return DEFAULT_BASE_URL_WSL
    return DEFAULT_BASE_URL_MAC


def remap_storage_path(path: Path | str) -> Path:
    """将另一台机器上的 baseURL 绝对路径映射到本机可用路径。"""
    p = Path(path)
    if not p.is_absolute():
        return p
    raw = p.as_posix()
    for src_prefix, dst_prefix in _CROSS_BASE_PREFIXES:
        if raw.startswith(src_prefix):
            alt = Path(dst_prefix + raw[len(src_prefix) :])
            if alt.exists():
                return alt.resolve()
        if raw.startswith(dst_prefix):
            alt = Path(src_prefix + raw[len(dst_prefix) :])
            if alt.exists():
                return alt.resolve()
    return p


def base_url() -> Path:
    """素材根目录 baseURL，优先级：环境变量 > user_config > 本机默认 > 对端默认。"""
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


def duration_render_suffix(hours: float) -> str:
    """成片时长后缀，如 3 → '3h'，2.5 → '2.5h'。"""
    h = float(hours)
    if h == int(h):
        return f"{int(h)}h"
    return f"{h:g}h"


def export_wav_basename(scene_id: str, hours: float) -> str:
    """导出混音文件名（无扩展名），如 MVI_6989_3h。"""
    return f"{scene_id}_{duration_render_suffix(hours)}"


def export_wav_name(scene_id: str, hours: float) -> str:
    return f"{export_wav_basename(scene_id, hours)}.wav"


# 四层音频架构（baseURL/audio/）
AUDIO_LAYER_IDS = ("1_rain", "2_impact", "3_random", "4_wildlife")


def ensure_base_url_dirs() -> None:
    """确保 baseURL 下标准子目录存在。"""
    for d in (material_dir(), fx_dir(), export_dir()):
        d.mkdir(parents=True, exist_ok=True)
    for layer_id in AUDIO_LAYER_IDS:
        audio_layer_dir(layer_id).mkdir(parents=True, exist_ok=True)


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
    return material_dir() / f"{scene_id}_material.md"


def scene_material_paths(scene_id: str) -> dict[str, Path]:
    """单场景在 material/ 下的主要产物路径。"""
    return {
        "snapshot_raw": get_snapshot_raw_path(scene_id),
        "thumbnail": get_thumbnail_path(scene_id),
        "material_md": material_md_path(scene_id),
        "clip_matches": clip_matches_path(scene_id),
        "vlm_matches": vlm_matches_path(scene_id),
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


def audio_booms_dir(layer_id: str) -> Path:
    """Boom 声源目录，如 baseURL/audio/3_random/booms。"""
    return audio_dir() / layer_id / "booms"
