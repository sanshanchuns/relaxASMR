"""六槽原子化 prompt：主体 / 动作 / 环境 / 镜头 / 风格 / 约束。

镜头 / 风格 / 约束：只能从 ``atom_pools`` 选取（对齐 Seedance 6 步公式指南）。
GUI 表格展示「槽位：原子1 + …」；送模仅为原子正文拼接。
构图归镜头。
"""

from __future__ import annotations

import json
import re
from collections.abc import Callable, Sequence

from scripts.config.paths import ensure_cli_path, t2v_lab_dir

LogFn = Callable[[str], None]

_REWRITE_MODEL = "gemini-3.6-flash"

RAIN_MODES: tuple[tuple[str, str], ...] = (
    ("light_mod", "小/中雨"),
    ("heavy", "大雨"),
    ("storm", "暴雨"),
)
DEFAULT_RAIN_MODE = "storm"
RAIN_MODE_IDS = frozenset(m for m, _ in RAIN_MODES)
RAIN_MODE_LABELS = {m: label for m, label in RAIN_MODES}

SLOT_ORDER: tuple[str, ...] = (
    "subject",
    "action",
    "environment",
    "camera",
    "style",
    "constraints",
)
SLOT_LABELS: dict[str, str] = {
    "subject": "主体",
    "action": "动作",
    "environment": "环境",
    "camera": "镜头",
    "style": "风格",
    "constraints": "约束",
}
ATOM_ORDER = SLOT_ORDER

# 开放槽：LLM 基线可自写；闭集槽：产品固定（纯自然雨 ASMR）
OPEN_SLOTS: tuple[str, ...] = ("subject", "action", "environment")
LOCKED_SLOTS: tuple[str, ...] = ("camera", "style", "constraints")

# 场景：只指导 LLM，不进送模正文
DEFAULT_SCENES: tuple[str, ...] = ("原始热带雨林",)
SCENE_SEED_POOL: tuple[str, ...] = (
    "原始热带雨林",
    "热带雨林溪谷",
    "热带雨林林冠下层",
    "红树林潮沼",
    "温带针叶密林",
    "竹林雨径",
)

# ---------------------------------------------------------------------------
# 闭集原子池（镜头 / 风格 / 约束）— LLM 只能原样选取
# 参考: https://help.apiyi.com/seedance-2-0-prompt-guide-video-generation-camera-style-tips.html
# 原则：像对剪辑师说话；不用焦距/广角等技术参数；原子正交、不重复。
# ---------------------------------------------------------------------------

# 镜头 = 运动 ×1 + 视角 ×1。景别/焦距不写——由「主体」覆盖范围内决定。
CAMERA_MOTION_POOL: tuple[str, ...] = (
    "固定镜头",
)
CAMERA_ANGLE_POOL: tuple[str, ...] = (
    "平视",
    "仰视",
    "俯视",
)
# 旧名兼容（钳制时映射）
_CAMERA_MOTION_ALIASES = {
    "固定机位": "固定镜头",
    "镜头完全静止": "固定镜头",
    "稳定固定机位": "固定镜头",
}

# 风格关键词 = 官方「高效风格关键词」原文（英文）；禁止自造「短拖影/自然重力」等
# 出处: Seedance 2.0 风格关键词与光线描述
STYLE_KEYWORD_POOL: tuple[str, ...] = (
    # 电影感
    "cinematic",
    "film tone",
    "35mm",
    # 画质
    "4K",
    "high detail",
    "sharp",
    # 胶片
    "film grain",
    "analog",
    "vintage",
    # 色调
    "warm tone",
    "cool palette",
    "desaturated",
    # 氛围
    "moody",
    "dreamy",
    "ethereal",
    # 真实感
    "realistic",
    "natural",
    "documentary",
)

# 光线 = 官方光线关键词；指南强调光线杠杆最高
STYLE_LIGHT_POOL: tuple[str, ...] = (
    "golden hour",
    "rim light",
    "natural light",
    "neon",
    "backlit",
    "overcast",
)

# 雨档默认优选（仍须是上面闭集的子集）
_STYLE_KEYWORD_DEFAULT: dict[str, tuple[str, ...]] = {
    "light_mod": ("documentary", "natural", "cool palette"),
    "heavy": ("documentary", "cool palette", "desaturated"),
    "storm": ("documentary", "moody", "desaturated"),
}
_STYLE_LIGHT_DEFAULT: dict[str, str] = {
    "light_mod": "overcast",
    "heavy": "overcast",
    "storm": "overcast",
}

# ASMR 声层：产品需要，不在官方风格表内，单独子池
STYLE_AUDIO_POOL: dict[str, tuple[str, ...]] = {
    "light_mod": (
        "轻到中等连续雨声、单滴击叶可辨或均匀沙沙",
    ),
    "heavy": (
        "密集连续大雨击打声、叶片与地面层次清晰",
    ),
    "storm": (
        "连续震耳暴雨ASMR、猛烈击打叶片树干与泥地的多层次声",
    ),
}

# 约束：只写「不要什么」；慢放用「无慢动作」承接（不再写短拖影正面句）
CONSTRAINTS_CORE: tuple[str, ...] = (
    "避免画面抖动",
    "避免时间闪烁",
    "避免构图混乱",
    "无慢动作",
)
CONSTRAINTS_EXTRA: tuple[str, ...] = (
    "无切镜",
    "无转场",
    "无闪电",
    "无人物",
    "无动物",
    "无音乐",
    "无旁白",
    "无狂风摇树",
)

# 主体：一条原子只描述一个可见主体，不能把多个物体并在一起。
# 主体范围决定画面覆盖范围，替代焦距/广角。
_SUBJECT_DEFAULT: tuple[str, ...] = (
    "香蕉树",
    "宽大蕉叶",
    "热带乔木",
    "浓密灌木",
    "粗壮树干",
    "湿润地面",
)

# 动作：只写雨与表面的互动（正交于环境的空中密度/能见度）
# 环境：空间设定 + 空中雨密度/水雾能见度 + 全程恒定（正交于动作）
_ACTION_ENV: dict[str, dict[str, tuple[str, ...]]] = {
    "light_mod": {
        "action": (
            "叶片挂珠、击打处小溅花、偶有滚落",
            "叶片轻颤但不被压垮",
            "树干湿润反光、地面涟漪稀疏、无成股急流",
        ),
        "environment": (
            "茂密原始热带雨林内部",
            "空中雨滴均匀稀疏到中等、远景轮廓仍可读",
            "该雨强已持续、开场即满、全程恒定无渐强",
        ),
    },
    "heavy": {
        "action": (
            "蕉叶持续溅水、叶缘间歇成线泄水",
            "叶片明显颤动与轻度压弯",
            "树干可见流股、地面频繁溅起与积水波纹",
        ),
        "environment": (
            "茂密原始热带雨林内部",
            "空中雨帘可见、中等水雾、后景仍隐约可辨",
            "该雨强已持续、开场即满、全程恒定无渐入",
        ),
    },
    "storm": {
        "action": (
            "宽大叶片上持续爆开溅花",
            "叶片被雨势压弯剧烈颤动、叶缘成片倾泻",
            "树干多股快速径流、地面密集飞溅与积水翻涌",
        ),
        "environment": (
            "茂密原始热带雨林内部",
            "空中厚重雨幕、浓水雾、远处植被几乎被遮没",
            "该雨强已持续、开场即满、全程恒定无渐入",
        ),
    },
}

_DEFAULT_CAMERA: tuple[str, ...] = (
    "固定镜头",
    "平视",
)

def _default_style_atoms(mode: str) -> list[str]:
    return [
        *_STYLE_KEYWORD_DEFAULT[mode],
        _STYLE_LIGHT_DEFAULT[mode],
        STYLE_AUDIO_POOL[mode][0],
    ]


_DEFAULT_CONSTRAINTS: tuple[str, ...] = CONSTRAINTS_CORE + (
    "无切镜",
    "无转场",
    "无闪电",
    "无人物",
    "无动物",
    "无音乐",
    "无旁白",
)


def normalize_rain_mode(mode: str | None) -> str:
    key = (mode or DEFAULT_RAIN_MODE).strip()
    if key in RAIN_MODE_IDS:
        return key
    aliases = {
        "小/中雨": "light_mod",
        "小雨": "light_mod",
        "中雨": "light_mod",
        "大雨": "heavy",
        "暴雨": "storm",
        "drizzle": "light_mod",
        "steady": "light_mod",
        "torrential": "storm",
    }
    return aliases.get(key, DEFAULT_RAIN_MODE)


def camera_pool() -> list[str]:
    return list(CAMERA_MOTION_POOL) + list(CAMERA_ANGLE_POOL)


def style_pool(rain_mode: str | None = None) -> list[str]:
    mode = normalize_rain_mode(rain_mode)
    return (
        list(STYLE_KEYWORD_POOL)
        + list(STYLE_LIGHT_POOL)
        + list(STYLE_AUDIO_POOL[mode])
    )


def constraints_pool() -> list[str]:
    return list(CONSTRAINTS_CORE) + list(CONSTRAINTS_EXTRA)


def format_pool_block(rain_mode: str | None = None) -> str:
    """给 LLM 的闭集池清单。"""
    mode = normalize_rain_mode(rain_mode)
    lines = [
        "【镜头 camera — 恰好 2 条，均须原样选自池】",
        f"  motion（恰好 1）: {' | '.join(CAMERA_MOTION_POOL)}",
        f"  angle（恰好 1）: {' | '.join(CAMERA_ANGLE_POOL)}",
        "  禁止：焦距、广角/超广角、景别术语（由主体描述覆盖）",
        "【风格 style — 关键词 1–3 条 + 光线 1 条 + 音频 1 条；均须原样选自池】",
        f"  风格关键词（官方表）: {' | '.join(STYLE_KEYWORD_POOL)}",
        f"  光线（官方表，恰好 1）: {' | '.join(STYLE_LIGHT_POOL)}",
        f"  音频（产品 ASMR，恰好 1）: {' | '.join(STYLE_AUDIO_POOL[mode])}",
        "  禁止自造：短拖影、自然重力、阴沉冷色光 等非表内词",
        "【约束 constraints — 只写不要什么；须含全部核心】",
        f"  核心必选: {' | '.join(CONSTRAINTS_CORE)}",
        f"  产品常选: {' | '.join(CONSTRAINTS_EXTRA)}",
        "正交：空中雨/雾→environment；表面溅水→action；光线只选官方 light；"
        "慢放只用约束「无慢动作」，不要写拖影正面句。",
    ]
    return "\n".join(lines)


def _filter_in_pool(atoms: Sequence[str], pool: Sequence[str]) -> list[str]:
    allowed = set(pool)
    chosen = [a for a in atoms if a in allowed]
    return [p for p in pool if p in chosen]


def _normalize_camera_atoms(atoms: Sequence[str]) -> list[str]:
    mapped: list[str] = []
    for a in atoms:
        a = str(a).strip()
        if not a:
            continue
        mapped.append(_CAMERA_MOTION_ALIASES.get(a, a))
    return mapped


def clamp_closed_slots(
    slots: dict[str, list[str]],
    *,
    rain_mode: str | None = None,
) -> dict[str, list[str]]:
    """把 camera/style/constraints 钳回闭集池；缺省则填基线。"""
    mode = normalize_rain_mode(rain_mode)
    out = {k: list(v) for k, v in slots.items()}

    cam_raw = _normalize_camera_atoms(out.get("camera") or [])
    cam = _filter_in_pool(cam_raw, camera_pool())
    motion = next((a for a in cam if a in CAMERA_MOTION_POOL), "固定镜头")
    angle = next((a for a in cam if a in CAMERA_ANGLE_POOL), "平视")
    out["camera"] = [motion, angle]

    raw_style = [str(a).strip() for a in (out.get("style") or []) if str(a).strip()]
    # 兼容旧中文风格/光线 → 官方英文词
    _style_aliases = {
        "自然纪录片质感": "documentary",
        "写实自然风格": "natural",
        "电影胶片纪实调": "film tone",
        "均匀阴天漫射光": "overcast",
        "柔和阴天冷光": "overcast",
        "阴沉冷色光": "overcast",
        "阴沉冷色自然光": "overcast",
        "暗低对比冷光": "overcast",
        "暗而低对比冷色光": "overcast",
        "低对比阴湿自然光": "overcast",
    }
    raw_style = [_style_aliases.get(a, a) for a in raw_style]
    keywords = [a for a in raw_style if a in STYLE_KEYWORD_POOL]
    # 保持池顺序、最多 3 条
    keywords = [k for k in STYLE_KEYWORD_POOL if k in keywords][:3]
    if not keywords:
        keywords = list(_STYLE_KEYWORD_DEFAULT[mode])
    light = next((a for a in raw_style if a in STYLE_LIGHT_POOL), None)
    if light is None:
        light = _STYLE_LIGHT_DEFAULT[mode]
    audio = next((a for a in raw_style if a in STYLE_AUDIO_POOL[mode]), None)
    if audio is None:
        audio = STYLE_AUDIO_POOL[mode][0]
    out["style"] = [*keywords, light, audio]

    cons = _filter_in_pool(out.get("constraints") or [], constraints_pool())
    # 丢掉已并入其它槽的旧约束
    cons = [c for c in cons if c != "无运镜"]
    for req in CONSTRAINTS_CORE:
        if req not in cons:
            cons.append(req)
    out["constraints"] = [p for p in constraints_pool() if p in cons]

    for key in SLOT_ORDER:
        out.setdefault(key, [])
    return out


# 图生视频产品建议默认原子（提示词软引导；管线不再强制覆写槽位）
I2V_FIXED_CAMERA: tuple[str, ...] = ("固定机位拍摄",)
I2V_FIXED_STYLE: tuple[str, ...] = ("写实自然风格",)
I2V_FIXED_CONSTRAINTS: tuple[str, ...] = ("无人物",)


def i2v_product_locked_slots() -> dict[str, list[str]]:
    """兼容旧调用：返回产品建议默认原子，非强制锁。"""
    return {
        "camera": list(I2V_FIXED_CAMERA),
        "style": list(I2V_FIXED_STYLE),
        "constraints": list(I2V_FIXED_CONSTRAINTS),
    }


def apply_i2v_fixed_slots(slots: dict[str, list[str]]) -> dict[str, list[str]]:
    """兼容旧调用：六槽全开放，原样返回（不再强制注入固定项）。"""
    return {k: list(slots.get(k) or []) for k in SLOT_ORDER}


def product_locked_closed_slots(rain_mode: str | None = None) -> dict[str, list[str]]:
    """纯自然雨 ASMR：镜头/风格关键词/光线/约束固定；音频随雨档。

    LLM 基线只允许改 subject / action / environment。
    """
    mode = normalize_rain_mode(rain_mode)
    # 关键词顺序跟 STYLE_KEYWORD_POOL / clamp_closed_slots 一致
    keywords = [k for k in STYLE_KEYWORD_POOL if k in ("documentary", "moody", "desaturated")]
    return {
        "camera": list(_DEFAULT_CAMERA),  # 固定镜头 + 平视
        "style": [
            *keywords,
            "overcast",
            STYLE_AUDIO_POOL[mode][0],
        ],
        "constraints": list(_DEFAULT_CONSTRAINTS),
    }


def default_scenes() -> list[str]:
    return list(DEFAULT_SCENES)


def format_scenes(scenes: Sequence[str] | None) -> str:
    tags = [str(s).strip() for s in (scenes or []) if str(s).strip()]
    if not tags:
        tags = list(DEFAULT_SCENES)
    return " · ".join(tags)


def default_slots(rain_mode: str | None = None) -> dict[str, list[str]]:
    mode = normalize_rain_mode(rain_mode)
    ae = _ACTION_ENV[mode]
    locked = product_locked_closed_slots(mode)
    raw = {
        "subject": list(_SUBJECT_DEFAULT),
        "action": list(ae["action"]),
        "environment": list(ae["environment"]),
        **locked,
    }
    return clamp_closed_slots(raw, rain_mode=mode)


def default_atoms(rain_mode: str | None = None) -> dict[str, str]:
    return {
        k: " + ".join(v) for k, v in default_slots(rain_mode).items() if v
    }


def split_atoms(text: str) -> list[str]:
    raw = (text or "").strip()
    if not raw:
        return []
    if " + " in raw or raw.count("+") >= 1:
        parts = re.split(r"\s*\+\s*", raw)
    else:
        parts = re.split(r"[、，,;；|/]+", raw)
    return [p.strip() for p in parts if p.strip()]


def format_slot_line(slot: str, atoms: Sequence[str]) -> str:
    label = SLOT_LABELS.get(slot, slot)
    body = " + ".join(a.strip() for a in atoms if a.strip())
    return f"{label}：{body}" if body else f"{label}："


def format_table(slots: dict[str, Sequence[str]]) -> str:
    lines: list[str] = []
    for key in SLOT_ORDER:
        lines.append(format_slot_line(key, list(slots.get(key) or [])))
    return "\n".join(lines)


def parse_table(text: str) -> dict[str, list[str]]:
    slots: dict[str, list[str]] = {k: [] for k in SLOT_ORDER}
    label_to_key = {v: k for k, v in SLOT_LABELS.items()}
    label_to_key.update(
        {
            "场景": "environment",
            "scene": "environment",
            "环境": "environment",
            "主体": "subject",
            "动作": "action",
            "镜头": "camera",
            "运镜": "camera",
            "风格": "style",
            "约束": "constraints",
            "audio": "style",
            "音频": "style",
            "fx": "constraints",
            "timeline": "environment",
        }
    )

    raw = (text or "").strip()
    if not raw:
        return slots

    matched = False
    for line in raw.splitlines():
        line = line.strip()
        if not line:
            continue
        m = re.match(r"^([^\s：:]{1,8})\s*[：:]\s*(.*)$", line)
        if not m:
            continue
        key = label_to_key.get(m.group(1).strip())
        if key is None:
            continue
        slots[key] = split_atoms(m.group(2))
        matched = True

    if not matched:
        slots["environment"] = [raw]
    return slots


def compose_prompt(
    slots: dict[str, Sequence[str]] | None = None,
    *,
    rain_mode: str | None = None,
) -> str:
    src = slots if slots is not None else default_slots(rain_mode)
    parts: list[str] = []
    for key in SLOT_ORDER:
        for atom in src.get(key) or []:
            a = str(atom).strip().rstrip("，,。；;")
            if a:
                parts.append(a)
    if not parts:
        return ""
    return "，".join(parts) + "。"


def baseline_prompt(rain_mode: str | None = None) -> str:
    return format_table(default_slots(rain_mode))


def baseline_model_prompt(rain_mode: str | None = None) -> str:
    return compose_prompt(rain_mode=rain_mode)


def format_agy_account(email: str) -> str:
    addr = str(email or "").strip()
    if not addr:
        return "未配置 agy"
    ensure_cli_path()
    from agy.client import agy_label_for_email

    label = agy_label_for_email(addr)
    return f"{label} · {addr}" if label else addr


def active_agy_account_display() -> str:
    ensure_cli_path()
    from agy.client import (
        agy_email_for_label,
        get_active_agy_email,
        has_agy_credentials,
    )

    if not has_agy_credentials():
        return "未配置 agy"
    email = get_active_agy_email() or agy_email_for_label("japan") or ""
    return format_agy_account(email)


def rain_mode_brief(rain_mode: str | None = None) -> str:
    mode = normalize_rain_mode(rain_mode)
    label = RAIN_MODE_LABELS[mode]
    slots = default_slots(mode)
    return (
        f"目标雨档：{label}（{mode}）。\n"
        f"{format_table(slots)}\n"
        f"送模正文：{compose_prompt(slots)}"
    )


def _system_for_mode(
    rain_mode: str,
    *,
    scenes: Sequence[str] | None = None,
) -> str:
    mode = normalize_rain_mode(rain_mode)
    label = RAIN_MODE_LABELS[mode]
    scene_text = format_scenes(scenes)
    locked = product_locked_closed_slots(mode)
    return f"""你是即梦 Seedance 2.0 提示词工程师，专写「纯自然雨 ASMR · {scene_text} × {label}」。
遵循官方 6 步公式：主体→动作→环境→镜头→风格→约束。
参考指南：镜头与动作分离；只写一个主镜头指令；光线必写；约束用 avoid 类负面词。

创作必须紧扣场景：{scene_text}。禁止漂移到无关地貌/城市/室内/人物题材。

只输出一个 JSON（不要 markdown），键：
subject, action, environment
值为字符串数组（每槽 2–4 条短句可见结果）。
不要输出 camera / style / constraints —— 它们由产品固定，你无权改。

【开放槽 — 可自写短句，须是可见结果，且符合场景】
- subject：该场景下一个受雨主体（植被或地表等），禁止人物
- action：一个雨水互动结果（溅水、泄水或径流之一）
- environment：一个空间/空中雨雾/恒定性条件

【原子化硬规则】
1. 数组中的每一项只能表达一个主体、一个动作结果或一个环境条件（即单一语义断言）。
2. subject 禁止在同一项里并列多个对象：禁止「A与B」「A和B」「A、B」。
3. 例如 subject 应写「香蕉树」「宽大蕉叶」「热带乔木」，不要写「高大香蕉树与热带乔木」或「巨大蕉叶与浓密灌木」。
4. 不写无法从单帧稳定核验的相对形容词，如「高大」「巨大」；以具体物体名替代。
5. action/environment 可以用顿号或逗号补全同一个结果/条件；例如「该雨强已持续、开场即满、全程恒定无渐入」是一个“雨势时间连续性”原子，必须保留为一项。

【产品固定闭集（仅供对齐，勿输出、勿改写）】
- camera：{' + '.join(locked['camera'])}
- style：{' + '.join(locked['style'])}
- constraints：{' + '.join(locked['constraints'])}

正交：action=表面互动；environment=空间+空中雨/雾+恒定
禁止 epic/amazing；禁止闪电狂风；禁止分时段「0–3秒」剧本

当前雨档开放槽参考：
{format_table({k: default_slots(mode)[k] for k in OPEN_SLOTS})}
"""


def rewrite_atomic(
    draft: str = "",
    *,
    rain_mode: str | None = None,
    scenes: Sequence[str] | None = None,
    log_fn: LogFn | None = None,
) -> tuple[dict[str, list[str]], str]:
    """LLM 基线：只生成主体/动作/环境；镜头/风格/约束用产品固定值。

    返回 (slots, agy_email)。
    """
    ensure_cli_path()
    from agy import generate_text_via_agy_accounts, has_agy_credentials
    from agy.client import AGY_PROMPT_LABELS

    if not has_agy_credentials():
        raise RuntimeError("未配置 agy 凭据，无法原子化改写")

    mode = normalize_rain_mode(rain_mode)
    label = RAIN_MODE_LABELS[mode]
    scene_text = format_scenes(scenes)
    user = (
        f"请围绕场景「{scene_text}」为「{label}」档生成六槽中的开放三槽原子 JSON"
        f"（仅 subject/action/environment）。\n"
        f"若草稿非空，在其基础上改写；若草稿为空，按该档基线风格新写一批，"
        f"须与参考基线有可见差异，但仍属同一场景与雨档。\n\n"
        f"草稿：\n{(draft or '').strip() or '（空）'}"
    )
    text, email = generate_text_via_agy_accounts(
        user,
        model=_REWRITE_MODEL,
        effort="medium",
        system=_system_for_mode(mode, scenes=scenes),
        log_fn=log_fn,
        account_labels=AGY_PROMPT_LABELS,
    )
    open_slots = _parse_rewrite_json(text, fallback_mode=mode)
    locked = product_locked_closed_slots(mode)
    slots = {
        "subject": list(open_slots.get("subject") or []),
        "action": list(open_slots.get("action") or []),
        "environment": list(open_slots.get("environment") or []),
        **locked,
    }
    # 开放槽若解析失败则回退基线开放槽
    base = default_slots(mode)
    for key in OPEN_SLOTS:
        if not slots[key]:
            slots[key] = list(base[key])
    return slots, email


def check_tag_conflicts(
    slots: dict[str, Sequence[str]],
    *,
    rain_mode: str | None = None,
    scenes: Sequence[str] | None = None,
    log_fn: LogFn | None = None,
) -> tuple[dict[str, list[dict[str, object]]], str]:
    """用 LLM 检查当前六槽标签之间是否自相矛盾或重复表达。

    返回 ``({conflicts: [...], duplicates: [...]}, agy_email)``。
    只接受能精确对应到当前标签的冲突，避免模型泛泛评论时误标红。
    """
    ensure_cli_path()
    from agy import generate_text_via_agy_accounts, has_agy_credentials
    from agy.client import AGY_PROMPT_LABELS

    if not has_agy_credentials():
        raise RuntimeError("未配置 agy 凭据，无法进行生成前标签冲突检查")

    mode = normalize_rain_mode(rain_mode)
    label = RAIN_MODE_LABELS[mode]
    scene_text = format_scenes(scenes)
    current = {
        key: [str(atom).strip() for atom in (slots.get(key) or []) if str(atom).strip()]
        for key in SLOT_ORDER
    }
    system = f"""你是即梦 Seedance 2.0 的生成前提示词质检员。
任务：只检查下列六槽标签之间是否存在会让同一条视频无法同时成立的明确矛盾。
场景：{scene_text}；雨档：{label}。

判为冲突的例子：同一画面同时要求固定镜头与明显推拉/摇移；同时要求无人物与出现人物；
同时要求暴雨与无雨；同一主体同时要求静止不动与剧烈摆动。
不判为冲突：同一暴雨场景中树干稳定、叶片轻微摆动、雨水持续流淌；不同主体的正常共存；
只是风格不同、描述颗粒度不同、或无法确定的轻微张力。

只输出 JSON，不要 markdown：
{{"conflicts":[
  {{"tags":[{{"slot":"subject","tag":"必须逐字引用当前标签"}}, {{"slot":"action","tag":"必须逐字引用当前标签"}}],
    "reason":"一句话说明为什么无法同时成立"}}
],
"duplicates":[
  {{"tags":[{{"slot":"subject","tag":"必须逐字引用当前标签"}}, {{"slot":"environment","tag":"必须逐字引用当前标签"}}],
    "reason":"一句话说明重复表达了什么"}}
]}}
重复只指两个标签表达同一主体、状态或动作，删除其中一个不会损失信息。
描述相近但各自补充了数量、空间关系、动作强度或时间条件时不是重复。
若没有问题，输出 {{"conflicts":[],"duplicates":[]}}。每项必须列出至少两个当前标签；不得编造标签。"""
    user = f"请检查这些当前标签：\n{format_table(current)}"
    text, email = generate_text_via_agy_accounts(
        user,
        model=_REWRITE_MODEL,
        effort="medium",
        system=system,
        log_fn=log_fn,
        account_labels=AGY_PROMPT_LABELS,
    )
    return _parse_tag_conflicts(text, current), email


def _parse_tag_conflicts(
    text: str,
    current: dict[str, list[str]],
) -> dict[str, list[dict[str, object]]]:
    """解析并严格过滤 LLM 返回的冲突/重复标签，防止误提示。"""
    m = re.search(r"\{.*\}", text or "", re.DOTALL)
    if not m:
        return {"conflicts": [], "duplicates": []}
    try:
        data = json.loads(m.group(0))
    except json.JSONDecodeError:
        return {"conflicts": [], "duplicates": []}

    valid = {(slot, tag) for slot, tags in current.items() for tag in tags}
    def parse_items(raw_items: object) -> list[dict[str, object]]:
        if not isinstance(raw_items, list):
            return []
        out: list[dict[str, object]] = []
        seen: set[tuple[tuple[str, str], ...]] = set()
        for item in raw_items:
            if not isinstance(item, dict):
                continue
            refs: list[dict[str, str]] = []
            seen_ref: set[tuple[str, str]] = set()
            for ref in item.get("tags") or []:
                if not isinstance(ref, dict):
                    continue
                slot = str(ref.get("slot") or "").strip()
                tag = str(ref.get("tag") or "").strip()
                key = (slot, tag)
                if key in valid and key not in seen_ref:
                    seen_ref.add(key)
                    refs.append({"slot": slot, "tag": tag})
            if len(refs) < 2:
                continue
            fingerprint = tuple(sorted((r["slot"], r["tag"]) for r in refs))
            if fingerprint in seen:
                continue
            seen.add(fingerprint)
            reason = str(item.get("reason") or "标签描述存在重复或矛盾").strip()
            out.append({"tags": refs, "reason": reason or "标签描述存在重复或矛盾"})
        return out

    return {
        "conflicts": parse_items(data.get("conflicts")),
        "duplicates": parse_items(data.get("duplicates")),
    }


def replace_failed_atoms(
    slots: dict[str, Sequence[str]],
    failed: dict[str, Sequence[str]],
    *,
    rain_mode: str | None = None,
    scenes: Sequence[str] | None = None,
    log_fn: LogFn | None = None,
) -> tuple[dict[str, list[str]], str]:
    """用 LLM 替换红框可疑标签；未标红的标签保持不变。

    开放槽可自写；闭集槽须从池原样选取。返回 (新 slots, agy_email)。
    """
    ensure_cli_path()
    from agy import generate_text_via_agy_accounts, has_agy_credentials
    from agy.client import AGY_PROMPT_LABELS

    if not has_agy_credentials():
        raise RuntimeError("未配置 agy 凭据，无法替换可疑标签")

    mode = normalize_rain_mode(rain_mode)
    label = RAIN_MODE_LABELS[mode]
    scene_text = format_scenes(scenes)

    fail_map: dict[str, list[str]] = {}
    for key in SLOT_ORDER:
        tags = [str(t).strip() for t in (failed.get(key) or []) if str(t).strip()]
        if tags:
            fail_map[key] = tags
    if not fail_map:
        raise ValueError("没有红框可疑标签可替换")

    current = {
        key: [str(a).strip() for a in (slots.get(key) or []) if str(a).strip()]
        for key in SLOT_ORDER
    }
    fail_lines = "\n".join(
        f"- {SLOT_LABELS[k]}: {' | '.join(v)}" for k, v in fail_map.items()
    )
    system = f"""你是即梦 Seedance 2.0 提示词工程师，专写「纯自然雨 ASMR · {scene_text} × {label}」。
任务：只替换「可疑/不合格」标签，其余标签一字不改。
创作必须紧扣场景：{scene_text}。

只输出一个 JSON（不要 markdown）：
{{
  "replacements": {{
    "<slot>": {{ "<旧标签>": "<新标签>", ... }},
    ...
  }}
}}
slot 只能是：subject, action, environment, camera, style, constraints。
新标签规则：
- subject/action/environment：可自写短句可见结果，须符合场景与雨档；每一项必须是一个语义断言。subject 禁止「A与B」「A和B」「A、B」等并列对象；action/environment 可用顿号或逗号补全同一结果/条件（如雨势时间连续性）。不要用「高大」「巨大」等不可稳定核验的相对形容词
- 【保真压缩】新标签必须是信息不丢失的最短电报式短语：保留数量、主体、必要的景别/空间关系、动作/状态和必要限定；删除「画面中、可以看到、排列着、分布的、正在、呈现、进行着」等不增加可见信息的语法填充，不要写完整句。
- 示例：保留景别、数量、前后交错关系和主体时，「中景排列着五株前后交错分布的野芭蕉树」应写成「中景五株交错野芭蕉树」。不得把它缩成「芭蕉树」而丢失数量或交错关系。
- 不添加旧标签没有的对象、数量、关系或动作；一个标签只输出一个短语。
- camera：必须从池原样选：{' | '.join(camera_pool())}
- style：必须从池原样选：{' | '.join(style_pool(mode))}
- constraints：必须从池原样选：{' | '.join(constraints_pool())}
禁止把旧标签原样写回；禁止改未列出的标签。
"""
    user = (
        f"当前六槽：\n{format_table(current)}\n\n"
        f"须替换的可疑标签：\n{fail_lines}\n\n"
        f"请为每条可疑标签给出符合场景「{scene_text}」的替代标签。"
    )
    text, email = generate_text_via_agy_accounts(
        user,
        model=_REWRITE_MODEL,
        effort="medium",
        system=system,
        log_fn=log_fn,
        account_labels=AGY_PROMPT_LABELS,
    )
    replacements = _parse_replacements_json(text)
    out = {k: list(v) for k, v in current.items()}
    for key, mapping in replacements.items():
        if key not in out or not isinstance(mapping, dict):
            continue
        new_list: list[str] = []
        for atom in out[key]:
            if atom in fail_map.get(key, []):
                replacements_for_atom = mapping.get(atom) or []
                if replacements_for_atom and replacements_for_atom != [atom]:
                    new_list.extend(replacements_for_atom)
                else:
                    # LLM 未给出有效替换则保留，留给人工
                    new_list.append(atom)
            else:
                new_list.append(atom)
        # 去重保序
        seen: set[str] = set()
        cleaned: list[str] = []
        for a in new_list:
            if a not in seen:
                seen.add(a)
                cleaned.append(a)
        out[key] = cleaned

    out = clamp_closed_slots(out, rain_mode=mode)
    return out, email


def _parse_replacements_json(text: str) -> dict[str, dict[str, list[str]]]:
    m = re.search(r"\{.*\}", text or "", re.DOTALL)
    if not m:
        return {}
    try:
        data = json.loads(m.group(0))
    except json.JSONDecodeError:
        return {}
    raw = data.get("replacements") if isinstance(data, dict) else None
    if not isinstance(raw, dict):
        # 兼容直接给 slot→{old:new}
        raw = data if isinstance(data, dict) else {}
    out: dict[str, dict[str, list[str]]] = {}
    for key in SLOT_ORDER:
        val = raw.get(key)
        if not isinstance(val, dict):
            continue
        mapping: dict[str, list[str]] = {}
        for old, new in val.items():
            o = str(old).strip()
            new_atoms = _atomic_open_atoms(new, slot=key)
            if o and new_atoms:
                mapping[o] = new_atoms
        if mapping:
            out[key] = mapping
    return out


def _parse_rewrite_json(text: str, *, fallback_mode: str) -> dict[str, list[str]]:
    m = re.search(r"\{.*\}", text or "", re.DOTALL)
    if not m:
        return {k: list(default_slots(fallback_mode)[k]) for k in OPEN_SLOTS}
    try:
        data = json.loads(m.group(0))
    except json.JSONDecodeError:
        parsed = parse_table(_strip_fence(text))
        if any(parsed.get(k) for k in OPEN_SLOTS):
            return _atomicize_open_slots(parsed)
        return {k: list(default_slots(fallback_mode)[k]) for k in OPEN_SLOTS}

    out: dict[str, list[str]] = {k: [] for k in SLOT_ORDER}
    for key in SLOT_ORDER:
        val = data.get(key)
        if isinstance(val, list):
            out[key] = [str(x).strip() for x in val if str(x).strip()]
        elif isinstance(val, str) and val.strip():
            out[key] = split_atoms(val)
    if not any(out.get(k) for k in OPEN_SLOTS):
        return {k: list(default_slots(fallback_mode)[k]) for k in OPEN_SLOTS}
    return _atomicize_open_slots(out)


_SUBJECT_OBJECT_SPLIT_RE = re.compile(r"\s*(?:以及|与|和|及|、)\s*")
_UNVERIFIABLE_SIZE_PREFIX_RE = re.compile(r"^(?:高大|巨大)\s*")


def _atomic_open_atoms(value: object, *, slot: str) -> list[str]:
    """规范 LLM 的开放槽输出为单一语义断言。

    只有 subject 会拆分并列对象；action/environment 中的顿号、逗号可能
    是同一结果/条件的必要限定，不能按标点机械拆分。
    此兜底只作用于 LLM 生成/替换结果；不会改写用户手工维护的既有标签。
    """
    raw_items = value if isinstance(value, list) else [value]
    out: list[str] = []
    seen: set[str] = set()
    for raw in raw_items:
        text = str(raw or "").strip()
        if not text:
            continue
        parts = _SUBJECT_OBJECT_SPLIT_RE.split(text) if slot == "subject" else [text]
        for part in parts:
            atom = _UNVERIFIABLE_SIZE_PREFIX_RE.sub("", part.strip())
            if atom and atom not in seen:
                seen.add(atom)
                out.append(atom)
    return out


def _atomicize_open_slots(slots: dict[str, list[str]]) -> dict[str, list[str]]:
    out = {key: list(vals) for key, vals in slots.items()}
    for key in OPEN_SLOTS:
        out[key] = _atomic_open_atoms(out.get(key) or [], slot=key)
    return out


def _strip_fence(text: str) -> str:
    t = (text or "").strip()
    if t.startswith("```"):
        lines = t.splitlines()
        if lines and lines[0].startswith("```"):
            lines = lines[1:]
        if lines and lines[-1].strip() == "```":
            lines = lines[:-1]
        t = "\n".join(lines).strip()
    return t.strip()


def atoms_doc_path():
    return t2v_lab_dir() / "prompt_atoms.md"


def pools_doc_path():
    return t2v_lab_dir() / "atom_pools.md"


__all__ = [
    "ATOM_ORDER",
    "CAMERA_ANGLE_POOL",
    "CAMERA_MOTION_POOL",
    "CONSTRAINTS_CORE",
    "CONSTRAINTS_EXTRA",
    "DEFAULT_RAIN_MODE",
    "DEFAULT_SCENES",
    "LOCKED_SLOTS",
    "OPEN_SLOTS",
    "RAIN_MODES",
    "RAIN_MODE_IDS",
    "RAIN_MODE_LABELS",
    "SCENE_SEED_POOL",
    "SLOT_LABELS",
    "SLOT_ORDER",
    "STYLE_AUDIO_POOL",
    "STYLE_KEYWORD_POOL",
    "STYLE_LIGHT_POOL",
    "active_agy_account_display",
    "atoms_doc_path",
    "baseline_model_prompt",
    "baseline_prompt",
    "camera_pool",
    "check_tag_conflicts",
    "clamp_closed_slots",
    "compose_prompt",
    "constraints_pool",
    "default_atoms",
    "default_scenes",
    "default_slots",
    "format_agy_account",
    "format_pool_block",
    "format_scenes",
    "format_slot_line",
    "format_table",
    "normalize_rain_mode",
    "parse_table",
    "pools_doc_path",
    "product_locked_closed_slots",
    "rain_mode_brief",
    "replace_failed_atoms",
    "rewrite_atomic",
    "split_atoms",
    "style_pool",
]
