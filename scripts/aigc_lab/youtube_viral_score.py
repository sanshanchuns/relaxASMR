"""成片油管黑马预测：对照同系列 Top5 真实爆款基准评分。"""

from __future__ import annotations

import json
import re
import tempfile
from collections.abc import Callable
from pathlib import Path

from scripts.aigc_lab.agent_store import AgentRun
from scripts.aigc_lab.youtube_benchmark import prepare_top_benchmarks
from scripts.aigc_lab.youtube_competitor_pool import (
    series_goal_for_rain_mode,
    series_goal_label,
)

LogFn = Callable[[str], None]
_MODEL = "gemini-3.6-flash"
_JSON_BLOCK = re.compile(r"\{.*\}", re.DOTALL)

_SYSTEM = """你是 YouTube 下雨 ASMR 频道的内容评审。你会收到新成片抽帧，以及同系列真实爆款 Top5 的结构化基准。
请逐维对比，判断这条短成片扩成长挂片/同系列异构条目的黑马潜力。
只输出 JSON：
{
  "score":0-100,
  "verdict":"strong|maybe|weak",
  "series_goal":"storm_sleep|steady_focus|drizzle_meditation",
  "dimensions":{
    "rain_realism":0-100,
    "foreground_rain_impact":0-100,
    "series_variation":0-100,
    "composition":0-100,
    "fixed_camera":0-100,
    "loop_ambiance":0-100,
    "goal_fit":0-100,
    "viral_potential":0-100
  },
  "benchmark_hits":[{"video_id":"","note":""}],
  "notes":["短评与改进建议"],
  "youtube_title_hint":"可选标题灵感"
}
评分要严格：对照基准找差距；灰雾发闷、字幕杂物、人物、雨感假、抖动运镜、不适合挂片 → 压分。
"""


def youtube_viral_score(
    run: AgentRun,
    *,
    log_fn: LogFn | None = None,
    rain_mode: str | None = None,
    series_goal: str | None = None,
) -> dict:
    """对 run.video_path 抽帧，注入 Top5 基准后打分；写入 viral_score.json。"""
    from scripts.config.paths import ensure_cli_path
    from scripts.series_video.video_probe import extract_review_frames, measure_motion, probe_video

    ensure_cli_path()
    from agy import generate_text_via_agy_accounts, has_agy_credentials
    from agy.client import AGY_IMAGE_LABELS

    if not has_agy_credentials():
        raise RuntimeError("未配置 agy 凭据，无法油管打分")
    video = run.video_path
    if not video.is_file():
        raise FileNotFoundError(f"无成片: {video}")

    log = log_fn or (lambda _m: None)
    meta = run.meta or {}
    mode = str(rain_mode or meta.get("rain_mode") or "heavy")
    goal = str(series_goal or meta.get("series_goal") or series_goal_for_rain_mode(mode))
    goal_label = series_goal_label(goal)

    log(f"[Viral] 基准准备 · 目标={goal_label}…")
    benchmarks = prepare_top_benchmarks(series_goal=goal, top_n=5, log_fn=log_fn)
    cache_hits = sum(1 for b in benchmarks if b.get("cache_hit"))
    log(f"[Viral] 基准 {len(benchmarks)} 条（缓存命中 {cache_hits}）")

    probe = probe_video(video)
    motion = measure_motion(video)
    rain = meta.get("rain_label") or meta.get("rain_mode") or mode
    prompt_preview = (run.prompt or "")[:500]

    bench_lines = []
    for i, b in enumerate(benchmarks, start=1):
        bench_lines.append(
            f"#{i} id={b.get('video_id')} title={b.get('title','')[:60]} "
            f"cache_hit={b.get('cache_hit')} rain_realism={b.get('rain_realism')} "
            f"scene={b.get('scene','')[:80]} strengths={b.get('reusable_strengths', [])[:2]}"
        )
    bench_blob = "\n".join(bench_lines) or "（无有效基准，请按通用 ASMR 标准保守打分）"

    with tempfile.TemporaryDirectory(prefix="viral_frames_") as tmp:
        frames = extract_review_frames(video, Path(tmp), count=6)
        images: list[tuple[str, bytes]] = []
        for fp in frames:
            p = Path(fp)
            if p.is_file():
                mime = "image/png" if p.suffix.lower() == ".png" else "image/jpeg"
                images.append((mime, p.read_bytes()))

        user = (
            f"目标系列：{goal_label}（{goal}）\n"
            f"雨档：{rain}\n时长探测：{probe}\n运动量：{motion}\n"
            f"生成提示词（参考）：{prompt_preview}\n\n"
            f"Top5 真实爆款基准：\n{bench_blob}\n\n"
            f"附 {len(images)} 张新成片抽帧，请对比打分。"
        )
        log(f"[Viral] 抽帧 {len(images)} 张 · Gemini 黑马预测…")
        text, email = generate_text_via_agy_accounts(
            user,
            model=_MODEL,
            effort="medium",
            system=_SYSTEM,
            images=images or None,
            log_fn=log_fn,
            account_labels=AGY_IMAGE_LABELS,
        )
        frame_count = len(images)

    data = _parse(text)
    data["reviewer"] = email
    data["motion"] = motion
    data["frame_count"] = frame_count
    data["rain_mode"] = mode
    data["series_goal"] = goal
    data["series_goal_label"] = goal_label
    data["benchmark_count"] = len(benchmarks)
    data["benchmark_cache_hits"] = cache_hits
    data["benchmark_video_ids"] = [str(b.get("video_id") or "") for b in benchmarks]
    data["benchmarks"] = [
        {
            "video_id": b.get("video_id"),
            "title": b.get("title"),
            "cache_hit": b.get("cache_hit"),
            "watch_url": b.get("watch_url"),
        }
        for b in benchmarks
    ]
    run.save_viral(data)
    return data


def _parse(text: str) -> dict:
    raw = (text or "").strip()
    m = _JSON_BLOCK.search(raw)
    blob = m.group(0) if m else raw
    try:
        data = json.loads(blob)
    except json.JSONDecodeError:
        return {
            "score": 0,
            "verdict": "weak",
            "dimensions": {},
            "notes": [f"解析失败: {raw[:300]}"],
            "raw": raw,
        }
    if not isinstance(data, dict):
        return {"score": 0, "verdict": "weak", "notes": ["非对象 JSON"], "raw": raw}
    data.setdefault("score", 0)
    data.setdefault("verdict", "maybe")
    data.setdefault("notes", [])
    data.setdefault("dimensions", {})
    return data
