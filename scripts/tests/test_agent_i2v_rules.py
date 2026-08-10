"""图生 Agent 共享规则 / Jimeng 技能。"""

from scripts.aigc_lab.agent_i2v_rules import (
    AGENT_I2V_RULES_DOC,
    JIMENG_I2V_SKILL_NAME,
    clear_agent_i2v_rules_cache,
    load_agent_i2v_rules_text,
    load_jimeng_i2v_skill,
)
from scripts.aigc_lab.agent_loop import (
    _i2v_draft_system,
    _i2v_review_system,
    build_draft_prompt,
)


def test_load_agent_i2v_rules_compressed():
    clear_agent_i2v_rules_cache()
    assert AGENT_I2V_RULES_DOC.is_file()
    text = load_agent_i2v_rules_text()
    assert "保留" in text
    assert "调整" in text
    assert "全能参考" in text
    assert "前景" in text
    assert "周期往复" in text
    # 压缩：远短于旧长文
    assert len(text) < 1200


def test_review_gets_rules_jimeng_draft_is_short():
    clear_agent_i2v_rules_cache()
    rules = load_agent_i2v_rules_text()
    draft = _i2v_draft_system()
    review = _i2v_review_system()
    assert rules in review
    assert rules not in draft
    assert "雨ASMR图生" in draft
    assert len(draft) < 400


def test_jimeng_skill_payload():
    clear_agent_i2v_rules_cache()
    skill = load_jimeng_i2v_skill()
    assert skill["name"] == JIMENG_I2V_SKILL_NAME
    assert len(skill["name"]) <= 20
    assert "六槽" in skill["description"] or "JSON" in skill["description"]
    assert "rain_mode" in skill["content"]
    assert "周期往复" in skill["content"] or "周期" in load_agent_i2v_rules_text()


def test_build_i2v_draft_prompt_short():
    clear_agent_i2v_rules_cache()
    text = build_draft_prompt(rain_mode="heavy", scene_keywords="见图", kind="i2v")
    assert "雨ASMR图生" in text
    assert "共享规则" not in text
    assert len(text) < 500


def test_shared_rules_forbid_example_parroting():
    clear_agent_i2v_rules_cache()
    text = load_agent_i2v_rules_text()
    assert "禁抄示例" in text or "禁" in text
    assert "稍近景特写" not in text
    assert "占画面约六成" not in text
    assert "换一簇更侧" not in text
    assert "正向构图" in text
    assert "至少两项" in text or "≥2" in text
