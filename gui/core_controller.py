"""核心逻辑控制器（Core Controller）。

负责解耦 app.py（纯 UI 层）与底层的各种业务逻辑（分析、写入配置、生成工程等）。
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Callable

from scripts.common_constants import CLIMATE_NAMES, CLOSE_NAMES, DISTANT_NAMES, SPACE_NAMES
from scripts.paths import audio_layer_dir, clip_matches_path, vlm_matches_path


def _layer_keys_from_clip(clip_analysis: dict) -> tuple[int | None, int | None, int | None]:
    return (
        clip_analysis.get("l3", {}).get("key"),
        clip_analysis.get("l2", {}).get("key"),
        clip_analysis.get("l1", {}).get("key"),
    )


def _layer_keys_from_vlm(vlm_analysis: dict) -> tuple[int | None, int | None, int | None]:
    return (
        vlm_analysis.get("l3_key"),
        vlm_analysis.get("l2_key"),
        vlm_analysis.get("l1_key"),
    )


def clip_vlm_agree(clip_analysis: dict, vlm_analysis: dict) -> bool:
    if not vlm_analysis:
        return True
    return _layer_keys_from_clip(clip_analysis) == _layer_keys_from_vlm(vlm_analysis)


def get_matches_for_keys(
    l3_key: int | None,
    l2_key: int | None,
    l1_key: int | None,
    all_wavs: list[Path],
) -> list[dict[str, Any]]:
    """根据远景 + 空间 + 近景三个维度，在声源库中匹配最多 9 条 WAV。"""
    import re

    l3_en = DISTANT_NAMES.get(l3_key, ("", ""))[0].replace(" ", "") if l3_key else ""
    l2_en = SPACE_NAMES.get(l2_key, ("", ""))[0].replace(" ", "") if l2_key else ""
    l1_en = CLOSE_NAMES.get(l1_key, ("", ""))[0].replace(" ", "") if l1_key else ""

    l3_cn = DISTANT_NAMES.get(l3_key, ("", "未知"))[1] if l3_key else "未知"
    l1_cn = CLOSE_NAMES.get(l1_key, ("", "未知"))[1] if l1_key else "未知"

    out_data: list[dict[str, Any]] = []
    for w in all_wavs:
        name = w.stem
        if l3_en and l3_en not in name:
            continue
        if l2_en and l2_en not in name:
            continue
        if l1_en and l1_en not in name:
            continue

        m = re.search(r"_C(\d+)_", name)
        c_idx = int(m.group(1)) if m else 1
        display_name = CLIMATE_NAMES.get(c_idx, f"C{c_idx} {l3_cn} {l1_cn}")
        out_data.append({"wav": str(w), "score": 100, "name": display_name})

    def get_c_index(wav_str: str) -> int:
        m = re.search(r"_C(\d+)_", Path(wav_str).stem)
        return int(m.group(1)) if m else 99

    out_data.sort(key=lambda x: get_c_index(x["wav"]))
    if not out_data:
        cands = all_wavs[:9]
        out_data = [{"wav": str(c), "score": 100, "name": c.stem} for c in cands]
    return out_data[:9]


def format_clip_title(clip_analysis: dict) -> str:
    """例如 [轻柔沙响 + 茂密树林 + 稀疏植被]"""
    if not clip_analysis:
        return "[未知配方]"
    l3_key, l2_key, l1_key = _layer_keys_from_clip(clip_analysis)
    l3_cn = DISTANT_NAMES.get(l3_key, ("", "未知"))[1] if l3_key else "未知"
    l2_cn = SPACE_NAMES.get(l2_key, ("", "未知"))[1] if l2_key else "未知"
    l1_cn = CLOSE_NAMES.get(l1_key, ("", "未知"))[1] if l1_key else "未知"
    return f"[{l3_cn} + {l2_cn} + {l1_cn}]"


def format_vlm_title(vlm_analysis: dict) -> str:
    if not vlm_analysis:
        return "[未知配方]"
    return f"[{vlm_analysis.get('l3_cn')} + {vlm_analysis.get('l2_cn')} + {vlm_analysis.get('l1_cn')}]"


def list_rain_wavs() -> list[Path]:
    return list(audio_layer_dir("1_rain").rglob("*.wav"))


def save_clip_matches(
    scene_id: str,
    clip_analysis: dict,
    all_wavs: list[Path] | None = None,
) -> tuple[Path, str, list[dict[str, Any]]]:
    wavs = all_wavs if all_wavs is not None else list_rain_wavs()
    l3, l2, l1 = _layer_keys_from_clip(clip_analysis)
    matches = get_matches_for_keys(l3, l2, l1, wavs)
    title = format_clip_title(clip_analysis)
    payload = {"title": title, "candidates": matches, "l3_key": l3, "l2_key": l2, "l1_key": l1}
    path = clip_matches_path(scene_id)
    path.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")
    return path, title, matches


def save_vlm_matches(
    scene_id: str,
    vlm_analysis: dict,
    all_wavs: list[Path] | None = None,
) -> tuple[Path, str, list[dict[str, Any]]]:
    wavs = all_wavs if all_wavs is not None else list_rain_wavs()
    l3, l2, l1 = _layer_keys_from_vlm(vlm_analysis)
    matches = get_matches_for_keys(l3, l2, l1, wavs)
    title = format_vlm_title(vlm_analysis)
    payload = {"title": title, "candidates": matches, "l3_key": l3, "l2_key": l2, "l1_key": l1}
    path = vlm_matches_path(scene_id)
    path.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")
    return path, title, matches


def reconcile_clip_vlm(
    scene_id: str,
    clip_analysis: dict,
    vlm_analysis: dict,
    logger: Callable[[str], None],
    all_wavs: list[Path] | None = None,
) -> dict[str, Any]:
    """对比 CLIP 与 VLM 三层结论，写入 clip_matches / vlm_matches。

    返回:
      agree: bool — 结论一致，GUI 只显示 1_rain（采用 CLIP）
      clip_json, vlm_json — 文件路径
      rain_tab — '1_rain' | '1_rain_clip'
      show_vlm_tab — 是否显示 1_rain_vlm
    """
    wavs = all_wavs if all_wavs is not None else list_rain_wavs()
    clip_json, clip_title, _ = save_clip_matches(scene_id, clip_analysis, wavs)
    logger(f"已保存: {clip_json.name}")

    vlm_json = vlm_matches_path(scene_id)
    agree = clip_vlm_agree(clip_analysis, vlm_analysis)

    if not vlm_analysis:
        return {
            "agree": True,
            "clip_json": clip_json,
            "vlm_json": None,
            "clip_title": clip_title,
            "vlm_title": "",
            "rain_tab": "1_rain",
            "show_vlm_tab": False,
        }

    if agree:
        if vlm_json.is_file():
            vlm_json.unlink()
        logger("结论: CLIP 与 VLM 一致，采用 CLIP 配方。")
        return {
            "agree": True,
            "clip_json": clip_json,
            "vlm_json": None,
            "clip_title": clip_title,
            "vlm_title": "",
            "rain_tab": "1_rain",
            "show_vlm_tab": False,
        }

    vlm_json, vlm_title, _ = save_vlm_matches(scene_id, vlm_analysis, wavs)
    logger(f"已保存: {vlm_json.name}")
    logger("结论: CLIP 与 VLM 不一致，请对比 1_rain_clip / 1_rain_vlm 两个选项卡。")
    return {
        "agree": False,
        "clip_json": clip_json,
        "vlm_json": vlm_json,
        "clip_title": clip_title,
        "vlm_title": vlm_title,
        "rain_tab": "1_rain_clip",
        "show_vlm_tab": True,
    }


def update_lua_config_with_selections(
    config_path: Path,
    scene_id: str,
    duration: float,
    selected_tracks: dict,
    lib_repo_root: Path,
    log_fn: Callable[[str], None] | None = None,
) -> None:
    import sys

    reaper_scripts = lib_repo_root / "Reaper" / "scripts"
    if str(reaper_scripts) not in sys.path:
        sys.path.insert(0, str(reaper_scripts))

    from generate_subproject import load_config
    from rain_subproject_lib import SCENES, config_to_lua
    from scripts.audio_loudness import adjust_1_rain_layer_vol

    cfg = load_config(config_path)
    cfg["duration_hours"] = duration

    def format_path(p: Path) -> str:
        from scripts.paths import path_for_config
        return path_for_config(p)

    for layer in cfg.get("loop_layers", []):
        if layer.get("id") in selected_tracks:
            layer["paths"] = [format_path(selected_tracks[layer["id"]])]

    for layer in cfg.get("scatter_layers", []):
        if layer.get("id") in selected_tracks:
            layer["paths"] = [format_path(selected_tracks[layer["id"]])]

    adjust_1_rain_layer_vol(cfg, log=log_fn)

    lua = config_to_lua(cfg)
    config_path.write_text(lua, encoding="utf-8")

    SCENES.mkdir(parents=True, exist_ok=True)
    (SCENES / f"{scene_id}.lua").write_text(lua, encoding="utf-8")
