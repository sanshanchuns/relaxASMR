"""三档提示词生成：输入校验、JSON 解析、避坑规则进 system。"""

import json

import pytest

from scripts.aigc_lab.prompt_gen import (
    SEEDANCE_GUARDRAILS,
    PromptGenError,
    PromptSet,
    RainPrompt,
    _build_user,
    _parse,
    assertions_from_prompt,
    build_system,
    compose_prompt,
    parse_prompt_parts,
)


def _payload(**overrides) -> str:
    modes = [
        {
            "rain_mode": m,
            "visual": f"固定机位中景，前景阔叶虚化，中景海芋清晰，远景垂藤微虚（{m}）",
            "lighting": "冷暗雨夜，右侧一点暖橙微光只照中景上半",
            "motion": f"叶被{m}雨点击中微幅下沉并弹回，细密竖向雨丝匀速下落",
            "constraints": ["镜头全程固定不移动", "画面中没有人物"],
        }
        for m in ("light_mod", "heavy", "storm")
    ]
    data = {"subjects": ["木屋", "屋檐"], "modes": modes}
    data.update(overrides)
    return json.dumps(data, ensure_ascii=False)


def test_parse_returns_three_modes_in_order():
    subjects, prompts = _parse(_payload())
    assert subjects == ["木屋", "屋檐"]
    assert [p.rain_mode for p in prompts] == ["light_mod", "heavy", "storm"]
    assert prompts[0].prompt.startswith("【画面】")
    assert "【光影】" in prompts[0].prompt
    assert "【动态】" in prompts[0].prompt
    assert "【约束】" in prompts[0].prompt
    assert prompts[0].assertions == ["镜头全程固定不移动", "画面中没有人物"]


def test_parse_tolerates_surrounding_prose():
    subjects, prompts = _parse("好的，结果如下：\n" + _payload() + "\n希望有帮助")
    assert len(prompts) == 3
    assert subjects


def test_parse_rejects_missing_mode():
    modes = [
        {
            "rain_mode": "heavy",
            "visual": "p",
            "lighting": "p",
            "motion": "p",
            "constraints": [],
        }
    ]
    with pytest.raises(PromptGenError, match="漏了雨档"):
        _parse(_payload(modes=modes))


def test_parse_rejects_non_json():
    with pytest.raises(PromptGenError, match="没有 JSON"):
        _parse("模型今天不想干活")


def test_empty_prompt_counts_as_missing():
    modes = [
        {
            "rain_mode": m,
            "visual": "" if m == "storm" else "p",
            "lighting": "" if m == "storm" else "p",
            "motion": "" if m == "storm" else "p",
            "constraints": [],
        }
        for m in ("light_mod", "heavy", "storm")
    ]
    with pytest.raises(PromptGenError, match="storm"):
        _parse(_payload(modes=modes))


def test_user_needs_image_or_subjects():
    with pytest.raises(PromptGenError):
        _build_user(subjects=[], has_image=False, note="")


def test_user_mentions_image_anchor_when_image_given():
    text = _build_user(subjects=[], has_image=True, note="")
    assert "参考原图" in text
    assert "不要复制参考图" in text
    assert "前景" in text


def test_system_carries_every_guardrail():
    system = build_system()
    for rule in SEEDANCE_GUARDRAILS:
        assert rule.split("。")[0][:12] in system


def test_extra_rules_append_to_guardrails():
    system = build_system(extra_rules=["后验发现：写「水柱」比写「水流」命中率高"])
    assert "后验发现" in system


def test_system_describes_four_parts():
    system = build_system()
    assert "【画面】" in system
    assert "【光影】" in system
    assert "【动态】" in system
    assert "【约束】" in system
    assert "constraints" in system
    assert "前景" in system and "远景" in system
    assert "双标注" in system
    assert "景别：" in system
    assert "【动作】" not in system


def test_prompt_set_lookup_by_mode():
    _, prompts = _parse(_payload())
    ps = PromptSet(subjects=["木屋"], prompts=prompts)
    assert ps.by_mode("暴雨").rain_mode == "storm"
    assert "【动态】叶被light_mod雨点击中" in ps.by_mode("light_mod").prompt


def test_rain_prompt_composes_parts():
    item = RainPrompt.from_dict(
        {
            "rain_mode": "downpour",
            "visual": "固定机位中景，前景阔叶虚化，中景海芋清晰",
            "lighting": "冷暗雨夜，右侧一点暖橙微光",
            "motion": "阔叶被砸弯后回弹，细密雨丝匀速下落",
            "constraints": ["镜头全程固定不移动", "画面中没有人物"],
        }
    )
    assert item.rain_mode == "storm"
    assert item.prompt == (
        "【画面】固定机位中景，前景阔叶虚化，中景海芋清晰\n"
        "【光影】冷暗雨夜，右侧一点暖橙微光\n"
        "【动态】阔叶被砸弯后回弹，细密雨丝匀速下落\n"
        "【约束】镜头全程固定不移动。画面中没有人物。"
    )
    assert item.assertions == ["镜头全程固定不移动", "画面中没有人物"]


def test_legacy_five_part_keys_map_to_four():
    item = RainPrompt.from_dict(
        {
            "rain_mode": "downpour",
            "action": "阔叶被砸弯后回弹",
            "multi": "海芋受击，木架泻水",
            "effect": "固定镜头，不要生成音乐",
            "rhythm": "中景",
            "constraints": ["镜头全程固定不移动", "画面中没有人物"],
        }
    )
    assert item.prompt == (
        "【画面】中景。海芋受击，木架泻水\n"
        "【光影】固定镜头，不要生成音乐\n"
        "【动态】阔叶被砸弯后回弹\n"
        "【约束】镜头全程固定不移动。画面中没有人物。"
    )


def test_legacy_prompt_appends_constraints():
    item = RainPrompt.from_dict(
        {"rain_mode": "downpour", "prompt": " p ", "assertions": ["a", "  ", ""]}
    )
    assert item.rain_mode == "storm"
    assert item.prompt == "p\n【约束】a。"
    assert item.assertions == ["a"]


def test_compose_and_parse_roundtrip():
    text = compose_prompt(
        visual="固定机位中景，前景阔叶虚化",
        lighting="冷暗雨夜，右侧一点暖橙微光",
        motion="叶被击中微动，细密雨丝匀速下落",
        constraints=["无人物", "镜头不移动"],
    )
    parts = parse_prompt_parts(text)
    assert parts["visual"] == "固定机位中景，前景阔叶虚化"
    assert parts["lighting"] == "冷暗雨夜，右侧一点暖橙微光"
    assert parts["motion"] == "叶被击中微动，细密雨丝匀速下落"
    assert assertions_from_prompt(text) == ["无人物", "镜头不移动"]
