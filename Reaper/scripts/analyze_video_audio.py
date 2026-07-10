#!/usr/bin/env python3
"""分析视频嵌入式音轨，按 rain 四层输出 Markdown（写入 video_analysis.md）。"""

from __future__ import annotations

import argparse
import math
import re
import struct
import subprocess
import tempfile
import wave
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]

LAYER_ROWS = [
    ("1_rain", "雨层", "500 Hz–6 kHz 连续能量 · 雨势主体"),
    ("2_impact", "击打", "2–8 kHz 瞬态峰 · 雨滴撞击"),
    ("3_random", "随机", "稀疏变化 · 风/远处声响"),
    ("4_wildlife", "生物", "1–6 kHz 稀疏瞬态 · 鸟鸣等"),
]


def extract_audio(video: Path, wav_out: Path) -> None:
    subprocess.run(
        [
            "ffmpeg",
            "-y",
            "-i",
            str(video),
            "-vn",
            "-ac",
            "1",
            "-ar",
            "44100",
            str(wav_out),
        ],
        check=True,
        capture_output=True,
    )


def load_samples(wav_path: Path) -> tuple[list[float], int]:
    with wave.open(str(wav_path)) as w:
        n = w.getnframes()
        sr = w.getframerate()
        raw = w.readframes(n)
    samples = struct.unpack(f"<{len(raw) // 2}h", raw)
    return [s / 32768.0 for s in samples], sr


def analyze_wav(samples: list[float], sr: int) -> dict:
    import numpy as np

    x = np.array(samples, dtype=np.float64)
    rms = float(np.sqrt(np.mean(x * x)))
    rms_db = 20 * math.log10(rms) if rms > 0 else -120.0
    peak = float(np.max(np.abs(x))) if len(x) else 0.0
    peak_db = 20 * math.log10(peak) if peak > 0 else -120.0

    fft = np.abs(np.fft.rfft(x))
    freqs = np.fft.rfftfreq(len(x), 1 / sr)

    def band_energy(lo: float, hi: float) -> float:
        mask = (freqs >= lo) & (freqs < hi)
        return float(np.sum(fft[mask] ** 2))

    bands = {
        "sub_low": band_energy(20, 200),
        "low_mid": band_energy(200, 500),
        "mid": band_energy(500, 2000),
        "high_mid": band_energy(2000, 6000),
        "high": band_energy(6000, min(12000, sr / 2)),
    }
    total = sum(bands.values()) or 1.0
    band_pct = {k: round(100 * v / total, 1) for k, v in bands.items()}

    env = np.abs(x)
    thr = np.percentile(env, 92)
    peak_idx = np.where(env > thr)[0]
    transient_groups = 0
    if len(peak_idx) > 0:
        gaps = np.diff(peak_idx)
        transient_groups = int(1 + np.sum(gaps > sr * 0.08))

    return {
        "duration": len(x) / sr,
        "rms_db": round(rms_db, 1),
        "peak_db": round(peak_db, 1),
        "band_pct": band_pct,
        "transient_groups": transient_groups,
    }


def layer_scores(stats: dict) -> dict[str, dict]:
    b = stats["band_pct"]
    tr = stats["transient_groups"]
    dur = stats["duration"]

    def level(score: float) -> str:
        if score >= 0.45:
            return "强"
        if score >= 0.25:
            return "中"
        if score >= 0.12:
            return "弱"
        return "无/极弱"

    scores = {
        "1_rain": 0.55 * b["mid"] / 100 + 0.35 * b["high_mid"] / 100 + 0.1 * b["high"] / 100,
        "2_impact": min(1.0, tr / max(dur * 2, 0.5)) * 0.5 + 0.3 * b["high_mid"] / 100,
        "3_random": min(1.0, (b["sub_low"] + b["low_mid"] + b["mid"]) / 100) * 0.5 + 0.2 * b["high"] / 100,
        "4_wildlife": min(1.0, tr / max(dur * 4, 1)) * 0.4 + 0.15 * b["high_mid"] / 100,
    }

    out = {}
    for lid, _name, hint in LAYER_ROWS:
        s = min(1.0, scores[lid])
        out[lid] = {"score": s, "level": level(s), "hint": hint}
    return out


def build_markdown(video: Path, stats: dict, layers: dict[str, dict]) -> str:
    b = stats["band_pct"]
    lines = [
        "# 二、视频原声拆解",
        "",
        "> 嵌入式音轨自动分析（FFT 频段 + 瞬态计数）。Looper 循环段整体代表全片听感。",
        f"> 源文件：`{video.as_posix()}`",
        "",
        "## 2.1 音轨技术摘要",
        "",
        "| 项 | 值 |",
        "|----|-----|",
        f"| 音轨时长 | {stats['duration']:.2f} s |",
        f"| RMS | {stats['rms_db']} dB |",
        f"| 峰值 | {stats['peak_db']} dB |",
        f"| 瞬态群（粗估） | {stats['transient_groups']} |",
        "",
        "## 2.2 频段能量分布",
        "",
        "| 频段 | 范围 | 占比 | 可能对应 |",
        "|------|------|------|----------|",
        f"| sub_low | 20–200 Hz | {b['sub_low']}% | 底噪 / 远雷 / 湖面低频 |",
        f"| low_mid | 200–500 Hz | {b['low_mid']}% | 水体 / 环境厚度 |",
        f"| mid | 500 Hz–2 kHz | {b['mid']}% | **雨层主体** |",
        f"| high_mid | 2–6 kHz | {b['high_mid']}% | 雨丝 / 击打 |",
        f"| high | 6 kHz+ | {b['high']}% | 细小雨滴 / 空气 |",
        "",
        "## 2.3 四层听感（原声客观拆解）",
        "",
        "| 层 | 原声强弱 | 听感线索 |",
        "|----|----------|----------|",
    ]
    for lid, name, hint in LAYER_ROWS:
        lv = layers[lid]
        lines.append(f"| {lid} {name} | **{lv['level']}** | {hint} |")
    lines.append("")
    lines.append(
        "本节仅描述 **视频内嵌音轨** 的客观听感，最终混音配方见 **§三**（可在原声基础上创新，但须符合画面逻辑）。"
    )
    lines.append("")
    return "\n".join(lines)


def merge_into_video_analysis(doc_path: Path, section_md: str) -> None:
    text = doc_path.read_text(encoding="utf-8")
    if "# 二、视频原声拆解" in text:
        text = re.sub(
            r"# 二、视频原声拆解.*?(?=\n---\n\n# 三、|\n# 三、)",
            section_md.rstrip() + "\n",
            text,
            count=1,
            flags=re.DOTALL,
        )
    elif "## 4. 视频原声" in text:
        text = re.sub(
            r"## 4\. 视频原声.*?(?=\n---\n\n## |\n## [5-9]\.)",
            section_md.rstrip() + "\n",
            text,
            count=1,
            flags=re.DOTALL,
        )
    doc_path.write_text(text, encoding="utf-8")


def main() -> None:
    parser = argparse.ArgumentParser(description="Analyze embedded video audio → 7-layer markdown")
    parser.add_argument("--video", type=Path, help="path to mp4")
    parser.add_argument("--scene", type=str, help="Rain subproject id (reads asmr_config video path)")
    parser.add_argument("--repo", type=Path, default=REPO_ROOT)
    parser.add_argument("--update-doc", action="store_true", help="merge into baseURL/material/<scene>_video_analysis.md")
    args = parser.parse_args()

    if args.scene:
        from asmr_config_parser import load_asmr_config

        import sys
        if str(args.repo) not in sys.path:
            sys.path.insert(0, str(args.repo))
        from scripts.paths import get_scene_config_path, material_dir, resolve_scene_config_path

        cfg_path = resolve_scene_config_path(args.scene) or get_scene_config_path(args.scene)
        cfg = load_asmr_config(cfg_path)
        video = Path(cfg["video"]["path"])
        if not video.is_file():
            video = args.repo / cfg["video"]["path"]
        doc_path = material_dir() / f"{args.scene}_video_analysis.md"
    elif args.video:
        video = args.video
        doc_path = None
    else:
        parser.error("need --video or --scene")

    if not video.is_file():
        raise SystemExit(f"视频不存在: {video}")

    with tempfile.TemporaryDirectory() as tmp:
        wav = Path(tmp) / "audio.wav"
        extract_audio(video, wav)
        samples, sr = load_samples(wav)
        stats = analyze_wav(samples, sr)
        layers = layer_scores(stats)
        section = build_markdown(video, stats, layers)

    print(section)
    if args.update_doc and doc_path:
        merge_into_video_analysis(doc_path, section)
        print(f"Updated {doc_path}")


if __name__ == "__main__":
    main()
