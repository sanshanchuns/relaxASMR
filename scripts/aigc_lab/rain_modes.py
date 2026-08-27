"""三档雨强的单一事实源：显示名、语义基线、客观运动量期望。

id 沿用历史值（light_mod / heavy / storm），只重挂语义与显示名，
旧 run 的 ``meta.rain_mode`` 因此无需迁移。

运动量刻度来自 ``video_probe`` 用真实素材的标定：
无雨空镜 0.5–1.3、小雨 2.7–5.1、中雨 8–12、大雨 16.8–19.1。
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class RainMode:
    mode_id: str
    label: str  # 中文显示名
    en: str  # 英文档位名，进 prompt
    motion_lo: float
    motion_hi: float
    baseline: str  # 该档的语义基线，喂给 LLM 当写作锚点

    @property
    def display(self) -> str:
        return f"{self.label} {self.en}"


RAIN_MODES: tuple[RainMode, ...] = (
    RainMode(
        mode_id="light_mod",
        label="小雨",
        en="drizzle",
        motion_lo=2.0,
        motion_hi=7.0,
        baseline=(
            "细密雨丝，落点稀疏可数；水面只起小涟漪，不成溅花；"
            "叶片被单滴打中时轻微下沉又弹回；无径流，地面只是湿透反光。"
        ),
    ),
    RainMode(
        mode_id="heavy",
        label="中雨",
        en="moderate rain",
        motion_lo=6.0,
        motion_hi=14.0,
        baseline=(
            "连续密集雨线，落点连成片；积水面持续起溅花小水柱；"
            "叶片被压得小幅起伏；屋檐与叶尖开始滴成断续水线；地面有薄薄流水。"
        ),
    ),
    RainMode(
        mode_id="storm",
        label="暴雨",
        en="downpour",
        motion_lo=13.0,
        motion_hi=100.0,
        baseline=(
            "雨幕成片，空气里有明显水汽；积水被砸出密集溅花与水花冠；"
            "屋檐边缘连成不断的水柱冲进积水；叶片被压弯后小幅回弹；地面径流明显。"
        ),
    ),
)

RAIN_MODE_ORDER: tuple[str, ...] = tuple(m.mode_id for m in RAIN_MODES)
_BY_ID: dict[str, RainMode] = {m.mode_id: m for m in RAIN_MODES}
DEFAULT_RAIN_MODE = "heavy"

#: 低于此运动量视为「几乎静止」——真实无雨空镜也有 0.5–1.3 的底噪。
STILL_FLOOR = 1.6

_ALIASES: dict[str, str] = {
    "light": "light_mod",
    "light_mod": "light_mod",
    "drizzle": "light_mod",
    "soft": "light_mod",
    "小雨": "light_mod",
    "小/中雨": "light_mod",
    "moderate": "heavy",
    "heavy": "heavy",
    "中雨": "heavy",
    "大雨": "heavy",
    "storm": "storm",
    "downpour": "storm",
    "暴雨": "storm",
}


def normalize_rain_mode(value: str | None) -> str:
    raw = str(value or "").strip().lower()
    return _ALIASES.get(raw, DEFAULT_RAIN_MODE)


def rain_mode(value: str | None) -> RainMode:
    return _BY_ID[normalize_rain_mode(value)]


def rain_label(value: str | None) -> str:
    return rain_mode(value).display


def motion_range(value: str | None) -> tuple[float, float]:
    m = rain_mode(value)
    return (m.motion_lo, m.motion_hi)


def motion_scale_hint() -> str:
    """给 VLM 的运动量参照说明。"""
    return (
        "运动量刻度（帧差 0–100，真实素材标定）："
        "无雨空镜 0.5–1.3，小雨 2.7–5.1，中雨 8–12，暴雨 16.8–19.1。"
    )
