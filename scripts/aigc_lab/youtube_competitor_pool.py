"""无 UI 的 YouTube 爆款候选池：复用「爆款分析」搜索与缓存逻辑。"""

from __future__ import annotations

import dataclasses
import re
from collections.abc import Callable

from gui.youtube_api import ChannelInfo, VideoInfo, YoutubeApiError
from gui.youtube_cache import cache_get, cache_set

LogFn = Callable[[str], None]

DEFAULT_KEYWORDS_TEXT = "leaf rain"
_SEARCH_MAX_RESULTS = 25
_MAX_KEYWORDS = 6
_CACHE_TTL_SEC = 24 * 3600
_POOL_CACHE_KEY_PREFIX = "competitor_pool_v3::"

# 按 AIGC 雨档映射的系列目标 → 默认搜索关键词（逗号可拆多个）
SERIES_GOAL_KEYWORDS: dict[str, list[str]] = {
    "storm_sleep": ["heavy rain sleep", "thunderstorm rain sounds", "torrential rain asmr"],
    "steady_focus": ["rain sounds focus", "steady rain ambient", "moderate rain sounds"],
    "drizzle_meditation": ["light rain meditation", "gentle rain sounds", "drizzle rain asmr"],
}

RAIN_MODE_TO_SERIES_GOAL: dict[str, str] = {
    "storm": "storm_sleep",
    "heavy": "steady_focus",
    "light_mod": "drizzle_meditation",
}

_SERIES_GOAL_LABELS: dict[str, str] = {
    "storm_sleep": "暴雨助眠",
    "steady_focus": "中雨专注",
    "drizzle_meditation": "轻雨冥想",
}

_ISO8601_DURATION = re.compile(
    r"^PT(?:(?P<hours>\d+)H)?(?:(?P<minutes>\d+)M)?(?:(?P<seconds>\d+)S)?$",
    re.IGNORECASE,
)


def series_goal_for_rain_mode(rain_mode: str) -> str:
    from scripts.aigc_lab.rain_modes import normalize_rain_mode

    return RAIN_MODE_TO_SERIES_GOAL.get(normalize_rain_mode(rain_mode), "steady_focus")


def series_goal_label(series_goal: str) -> str:
    return _SERIES_GOAL_LABELS.get(series_goal, series_goal)


def parse_keywords(text: str) -> list[str]:
    parts = [p.strip() for p in text.replace("，", ",").split(",")]
    keywords = [p for p in parts if p]
    return keywords[:_MAX_KEYWORDS] or [DEFAULT_KEYWORDS_TEXT]


def keywords_for_series_goal(series_goal: str) -> list[str]:
    return list(SERIES_GOAL_KEYWORDS.get(series_goal) or [DEFAULT_KEYWORDS_TEXT])


def parse_iso8601_duration_seconds(text: str) -> float | None:
    raw = (text or "").strip().upper()
    if not raw:
        return None
    m = _ISO8601_DURATION.match(raw)
    if not m:
        return None
    hours = int(m.group("hours") or 0)
    minutes = int(m.group("minutes") or 0)
    seconds = int(m.group("seconds") or 0)
    total = hours * 3600 + minutes * 60 + seconds
    return float(total) if total > 0 else None


def is_short_form_video(video: VideoInfo, *, min_long_seconds: float = 60.0) -> bool:
    title = (video.title or "").lower()
    if "#short" in title or "#shorts" in title:
        return True
    dur = parse_iso8601_duration_seconds(video.duration)
    if dur is not None and dur < min_long_seconds:
        return True
    return False


def _video_to_dict(v: VideoInfo) -> dict:
    return dataclasses.asdict(v)


def _video_from_dict(d: dict) -> VideoInfo:
    return VideoInfo(**d)


def _channel_to_dict(c: ChannelInfo) -> dict:
    return dataclasses.asdict(c)


def _channel_from_dict(d: dict) -> ChannelInfo:
    return ChannelInfo(**d)


def fetch_competitor_pool(
    keywords: list[str],
    *,
    force: bool = False,
    log_fn: LogFn | None = None,
) -> tuple[list[VideoInfo], dict[str, ChannelInfo], bool]:
    """返回 (视频池, 频道信息, 是否命中缓存)。"""
    from gui import youtube_api as yt

    log = log_fn or (lambda _m: None)
    cache_key = _POOL_CACHE_KEY_PREFIX + "|".join(keywords)

    if not force:
        cached = cache_get(cache_key, ttl_seconds=_CACHE_TTL_SEC)
        if cached:
            videos = [_video_from_dict(d) for d in cached.get("videos", [])]
            channels = {
                cid: _channel_from_dict(d)
                for cid, d in (cached.get("channels") or {}).items()
            }
            log(f"[爆款池] 命中缓存 · {len(videos)} 条 · 关键词={keywords}")
            return videos, channels, True

    seen_ids: dict[str, None] = {}
    for kw in keywords:
        log(f"[爆款池] 搜索「{kw}」（按播放量）…")
        for vid in yt.search_video_ids(kw, max_results=_SEARCH_MAX_RESULTS, order="viewCount"):
            seen_ids.setdefault(vid, None)
        log(f"[爆款池] 搜索「{kw}」（按最新发布）…")
        for vid in yt.search_video_ids(kw, max_results=_SEARCH_MAX_RESULTS, order="date"):
            seen_ids.setdefault(vid, None)

    all_details = yt.get_videos_details(list(seen_ids.keys()))
    channel_ids = list(dict.fromkeys(v.channel_id for v in all_details))
    channels = yt.get_channels_details(channel_ids)

    cache_set(
        cache_key,
        {
            "videos": [_video_to_dict(v) for v in all_details],
            "channels": {cid: _channel_to_dict(c) for cid, c in channels.items()},
        },
    )
    log(f"[爆款池] 抓取完成 · {len(all_details)} 条")
    return all_details, channels, False


def select_benchmark_candidates(
    videos: list[VideoInfo],
    *,
    top_n: int = 5,
    exclude_shorts: bool = True,
) -> list[VideoInfo]:
    """按 growth_score 排序，排除 Shorts/超短视频。"""
    pool = list(videos)
    if exclude_shorts:
        pool = [v for v in pool if not is_short_form_video(v)]
    pool.sort(key=lambda v: v.growth_score(), reverse=True)
    return pool[:top_n]


__all__ = [
    "DEFAULT_KEYWORDS_TEXT",
    "RAIN_MODE_TO_SERIES_GOAL",
    "SERIES_GOAL_KEYWORDS",
    "YoutubeApiError",
    "fetch_competitor_pool",
    "is_short_form_video",
    "keywords_for_series_goal",
    "parse_iso8601_duration_seconds",
    "parse_keywords",
    "select_benchmark_candidates",
    "series_goal_for_rain_mode",
    "series_goal_label",
]
