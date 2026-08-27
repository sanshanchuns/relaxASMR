"""YouTube 爆款基准：前 5 分钟下载、抽帧 VLM 分析、版本化磁盘缓存。"""

from __future__ import annotations

import json
import re
import shutil
import subprocess
import tempfile
from collections.abc import Callable, Sequence
from pathlib import Path

from gui.youtube_api import VideoInfo
from gui.youtube_cache import CACHE_ROOT
from scripts.aigc_lab.youtube_competitor_pool import (
    fetch_competitor_pool,
    keywords_for_series_goal,
    select_benchmark_candidates,
    series_goal_label,
)

LogFn = Callable[[str], None]

RUBRIC_VERSION = "benchmark_v1"
_BENCHMARK_DIR = CACHE_ROOT / "benchmark"
_DOWNLOAD_SECONDS = 300
_FRAME_COUNT = 8
_JSON_BLOCK = re.compile(r"\{.*\}", re.DOTALL)
_MODEL = "gemini-3.7-flash"

_BENCHMARK_SYSTEM = """你是 YouTube 下雨 ASMR 横屏长视频分析师。根据视频抽帧，输出结构化基准 JSON（不要 markdown 围栏）：
{
  "video_id":"",
  "title_hint":"",
  "scene":"场景简述",
  "composition":"构图与景别",
  "rain_realism":0-100,
  "rain_layers":"前中后景雨层次描述",
  "fixed_camera":true,
  "goal_fit":{"sleep":0-100,"focus":0-100,"meditation":0-100},
  "reusable_strengths":["可复用优点"],
  "risks":["风险/扣分点"],
  "notes":["其它观察"]
}
评分要贴近真实挂片体验：雨感、层次、固定镜头、画面干净、适合长时间收听。"""


def benchmark_cache_path(video_id: str) -> Path:
    digest = f"{video_id}__{RUBRIC_VERSION}"
    safe = re.sub(r"[^\w.-]+", "_", digest)
    _BENCHMARK_DIR.mkdir(parents=True, exist_ok=True)
    return _BENCHMARK_DIR / f"{safe}.json"


def load_benchmark_cache(video_id: str) -> dict | None:
    path = benchmark_cache_path(video_id)
    if not path.is_file():
        return None
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None
    return data if isinstance(data, dict) else None


def save_benchmark_cache(video_id: str, data: dict) -> Path:
    path = benchmark_cache_path(video_id)
    payload = dict(data)
    payload["video_id"] = video_id
    payload["rubric_version"] = RUBRIC_VERSION
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return path


def _ffprobe_landscape(video: Path) -> bool:
    try:
        proc = subprocess.run(
            [
                "ffprobe",
                "-v",
                "error",
                "-select_streams",
                "v:0",
                "-show_entries",
                "stream=width,height",
                "-of",
                "json",
                str(video),
            ],
            capture_output=True,
            text=True,
            check=False,
        )
        if proc.returncode != 0:
            return False
        data = json.loads(proc.stdout or "{}")
        streams = data.get("streams") or []
        if not streams:
            return False
        w = int(streams[0].get("width") or 0)
        h = int(streams[0].get("height") or 0)
        return w > h > 0
    except (OSError, json.JSONDecodeError, ValueError, TypeError):
        return False


def _download_first_segment(url: str, out_path: Path, *, seconds: int = _DOWNLOAD_SECONDS) -> None:
    exe = shutil.which("yt-dlp")
    if not exe:
        raise RuntimeError("未找到 yt-dlp，无法下载 YouTube 基准片段")
    section = f"*0-{seconds}"
    cmd = [
        exe,
        "-f",
        "best[height<=720]/best",
        "--download-sections",
        section,
        "--force-overwrites",
        "-o",
        str(out_path),
        url,
    ]
    proc = subprocess.run(cmd, capture_output=True, text=True, check=False)
    if proc.returncode != 0 or not out_path.is_file():
        err = (proc.stderr or proc.stdout or "").strip()[:400]
        raise RuntimeError(f"yt-dlp 下载失败：{err or '无输出文件'}")


def _extract_spread_frames(video: Path, out_dir: Path, *, count: int = _FRAME_COUNT) -> list[Path]:
    from scripts.aigc_lab.video_probe import extract_review_frames

    return extract_review_frames(video, out_dir, count=count)


def _call_gemini_benchmark(
    video: VideoInfo,
    frames: Sequence[Path],
    *,
    series_goal: str,
    log_fn: LogFn | None = None,
) -> tuple[dict, str]:
    from scripts.config.paths import ensure_cli_path

    ensure_cli_path()
    from agy import generate_text_via_agy_accounts, has_agy_credentials
    from agy.client import AGY_IMAGE_LABELS

    if not has_agy_credentials():
        raise RuntimeError("未配置 agy 凭据，无法 VLM 基准分析")

    images: list[tuple[str, bytes]] = []
    for fp in frames:
        p = Path(fp)
        if p.is_file():
            mime = "image/png" if p.suffix.lower() == ".png" else "image/jpeg"
            images.append((mime, p.read_bytes()))

    goal = series_goal_label(series_goal)
    user = (
        f"目标系列：{goal}（{series_goal}）\n"
        f"YouTube 视频：{video.title}\n"
        f"URL：{video.watch_url}\n"
        f"附 {len(images)} 张均匀抽帧，请输出基准 JSON。"
    )
    text, email = generate_text_via_agy_accounts(
        user,
        model=_MODEL,
        effort="medium",
        system=_BENCHMARK_SYSTEM,
        images=images or None,
        log_fn=log_fn,
        account_labels=AGY_IMAGE_LABELS,
    )
    return _parse_benchmark_json(text, video_id=video.id), email


def _parse_benchmark_json(text: str, *, video_id: str) -> dict:
    raw = (text or "").strip()
    m = _JSON_BLOCK.search(raw)
    blob = m.group(0) if m else raw
    try:
        data = json.loads(blob)
    except json.JSONDecodeError:
        return {
            "video_id": video_id,
            "parse_error": raw[:500],
            "scene": "",
            "composition": "",
            "rain_realism": 0,
            "rain_layers": "",
            "fixed_camera": False,
            "goal_fit": {},
            "reusable_strengths": [],
            "risks": ["JSON 解析失败"],
            "notes": [],
        }
    if not isinstance(data, dict):
        return {"video_id": video_id, "parse_error": "非对象 JSON"}
    data.setdefault("video_id", video_id)
    return data


def analyze_benchmark_video(
    video: VideoInfo,
    *,
    series_goal: str,
    log_fn: LogFn | None = None,
) -> dict:
    """单条视频：缓存命中则直接返回；否则下载前 5 分钟并 VLM 分析。"""
    log = log_fn or (lambda _m: None)
    cached = load_benchmark_cache(video.id)
    if cached and cached.get("rubric_version") == RUBRIC_VERSION and not cached.get("failed"):
        log(f"[基准] 缓存命中 · {video.id} · {video.title[:40]}")
        out = dict(cached)
        out["cache_hit"] = True
        return out

    log(f"[基准] 下载前 {_DOWNLOAD_SECONDS}s · {video.title[:50]}…")
    with tempfile.TemporaryDirectory(prefix="yt_bench_") as tmp:
        tmp_path = Path(tmp)
        video_file = tmp_path / f"{video.id}.mp4"
        try:
            _download_first_segment(video.watch_url, video_file)
        except Exception as exc:  # noqa: BLE001
            fail = {
                "video_id": video.id,
                "title": video.title,
                "watch_url": video.watch_url,
                "failed": True,
                "failure_reason": str(exc),
                "rubric_version": RUBRIC_VERSION,
            }
            save_benchmark_cache(video.id, fail)
            log(f"[基准] 下载失败 · {video.id}：{exc}")
            return fail

        if not _ffprobe_landscape(video_file):
            fail = {
                "video_id": video.id,
                "title": video.title,
                "watch_url": video.watch_url,
                "failed": True,
                "failure_reason": "非横屏长视频",
                "rubric_version": RUBRIC_VERSION,
            }
            save_benchmark_cache(video.id, fail)
            log(f"[基准] 跳过竖屏/无效画幅 · {video.id}")
            return fail

        frames = _extract_spread_frames(video_file, tmp_path / "frames")
        log(f"[基准] VLM 分析 · {video.id} · {len(frames)} 帧")
        data, reviewer = _call_gemini_benchmark(
            video, frames, series_goal=series_goal, log_fn=log_fn
        )
        data["title"] = video.title
        data["watch_url"] = video.watch_url
        data["reviewer"] = reviewer
        data["cache_hit"] = False
        data["failed"] = False
        save_benchmark_cache(video.id, data)
        return data


def prepare_top_benchmarks(
    *,
    series_goal: str,
    top_n: int = 5,
    force_pool: bool = False,
    log_fn: LogFn | None = None,
) -> list[dict]:
    """拉候选池 → 过滤 → 逐条基准（缓存/下载/分析），失败自动补位。"""
    log = log_fn or (lambda _m: None)
    keywords = keywords_for_series_goal(series_goal)
    log(f"[基准] 准备候选池 · 目标={series_goal_label(series_goal)} · 关键词={keywords}")
    videos, _channels, from_cache = fetch_competitor_pool(
        keywords, force=force_pool, log_fn=log_fn
    )
    log(f"[基准] 候选 {len(videos)} 条（{'缓存' if from_cache else '新抓取'}）")
    ranked = select_benchmark_candidates(videos, top_n=max(top_n * 3, top_n))
    benchmarks: list[dict] = []
    for video in ranked:
        if len(benchmarks) >= top_n:
            break
        item = analyze_benchmark_video(video, series_goal=series_goal, log_fn=log_fn)
        if item.get("failed"):
            continue
        benchmarks.append(item)
    log(f"[基准] 有效基准 {len(benchmarks)}/{top_n}")
    return benchmarks


__all__ = [
    "RUBRIC_VERSION",
    "analyze_benchmark_video",
    "load_benchmark_cache",
    "prepare_top_benchmarks",
    "save_benchmark_cache",
]
