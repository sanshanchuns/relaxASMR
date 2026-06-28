"""RS-PASS 心理声学近似测量与打分（benchmark/theory.md §四）。"""

from __future__ import annotations

import subprocess
from pathlib import Path

DEFAULT_DURATION = 300.0

# theory.md RS-PASS 权重
RS_PASS_WEIGHTS: dict[str, float] = {
    "n5_peak_loudness": 0.25,
    "s50_sharpness": 0.20,
    "r5_roughness": 0.15,
    "iacc": 0.15,
    "f50_fluctuation": 0.10,
    "si_irregularity": 0.10,
    "tmax_tonality": 0.05,
}

# 目标域（理论值；脚本用可测代理量标定）
TARGETS = {
    "sleep": {"n5_sone_max": 3.0},
    "focus": {"n5_sone_max": 8.0},
    "s50_acum_max": 1.1,
    "r5_asper_max": 0.08,
    "iacc_max": 0.3,
    "f50_vacil_range": (0.03, 0.18),
    "tmax_max": 0.02,
    "si_range": (0.06, 0.28),
}


def clip(x: float, lo: float = 0.0, hi: float = 1.0) -> float:
    return max(lo, min(hi, x))


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


def measure_rs_pass(path: Path, duration: float) -> dict:
    import numpy as np

    L, R, sr = load_stereo(path, duration)
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

    rms = float(np.sqrt(np.mean(mono ** 2)))
    rms_dbfs = 20 * np.log10(max(rms, 1e-12))
    peak_dbfs = 20 * np.log10(float(np.max(np.abs(mono))) + 1e-12)

    return {
        "source": str(path),
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
        "rms_dbfs": round(rms_dbfs, 2),
        "peak_dbfs": round(peak_dbfs, 2),
    }


def score_in_range(value: float, lo: float, hi: float, margin: float = 0.5) -> float:
    if lo <= value <= hi:
        return 1.0
    if value < lo:
        return clip(1.0 - (lo - value) / (margin * lo + 1e-9))
    return clip(1.0 - (value - hi) / (margin * hi + 1e-9))


def score_n5(m: dict, mode: str) -> dict:
    limit = TARGETS["sleep"]["n5_sone_max"] if mode == "sleep" else TARGETS["focus"]["n5_sone_max"]
    sone = m["n5_sone_est"]
    raw = clip(1.0 - max(0.0, sone - limit) / limit)
    # 过静也略扣（缺乏掩蔽）
    if sone < 0.15:
        raw *= 0.85
    return {
        "score": round(100 * raw, 1),
        "n5_sone_est": sone,
        "target_sone_max": limit,
        "mode": mode,
        "p95_dbfs": m["n5_p95_dbfs"],
    }


def score_s50(m: dict) -> dict:
    limit = TARGETS["s50_acum_max"]
    raw = clip(1.0 - max(0.0, m["s50_acum_est"] - limit) / limit)
    return {
        "score": round(100 * raw, 1),
        "s50_acum_est": m["s50_acum_est"],
        "target_max": limit,
    }


def score_r5(m: dict) -> dict:
    limit = TARGETS["r5_asper_max"]
    raw = clip(1.0 - max(0.0, m["r5_asper_est"] - limit) / (limit * 2))
    return {
        "score": round(100 * raw, 1),
        "r5_asper_est": m["r5_asper_est"],
        "target_max": limit,
    }


def score_iacc(m: dict) -> dict:
    """越低越好 → 包裹感越强。"""
    v = m["iacc"]
    limit = TARGETS["iacc_max"]
    if v <= limit:
        raw = 1.0
    else:
        raw = clip(1.0 - (v - limit) / (1.0 - limit))
    return {
        "score": round(100 * raw, 1),
        "iacc": v,
        "target_max": limit,
    }


def score_f50(m: dict) -> dict:
    lo, hi = TARGETS["f50_vacil_range"]
    raw = score_in_range(m["f50_vacil_est"], lo, hi, margin=0.4)
    return {
        "score": round(100 * raw, 1),
        "f50_vacil_est": m["f50_vacil_est"],
        "target_range": (lo, hi),
    }


def score_si(m: dict) -> dict:
    lo, hi = TARGETS["si_range"]
    raw = score_in_range(m["si"], lo, hi, margin=0.35)
    return {
        "score": round(100 * raw, 1),
        "si": m["si"],
        "target_range": (lo, hi),
    }


def score_tmax(m: dict) -> dict:
    limit = TARGETS["tmax_max"]
    v = m["tmax"]
    raw = clip(1.0 - max(0.0, v - limit) / (limit * 3 + 1e-9))
    return {
        "score": round(100 * raw, 1),
        "tmax": v,
        "target_max": limit,
    }


def rs_pass_grade(total: float) -> str:
    if total >= 90:
        return "极品"
    if total >= 75:
        return "优秀"
    if total >= 60:
        return "普通"
    return "劣质"


def score_rs_pass(path: Path, duration: float = DEFAULT_DURATION, mode: str = "sleep") -> dict:
    m = measure_rs_pass(path, duration)
    dims = {
        "n5_peak_loudness": score_n5(m, mode),
        "s50_sharpness": score_s50(m),
        "r5_roughness": score_r5(m),
        "iacc": score_iacc(m),
        "f50_fluctuation": score_f50(m),
        "si_irregularity": score_si(m),
        "tmax_tonality": score_tmax(m),
    }
    total = sum(dims[k]["score"] * RS_PASS_WEIGHTS[k] for k in RS_PASS_WEIGHTS)
    return {
        "standard": "RS-PASS",
        "theory": "benchmark/theory.md",
        "file": str(path),
        "mode": mode,
        "duration_s": m["duration_analyzed_s"],
        "total_score": round(total, 1),
        "grade": rs_pass_grade(total),
        "weights": RS_PASS_WEIGHTS,
        "dimensions": dims,
        "measurements": m,
    }
