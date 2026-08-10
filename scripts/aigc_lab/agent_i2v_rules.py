"""AIGC 图生视频 Agent 共享规则（Jimeng 技能 ↔ Gemini 注入）。

事实源：``instructions/rain_asmr_agent_i2v.md`` 文末 ``<!-- agent:rules -->`` 压缩块。
Jimeng：技能「雨ASMR图生」承载规则；对话只发短指令。
Gemini：审核 system 注入同一压缩块。
"""

from __future__ import annotations

import re
from functools import lru_cache
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
AGENT_I2V_RULES_DOC = REPO_ROOT / "instructions" / "rain_asmr_agent_i2v.md"
JIMENG_I2V_SKILL_DOC = REPO_ROOT / "instructions" / "jimeng_skills" / "雨ASMR图生.md"

_RULES_MARKER = "<!-- agent:rules -->"
_RULES_BLOCK = re.compile(
    re.escape(_RULES_MARKER) + r"\s*```(?:text)?\s*(?P<body>.*?)```",
    re.DOTALL,
)
_SKILL_SECTION = re.compile(
    r"## 技能(?P<kind>名称|描述|内容)\s*```(?:text)?\s*(?P<body>.*?)```",
    re.DOTALL,
)

#: 即梦技能名称（≤20 字，与 UI「技能名称」一致）
JIMENG_I2V_SKILL_NAME = "雨ASMR图生"


class AgentI2vRulesError(RuntimeError):
    pass


@lru_cache(maxsize=1)
def load_agent_i2v_rules_text() -> str:
    """读取压缩共享规则；文件缺失或标记损坏则抛错，禁止静默退化。"""
    doc = AGENT_I2V_RULES_DOC
    if not doc.is_file():
        raise AgentI2vRulesError(
            f"图生 Agent 规范缺失：{doc}。请恢复 instructions/rain_asmr_agent_i2v.md"
        )
    raw = doc.read_text(encoding="utf-8")
    m = _RULES_BLOCK.search(raw)
    if not m:
        raise AgentI2vRulesError(
            f"{doc.name} 缺少 <!-- agent:rules --> 文本块，无法注入 Gemini/技能"
        )
    text = m.group("body").strip()
    if len(text) < 80:
        raise AgentI2vRulesError(f"{doc.name} 共享规则块过短，请检查是否写坏")
    return text


@lru_cache(maxsize=1)
def load_jimeng_i2v_skill() -> dict[str, str]:
    """读取即梦技能三字段：name / description / content。"""
    doc = JIMENG_I2V_SKILL_DOC
    if not doc.is_file():
        # 技能 md 缺失时用规则块合成，保证自动化可建技能
        rules = load_agent_i2v_rules_text()
        return {
            "name": JIMENG_I2V_SKILL_NAME,
            "description": "雨ASMR图生六槽：全能参考·同系列异构；据附图输出 rain_mode+六槽JSON",
            "content": (
                "角色:雨ASMR图生提示词作者(Seedance·全能参考·同系列异构)。\n"
                "用户会附参考图。你只输出一个JSON(无markdown/无解释),键:\n"
                "rain_mode,subject,action,environment,camera,style,constraints\n"
                "rain_mode=storm|heavy|light_mod(按图;无雨默认heavy)。各槽=字符串数组。\n\n"
                + rules
            ),
        }
    raw = doc.read_text(encoding="utf-8")
    parts: dict[str, str] = {}
    for m in _SKILL_SECTION.finditer(raw):
        kind = m.group("kind")
        key = {"名称": "name", "描述": "description", "内容": "content"}[kind]
        parts[key] = m.group("body").strip()
    if not parts.get("name"):
        parts["name"] = JIMENG_I2V_SKILL_NAME
    if not parts.get("description"):
        parts["description"] = "雨ASMR图生六槽 JSON"
    if not parts.get("content"):
        parts["content"] = load_agent_i2v_rules_text()
    # 名称硬限制与即梦 UI 一致
    parts["name"] = parts["name"].strip()[:20]
    parts["description"] = parts["description"].strip()[:500]
    return parts


def clear_agent_i2v_rules_cache() -> None:
    load_agent_i2v_rules_text.cache_clear()
    load_jimeng_i2v_skill.cache_clear()
