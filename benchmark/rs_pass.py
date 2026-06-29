"""RS-PASS 心理声学近似测量与打分（benchmark/theory.md §四）。"""

from __future__ import annotations

import subprocess
from pathlib import Path

from noise_type import (
    S50_LIMIT_BY_TYPE,
    TYPE_META,
    classify_noise_type,
    combined_type_score,
    psd_slope,
)

DEFAULT_DURATION = 1800.0

# theory.md RS-PASS 权重
RS_PASS_WEIGHTS: dict[str, float] = {
    "n5_peak_loudness": 0.22,
    "s50_sharpness": 0.18,
    "r5_roughness": 0.13,
    "iacc": 0.13,
    "f50_fluctuation": 0.09,
    "si_irregularity": 0.09,
    "tmax_tonality": 0.06,
    "crest_headroom": 0.10,  # peak−RMS，惩罚稀疏尖峰
}

# 目标域：ideal = 满分甜区；outer = 超出则趋近 0（非仅「不超标即满分」）
TARGETS = {
    "sleep": {
        "n5_sone": {"ideal": (1.0, 2.2), "outer": (0.35, 3.0)},
        "n5_drift_db": {"ideal": (5.0, 9.0), "outer": (2.0, 14.0)},  # P95−P5 宏观起伏
    },
    "focus": {
        "n5_sone": {"ideal": (2.5, 5.5), "outer": (1.0, 8.0)},
        "n5_drift_db": {"ideal": (3.0, 9.0), "outer": (1.0, 14.0)},
    },
    "s50_acum": {"ideal": (0.40, 0.48), "outer": (0.24, 0.72)},
    "r5_asper": {"ideal": (0.022, 0.048), "outer": (0.008, 0.09)},
    "iacc": {"ideal": (0.12, 0.26), "outer": (0.04, 0.48)},  # 过低=假宽，过高=窄
    "f50_vacil": {"ideal": (0.07, 0.11), "outer": (0.025, 0.17)},
    "si": {"ideal": (0.14, 0.22), "outer": (0.08, 0.30)},
    "tmax": {"ideal": (0.0, 0.004), "outer": (0.0, 0.025)},
    "crest_db": {"ideal": (14.0, 22.0), "outer": (8.0, 32.0)},  # peak−RMS，偶发尖峰
}


def clip(x: float, lo: float = 0.0, hi: float = 1.0) -> float:
    return max(lo, min(hi, x))


def probe_media_duration(path: Path) -> float | None:
    proc = subprocess.run(
        [
            "ffprobe", "-v", "error",
            "-show_entries", "format=duration",
            "-of", "default=noprint_wrappers=1:nokey=1",
            str(path),
        ],
        capture_output=True,
        text=True,
    )
    if proc.returncode != 0:
        return None
    try:
        d = float(proc.stdout.strip())
    except ValueError:
        return None
    return d if d > 0 else None


def resolve_analysis_duration(path: Path, duration: float) -> tuple[float, float | None]:
    """返回 (实际分析秒数, 媒体总时长)。不足 duration 时分析全长。"""
    file_dur = probe_media_duration(path)
    if file_dur is None:
        return duration, None
    return min(duration, file_dur), file_dur


def load_stereo(path: Path, duration: float) -> tuple:
    import numpy as np

    sr = 48000
    proc = subprocess.run(
        [
            "ffmpeg", "-v", "error", "-i", str(path),
            "-t", str(duration), "-ac", "2", "-ar", str(sr),
            "-f", "f32le", "-",
        ],
        capture_output=True,
        check=True,
    )
    data = np.frombuffer(proc.stdout, dtype="<f4")
    if data.size % 2:
        data = data[:-1]
    stereo = data.reshape(-1, 2)
    return (
        stereo[:, 0].astype(np.float64),
        stereo[:, 1].astype(np.float64),
        sr,
    )


def frame_rms_db(x, frame: int) -> list[float]:
    import numpy as np

    n = len(x) // frame
    if n < 1:
        return [-120.0]
    blocks = x[: n * frame].reshape(n, frame)
    rms = np.sqrt(np.mean(blocks ** 2, axis=1))
    return [float(20 * np.log10(max(r, 1e-12))) for r in rms]


def db_to_sone_approx(db: float) -> float:
    """宽带噪声响度粗估（非实验室级 Zwicker）。"""
    phon = db + 70.0
    if phon <= 40.0:
        return max(0.0, phon / 40.0)
    return ((phon - 40.0) / 10.0) ** 2.86 / 50.0


def bandpass_fft(x, sr: int, lo: float, hi: float):
    import numpy as np

    n = len(x)
    fft = np.fft.rfft(x)
    freqs = np.fft.rfftfreq(n, 1 / sr)
    mask = (freqs >= lo) & (freqs < hi)
    fft[~mask] = 0
    return np.fft.irfft(fft, n=n)


def envelope_modulation_depth(x, sr: int, mod_lo: float, mod_hi: float) -> float:
    """带通信号包络在调制频段的相对深度。"""
    import numpy as np

    if len(x) < sr // 2:
        return 0.0
    analytic = bandpass_fft(x, sr, 500, min(8000, sr / 2 - 1))
    env = np.abs(analytic)
    hop = max(1, sr // 100)
    n = len(env) // hop
    if n < 8:
        return 0.0
    env_s = env[: n * hop].reshape(n, hop).mean(axis=1)
    env_s = env_s - np.mean(env_s)
    if np.std(env_s) < 1e-12:
        return 0.0
    spec = np.abs(np.fft.rfft(env_s))
    freqs = np.fft.rfftfreq(len(env_s), hop / sr)
    mask = (freqs >= mod_lo) & (freqs <= mod_hi)
    mod_e = float(np.sum(spec[mask] ** 2))
    total_e = float(np.sum(spec ** 2)) or 1.0
    return mod_e / total_e


def compute_iacc(L, R, sr: int, frame_ms: float = 20.0) -> float:
    import numpy as np

    frame = max(64, int(sr * frame_ms / 1000))
    vals: list[float] = []
    for i in range(0, len(L) - frame, frame):
        l = L[i : i + frame]
        r = R[i : i + frame]
        nl = float(np.sqrt(np.sum(l ** 2)))
        nr = float(np.sqrt(np.sum(r ** 2)))
        if nl < 1e-12 or nr < 1e-12:
            continue
        c = np.correlate(l, r, mode="full")
        vals.append(float(np.max(np.abs(c)) / (nl * nr)))
    return float(np.mean(vals)) if vals else 1.0


def sharpness_proxy(mono, sr: int) -> float:
    """尖锐度代理（Acum 量级启发式）。"""
    import numpy as np

    n = min(len(mono), sr * 120)
    x = mono[:n]
    fft = np.abs(np.fft.rfft(x))
    freqs = np.fft.rfftfreq(len(x), 1 / sr)
    mask = freqs >= 500
    p = fft[mask] ** 2
    f = freqs[mask]
    if np.sum(p) < 1e-20:
        return 0.0
    # DIN 45692 风格：高频权重递增
    g = (f - 500) / 1000.0
    return float(0.11 * np.sum(g * p) / (np.sum(p) + 1e-20) * 2.4)


def spectral_irregularity(mono, sr: int) -> float:
    """光谱不规则度：log 谱相对平滑包络的起伏。"""
    import numpy as np

    n = min(len(mono), sr * 120)
    x = mono[:n]
    fft = np.abs(np.fft.rfft(x))
    freqs = np.fft.rfftfreq(len(x), 1 / sr)
    mask = (freqs >= 200) & (freqs <= 8000)
    p = np.maximum(fft[mask], 1e-12)
    log_p = np.log10(p)
    kernel = 9
    pad = kernel // 2
    lp = np.pad(log_p, pad, mode="edge")
    smooth = np.array([np.mean(lp[i : i + kernel]) for i in range(len(log_p))])
    return float(np.std(log_p - smooth))


def tonality_max(mono, sr: int) -> float:
    """纯音色调度：窄带峰相对局部平滑谱的最大突出度。"""
    import numpy as np

    n = min(len(mono), sr * 120)
    x = mono[:n]
    fft = np.abs(np.fft.rfft(x))
    freqs = np.fft.rfftfreq(len(x), 1 / sr)
    mask = (freqs >= 80) & (freqs <= 6000)
    p = fft[mask] ** 2
    if p.size < 16:
        return 0.0
    total = float(np.sum(p)) or 1.0
    kernel = 11
    pad = kernel // 2
    pp = np.pad(p, pad, mode="edge")
    smooth = np.array([np.mean(pp[i : i + kernel]) for i in range(len(p))])
    prominence = p / (smooth + 1e-20)
    return float(np.max(prominence) * np.max(p) / total)


def band_pct(mono, sr) -> dict:
    import numpy as np

    fft = np.abs(np.fft.rfft(mono))
    freqs = np.fft.rfftfreq(len(mono), 1 / sr)
    power = fft ** 2

    def be(lo, hi):
        return float(np.sum(power[(freqs >= lo) & (freqs < hi)]))

    bands = {
        "sub_low": be(20, 200),
        "low_mid": be(200, 500),
        "mid": be(500, 2000),
        "high_mid": be(2000, 6000),
        "high_5k": be(5000, sr / 2),
    }
    total = sum(bands.values()) or 1.0
    return {k: round(100 * v / total, 2) for k, v in bands.items()}


def measure_rs_pass(path: Path, duration: float) -> dict:
    import numpy as np

    analyze_dur, file_dur = resolve_analysis_duration(path, duration)
    L, R, sr = load_stereo(path, analyze_dur)
    mono = (L + R) / 2.0
    actual_dur = len(mono) / sr

    frame = max(1, int(sr * 0.1))
    rms_db_frames = frame_rms_db(mono, frame)
    p95_db = float(np.percentile(rms_db_frames, 95))
    p5_db = float(np.percentile(rms_db_frames, 5))
    n5_sone = db_to_sone_approx(p95_db)

    s50 = sharpness_proxy(mono, sr)
    r5 = envelope_modulation_depth(mono, sr, 30.0, 200.0) * 0.35
    iacc = compute_iacc(L, R, sr)
    f50 = envelope_modulation_depth(mono, sr, 0.08, 1.2) * 0.65
    si = spectral_irregularity(mono, sr)
    tmax = tonality_max(mono, sr)
    bp = band_pct(mono, sr)
    slope = psd_slope(mono, sr)

    rms = float(np.sqrt(np.mean(mono ** 2)))
    rms_dbfs = 20 * np.log10(max(rms, 1e-12))
    peak_dbfs = 20 * np.log10(float(np.max(np.abs(mono))) + 1e-12)

    return {
        "source": str(path),
        "duration_requested_s": round(duration, 2),
        "duration_file_s": round(file_dur, 2) if file_dur is not None else None,
        "duration_analyzed_s": round(actual_dur, 2),
        "n5_sone_est": round(n5_sone, 3),
        "n5_p95_dbfs": round(p95_db, 2),
        "n5_p5_dbfs": round(p5_db, 2),
        "s50_acum_est": round(s50, 3),
        "r5_asper_est": round(r5, 4),
        "iacc": round(iacc, 3),
        "f50_vacil_est": round(f50, 4),
        "si": round(si, 4),
        "tmax": round(tmax, 4),
        "psd_slope": round(slope, 3),
        "band_pct": bp,
        "rms_dbfs": round(rms_dbfs, 2),
        "peak_dbfs": round(peak_dbfs, 2),
    }


def score_band(value: float, ideal_lo: float, ideal_hi: float, outer_lo: float, outer_hi: float) -> float:
    """ideal 区间内 1.0；向外线性衰减至 outer 边界为 0。"""
    if outer_lo >= outer_hi or ideal_lo > ideal_hi:
        return 0.0
    if value <= outer_lo or value >= outer_hi:
        return 0.0
    if ideal_lo <= value <= ideal_hi:
        return 1.0
    if value < ideal_lo:
        return clip((value - outer_lo) / (ideal_lo - outer_lo))
    return clip((outer_hi - value) / (outer_hi - ideal_hi))


def band_score(value: float, spec: dict) -> float:
    il, ih = spec["ideal"]
    ol, oh = spec["outer"]
    return score_band(value, il, ih, ol, oh)


def score_in_range(value: float, lo: float, hi: float, margin: float = 0.5) -> float:
    if lo <= value <= hi:
        return 1.0
    if value < lo:
        return clip(1.0 - (lo - value) / (margin * lo + 1e-9))
    return clip(1.0 - (value - hi) / (margin * hi + 1e-9))


def score_n5(m: dict, mode: str) -> dict:
    t = TARGETS[mode]
    sone_raw = band_score(m["n5_sone_est"], t["n5_sone"])
    drift_db = m["n5_p95_dbfs"] - m["n5_p5_dbfs"]
    drift_raw = band_score(drift_db, t["n5_drift_db"])
    raw = 0.65 * sone_raw + 0.35 * drift_raw
    return {
        "score": round(100 * raw, 1),
        "n5_sone_est": m["n5_sone_est"],
        "n5_drift_db": round(drift_db, 2),
        "sone_band_score": round(100 * sone_raw, 1),
        "drift_band_score": round(100 * drift_raw, 1),
        "mode": mode,
        "p95_dbfs": m["n5_p95_dbfs"],
        "p5_dbfs": m["n5_p5_dbfs"],
    }


def score_s50(m: dict) -> dict:
    raw = band_score(m["s50_acum_est"], TARGETS["s50_acum"])
    return {
        "score": round(100 * raw, 1),
        "s50_acum_est": m["s50_acum_est"],
        "ideal": TARGETS["s50_acum"]["ideal"],
        "outer": TARGETS["s50_acum"]["outer"],
    }


def score_r5(m: dict) -> dict:
    raw = band_score(m["r5_asper_est"], TARGETS["r5_asper"])
    return {
        "score": round(100 * raw, 1),
        "r5_asper_est": m["r5_asper_est"],
        "ideal": TARGETS["r5_asper"]["ideal"],
        "outer": TARGETS["r5_asper"]["outer"],
    }


def score_iacc(m: dict) -> dict:
    raw = band_score(m["iacc"], TARGETS["iacc"])
    return {
        "score": round(100 * raw, 1),
        "iacc": m["iacc"],
        "ideal": TARGETS["iacc"]["ideal"],
        "outer": TARGETS["iacc"]["outer"],
    }


def score_f50(m: dict) -> dict:
    raw = band_score(m["f50_vacil_est"], TARGETS["f50_vacil"])
    return {
        "score": round(100 * raw, 1),
        "f50_vacil_est": m["f50_vacil_est"],
        "ideal": TARGETS["f50_vacil"]["ideal"],
        "outer": TARGETS["f50_vacil"]["outer"],
    }


def score_si(m: dict) -> dict:
    raw = band_score(m["si"], TARGETS["si"])
    return {
        "score": round(100 * raw, 1),
        "si": m["si"],
        "ideal": TARGETS["si"]["ideal"],
        "outer": TARGETS["si"]["outer"],
    }


def score_tmax(m: dict) -> dict:
    raw = band_score(m["tmax"], TARGETS["tmax"])
    return {
        "score": round(100 * raw, 1),
        "tmax": m["tmax"],
        "ideal": TARGETS["tmax"]["ideal"],
        "outer": TARGETS["tmax"]["outer"],
    }


def score_crest(m: dict) -> dict:
    """peak−RMS；稀疏层/导出尖峰会拉低分。"""
    crest = m["peak_dbfs"] - m["rms_dbfs"]
    raw = band_score(crest, TARGETS["crest_db"])
    return {
        "score": round(100 * raw, 1),
        "crest_db": round(crest, 2),
        "ideal": TARGETS["crest_db"]["ideal"],
        "outer": TARGETS["crest_db"]["outer"],
    }


def rs_pass_grade(total: float) -> str:
    if total >= 88:
        return "极品"
    if total >= 81:
        return "优秀"
    if total >= 62:
        return "普通"
    return "劣质"


def score_rs_pass(
    path: Path,
    duration: float = DEFAULT_DURATION,
    mode: str | None = None,
    *,
    auto_mode: bool = True,
    project: dict | None = None,
) -> dict:
    from recommendations import build_recommendations

    m = measure_rs_pass(path, duration)
    noise = classify_noise_type(m["psd_slope"])
    primary = noise["primary"]
    type_fit = combined_type_score(m["psd_slope"], primary, m["band_pct"])

    eval_mode = mode
    if eval_mode is None and auto_mode:
        eval_mode = TYPE_META[primary]["recommended_mode"]
    elif eval_mode is None:
        eval_mode = "sleep"

    dims = {
        "n5_peak_loudness": score_n5(m, eval_mode),
        "s50_sharpness": score_s50(m, primary),
        "r5_roughness": score_r5(m),
        "iacc": score_iacc(m),
        "f50_fluctuation": score_f50(m),
        "si_irregularity": score_si(m),
        "tmax_tonality": score_tmax(m),
        "crest_headroom": score_crest(m),
    }
    rs_pass_total = sum(dims[k]["score"] * RS_PASS_WEIGHTS[k] for k in RS_PASS_WEIGHTS)

    # 综合分：RS-PASS 85% + 类型贴合 15%
    total = 0.85 * rs_pass_total + 0.15 * type_fit["type_fit_score"]

    result = {
        "standard": "RS-PASS",
        "theory": "benchmark/theory.md",
        "file": str(path),
        "mode": eval_mode,
        "mode_requested": mode,
        "duration_requested_s": m.get("duration_requested_s", duration),
        "duration_file_s": m.get("duration_file_s"),
        "duration_s": m["duration_analyzed_s"],
        "total_score": round(total, 1),
        "rs_pass_score": round(rs_pass_total, 1),
        "grade": rs_pass_grade(total),
        "weights": RS_PASS_WEIGHTS,
        "dimensions": dims,
        "measurements": m,
        "noise_type": {
            **noise,
            "label_zh": TYPE_META[primary]["label_zh"],
            "use_zh": TYPE_META[primary]["use_zh"],
            "recommended_mode": TYPE_META[primary]["recommended_mode"],
        },
        "type_fit": type_fit,
        "project": {
            "rpp_path": (project or {}).get("rpp_path"),
            "config_path": (project or {}).get("config_path"),
            "mix": (project or {}).get("mix"),
        }
        if project
        else None,
    }
    result["recommendations"] = build_recommendations(
        result, project, intent_mode=mode or eval_mode
    )
    return result
