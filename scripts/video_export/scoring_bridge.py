#!/usr/bin/env python3
"""调用 sibling 工程 youtube_analysis 的 RS-PASS 打分（见 ../youtube_analysis/README.md）。"""

from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_YOUTUBE_ANALYSIS = REPO_ROOT.parent / "youtube_analysis"


def resolve_youtube_analysis_root() -> Path | None:
    env = os.environ.get("YOUTUBE_ANALYSIS_ROOT", "").strip()
    if env:
        root = Path(env).expanduser().resolve()
        return root if (root / "scoring").is_dir() else None
    root = DEFAULT_YOUTUBE_ANALYSIS.resolve()
    return root if (root / "scoring").is_dir() else None


def run_scoring(
    media: Path,
    *,
    out_dir: Path,
    duration: float = 300.0,
    report_stem: str = "benchmark",
    rpp: Path | None = None,
    mode: str | None = None,
) -> dict | None:
    """对单个媒体文件跑 RS-PASS，写入 out_dir/{report_stem}.md|.json。"""
    root = resolve_youtube_analysis_root()
    if root is None:
        hint = DEFAULT_YOUTUBE_ANALYSIS
        print(
            f"Warning: youtube_analysis not found at {hint} "
            f"(or set YOUTUBE_ANALYSIS_ROOT), skip scoring",
            file=sys.stderr,
        )
        return None

    media = media.resolve()
    out_dir = out_dir.resolve()
    out_dir.mkdir(parents=True, exist_ok=True)

    cmd = [
        sys.executable,
        "-m",
        "scoring",
        str(media),
        "--task",
        "file",
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

    print(f"==> RS-PASS scoring (youtube_analysis, first {duration:.0f}s) ...")
    proc = subprocess.run(
        cmd,
        cwd=str(root),
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

    ap = argparse.ArgumentParser(description="Call youtube_analysis RS-PASS scoring")
    ap.add_argument("media", type=Path, help="mp4 / wav 等成品")
    ap.add_argument("--output-dir", type=Path, required=True)
    ap.add_argument("--duration", type=float, default=300.0)
    ap.add_argument("--report-stem", default="benchmark")
    ap.add_argument("--rpp", type=Path, default=None)
    ap.add_argument("--mode", choices=("sleep", "focus"), default=None)
    args = ap.parse_args()

    result = run_scoring(
        args.media,
        out_dir=args.output_dir,
        duration=args.duration,
        report_stem=args.report_stem,
        rpp=args.rpp,
        mode=args.mode,
    )
    sys.exit(0 if result else 1)


if __name__ == "__main__":
    main()
