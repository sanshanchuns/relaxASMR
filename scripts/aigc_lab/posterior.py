"""抽卡视频的后验：客观闸门 → 断言核对 → 人工裁决。

三层的成本与可信度递增：

- 第 0 层｜客观闸门：本地 ffmpeg 抽帧算运动量/闪烁/跳变，零 API 成本，先砍废片。
- 第 1 层｜断言核对：把抽帧连同运动量交给 VLM，逐条判定生成时随 prompt 产出的断言。
- 第 2 层｜人工裁决：抽卡本来就要人看，这一条是真值，也用来量第 1 层的准确率。

结论落在 run 目录的 ``posterior.json``，结构固定，后续可跨 run 聚合成提示词手册。
"""

from __future__ import annotations

import json
import mimetypes
import re
from collections.abc import Callable, Sequence
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path

from scripts.aigc_lab.agent_store import AgentRun
from scripts.aigc_lab.rain_modes import (
    STILL_FLOOR,
    motion_range,
    motion_scale_hint,
    normalize_rain_mode,
    rain_mode as rain_mode_of,
)
from scripts.aigc_lab.video_probe import (
    VideoProbeError,
    extract_review_frames,
    measure_dynamics,
)
from scripts.config.paths import ensure_cli_path

LogFn = Callable[[str], None]

_MODEL = "gemini-3.7-flash"
_JSON_BLOCK = re.compile(r"\{.*\}", re.DOTALL)
_REVIEW_FRAMES = 8

#: 相邻帧整体亮度跳动上限（0–255 刻度）。稳定空镜远低于此值。
FLICKER_MAX = 3.0
#: 最大帧差 / 中位帧差 的上限。超过说明片中多半有硬切。
CUT_RATIO_MAX = 3.0

HUMAN_ADOPT = "adopt"
HUMAN_REJECT = "reject"


class PosteriorError(RuntimeError):
    pass


@dataclass
class AssertionVerdict:
    text: str
    verdict: str  # yes | partial | no
    confidence: float = 0.0
    note: str = ""

    def to_dict(self) -> dict:
        return {
            "text": self.text,
            "verdict": self.verdict,
            "confidence": self.confidence,
            "note": self.note,
        }

    @classmethod
    def from_dict(cls, data: dict) -> AssertionVerdict:
        return cls(
            text=str(data.get("text") or ""),
            verdict=str(data.get("verdict") or "no").lower(),
            confidence=float(data.get("confidence") or 0.0),
            note=str(data.get("note") or ""),
        )


@dataclass
class Gate:
    """第 0 层：纯客观，不花钱。"""

    rain_mode: str = ""
    motion_score: float = 0.0
    flicker: float = 0.0
    cut_ratio: float = 1.0
    ok: bool = True
    issues: list[str] = field(default_factory=list)

    def to_dict(self) -> dict:
        return {
            "rain_mode": self.rain_mode,
            "motion_score": self.motion_score,
            "flicker": self.flicker,
            "cut_ratio": self.cut_ratio,
            "ok": self.ok,
            "issues": list(self.issues),
        }

    @classmethod
    def from_dict(cls, data: dict) -> Gate:
        return cls(
            rain_mode=str(data.get("rain_mode") or ""),
            motion_score=float(data.get("motion_score") or 0.0),
            flicker=float(data.get("flicker") or 0.0),
            cut_ratio=float(data.get("cut_ratio") or 1.0),
            ok=bool(data.get("ok", True)),
            issues=[str(x) for x in (data.get("issues") or [])],
        )

    @property
    def summary(self) -> str:
        state = "通过" if self.ok else "不通过"
        return f"运动 {self.motion_score:.1f} · 闪烁 {self.flicker:.1f} · {state}"


@dataclass
class Posterior:
    gate: Gate = field(default_factory=Gate)
    assertions: list[AssertionVerdict] = field(default_factory=list)
    reviewer: str = ""
    human: str = ""  # "" 未裁决 | adopt | reject
    human_note: str = ""
    checked_at: str = ""

    def to_dict(self) -> dict:
        return {
            "gate": self.gate.to_dict(),
            "assertions": [a.to_dict() for a in self.assertions],
            "reviewer": self.reviewer,
            "human": self.human,
            "human_note": self.human_note,
            "checked_at": self.checked_at,
        }

    @classmethod
    def from_dict(cls, data: dict) -> Posterior:
        return cls(
            gate=Gate.from_dict(data.get("gate") or {}),
            assertions=[
                AssertionVerdict.from_dict(a) for a in (data.get("assertions") or [])
            ],
            reviewer=str(data.get("reviewer") or ""),
            human=str(data.get("human") or ""),
            human_note=str(data.get("human_note") or ""),
            checked_at=str(data.get("checked_at") or ""),
        )

    @property
    def hit_rate(self) -> float:
        """断言命中率：yes 记 1，partial 记 0.5。"""
        if not self.assertions:
            return 0.0
        score = sum(
            1.0 if a.verdict == "yes" else 0.5 if a.verdict == "partial" else 0.0
            for a in self.assertions
        )
        return score / len(self.assertions)

    @property
    def summary(self) -> str:
        parts = [self.gate.summary]
        if self.assertions:
            yes = sum(1 for a in self.assertions if a.verdict == "yes")
            parts.append(f"断言 {yes}/{len(self.assertions)}")
        if self.human:
            parts.append("人工采用" if self.human == HUMAN_ADOPT else "人工废弃")
        return " · ".join(parts)


def _now_iso() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def posterior_path(run: AgentRun) -> Path:
    return run.dir / "posterior.json"


def load_posterior(run: AgentRun) -> Posterior | None:
    path = posterior_path(run)
    if not path.is_file():
        return None
    try:
        return Posterior.from_dict(json.loads(path.read_text(encoding="utf-8")))
    except (OSError, json.JSONDecodeError):
        return None


def save_posterior(run: AgentRun, result: Posterior) -> Path:
    path = posterior_path(run)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(result.to_dict(), ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    return path


def assertions_of(run: AgentRun) -> list[str]:
    raw = (run.meta or {}).get("assertions") or []
    return [str(a).strip() for a in raw if str(a).strip()]


# --- 第 0 层：客观闸门 -------------------------------------------------


def run_gate(video: Path, *, rain_mode: str) -> Gate:
    """本地测量并按雨档判定。不发任何网络请求。"""
    if not Path(video).is_file():
        raise PosteriorError(f"视频不存在：{video}")
    mode = normalize_rain_mode(rain_mode)
    try:
        dyn = measure_dynamics(Path(video))
    except VideoProbeError as exc:
        raise PosteriorError(str(exc)) from exc

    lo, hi = motion_range(mode)
    label = rain_mode_of(mode).display
    issues: list[str] = []
    if dyn.motion_score < STILL_FLOOR:
        issues.append(f"运动量 {dyn.motion_score:.1f} 近乎静止，多半是慢镜头或没下雨")
    elif dyn.motion_score < lo:
        issues.append(f"运动量 {dyn.motion_score:.1f} 低于「{label}」下限 {lo:.0f}，雨强不足")
    elif dyn.motion_score > hi:
        issues.append(f"运动量 {dyn.motion_score:.1f} 高于「{label}」上限 {hi:.0f}，疑似滑档或镜头在动")
    if dyn.flicker > FLICKER_MAX:
        issues.append(f"亮度跳动 {dyn.flicker:.1f} 偏大，画面忽明忽暗")
    if dyn.cut_ratio > CUT_RATIO_MAX:
        issues.append(f"帧差突变比 {dyn.cut_ratio:.1f}，片中疑似有硬切")

    return Gate(
        rain_mode=mode,
        motion_score=dyn.motion_score,
        flicker=dyn.flicker,
        cut_ratio=dyn.cut_ratio,
        ok=not issues,
        issues=issues,
    )


# --- 第 1 层：断言核对 -------------------------------------------------


def _load_images(paths: Sequence[Path]) -> list[tuple[str, bytes]]:
    out: list[tuple[str, bytes]] = []
    for p in paths:
        if not p.is_file():
            continue
        mime, _ = mimetypes.guess_type(p.name)
        out.append((mime or "image/png", p.read_bytes()))
    return out


def _build_check_prompt(
    assertions: Sequence[str],
    *,
    rain_mode: str,
    motion_score: float,
) -> tuple[str, str]:
    label = rain_mode_of(rain_mode).display
    baseline = rain_mode_of(rain_mode).baseline
    system = (
        "你是雨 ASMR 视频的验收员。\n"
        "输入是同一条短视频按时间顺序抽出的多帧，请把它们当作视频的时间轴来读。\n"
        "任务：逐条判定给定断言在这条视频里是否成立。\n"
        "只依据画面与帧间变化判断，不要脑补，不要照抄断言原文当依据。\n"
        f"该片的目标雨档是「{label}」：{baseline}"
    )
    listed = "\n".join(f"{i}. {a}" for i, a in enumerate(assertions, start=1))
    user = (
        f"客观运动量：{motion_score:.1f}。{motion_scale_hint()}\n"
        "运动量很低却声称有密集溅花或剧烈雨势时，相关断言应判 no。\n\n"
        f"待核对断言：\n{listed}\n\n"
        "逐条给出 verdict=yes|partial|no、confidence(0-1)、note(一句画面依据)。\n"
        "yes=画面/时序明确支持；partial=部分支持或证据不足；no=明显不符或缺失。\n\n"
        "只输出一个 JSON（不要 markdown）：\n"
        '{"results": [{"index": 1, "verdict": "yes", "confidence": 0.0, "note": "一句"}]}'
    )
    return system, user


def _parse_verdicts(text: str, assertions: Sequence[str]) -> list[AssertionVerdict]:
    m = _JSON_BLOCK.search(text or "")
    if not m:
        raise PosteriorError(f"VLM 输出里没有 JSON：{(text or '')[:200]}")
    data = json.loads(m.group(0))
    by_index: dict[int, dict] = {}
    for entry in data.get("results") or []:
        if not isinstance(entry, dict):
            continue
        try:
            idx = int(entry.get("index"))
        except (TypeError, ValueError):
            continue
        by_index[idx] = entry

    out: list[AssertionVerdict] = []
    for i, text_i in enumerate(assertions, start=1):
        hit = by_index.get(i)
        if hit is None:
            out.append(
                AssertionVerdict(text=text_i, verdict="no", note="模型未返回该条")
            )
            continue
        out.append(
            AssertionVerdict(
                text=text_i,
                verdict=str(hit.get("verdict") or "no").lower(),
                confidence=float(hit.get("confidence") or 0.0),
                note=str(hit.get("note") or ""),
            )
        )
    return out


def check_assertions(
    video: Path,
    assertions: Sequence[str],
    *,
    rain_mode: str,
    motion_score: float,
    frames_dir: Path | None = None,
    log_fn: LogFn | None = None,
) -> tuple[list[AssertionVerdict], str]:
    """一次 VLM 调用核对全部断言，返回 (判定列表, 审核账号)。"""
    if not assertions:
        return [], ""
    ensure_cli_path()
    from agy import generate_text_via_agy_accounts, has_agy_credentials
    from agy.client import AGY_IMAGE_LABELS

    if not has_agy_credentials():
        raise PosteriorError("未配置 agy 凭据（cli/agy/credentials.json）")

    out_dir = frames_dir or (Path(video).parent / "_frames")
    out_dir.mkdir(parents=True, exist_ok=True)
    try:
        frames = extract_review_frames(Path(video), out_dir, count=_REVIEW_FRAMES)
    except VideoProbeError as exc:
        raise PosteriorError(str(exc)) from exc
    if not frames:
        raise PosteriorError("抽帧失败，无法核对断言")

    system, user = _build_check_prompt(
        assertions, rain_mode=rain_mode, motion_score=motion_score
    )
    text, email = generate_text_via_agy_accounts(
        user,
        model=_MODEL,
        effort="medium",
        system=system,
        images=_load_images(frames) or None,
        log_fn=log_fn,
        account_labels=AGY_IMAGE_LABELS,
    )
    return _parse_verdicts(text, assertions), email


# --- 组装 -------------------------------------------------------------


def run_posterior(
    run: AgentRun,
    *,
    with_vlm: bool = True,
    log_fn: LogFn | None = None,
) -> Posterior:
    """跑第 0 层（必做）与第 1 层（可关），写回 ``posterior.json``。

    人工裁决若已存在则原样保留——重跑机器判定不应抹掉真值。
    """
    log = log_fn or (lambda _m: None)
    video = run.video_path
    if not video.is_file():
        raise PosteriorError(f"视频尚未落盘：{video}")

    mode = normalize_rain_mode((run.meta or {}).get("rain_mode"))
    gate = run_gate(video, rain_mode=mode)
    log(f"[后验] {run.run_id} · {gate.summary}")
    for msg in gate.issues:
        log(f"[后验] {msg}")

    previous = load_posterior(run)
    result = Posterior(
        gate=gate,
        human=previous.human if previous else "",
        human_note=previous.human_note if previous else "",
        checked_at=_now_iso(),
    )

    items = assertions_of(run)
    if with_vlm and items:
        log(f"[后验] 断言核对（{len(items)} 条）…")
        verdicts, email = check_assertions(
            video,
            items,
            rain_mode=mode,
            motion_score=gate.motion_score,
            frames_dir=run.dir / "_frames",
            log_fn=log_fn,
        )
        result.assertions = verdicts
        result.reviewer = email
        yes = sum(1 for v in verdicts if v.verdict == "yes")
        no = sum(1 for v in verdicts if v.verdict == "no")
        log(f"[后验] 断言 yes/no = {yes}/{no} · 命中率 {result.hit_rate:.0%}")
    elif not items:
        log("[后验] 该 run 没有断言，只做客观闸门")

    save_posterior(run, result)
    return result


def set_human_verdict(run: AgentRun, verdict: str, note: str = "") -> Posterior:
    """写入人工裁决；机器判定原样保留。"""
    value = str(verdict or "").strip().lower()
    if value not in (HUMAN_ADOPT, HUMAN_REJECT, ""):
        raise PosteriorError(f"未知裁决：{verdict}")
    result = load_posterior(run) or Posterior(checked_at=_now_iso())
    result.human = value
    result.human_note = str(note or "").strip()
    save_posterior(run, result)
    return result


def machine_human_agreement(results: Sequence[Posterior]) -> tuple[int, int]:
    """机器与人工的一致数 / 已裁决总数。

    机器口径：闸门通过且断言命中率 ≥ 0.6 视为「机器认可」。
    低一致率说明第 1 层结论不能直接拿来指导 prompt。
    """
    agree = 0
    total = 0
    for r in results:
        if r.human not in (HUMAN_ADOPT, HUMAN_REJECT):
            continue
        total += 1
        machine_ok = r.gate.ok and (not r.assertions or r.hit_rate >= 0.6)
        if machine_ok == (r.human == HUMAN_ADOPT):
            agree += 1
    return agree, total
