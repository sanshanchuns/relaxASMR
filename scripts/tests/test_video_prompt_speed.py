"""图生视频提示词：自然速度这条闸门必须拦得住慢镜头。"""

from __future__ import annotations

import pytest

from scripts.series_video.prompt_rules import validate_video_prompt
from scripts.series_video.prompts import RAIN_INTENSITY_VARIANTS, build_video_prompt


@pytest.mark.parametrize("intensity", sorted(RAIN_INTENSITY_VARIANTS))
def test_template_passes_rules(intensity: str) -> None:
    prompt = build_video_prompt(
        subject_hint="a purple petal resting on a lily pad, rain bouncing around it",
        rain_intensity=intensity,
    )
    assert validate_video_prompt(prompt) == []


def test_template_states_realtime_speed_and_intensity() -> None:
    prompt = build_video_prompt(rain_intensity="heavy").lower()
    assert "real-time speed" in prompt
    assert "heavy rain pours down" in prompt
    assert "motion-blurred streaks" in prompt
    assert "avoid slow motion" in prompt


def test_slow_motion_wording_is_rejected() -> None:
    """把速度锚点换成慢镜头措辞，校验器必须拒收。"""
    prompt = build_video_prompt(rain_intensity="heavy").replace(
        "heavy rain pours down at real-time speed under natural gravity",
        "rain drifts down slowly in dreamy slow motion",
    )
    problems = validate_video_prompt(prompt)
    assert problems, "慢镜头措辞被放行了"
    assert any("slow motion" in p for p in problems)


def test_2026_08_regression_prompt_is_stale() -> None:
    """线上第一条慢镜头 prompt：改规范后必须判为过期，触发重新生成。"""
    shipped = (
        "Animate the provided image. Subject: purple flower on a lily pad.\n"
        "Motion: Raindrops steadily hit the leaf and water surface, creating "
        "gentle splash crowns and expanding ripples while fine mist drifts, "
        "with the subject remaining stationary.\n"
        "Environment: Unchanged from the provided image.\n"
        "Camera: Locked-off tripod, fixed framing, no pan no zoom.\n"
        "Style: Cinematic macro realism, cool desaturated film tone.\n"
        "Loop seamlessly: last frame matches the first.\n"
        "Constraints: Avoid camera movement, panning, zooming, shaking, "
        "temporal flicker, morphing, transitions, humans, text."
    )
    assert validate_video_prompt(shipped)
