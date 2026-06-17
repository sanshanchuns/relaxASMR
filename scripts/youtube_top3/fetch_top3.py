#!/usr/bin/env python3
"""按主题系列抓取 YouTube 近 N 天 3万+ 播放 Top3，并下载前 300s 片段。"""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

SCRIPT_DIR = Path(__file__).resolve().parent
SERIES_PATH = SCRIPT_DIR / "series.json"
OUTPUT_ROOT = SCRIPT_DIR / "output"


def load_series_config() -> dict:
    data = json.loads(SERIES_PATH.read_text(encoding="utf-8"))
    defaults = data.get("defaults", {})
    return {"defaults": defaults, "series": data.get("series", {})}


def cutoff_date(days: int) -> str:
    d = datetime.now(timezone.utc) - timedelta(days=days)
    return d.strftime("%Y%m%d")


def run_yt_dlp_search(query: str, limit: int) -> list[dict]:
    cmd = [
        "yt-dlp",
        "-j",
        "--no-warnings",
        "--no-playlist",
        f"--playlist-end={limit}",
        f"ytsearch{limit}:{query}",
    ]
    proc = subprocess.run(cmd, capture_output=True, text=True)
    if proc.returncode not in (0, 101) and not proc.stdout.strip():
        raise RuntimeError(f"yt-dlp search failed: {proc.stderr.strip() or proc.returncode}")

    entries: list[dict] = []
    for line in proc.stdout.splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            entries.append(json.loads(line))
        except json.JSONDecodeError:
            continue
    return entries


def parse_video(entry: dict) -> dict | None:
    vid = entry.get("id")
    upload_date = entry.get("upload_date")
    view_count = entry.get("view_count")
    if not vid or not upload_date or view_count is None:
        return None
    return {
        "id": vid,
        "title": entry.get("title", ""),
        "url": f"https://www.youtube.com/watch?v={vid}",
        "view_count": int(view_count),
        "upload_date": str(upload_date),
        "duration": entry.get("duration"),
        "channel": entry.get("channel") or entry.get("uploader") or "",
        "channel_url": entry.get("channel_url") or entry.get("uploader_url") or "",
    }


def collect_top_videos(
    queries: list[str],
    *,
    days: int,
    min_views: int,
    top_n: int,
    search_limit: int,
) -> list[dict]:
    cutoff = cutoff_date(days)
    pool: dict[str, dict] = {}

    for query in queries:
        print(f"  搜索: {query}")
        try:
            entries = run_yt_dlp_search(query, search_limit)
        except RuntimeError as exc:
            print(f"    ⚠ {exc}", file=sys.stderr)
            continue
        for entry in entries:
            video = parse_video(entry)
            if not video:
                continue
            if video["upload_date"] < cutoff:
                continue
            if video["view_count"] < min_views:
                continue
            vid = video["id"]
            if vid not in pool or video["view_count"] > pool[vid]["view_count"]:
                pool[vid] = video

    ranked = sorted(pool.values(), key=lambda v: v["view_count"], reverse=True)
    return ranked[:top_n]


def download_clip(
    url: str,
    out_path: Path,
    *,
    seconds: int,
    max_height: int,
) -> None:
    out_path.parent.mkdir(parents=True, exist_ok=True)
    fmt = f"bv*[height<={max_height}]+ba/b[height<={max_height}]/b"
    cmd = [
        "yt-dlp",
        "--no-warnings",
        "--download-sections",
        f"*0-{seconds}",
        "-f",
        fmt,
        "--merge-output-format",
        "mp4",
        "-o",
        str(out_path),
        url,
    ]
    subprocess.run(cmd, check=True)


def format_upload_date(yyyymmdd: str) -> str:
    return f"{yyyymmdd[:4]}-{yyyymmdd[4:6]}-{yyyymmdd[6:8]}"


def render_report(
    series_id: str,
    series_name: str,
    params: dict,
    videos: list[dict],
    clips: list[dict],
    run_id: str,
) -> str:
    lines = [
        f"# YouTube Top3 · {series_name} (`{series_id}`)",
        "",
        f"抓取时间：{run_id}",
        "",
        "## 筛选条件",
        "",
        f"| 项 | 值 |",
        f"|----|-----|",
        f"| 发布窗口 | 近 **{params['days']}** 天 |",
        f"| 最低播放 | **{params['min_views']:,}** |",
        f"| Top N | **{params['top_n']}** |",
        f"| 片段时长 | 前 **{params['clip_seconds']}s** |",
        "",
        "## Top 视频",
        "",
    ]

    if not videos:
        lines.append("（未找到符合条件的视频，可放宽 `min_views` 或增加 `queries`）")
        lines.append("")
        return "\n".join(lines)

    for i, v in enumerate(videos, 1):
        lines.extend([
            f"### #{i} · {v['title']}",
            "",
            f"- 播放：**{v['view_count']:,}**",
            f"- 发布：{format_upload_date(v['upload_date'])}",
            f"- 频道：{v['channel']}",
            f"- 链接：{v['url']}",
            "",
        ])

    if clips:
        lines.extend(["## 本地片段", ""])
        for c in clips:
            lines.append(f"- `{c['file']}` ← {c['url']}")
        lines.append("")

    lines.extend([
        "## 说明",
        "",
        "- 近 30 天播放以 **发布日在窗口内** 的视频总播放量近似（YouTube 公开 API 无「30 日增量」字段）。",
        "- 分析响度 / 结构时请用 `clips/` 下 mp4。",
        "",
    ])
    return "\n".join(lines)


def process_series(
    series_id: str,
    spec: dict,
    defaults: dict,
    *,
    dry_run: bool,
    skip_download: bool,
) -> Path:
    params = {**defaults, **{k: v for k, v in spec.items() if k != "queries" and k != "name"}}
    queries = spec.get("queries", [])
    name = spec.get("name", series_id)

    days = int(params["days"])
    min_views = int(params["min_views"])
    top_n = int(params["top_n"])
    clip_seconds = int(params["clip_seconds"])
    search_limit = int(params["search_limit"])
    max_height = int(params.get("max_height", 720))

    run_id = datetime.now().strftime("%Y-%m-%d %H:%M")
    out_dir = OUTPUT_ROOT / series_id / datetime.now().strftime("%Y%m%d_%H%M%S")
    clips_dir = out_dir / "clips"

    print(f"\n==> 系列: {name} ({series_id})")
    print(f"    条件: {days}天内 · ≥{min_views:,} 播放 · Top{top_n}")

    top_videos = collect_top_videos(
        queries,
        days=days,
        min_views=min_views,
        top_n=top_n,
        search_limit=search_limit,
    )
    print(f"    命中: {len(top_videos)} 条")

    clips_meta: list[dict] = []
    out_dir.mkdir(parents=True, exist_ok=True)

    if not dry_run and not skip_download:
        for i, v in enumerate(top_videos, 1):
            fname = f"{i:02d}_{v['id']}_{clip_seconds}s.mp4"
            out_path = clips_dir / fname
            print(f"    下载片段 [{i}/{len(top_videos)}]: {v['title'][:50]}...")
            try:
                download_clip(
                    v["url"],
                    out_path,
                    seconds=clip_seconds,
                    max_height=max_height,
                )
                clips_meta.append({"file": f"clips/{fname}", "url": v["url"], "id": v["id"]})
            except subprocess.CalledProcessError as exc:
                print(f"    ✗ 下载失败 {v['id']}: {exc}", file=sys.stderr)

    manifest = {
        "series_id": series_id,
        "series_name": name,
        "run_at": run_id,
        "params": {
            "days": days,
            "min_views": min_views,
            "top_n": top_n,
            "clip_seconds": clip_seconds,
            "search_limit": search_limit,
            "max_height": max_height,
        },
        "queries": queries,
        "videos": top_videos,
        "clips": clips_meta,
    }
    (out_dir / "manifest.json").write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    (out_dir / "report.md").write_text(
        render_report(series_id, name, params, top_videos, clips_meta, run_id),
        encoding="utf-8",
    )

    print(f"    输出: {out_dir}/")
    return out_dir


def main() -> None:
    parser = argparse.ArgumentParser(
        description="按主题系列抓取 YouTube Top3（30天·3万+）并下载前300s",
    )
    parser.add_argument(
        "--series",
        action="append",
        help="系列 ID（可多次指定；默认 --all）",
    )
    parser.add_argument("--all", action="store_true", help="处理 series.json 中全部系列")
    parser.add_argument("--dry-run", action="store_true", help="只搜索排序，不下载片段")
    parser.add_argument("--skip-download", action="store_true", help="只写 manifest/report")
    parser.add_argument("--list", action="store_true", help="列出可用系列")
    args = parser.parse_args()

    if not SERIES_PATH.is_file():
        print(f"Error: 找不到配置 {SERIES_PATH}", file=sys.stderr)
        sys.exit(1)

    cfg = load_series_config()
    all_series: dict = cfg["series"]
    defaults = cfg["defaults"]

    if args.list:
        for sid, spec in all_series.items():
            print(f"  {sid}: {spec.get('name', sid)}")
        return

    if args.all or not args.series:
        targets = list(all_series.keys())
    else:
        targets = args.series
        unknown = [s for s in targets if s not in all_series]
        if unknown:
            print(f"Error: 未知系列: {', '.join(unknown)}", file=sys.stderr)
            print("可用:", ", ".join(all_series.keys()), file=sys.stderr)
            sys.exit(1)

    print("YouTube Top3 抓取")
    print(f"配置: {SERIES_PATH}")

    for sid in targets:
        process_series(
            sid,
            all_series[sid],
            defaults,
            dry_run=args.dry_run,
            skip_download=args.skip_download,
        )

    print("\n完成。")


if __name__ == "__main__":
    main()
