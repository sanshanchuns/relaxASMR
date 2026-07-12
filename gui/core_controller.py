"""核心逻辑控制器（Core Controller）。

负责解耦 app.py（纯 UI 层）与底层的各种业务逻辑（分析、写入配置、生成工程等）。
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Callable

from scripts.config.common_constants import CLIMATE_NAMES, CLOSE_NAMES, DISTANT_NAMES, SPACE_NAMES
from scripts.config.paths import audio_layer_dir, clip_matches_path, vlm_matches_path

# 步骤 2 稀疏层（散布轨）：选中后写入 Reaper 轨 2–4
SCATTER_LAYER_IDS = ("2_impact", "3_random", "4_wildlife")

# 步骤 2 中竞争 Reaper 1_rain loop 层的三个 tab（track_name）
RAIN_LOOP_EXCLUSIVE_TRACK_NAMES = frozenset({
    "1_rain_clip",
    "1_rain_vlm",
    "1_rain_boom",
    "1_rain",  # CLIP/VLM 一致时的单 tab
})

# track_pickers 字典 key（1_rain 对应 tab 显示名可能是 1_rain_clip 或 1_rain）
RAIN_LOOP_PICKER_KEYS = ("1_rain", "1_rain_vlm", "1_rain_boom")

# 防御性多选冲突时的优先级：boom > vlm > clip
RAIN_LOOP_PICKER_PRIORITY = ("1_rain_boom", "1_rain_vlm", "1_rain")


def is_rain_loop_exclusive_track_name(track_name: str) -> bool:
    return track_name in RAIN_LOOP_EXCLUSIVE_TRACK_NAMES


def collect_selected_tracks_for_reaper(
    track_pickers: dict[str, Any],
    *,
    log_fn: Callable[[str], None] | None = None,
) -> dict[str, Path]:
    """从步骤 2 拾取器收集写入 Reaper 的轨道路径。

    1_rain_clip / 1_rain_vlm / 1_rain_boom（及一致时的 1_rain）三者互斥，
    最终只写入 layer id ``1_rain`` 一条 loop 路径。
    """
    log = log_fn or (lambda _msg: None)
    selected: dict[str, Path] = {}

    rain_candidates: list[tuple[str, str, Path]] = []
    for key in RAIN_LOOP_PICKER_KEYS:
        picker = track_pickers.get(key)
        if not picker:
            continue
        sel = picker.get_selected()
        if sel:
            track_name = getattr(picker, "track_name", key)
            rain_candidates.append((key, track_name, Path(sel)))

    if rain_candidates:
        if len(rain_candidates) > 1:
            names = ", ".join(t[1] for t in rain_candidates)
            log(f"警告：多个 rain loop 选项同时选中 ({names})，按优先级只采用一个")
        chosen: tuple[str, Path] | None = None
        for key in RAIN_LOOP_PICKER_PRIORITY:
            for cand_key, track_name, sel in rain_candidates:
                if cand_key == key:
                    chosen = (track_name, sel)
                    break
            if chosen:
                break
        if chosen is None:
            chosen = (rain_candidates[0][1], rain_candidates[0][2])
        track_name, rain_path = chosen
        selected["1_rain"] = rain_path
        log(f"1_rain loop 层：{track_name} → {rain_path.name}")

    for tid, picker in track_pickers.items():
        if tid in RAIN_LOOP_PICKER_KEYS:
            continue
        sel = picker.get_selected()
        if sel:
            selected[tid] = Path(sel)
            if tid in SCATTER_LAYER_IDS:
                log(f"{tid} 散布层：{Path(sel).name}")
        elif tid in SCATTER_LAYER_IDS:
            log(f"{tid} 散布层：未选中，生成工程时将留空")
    return selected


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
    *,
    vlm_reconciled: bool = False,
) -> tuple[Path, str, list[dict[str, Any]]]:
    wavs = all_wavs if all_wavs is not None else list_rain_wavs()
    l3, l2, l1 = _layer_keys_from_clip(clip_analysis)
    matches = get_matches_for_keys(l3, l2, l1, wavs)
    title = format_clip_title(clip_analysis)
    payload = {
        "title": title,
        "candidates": matches,
        "l3_key": l3,
        "l2_key": l2,
        "l1_key": l1,
        "vlm_reconciled": vlm_reconciled,
    }
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


def clip_analysis_from_matches(clip_json: Path) -> dict:
    data = json.loads(clip_json.read_text(encoding="utf-8"))
    return {
        "l3": {"key": data.get("l3_key")},
        "l2": {"key": data.get("l2_key")},
        "l1": {"key": data.get("l1_key")},
    }


def load_cached_rain_tabs(scene_id: str) -> dict[str, Any] | None:
    """若 clip/vlm 匹配结果已存在，返回 _apply_rain_tabs 所需结构。"""
    clip_path = clip_matches_path(scene_id)
    if not clip_path.is_file():
        return None

    clip_data = json.loads(clip_path.read_text(encoding="utf-8"))
    clip_title = clip_data.get("title", "")
    vlm_path = vlm_matches_path(scene_id)

    if vlm_path.is_file():
        vlm_data = json.loads(vlm_path.read_text(encoding="utf-8"))
        return {
            "rain_tab": "1_rain_clip",
            "clip_json": clip_path,
            "clip_title": clip_title,
            "show_vlm_tab": True,
            "vlm_json": vlm_path,
            "vlm_title": vlm_data.get("title", ""),
            "partial": False,
        }

    if clip_data.get("vlm_reconciled") is False:
        return {
            "rain_tab": "1_rain_clip",
            "clip_json": clip_path,
            "clip_title": clip_title,
            "show_vlm_tab": False,
            "vlm_json": None,
            "vlm_title": "",
            "partial": True,
        }

    return {
        "rain_tab": "1_rain",
        "clip_json": clip_path,
        "clip_title": clip_title,
        "show_vlm_tab": False,
        "vlm_json": None,
        "vlm_title": "",
        "partial": False,
    }


def _mark_clip_vlm_reconciled(clip_json: Path, *, agree: bool) -> None:
    data = json.loads(clip_json.read_text(encoding="utf-8"))
    data["vlm_reconciled"] = True
    data["vlm_agree"] = agree
    clip_json.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")


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
        _mark_clip_vlm_reconciled(clip_json, agree=True)
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
        _mark_clip_vlm_reconciled(clip_json, agree=True)
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
    _mark_clip_vlm_reconciled(clip_json, agree=False)
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
