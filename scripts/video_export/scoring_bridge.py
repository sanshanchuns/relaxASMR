#!/usr/bin/env python3
"""RS-PASS 打分桥接：Reaper Lua / 导出流水线 → 本仓库 benchmark/。"""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
BENCHMARK_DIR = REPO_ROOT / "benchmark"
SCORE_PY = BENCHMARK_DIR / "score.py"


def run_scoring(
    media: Path,
    *,
    out_dir: Path,
    duration: float = 300.0,
    report_stem: str = "benchmark",
    rpp: Path | None = None,
    mode: str | None = None,
    summary_file: Path | None = None,
) -> dict | None:
    """对单个媒体文件跑 RS-PASS，写入 out_dir/{report_stem}.md|.json。"""
    if not SCORE_PY.is_file():
        print(f"Warning: {SCORE_PY} not found, skip scoring", file=sys.stderr)
        return None

    media = media.resolve()
    out_dir = out_dir.resolve()
    out_dir.mkdir(parents=True, exist_ok=True)

    cmd = [
        sys.executable,
        str(SCORE_PY),
        str(media),
        "--duration",
        str(duration),
        "--output-dir",
        str(out_dir),
        "--report-stem",
        report_stem,
    ]
    if rpp is not None:
        cmd.extend(["--rpp", str(rpp.resolve())])
    if mode is not None:
        cmd.extend(["--mode", mode])
    if summary_file is not None:
        cmd.extend(["--summary-file", str(summary_file.resolve())])

    print(f"==> RS-PASS scoring (benchmark/, first {duration:.0f}s) ...")
    proc = subprocess.run(
        cmd,
        cwd=str(BENCHMARK_DIR),
        capture_output=True,
        text=True,
        encoding="utf-8",
    )
    if proc.stdout:
        print(proc.stdout.rstrip())
    if proc.returncode != 0:
        print(proc.stderr or "scoring failed", file=sys.stderr)
        return None

    json_path = out_dir / f"{report_stem}.json"
    if json_path.is_file():
        return json.loads(json_path.read_text(encoding="utf-8"))
    return None


def main() -> None:
    import argparse

    ap = argparse.ArgumentParser(description="Call relaxASMR benchmark/score.py")
    ap.add_argument("media", type=Path, help="mp4 / wav 等成品")
    ap.add_argument("--output-dir", type=Path, required=True)
    ap.add_argument("--duration", type=float, default=300.0)
    ap.add_argument("--report-stem", default="benchmark")
    ap.add_argument("--rpp", type=Path, default=None)
    ap.add_argument("--mode", choices=("sleep", "focus"), default=None)
    ap.add_argument("--summary-file", type=Path, default=None)
    args = ap.parse_args()

    result = run_scoring(
        args.media,
        out_dir=args.output_dir,
        duration=args.duration,
        report_stem=args.report_stem,
        rpp=args.rpp,
        mode=args.mode,
        summary_file=args.summary_file,
    )
    sys.exit(0 if result else 1)


if __name__ == "__main__":
    main()
