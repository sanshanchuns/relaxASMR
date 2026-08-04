"""从关键字 + 子系列约束，让 Gemini 批量产出候选种子图的文生图 prompt。"""

from __future__ import annotations

import json
import re
from collections.abc import Callable

from scripts.series_video.prompt_rules import IMAGE_RULES_DOC, ensure_image_prompt
from scripts.series_video.prompts import SEED_SYSTEM_PROMPT, ImageVariant, style_anchor
from scripts.series_video.series import SeriesSpec, get_series

LogFn = Callable[[str], None]

_RULES_MARKER = "<!-- validator:rules -->"
_JSON_ARRAY = re.compile(r"\[\s*\{.*\}\s*\]", re.DOTALL)


def _doc_body() -> str:
    text = IMAGE_RULES_DOC.read_text(encoding="utf-8")
    if _RULES_MARKER in text:
        return text.split(_RULES_MARKER, 1)[0].strip()
    return text.strip()


def generate_seed_prompts_from_keywords(
    *,
    keywords: str,
    series_id: str,
    count: int,
    log_fn: LogFn | None = None,
) -> list[ImageVariant]:
    """根据几个关键字 + 子系列意图，生成 *count* 条互不重复的种子图文生图 prompt。

    关键字不是完整 prompt，只是方向（如「荷叶、池塘、傍晚」）；Gemini 负责填四段式并
    保证每条在主体/场景/光线上有足够差异。
    """
    log = log_fn or (lambda _m: None)
    spec = get_series(series_id)
    count = max(1, min(count, 12))

    from scripts.config.paths import ensure_cli_path

    ensure_cli_path()
    from agy import AgyDirectError, generate_text_via_agy_accounts, has_agy_credentials

    if not has_agy_credentials():
        raise RuntimeError("未配置 agy 凭据，无法生成种子图 prompt")

    system = (
        f"{_doc_body()}\n\n"
        f"=== 本批子系列 ===\n"
        f"{spec.label}（{spec.id}）\n"
        f"意图：{spec.intent}\n"
        f"雨量措辞参考：{spec.rain_phrase}\n"
        f"风格增补：{spec.style_extra}\n"
    )
    user = f"""Write exactly {count} DIFFERENT English seed-image prompts for the rain-ASMR series
「{spec.label}」.

User keywords (expand into Subject/Scene/Time — do NOT paste verbatim as the whole prompt):
{keywords.strip() or '(no keywords — pick varied subjects from the series subject pool)'}

Each prompt MUST use this exact structure (plain text, one prompt per array element):
{{
  "time": "...",
  "subject": "...",
  "scene": "...",
  "style": "..."
}}

Rules:
- mode is always seed (text-to-image, no reference image).
- Scene line MUST include rain intensity matching this series: {spec.rain_phrase}
- Style MUST include the series style extra: {spec.style_extra}
- Video-friendly stills only: wet surface beads / soft mist. NEVER write frozen,
  high-speed, suspended mid-air droplets, or clean splash crowns as the hero.
- Subjects must differ across the {count} prompts; time/light may vary.
- Output ONLY a JSON array of {count} objects with keys time, subject, scene, style.
"""

    log(f"[种子 prompt] Gemini 根据关键字生成 {count} 条（{spec.label}）…")
    try:
        text, email = generate_text_via_agy_accounts(
            user, system=system, effort="medium", log_fn=log_fn
        )
    except AgyDirectError as exc:
        raise RuntimeError(f"Gemini 生成种子 prompt 失败：{exc}") from exc

    m = _JSON_ARRAY.search(text or "")
    if not m:
        raise RuntimeError(f"Gemini 未返回 JSON 数组：{(text or '')[:300]}")
    raw = json.loads(m.group(0))
    if not isinstance(raw, list) or not raw:
        raise RuntimeError("Gemini 返回的 prompt 列表为空")

    variants: list[ImageVariant] = []
    for item in raw[:count]:
        if not isinstance(item, dict):
            continue
        style = str(item.get("style") or "").strip()
        if style:
            style = f"{style_anchor(spec)}, {style}"
        else:
            style = style_anchor(spec)
        variant = ImageVariant(
            time=str(item.get("time") or spec.time_variants[0]),
            subject=str(item.get("subject") or keywords or "wet surface in rain"),
            scene=f"{item.get('scene') or spec.scene_variants[0]}, {spec.rain_phrase}",
            style=style,
            mode="seed",
            series_id=spec.id,
        )
        prompt = variant.to_prompt()
        ensure_image_prompt(prompt, spec.id)
        variants.append(variant)

    if not variants:
        raise RuntimeError("没有一条 prompt 通过校验")
    log(f"[种子 prompt] 完成 {len(variants)} 条（{email}）")
    return variants
