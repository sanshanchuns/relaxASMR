#!/usr/bin/env python3
"""RS-PASS 雨声舒缓安逸度 benchmark（benchmark/theory.md §四）。

对渲染成品 mp4 / wav 分析前 N 秒（默认 300s），七项心理声学代理指标：

  N_5   动态峰值响度   25%  助眠 ≤3 Sone / 专注 ≤8 Sone
  S_50  尖锐度         20%  ≤1.1 Acum
  R_5   粗糙度         15%  ≤0.08 Asper
  IACC  双耳互相关     15%  ≤0.3（越低包裹感越强）
  F_50  波动强度       10%  0.05–0.15 Vacil
  SI    光谱不规则度   10%  中高水平
  T_max 纯音色调度     5%   ≤0.02

用法：
  python3 benchmark/score.py path/to/render.mp4
  python3 benchmark/score.py path/to/mix.wav --mode focus --json
  python3 benchmark/score.py path/to/render.mp4 --output-dir material/out/
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from rs_pass import (
    DEFAULT_DURATION,
    RS_PASS_WEIGHTS,
    rs_pass_grade,
    score_rs_pass,
)

REPO_ROOT = Path(__file__).resolve().parents[1]

DIM_LABELS = {
    "n5_peak_loudness": "动态峰值响度 N_5",
    "s50_sharpness": "尖锐度 S_50",
    "r5_roughness": "粗糙度 R_5",
    "iacc": "双耳互相关 IACC",
    "f50_fluctuation": "波动强度 F_50",
    "si_irregularity": "光谱不规则度 SI",
    "tmax_tonality": "纯音色调度 T_max",
    "crest_headroom": "峰均差 Crest（稀疏尖峰）",
}


def render_markdown(result: dict) -> str:
    d = result["dimensions"]
    lines = [
        f"# RS-PASS Benchmark · {Path(result['file']).name}",
        "",
        "> 依据 `benchmark/theory.md` §四 RS-PASS · "
        f"模式 **{result['mode']}** · 前 **{result['duration_s']:.0f} s**",
        "",
        f"**总分 {result['total_score']:.1f} / 100** · **{result['grade']}**",
        "",
        "| 指标 | 得分 / 100 | 权重 |",
        "|------|------------|------|",
    ]
    for key, w in RS_PASS_WEIGHTS.items():
        lines.append(
            f"| {DIM_LABELS[key]} | **{d[key]['score']:.1f}** | {int(w * 100)}% |"
        )
    lines += ["", "## 指标详情", ""]
    for key in RS_PASS_WEIGHTS:
        lines.append(f"### {DIM_LABELS[key]}")
        for k, v in d[key].items():
            if k != "score":
                lines.append(f"- {k}: {v}")
        lines.append("")
    m = result["measurements"]
    lines += [
        "## 原始测量（代理量，非实验室级）",
        "",
        f"- N_5 响度估计: {m['n5_sone_est']} Sone (P95 {m['n5_p95_dbfs']} dBFS)",
        f"- S_50: {m['s50_acum_est']} Acum(est)",
        f"- R_5: {m['r5_asper_est']} Asper(est)",
        f"- IACC: {m['iacc']}",
        f"- F_50: {m['f50_vacil_est']} Vacil(est)",
        f"- SI: {m['si']}",
        f"- T_max: {m['tmax']}",
        f"- RMS / Peak / Crest: {m['rms_dbfs']} / {m['peak_dbfs']} / "
        f"{round(m['peak_dbfs'] - m['rms_dbfs'], 2)} dB",
        "",
        "## 等级（甜区校准 · 代理量）",
        "",
        "> 旧版「不超标即满分」已改为 **ideal 甜区** 打分；88+ 应少见。",
        "",
        "| 总分 | 等级 | 含义 |",
        "|------|------|------|",
        "| ≥88 | 极品 | 各维接近甜区中心 |",
        "| 81–87 | 优秀 | 明显好于平均 |",
        "| 62–80 | 普通 | 合格日常雨片 |",
        "| <62 | 劣质 | 需返工 |",
    ]
    return "\n".join(lines)


def write_results(
    result: dict,
    out_dir: Path,
    report_stem: str = "benchmark",
) -> tuple[Path, Path]:
    out_dir.mkdir(parents=True, exist_ok=True)
    md_path = out_dir / f"{report_stem}.md"
    json_path = out_dir / f"{report_stem}.json"
    md_path.write_text(render_markdown(result), encoding="utf-8")
    json_path.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    return md_path, json_path


def run_benchmark(
    path: Path,
    duration: float = DEFAULT_DURATION,
    out_dir: Path | None = None,
    report_stem: str = "benchmark",
    mode: str = "sleep",
) -> dict:
    result = score_rs_pass(path.resolve(), duration=duration, mode=mode)
    if out_dir is not None:
        write_results(result, out_dir, report_stem=report_stem)
    return result


def main() -> None:
    ap = argparse.ArgumentParser(description="RS-PASS 雨声舒缓安逸度 benchmark")
    ap.add_argument("input", type=Path, help="mp4 / wav / ffmpeg 可读音频")
    ap.add_argument(
        "--duration",
        type=float,
        default=DEFAULT_DURATION,
        help=f"分析时长（秒），默认 {int(DEFAULT_DURATION)}",
    )
    ap.add_argument(
        "--mode",
        choices=("sleep", "focus"),
        default="sleep",
        help="N_5 目标域：sleep≤3 Sone / focus≤8 Sone",
    )
    ap.add_argument("--json", action="store_true", help="JSON 输出到 stdout")
    ap.add_argument("--markdown", action="store_true", help="Markdown 输出到 stdout")
    ap.add_argument("--output-dir", type=Path, help="写入 benchmark.md / benchmark.json")
    ap.add_argument(
        "--report-stem",
        default="benchmark",
        help="报告文件名前缀",
    )
    args = ap.parse_args()

    path = args.input.resolve()
    if not path.is_file():
        ap.error(f"文件不存在: {path}")

    result = run_benchmark(
        path,
        duration=args.duration,
        out_dir=args.output_dir,
        report_stem=args.report_stem,
        mode=args.mode,
    )

    if args.output_dir:
        json_path = args.output_dir / f"{args.report_stem}.json"
        print(
            f"==> RS-PASS: {result['total_score']:.1f} / 100 "
            f"({result['grade']}, 前 {result['duration_s']:.0f}s) → {json_path}"
        )

    if args.json:
        print(json.dumps(result, ensure_ascii=False, indent=2))
    elif args.markdown or not args.output_dir:
        print(render_markdown(result))


if __name__ == "__main__":
    main()
