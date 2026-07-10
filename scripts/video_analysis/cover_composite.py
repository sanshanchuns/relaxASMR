"""封面合成：场景首帧 + 雨效 PNG overlay。"""

from __future__ import annotations

from pathlib import Path

import cv2
import numpy as np

from scripts.paths import ensure_rain_fx_png

DEFAULT_RAIN_OPACITY = 0.45


def _read_rain_overlay(rain_path: Path) -> np.ndarray:
    rain = cv2.imread(str(rain_path), cv2.IMREAD_COLOR)
    if rain is None:
        raise RuntimeError(f"无法读取雨效 PNG: {rain_path}")
    return rain


def _rain_alpha_mask(rain: np.ndarray) -> np.ndarray:
    """黑底雨效 PNG：用亮度做 alpha，并把雨丝归一化到满强度。"""
    gray = np.max(rain.astype(np.float32), axis=2)
    peak = max(float(gray.max()), 1.0)
    return np.clip(gray / peak, 0.0, 1.0)


def _composite_rain_on_black_bg(
    base: np.ndarray,
    rain: np.ndarray,
    opacity: float,
) -> np.ndarray:
    """黑底雨丝 PNG → 亮度当 alpha，雨丝按白色叠加到场景上。"""
    b = base.astype(np.float32)
    alpha = _rain_alpha_mask(rain) * opacity
    alpha3 = alpha[..., None]
    white = np.full_like(b, 255.0)
    result = b * (1.0 - alpha3) + white * alpha3
    return np.clip(result, 0, 255).astype(np.uint8)


def composite_rain_cover(
    base_path: Path,
    output_path: Path,
    rain_fx_path: Path | None = None,
    rain_opacity: float = DEFAULT_RAIN_OPACITY,
) -> Path:
    """将原始首帧与 fx/rain_fx.png 混合，写出封面 thumbnail。"""
    base_path = Path(base_path)
    out = Path(output_path)
    rain_path = Path(rain_fx_path) if rain_fx_path else ensure_rain_fx_png()

    if not base_path.is_file():
        raise FileNotFoundError(f"首帧不存在: {base_path}")
    if not rain_path.is_file():
        raise FileNotFoundError(f"雨效素材不存在: {rain_path}")

    base = cv2.imread(str(base_path))
    if base is None:
        raise RuntimeError(f"无法读取首帧: {base_path}")

    rain = _read_rain_overlay(rain_path)
    rain = cv2.resize(rain, (base.shape[1], base.shape[0]), interpolation=cv2.INTER_LINEAR)

    result = _composite_rain_on_black_bg(base, rain, rain_opacity)
    out.parent.mkdir(parents=True, exist_ok=True)
    cv2.imwrite(str(out), result, [cv2.IMWRITE_JPEG_QUALITY, 92])
    return out
