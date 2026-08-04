"""提示词规范的加载与校验。

规范正文写在 ``instructions/`` 下的两个 markdown 里，每份末尾带一个
``<!-- validator:rules -->`` 标记 + 一段 JSON。本模块在**每次调用模型之前**读取该 JSON
并逐条校验提示词，不通过就抛 :class:`PromptValidationError`，调用方不得继续执行。

这样做的意义是让「必须参考 instructions/」变成硬约束而不是口头约定：
规范文件被删掉或者写坏了，出图/出视频这两条路径会直接停下来，而不是悄悄退化成随便发一段
提示词给模型。想调整规则就改 markdown，不用动代码。

规则字段
--------
``word_count``          ``{"min": n, "max": m}``，按空白切词计数。
``required_sections``   必须出现的段落标签，如 ``"Motion:"``。
``required_all``        每组 ``{"name", "terms"}`` 至少命中一个词，否则算缺失该维度。
``forbidden``           命中即失败。``allow_negated`` 为真时，被 ``no/without/avoid``
                        等否定词修饰的用法放行 —— 例如 ``no people`` 合法而 ``a person``
                        非法，``avoid camera movement`` 合法而 ``camera pans left`` 非法。
``require_qualified``   某个词必须在其后一小段窗口内跟上限定词，用于拦 ``cinematic`` 单用。

子系列覆盖层
------------
频道分「暴雨助眠 / 中雨专注 / 轻雨冥想」三个子系列，规范写在
``instructions/rain_asmr_series.md``。基础规范里有几条是照中雨调的（比如禁 ``storm``），
暴雨系列会被自己的校验器拦下来，所以系列可以对基础规则做三件事：追加 ``required_all``、
追加 ``forbidden``、按组名摘掉基础的组（``drop_forbidden`` / ``drop_required``）。
有效规则 = 基础规则 ⊕ 系列覆盖层，见 :meth:`PromptRules.with_overlay`。
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
INSTRUCTIONS_DIR = REPO_ROOT / "instructions"

IMAGE_RULES_DOC = INSTRUCTIONS_DIR / "rain_asmr_image_prompt.md"
VIDEO_RULES_DOC = INSTRUCTIONS_DIR / "rain_asmr_video_prompt.md"
SERIES_RULES_DOC = INSTRUCTIONS_DIR / "rain_asmr_series.md"

_RULES_MARKER = "<!-- validator:rules -->"
_RULES_BLOCK = re.compile(
    re.escape(_RULES_MARKER) + r"\s*```json\s*(?P<body>.*?)```",
    re.DOTALL,
)

#: 否定词。作用域是「从最近的句子分隔符到命中词之间」，这样
#: ``avoid camera movement, jitter, …, people`` 里排在很后面的 people 也算被否定。
_NEGATION = re.compile(r"\b(no|not|without|avoid|avoiding|exclude|never)\b")
_SENTENCE_BREAK = re.compile(r"[.;:\n]")

#: ``require_qualified`` 往后看的窗口，够放下 "macro realism, cool desaturated film tone"。
_QUALIFIER_WINDOW = 60


class PromptRulesError(RuntimeError):
    """规范文件缺失或格式不对 —— 属于工程问题，不是提示词问题。"""


class PromptValidationError(ValueError):
    """提示词没通过规范校验。``violations`` 是逐条原因。"""

    def __init__(self, doc: Path, violations: list[str]) -> None:
        self.doc = doc
        self.violations = violations
        detail = "\n".join(f"  · {v}" for v in violations)
        try:
            shown = doc.relative_to(REPO_ROOT)
        except ValueError:
            shown = doc
        super().__init__(f"提示词未通过 {shown} 的校验：\n{detail}")


@dataclass(frozen=True)
class PromptRules:
    """一份规范文件解析出来的规则集。"""

    doc: Path
    rule_id: str
    raw: dict

    @property
    def word_count(self) -> tuple[int, int]:
        wc = self.raw.get("word_count") or {}
        return int(wc.get("min", 0)), int(wc.get("max", 10**6))

    def check_items(self, prompt: str) -> list[tuple[str, bool, str]]:
        """逐条规则检查，返回 ``(维度名, 是否通过, 说明)``。

        这是校验与打分的共用底层：``validate`` 只收集失败项，``score`` 按通过比例算分。
        """
        text = prompt or ""
        low = text.lower()
        items: list[tuple[str, bool, str]] = []

        lo, hi = self.word_count
        words = len(text.split())
        ok_wc = lo <= words <= hi
        items.append(
            (
                "词数",
                ok_wc,
                f"{words} 词" if ok_wc else f"词数 {words} 不在 {lo}–{hi} 之间",
            )
        )

        for label in self.raw.get("required_sections") or []:
            ok = label.lower() in low
            items.append(
                (f"段落:{label}", ok, "已包含" if ok else f"缺少段落标签「{label}」")
            )

        for group in self.raw.get("required_all") or []:
            name = str(group.get("name") or "?")
            terms = group.get("terms") or []
            ok = any(_contains(low, t) for t in terms)
            items.append(
                (
                    name,
                    ok,
                    "已命中" if ok else f"缺少维度（需命中其一：{', '.join(terms[:5])}…）",
                )
            )

        for group in self.raw.get("forbidden") or []:
            name = str(group.get("name") or "?")
            allow_negated = bool(group.get("allow_negated"))
            hits = [
                t
                for t in group.get("terms") or []
                if _contains(low, t, skip_negated=allow_negated)
            ]
            ok = not hits
            items.append(
                (
                    f"禁用:{name}",
                    ok,
                    "未出现" if ok else f"出现禁用表述：{', '.join(sorted(set(hits)))}",
                )
            )

        for rule in self.raw.get("require_qualified") or []:
            name = str(rule.get("name") or rule.get("term") or "?")
            term = str(rule.get("term", "")).lower()
            quals = [str(q).lower() for q in rule.get("must_be_followed_by") or []]
            ok = (not term) or _is_qualified(low, term, quals)
            items.append(
                (
                    name,
                    ok,
                    "合格" if ok else f"需要在其后跟上限定词（{', '.join(quals[:4])}…）",
                )
            )

        return items

    def validate(self, prompt: str) -> list[str]:
        """返回违规原因列表；空列表表示通过。"""
        return [msg for _name, ok, msg in self.check_items(prompt) if not ok]

    def score(self, prompt: str) -> tuple[int, list[str]]:
        """按规则通过比例打 0–100 分，并附上未通过项的说明。

        满分 = 全部规则项通过。词数、必填段落、必填维度、禁用项、限定词各占一票，
        权重相同 —— 够用且可解释，不引入主观加权。
        """
        items = self.check_items(prompt)
        if not items:
            return 0, ["无规则可评"]
        passed = sum(1 for _n, ok, _m in items if ok)
        pct = int(round(100.0 * passed / len(items)))
        fails = [msg for _n, ok, msg in items if not ok]
        return pct, fails

    def ensure(self, prompt: str) -> None:
        problems = self.validate(prompt)
        if problems:
            raise PromptValidationError(self.doc, problems)

    def with_overlay(self, overlay: dict, *, label: str = "") -> PromptRules:
        """叠一层子系列覆盖：追加维度 / 追加禁用组 / 按组名摘掉基础的组。

        摘除按**组名**而不是词条：暴雨系列要解禁基础规范里整组「会破坏 loop 的剧烈天气」，
        然后自己补一组只禁 hurricane / lightning —— 这样共性仍然只写一遍。
        """
        if not overlay:
            return self
        raw = dict(self.raw)
        if overlay.get("word_count"):
            raw["word_count"] = overlay["word_count"]
        raw["required_sections"] = list(self.raw.get("required_sections") or []) + list(
            overlay.get("required_sections") or []
        )
        raw["required_all"] = _merge_groups(
            self.raw.get("required_all"),
            overlay.get("required_all"),
            overlay.get("drop_required"),
        )
        raw["forbidden"] = _merge_groups(
            self.raw.get("forbidden"),
            overlay.get("forbidden"),
            overlay.get("drop_forbidden"),
        )
        raw["require_qualified"] = list(self.raw.get("require_qualified") or []) + list(
            overlay.get("require_qualified") or []
        )
        rule_id = f"{self.rule_id}+{label}" if label else self.rule_id
        return PromptRules(doc=self.doc, rule_id=rule_id, raw=raw)


def _merge_groups(base: list | None, extra: list | None, drop: list | None) -> list:
    dropped = {str(name) for name in (drop or [])}
    kept = [g for g in (base or []) if str(g.get("name")) not in dropped]
    return kept + list(extra or [])


def _contains(low: str, term: str, *, skip_negated: bool = False) -> bool:
    """*term* 是否出现在 *low* 里；``skip_negated`` 时忽略被否定的那些命中。"""
    term = term.lower()
    pattern = _term_pattern(term)
    for m in re.finditer(pattern, low):
        if skip_negated and _is_negated(low, m.start()):
            continue
        return True
    return False


def _term_pattern(term: str) -> str:
    """词条 → 正则。

    末尾带空格的词条（如 ``"no "``）按原样匹配；其余走词边界，避免 ``pan`` 命中 ``expand``。
    单个纯字母词额外容忍常见词形变化，这样 ``pan`` 能拦住 ``pans`` / ``panning``。
    """
    if term != term.strip():
        return re.escape(term)
    body = rf"\b{re.escape(term)}"
    if term.isalpha():
        body += r"(?:s|es|ed|ing)?"
    return body + r"\b"


def _is_negated(low: str, pos: int) -> bool:
    """*pos* 处的命中是否落在一句否定表述里。

    只回看到最近的句子分隔符，避免上一句的 ``avoid`` 把下一句的用法也一并赦免。
    """
    breaks = [m.end() for m in _SENTENCE_BREAK.finditer(low, 0, pos)]
    start = breaks[-1] if breaks else 0
    return bool(_NEGATION.search(low, start, pos))


def _is_qualified(low: str, term: str, qualifiers: list[str]) -> bool:
    """*term* 每一次出现，后面窗口内都得跟上至少一个限定词。

    压根没出现也算通过：这条规则只管「出现了就必须带限定」。
    """
    for m in re.finditer(rf"\b{re.escape(term)}\b", low):
        window = low[m.end() : m.end() + _QUALIFIER_WINDOW]
        if not any(q in window for q in qualifiers):
            return False
    return True


def _parse_rules(doc: Path) -> PromptRules:
    if not doc.is_file():
        raise PromptRulesError(
            f"提示词规范缺失：{doc}。生成前必须参考 instructions/ 下的规范，请先恢复该文件。"
        )
    text = doc.read_text(encoding="utf-8")
    m = _RULES_BLOCK.search(text)
    if not m:
        raise PromptRulesError(f"{doc} 里找不到 `{_RULES_MARKER}` 后面的 json 规则块")
    try:
        raw = json.loads(m.group("body"))
    except json.JSONDecodeError as exc:
        raise PromptRulesError(f"{doc} 的规则块不是合法 JSON：{exc}") from exc
    if not isinstance(raw, dict):
        raise PromptRulesError(f"{doc} 的规则块必须是 JSON 对象")
    return PromptRules(doc=doc, rule_id=str(raw.get("id") or doc.stem), raw=raw)


@lru_cache(maxsize=4)
def _cached_rules(doc_str: str, mtime: float) -> PromptRules:
    return _parse_rules(Path(doc_str))


def load_rules(doc: Path) -> PromptRules:
    """读取并缓存规则；文件改动后（mtime 变化）自动重新解析。"""
    if not doc.is_file():
        raise PromptRulesError(
            f"提示词规范缺失：{doc}。生成前必须参考 instructions/ 下的规范，请先恢复该文件。"
        )
    return _cached_rules(str(doc), doc.stat().st_mtime)


def series_catalog() -> dict:
    """``rain_asmr_series.md`` 里的三系列定义（原始 JSON）。"""
    return load_rules(SERIES_RULES_DOC).raw


def series_overlay(series_id: str, kind: str) -> dict:
    """取某系列对 ``kind``（``image`` / ``video``）规则的覆盖层；找不到返回空。"""
    if not series_id:
        return {}
    for entry in series_catalog().get("series") or []:
        if str(entry.get("id")) == series_id:
            return (entry.get("prompt_overlay") or {}).get(kind) or {}
    raise PromptRulesError(
        f"未知子系列 {series_id!r}；可选：{', '.join(series_ids())}"
    )


def series_ids() -> list[str]:
    return [str(e.get("id")) for e in series_catalog().get("series") or []]


@lru_cache(maxsize=16)
def _composed(doc_str: str, kind: str, series_id: str, _stamp: tuple) -> PromptRules:
    base = load_rules(Path(doc_str))
    return base.with_overlay(series_overlay(series_id, kind), label=series_id)


def _rules_for(doc: Path, kind: str, series_id: str) -> PromptRules:
    if not series_id:
        return load_rules(doc)
    # 两份文件任意一份改动都要重新组合，所以 mtime 一起进缓存 key。
    stamp = (doc.stat().st_mtime, SERIES_RULES_DOC.stat().st_mtime)
    return _composed(str(doc), kind, series_id, stamp)


def image_rules(series_id: str = "") -> PromptRules:
    return _rules_for(IMAGE_RULES_DOC, "image", series_id)


def video_rules(series_id: str = "") -> PromptRules:
    return _rules_for(VIDEO_RULES_DOC, "video", series_id)


def validate_image_prompt(prompt: str, series_id: str = "") -> list[str]:
    return image_rules(series_id).validate(prompt)


def validate_video_prompt(prompt: str, series_id: str = "") -> list[str]:
    return video_rules(series_id).validate(prompt)


def ensure_image_prompt(prompt: str, series_id: str = "") -> None:
    """出图前的闸门：不通过直接抛 :class:`PromptValidationError`。"""
    image_rules(series_id).ensure(prompt)


def ensure_video_prompt(prompt: str, series_id: str = "") -> None:
    """提交视频任务前的闸门：不通过直接抛 :class:`PromptValidationError`。"""
    video_rules(series_id).ensure(prompt)


def score_image_prompt(prompt: str, series_id: str = "") -> int:
    """图生图 / 文生图提示词得分（0–100）。空串返回 0。"""
    if not (prompt or "").strip():
        return 0
    return image_rules(series_id).score(prompt)[0]


def score_video_prompt(prompt: str, series_id: str = "") -> int:
    """图生视频提示词得分（0–100）。空串返回 0。"""
    if not (prompt or "").strip():
        return 0
    return video_rules(series_id).score(prompt)[0]
