"""雨声循环素材：静音检测、首尾裁切、循环接缝评分。"""

from __future__ import annotations

import json
import subprocess
from pathlib import Path


def ffprobe_duration(path: Path) -> float:
    out = subprocess.check_output(
        [
            "ffprobe", "-v", "error",
            "-show_entries", "format=duration",
            "-of", "json", str(path),
        ],
        text=True,
    )
    data = json.loads(out)
    return float(data["format"]["duration"])


def trim_wav_fixed(
    src: Path,
    dst: Path,
    *,
    head_s: float = 1.0,
    tail_s: float = 1.0,
) -> float:
    """裁掉首尾固定时长，返回输出时长（秒）。"""
    dur = ffprobe_duration(src)
    body = dur - head_s - tail_s
    if body <= 0.5:
        raise ValueError(f"裁切后过短: {src.name} dur={dur:.2f}s head={head_s} tail={tail_s}")
    dst.parent.mkdir(parents=True, exist_ok=True)
    subprocess.run(
        [
            "ffmpeg", "-y", "-hide_banner", "-loglevel", "error",
            "-ss", str(head_s),
            "-i", str(src),
            "-t", str(body),
            "-c:a", "pcm_s24le",
            str(dst),
        ],
        check=True,
    )
    return ffprobe_duration(dst)


def _load_mono(path: Path, sr: int = 22050, max_s: float | None = None):
    import numpy as np
    import librosa

    y, _ = librosa.load(path, sr=sr, mono=True, duration=max_s, res_type="kaiser_fast")
    return y.astype(np.float64), sr


def detect_silence_bounds(
    path: Path,
    *,
    threshold_db: float = -42.0,
    min_run_ms: float = 20.0,
    pad_ms: float = 15.0,
) -> tuple[float, float]:
    """返回 (start_sec, end_sec) 有效音频区间（相对文件起点）。"""
    import numpy as np

    y, sr = _load_mono(path)
    if y.size == 0:
        return 0.0, 0.0

    frame = max(1, int(sr * 0.005))
    n_frames = max(1, len(y) // frame)
    rms = np.array(
        [np.sqrt(np.mean(y[i * frame : (i + 1) * frame] ** 2) + 1e-12) for i in range(n_frames)]
    )
    db = 20.0 * np.log10(rms + 1e-12)
    active = db > threshold_db

    min_run = max(1, int(min_run_ms / 1000.0 / (frame / sr)))
    start_i = 0
    for i in range(n_frames):
        if active[i : i + min_run].all():
            start_i = i
            break
    end_i = n_frames - 1
    for i in range(n_frames - 1, -1, -1):
        if i - min_run + 1 < 0:
            continue
        if active[i - min_run + 1 : i + 1].all():
            end_i = i
            break

    pad = pad_ms / 1000.0
    start_s = max(0.0, start_i * frame / sr - pad)
    end_s = min(len(y) / sr, (end_i + 1) * frame / sr + pad)
    return start_s, end_s


def trim_wav_auto(
    src: Path,
    dst: Path,
    *,
    threshold_db: float = -42.0,
    min_body_s: float = 8.0,
) -> dict:
    """按静音检测裁切；返回 {start, end, duration}。"""
    start_s, end_s = detect_silence_bounds(src, threshold_db=threshold_db)
    body = end_s - start_s
    if body < min_body_s:
        dur = ffprobe_duration(src)
        # 回退：固定去掉 0.5s 首尾
        start_s, end_s = 0.5, max(0.5, dur - 0.5)
        body = end_s - start_s
    dst.parent.mkdir(parents=True, exist_ok=True)
    subprocess.run(
        [
            "ffmpeg", "-y", "-hide_banner", "-loglevel", "error",
            "-ss", f"{start_s:.4f}",
            "-i", str(src),
            "-t", f"{body:.4f}",
            "-c:a", "pcm_s24le",
            str(dst),
        ],
        check=True,
    )
    out_dur = ffprobe_duration(dst)
    return {"start_s": start_s, "end_s": end_s, "duration_s": out_dur}


def loop_seam_score(path: Path, *, window_ms: float = 50.0) -> float:
    """首尾 RMS 差越小越好；返回 dB 差（0=完美）。"""
    import numpy as np

    y, sr = _load_mono(path)
    w = max(1, int(sr * window_ms / 1000.0))
    if len(y) < w * 2:
        return 99.0
    head_rms = float(np.sqrt(np.mean(y[:w] ** 2) + 1e-12))
    tail_rms = float(np.sqrt(np.mean(y[-w:] ** 2) + 1e-12))
    head_db = 20.0 * np.log10(head_rms + 1e-12)
    tail_db = 20.0 * np.log10(tail_rms + 1e-12)
    return abs(head_db - tail_db)


def _boundary_scores(
    y_segment,
    sr: int,
    *,
    window_ms: float = 50.0,
    mel_window_ms: float = 100.0,
    mel_n_mels: int = 32,
) -> tuple[float, float]:
    """返回 (seam_db, mel_diff)。"""
    import numpy as np
    import librosa

    w = max(1, int(sr * window_ms / 1000.0))
    if len(y_segment) < w * 2:
        return 99.0, 99.0

    head_rms = float(np.sqrt(np.mean(y_segment[:w] ** 2) + 1e-12))
    tail_rms = float(np.sqrt(np.mean(y_segment[-w:] ** 2) + 1e-12))
    seam_db = abs(
        20.0 * np.log10(head_rms + 1e-12) - 20.0 * np.log10(tail_rms + 1e-12)
    )

    mw = max(64, int(sr * mel_window_ms / 1000.0))
    head_m = y_segment[:mw]
    tail_m = y_segment[-mw:]
    n_fft = min(2048, len(head_m), len(tail_m))
    n_fft = max(64, 2 ** int(np.log2(n_fft)))
    hop = max(1, n_fft // 4)

    mel_h = librosa.feature.melspectrogram(
        y=head_m, sr=sr, n_fft=n_fft, hop_length=hop, n_mels=mel_n_mels
    )
    mel_t = librosa.feature.melspectrogram(
        y=tail_m, sr=sr, n_fft=n_fft, hop_length=hop, n_mels=mel_n_mels
    )
    mel_h = np.log1p(np.mean(mel_h, axis=1))
    mel_t = np.log1p(np.mean(mel_t, axis=1))
    mel_diff = float(np.sqrt(np.mean((mel_h - mel_t) ** 2)))
    return seam_db, mel_diff


def find_best_loop_window(
    path: Path,
    *,
    output_s: float = 30.0,
    margin_head: float = 1.0,
    margin_tail: float = 1.0,
    step_ms: float = 50.0,
    window_ms: float = 50.0,
    metric: str = "combined",
    sr: int = 22050,
) -> dict:
    """在源文件中滑动搜索 output_s 窗口，使首尾 seam / mel 最接近。"""
    y, sr = _load_mono(path, sr=sr)
    dur = len(y) / sr
    start_min = margin_head
    start_max = dur - output_s - margin_tail
    if start_max < start_min:
        raise ValueError(
            f"搜索区间无效: dur={dur:.2f}s output={output_s} "
            f"margin_head={margin_head} margin_tail={margin_tail}"
        )

    step = step_ms / 1000.0
    best: dict | None = None
    n_candidates = 0
    start_s = start_min
    while start_s <= start_max + 1e-9:
        i0 = int(round(start_s * sr))
        i1 = i0 + int(round(output_s * sr))
        seg = y[i0:i1]
        seam_db, mel_diff = _boundary_scores(seg, sr, window_ms=window_ms)
        if metric == "seam":
            cost = seam_db
        elif metric == "mel":
            cost = mel_diff
        else:
            cost = seam_db + mel_diff * 8.0
        rec = {
            "start_s": round(start_s, 4),
            "seam_db": round(seam_db, 4),
            "mel_diff": round(mel_diff, 6),
            "cost": round(cost, 6),
        }
        n_candidates += 1
        if best is None or cost < best["cost"]:
            best = rec
        start_s += step

    assert best is not None
    return {
        **best,
        "output_s": output_s,
        "search_range": [round(start_min, 4), round(start_max, 4)],
        "candidates": n_candidates,
        "metric": metric,
        "source_duration_s": round(dur, 4),
    }


def trim_wav_best_window(
    src: Path,
    dst: Path,
    *,
    output_s: float = 30.0,
    margin_head: float = 1.0,
    margin_tail: float = 1.0,
    step_ms: float = 50.0,
    window_ms: float = 50.0,
    metric: str = "combined",
) -> dict:
    """搜索最佳循环窗口并导出。"""
    info = find_best_loop_window(
        src,
        output_s=output_s,
        margin_head=margin_head,
        margin_tail=margin_tail,
        step_ms=step_ms,
        window_ms=window_ms,
        metric=metric,
    )
    dst.parent.mkdir(parents=True, exist_ok=True)
    subprocess.run(
        [
            "ffmpeg", "-y", "-hide_banner", "-loglevel", "error",
            "-ss", f"{info['start_s']:.4f}",
            "-i", str(src),
            "-t", f"{output_s:.4f}",
            "-c:a", "pcm_s24le",
            str(dst),
        ],
        check=True,
    )
    info["duration_s"] = ffprobe_duration(dst)
    return info
