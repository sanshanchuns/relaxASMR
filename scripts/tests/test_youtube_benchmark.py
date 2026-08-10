"""youtube_competitor_pool 与 benchmark 缓存/过滤。"""

from __future__ import annotations

import json
from pathlib import Path

from gui.youtube_api import VideoInfo
from scripts.aigc_lab.youtube_benchmark import (
    RUBRIC_VERSION,
    benchmark_cache_path,
    load_benchmark_cache,
    save_benchmark_cache,
)
from scripts.aigc_lab.youtube_competitor_pool import (
    is_short_form_video,
    keywords_for_series_goal,
    parse_iso8601_duration_seconds,
    select_benchmark_candidates,
    series_goal_for_rain_mode,
)


def test_rain_mode_series_goal_mapping():
    assert series_goal_for_rain_mode("storm") == "storm_sleep"
    assert series_goal_for_rain_mode("heavy") == "steady_focus"
    assert series_goal_for_rain_mode("light_mod") == "drizzle_meditation"


def test_keywords_for_series_goal():
    kws = keywords_for_series_goal("steady_focus")
    assert kws
    assert all(isinstance(k, str) for k in kws)


def test_parse_iso8601_duration():
    assert parse_iso8601_duration_seconds("PT5M") == 300.0
    assert parse_iso8601_duration_seconds("PT45S") == 45.0


def test_is_short_form_video():
    short = VideoInfo(
        id="s",
        title="rain #shorts",
        description="",
        channel_id="c",
        channel_title="",
        published_at="2026-01-01T00:00:00Z",
        thumbnail_url="",
        duration="PT30S",
    )
    long = VideoInfo(
        id="l",
        title="rain sleep",
        description="",
        channel_id="c",
        channel_title="",
        published_at="2026-01-01T00:00:00Z",
        thumbnail_url="",
        duration="PT2H",
        view_count=1000,
    )
    assert is_short_form_video(short)
    assert not is_short_form_video(long)


def test_select_benchmark_candidates_excludes_shorts():
    videos = [
        VideoInfo(
            id="s",
            title="#shorts",
            description="",
            channel_id="c",
            channel_title="",
            published_at="2026-01-01T00:00:00Z",
            thumbnail_url="",
            duration="PT20S",
            view_count=999999,
        ),
        VideoInfo(
            id="l",
            title="long rain",
            description="",
            channel_id="c",
            channel_title="",
            published_at="2026-01-01T00:00:00Z",
            thumbnail_url="",
            duration="PT3H",
            view_count=100,
        ),
    ]
    picked = select_benchmark_candidates(videos, top_n=5)
    assert len(picked) == 1
    assert picked[0].id == "l"


def test_benchmark_cache_roundtrip(tmp_path, monkeypatch):
    monkeypatch.setattr(
        "scripts.aigc_lab.youtube_benchmark._BENCHMARK_DIR",
        tmp_path,
    )
    save_benchmark_cache("abc123", {"scene": "forest", "rain_realism": 80})
    loaded = load_benchmark_cache("abc123")
    assert loaded is not None
    assert loaded["scene"] == "forest"
    assert loaded["rubric_version"] == RUBRIC_VERSION


def test_benchmark_cache_path_name():
    p = benchmark_cache_path("dQw4w9WgXcQ")
    assert "dQw4w9WgXcQ" in p.name
    assert RUBRIC_VERSION.replace("_", "") in p.name.replace("_", "")
