"""三个子系列的闸门：规则覆盖层、按系列派生的提示词、评审结论解析。"""

from __future__ import annotations

import pytest

from scripts.series_video.prompt_rules import (
    image_rules,
    series_ids,
    validate_image_prompt,
    validate_video_prompt,
)
from scripts.series_video.prompts import build_image_variants, build_video_prompt
from scripts.series_video.review import Review, _parse
from scripts.series_video.series import get_series, list_series

STORM = "storm_sleep"
FOCUS = "steady_focus"
DRIZZLE = "drizzle_meditation"


def test_three_series_defined() -> None:
    assert series_ids() == [STORM, FOCUS, DRIZZLE]
    for spec in list_series():
        assert spec.rain_phrase and spec.review_rubric
        lo, hi = spec.frame_motion
        assert 0 <= lo < hi <= 100


@pytest.mark.parametrize("series_id", [STORM, FOCUS, DRIZZLE])
def test_generated_prompts_pass_own_rules(series_id: str) -> None:
    video = build_video_prompt(subject_hint="a broad green lotus leaf", series_id=series_id)
    assert validate_video_prompt(video, series_id) == []
    image = build_image_variants(1, series_id=series_id, seed=7)[0].to_prompt()
    assert validate_image_prompt(image, series_id) == []


def test_storm_drops_the_base_storm_ban() -> None:
    """基础图片规则禁 storm，暴雨系列必须能解禁，否则自己拦自己。"""
    base_groups = {g["name"] for g in image_rules().raw["forbidden"]}
    storm_groups = {g["name"] for g in image_rules(STORM).raw["forbidden"]}
    assert "会破坏 loop 的剧烈天气" in base_groups
    assert "会破坏 loop 的剧烈天气" not in storm_groups
    # 但灾难片元素仍然要拦住 —— 狂暴的是雨量不是天气
    assert "狂暴的是雨量不是天气" in storm_groups


def test_series_prompts_are_not_interchangeable() -> None:
    """暴雨的提示词拿去过细雨的规则必须失败，反之亦然，否则覆盖层等于没写。"""
    storm = build_video_prompt(series_id=STORM)
    drizzle = build_video_prompt(series_id=DRIZZLE)
    assert validate_video_prompt(storm, DRIZZLE)
    assert validate_video_prompt(drizzle, STORM)


def test_video_rain_intensity_follows_series() -> None:
    assert "heavy rain pours down" in build_video_prompt(series_id=STORM)
    assert "steady rain falls" in build_video_prompt(series_id=FOCUS)
    assert "a light drizzle falls" in build_video_prompt(series_id=DRIZZLE)


def test_unknown_series_falls_back_to_default() -> None:
    """老批次没有 series_id 字段，读到空串不能炸。"""
    assert get_series("").id == FOCUS


def test_review_parses_json_with_noise() -> None:
    """模型偶尔会包 code fence 或多说一句话，都要能挖出 JSON。"""
    data = _parse('好的：\n```json\n{"verdict": "revise", "score": 40, "issues": ["雨太稀"]}\n```')
    review = Review(
        verdict=data["verdict"], score=data["score"], issues=data["issues"]
    )
    assert review.blocked and not review.ok
    assert "雨太稀" in review.summary


def test_review_error_is_hard_gate() -> None:
    from scripts.series_video.review import ReviewError

    assert issubclass(ReviewError, RuntimeError)


def test_format_seed_analysis() -> None:
    from scripts.series_video.review import format_seed_analysis

    text = format_seed_analysis(
        {
            "series_id": FOCUS,
            "verdict": "pass",
            "score": 92,
            "shot_scale": "近景",
            "rain_subjects": ["睡莲花瓣", "叶面"],
            "composition": "主体居中，浅景深，雨丝清晰可见",
            "issues": ["雨量符合中雨专注系列"],
        }
    )
    assert "中雨专注" in text
    assert "近景" in text
    assert "睡莲花瓣" in text
    assert "画面构成" in text

