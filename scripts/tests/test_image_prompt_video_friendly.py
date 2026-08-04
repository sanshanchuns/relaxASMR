"""系列图提示词：必须是视频友好静帧，不能写成高速摄影。"""

from __future__ import annotations

import pytest

from scripts.series_video.prompt_rules import validate_image_prompt
from scripts.series_video.prompts import THEME_ANCHOR, build_image_variants

STORM = "storm_sleep"
FOCUS = "steady_focus"
DRIZZLE = "drizzle_meditation"


@pytest.mark.parametrize("series_id", [STORM, FOCUS, DRIZZLE])
def test_generated_image_prompts_are_video_friendly(series_id: str) -> None:
    prompt = build_image_variants(1, series_id=series_id, seed=11)[0].to_prompt().lower()
    assert "frozen" not in prompt
    assert "clean splash crowns" not in prompt
    assert "wet surface beads" in prompt or "wet sheen" in prompt or "clinging" in prompt or "mist" in prompt
    assert validate_image_prompt(
        build_image_variants(1, series_id=series_id, seed=11)[0].to_prompt(),
        series_id,
    ) == []


def test_theme_anchor_avoids_highspeed_cues() -> None:
    low = THEME_ANCHOR.lower()
    assert "frozen" not in low
    assert "splash crowns" not in low


def test_frozen_still_wording_is_rejected() -> None:
    prompt = build_image_variants(1, series_id=FOCUS, seed=3)[0].to_prompt()
    toxic = prompt.replace(
        "wet surface beads on the subject, soft airborne mist, calm grey background",
        "crisp frozen droplets on the subject, clean splash crowns, calm grey background",
    )
    problems = validate_image_prompt(toxic, FOCUS)
    assert problems, "高速冻滴措辞被放行了"
    assert any("高速摄影" in p or "frozen" in p.lower() for p in problems)


def test_gate_still_for_video_is_exported() -> None:
    from scripts.series_video.review import gate_still_for_video

    assert callable(gate_still_for_video)
