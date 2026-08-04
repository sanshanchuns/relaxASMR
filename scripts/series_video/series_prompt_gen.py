"""从种子图 + 限定词，让 Gemini 批量产出系列图（图生图）prompt。"""

from __future__ import annotations

import json
import mimetypes
import re
from collections.abc import Callable
from pathlib import Path

from scripts.series_video.prompt_rules import IMAGE_RULES_DOC, ensure_image_prompt
from scripts.series_video.prompts import ImageVariant, style_anchor
from scripts.series_video.series import get_series
from scripts.series_video.store import BatchMeta

LogFn = Callable[[str], None]

_RULES_MARKER = "<!-- validator:rules -->"
_JSON_ARRAY = re.compile(r"\[\s*\{.*\}\s*\]", re.DOTALL)


def _doc_body() -> str:
    text = IMAGE_RULES_DOC.read_text(encoding="utf-8")
    if _RULES_MARKER in text:
        return text.split(_RULES_MARKER, 1)[0].strip()
    return text.strip()


def _guess_mime(path: Path) -> str:
    mime, _ = mimetypes.guess_type(path.name)
    return mime or "image/png"


def generate_series_image_prompts(
    meta: BatchMeta,
    *,
    count: int,
    constraints: str = "",
    log_fn: LogFn | None = None,
) -> list[ImageVariant]:
    """根据种子图 + 限定词 + 子系列，生成 *count* 条图生图 prompt。

    ``constraints`` 描述系列图中必须保持一致的东西（如「主体、拍摄角度、环境」），
    以及允许变化的部分。留空则只要求与种子图同系列、主体不同。
    """
    log = log_fn or (lambda _m: None)
    spec = get_series(meta.series_id)
    seed = meta.seed_path
    if not seed.is_file():
        raise FileNotFoundError(f"种子图不存在：{seed}")
    count = max(1, min(count, 20))
    hold = (constraints or meta.series_constraints or "").strip()

    from scripts.config.paths import ensure_cli_path

    ensure_cli_path()
    from agy import AgyDirectError, generate_text_via_agy_accounts, has_agy_credentials

    if not has_agy_credentials():
        raise RuntimeError("未配置 agy 凭据，无法生成系列图 prompt")

    system = (
        f"{_doc_body()}\n\n"
        f"=== 本批子系列 ===\n"
        f"{spec.label}（{spec.id}）\n"
        f"意图：{spec.intent}\n"
        f"雨量：{spec.rain_phrase}\n"
    )
    user = f"""Look at the seed image. Write exactly {count} DIFFERENT English series-image prompts
for the same rain-ASMR series 「{spec.label}」.

Series constraints (what MUST stay consistent across all {count} frames):
{hold or 'Same grading, lens feel, rain intensity and general environment as the seed; vary subject and framing clearly.'}

Each prompt MUST use series mode structure. Output ONLY a JSON array of {count} objects:
{{ "time": "...", "subject": "...", "scene": "...", "style": "..." }}

Rules:
- Each subject must be clearly different from the seed AND from each other.
- Respect the constraints above for anything the user locked.
- Scene includes rain: {spec.rain_phrase}
- Style matches seed grading; include: {spec.style_extra}
- Video-friendly stills only: wet surface beads / soft mist. NEVER write frozen,
  high-speed, suspended mid-air droplets, or clean splash crowns as the hero
  (those lock Jimeng/Seedance into slow motion when reused as first/last frame).
"""

    log(f"[系列 prompt] Gemini 生成 {count} 条（限定：{hold[:40] or '默认'}）…")
    try:
        text, email = generate_text_via_agy_accounts(
            user,
            system=system,
            effort="medium",
            images=[(_guess_mime(seed), seed.read_bytes())],
            log_fn=log_fn,
        )
    except AgyDirectError as exc:
        raise RuntimeError(f"Gemini 生成系列 prompt 失败：{exc}") from exc

    m = _JSON_ARRAY.search(text or "")
    if not m:
        raise RuntimeError(f"Gemini 未返回 JSON 数组：{(text or '')[:300]}")
    raw = json.loads(m.group(0))

    variants: list[ImageVariant] = []
    for item in raw[:count]:
        if not isinstance(item, dict):
            continue
        st = str(item.get("style") or "").strip()
        style = f"{style_anchor(spec)}, {st}" if st else style_anchor(spec)
        variant = ImageVariant(
            time=str(item.get("time") or spec.time_variants[0]),
            subject=str(item.get("subject") or "rain-struck surface"),
            scene=f"{item.get('scene') or spec.scene_variants[0]}, {spec.rain_phrase}",
            style=style,
            mode="series",
            series_id=spec.id,
        )
        prompt = variant.to_prompt()
        ensure_image_prompt(prompt, spec.id)
        variants.append(variant)

    if not variants:
        raise RuntimeError("没有一条系列 prompt 通过校验")
    log(f"[系列 prompt] 完成 {len(variants)} 条（{email}）")
    return variants
