"""系列视频提示词构造。

两套公式的完整最佳实践写在 ``instructions/`` 下，由 ``prompt_rules.py`` 在生成前强制校验：

* ``instructions/rain_asmr_image_prompt.md`` —— 文生图（种子图）与图生图（系列图）
* ``instructions/rain_asmr_video_prompt.md`` —— 图生视频

本模块只负责「按公式拼出提示词」，是否放行由校验器说了算。

两套提示词各有自己的公式，不要混用：

文生图（生成待选种子图）与图生图（同系列图）——「时间 + 主体 + 场景 + 风格」四段式：
    时间：一天中的时刻/天气/季节，决定光线（提示词里杠杆最高的一项）
    主体：被雨打击的物体（叶片/花瓣/水面…）及其材质细节
    场景：主体所处环境与背景景深
    风格：镜头语言 + 画质 + 色调

图生视频（把静帧变成 5s loop）——Seedance 官方 6 步公式：
    主体 → 动作 → 环境 → 镜头 → 风格 → 约束
关键纪律（照抄官方避坑清单 + 本项目补充）：
    · 60–115 词，太长会产生互相矛盾的指令
    · Motion 段开头必须写实时速度和雨的强度，否则默认出慢镜头
    · 只写一个主镜头指令；本项目固定镜头，所以永远是 static / locked-off
    · 镜头运动与主体运动分开描述，别写成「镜头绕着跳舞的人转」
    · 用节奏词（steady / continuous / rhythmic）而不是摄影参数（f/2.8、ISO）；
      注意节奏词管的是节拍均匀，管速度的是 real-time，两个都要写
    · 负面提示词是标配，至少排除慢镜头、抖动与时间闪烁
"""

from __future__ import annotations

import random
from dataclasses import dataclass, field

from scripts.series_video.series import SeriesSpec, get_series

# ---------------------------------------------------------------- 图生图

#: 主题锚点：所有系列图都必须落在「雨 + 打击物 + ASMR 感」这个范围内。
#: 刻意不写 splash crowns / frozen droplets——那些会把 Gemini 推向高速摄影静帧，
#: 同图做即梦首尾帧后 Seedance 几乎必出慢镜头；水冠留给视频 Motion 段。
THEME_ANCHOR = (
    "rain ASMR macro cinematography: raindrops striking a wet surface, "
    "visible moisture on the subject and fine water mist"
)

_STILL_FOR_VIDEO = (
    "This still will be reused as first and last frame for image-to-video, "
    "so it must be video-friendly: wet surface beads and soft mist are good; "
    "high-speed photography looks are forbidden — no fields of mid-air suspended "
    "droplets, no peak frozen splash crowns as the hero moment."
)

IMAGE_SYSTEM_PROMPT = (
    "You are a still-frame art director for a rain-ASMR video channel. "
    "You output one photographic image only, never text or collage. "
    "The reference image defines the visual language: keep its lighting mood, "
    "color grading, lens character and composition discipline, and vary only "
    "what the instruction asks you to vary. "
    + _STILL_FOR_VIDEO
)

#: 文生图没有参考图，系统提示里要把「视觉语言」本身讲清楚。
#: 水滴渲染由 ``SeriesSpec.style_extra`` 决定：暴雨要中景雨帘，中雨/细雨要表面挂珠。
SEED_SYSTEM_PROMPT = (
    "You are a still-frame art director for a rain-ASMR video channel. "
    "You output one photographic image only, never text or collage. "
    "This frame will become the seed of a whole series and will later be animated "
    "as a five-second static-camera loop, so keep the composition calm and the "
    "subject off the edges. "
    + _STILL_FOR_VIDEO
)

#: 「风格」维度的公共部分：镜头语言与硬性排除项，三个子系列共用。
#: 水的形态（雨帘 / 表面挂珠 / 薄雾）由各系列的 ``style_extra`` 追加在后面。
STYLE_BASE = (
    "cinematic macro photography, 100mm lens, very shallow depth of field, "
    "desaturated cool film tone, high dynamic range, no text, no watermark, "
    "no people, 16:9 horizontal composition"
)


def style_anchor(series: SeriesSpec, extra: str = "") -> str:
    """公共风格串 + 该系列的水滴渲染方式（+ 用户临时追加）。"""
    parts = [STYLE_BASE]
    if series.style_extra:
        parts.append(series.style_extra)
    if extra.strip():
        parts.append(extra.strip())
    return ", ".join(parts)


#: 文生图与图生图只差「与参考图的关系」这一句，四段式主体完全共用。
_SERIES_LEAD = "Create a NEW image in the same series as the reference image."
_SERIES_TAIL = (
    "Keep the reference image's grading and lens feel so the images look "
    "like frames from one series, but make the subject and framing clearly "
    "different from the reference. Leave the frame calm enough that it can "
    "be animated later as a static-camera loop."
)
_SEED_LEAD = "Create a single photographic still frame that will seed a whole series."
_SEED_TAIL = (
    "This frame defines the look of every later image in the series, so make the "
    "lighting and grading decisive and repeatable. Leave the frame calm enough that "
    "it can be animated later as a static-camera loop."
)


@dataclass(frozen=True)
class ImageVariant:
    """一张图对应的四段式提示词。

    ``mode="series"`` 是图生图（带参考图），``mode="seed"`` 是文生图（生成待选种子图）。
    ``series_id`` 记下这张图属于哪个子系列，校验时要拿它去叠覆盖层。
    """

    time: str
    subject: str
    scene: str
    style: str
    mode: str = "series"
    series_id: str = ""

    def to_prompt(self) -> str:
        seed_mode = self.mode == "seed"
        return (
            f"{_SEED_LEAD if seed_mode else _SERIES_LEAD}\n"
            f"Theme: {THEME_ANCHOR}.\n"
            f"Time: {self.time}.\n"
            f"Subject: {self.subject}.\n"
            f"Scene: {self.scene}.\n"
            f"Style: {self.style}.\n"
            f"{_SEED_TAIL if seed_mode else _SERIES_TAIL}"
        )

    def system_prompt(self) -> str:
        return SEED_SYSTEM_PROMPT if self.mode == "seed" else IMAGE_SYSTEM_PROMPT

    def summary(self) -> str:
        """短标题，用于宫格单元格显示。"""
        return self.subject.split(",", 1)[0].strip()


def build_image_variants(
    count: int,
    *,
    series_id: str = "",
    seed: int | None = None,
    extra_style: str = "",
    mode: str = "series",
    subject: str = "",
    scene: str = "",
) -> list[ImageVariant]:
    """挑出 *count* 组互不重复的「时间/主体/场景」组合。

    候选全部来自 *series_id* 对应的子系列（暴雨/中雨/细雨的主体和光线本来就不同）。
    主体优先不重复（视觉差异最明显），时间和场景允许在主体用尽后循环复用。
    传入 ``subject`` / ``scene`` 可锁死那一段（生成种子图候选时用：同一个想法出 N 张，
    只让时间/光线变化，方便横向比较）。
    """
    spec = get_series(series_id)
    rng = random.Random(seed)
    subjects = [subject.strip()] if subject.strip() else list(spec.subject_variants)
    scenes = [scene.strip()] if scene.strip() else list(spec.scene_variants)
    times = list(spec.time_variants)
    rng.shuffle(subjects)
    rng.shuffle(times)
    rng.shuffle(scenes)

    style = style_anchor(spec, extra_style)

    return [
        ImageVariant(
            # 雨量措辞跟在场景后面：四段式里「场景」这一段本来就要求写雨的强度。
            time=times[i % len(times)],
            subject=subjects[i % len(subjects)],
            scene=f"{scenes[i % len(scenes)]}, {spec.rain_phrase}",
            style=style,
            mode=mode,
            series_id=spec.id,
        )
        for i in range(max(0, count))
    ]


def _enrich_seed_subject(idea: str) -> str:
    """把用户随手写的主体补成「材质 + 表面细节」，否则过不了图生图校验。"""
    idea = idea.strip()
    if not idea:
        return ""
    low = idea.lower()
    material_terms = (
        "surface", "texture", "wet", "glossy", "waxy", "mossy", "smooth",
        "material", "beading", "droplet", "droplets", "water",
    )
    if any(t in low for t in material_terms):
        return idea
    return f"{idea}, wet textured surface, water beading into clear droplets"


def build_seed_variants(
    count: int,
    *,
    idea: str = "",
    series_id: str = "",
    seed: int | None = None,
) -> list[ImageVariant]:
    """为「用 prompt 生成待选种子图」构造 *count* 条文生图提示词。

    ``idea`` 是用户输入的自由描述（想拍什么被雨打的东西）。它只会填进 Subject 段，
    其余三段仍由公式补齐 —— 这样用户随手写一句话也能拼出结构合规、能过校验的提示词。
    留空则从该系列的主体库里随机挑，每张一个不同主体。
    """
    return build_image_variants(
        count,
        series_id=series_id,
        seed=seed,
        mode="seed",
        subject=_enrich_seed_subject(idea),
    )


# -------------------------------------------------------------- 图生视频

#: 固定镜头 —— 本项目所有 loop 都不做运镜，只让水动。
CAMERA_INSTRUCTION = "locked-off tripod, fixed framing, no pan no zoom"

#: 负面约束：官方避坑清单里对 loop 素材最致命的几项，外加本项目的慢镜头补刀。
NEGATIVE_CONSTRAINTS = (
    "avoid slow motion, high-speed camera look, frozen droplets, time-lapse, "
    "camera movement, jitter, temporal flicker, morphing, scene changes, "
    "people, text overlays"
)

#: 播放速度锚点。不写这一句，Seedance 对「雨 + 微距 + cinematic」的默认理解就是高速摄影
#: 慢放（训练素材几乎全是慢镜头），负面提示单独用是压不住的，必须正面锚定。
REALTIME_INSTRUCTION = "at real-time speed under natural gravity"

#: 雨的强度。同样必填：不写强度，模型只给几滴稀疏水珠慢慢飘，看着也是慢放。
#: 键对应子系列 ``video.rain_intensity``（暴雨/中雨/细雨）。
RAIN_INTENSITY_VARIANTS: dict[str, str] = {
    "heavy": "heavy rain pours down",
    "steady": "steady rain falls",
    "drizzle": "a light drizzle falls",
}
DEFAULT_RAIN_INTENSITY = "steady"

#: 实时快门的视觉证据：真实速度下的雨滴是带拖影的雨丝，不是悬停的小球。
#: 这句比速度词本身更有效 —— 它描述画面证据，模型照着画就必然是实时速度。
MOTION_BLUR_INSTRUCTION = "the drops leave short motion-blurred streaks"

#: 动作：只让雨与水动，主体保持原位，这样首尾才好接成 loop。
MOTION_EVENTS = (
    "splash crowns burst on impact, ripples spread and fade, fine mist drifts; "
    "the subject stays in place"
)

VIDEO_STYLE = "cinematic macro realism, cool desaturated film tone, real-time motion"


def build_motion(series_id: str = "", *, rain_intensity: str = "") -> str:
    """拼出 Motion 段：速度 → 雨量 → 拖影 → 撞击事件 → 主体静止 → 系列补充。

    顺序是有意的：速度和雨量放最前面，模型对句首的指令更敏感。
    雨量默认由子系列决定，``rain_intensity`` 只在调试时手动覆盖。
    """
    spec = get_series(series_id)
    key = rain_intensity or spec.video_rain_intensity
    intensity = RAIN_INTENSITY_VARIANTS.get(
        key, RAIN_INTENSITY_VARIANTS[DEFAULT_RAIN_INTENSITY]
    )
    parts = [
        f"{intensity} {REALTIME_INSTRUCTION} in a continuous rhythm",
        MOTION_BLUR_INSTRUCTION,
        MOTION_EVENTS,
    ]
    if spec.video_motion_extra:
        parts.append(spec.video_motion_extra)
    return ", ".join(parts)


#: 向后兼容的默认 Motion 段（默认系列 + 实时速度）。
MOTION_INSTRUCTION = build_motion()


@dataclass
class VideoPromptSpec:
    """图生视频提示词的 6 个槽位，便于逐项覆写。"""

    subject: str = "the subject in the provided image"
    motion: str = MOTION_INSTRUCTION
    environment: str = "unchanged from the provided image"
    camera: str = CAMERA_INSTRUCTION
    style: str = VIDEO_STYLE
    constraints: str = NEGATIVE_CONSTRAINTS
    loop: bool = True
    extra: str = field(default="")

    def to_prompt(self) -> str:
        parts = [
            f"Animate the provided image. Subject: {self.subject}.",
            f"Motion: {self.motion}.",
            f"Environment: {self.environment}.",
            f"Camera: {self.camera}.",
            f"Style: {self.style}.",
        ]
        if self.loop:
            parts.append("Loop seamlessly: last frame matches the first.")
        if self.extra.strip():
            parts.append(self.extra.strip())
        parts.append(f"Constraints: {self.constraints}.")
        return " ".join(parts)


def build_video_prompt(
    *,
    subject_hint: str = "",
    series_id: str = "",
    extra: str = "",
    loop: bool = True,
    rain_intensity: str = "",
) -> str:
    """按 6 步公式生成图生视频提示词。

    ``subject_hint`` 传入该帧的主体描述（通常直接用系列图的 subject 段），
    留空则让模型沿用参考图里看到的主体。雨量由 ``series_id`` 决定，
    ``rain_intensity`` 只在调试时手动覆盖。
    """
    spec = VideoPromptSpec(
        loop=loop,
        extra=extra,
        motion=build_motion(series_id, rain_intensity=rain_intensity),
    )
    if subject_hint.strip():
        spec.subject = subject_hint.strip()
    return spec.to_prompt()


def prompt_word_count(prompt: str) -> int:
    return len(prompt.split())
