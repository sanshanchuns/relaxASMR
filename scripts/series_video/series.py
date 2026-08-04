"""三个子系列（暴雨助眠 / 中雨专注 / 轻雨冥想）的定义读取。

事实来源是 ``instructions/rain_asmr_series.md`` 末尾的 JSON，本模块只做解析和取值，
不在代码里写任何系列参数 —— 想调雨量、光线、主体库，改 markdown 就行。

一个批次只属于一个系列，从种子图定稿那一刻定死，系列图和视频全部继承：

* 提示词侧：:mod:`prompts` 按系列取时间/主体/场景候选与雨量措辞
* 校验侧：:func:`prompt_rules.image_rules` / ``video_rules`` 叠系列覆盖层
* 评审侧：:mod:`review` 把 ``review_rubric`` 喂给 Gemini 判产物合不合意图
* 验收侧：:mod:`video_probe` 用 ``frame_motion`` 区间拦慢镜头和死画面
"""

from __future__ import annotations

from dataclasses import dataclass, field

from scripts.series_video.prompt_rules import PromptRulesError, series_catalog


@dataclass(frozen=True)
class SeriesSpec:
    """一个子系列的完整意图。"""

    id: str
    label: str
    intent: str
    review_rubric: str
    rain_phrase: str
    style_extra: str
    time_variants: tuple[str, ...]
    subject_variants: tuple[str, ...]
    scene_variants: tuple[str, ...]
    video_rain_intensity: str
    video_motion_extra: str
    frame_motion: tuple[float, float] = (0.0, 100.0)
    #: 未在 markdown 里定义的原始字段，留给后续扩展。
    raw: dict = field(default_factory=dict, repr=False, compare=False)

    @property
    def display(self) -> str:
        return f"{self.label}（{self.id}）"


def _spec_from_raw(raw: dict) -> SeriesSpec:
    image = raw.get("image") or {}
    video = raw.get("video") or {}
    motion = raw.get("frame_motion") or {}
    return SeriesSpec(
        id=str(raw.get("id") or ""),
        label=str(raw.get("label") or raw.get("id") or ""),
        intent=str(raw.get("intent") or ""),
        review_rubric=str(raw.get("review_rubric") or ""),
        rain_phrase=str(image.get("rain_phrase") or ""),
        style_extra=str(image.get("style_extra") or ""),
        time_variants=tuple(image.get("time_variants") or ()),
        subject_variants=tuple(image.get("subject_variants") or ()),
        scene_variants=tuple(image.get("scene_variants") or ()),
        video_rain_intensity=str(video.get("rain_intensity") or "steady"),
        video_motion_extra=str(video.get("motion_extra") or ""),
        frame_motion=(
            float(motion.get("min", 0.0)),
            float(motion.get("max", 100.0)),
        ),
        raw=raw,
    )


def list_series() -> list[SeriesSpec]:
    return [_spec_from_raw(e) for e in series_catalog().get("series") or []]


def default_series_id() -> str:
    catalog = series_catalog()
    fallback = str(catalog.get("default_series") or "")
    if fallback:
        return fallback
    entries = catalog.get("series") or []
    return str(entries[0].get("id")) if entries else ""


def get_series(series_id: str) -> SeriesSpec:
    """按 id 取系列；``series_id`` 为空时返回默认系列（老批次没有这个字段）。"""
    wanted = (series_id or "").strip() or default_series_id()
    for spec in list_series():
        if spec.id == wanted:
            return spec
    raise PromptRulesError(
        f"未知子系列 {series_id!r}；可选：{', '.join(s.id for s in list_series())}"
    )


def series_label(series_id: str) -> str:
    try:
        return get_series(series_id).label
    except PromptRulesError:
        return series_id or "?"
