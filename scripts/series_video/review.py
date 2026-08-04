"""Gemini 评审层：程序校验兜不住的那一半。

``prompt_rules`` 查的是「有没有写这个词」，查不了「写得对不对」—— 一条把所有必填词都塞
齐、语义却完全跑偏的提示词照样全绿。图片和视频产物更是程序完全看不懂。所以每一步都是
两道闸门：

1. **程序校验**（``prompt_rules`` / ``video_probe``）：免费、确定性、可写进测试，先跑；
2. **Gemini 评审**（本模块）：花钱，只在第一道过了之后跑。

评审是**硬闸门**：agy 调用失败或输出无法解析时直接抛 :class:`ReviewError`，
不降级、不跳过 —— 继续往下走只会浪费生视频的 token。
产物判定不合格（``reject`` / ``revise``）仍然只标记，不删文件。

四个入口对应流程里的四个卡点：

* :func:`classify_seed_image`  种子图属于哪个子系列（可判「都不适合」）
* :func:`review_prompt`        提示词的语义与意图是否一致
* :func:`review_image`         系列图产物是否守住了本系列意图（含高速静帧风险）
* :func:`gate_still_for_video` 出视频前再拦一次：高速摄影静帧 → 不提交即梦
* :func:`review_video_frames`  视频抽帧是否守住意图（配合 ``video_probe`` 的客观运动量）
"""

from __future__ import annotations

import json
import mimetypes
import re
from collections.abc import Callable, Sequence
from dataclasses import dataclass, field
from pathlib import Path

from scripts.series_video.prompt_rules import (
    IMAGE_RULES_DOC,
    SERIES_RULES_DOC,
    VIDEO_RULES_DOC,
)
from scripts.series_video.series import SeriesSpec, get_series, list_series

LogFn = Callable[[str], None]

_RULES_MARKER = "<!-- validator:rules -->"
_JSON_BLOCK = re.compile(r"\{.*\}", re.DOTALL)

VERDICT_PASS = "pass"
VERDICT_REVISE = "revise"
VERDICT_REJECT = "reject"


class ReviewError(RuntimeError):
    """Gemini 评审调用失败或输出无法解析 —— 必须停下，不能继续生视频。"""

#: 评审用轻量模型：这一步只做判断不做创作，flash 足够，也便宜。
_REVIEW_MODEL = "gemini-3.6-flash"


@dataclass
class Review:
    """一次评审的结论。"""

    verdict: str = VERDICT_REJECT
    score: int = 0
    series_id: str = ""
    issues: list[str] = field(default_factory=list)
    fix: str = ""
    reviewer: str = ""
    raw: str = field(default="", repr=False)
    #: 种子图分析：景别 / 雨击打对象 / 构图摘要（仅 ``classify_seed_image`` 填充）
    shot_scale: str = ""
    rain_subjects: list[str] = field(default_factory=list)
    composition: str = ""

    @property
    def ok(self) -> bool:
        return self.verdict == VERDICT_PASS

    @property
    def blocked(self) -> bool:
        """产物判定不合格，需要调整 prompt 或重新生成。"""
        return self.verdict in (VERDICT_REVISE, VERDICT_REJECT)

    @property
    def summary(self) -> str:
        head = {
            VERDICT_PASS: "通过",
            VERDICT_REVISE: "需调整",
            VERDICT_REJECT: "不合格",
        }.get(self.verdict, self.verdict)
        detail = f"：{'；'.join(self.issues)}" if self.issues else ""
        return f"{head}（{self.score}/100）{detail}"

    def to_dict(self) -> dict:
        return {
            "verdict": self.verdict,
            "score": self.score,
            "series_id": self.series_id,
            "issues": list(self.issues),
            "fix": self.fix,
            "reviewer": self.reviewer,
            "shot_scale": self.shot_scale,
            "rain_subjects": list(self.rain_subjects),
            "composition": self.composition,
        }

    @classmethod
    def from_dict(cls, data: dict | None) -> Review:
        data = data or {}
        return cls(
            verdict=str(data.get("verdict") or VERDICT_REJECT),
            score=int(data.get("score") or 0),
            series_id=str(data.get("series_id") or ""),
            issues=[str(x) for x in data.get("issues") or []],
            fix=str(data.get("fix") or ""),
            reviewer=str(data.get("reviewer") or ""),
            shot_scale=str(data.get("shot_scale") or ""),
            rain_subjects=[str(x) for x in data.get("rain_subjects") or []],
            composition=str(data.get("composition") or ""),
        )


# --------------------------------------------------------------- 规范正文


def _doc_body(doc: Path) -> str:
    """取规范正文（机器规则块之前的部分）—— 那才是写给人和模型看的。"""
    text = doc.read_text(encoding="utf-8")
    if _RULES_MARKER in text:
        return text.split(_RULES_MARKER, 1)[0].strip()
    return text.strip()


def _series_brief(spec: SeriesSpec) -> str:
    return (
        f"子系列：{spec.label}（{spec.id}）\n"
        f"意图：{spec.intent}\n"
        f"评审标准：{spec.review_rubric}"
    )


_OUTPUT_CONTRACT = """只输出一个 JSON 对象，不要 markdown 代码块，不要任何解释文字：
{"verdict": "pass|revise|reject", "score": 0-100, "issues": ["具体问题，指出画面/文字证据"], "fix": "如果 verdict 是 revise，这里给出改好的完整提示词；否则留空"}
issues 用中文，要具体到看见了什么，不要写「不够好」这种没有信息量的话。"""


# --------------------------------------------------------------- Gemini


def _guess_mime(path: Path) -> str:
    mime, _ = mimetypes.guess_type(path.name)
    return mime or "image/png"


def _load_images(paths: Sequence[Path]) -> list[tuple[str, bytes]]:
    return [(_guess_mime(p), p.read_bytes()) for p in paths if p.is_file()]


def _ask(
    system: str,
    user: str,
    images: Sequence[Path] = (),
    *,
    account_labels: Sequence[str] | None = None,
    log_fn: LogFn | None = None,
) -> tuple[str, str]:
    from scripts.config.paths import ensure_cli_path

    ensure_cli_path()
    from agy import generate_text_via_agy_accounts, has_agy_credentials
    from agy.client import AGY_IMAGE_LABELS, AGY_PROMPT_LABELS

    if not has_agy_credentials():
        raise RuntimeError("未配置 agy 凭据（cli/agy/credentials.json），无法评审")
    labels = account_labels
    if labels is None:
        labels = AGY_IMAGE_LABELS if images else AGY_PROMPT_LABELS
    return generate_text_via_agy_accounts(
        user,
        model=_REVIEW_MODEL,
        effort="medium",
        system=system,
        images=_load_images(images) or None,
        log_fn=log_fn,
        account_labels=labels,
    )


def _parse(text: str) -> dict:
    """从模型输出里挖出 JSON。模型偶尔会包 code fence 或加一句废话，都容忍。"""
    m = _JSON_BLOCK.search(text or "")
    if not m:
        raise ValueError(f"评审输出里没有 JSON：{(text or '')[:200]}")
    return json.loads(m.group(0))


def _run(
    system: str,
    user: str,
    images: Sequence[Path] = (),
    *,
    account_labels: Sequence[str] | None = None,
    what: str,
    log_fn: LogFn | None = None,
) -> Review:
    """跑一次评审。agy 失败或输出无法解析时抛 :class:`ReviewError`。"""
    log = log_fn or (lambda _m: None)
    try:
        text, email = _ask(
            system, user, images, account_labels=account_labels, log_fn=log_fn
        )
    except Exception as exc:
        raise ReviewError(f"[评审] {what} agy 调用失败：{exc}") from exc

    try:
        data = _parse(text)
    except (ValueError, json.JSONDecodeError) as exc:
        raise ReviewError(
            f"[评审] {what} 输出无法解析：{exc}\n{(text or '')[:400]}"
        ) from exc

    review = Review(
        verdict=str(data.get("verdict") or VERDICT_REJECT).lower(),
        score=int(data.get("score") or 0),
        series_id=str(data.get("series_id") or ""),
        issues=[str(x) for x in data.get("issues") or []],
        fix=str(data.get("fix") or ""),
        reviewer=email,
        raw=text,
        shot_scale=str(data.get("shot_scale") or ""),
        rain_subjects=[str(x) for x in data.get("rain_subjects") or []],
        composition=str(data.get("composition") or ""),
    )
    log(f"[评审] {what} · {review.summary}")
    return review


# --------------------------------------------------------------- 四个入口


def classify_seed_image(
    image_path: Path,
    *,
    prompt: str = "",
    log_fn: LogFn | None = None,
) -> Review:
    """看图判断这张种子图属于哪个子系列。

    ``series_id`` 为空字符串表示三个系列都不适合，此时 ``verdict`` 是 ``reject``，
    ``issues`` 里是理由 —— 种子图定了整批的调子，不合适就该重出，不要将就。
    """
    catalog = "\n\n".join(_series_brief(s) for s in list_series())
    system = (
        "你是雨 ASMR 频道的选片人。频道分三个子系列，每个系列的用户场景和画面要求不同。\n\n"
        f"{catalog}\n\n"
        "你的任务：看图判断它属于哪个子系列，或者判定三个都不适合。"
        "判断依据只能是画面证据（雨的密度、光线明暗、主体形态、雾气、留白），"
        "不要被提示词文字影响。"
    )
    user = (
        "判断这张种子图属于哪个子系列，并描述画面构成。\n"
        f"{'它的生成提示词（仅供参考，以画面为准）：' + prompt[:600] if prompt else ''}\n\n"
        '只输出一个 JSON 对象，不要 markdown 代码块：\n'
        '{"series_id": "storm_sleep|steady_focus|drizzle_meditation|", '
        '"verdict": "pass|reject", "score": 0-100, '
        '"shot_scale": "近景|中景|远景", '
        '"rain_subjects": ["被雨击打或可见雨丝的对象，中文列举"], '
        '"composition": "一句话概括构图、景深、主体与环境关系", '
        '"issues": ["系列判定依据与画面细节；若三个都不适合，说明为什么"], "fix": ""}\n'
        "series_id 留空字符串表示三个都不适合，这时 verdict 必须是 reject。"
        "score 表示它落在所选系列里的典型程度。"
        "shot_scale / rain_subjects / composition 必须根据画面填写，不要照抄提示词。"
    )
    review = _run(system, user, [image_path], what=f"种子图分类 {image_path.name}", log_fn=log_fn)
    if review.verdict == VERDICT_PASS and not review.series_id:
        review.verdict = VERDICT_REJECT
        review.issues.append("模型判为通过却没给出系列，按不合格处理")
    return review


def review_prompt(
    kind: str,
    prompt: str,
    series_id: str,
    *,
    image_path: Path | None = None,
    log_fn: LogFn | None = None,
) -> Review:
    """评审提示词的语义：是否守住本系列意图、是否和参考图对得上。

    ``kind`` 取 ``"image"`` / ``"video"``，决定喂哪份规范正文。
    ``image_path`` 是图生视频的首帧（或图生图的参考图），给了模型才能查图文一致性。
    """
    doc = IMAGE_RULES_DOC if kind == "image" else VIDEO_RULES_DOC
    spec = get_series(series_id)
    system = (
        "你是雨 ASMR 频道的提示词评审。下面是本项目的提示词规范和子系列意图，"
        "你要判断给定提示词是否真的符合它们 —— 注意机器校验已经查过关键词和结构了，"
        "你要查的是语义：有没有自相矛盾、有没有偏离系列意图、和参考图对不对得上。\n\n"
        f"=== 提示词规范 ===\n{_doc_body(doc)}\n\n"
        f"=== 子系列规范 ===\n{_doc_body(SERIES_RULES_DOC)}\n\n"
        f"=== 本次要评审的系列 ===\n{_series_brief(spec)}"
    )
    hint = "，并检查它和所给参考图是否一致" if image_path else ""
    user = (
        f"评审下面这条 {kind} 提示词是否符合「{spec.label}」的意图{hint}：\n\n"
        f"{prompt}\n\n{_OUTPUT_CONTRACT}"
    )
    images = [image_path] if image_path is not None else []
    return _run(system, user, images, what=f"{kind} 提示词评审", log_fn=log_fn)


#: 高速摄影静帧 → 即梦慢镜头：系列图评审与出片前闸门共用这段硬标准。
_HIGHSPEED_STILL_RULES = (
    "这张图后面会作为图生视频的首尾帧。下列画面是硬性不合格"
    "（Gemini 高速摄影静帧会把 Seedance/即梦锁进慢镜头）：\n"
    "· 空中大片悬停、未落地的颗粒状水珠（suspended mid-air droplets）\n"
    "· 完整定格的水冠（crown splash）作为画面主角，像 high-speed / phantom 抓拍\n"
    "· 整体观感是高速快门冻帧，而不是「湿表面 + 轻雾」的可动画静帧\n"
    "合格静帧：水珠主要挂在主体表面，可有轻雾与湿润反光；"
    "撞击感靠表面水膜暗示，不要满屏定格水花。"
)


def review_image(
    image_path: Path,
    series_id: str,
    *,
    prompt: str = "",
    log_fn: LogFn | None = None,
) -> Review:
    """评审出来的图是否守住了本系列意图，并是否适合做图生视频首尾帧。"""
    spec = get_series(series_id)
    system = (
        "你是雨 ASMR 频道的选片人，判断一张图能不能进这个子系列。"
        "只看画面，不要因为提示词写得好就放行。\n\n"
        f"{_series_brief(spec)}\n\n"
        "另外无论哪个系列，这些是硬性不合格：画面里有人、有文字或水印、"
        "主体贴边没有给水花留空间、画面里有正在移动的非水物体（后面要做固定镜头 loop）。\n\n"
        f"{_HIGHSPEED_STILL_RULES}\n"
        "若因高速摄影不合格：verdict 用 revise，issues 里点明「高速静帧/慢镜头风险」，"
        "fix 给出改成「表面挂珠 + 轻雾、无空中悬珠/定格水冠」的完整出图提示词。"
    )
    user = (
        f"这张图要进「{spec.label}」系列，判断合不合格。\n"
        f"{'它的生成提示词（仅供参考）：' + prompt[:600] if prompt else ''}\n\n"
        f"{_OUTPUT_CONTRACT}\n"
        "verdict 用 revise 表示「提示词改一下重生成就行」，这时 fix 里给出改好的完整提示词；"
        "用 reject 表示这个方向本身就不对。"
    )
    return _run(system, user, [image_path], what=f"系列图评审 {image_path.name}", log_fn=log_fn)


def gate_still_for_video(
    image_path: Path,
    series_id: str,
    *,
    prompt: str = "",
    log_fn: LogFn | None = None,
) -> Review:
    """出视频前的硬闸：参考图若是高速摄影静帧，直接拦住，不提交即梦。

    系列图评审可能是旧批次（当时还没查这项），所以花钱生视频前必须再看一眼。
    """
    spec = get_series(series_id)
    system = (
        "你是雨 ASMR 频道的出片质检。唯一任务：判断这张静帧能不能安全用作"
        "图生视频（即梦/Seedance）的首尾帧。\n\n"
        f"{_series_brief(spec)}\n\n"
        f"{_HIGHSPEED_STILL_RULES}\n"
        "只根据画面判定。看到高速摄影线索就 revise；"
        "视频友好（表面挂珠、轻雾、无悬空冻珠/定格水冠主角）才 pass。"
    )
    user = (
        f"这张图将作为「{spec.label}」系列 5 秒 loop 的首尾帧，判断能否提交图生视频。\n"
        f"{'生成提示词（仅供参考）：' + prompt[:600] if prompt else ''}\n\n"
        f"{_OUTPUT_CONTRACT}\n"
        "若 revise：issues 点明慢镜头风险的画面证据；fix 给出适合重出系列图的完整提示词"
        "（表面挂珠 + 轻雾，禁止 frozen / high-speed / 定格水冠英雄瞬间）。"
    )
    return _run(
        system,
        user,
        [image_path],
        what=f"出片前静帧闸 {image_path.name}",
        log_fn=log_fn,
    )


def review_video_frames(
    frames: Sequence[Path],
    series_id: str,
    *,
    motion_score: float | None = None,
    prompt: str = "",
    log_fn: LogFn | None = None,
) -> Review:
    """评审视频抽帧：意图对不对，以及雨滴有没有拖影（拖影 = 实时快门）。

    ``motion_score`` 是 :mod:`video_probe` 量出来的客观运动量，一并告诉模型，
    让它的判断和客观数据对齐而不是各说各话。
    """
    spec = get_series(series_id)
    lo, hi = spec.frame_motion
    system = (
        "你是雨 ASMR 频道的成片验收。给你的是同一条 5 秒视频里按时间顺序抽出的几帧，"
        "判断这条视频能不能用。\n\n"
        f"{_series_brief(spec)}\n\n"
        "除了系列意图，还要重点查两件事：\n"
        "1. 慢镜头 —— 实时速度下的雨滴是**带拖影的短雨丝**，慢放时是悬停不动的小球。"
        "看到悬停的水珠就判 reject 并在 issues 里点明说是慢镜头。\n"
        "2. 画面漂移 —— 几帧之间构图、主体形状、颜色应当基本不变，"
        "只有雨和水在动；主体变形、背景换了、出现转场都判 reject。"
    )
    motion_line = ""
    if motion_score is not None:
        motion_line = (
            f"客观测得的运动量是 {motion_score:.1f}（本系列合理区间 {lo:.0f}–{hi:.0f}，"
            "无雨空镜约 0.5–1.3，真实轻雨 2.7–5.1，中雨 8–12，大雨 16.8–19.1）。\n"
        )
    user = (
        f"这条视频属于「{spec.label}」系列，判断合不合格。\n"
        f"{motion_line}"
        f"{'它的生成提示词（仅供参考）：' + prompt[:600] if prompt else ''}\n\n"
        f"{_OUTPUT_CONTRACT}\n"
        "如果判定是慢镜头，verdict 用 revise，fix 里给出加强实时速度后的完整提示词。"
    )
    return _run(
        system,
        user,
        list(frames),
        what=f"视频抽帧评审（{len(frames)} 帧）",
        log_fn=log_fn,
    )


def format_seed_analysis(
    review: dict | None,
    *,
    series_id: str = "",
    seed_prompt: str = "",
) -> str:
    """把种子图 Gemini 分析格式化为预览区右侧文案。"""
    from scripts.series_video.series import series_label

    data = review or {}
    rev = Review.from_dict(data)
    sid = rev.series_id or series_id
    lines: list[str] = []

    if sid:
        lines.append(f"子系列：{series_label(sid)}（{sid}）")
    else:
        lines.append("子系列：未判定（三个系列均不适合）")

    if rev.shot_scale:
        lines.append(f"景别：{rev.shot_scale}")
    if rev.rain_subjects:
        lines.append(f"雨击打对象：{'、'.join(rev.rain_subjects)}")
    if rev.composition:
        lines.append(f"画面构成：{rev.composition}")

    if rev.verdict or rev.score:
        lines.append(f"判定：{rev.summary}")

    if rev.issues:
        lines.append("")
        lines.append("分析要点：")
        lines.extend(f"· {item}" for item in rev.issues)

    if not lines or (len(lines) <= 2 and not rev.composition and not rev.issues):
        if seed_prompt.strip():
            lines.append("")
            lines.append("生成提示词：")
            lines.append(seed_prompt.strip())

    return "\n".join(lines) if lines else "（尚无 Gemini 分析）"


def format_series_image_review(
    review: dict | None,
    *,
    series_id: str = "",
    image_error: str = "",
) -> str:
    """把系列图 Gemini 评审格式化为预览区右侧文案。"""
    from scripts.series_video.series import series_label

    if image_error:
        return f"出图失败：{image_error}"

    rev = Review.from_dict(review)
    lines: list[str] = []

    sid = rev.series_id or series_id
    if sid:
        lines.append(f"子系列：{series_label(sid)}（{sid}）")

    if rev.verdict or rev.score:
        lines.append(f"判定：{rev.summary}")

    if rev.issues:
        lines.append("")
        lines.append("评审要点：")
        lines.extend(f"· {item}" for item in rev.issues)

    if rev.fix:
        lines.append("")
        lines.append("建议修改：")
        lines.append(rev.fix.strip())

    return "\n".join(lines) if lines else "（尚无 Gemini 评审）"
