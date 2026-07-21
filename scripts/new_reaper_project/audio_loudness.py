"""音频响度测量与 Reaper 音量换算。"""

from __future__ import annotations

import json
import re
import subprocess
from pathlib import Path
from typing import Callable

from scripts.config.paths import REPO_ROOT

# YouTube 睡眠系列默认目标（可在 gui/user_config.json 用 lufs_target_min/max 覆盖）
DEFAULT_LUFS_TARGET_MIN = -28.0
DEFAULT_LUFS_TARGET_MAX = -28.0
# 1_rain ReaEQ + Group ReaEQ 默认旁路，响度归一按无 EQ 链路计算
DEFAULT_FX_COMPENSATION_DB = 0.0

MAX_ANALYZE_SECONDS = 180.0
VOL_MIN = 0.01
VOL_MAX = 128.0

# 稀疏层 2/4 轨道推子（item 固定 1.0）；3_random 由 LUFS 动态计算
SCATTER_LEGACY_TRACK_VOL: dict[str, float] = {
    "2_impact": 0.5,
    "4_wildlife": 0.28,
}
# 3_random 目标 = 1_rain LUFS 目标 + 此偏移（正值 = 高于主 bed；远处雷声需更响才听得到）
DEFAULT_3_RANDOM_LUFS_OFFSET_DB = 3.0
VOL_FALLBACK_3_RANDOM = 0.35


def _read_user_audio_cfg() -> dict:
    cfg_path = REPO_ROOT / "gui" / "user_config.json"
    if not cfg_path.is_file():
        return {}
    try:
        return json.loads(cfg_path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return {}


def resolve_lufs_target() -> tuple[float, float, float]:
    """读取 LUFS 目标区间，返回 (min, max, center)。"""
    lo, hi = DEFAULT_LUFS_TARGET_MIN, DEFAULT_LUFS_TARGET_MAX
    data = _read_user_audio_cfg()
    try:
        lo = float(data.get("lufs_target_min", lo))
        hi = float(data.get("lufs_target_max", hi))
    except (TypeError, ValueError):
        pass
    if lo > hi:
        lo, hi = hi, lo
    return lo, hi, (lo + hi) / 2.0


def resolve_fx_compensation_db() -> float:
    """Reaper 轨/Group FX 链响度补偿（dB），可在 user_config.json 微调。"""
    data = _read_user_audio_cfg()
    try:
        return float(data.get("lufs_fx_compensation_db", DEFAULT_FX_COMPENSATION_DB))
    except (TypeError, ValueError):
        return DEFAULT_FX_COMPENSATION_DB


def measure_lufs_i(path: Path, *, max_seconds: float = MAX_ANALYZE_SECONDS) -> float | None:
    """用 ffmpeg loudnorm 测量素材 LUFS-I（integrated）。"""
    path = Path(path)
    if not path.is_file():
        return None
    cmd = [
        "ffmpeg",
        "-hide_banner",
        "-nostats",
        "-t",
        str(max_seconds),
        "-i",
        str(path),
        "-af",
        "loudnorm=print_format=json",
        "-f",
        "null",
        "-",
    ]
    try:
        proc = subprocess.run(cmd, capture_output=True, text=True, check=False, timeout=120)
    except (subprocess.TimeoutExpired, FileNotFoundError, OSError):
        return None
    stderr = proc.stderr or ""
    match = re.search(r"\{[\s\S]*\}", stderr)
    if not match:
        return None
    try:
        data = json.loads(match.group())
        return float(data["input_i"])
    except (json.JSONDecodeError, KeyError, TypeError, ValueError):
        return None


def vol_for_target_lufs(
    measured_lufs: float,
    target_lufs: float,
    *,
    fx_compensation_db: float = 0.0,
) -> float:
    """素材在 vol=1.0 时测得 measured_lufs，返回达到 target 所需的轨道推子 vol。"""
    gain_db = target_lufs - measured_lufs + fx_compensation_db
    vol = 10 ** (gain_db / 20.0)
    return max(VOL_MIN, min(VOL_MAX, vol))


def resolve_3_random_lufs_offset_db() -> float:
    data = _read_user_audio_cfg()
    try:
        return float(data.get("random_lufs_offset_db", DEFAULT_3_RANDOM_LUFS_OFFSET_DB))
    except (TypeError, ValueError):
        return DEFAULT_3_RANDOM_LUFS_OFFSET_DB


def _find_scatter_layer(cfg: dict, layer_id: str) -> dict | None:
    for layer in cfg.get("scatter_layers", []):
        if layer.get("id") == layer_id:
            return layer
    return None


def _scatter_paths(layer: dict) -> list[Path]:
    return [Path(p) for p in layer.get("paths", []) if p and Path(p).is_file()]


def _measure_loudest_lufs(paths: list[Path]) -> tuple[float | None, Path | None]:
    best: float | None = None
    best_path: Path | None = None
    for wav in paths:
        measured = measure_lufs_i(wav)
        if measured is not None and (best is None or measured > best):
            best = measured
            best_path = wav
    return best, best_path


def adjust_3_random_layer_vol(
    cfg: dict,
    *,
    log: Callable[[str], None] | None = None,
) -> dict | None:
    """3_random：按 booms 实测 LUFS 写轨道推子（item 保持 1.0），高于主 bed 约 3 LU（远处雷声）。"""
    layer = _find_scatter_layer(cfg, "3_random")
    if not layer:
        return None

    paths = _scatter_paths(layer)
    if not paths:
        if log:
            log("3_random 未选择素材，跳过响度归一化")
        return None

    _, _, rain_target = resolve_lufs_target()
    offset = resolve_3_random_lufs_offset_db()
    target_lufs = rain_target + offset
    fx_comp = resolve_fx_compensation_db()

    measured, wav = _measure_loudest_lufs(paths)
    if measured is None or wav is None:
        layer["vol"] = VOL_FALLBACK_3_RANDOM
        if log:
            log(f"3_random 响度测量失败，推子 fallback vol={VOL_FALLBACK_3_RANDOM}")
        return {"fallback_vol": VOL_FALLBACK_3_RANDOM, "wav": paths[0]}

    new_vol = round(
        vol_for_target_lufs(measured, target_lufs, fx_compensation_db=fx_comp),
        4,
    )
    layer["vol"] = new_vol

    info = {
        "measured_lufs": measured,
        "target_lufs": target_lufs,
        "rain_target_lufs": rain_target,
        "offset_db": offset,
        "fx_compensation_db": fx_comp,
        "new_vol": new_vol,
        "wav": wav,
    }
    if log:
        capped = "（已触及上限）" if new_vol >= VOL_MAX else ""
        log(
            f"3_random [{wav.name}] 实测 {measured:.1f} LUFS-I → "
            f"目标 {target_lufs:.1f}（主 bed {rain_target:.1f}{offset:+.0f} LU），"
            f"推子 vol → {new_vol:.3f}{capped}"
            + (f"（FX 补偿 +{fx_comp:.1f} dB）" if fx_comp else "")
        )
    return info


def apply_scatter_layer_vols(
    cfg: dict,
    *,
    log: Callable[[str], None] | None = None,
) -> None:
    """稀疏层推子：3_random 动态 LUFS；4_wildlife legacy 固定；2_impact 循环层 legacy 固定；item 均为 1.0。"""
    adjust_3_random_layer_vol(cfg, log=log)

    for layer in cfg.get("loop_layers", []):
        lid = layer.get("id", "")
        if lid != "2_impact" or not _scatter_paths(layer):
            continue
        legacy = SCATTER_LEGACY_TRACK_VOL.get(lid)
        if legacy is None:
            continue
        layer["vol"] = legacy
        if log:
            log(f"2_impact 推子 vol → {legacy:.2f}（legacy 固定，循环层）")

    for layer in cfg.get("scatter_layers", []):
        lid = layer.get("id", "")
        if lid == "3_random":
            continue
        if not _scatter_paths(layer):
            continue
        legacy = SCATTER_LEGACY_TRACK_VOL.get(lid)
        if legacy is None:
            continue
        layer["vol"] = legacy
        if log:
            log(f"{lid} 推子 vol → {legacy:.2f}（legacy 固定）")


def adjust_1_rain_layer_vol(
    cfg: dict,
    *,
    target_lufs: float | None = None,
    log: Callable[[str], None] | None = None,
) -> dict | None:
    """按当前选中的 1_rain WAV 实测 LUFS-I，动态写入该轨 fader vol（item 保持 1.0）。

    增益只作用于轨道推子；.rpp 中 item VOLPAN 固定为 1.0，避免推子+item 叠乘。
    另加可选 FX 链补偿（默认 0；若手动启用 EQ 可在 user_config 调高 lufs_fx_compensation_db）。
    """
    rain_layer = None
    for layer in cfg.get("loop_layers", []):
        if layer.get("id") == "1_rain":
            rain_layer = layer
            break
    if not rain_layer:
        return None

    paths = [p for p in rain_layer.get("paths", []) if p]
    if not paths:
        if log:
            log("1_rain 未选择素材，跳过响度归一化")
        return None

    if target_lufs is None:
        _, _, target_lufs = resolve_lufs_target()

    fx_comp = resolve_fx_compensation_db()
    wav = Path(paths[0])
    measured = measure_lufs_i(wav)
    if measured is None:
        if log:
            log(f"1_rain 响度测量失败，保持 vol={rain_layer.get('vol', 1.0)}")
        return None

    new_vol = round(
        vol_for_target_lufs(measured, target_lufs, fx_compensation_db=fx_comp),
        4,
    )
    rain_layer["vol"] = new_vol

    info = {
        "measured_lufs": measured,
        "target_lufs": target_lufs,
        "fx_compensation_db": fx_comp,
        "new_vol": new_vol,
        "wav": wav,
    }
    if log:
        lo, hi, _ = resolve_lufs_target()
        capped = "（已触及上限）" if new_vol >= VOL_MAX else ""
        log(
            f"1_rain [{wav.name}] 实测 {measured:.1f} LUFS-I → "
            f"目标 {target_lufs:.1f}（{lo:.0f}~{hi:.0f}），"
            f"推子 vol → {new_vol:.3f}{capped}"
            + (f"（FX 补偿 +{fx_comp:.1f} dB）" if fx_comp else "")
        )
    return info
