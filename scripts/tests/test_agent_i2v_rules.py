"""图生 Agent 共享规则 / Jimeng 技能。"""

from scripts.aigc_lab.agent_i2v_rules import (
    AGENT_I2V_RULES_DOC,
    JIMENG_I2V_SKILL_NAME,
    clear_agent_i2v_rules_cache,
    load_agent_i2v_rules_text,
    load_jimeng_i2v_skill,
)


def test_load_agent_i2v_rules_compressed():
    clear_agent_i2v_rules_cache()
    assert AGENT_I2V_RULES_DOC.is_file()
    text = load_agent_i2v_rules_text()
    assert "保留" in text
    assert "全能参考" in text
    assert len(text) < 1200


def test_jimeng_skill_payload():
    clear_agent_i2v_rules_cache()
    skill = load_jimeng_i2v_skill()
    assert skill["name"] == JIMENG_I2V_SKILL_NAME
    assert len(skill["name"]) <= 20
    assert skill["content"]
    assert "rain_mode" in skill["content"] or "雨" in skill["content"]


def test_shared_rules_forbid_example_parroting():
    clear_agent_i2v_rules_cache()
    text = load_agent_i2v_rules_text()
    assert "禁抄示例" in text or "禁" in text
    assert "稍近景特写" not in text
    assert "占画面约六成" not in text
