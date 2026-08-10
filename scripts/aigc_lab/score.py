"""L1 画面标签核对 + L2 动作标签核对（agy · gemini-3.6-flash）。

L1：主体 / 环境 — 与抽帧画面是否匹配  
L2：动作 — 与视频动作（多帧时序 + 运动量）是否匹配  

粒度：逐标签 yes|partial|no，不是整槽一条。
"""

from __future__ import annotations

import json
import mimetypes
import re
from collections.abc import Callable, Sequence
from dataclasses import dataclass, field
from pathlib import Path

from scripts.aigc_lab.store import T2vRun, load_run
from scripts.config.paths import ensure_cli_path
from scripts.series_video.video_probe import (
    VideoProbeError,
    extract_review_frames,
    measure_motion,
    probe_video,
)

LogFn = Callable[[str], None]

_REVIEW_MODEL = "gemini-3.6-flash"
_JSON_BLOCK = re.compile(r"\{.*\}", re.DOTALL)

# 仅检查会随单次生成内容变化的开放槽。
# 镜头 / 风格 / 约束是产品固定项，不参与 VLM 验收或可疑红框。
_L1_SLOTS: tuple[str, ...] = (
    "subject",
    "environment",
)
_L2_SLOTS: tuple[str, ...] = ("action",)
_L2_FRAME_COUNT = 8

# 粗标定：真实素材区间（见 CONTEXT / video_probe）
_MOTION_HEAVY_LO = 14.0
_MOTION_LIGHT_HI = 6.0


class ScoreError(RuntimeError):
    pass


@dataclass
class TagScore:
    tag: str
    verdict: str  # yes | partial | no
    confidence: float = 0.0
    note: str = ""

    def to_dict(self) -> dict:
        return {
            "tag": self.tag,
            "verdict": self.verdict,
            "confidence": self.confidence,
            "note": self.note,
        }


@dataclass
class LayerScore:
    """一层评分：slot → 该槽标签列表。"""

    layer: str  # visual | motion
    slots: dict[str, list[TagScore]] = field(default_factory=dict)
    reviewer: str = ""

    def to_dict(self) -> dict:
        return {
            "layer": self.layer,
            "reviewer": self.reviewer,
            "slots": {
                sid: [t.to_dict() for t in tags] for sid, tags in self.slots.items()
            },
        }


@dataclass
class RunScore:
    motion_score: float = 0.0
    motion_ok: bool = True
    motion_issues: list[str] = field(default_factory=list)
    l1: LayerScore = field(default_factory=lambda: LayerScore(layer="visual"))
    l2: LayerScore = field(default_factory=lambda: LayerScore(layer="motion"))
    needs_human: bool = False
    dispute_reasons: list[str] = field(default_factory=list)
    reviewer: str = ""
    source: str = "auto"
    rain_mode: str = ""

    def to_dict(self) -> dict:
        return {
            "rain_mode": self.rain_mode,
            "motion_score": self.motion_score,
            "motion_ok": self.motion_ok,
            "motion_issues": list(self.motion_issues),
            "l1": self.l1.to_dict(),
            "l2": self.l2.to_dict(),
            "needs_human": self.needs_human,
            "dispute_reasons": list(self.dispute_reasons),
            "reviewer": self.reviewer,
            "source": self.source,
        }


def _guess_mime(path: Path) -> str:
    mime, _ = mimetypes.guess_type(path.name)
    return mime or "image/png"


def _load_images(paths: Sequence[Path]) -> list[tuple[str, bytes]]:
    return [(_guess_mime(p), p.read_bytes()) for p in paths if p.is_file()]


def _ask_vlm(
    system: str,
    user: str,
    frames: Sequence[Path],
    *,
    log_fn: LogFn | None = None,
) -> tuple[str, str]:
    ensure_cli_path()
    from agy import generate_text_via_agy_accounts, has_agy_credentials
    from agy.client import AGY_IMAGE_LABELS

    if not has_agy_credentials():
        raise ScoreError("未配置 agy 凭据（cli/agy/credentials.json）")
    return generate_text_via_agy_accounts(
        user,
        model=_REVIEW_MODEL,
        effort="medium",
        system=system,
        images=_load_images(frames) or None,
        log_fn=log_fn,
        account_labels=AGY_IMAGE_LABELS,
    )


def _parse_json(text: str) -> dict:
    m = _JSON_BLOCK.search(text or "")
    if not m:
        raise ScoreError(f"VLM 输出里没有 JSON：{(text or '')[:200]}")
    return json.loads(m.group(0))


def _slots_from_run(run: T2vRun) -> dict[str, list[str]]:
    from scripts.aigc_lab.store import slots_from_run

    return slots_from_run(run)


def _format_tag_list(slots: dict[str, list[str]], keys: Sequence[str]) -> str:
    from scripts.aigc_lab.prompt_atoms import SLOT_LABELS

    lines: list[str] = []
    for key in keys:
        tags = slots.get(key) or []
        label = SLOT_LABELS.get(key, key)
        if not tags:
            lines.append(f"【{label} / {key}】（空）")
            continue
        lines.append(f"【{label} / {key}】")
        for i, tag in enumerate(tags, start=1):
            lines.append(f'  {i}. "{tag}"')
    return "\n".join(lines)


def _build_l1_prompt(
    slots: dict[str, list[str]],
    *,
    rain_mode: str,
) -> tuple[str, str]:
    from scripts.aigc_lab.prompt_atoms import RAIN_MODE_LABELS

    label = RAIN_MODE_LABELS.get(rain_mode, rain_mode)
    system = (
        "你是雨 ASMR 文生视频的「画面验收员」。\n"
        "输入：同一条短视频按时间顺序抽出的静帧。\n"
        "任务：逐条核对【主体 / 环境】标签是否在画面中可见/成立。\n"
        "只根据画面证据判断，不要编造。\n"
        f"目标雨档「{label}」仅作氛围参考；L1 不评动作强度。\n"
        "镜头、风格、约束为产品固定项，不在本次验收范围内。"
    )
    user = (
        "请对下列每个标签给出 verdict=yes|partial|no、confidence(0-1)、note(一句依据)。\n"
        "yes=画面明确支持；partial=部分支持或证据不足；no=画面明显不符或缺失。\n\n"
        f"{_format_tag_list(slots, _L1_SLOTS)}\n\n"
        "只输出一个 JSON（不要 markdown）：\n"
        '{"tags": [{"slot":"subject","tag":"原文","verdict":"yes|partial|no",'
        '"confidence":0.0,"note":"一句"}], "needs_human": false, "dispute_reasons": []}'
    )
    return system, user


def _build_l2_prompt(
    slots: dict[str, list[str]],
    *,
    rain_mode: str,
    motion_score: float,
) -> tuple[str, str]:
    from scripts.aigc_lab.prompt_atoms import RAIN_MODE_LABELS, rain_mode_brief

    label = RAIN_MODE_LABELS.get(rain_mode, rain_mode)
    system = (
        "你是雨 ASMR 文生视频的「动作验收员」。\n"
        "输入：同一条短视频按时间顺序抽出的多帧（把它们当作视频时间轴）+ 客观运动量。\n"
        "任务：逐条核对【动作】标签是否与视频动作匹配。\n"
        "关注：雨滴/溅花/叶动/径流/雨幕是否随时间变化。\n"
        f"目标雨档「{label}」——动作强度须匹配该档，滑档 → no。\n"
        "镜头、风格、约束为产品固定项，不在本次验收范围内。"
    )
    user = (
        f"客观运动量（帧差 0–100）：{motion_score:.1f}。"
        "参考：无雨空镜 0.5–1.3，轻雨 2.7–5.1，中雨 8–12，大雨 16.8–19.1。\n"
        "运动量极低却声称暴雨溅水/剧烈颤动 → 动作标签倾向 no。\n\n"
        f"{rain_mode_brief(rain_mode)}\n\n"
        "请对下列每个标签给出 verdict=yes|partial|no、confidence(0-1)、note(一句依据)。\n"
        "yes=时序/运动明确支持；partial=部分支持；no=不符或几乎静止。\n\n"
        f"{_format_tag_list(slots, _L2_SLOTS)}\n\n"
        "只输出一个 JSON（不要 markdown）：\n"
        '{"tags": [{"slot":"action","tag":"原文","verdict":"yes|partial|no",'
        '"confidence":0.0,"note":"一句"}], "needs_human": false, "dispute_reasons": []}'
    )
    return system, user


def _parse_tag_scores(
    data: dict,
    *,
    expected: dict[str, list[str]],
) -> dict[str, list[TagScore]]:
    """把 VLM 输出对齐到期望标签列表（按原文匹配，漏了补 no）。"""
    out: dict[str, list[TagScore]] = {k: [] for k in expected}
    by_slot_tag: dict[tuple[str, str], TagScore] = {}
    for entry in data.get("tags") or []:
        if not isinstance(entry, dict):
            continue
        slot = str(entry.get("slot") or "").strip()
        tag = str(entry.get("tag") or "").strip()
        if not slot or not tag:
            continue
        by_slot_tag[(slot, tag)] = TagScore(
            tag=tag,
            verdict=str(entry.get("verdict") or "no").lower(),
            confidence=float(entry.get("confidence") or 0.0),
            note=str(entry.get("note") or ""),
        )

    for slot, tags in expected.items():
        for tag in tags:
            hit = by_slot_tag.get((slot, tag))
            if hit is None:
                # 模糊：同槽内 tag 子串匹配
                for (s, t), sc in by_slot_tag.items():
                    if s == slot and (tag in t or t in tag):
                        hit = TagScore(
                            tag=tag,
                            verdict=sc.verdict,
                            confidence=sc.confidence,
                            note=sc.note,
                        )
                        break
            if hit is None:
                hit = TagScore(
                    tag=tag,
                    verdict="no",
                    confidence=0.0,
                    note="模型未返回该标签",
                )
            out[slot].append(hit)
    return out


def _score_layer(
    *,
    layer: str,
    system: str,
    user: str,
    frames: Sequence[Path],
    expected: dict[str, list[str]],
    log_fn: LogFn | None,
) -> LayerScore:
    log = log_fn or (lambda _m: None)
    log(f"[AIGC] {layer} 评分中（{sum(len(v) for v in expected.values())} 个标签）…")
    text, email = _ask_vlm(system, user, frames, log_fn=log_fn)
    data = _parse_json(text)
    slots = _parse_tag_scores(data, expected=expected)
    return LayerScore(layer=layer, slots=slots, reviewer=email)


def _route_disputes(result: RunScore, *, rain_mode: str) -> None:
    reasons: list[str] = []
    critical_slots = {"subject", "environment", "action"}

    def walk(layer: LayerScore, prefix: str) -> None:
        for slot, tags in layer.slots.items():
            for sc in tags:
                short = sc.tag if len(sc.tag) <= 18 else sc.tag[:16] + "…"
                key = f"{prefix}.{slot}:{short}"
                if sc.verdict in ("partial", "no") and slot in critical_slots:
                    if sc.confidence < 0.75 and sc.verdict == "partial":
                        reasons.append(f"{key} 低置信 {sc.confidence:.2f}")
                    else:
                        reasons.append(f"{key}={sc.verdict}")
                elif sc.confidence < 0.55:
                    reasons.append(f"{key} 置信过低 {sc.confidence:.2f}")

    walk(result.l1, "L1")
    walk(result.l2, "L2")

    action_tags = result.l2.slots.get("action") or []
    action_yes = [t for t in action_tags if t.verdict == "yes"]
    action_no = [t for t in action_tags if t.verdict == "no"]
    if rain_mode in ("heavy", "storm") and action_yes:
        if result.motion_score < _MOTION_LIGHT_HI:
            reasons.append(
                f"动作有 yes 但运动量 {result.motion_score:.1f} 偏低（疑似慢镜头/薄雨）"
            )
    if rain_mode == "light_mod" and action_yes:
        if result.motion_score >= _MOTION_HEAVY_LO:
            reasons.append(
                f"小/中雨档但运动量 {result.motion_score:.1f} 偏高（疑似滑档）"
            )
    if rain_mode == "storm" and action_no and result.motion_score >= _MOTION_HEAVY_LO:
        reasons.append(
            f"暴雨动作多 no 但运动量 {result.motion_score:.1f} 偏高（模型可能误判）"
        )

    if not result.motion_ok:
        reasons.append("运动量闸门未过")

    # 去重保序
    seen: set[str] = set()
    uniq: list[str] = []
    for r in reasons:
        if r not in seen:
            seen.add(r)
            uniq.append(r)
    result.dispute_reasons = uniq
    result.needs_human = bool(uniq)


def score_run(
    run_id: str | T2vRun,
    *,
    log_fn: LogFn | None = None,
) -> RunScore:
    """对一条 run 跑 L1（画面标签）+ L2（动作标签），写回 ``scores.json``。"""
    log = log_fn or (lambda _m: None)
    run = run if isinstance(run_id, T2vRun) else load_run(str(run_id))
    if not run.video_path.is_file():
        raise ScoreError(f"视频尚未落盘：{run.video_path}")

    from scripts.aigc_lab.prompt_atoms import DEFAULT_RAIN_MODE, normalize_rain_mode

    rain_mode = normalize_rain_mode(
        str((run.meta or {}).get("rain_mode") or DEFAULT_RAIN_MODE)
    )
    slots = _slots_from_run(run)
    frames_dir = run.dir / "_frames"
    try:
        probe = probe_video(
            run.video_path,
            motion_range=(0.0, 100.0),
            frames_dir=frames_dir,
            log_fn=log,
        )
    except VideoProbeError as exc:
        raise ScoreError(str(exc)) from exc

    result = RunScore(
        motion_score=probe.motion_score,
        motion_ok=probe.ok,
        motion_issues=list(probe.issues),
        rain_mode=rain_mode,
    )

    l1_expected = {k: list(slots.get(k) or []) for k in _L1_SLOTS}
    l2_expected = {k: list(slots.get(k) or []) for k in _L2_SLOTS}

    if not any(l1_expected.values()) and not any(l2_expected.values()):
        raise ScoreError("run 无可用标签（meta.slots / prompt_table 为空）")

    # L1：画面 — 用均匀抽帧
    if any(l1_expected.values()):
        try:
            system, user = _build_l1_prompt(slots, rain_mode=rain_mode)
            result.l1 = _score_layer(
                layer="visual",
                system=system,
                user=user,
                frames=probe.frames,
                expected=l1_expected,
                log_fn=log_fn,
            )
        except Exception as exc:
            raise ScoreError(f"L1 画面标签核对失败：{exc}") from exc

    # L2：动作 — 更密抽帧 + 运动量
    if any(l2_expected.values()):
        try:
            motion_frames_dir = run.dir / "_frames_motion"
            motion_frames_dir.mkdir(parents=True, exist_ok=True)
            motion_frames = extract_review_frames(
                run.video_path, motion_frames_dir, count=_L2_FRAME_COUNT
            )
            if not motion_frames:
                motion_frames = probe.frames
            # 若 probe 未测到，补测一次
            motion = result.motion_score
            if motion <= 0:
                try:
                    motion = measure_motion(run.video_path)
                    result.motion_score = motion
                except VideoProbeError:
                    pass
            system, user = _build_l2_prompt(
                slots, rain_mode=rain_mode, motion_score=motion
            )
            result.l2 = _score_layer(
                layer="motion",
                system=system,
                user=user,
                frames=motion_frames,
                expected=l2_expected,
                log_fn=log_fn,
            )
        except Exception as exc:
            raise ScoreError(f"L2 动作标签核对失败：{exc}") from exc

    reviewers = [r for r in (result.l1.reviewer, result.l2.reviewer) if r]
    result.reviewer = " + ".join(dict.fromkeys(reviewers)) or ""
    _route_disputes(result, rain_mode=rain_mode)

    run.save_scores(result.to_dict())

    def _count(layer: LayerScore) -> tuple[int, int, int]:
        y = p = n = 0
        for tags in layer.slots.values():
            for t in tags:
                if t.verdict == "yes":
                    y += 1
                elif t.verdict == "partial":
                    p += 1
                else:
                    n += 1
        return y, p, n

    y1, p1, n1 = _count(result.l1)
    y2, p2, n2 = _count(result.l2)
    log(
        f"[AIGC] {run.run_id} · 运动 {result.motion_score:.1f} · "
        f"L1画面 yes/partial/no={y1}/{p1}/{n1} · "
        f"L2动作 yes/partial/no={y2}/{p2}/{n2} · "
        f"{'待人审' if result.needs_human else '自动通过'}"
    )
    return result
