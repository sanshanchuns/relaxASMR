"""theory.md §一 三种色噪声分类与类型贴合度。"""

from __future__ import annotations

import math

NOISE_TYPES = ("pink", "white", "brown")

# log10(power) vs log10(freq) 理想斜率
IDEAL_SLOPES = {
    "pink": -1.0,   # −3 dB/倍频程
    "white": 0.0,
    "brown": -2.0,  # −6 dB/倍频程
}

TYPE_META = {
    "pink": {
        "label_zh": "粉红噪声",
        "scene_zh": "毛毛雨、细雨拂叶",
        "use_zh": "深度助眠、慢波同步",
        "recommended_mode": "sleep",
        "rs_pass_note": "RS-PASS 以 sleep 域（N_5≤3 Sone）评估",
    },
    "white": {
        "label_zh": "白噪声",
        "scene_zh": "开阔地降雨、林间暴雨",
        "use_zh": "声学掩蔽、专注心流",
        "recommended_mode": "focus",
        "rs_pass_note": "RS-PASS 以 focus 域（N_5≤8 Sone）评估；不宜整夜助眠",
    },
    "brown": {
        "label_zh": "棕色噪声",
        "scene_zh": "强降雨、远雷、深沉瀑布",
        "use_zh": "深度镇静、冥想、庇护所边界感",
        "recommended_mode": "sleep",
        "rs_pass_note": "RS-PASS 以 sleep 域评估；注意超低频不过量",
    },
}

# 类型内 S_50 容忍（白噪天然偏高频）
S50_LIMIT_BY_TYPE = {
    "pink": 1.1,
    "white": 1.35,
    "brown": 1.0,
}


def clip(x: float, lo: float = 0.0, hi: float = 1.0) -> float:
    return max(lo, min(hi, x))


def psd_slope(mono, sr: int, lo: float = 100.0, hi: float = 8000.0) -> float:
    import numpy as np

    n = min(len(mono), sr * 120)
    x = mono[:n]
    fft = np.abs(np.fft.rfft(x))
    freqs = np.fft.rfftfreq(len(x), 1 / sr)
    power = fft ** 2
    mask = (freqs >= lo) & (freqs <= hi)
    f = freqs[mask]
    p = power[mask]
    if len(f) < 8:
        return 0.0
    log_f = np.log10(f)
    log_p = np.log10(np.maximum(p, 1e-20))
    slope, _ = np.polyfit(log_f, log_p, 1)
    return float(slope)


def classify_noise_type(slope: float) -> dict:
    """最近邻 + 置信度（斜率距理想值）。"""
    dists = {t: abs(slope - IDEAL_SLOPES[t]) for t in NOISE_TYPES}
    primary = min(dists, key=dists.get)
    sorted_d = sorted(dists.values())
    gap = sorted_d[1] - sorted_d[0] if len(sorted_d) > 1 else 1.0
    confidence = clip(1.0 - sorted_d[0] / 0.55) * clip(gap / 0.25)
    secondary = None
    if gap < 0.12:
        others = [t for t in NOISE_TYPES if t != primary]
        secondary = min(others, key=lambda t: dists[t])
    return {
        "primary": primary,
        "secondary": secondary,
        "slope": round(slope, 3),
        "confidence": round(confidence, 3),
        "ideal_slope": IDEAL_SLOPES[primary],
        "distances": {k: round(v, 3) for k, v in dists.items()},
    }


def score_type_fit(slope: float, noise_type: str) -> dict:
    ideal = IDEAL_SLOPES[noise_type]
    dev = abs(slope - ideal)
    raw = clip(1.0 - dev / 0.55)
    return {
        "score": round(100 * raw, 1),
        "slope": round(slope, 3),
        "ideal_slope": ideal,
        "deviation": round(dev, 3),
    }


def score_type_spectrum(noise_type: str, band_pct: dict) -> dict:
    """类型典型频段轮廓加分（辅助 type_fit）。"""
    sub = band_pct.get("sub_low", 0)
    mid = band_pct.get("mid", 0) + band_pct.get("low_mid", 0)
    high = band_pct.get("high_mid", 0) + band_pct.get("high_5k", 0)
    if noise_type == "pink":
        raw = clip(1.0 - abs(mid - 45) / 35) * clip(1.0 - max(0, high - 35) / 35)
    elif noise_type == "white":
        spread = abs(sub - 15) + abs(mid - 30) + abs(high - 25)
        raw = clip(1.0 - spread / 80)
    else:  # brown
        raw = clip(sub / 30) * clip(1.0 - max(0, high - 20) / 30)
    return {
        "score": round(100 * raw, 1),
        "sub_low_pct": sub,
        "mid_pct": mid,
        "high_pct": high,
    }


def combined_type_score(slope: float, noise_type: str, band_pct: dict) -> dict:
    fit = score_type_fit(slope, noise_type)
    spec = score_type_spectrum(noise_type, band_pct)
    total = 0.65 * fit["score"] + 0.35 * spec["score"]
    meta = TYPE_META[noise_type]
    return {
        "noise_type": noise_type,
        "type_fit_score": round(total, 1),
        "slope_fit": fit,
        "spectrum_fit": spec,
        "label_zh": meta["label_zh"],
        "recommended_mode": meta["recommended_mode"],
        "use_zh": meta["use_zh"],
    }
