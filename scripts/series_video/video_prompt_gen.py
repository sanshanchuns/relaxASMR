"""图生视频 prompt：缺失时调用 Gemini（agy），参考 ``rain_asmr_video_prompt.md``。"""

from __future__ import annotations

import mimetypes
import re
from collections.abc import Callable
from pathlib import Path

from scripts.series_video.prompt_rules import (
    VIDEO_RULES_DOC,
    ensure_video_prompt,
    validate_video_prompt,
)
from scripts.series_video.prompts import build_video_prompt
from scripts.series_video.series import get_series
from scripts.series_video.store import BatchMeta, SeriesItem

LogFn = Callable[[str], None]

_RULES_MARKER = "<!-- validator:rules -->"
_FENCE = re.compile(r"^```(?:\w+)?\s*|\s*```$", re.MULTILINE)

#: Gemini 每次都会漏一两个必填维度，把违规原因回喂给它比重抽一次更省。
_MAX_ATTEMPTS = 3


def _guess_mime(path: Path) -> str:
    mime, _ = mimetypes.guess_type(path.name)
    return mime or "image/png"


def _doc_body(doc: Path) -> str:
    text = doc.read_text(encoding="utf-8")
    if _RULES_MARKER in text:
        return text.split(_RULES_MARKER, 1)[0].strip()
    return text.strip()


def _system_prompt(series_id: str) -> str:
    """视频规范正文 + 本批次子系列的意图。两份都给，模型才知道要写多大的雨。"""
    spec = get_series(series_id)
    return (
        f"{_doc_body(VIDEO_RULES_DOC)}\n\n"
        f"=== 本批次的子系列 ===\n"
        f"{spec.label}（{spec.id}）\n"
        f"意图：{spec.intent}\n"
        f"验收标准：{spec.review_rubric}"
    )


def _strip_fences(text: str) -> str:
    t = text.strip()
    if t.startswith("```"):
        t = _FENCE.sub("", t).strip()
    return t


def generate_video_prompt_for_item(
    meta: BatchMeta,
    item: SeriesItem,
    *,
    log_fn: LogFn | None = None,
    force: bool = False,
) -> str:
    """返回校验通过的 video prompt；写入 ``item.video_prompt`` 并 ``meta.save()``。

    已存过的 prompt 会先按**当前**规则复校一遍：规范改了（例如加了「实时速度」这一维），
    旧 prompt 就地作废并重新生成，否则老批次会一直拿着违规的 prompt 去烧钱。
    """
    log = log_fn or (lambda _m: None)
    series_id = meta.series_id
    spec = get_series(series_id)
    existing = (item.video_prompt or "").strip()
    if existing and not force:
        stale = validate_video_prompt(existing, series_id)
        if not stale:
            return existing
        log(f"[视频 prompt] 旧 prompt 不符合当前规范，重新生成：{'；'.join(stale)}")

    image_path = item.image_path(meta.batch_id)
    if not image_path.is_file():
        raise FileNotFoundError(f"系列图不存在：{image_path}")

    from scripts.config.paths import ensure_cli_path

    ensure_cli_path()
    from agy import AgyDirectError, generate_text_via_agy_accounts, has_agy_credentials

    if not has_agy_credentials():
        raise RuntimeError("未配置 agy 凭据（cli/agy/credentials.json），无法生成视频 prompt")

    log(f"[视频 prompt] 调用 Gemini 生成（{spec.label}）…")
    reference = build_video_prompt(subject_hint=item.summary, series_id=series_id)
    base_prompt = f"""Write ONE English image-to-video prompt for a 5s seamless loop.

Series: {spec.label} — {spec.intent}
Subject hint: {item.summary or 'rain ASMR macro scene'}
Image series prompt (context only — do NOT restate appearance from the image):
{(item.prompt or '')[:600]}

The Motion line MUST start with playback speed and rain intensity, in this order:
real-time speed (never slow motion), then how hard it rains — the rain intensity
MUST match this series, not what looks nice — then the motion-blurred rain streaks
that prove real-time shutter, then the impact events.

This template already satisfies every rule; stay this close to it and only adapt
the Subject and the impact events to what is actually in the image:
{reference}

Output ONLY the final prompt using the six tagged lines from the system instructions:
Animate the provided image. Subject: … Motion: … Environment: … Camera: … Style: … Loop seamlessly: … Constraints: …"""

    image_bytes = image_path.read_bytes()
    mime = _guess_mime(image_path)
    user_prompt = base_prompt
    text = ""
    email = ""
    for attempt in range(1, _MAX_ATTEMPTS + 1):
        try:
            text, email = generate_text_via_agy_accounts(
                user_prompt,
                model="gemini-3.6-flash",
                effort="medium",
                system=_system_prompt(series_id),
                images=[(mime, image_bytes)],
                log_fn=log_fn,
            )
        except AgyDirectError as exc:
            raise RuntimeError(f"Gemini 生成视频 prompt 失败：{exc}") from exc

        text = _strip_fences(text)
        problems = validate_video_prompt(text, series_id)
        if not problems:
            break
        log(f"[视频 prompt] 第 {attempt} 稿未过校验：{'；'.join(problems)}")
        user_prompt = (
            f"{base_prompt}\n\n"
            f"Your previous attempt was REJECTED by the validator:\n{text}\n\n"
            "Fix exactly these violations and output the corrected prompt only:\n"
            + "\n".join(f"- {p}" for p in problems)
        )
    else:
        # 三稿都没过就退回模板。模板是规范的标准答案，必然通过校验，
        # 总比让整条链路卡在 prompt 这一步强。
        text = reference
        log("[视频 prompt] Gemini 三稿均未过校验，改用规范模板")

    ensure_video_prompt(text, series_id)
    item.video_prompt = text
    item.video_error = ""
    meta.save()
    log(f"[视频 prompt] 完成（{email or '模板'}）")
    return text
