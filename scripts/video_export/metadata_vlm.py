"""Gemini VLM 生成差异化 YouTube 标题/描述（参考 metadata_templates_report.md）。"""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Callable

from scripts.config.common_constants import CLOSE_NAMES, DISTANT_NAMES, SPACE_NAMES
from scripts.config.paths import clip_matches_path, vlm_matches_path
from scripts.video_analysis.vlm_engine import call_gemini_vision_json, seed_rng

# 标题模版 T1–T4（design/rain_series/metadata_templates_report.md）
TITLE_TEMPLATES = {
    "T1": "{Benefit} | {SceneRain} | {Format}",
    "T2": "{Pct}% {Benefit} With {SceneRain} | {Secondary}",
    "T3": "{Duration} {SceneRain} for {Purpose}",
    "T4": "{Emoji}{Adj} {SceneRain} | {Format}",
}

TITLE_BENEFITS = [
    "Rain Sounds for Sleep",
    "Relaxing Rain Sounds",
    "Deep Sleep Rain ASMR",
    "Calming Rain for Focus",
    "Cozy Rain ASMR",
]

TITLE_PURPOSES = ["Sleeping", "Studying", "Relaxation", "Meditation", "Deep Focus"]
TITLE_SECONDARY = [
    "Calm Anxiety & Beat Insomnia",
    "Stress Relief & Better Sleep",
    "Focus & Relaxation",
]
TITLE_ADJECTIVES = ["Peaceful", "Calming", "Cozy", "Gentle", "Misty", "Soothing"]

CORE_TAGS = [
    "rain sounds",
    "rain",
    "rain sounds for sleeping",
    "sleep",
    "rain asmr",
    "heavy rain",
    "sleep sounds",
    "white noise",
    "nature sounds",
    "relaxing rain",
    "rain ambience",
    "insomnia",
]


def enrich_layer_context(raw: dict) -> dict:
    """补全 l1/l2/l3 英中文名。"""
    if not raw:
        return {}
    ctx = dict(raw)
    for key_attr, name_map in (
        ("l3_key", DISTANT_NAMES),
        ("l2_key", SPACE_NAMES),
        ("l1_key", CLOSE_NAMES),
    ):
        kid = ctx.get(key_attr)
        if kid is not None:
            en, cn = name_map.get(kid, ("", ""))
            prefix = key_attr.replace("_key", "")
            ctx[f"{prefix}_en"] = en
            ctx[f"{prefix}_cn"] = cn
    return ctx


def load_vlm_context(scene_id: str) -> dict:
    """从 material/ 下的 clip/vlm matches 加载声学三层上下文。"""
    if not scene_id:
        return {}
    for path_fn in (vlm_matches_path, clip_matches_path):
        p = path_fn(scene_id)
        if not p.is_file():
            continue
        data = json.loads(p.read_text(encoding="utf-8"))
        return enrich_layer_context(
            {
                "l3_key": data.get("l3_key"),
                "l2_key": data.get("l2_key"),
                "l1_key": data.get("l1_key"),
            }
        )
    return {}


def _duration_title_en(meta: dict) -> str:
    s = int(meta["duration_s"])
    h = s // 3600
    m = (s % 3600) // 60
    if h >= 1:
        return f"{h} Hour{'s' if h != 1 else ''}"
    if m >= 1:
        return f"{m} Minutes"
    return f"{s} Seconds"


def _format_en(meta: dict, *, show_4k: bool) -> str:
    dur = _duration_title_en(meta)
    k4 = "4K " if show_4k else ""
    return f"{dur} {k4}Rain Loop ASMR".strip()


def _format_zh(meta: dict, *, show_4k: bool) -> str:
    k4 = "4K " if show_4k else ""
    return f"{meta['duration_human']}{k4}雨景循环 ASMR"


def select_title_template(video_seed: str) -> str:
    rng = seed_rng(video_seed or "default")
    return rng.choice(["T1", "T2", "T3", "T4"])


def build_metadata_prompt(
    scene: dict,
    meta: dict,
    vlm_ctx: dict,
    *,
    video_seed: str,
    show_4k: bool,
    template_id: str,
    visual_context: dict | None = None,
) -> str:
    fmt_en = _format_en(meta, show_4k=show_4k)
    fmt_zh = _format_zh(meta, show_4k=show_4k)
    dur_en = _duration_title_en(meta)

    acoustic = ""
    if vlm_ctx:
        acoustic = (
            f"Distant atmosphere: {vlm_ctx.get('l3_en', 'unknown')}; "
            f"Space/environment: {vlm_ctx.get('l2_en', 'unknown')}; "
            f"Close surface: {vlm_ctx.get('l1_en', 'unknown')}."
        )

    visual_block = ""
    if visual_context:
        from scripts.video_export.visual_scene import format_visual_constraints
        visual_block = format_visual_constraints(visual_context) + "\n"

    heuristic = (
        f"(Low trust — verify with image) heuristic key: {scene.get('scene_key', 'nature')}; "
        f"draft place EN: {scene.get('place_en_long', '')}."
    )

    tmpl = TITLE_TEMPLATES.get(template_id, TITLE_TEMPLATES["T1"])
    rng = seed_rng(f"{video_seed}:{template_id}")

    return f"""You are a YouTube metadata writer for a rain ASMR channel.
Write UNIQUE title and description for THIS specific video frame — avoid generic copy reused across uploads.

{visual_block}
## Channel constraints (MUST follow)
- Real 4K rain loop FOOTAGE (NOT black screen). Never mention "black screen".
- Format segment for English title MUST be exactly: `{fmt_en}`
- English title ≤ 100 characters; include rain + sleep/relax/ASMR keywords.
- Use assigned title template structure: **{template_id}** → `{tmpl}`
- SceneRain phrase MUST describe ONLY what you SEE in the image (pond, lily pads, trees — NOT path unless visible).
- If VISUAL FACTS say has_path=false, NEVER use path/trail/walkway/stone path in title or description.
- Descriptions: Hook → 3 benefit bullets (✅) → scene sensory paragraph → CTA → hashtags
- Chinese and English must match the same scene but NOT be literal translations — vary wording.
- Video seed (for uniqueness): `{video_seed}` — make copy distinct from other videos with same template.

## Suggested slot values (you may adapt)
- Benefit examples: {", ".join(TITLE_BENEFITS[:4])}
- Purpose examples: {", ".join(TITLE_PURPOSES)}
- Secondary benefit (T2): {rng.choice(TITLE_SECONDARY)}
- Adjective (T4): {rng.choice(TITLE_ADJECTIVES)}
- Percent hook (T2): {rng.choice([95, 97, 99])}%
- Duration (T3): {dur_en}
- Chinese format segment: `{fmt_zh}`

## Low-priority hints (do NOT override VISUAL FACTS)
{heuristic}
Acoustic mix hint (sound design, not necessarily visible): {acoustic or "not available"}

## Description hashtags (pick 6–10, include #asmr #rainsounds #whitenoise)
Example: #rainsounds #sleepsounds #asmr #whitenoise #insomnia #relaxingrain #4K

Return ONLY raw JSON (no markdown):
{{
  "title_en": "...",
  "title_zh": "...",
  "description_en": "...",
  "description_zh": "...",
  "scene_rain_en": "short scene phrase for thumbnail, e.g. Calming Rain on Forest Pond Lily Pads",
  "tags_en": ["rain sounds", "rain asmr", "..."]
}}
"""


def _validate_copy(data: dict, fmt_en: str) -> dict | None:
    required = ("title_en", "title_zh", "description_en", "description_zh")
    if not all(data.get(k) for k in required):
        return None
    title_en = str(data["title_en"]).strip()
    if len(title_en) > 100:
        title_en = title_en[:100].rsplit(" ", 1)[0]
    desc_en = str(data["description_en"]).strip()
    desc_zh = str(data["description_zh"]).strip()
    if len(desc_en) < 80 or len(desc_zh) < 40:
        return None
    tags = data.get("tags_en") or data.get("tags") or []
    if isinstance(tags, str):
        tags = [t.strip() for t in re.split(r"[,，]", tags) if t.strip()]
    tags = list(dict.fromkeys(str(t).strip() for t in tags if str(t).strip()))
    scene_rain = str(data.get("scene_rain_en", "")).strip()
    return {
        "title_en": title_en,
        "title_zh": str(data["title_zh"]).strip(),
        "description_en": desc_en,
        "description_zh": desc_zh,
        "scene_rain_en": scene_rain,
        "tags": tags or list(CORE_TAGS),
        "format_en": fmt_en,
        "template_id": data.get("template_id", ""),
    }


def generate_youtube_copy_with_vlm(
    frame_path: Path,
    scene: dict,
    meta: dict,
    *,
    video_seed: str = "",
    vlm_ctx: dict | None = None,
    visual_context: dict | None = None,
    show_4k: bool = False,
    on_progress: Callable[[str], None] | None = None,
) -> dict | None:
    """调用 Gemini 生成差异化物料；失败返回 None（由调用方回退模版池）。"""
    from scripts.video_export.visual_scene import (
        sanitize_copy_for_visual,
        validate_copy_against_visual,
    )

    frame_path = Path(frame_path)
    if not frame_path.is_file():
        return None

    fmt_en = _format_en(meta, show_4k=show_4k)
    template_id = select_title_template(video_seed)
    ctx = enrich_layer_context(vlm_ctx or {})

    def _run_once(extra_note: str = "") -> dict | None:
        prompt = build_metadata_prompt(
            scene,
            meta,
            ctx,
            video_seed=video_seed,
            show_4k=show_4k,
            template_id=template_id,
            visual_context=visual_context,
        )
        if extra_note:
            prompt += f"\n\nRETRY NOTE: Previous draft violated visual constraints. {extra_note}\n"
        raw = call_gemini_vision_json(prompt, frame_path, on_progress=on_progress)
        raw["template_id"] = template_id
        result = _validate_copy(raw, fmt_en)
        if result and fmt_en not in result["title_en"]:
            if template_id in ("T1", "T4") and "|" in result["title_en"]:
                parts = [p.strip() for p in result["title_en"].split("|")]
                if len(parts) >= 2:
                    parts[-1] = fmt_en
                    result["title_en"] = " | ".join(parts)
        return result

    if on_progress:
        on_progress(f"VLM 生成差异化文案（模版 {template_id}）…")

    try:
        result = _run_once()
        if result and visual_context:
            violations = validate_copy_against_visual(result, visual_context)
            if violations:
                if on_progress:
                    on_progress(f"文案校验未通过（{violations[:3]}），重试…")
                setting = (visual_context.get("vlm_visual") or {}).get("setting_en", "the visible scene")
                result = _run_once(
                    extra_note=f"Remove these terms completely: {violations}. "
                    f"Describe ONLY: {setting}. has_path is false — no path/trail."
                )
                if result:
                    violations = validate_copy_against_visual(result, visual_context)
                    if violations:
                        result = sanitize_copy_for_visual(result, visual_context)
                        if on_progress:
                            on_progress(f"已自动修正违规词：{violations[:3]}")

        if on_progress and result:
            on_progress(f"VLM 文案完成 · 模版 {template_id} · {result['title_en'][:60]}…")
        return result
    except Exception as e:
        if on_progress:
            on_progress(f"VLM 文案生成失败，回退模版池: {e}")
        return None


def merge_vlm_copy_with_tags(vlm_copy: dict, core_tags: list[str], scene_tags: list[str], scene: dict) -> dict:
    """组装与 generate_youtube_material 一致的 copy dict。"""
    extra = scene.get("tags_en", [])
    tags = list(dict.fromkeys((vlm_copy.get("tags") or []) + core_tags + scene_tags + extra))
    return {
        "title_zh": vlm_copy["title_zh"],
        "title_en": vlm_copy["title_en"],
        "description_zh": vlm_copy["description_zh"],
        "description_en": vlm_copy["description_en"],
        "tags": tags,
        "subtitle_zh": "睡眠 · 专注 · 冥想 · 减压",
        "subtitle_en": "Sleep · Focus · Meditation · Stress Relief",
        "scene_rain_en": vlm_copy.get("scene_rain_en", ""),
        "metadata_source": "vlm",
        "template_id": vlm_copy.get("template_id", ""),
    }
