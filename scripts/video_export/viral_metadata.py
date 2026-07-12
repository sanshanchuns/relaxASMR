"""爆款元数据变体生成（参考 design/rain_series/metadata_templates_report.md）。

每条视频约 50% 套用模版结构，50% 根据画面场景自由发挥，避免千篇一律。
"""

from __future__ import annotations

import hashlib
import random
import re
from typing import Callable

# --- 标题模版（T1/T2/T3/T4，来自 metadata_templates_report.md）---

TITLE_BENEFITS_EN = [
    "Rain Sounds for Sleep",
    "Relaxing Rain Sounds",
    "Deep Sleep Rain ASMR",
    "Calming Rain for Focus",
    "Cozy Rain ASMR",
    "Peaceful Rain for Sleeping",
]

TITLE_BENEFITS_ZH = [
    "助眠雨声",
    "放松雨声",
    "深度睡眠雨声",
    "专注冥想雨声",
    "治愈雨声",
]

TITLE_PURPOSES_EN = ["Sleeping", "Studying", "Relaxation", "Meditation", "Deep Focus"]
TITLE_ADJECTIVES_EN = ["Peaceful", "Calming", "Cozy", "Gentle", "Misty", "Soothing"]
TITLE_SECONDARY_EN = [
    "Calm Anxiety & Beat Insomnia",
    "Stress Relief & Better Sleep",
    "Focus & Relaxation",
]

# --- 描述：模版池（约 50%）---

HOOKS_EN = [
    "Fall asleep fast with gentle rain sounds on {place}.",
    "Let steady rain on {place} carry you into deep, restful sleep.",
    "Unwind tonight with natural rain ambience over {place}.",
    "Drift off to soft rain falling across {place} — no music, no voice.",
    "Create a cozy sleep cocoon with rain sounds from {place}.",
    "Need to quiet your mind? This {place} rain loop is made for you.",
]

HOOKS_ZH = [
    "伴着{place}的雨声，让身心慢慢沉入梦乡。",
    "把{place}的雨景当作今晚的背景，听见雨落、看见绿意。",
    "无需音乐与人声，只有{place}的真实雨声陪伴你入睡。",
    "如果你需要一段安静的雨夜，{place}的循环画面正合适。",
    "把焦虑交给雨声——{place}的细雨会帮你放松下来。",
]

BENEFITS_EN = [
    "Deep sleep & beat insomnia",
    "Anxiety / stress / tinnitus relief",
    "Perfect for study, meditation, baby sleep",
    "Focus without distraction",
    "White noise masking for noisy nights",
    "Gentle relaxation after a long day",
    "Mindfulness & breathing practice",
]

BENEFITS_ZH = [
    "深度睡眠 · 缓解失眠",
    "减轻焦虑、压力与耳鸣",
    "适合学习、冥想、宝宝入睡",
    "提升专注，屏蔽环境噪音",
    "白噪音助眠，整夜安稳",
    "下班后放松减压",
]

CTAS_EN = [
    "Subscribe for more relaxing rain sounds 🌧️\nLike if this helped you sleep!",
    "If this rain helped you relax, a like means a lot 🌧️\nSubscribe for new rain loops every week.",
    "New rain scenes upload regularly — subscribe so you don't miss them 🌧️",
]

CTAS_ZH = [
    "订阅获取更多放松雨声 🌧️\n有帮助请点赞！",
    "如果这段雨声帮到你，欢迎点赞并订阅 🌧️",
    "每周更新雨景循环，订阅不错过 🌧️",
]

HASHTAG_SETS_EN = [
    "#rainsounds #sleepsounds #asmr #whitenoise #insomnia #relaxingrain #forestrain",
    "#rainasmr #rainsounds #sleep #relax #naturesounds #meditation #4K",
    "#asmr #rain #rainsoundsforsleeping #thunderstorm #ambience #cozy",
]

HASHTAG_SETS_ZH = [
    "#雨声 #助眠 #ASMR #白噪音 #失眠 #放松雨声 #森林雨",
    "#雨声ASMR #助眠 #冥想 #自然音 #4K #放松",
    "#雨声 #睡眠 #白噪音 #治愈 #雨景循环",
]

# --- 描述：画面发挥池（约 50%）---

SCENE_CREATIVE_EN: dict[str, list[str]] = {
    "grove": [
        "Rain beads roll off fresh leaves while the forest breathes in slow green rhythm.",
        "You are walking under a living canopy — every drop adds texture to the hush.",
    ],
    "grove_path": [
        "A stone path disappears into wet woodland; footsteps are replaced by rainfall.",
        "Forest trees frame a narrow trail made glossy by steady drizzle.",
    ],
    "grove_pond": [
        "Mist lingers between trunks as rain taps the pond and reeds at the grove edge.",
        "Lotus and wetland plants catch the rain beside a quiet forest clearing.",
    ],
    "grove_pond_path": [
        "Rain threads through grove and pond — path, water, and leaves share the same hush.",
        "A misty forest path meets still water; the loop feels like one unbroken breath.",
    ],
    "park": [
        "Open lawn turns deep green under rain; the park feels private and unhurried.",
        "Wide green space, soft rainfall — an urban park turned into a sleep sanctuary.",
    ],
    "park_path": [
        "Winding stone through rain-wet grass — the park path invites a slow mental walk.",
        "Trees line a glistening path while rain smooths every hard edge of the day.",
    ],
    "park_pond": [
        "Lotus pond in a rainy park: water, petals, and drizzle in one gentle frame.",
        "Park greenery mirrors in pond ripples as rain keeps the scene softly moving.",
    ],
    "park_pond_path": [
        "Stone path, lotus pond, rainy lawn — three textures in one peaceful loop.",
        "Rain connects path and pond; the park scene feels like a watercolor in motion.",
    ],
    "pond": [
        "Lotus leaves hold silver drops; the pond surface shivers with quiet rhythm.",
        "Still water and rain create a minimal scene — nothing competes for your attention.",
    ],
    "nature": [
        "A calm natural frame with honest rainfall — simple, honest, easy to sleep to.",
        "No spectacle, just rain and green — the kind of view your nervous system trusts.",
    ],
}

SCENE_CREATIVE_ZH: dict[str, list[str]] = {
    "grove": [
        "雨后林木泛着深绿，雨滴从叶尖滑落，林间空气格外清新。",
        "树冠层过滤了雨势，只剩绵密的沙沙声与偶尔滴落。",
    ],
    "grove_path": [
        "石径在雨中泛着微光，两旁绿树把世界隔成一座安静的岛。",
        "沿着林间小径听雨，脚步声被雨声取代，思绪也慢慢放慢。",
    ],
    "grove_pond": [
        "雾气在林间与荷塘之间流动，雨点打在水面与叶片上，层次细腻。",
        "荷塘与林木交界处的雨景，湿润而不压抑，适合整夜循环。",
    ],
    "grove_pond_path": [
        "石径、荷塘、林木在同一场雨里交汇，画面与听感都连贯自然。",
        "雾雨中的林间荷塘小径，像一幅会动的淡彩画。",
    ],
    "park": [
        "开阔草坪被雨洗得格外翠绿，公园在雨里变得私密而松弛。",
        "城市公园在雨幕下安静下来，只剩雨声与远处朦胧的树线。",
    ],
    "park_path": [
        "蜿蜒石径穿过雨后草坪，适合把画面当作睡前的视觉锚点。",
        "雨中的公园步道泛着水光，节奏平稳，不易分心。",
    ],
    "park_pond": [
        "公园荷塘承接雨点，荷叶与远景绿树构成柔和景深。",
        "雨落荷塘，近处水面与远处林木形成舒适的视觉层次。",
    ],
    "park_pond_path": [
        "石径通向荷塘，雨声把草坪、水面与树影连成一条放松的线。",
        "公园里的路径与荷塘在雨中彼此呼应，画面干净不杂乱。",
    ],
    "pond": [
        "荷叶与水面在雨中轻轻颤动，场景极简，却格外耐看。",
        "荷塘雨景节奏缓慢，适合需要稳定视觉的人整夜播放。",
    ],
    "nature": [
        "自然的雨景循环，没有夸张特效，只有真实的雨与绿意。",
        "画面克制、雨声真实，适合作为背景整夜陪伴。",
    ],
}

MISTY_EXTRA_EN = [
    "A thin veil of mist makes the distance feel farther and safer.",
    "Soft fog blurs the horizon — your eyes can rest while rain does the work.",
]

MISTY_EXTRA_ZH = [
    "薄雾让远景更柔和，眼睛可以轻松休息。",
    "雾气把画面边缘柔化，雨声因此显得更远、更轻。",
]


def _rng(seed: str) -> random.Random:
    h = int(hashlib.sha256(seed.encode()).hexdigest()[:16], 16)
    return random.Random(h)


CLIMATE_ADJECTIVES = {
    "drizzle": "Gentle",
    "light": "Soft",
    "medium": "Steady",
    "heavy": "Heavy",
}


def scene_rain_from_vlm(vlm_ctx: dict, scene: dict) -> str | None:
    """根据 VLM/CLIP 三层声学标签生成差异化 SceneRain 短语。"""
    if not vlm_ctx:
        return None
    l1 = vlm_ctx.get("l1_en") or ""
    l2 = vlm_ctx.get("l2_en") or ""
    climate = vlm_ctx.get("climate_key", "medium")
    adj = CLIMATE_ADJECTIVES.get(climate, "Calming")
    if l1 and l2:
        return f"{adj} Rain on {l1} in {l2}"
    if l1:
        return f"{adj} Rain on {l1}"
    if l2:
        return f"{adj} Rain in {l2}"
    return None


def _pick(rng: random.Random, items: list, count: int = 1) -> list:
    if count >= len(items):
        return list(items)
    return rng.sample(items, count)


def _duration_title_en(meta: dict) -> str:
    s = int(meta["duration_s"])
    h = s // 3600
    m = (s % 3600) // 60
    if h >= 1:
        return f"{h} Hour{'s' if h != 1 else ''}"
    if m >= 1:
        return f"{m} Minutes"
    return f"{s} Seconds"


def _viral_format_en(meta: dict, *, show_4k: bool) -> str:
    dur = _duration_title_en(meta)
    k4 = "4K " if show_4k else ""
    return f"{dur} {k4}Rain Loop ASMR".strip()


def _viral_format_zh(meta: dict, *, show_4k: bool) -> str:
    dur = meta["duration_human"]
    k4 = "4K " if show_4k else ""
    return f"{dur}{k4}雨景循环 ASMR"


def _build_title_en(
    rng: random.Random,
    scene_rain: str,
    fmt_en: str,
    meta: dict,
) -> str:
    variant = rng.randint(0, 3)
    benefit = rng.choice(TITLE_BENEFITS_EN)
    adj = rng.choice(TITLE_ADJECTIVES_EN)
    purpose = rng.choice(TITLE_PURPOSES_EN)
    dur = _duration_title_en(meta)

    if variant == 0:
        return f"{benefit} | {scene_rain} | {fmt_en}"
    if variant == 1:
        pct = rng.choice([95, 97, 99])
        secondary = rng.choice(TITLE_SECONDARY_EN)
        return f"{pct}% {benefit} With {scene_rain} | {secondary}"
    if variant == 2:
        return f"{dur} {scene_rain} for {purpose}"
    emoji = rng.choice(["🌧️ ", "☔ ", ""])
    return f"{emoji}{adj} {scene_rain} | {fmt_en}"


def _build_title_zh(
    rng: random.Random,
    scene: dict,
    fmt_zh: str,
) -> str:
    variant = rng.randint(0, 2)
    benefit = rng.choice(TITLE_BENEFITS_ZH)
    place = scene["place_zh_short"]
    if variant == 0:
        return f"{benefit} | {place}雨声 | {fmt_zh}"
    if variant == 1:
        mood = "雾气" if scene.get("misty") else "治愈"
        return f"{mood}{place}雨景 | {benefit} | {fmt_zh}"
    return f"{scene['place_zh_long']} | {benefit} | {fmt_zh}"


def _creative_scene_lines(
    rng: random.Random,
    scene: dict,
    lang: str,
) -> list[str]:
    key = scene.get("scene_key", "nature")
    bank = SCENE_CREATIVE_ZH if lang == "zh" else SCENE_CREATIVE_EN
    lines = list(bank.get(key, bank["nature"]))
    if scene.get("misty"):
        extra = MISTY_EXTRA_ZH if lang == "zh" else MISTY_EXTRA_EN
        lines.extend(extra)
    return _pick(rng, lines, min(2, len(lines)))


def _build_description_en(
    rng: random.Random,
    scene: dict,
    meta: dict,
    hear: str,
) -> str:
    place = scene.get("thumb_place", scene["place_en_long"])
    hook = rng.choice(HOOKS_EN).format(place=place)
    creative = _creative_scene_lines(rng, scene, "en")
    benefits = _pick(rng, BENEFITS_EN, 3)
    experience = (
        f"What you'll see & hear: {scene['bullet_en'].lstrip('🪷🌳🌧 ')} "
        f"Seamless {hear} loop · {meta['duration_en']} · no music, no voice."
    )
    cta = rng.choice(CTAS_EN)
    tags = rng.choice(HASHTAG_SETS_EN)

    parts = [
        hook,
        "",
        creative[0] if creative else "",
        creative[1] if len(creative) > 1 else "",
        "",
        "\n".join(f"✅ {b}" for b in benefits),
        "",
        experience,
        "",
        cta,
        "",
        tags,
    ]
    return "\n".join(p for p in parts if p is not None)


def _build_description_zh(
    rng: random.Random,
    scene: dict,
    meta: dict,
) -> str:
    place = scene["place_zh_long"]
    hook = rng.choice(HOOKS_ZH).format(place=place)
    creative = _creative_scene_lines(rng, scene, "zh")
    benefits = _pick(rng, BENEFITS_ZH, 3)
    experience = (
        f"画面与听感：{scene['bullet_zh'].lstrip('🪷🌳🌧 ')}"
        f" 循环时长 {meta['duration_human']}，无音乐无人声。"
    )
    cta = rng.choice(CTAS_ZH)
    tags = rng.choice(HASHTAG_SETS_ZH)

    parts = [
        hook,
        "",
        creative[0] if creative else "",
        creative[1] if len(creative) > 1 else "",
        "",
        "\n".join(f"✅ {b}" for b in benefits),
        "",
        experience,
        "",
        cta,
        "",
        tags,
    ]
    return "\n".join(p for p in parts if p is not None)


def build_varied_forest_rain_copy(
    scene: dict,
    meta: dict,
    *,
    video_seed: str,
    show_4k: bool = False,
    scene_rain_resolver: Callable[[str, dict], str] | None = None,
    core_tags: list[str] | None = None,
    scene_tags: list[str] | None = None,
    vlm_ctx: dict | None = None,
) -> dict:
    """生成差异化标题/描述（模版 ≤50% + 画面发挥 ≥50%）。"""
    seed = video_seed or scene.get("scene_key", "nature")
    rng = _rng(seed)
    scene_key = scene.get("scene_key", "nature")

    scene_rain = scene_rain_from_vlm(vlm_ctx or {}, scene)
    if not scene_rain:
        if scene_rain_resolver:
            scene_rain = scene_rain_resolver(scene_key, scene)
        else:
            scene_rain = f"Calming Rain on {scene['place_en_short']}"

    hear = scene.get("thumb_place", scene["place_en_long"])
    fmt_en = _viral_format_en(meta, show_4k=show_4k)
    fmt_zh = _viral_format_zh(meta, show_4k=show_4k)

    title_en = _build_title_en(rng, scene_rain, fmt_en, meta)
    title_zh = _build_title_zh(rng, scene, fmt_zh)
    desc_en = _build_description_en(rng, scene, meta, hear)
    desc_zh = _build_description_zh(rng, scene, meta)

    base_core = core_tags or []
    base_scene = scene_tags or []
    extra = scene.get("tags_en", [])
    tags = list(dict.fromkeys(base_core + base_scene + extra))

    return {
        "title_zh": title_zh,
        "title_en": title_en,
        "description_zh": desc_zh,
        "description_en": desc_en,
        "tags": tags,
        "subtitle_zh": "睡眠 · 专注 · 冥想 · 减压",
        "subtitle_en": "Sleep · Focus · Meditation · Stress Relief",
        "metadata_source": "template",
        "scene_rain_en": scene_rain,
    }
