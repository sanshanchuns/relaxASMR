"""Jimeng Agent 草稿 ↔ Gemini 审核/共识（最多 3 轮）协议。"""

from __future__ import annotations

import json
import re
from collections.abc import Callable, Sequence
from dataclasses import dataclass, field
from pathlib import Path

from scripts.aigc_lab.prompt_atoms import (
    DEFAULT_RAIN_MODE,
    RAIN_MODE_LABELS,
    SLOT_ORDER,
    compose_prompt,
    format_table,
    normalize_rain_mode,
)
from scripts.aigc_lab.youtube_competitor_pool import (
    series_goal_for_rain_mode,
    series_goal_label,
)

LogFn = Callable[[str], None]

_REVIEW_MODEL = "gemini-3.6-flash"
_MAX_ROUNDS = 3
_JSON_BLOCK = re.compile(r"\{.*\}", re.DOTALL)
_I2V_NO_RAIN_DEFAULT = "heavy"

_DRAFT_SYSTEM = """你是下雨 ASMR 文生/图生视频提示词作者。必须严格按六槽原子标签输出。
只输出一个 JSON（不要 markdown 围栏），键固定为：
subject, action, environment, camera, style, constraints
每个键的值是字符串数组；数组每一项是一个原子标签（单一语义断言）。

硬规则：
1. subject：一项=一个可见主体；禁止「A与B/和/、」并列；禁止高大/巨大等不可核验形容词。
2. action / environment：一项=一个结果或条件。
3. 标签不重不漏；六槽都要有内容。
4. 全中文为主；风格类可保留少量英文词（如 cinematic）单独成项。
5. 无人物、无字幕、无杂乱杂物；固定镜头优先；雨型强度必须与用户指定雨档一致。
"""

_REVIEW_SYSTEM = """你是雨 ASMR 频道的提示词审核员。检查六槽原子草稿的歧义、冲突、非原子、漏项、与雨型不符。
只输出 JSON：
{"verdict":"pass|revise","issues":[{"slot":"subject|action|environment|camera|style|constraints","tag":"原文或空","problem":"具体问题"}],"missing":["slot或描述"],"duplicates":["重复描述"],"conflict_tags":[{"slot":"...","tag":"..."}]}
verdict=pass 仅当标签原子清晰、互不矛盾、覆盖六槽且符合雨型。
conflict_tags 列出最需要标红的冲突标签（可多条）。
"""

#: Jimeng 对话短指令（规则由技能「雨ASMR图生」承载，勿再整段粘贴）
_JIMENG_I2V_TASK = """技能「雨ASMR图生」已启用。观察附图，只输出一个JSON(无markdown/无解释)，键:
rain_mode,subject,action,environment,camera,style,constraints
rain_mode=storm|heavy|light_mod(按图;无雨默认heavy)。各槽=字符串数组;一项=一中文原子;不重不漏。"""

_DRAFT_SYSTEM_I2V = _JIMENG_I2V_TASK  # 兼容旧引用；Jimeng 路径用短任务，不再附规则全文

_GEMINI_DRAFT_SYSTEM_I2V = """你是图生视频提示词独立观察者（Seedance · 全能参考 · 同系列异构）。
与 Jimeng 作者互不参考对方文案；只根据参考图与【共享规则】独立输出 JSON（不要 markdown 围栏）：
rain_mode, subject, action, environment, camera, style, constraints
rain_mode 取值：storm | heavy | light_mod（根据参考图判断；参考图无明显雨时用 heavy）。
每个槽的值是字符串数组；数组每一项是一个原子标签。
"""

_COMPARE_SYSTEM_I2V = """你是图生视频六槽语义对比员。你会收到 Jimeng 稿与 Gemini 独立稿（均已看图）。
按【共享规则】逐槽语义对比，判断双方是否达成一致（不要求字面相同，语义等价即可）。

只输出 JSON：
{
  "agreed": true|false,
  "rain_mode_agreed": true|false,
  "agreements": ["一致点简述"],
  "conflicts": [{"slot":"...","jimeng":"...","gemini":"...","reason":"..."}],
  "missing": [{"slot":"...","side":"jimeng|gemini","description":"..."}],
  "duplicates": ["重复描述"],
  "contradictions": [{"slot":"...","tags":["..."],"reason":"..."}],
  "conflict_tags": [{"slot":"...","tag":"...","side":"jimeng|gemini|both"}]
}
agreed=true 仅当六槽语义一致且 rain_mode 一致；否则 agreed=false。
conflict_tags 列出 GUI 应标红的 Jimeng 标签（side=jimeng 或 both）；Gemini 独有冲突也尽量映射到 Jimeng 可标标签。
missing 中 side=gemini 表示 Gemini 认为 Jimeng 缺失的内容。
"""


_REVIEW_SYSTEM_I2V = """你是图生视频提示词审核员。你会收到参考图与 Jimeng 六槽草稿。
你不产出六槽 JSON，只审核 Jimeng 稿是否合格；不通过则 verdict=revise。

审核重点（按优先级）：
1. **针对参考图的具体修改（最重要）**：对照参考图，检查 camera / subject 是否写清「如何异构」——必须是具体、可执行的正向描述。
   例：参考图枝条从右向左伸展 → 须写镜像为从左向右、或斜向插入画框等具体改法。
   仅有「勿复制构图」「同系列异构」等负面约束不算通过；缺少具体修改须在 missing / issues 中说明应补什么，并令 Jimeng 修订。
2. **动作周期往复（loop 硬要求）**：action 里凡是运动，都必须是周期往复（可持续、可回到相近状态），以便成片无缝 loop。
   叶片/枝条须小幅往复摆动；雨可写持续下落/持续砸叶。禁止单向完结型运动。
   约束里的「循环过渡自然 / seamless loop / 无缝循环」**无效**，不能当作通过依据；缺周期往复须让 Jimeng 改 action，不是加约束。
3. **重复**：跨槽或同槽内语义重复 → duplicates；需标红的写入 conflict_tags。
4. **歧义 / 模糊**：标签含义不清、不可核验、过于笼统 → issues + conflict_tags，要求改到尽量明确。

**疑问（questions）**：对提示词措辞、术语搭配、看似冗余的标签有任何不清楚之处，必须写入 questions，交给 Jimeng Agent 解释并存档。
例：「焦点对准前景 + 背景虚化」之外为何还要「浅景深」？——应提问，勿仅因「看起来重复」就判 duplicates 删掉有用术语。
若手册已有同类答案，可参考，不必重复提问。questions 不代替 revise；真问题仍用 issues/missing。

仍须检查：六槽均有内容、前景雨击打、共享规则、rain_mode 与参考图一致（无明显雨默认 heavy）。

只输出 JSON：
{"verdict":"pass|revise","issues":[{"slot":"subject|action|environment|camera|style|constraints","tag":"原文或空","problem":"具体问题"}],"missing":["slot或应补充的具体修改描述"],"duplicates":["重复描述"],"conflict_tags":[{"slot":"...","tag":"..."}],"questions":["对提示词的具体疑问（可空数组）"]}
verdict=pass 仅当无重复/歧义，camera（及必要的 subject）含针对参考图的具体构图/主体调整，且 action 运动均为周期往复。
conflict_tags 列出最需要标红的 Jimeng 标签。
"""

_HANDBOOK_ANSWER_SYSTEM = """你是 Seedance / 即梦图生视频提示词作者（Jimeng Agent）。
Gemini 审核员对你刚写的六槽标签提出了疑问。请针对每个疑问给出专业、可落地的解释：
- 说明这些标签在 Seedance 里各自约束什么；
- 若看似重复，解释为何仍要保留（例如光学虚化 vs 雨雾朦胧）；
- 用中文，具体，不要空话。

只输出 JSON（不要 markdown 围栏）：
{"answers":[{"question":"原问原文","answer":"合理解释","title":"可选短标题"}]}
answers 数量须覆盖所有问题。
"""



def _i2v_shared_rules_block() -> str:
    from scripts.aigc_lab.agent_i2v_rules import load_agent_i2v_rules_text

    return load_agent_i2v_rules_text()


def _i2v_review_system() -> str:
    return _REVIEW_SYSTEM_I2V.strip() + "\n\n" + _i2v_shared_rules_block()


def _i2v_draft_system() -> str:
    """Jimeng 出稿：短任务（技能已含规则）。"""
    return _JIMENG_I2V_TASK.strip()


def _i2v_gemini_draft_system() -> str:
    return _GEMINI_DRAFT_SYSTEM_I2V.strip() + "\n\n" + _i2v_shared_rules_block()


def _i2v_compare_system() -> str:
    return _COMPARE_SYSTEM_I2V.strip() + "\n\n" + _i2v_shared_rules_block()


@dataclass
class ReviewIssue:
    slot: str
    tag: str
    problem: str

    def to_dict(self) -> dict:
        return {"slot": self.slot, "tag": self.tag, "problem": self.problem}


@dataclass
class ReviewResult:
    verdict: str  # pass | revise
    issues: list[ReviewIssue] = field(default_factory=list)
    missing: list[str] = field(default_factory=list)
    duplicates: list[str] = field(default_factory=list)
    conflict_tags: list[dict[str, str]] = field(default_factory=list)
    questions: list[str] = field(default_factory=list)
    raw: str = ""
    reviewer: str = ""

    def to_dict(self) -> dict:
        return {
            "verdict": self.verdict,
            "issues": [i.to_dict() for i in self.issues],
            "missing": list(self.missing),
            "duplicates": list(self.duplicates),
            "conflict_tags": list(self.conflict_tags),
            "questions": list(self.questions),
            "reviewer": self.reviewer,
        }


@dataclass
class ConsensusComparison:
    agreed: bool
    rain_mode_agreed: bool = True
    agreements: list[str] = field(default_factory=list)
    conflicts: list[dict] = field(default_factory=list)
    missing: list[dict] = field(default_factory=list)
    duplicates: list[str] = field(default_factory=list)
    contradictions: list[dict] = field(default_factory=list)
    conflict_tags: list[dict[str, str]] = field(default_factory=list)
    raw: str = ""
    reviewer: str = ""

    def to_dict(self) -> dict:
        return {
            "agreed": self.agreed,
            "rain_mode_agreed": self.rain_mode_agreed,
            "agreements": list(self.agreements),
            "conflicts": list(self.conflicts),
            "missing": list(self.missing),
            "duplicates": list(self.duplicates),
            "contradictions": list(self.contradictions),
            "conflict_tags": list(self.conflict_tags),
            "reviewer": self.reviewer,
        }


@dataclass
class RoundRecord:
    round: int
    source: str  # jimeng_agent | revise
    jimeng_slots: dict[str, list[str]] = field(default_factory=dict)
    gemini_slots: dict[str, list[str]] = field(default_factory=dict)
    jimeng_rain_mode: str = ""
    gemini_rain_mode: str = ""
    jimeng_raw: str = ""
    gemini_raw: str = ""
    comparison: dict = field(default_factory=dict)
    # 文生兼容字段
    draft_slots: dict[str, list[str]] = field(default_factory=dict)
    draft_raw: str = ""
    review: dict = field(default_factory=dict)
    handbook_qa: list[dict[str, str]] = field(default_factory=list)

    def to_dict(self) -> dict:
        return {
            "round": self.round,
            "source": self.source,
            "jimeng_slots": self.jimeng_slots,
            "gemini_slots": self.gemini_slots,
            "jimeng_rain_mode": self.jimeng_rain_mode,
            "gemini_rain_mode": self.gemini_rain_mode,
            "jimeng_raw": self.jimeng_raw[:4000],
            "gemini_raw": self.gemini_raw[:4000],
            "comparison": self.comparison,
            "draft_slots": self.draft_slots or self.jimeng_slots,
            "draft_raw": (self.draft_raw or self.jimeng_raw)[:4000],
            "review": self.review or self.comparison,
            "handbook_qa": list(self.handbook_qa),
        }


@dataclass
class LoopResult:
    slots: dict[str, list[str]]
    agreed: bool
    rounds: list[RoundRecord] = field(default_factory=list)
    unresolved_conflicts: list[dict[str, str]] = field(default_factory=list)
    fail_slots: list[str] = field(default_factory=list)
    prompt: str = ""
    rain_mode: str = ""
    series_goal: str = ""
    gemini_slots: dict[str, list[str]] = field(default_factory=dict)
    handbook_qa: list[dict[str, str]] = field(default_factory=list)

    def to_review_json(self) -> dict:
        return {
            "agreed": self.agreed,
            "max_rounds": _MAX_ROUNDS,
            "rounds": [r.to_dict() for r in self.rounds],
            "unresolved_conflicts": list(self.unresolved_conflicts),
            "fail_slots": list(self.fail_slots),
            "final_slots": self.slots,
            "rain_mode": self.rain_mode,
            "series_goal": self.series_goal,
            "gemini_final_slots": self.gemini_slots,
            "handbook_qa": list(self.handbook_qa),
        }


def loop_result_from_review_json(data: dict | None) -> LoopResult | None:
    """从 session / review JSON 恢复 LoopResult（详情面板用）。"""
    if not isinstance(data, dict):
        return None
    rounds_raw = data.get("rounds") or []
    final = data.get("final_slots")
    if not rounds_raw and not final:
        return None
    slots = final if isinstance(final, dict) else empty_slots()
    rounds: list[RoundRecord] = []
    for raw in rounds_raw:
        if not isinstance(raw, dict):
            continue
        jimeng = raw.get("jimeng_slots") or raw.get("draft_slots")
        gemini = raw.get("gemini_slots") or {}
        comparison = raw.get("comparison") or raw.get("review") or {}
        rounds.append(
            RoundRecord(
                round=int(raw.get("round") or 0),
                source=str(raw.get("source") or ""),
                jimeng_slots=jimeng if isinstance(jimeng, dict) else empty_slots(),
                gemini_slots=gemini if isinstance(gemini, dict) else empty_slots(),
                jimeng_rain_mode=str(raw.get("jimeng_rain_mode") or ""),
                gemini_rain_mode=str(raw.get("gemini_rain_mode") or ""),
                jimeng_raw=str(raw.get("jimeng_raw") or raw.get("draft_raw") or ""),
                gemini_raw=str(raw.get("gemini_raw") or ""),
                comparison=comparison if isinstance(comparison, dict) else {},
                draft_slots=jimeng if isinstance(jimeng, dict) else empty_slots(),
                draft_raw=str(raw.get("draft_raw") or raw.get("jimeng_raw") or ""),
                review=comparison if isinstance(comparison, dict) else {},
                handbook_qa=[
                    {
                        "question": str(x.get("question") or ""),
                        "answer": str(x.get("answer") or ""),
                        "title": str(x.get("title") or ""),
                    }
                    for x in (raw.get("handbook_qa") or [])
                    if isinstance(x, dict)
                ],
            )
        )
    conflicts = data.get("unresolved_conflicts")
    fail_slots = data.get("fail_slots") or []
    rain_mode = str(data.get("rain_mode") or "")
    series_goal = str(data.get("series_goal") or "")
    gemini_final = data.get("gemini_final_slots") or {}
    handbook_qa = data.get("handbook_qa") or []
    return LoopResult(
        slots=slots,
        agreed=bool(data.get("agreed")),
        rounds=rounds,
        unresolved_conflicts=list(conflicts) if isinstance(conflicts, list) else [],
        fail_slots=[str(s) for s in fail_slots if str(s).strip()],
        rain_mode=rain_mode,
        series_goal=series_goal,
        gemini_slots=gemini_final if isinstance(gemini_final, dict) else empty_slots(),
        handbook_qa=[
            {
                "question": str(x.get("question") or ""),
                "answer": str(x.get("answer") or ""),
                "title": str(x.get("title") or ""),
            }
            for x in handbook_qa
            if isinstance(x, dict)
        ],
    )


def empty_slots() -> dict[str, list[str]]:
    return {k: [] for k in SLOT_ORDER}


def _strip_json_fence(text: str) -> str:
    raw = (text or "").strip()
    raw = re.sub(r"^```(?:json)?\s*", "", raw)
    raw = re.sub(r"\s*```$", "", raw)
    return raw


def _parse_slot_value(val) -> list[str]:
    if isinstance(val, str):
        return [a.strip() for a in re.split(r"[+＋|/]", val) if a.strip()]
    if isinstance(val, list):
        return [str(a).strip() for a in val if str(a).strip()]
    if val is None:
        return []
    s = str(val).strip()
    return [s] if s else []


def parse_draft_json(text: str) -> tuple[str, dict[str, list[str]]]:
    """解析含 rain_mode 的六槽 JSON。"""
    raw = _strip_json_fence(text)
    if not raw:
        raise ValueError("空回复，无法解析六槽")
    m = _JSON_BLOCK.search(raw)
    blob = m.group(0) if m else raw
    data = json.loads(blob)
    if not isinstance(data, dict):
        raise ValueError("JSON 根节点不是对象")
    rain_raw = data.get("rain_mode") or data.get("雨档") or data.get("rain")
    rain_mode = normalize_rain_mode(str(rain_raw)) if rain_raw else DEFAULT_RAIN_MODE
    aliases = {
        "主体": "subject",
        "动作": "action",
        "环境": "environment",
        "镜头": "camera",
        "风格": "style",
        "约束": "constraints",
    }
    out = empty_slots()
    for key, val in data.items():
        slot = aliases.get(str(key), str(key))
        if slot not in out:
            continue
        out[slot] = _parse_slot_value(val)
    if not any(out.values()):
        raise ValueError("六槽均为空")
    return rain_mode, out


def parse_slots_json(text: str) -> dict[str, list[str]]:
    """从 Agent/模型回复中解析六槽 JSON（兼容无 rain_mode）。"""
    _rain, slots = parse_draft_json(text)
    return slots


def _handbook_rain_hint(rain_mode: str) -> str:
    mode = normalize_rain_mode(rain_mode)
    label = RAIN_MODE_LABELS[mode]
    briefs = {
        "light_mod": "细密至匀速雨丝；叶片露珠/滚珠；零星小水洼；无明显暴雨幕",
        "heavy": "密集大雨；半透明雨幕；水洼白水花；叶片持续小幅摆动",
        "storm": "超大倾盆暴雨；厚重白雾状雨幕；水面沸腾水花；可有冷白闪电",
    }
    return f"雨档={label}（{mode}）。画面雨感：{briefs.get(mode, label)}"


def build_draft_prompt(
    *,
    rain_mode: str,
    scene_keywords: str = "",
    kind: str = "t2v",
    prior_issues: ReviewResult | None = None,
    prior_slots: dict[str, list[str]] | None = None,
    prior_rain_mode: str = "",
    prior_gemini_slots: dict[str, list[str]] | None = None,
    prior_gemini_rain_mode: str = "",
    prior_comparison: ConsensusComparison | None = None,
) -> str:
    if kind == "i2v":
        lines = [_i2v_draft_system()]
        if prior_slots and prior_issues and prior_issues.verdict == "revise":
            lines.append("按技能修订。只输出JSON。")
            lines.append(f"上稿 rain_mode={prior_rain_mode or '?'}")
            lines.append(format_table(prior_slots))
            lines.append("审核问题:")
            for iss in prior_issues.issues:
                lines.append(f"- [{iss.slot}] {iss.tag}: {iss.problem}")
            for m in prior_issues.missing:
                lines.append(f"- 缺:{m}")
            for d in prior_issues.duplicates:
                lines.append(f"- 重:{d}")
        return "\n".join(lines)

    mode = normalize_rain_mode(rain_mode)
    label = RAIN_MODE_LABELS[mode]
    lines = [
        _DRAFT_SYSTEM.strip(),
        "",
        "管线：文生视频",
        f"雨型：{label}",
        _handbook_rain_hint(mode),
        f"场景关键字：{(scene_keywords or '').strip() or '（无）'}",
        "请扩展关键字，给出六槽原子 JSON。",
    ]
    if prior_slots and prior_issues and prior_issues.verdict == "revise":
        lines.append("")
        lines.append("【上一稿】")
        lines.append(format_table(prior_slots))
        lines.append("【Gemini 审核问题 — 请融合提炼成一份最终文案，标签不重不漏】")
        for iss in prior_issues.issues:
            lines.append(f"- [{iss.slot}] {iss.tag}: {iss.problem}")
        for m in prior_issues.missing:
            lines.append(f"- 缺失: {m}")
        for d in prior_issues.duplicates:
            lines.append(f"- 重复: {d}")
    return "\n".join(lines)


def _guess_mime(path: Path) -> str:
    import mimetypes

    mime, _ = mimetypes.guess_type(path.name)
    return mime or "image/png"


def _load_review_images(paths: Sequence[Path] | None) -> list[tuple[str, bytes]]:
    if not paths:
        return []
    return [(_guess_mime(p), p.read_bytes()) for p in paths if Path(p).is_file()]


def _call_gemini(
    system: str,
    user: str,
    *,
    images: Sequence[Path] | None = None,
    log_fn: LogFn | None = None,
) -> tuple[str, str]:
    from scripts.config.paths import ensure_cli_path

    ensure_cli_path()
    from agy import generate_text_via_agy_accounts, has_agy_credentials
    from agy.client import AGY_IMAGE_LABELS, AGY_PROMPT_LABELS

    if not has_agy_credentials():
        raise RuntimeError("未配置 agy 凭据，无法 Gemini 审核")
    img_payload = _load_review_images(images)
    return generate_text_via_agy_accounts(
        user,
        model=_REVIEW_MODEL,
        effort="medium",
        system=system,
        images=img_payload or None,
        log_fn=log_fn,
        account_labels=AGY_IMAGE_LABELS if img_payload else AGY_PROMPT_LABELS,
    )


def review_slots(
    slots: dict[str, list[str]],
    *,
    rain_mode: str,
    scene_keywords: str = "",
    kind: str = "t2v",
    images: Sequence[Path] | None = None,
    log_fn: LogFn | None = None,
) -> ReviewResult:
    mode = normalize_rain_mode(rain_mode)
    label = RAIN_MODE_LABELS[mode]
    review_images = list(images) if images and kind == "i2v" else None
    if kind == "i2v":
        system = _i2v_review_system()
        rain_line = "雨档以参考图为准；无明显雨默认 heavy"
        vision_hint = (
            "已附参考图：只审核 Jimeng 草稿，不要自己生成六槽。"
            "重点检查重复、歧义、以及 camera/subject 是否针对参考图写了具体异构修改。"
            "对术语搭配有疑问请写入 questions，勿轻易当 duplicates 删掉。"
            if review_images
            else "未附参考图：仅按文案审核（缺少视觉核对）。"
        )
        from scripts.aigc_lab.seedance_handbook import load_handbook_text

        handbook = load_handbook_text(max_chars=4500)
        handbook_block = (
            f"\n【Seedance 手册摘录 — 已有答疑，同类勿重复提问】\n{handbook}\n"
            if handbook
            else "\n【Seedance 手册】尚无条目。\n"
        )
    else:
        system = _REVIEW_SYSTEM
        rain_line = f"雨档：{label}"
        vision_hint = ""
        handbook_block = ""
    user = (
        f"管线：{'图生' if kind == 'i2v' else '文生'}；{rain_line}；"
        f"场景：{scene_keywords or ('（见图）' if kind == 'i2v' else '（无）')}\n"
        f"{vision_hint}\n"
        f"{handbook_block}\n"
        f"Jimeng 草稿 rain_mode={mode}\n"
        f"草稿表格：\n{format_table(slots)}\n\n"
        f"送模拼接预览：\n{compose_prompt(slots)}\n"
    )
    text, email = _call_gemini(system, user, images=review_images, log_fn=log_fn)
    return _parse_review(text, reviewer=email)


def gemini_draft_slots_i2v(
    *,
    scene_keywords: str = "",
    images: Sequence[Path] | None = None,
    log_fn: LogFn | None = None,
) -> tuple[str, dict[str, list[str]], str]:
    """Gemini 独立看图产六槽。"""
    review_images = list(images) if images else None
    user = (
        "管线：图生视频 · 独立观察者\n"
        f"场景：{scene_keywords or '（见图）'}\n"
        "请仅根据参考图与共享规则输出 JSON（含 rain_mode 与六槽）。"
    )
    text, email = _call_gemini(
        _i2v_gemini_draft_system(),
        user,
        images=review_images,
        log_fn=log_fn,
    )
    rain_mode, slots = parse_draft_json(text)
    return rain_mode, slots, text


def compare_slots_semantic_i2v(
    jimeng_rain: str,
    jimeng_slots: dict[str, list[str]],
    gemini_rain: str,
    gemini_slots: dict[str, list[str]],
    *,
    scene_keywords: str = "",
    images: Sequence[Path] | None = None,
    log_fn: LogFn | None = None,
) -> ConsensusComparison:
    user = (
        "管线：图生视频 · 语义对比\n"
        f"场景：{scene_keywords or '（见图）'}\n\n"
        f"Jimeng rain_mode={jimeng_rain}\n{format_table(jimeng_slots)}\n\n"
        f"Gemini rain_mode={gemini_rain}\n{format_table(gemini_slots)}\n"
    )
    text, email = _call_gemini(
        _i2v_compare_system(),
        user,
        images=list(images) if images else None,
        log_fn=log_fn,
    )
    return _parse_comparison(text, reviewer=email)


def _parse_review(text: str, *, reviewer: str = "") -> ReviewResult:
    raw = (text or "").strip()
    m = _JSON_BLOCK.search(raw)
    blob = m.group(0) if m else raw
    try:
        data = json.loads(blob)
    except json.JSONDecodeError:
        return ReviewResult(
            verdict="revise",
            issues=[ReviewIssue(slot="", tag="", problem=f"审核 JSON 解析失败: {raw[:200]}")],
            raw=raw,
            reviewer=reviewer,
        )
    verdict = str(data.get("verdict") or "revise").strip().lower()
    if verdict not in {"pass", "revise"}:
        verdict = "revise"
    issues: list[ReviewIssue] = []
    for item in data.get("issues") or []:
        if not isinstance(item, dict):
            continue
        issues.append(
            ReviewIssue(
                slot=str(item.get("slot") or ""),
                tag=str(item.get("tag") or ""),
                problem=str(item.get("problem") or ""),
            )
        )
    conflicts = []
    for item in data.get("conflict_tags") or []:
        if isinstance(item, dict) and (item.get("tag") or item.get("slot")):
            conflicts.append(
                {"slot": str(item.get("slot") or ""), "tag": str(item.get("tag") or "")}
            )
    questions: list[str] = []
    for q in data.get("questions") or []:
        text_q = str(q).strip() if not isinstance(q, dict) else str(
            q.get("question") or q.get("q") or ""
        ).strip()
        if text_q:
            questions.append(text_q)
    return ReviewResult(
        verdict=verdict,
        issues=issues,
        missing=[str(x) for x in (data.get("missing") or [])],
        duplicates=[str(x) for x in (data.get("duplicates") or [])],
        conflict_tags=conflicts,
        questions=questions,
        raw=raw,
        reviewer=reviewer,
    )


def parse_handbook_answers_json(text: str, *, questions: Sequence[str]) -> list[dict[str, str]]:
    """解析 Jimeng 对手册疑问的答复。"""
    raw = _strip_json_fence(text)
    m = _JSON_BLOCK.search(raw)
    blob = m.group(0) if m else raw
    out: list[dict[str, str]] = []
    try:
        data = json.loads(blob)
    except json.JSONDecodeError:
        # 整段当唯一答复
        if questions and raw.strip():
            return [
                {
                    "question": questions[0],
                    "answer": raw.strip()[:4000],
                    "title": "",
                }
            ]
        return []
    answers = data.get("answers") if isinstance(data, dict) else None
    if isinstance(answers, list):
        for item in answers:
            if not isinstance(item, dict):
                continue
            q = str(item.get("question") or "").strip()
            a = str(item.get("answer") or "").strip()
            title = str(item.get("title") or "").strip()
            if a:
                out.append({"question": q or (questions[0] if questions else ""), "answer": a, "title": title})
    # 按问题顺序补齐缺失
    if questions and len(out) < len(questions):
        answered = {str(x.get("question") or "") for x in out}
        for q in questions:
            if q not in answered and out:
                # 已有答复但 question 字段对不上时，按序配对
                pass
        if len(out) == 1 and len(questions) == 1 and not out[0].get("question"):
            out[0]["question"] = questions[0]
        elif len(out) == len(questions):
            for i, q in enumerate(questions):
                if not out[i].get("question"):
                    out[i]["question"] = q
        elif not out and raw.strip():
            out = [{"question": questions[0], "answer": raw.strip()[:4000], "title": ""}]
    return [x for x in out if x.get("answer") and x.get("question")]


def ask_jimeng_handbook_answers(
    questions: Sequence[str],
    *,
    slots: dict[str, list[str]],
    rain_mode: str = "",
    images: Sequence[Path] | None = None,
    log_fn: LogFn | None = None,
    jimeng_fn: Callable[..., str] | None = None,
) -> list[dict[str, str]]:
    """向 Jimeng Agent 索取 Gemini 疑问的合理解释。"""
    qs = [str(q).strip() for q in questions if str(q).strip()]
    if not qs:
        return []
    ask = jimeng_fn or (
        lambda prompt, imgs: _jimeng_draft(prompt, images=imgs, log_fn=log_fn)
    )
    lines = [
        _HANDBOOK_ANSWER_SYSTEM.strip(),
        "",
        f"当前雨档 rain_mode={rain_mode or '（未标）'}",
        "当前六槽：",
        format_table(slots),
        "",
        "Gemini 疑问（请逐条答复）：",
    ]
    for i, q in enumerate(qs, start=1):
        lines.append(f"{i}. {q}")
    lines.append("")
    lines.append("请只输出 answers JSON。")
    raw = ask("\n".join(lines), list(images) if images else None)
    return parse_handbook_answers_json(raw, questions=qs)


def resolve_and_archive_handbook_qa(
    questions: Sequence[str],
    *,
    slots: dict[str, list[str]],
    rain_mode: str = "",
    images: Sequence[Path] | None = None,
    log_fn: LogFn | None = None,
    jimeng_fn: Callable[..., str] | None = None,
) -> list[dict[str, str]]:
    """提问 → Agent 答复 → 写入 Seedance2.0手册.md；返回本轮新写入条目。"""
    from scripts.aigc_lab.seedance_handbook import append_handbook_entries

    log = log_fn or (lambda _m: None)
    qs = [str(q).strip() for q in questions if str(q).strip()]
    if not qs:
        return []
    log(f"[AgentLoop] Gemini 提出 {len(qs)} 个提示词疑问 · 向 Jimeng 索答…")
    answers = ask_jimeng_handbook_answers(
        qs,
        slots=slots,
        rain_mode=rain_mode,
        images=images,
        log_fn=log_fn,
        jimeng_fn=jimeng_fn,
    )
    if not answers:
        log("[AgentLoop] Jimeng 手册答疑解析为空，跳过存档")
        return []
    written = append_handbook_entries(answers)
    for item in written:
        log(f"[AgentLoop] 已存档手册：{(item.get('title') or item.get('question') or '')[:40]}")
    if len(written) < len(answers):
        log(f"[AgentLoop] 手册答疑 {len(answers)} 条，新写入 {len(written)}（其余已存在）")
    return written



def _parse_comparison(text: str, *, reviewer: str = "") -> ConsensusComparison:
    raw = (text or "").strip()
    m = _JSON_BLOCK.search(raw)
    blob = m.group(0) if m else raw
    try:
        data = json.loads(blob)
    except json.JSONDecodeError:
        return ConsensusComparison(
            agreed=False,
            rain_mode_agreed=False,
            conflicts=[{"slot": "", "reason": f"对比 JSON 解析失败: {raw[:200]}"}],
            raw=raw,
            reviewer=reviewer,
        )
    missing: list[dict] = []
    for item in data.get("missing") or []:
        if isinstance(item, dict):
            missing.append(
                {
                    "slot": str(item.get("slot") or ""),
                    "side": str(item.get("side") or ""),
                    "description": str(item.get("description") or ""),
                }
            )
        else:
            missing.append({"slot": str(item), "side": "gemini", "description": str(item)})
    conflicts = []
    for item in data.get("conflicts") or []:
        if isinstance(item, dict):
            conflicts.append(dict(item))
    contradictions = []
    for item in data.get("contradictions") or []:
        if isinstance(item, dict):
            contradictions.append(dict(item))
    conflict_tags = []
    for item in data.get("conflict_tags") or []:
        if isinstance(item, dict) and (item.get("tag") or item.get("slot")):
            conflict_tags.append(
                {
                    "slot": str(item.get("slot") or ""),
                    "tag": str(item.get("tag") or ""),
                    "side": str(item.get("side") or ""),
                }
            )
    return ConsensusComparison(
        agreed=bool(data.get("agreed")),
        rain_mode_agreed=bool(data.get("rain_mode_agreed", data.get("agreed"))),
        agreements=[str(x) for x in (data.get("agreements") or [])],
        conflicts=conflicts,
        missing=missing,
        duplicates=[str(x) for x in (data.get("duplicates") or [])],
        contradictions=contradictions,
        conflict_tags=conflict_tags,
        raw=raw,
        reviewer=reviewer,
    )


def _jimeng_draft(
    prompt: str,
    *,
    images: Sequence[Path] | None,
    log_fn: LogFn | None,
    new_chat: bool = True,
) -> str:
    """单次打开浏览器对话（兼容旧调用）。多轮请用 JimengAgentSession。"""
    from scripts.config.paths import ensure_cli_path

    ensure_cli_path()
    from jimeng_web.client import JimengWebClient

    return JimengWebClient().agentic_chat(
        prompt,
        images=list(images) if images else None,
        new_chat=new_chat,
        log=log_fn,
    )


def _open_jimeng_session(*, log_fn: LogFn | None):
    from scripts.config.paths import ensure_cli_path

    ensure_cli_path()
    from jimeng_web.agentic import JimengAgentSession

    return JimengAgentSession(log=log_fn)


def _resolve_i2v_rain_mode(parsed: str) -> str:
    return normalize_rain_mode(parsed or _I2V_NO_RAIN_DEFAULT)


def _finalize_loop_result(
    *,
    slots: dict[str, list[str]],
    agreed: bool,
    rounds: list[RoundRecord],
    comparison: ConsensusComparison | None,
    rain_mode: str,
    gemini_slots: dict[str, list[str]],
) -> LoopResult:
    mode = _resolve_i2v_rain_mode(rain_mode)
    goal = series_goal_for_rain_mode(mode)
    conflicts, fail_slots = comparison_to_ui(comparison, slots) if comparison else ([], [])
    return LoopResult(
        slots=slots,
        agreed=agreed,
        rounds=rounds,
        unresolved_conflicts=conflicts,
        fail_slots=fail_slots,
        prompt=compose_prompt(slots),
        rain_mode=mode,
        series_goal=goal,
        gemini_slots=gemini_slots,
    )


def review_result_to_ui(
    review: ReviewResult | None,
    slots: dict[str, list[str]],
) -> tuple[list[dict[str, str]], list[str]]:
    """从 Gemini 审核结果映射 GUI 红框。"""
    if review is None:
        return [], []
    conflicts = [
        {"slot": str(c.get("slot") or ""), "tag": str(c.get("tag") or "")}
        for c in review.conflict_tags
        if str(c.get("tag") or "").strip()
    ]
    if not conflicts:
        for iss in review.issues:
            if iss.tag or iss.slot:
                conflicts.append({"slot": iss.slot, "tag": iss.tag})
    fail_slots: set[str] = set()
    tags_by_slot = {k: set(v) for k, v in slots.items()}
    from scripts.aigc_lab.prompt_atoms import SLOT_LABELS

    label_to_slot = {v: k for k, v in SLOT_LABELS.items()}
    for raw in review.missing:
        text = str(raw).strip()
        if not text:
            continue
        slot = text if text in SLOT_ORDER else label_to_slot.get(text, "")
        if slot not in SLOT_ORDER:
            for sk in SLOT_ORDER:
                if sk in text.lower() or SLOT_LABELS.get(sk, "") in text:
                    slot = sk
                    break
        if slot not in SLOT_ORDER:
            continue
        vague = any(kw in text for kw in ("具体", "异构", "修改", "镜像", "构图", "缺少", "缺失", "未写"))
        if vague and not tags_by_slot.get(slot):
            fail_slots.add(slot)
        elif vague and not any(
            kw in t for t in tags_by_slot.get(slot, set()) for kw in ("镜像", "左", "右", "斜", "近", "远", "特写", "占比")
        ):
            fail_slots.add(slot)
    for iss in review.issues:
        if iss.slot in SLOT_ORDER and not iss.tag.strip():
            prob = iss.problem or ""
            if any(kw in prob for kw in ("具体", "异构", "修改", "镜像", "构图", "模糊", "歧义")):
                fail_slots.add(iss.slot)
    return conflicts, sorted(fail_slots)


def _finalize_i2v_loop_result(
    *,
    slots: dict[str, list[str]],
    agreed: bool,
    rounds: list[RoundRecord],
    review: ReviewResult | None,
    rain_mode: str,
) -> LoopResult:
    mode = _resolve_i2v_rain_mode(rain_mode)
    goal = series_goal_for_rain_mode(mode)
    if agreed:
        conflicts, fail_slots = [], []
    else:
        conflicts, fail_slots = review_result_to_ui(review, slots)
    handbook_qa: list[dict[str, str]] = []
    for r in rounds:
        for item in r.handbook_qa:
            if item not in handbook_qa:
                handbook_qa.append(item)
    return LoopResult(
        slots=slots,
        agreed=agreed,
        rounds=rounds,
        unresolved_conflicts=conflicts,
        fail_slots=fail_slots,
        prompt=compose_prompt(slots),
        rain_mode=mode,
        series_goal=goal,
        gemini_slots={},
        handbook_qa=handbook_qa,
    )


def run_i2v_consensus_loop(
    *,
    scene_keywords: str = "",
    images: Sequence[Path] | None = None,
    max_rounds: int = _MAX_ROUNDS,
    log_fn: LogFn | None = None,
    jimeng_fn: Callable[..., str] | None = None,
    review_fn: Callable[..., ReviewResult] | None = None,
    gemini_draft_fn: Callable[..., tuple[str, dict[str, list[str]], str]] | None = None,
    compare_fn: Callable[..., ConsensusComparison] | None = None,
    handbook_fn: Callable[..., list[dict[str, str]]] | None = None,
) -> LoopResult:
    """图生：Jimeng 出稿 → Gemini VLM 审核 → 疑问由 Agent 答并入手册 → 最多三轮修订。"""
    del gemini_draft_fn, compare_fn  # 保留 API；当前流程不再独立产稿/语义对比
    log = log_fn or (lambda _m: None)
    imgs = list(images) if images else None

    own_session = jimeng_fn is None
    session = _open_jimeng_session(log_fn=log_fn) if own_session else None
    if session is not None:
        session.__enter__()

    def default_ask(prompt: str, chat_imgs) -> str:
        assert session is not None
        return session.chat(prompt, chat_imgs)

    ask_jimeng = jimeng_fn or default_ask
    do_review = review_fn or (
        lambda slots, rain: review_slots(
            slots,
            rain_mode=rain,
            scene_keywords=scene_keywords,
            kind="i2v",
            images=imgs,
            log_fn=log_fn,
        )
    )
    do_handbook = handbook_fn or (
        lambda questions, slots, rain: resolve_and_archive_handbook_qa(
            questions,
            slots=slots,
            rain_mode=rain,
            images=imgs,
            log_fn=log_fn,
            jimeng_fn=ask_jimeng,
        )
    )

    rounds: list[RoundRecord] = []
    jimeng_slots = empty_slots()
    jimeng_rain = _I2V_NO_RAIN_DEFAULT
    jimeng_raw = ""
    last_review: ReviewResult | None = None

    try:
        for i in range(1, max_rounds + 1):
            if i == 1:
                prompt = build_draft_prompt(
                    rain_mode=_I2V_NO_RAIN_DEFAULT,
                    scene_keywords=scene_keywords,
                    kind="i2v",
                )
                source = "jimeng_agent"
            else:
                assert last_review is not None
                prompt = build_draft_prompt(
                    rain_mode=jimeng_rain,
                    scene_keywords=scene_keywords,
                    kind="i2v",
                    prior_issues=last_review,
                    prior_slots=jimeng_slots,
                    prior_rain_mode=jimeng_rain,
                )
                source = "revise"

            log(f"[AgentLoop] 第 {i}/{max_rounds} 轮 · Jimeng 六槽…")
            jimeng_raw = ask_jimeng(prompt, imgs)
            try:
                jimeng_rain, jimeng_slots = parse_draft_json(jimeng_raw)
            except Exception as exc:  # noqa: BLE001
                log(f"[AgentLoop] Jimeng JSON 解析失败，追问：{exc}")
                jimeng_raw = ask_jimeng(
                    "上一条回复无法解析为六槽 JSON。"
                    "请只输出一个 JSON 对象（不要 markdown、不要解释），键必须含："
                    "rain_mode, subject, action, environment, camera, style, constraints；"
                    "各槽值为字符串数组。",
                    None,
                )
                jimeng_rain, jimeng_slots = parse_draft_json(jimeng_raw)
            jimeng_rain = _resolve_i2v_rain_mode(jimeng_rain)

            log(f"[AgentLoop] 第 {i} 轮 · Gemini VLM 审核 Jimeng 稿…")
            last_review = do_review(jimeng_slots, jimeng_rain)
            qa_written: list[dict[str, str]] = []
            if last_review.questions:
                try:
                    qa_written = do_handbook(
                        last_review.questions, jimeng_slots, jimeng_rain
                    )
                except Exception as exc:  # noqa: BLE001
                    log(f"[AgentLoop] 手册答疑失败（不阻断审核）：{exc}")
            review_dict = last_review.to_dict()
            if qa_written:
                review_dict["handbook_qa"] = qa_written
            rounds.append(
                RoundRecord(
                    round=i,
                    source=source,
                    jimeng_slots={k: list(v) for k, v in jimeng_slots.items()},
                    jimeng_rain_mode=jimeng_rain,
                    jimeng_raw=jimeng_raw,
                    review=review_dict,
                    comparison=review_dict,
                    draft_slots={k: list(v) for k, v in jimeng_slots.items()},
                    draft_raw=jimeng_raw,
                    handbook_qa=qa_written,
                )
            )
            if last_review.verdict == "pass":
                log(
                    f"[AgentLoop] 第 {i} 轮审核通过 · rain={jimeng_rain} · "
                    f"目标={series_goal_label(series_goal_for_rain_mode(jimeng_rain))}"
                )
                return _finalize_i2v_loop_result(
                    slots=jimeng_slots,
                    agreed=True,
                    rounds=rounds,
                    review=last_review,
                    rain_mode=jimeng_rain,
                )

        log("[AgentLoop] 3 轮仍未通过，保留 Jimeng 末稿待人工确认")
        return _finalize_i2v_loop_result(
            slots=jimeng_slots,
            agreed=False,
            rounds=rounds,
            review=last_review,
            rain_mode=jimeng_rain,
        )
    finally:
        if session is not None:
            session.__exit__(None, None, None)


def run_t2v_review_loop(
    *,
    rain_mode: str,
    scene_keywords: str = "",
    max_rounds: int = _MAX_ROUNDS,
    log_fn: LogFn | None = None,
    jimeng_fn: Callable[..., str] | None = None,
    review_fn: Callable[..., ReviewResult] | None = None,
) -> LoopResult:
    """文生：Jimeng 出稿 → Gemini 审 → 不通过则回灌 Jimeng。"""
    log = log_fn or (lambda _m: None)

    own_session = jimeng_fn is None
    session = _open_jimeng_session(log_fn=log_fn) if own_session else None
    if session is not None:
        session.__enter__()

    def default_ask(prompt: str, chat_imgs) -> str:
        assert session is not None
        return session.chat(prompt, chat_imgs)

    ask_jimeng = jimeng_fn or default_ask
    do_review = review_fn or (
        lambda slots: review_slots(
            slots,
            rain_mode=rain_mode,
            scene_keywords=scene_keywords,
            kind="t2v",
            log_fn=log_fn,
        )
    )

    rounds: list[RoundRecord] = []
    slots = empty_slots()
    last_review: ReviewResult | None = None

    try:
        for i in range(1, max_rounds + 1):
            if i == 1:
                prompt = build_draft_prompt(
                    rain_mode=rain_mode,
                    scene_keywords=scene_keywords,
                    kind="t2v",
                )
                source = "jimeng_agent"
            else:
                assert last_review is not None
                prompt = build_draft_prompt(
                    rain_mode=rain_mode,
                    scene_keywords=scene_keywords,
                    kind="t2v",
                    prior_issues=last_review,
                    prior_slots=slots,
                )
                source = "revise"

            log(f"[AgentLoop] 第 {i}/{max_rounds} 轮 · Jimeng…")
            raw = ask_jimeng(prompt, None)
            try:
                slots = parse_slots_json(raw)
            except Exception as exc:  # noqa: BLE001
                log(f"[AgentLoop] JSON 解析失败，追问只输出 JSON：{exc}")
                raw2 = ask_jimeng(
                    "上一条回复无法解析为六槽 JSON。"
                    "请只输出一个 JSON 对象（不要 markdown、不要解释），键必须含："
                    "subject, action, environment, camera, style, constraints；"
                    "各槽值为字符串数组。",
                    None,
                )
                slots = parse_slots_json(raw2)
                raw = raw2

            log(f"[AgentLoop] 第 {i} 轮 · Gemini 审核…")
            last_review = do_review(slots)
            rounds.append(
                RoundRecord(
                    round=i,
                    source=source,
                    jimeng_slots={k: list(v) for k, v in slots.items()},
                    draft_slots={k: list(v) for k, v in slots.items()},
                    jimeng_raw=raw,
                    draft_raw=raw,
                    review=last_review.to_dict(),
                    comparison=last_review.to_dict(),
                )
            )
            if last_review.verdict == "pass":
                log(f"[AgentLoop] 第 {i} 轮通过")
                mode = normalize_rain_mode(rain_mode)
                return LoopResult(
                    slots=slots,
                    agreed=True,
                    rounds=rounds,
                    prompt=compose_prompt(slots),
                    rain_mode=mode,
                    series_goal=series_goal_for_rain_mode(mode),
                )

        conflicts = list(last_review.conflict_tags) if last_review else []
        if not conflicts and last_review:
            for iss in last_review.issues:
                if iss.tag or iss.slot:
                    conflicts.append({"slot": iss.slot, "tag": iss.tag})
        log("[AgentLoop] 3 轮仍未达成一致，冲突标签待人工确认")
        mode = normalize_rain_mode(rain_mode)
        return LoopResult(
            slots=slots,
            agreed=False,
            rounds=rounds,
            unresolved_conflicts=conflicts,
            prompt=compose_prompt(slots),
            rain_mode=mode,
            series_goal=series_goal_for_rain_mode(mode),
        )
    finally:
        if session is not None:
            session.__exit__(None, None, None)


def run_agent_review_loop(
    *,
    kind: str,
    rain_mode: str,
    scene_keywords: str = "",
    images: Sequence[Path] | None = None,
    max_rounds: int = _MAX_ROUNDS,
    log_fn: LogFn | None = None,
    jimeng_fn: Callable[..., str] | None = None,
    review_fn: Callable[..., ReviewResult] | None = None,
    gemini_draft_fn: Callable[..., tuple[str, dict[str, list[str]], str]] | None = None,
    compare_fn: Callable[..., ConsensusComparison] | None = None,
) -> LoopResult:
    if kind == "i2v":
        return run_i2v_consensus_loop(
            scene_keywords=scene_keywords or "见图",
            images=images,
            max_rounds=max_rounds,
            log_fn=log_fn,
            jimeng_fn=jimeng_fn,
            review_fn=review_fn,
            gemini_draft_fn=gemini_draft_fn,
            compare_fn=compare_fn,
        )
    return run_t2v_review_loop(
        rain_mode=rain_mode,
        scene_keywords=scene_keywords,
        max_rounds=max_rounds,
        log_fn=log_fn,
        jimeng_fn=jimeng_fn,
        review_fn=review_fn,
    )


def comparison_to_ui(
    comparison: ConsensusComparison | None,
    jimeng_slots: dict[str, list[str]],
) -> tuple[list[dict[str, str]], list[str]]:
    """冲突标签 + 缺失槽位标题红框。"""
    if comparison is None:
        return [], []
    conflicts = [
        {"slot": str(c.get("slot") or ""), "tag": str(c.get("tag") or "")}
        for c in comparison.conflict_tags
        if str(c.get("tag") or "").strip()
    ]
    fail_slots: set[str] = set()
    jimeng_tags_by_slot = {k: set(v) for k, v in jimeng_slots.items()}
    for item in comparison.missing:
        if str(item.get("side") or "").lower() != "gemini":
            continue
        slot = str(item.get("slot") or "")
        if slot not in SLOT_ORDER:
            continue
        tag = str(item.get("tag") or "").strip()
        desc = str(item.get("description") or "").strip()
        mapped = False
        if tag and tag in jimeng_tags_by_slot.get(slot, set()):
            mapped = True
        if not mapped and not jimeng_tags_by_slot.get(slot):
            fail_slots.add(slot)
        elif not mapped and desc and not any(desc in t or t in desc for t in jimeng_tags_by_slot.get(slot, set())):
            fail_slots.add(slot)
    return conflicts, sorted(fail_slots)


def conflict_tag_set(conflicts: Sequence[dict[str, str]]) -> dict[str, set[str]]:
    """slot -> tags 标红集合。无 slot 时按 tag 字面挂到所有槽，由 UI 只点亮实际存在的标签。"""
    out: dict[str, set[str]] = {k: set() for k in SLOT_ORDER}
    orphans: list[str] = []
    for item in conflicts:
        slot = str(item.get("slot") or "")
        tag = str(item.get("tag") or "").strip()
        if not tag:
            continue
        if slot in out:
            out[slot].add(tag)
        else:
            orphans.append(tag)
    for tag in orphans:
        for sk in SLOT_ORDER:
            out[sk].add(tag)
    return out


def slot_labels_zh() -> dict[str, str]:
    from scripts.aigc_lab.prompt_atoms import SLOT_LABELS

    return dict(SLOT_LABELS)
