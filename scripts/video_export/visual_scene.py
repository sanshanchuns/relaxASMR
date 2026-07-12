"""视觉场景解析：CV 水面检测 + VLM 视觉锁定，提升标题/描述正确率。"""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Callable

from scripts.video_analysis.vlm_engine import call_gemini_vision_json

# 无 path 时禁止出现在标题/描述中的词（英文小写匹配）
PATH_TERMS_EN = (
    "stone path",
    "forest path",
    "forest grove path",
    "winding path",
    "trail",
    "walkway",
    "sidewalk",
    "footpath",
    "grove path",
    "park path",
)
PATH_TERMS_ZH = ("石径", "小径", "步道", "路径", "林间小径", "石板小径")

POND_TERMS_EN = ("pond", "lotus", "lily pad", "water surface", "wetland", "pool")
POND_TERMS_ZH = ("池塘", "荷塘", "水面", "荷叶", "睡莲", "湿地")


def analyze_visual_scene_vlm(
    frame_path: Path,
    *,
    on_progress: Callable[[str], None] | None = None,
) -> dict | None:
    """VLM 视觉锁定：结构化描述画面可见元素（防 path/pond 等幻觉）。"""
    prompt = """
You are a strict video scene annotator. Look ONLY at what is visible in this rain video frame.

Return ONLY raw JSON (no markdown):
{
  "setting_en": "3-8 words, e.g. forest pond with lily pads",
  "setting_zh": "中文场景，如 林间池塘荷叶",
  "has_water": true,
  "has_path": false,
  "has_lotus_or_lily_pads": true,
  "environment": "forest",
  "visible_elements_en": ["lily pads", "pond water", "dense green shrubs"],
  "visible_elements_zh": ["荷叶", "池塘水面", "茂密灌木"],
  "forbidden_in_copy_en": ["path", "stone path", "trail"],
  "forbidden_in_copy_zh": ["小径", "石径"]
}

Rules (CRITICAL):
- has_path=true ONLY if a clear walkable path/trail/sidewalk/stone walkway is visible.
  A pond edge, water surface, or muddy bank is NOT a path.
- has_water=true if pond/lake/stream/wetland water occupies noticeable area (often lower half).
- has_lotus_or_lily_pads=true if lotus flowers or round floating lily pads are visible.
- forbidden_in_copy_*: terms that must NOT appear in YouTube copy because they are NOT in the image.
- Do NOT guess off-screen elements. If unsure, set has_path=false.
"""
    if on_progress:
        on_progress("VLM 视觉场景锁定（path/pond 校验）…")
    try:
        data = call_gemini_vision_json(prompt, frame_path, on_progress=on_progress)
        return _normalize_visual_scene(data)
    except Exception as e:
        if on_progress:
            on_progress(f"VLM 视觉锁定失败: {e}")
        return None


def _normalize_visual_scene(raw: dict) -> dict:
    if not raw:
        return {}
    forbidden_en = [str(x).lower() for x in raw.get("forbidden_in_copy_en") or []]
    forbidden_zh = list(raw.get("forbidden_in_copy_zh") or [])
    if not raw.get("has_path", True):
        forbidden_en.extend(t.lower() for t in PATH_TERMS_EN)
        forbidden_zh.extend(PATH_TERMS_ZH)
    return {
        "setting_en": str(raw.get("setting_en", "")).strip(),
        "setting_zh": str(raw.get("setting_zh", "")).strip(),
        "has_water": bool(raw.get("has_water")),
        "has_path": bool(raw.get("has_path")),
        "has_lotus_or_lily_pads": bool(raw.get("has_lotus_or_lily_pads")),
        "environment": str(raw.get("environment", "unknown")).strip(),
        "visible_elements_en": list(raw.get("visible_elements_en") or []),
        "visible_elements_zh": list(raw.get("visible_elements_zh") or []),
        "forbidden_in_copy_en": list(dict.fromkeys(forbidden_en)),
        "forbidden_in_copy_zh": list(dict.fromkeys(forbidden_zh)),
        "source": "vlm_visual",
    }


def analyze_cv_scene(frame_path: Path, on_progress: Callable[[str], None] | None = None) -> dict | None:
    """OpenCV 帧分析（含 dark reflective pond 检测）。"""
    try:
        from scripts.video_analysis.analyze import analyze_frame
    except ImportError:
        return None
    try:
        fa = analyze_frame(frame_path, on_progress=on_progress)
    except Exception as e:
        if on_progress:
            on_progress(f"CV 场景分析失败: {e}")
        return None
    return {
        "scene_type": fa.scene_type,
        "scene_description": fa.scene_description,
        "water_detected": fa.water_detected,
        "water_score": fa.water_score,
        "foliage_density": fa.foliage_density,
        "green_pct": fa.green_pct,
        "source": "cv",
    }


def _cv_scene_key(cv: dict) -> str | None:
    if not cv:
        return None
    water = cv.get("water_detected") and float(cv.get("water_score", 0)) > 15
    st = cv.get("scene_type", "")
    green = float(cv.get("green_pct", 0))
    foliage = float(cv.get("foliage_density", 0))

    if water:
        if st in ("stream", "lake"):
            if foliage > 20 or green > 15:
                return "grove_pond"
            return "pond"
    if st == "path" and not water:
        return "grove_path" if green > 15 else "park_path"
    if st in ("forest", "canopy", "bamboo"):
        return "grove"
    if st == "garden":
        return "park"
    if st == "open":
        return "park"
    return None


def visual_scene_cache_path(material_dir: Path, scene_id: str) -> Path:
    return material_dir / f"{scene_id}_visual_scene.json"


def load_visual_scene_cache(path: Path) -> dict | None:
    if not path.is_file():
        return None
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return None


def save_visual_scene_cache(path: Path, data: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")


def resolve_visual_scene(
    frame_path: Path,
    heuristic_scene: dict,
    *,
    scene_id: str = "",
    material_dir: Path | None = None,
    use_vlm_visual: bool = True,
    force_refresh: bool = False,
    on_progress: Callable[[str], None] | None = None,
) -> tuple[dict, dict]:
    """
    合并启发式 / CV / VLM 视觉锁定，返回 (最终 scene dict, visual_context dict)。
    优先级：VLM 视觉锁定 > CV > 启发式。
    """
    from video_export.generate_youtube_material import scene_template_by_key

    visual: dict = {"heuristic_key": heuristic_scene.get("scene_key", "")}
    misty = heuristic_scene.get("misty", False)
    chosen_key = heuristic_scene.get("scene_key", "nature")

    cv = analyze_cv_scene(frame_path, on_progress=on_progress)
    if cv:
        visual["cv"] = cv
        cv_key = _cv_scene_key(cv)
        if cv_key:
            visual["cv_scene_key"] = cv_key
            should_upgrade = (
                "path" in chosen_key
                or (cv.get("water_detected") and chosen_key in ("grove", "nature", "park"))
            )
            if should_upgrade and cv_key != chosen_key:
                if on_progress:
                    on_progress(
                        f"CV 修正场景：{chosen_key} → {cv_key}（检测到水面 score={cv.get('water_score', 0):.0f}）"
                    )
                chosen_key = cv_key

    vlm_visual = None
    cache_path = None
    if scene_id and material_dir:
        cache_path = visual_scene_cache_path(material_dir, scene_id)
        if not force_refresh:
            vlm_visual = load_visual_scene_cache(cache_path)

    if use_vlm_visual and vlm_visual is None:
        vlm_visual = analyze_visual_scene_vlm(frame_path, on_progress=on_progress)
        if vlm_visual and cache_path:
            save_visual_scene_cache(cache_path, vlm_visual)

    if vlm_visual:
        visual["vlm_visual"] = vlm_visual
        if vlm_visual.get("has_water") and not vlm_visual.get("has_path"):
            if "path" in chosen_key or chosen_key in ("grove", "nature"):
                new_key = "grove_pond" if vlm_visual.get("environment") == "forest" else "pond"
                if on_progress and new_key != chosen_key:
                    on_progress(f"VLM 视觉修正场景：{chosen_key} → {new_key}（有水面、无路径）")
                chosen_key = new_key

    scene = scene_template_by_key(chosen_key, misty=misty)

    if vlm_visual:
        if vlm_visual.get("setting_en"):
            scene["place_en_long"] = vlm_visual["setting_en"]
            scene["thumb_place"] = vlm_visual["setting_en"]
            if vlm_visual.get("has_lotus_or_lily_pads"):
                scene["place_en_short"] = "Forest Pond"
                scene["bullet_en"] = (
                    f"🪷 {vlm_visual['setting_en']} · rain ripples on lily pads · calm wetland"
                )
        if vlm_visual.get("setting_zh"):
            scene["place_zh_long"] = vlm_visual["setting_zh"]
            scene["place_zh_short"] = vlm_visual["setting_zh"][:6]

    visual["resolved_scene_key"] = chosen_key
    return scene, visual


def format_visual_constraints(visual: dict) -> str:
    """供 metadata prompt 使用的硬约束文本。"""
    lines = ["## VISUAL FACTS (HARD CONSTRAINTS — override any heuristic hint)"]
    vlm = visual.get("vlm_visual") or {}
    cv = visual.get("cv") or {}

    if vlm.get("setting_en"):
        lines.append(f"- Primary setting (EN): **{vlm['setting_en']}**")
    if vlm.get("setting_zh"):
        lines.append(f"- Primary setting (ZH): **{vlm['setting_zh']}**")
    if vlm:
        lines.append(f"- has_water: {vlm.get('has_water')}; has_path: {vlm.get('has_path')}; "
                     f"has_lotus: {vlm.get('has_lotus_or_lily_pads')}")
        if vlm.get("visible_elements_en"):
            lines.append(f"- Visible: {', '.join(vlm['visible_elements_en'][:8])}")
        if vlm.get("forbidden_in_copy_en"):
            lines.append(f"- NEVER mention (not in frame): {', '.join(vlm['forbidden_in_copy_en'][:12])}")
    elif cv:
        lines.append(f"- CV scene: {cv.get('scene_type')} — {cv.get('scene_description')}")
        lines.append(f"- water_detected: {cv.get('water_detected')} (score {cv.get('water_score', 0):.0f})")
        if cv.get("water_detected") and not cv.get("scene_type") == "path":
            lines.append("- NEVER mention path/trail/stone walkway unless clearly visible")

    lines.append("- Describe ONLY what is visible. Pond edge ≠ path.")
    return "\n".join(lines)


def _contains_forbidden(text: str, forbidden: list[str]) -> list[str]:
    lower = text.lower()
    hits = []
    for term in forbidden:
        t = term.lower().strip()
        if t and t in lower:
            hits.append(term)
    return hits


def validate_copy_against_visual(copy: dict, visual: dict) -> list[str]:
    """返回违规词列表；空列表表示通过。"""
    vlm = visual.get("vlm_visual") or {}
    forbidden_en = list(vlm.get("forbidden_in_copy_en") or [])
    forbidden_zh = list(vlm.get("forbidden_in_copy_zh") or [])

    if not vlm.get("has_path", True):
        forbidden_en.extend(PATH_TERMS_EN)
        forbidden_zh.extend(PATH_TERMS_ZH)

    text_en = " ".join(
        copy.get(k, "") for k in ("title_en", "description_en", "scene_rain_en") if copy.get(k)
    )
    text_zh = " ".join(copy.get(k, "") for k in ("title_zh", "description_zh") if copy.get(k))

    hits = _contains_forbidden(text_en, forbidden_en)
    hits += [t for t in forbidden_zh if t in text_zh]

    # 有水面但 copy 完全没提 water/pond 也算弱违规（仅 warning，不强制 fail）
    return hits


def sanitize_copy_for_visual(copy: dict, visual: dict) -> dict:
    """移除/替换违规词（最后兜底）。"""
    vlm = visual.get("vlm_visual") or {}
    out = dict(copy)
    replacement_en = vlm.get("setting_en") or "rainy nature scene"
    replacement_zh = vlm.get("setting_zh") or "雨景"

    for field in ("title_en", "description_en", "scene_rain_en"):
        text = out.get(field, "")
        if not text:
            continue
        for term in PATH_TERMS_EN:
            text = re.sub(re.escape(term), replacement_en, text, flags=re.I)
        text = re.sub(r"\bpath\b", "pond" if vlm.get("has_water") else "grove", text, flags=re.I)
        out[field] = text

    for field in ("title_zh", "description_zh"):
        text = out.get(field, "")
        for term in PATH_TERMS_ZH:
            text = text.replace(term, replacement_zh)
        out[field] = text

    return out
