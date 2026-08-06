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

# 主体：画面里有什么（决定「拍到多大范围」，替代焦距/广角）
_SUBJECT_DEFAULT: tuple[str, ...] = (
    "高大香蕉树与热带乔木",
    "巨大蕉叶与浓密灌木",
    "粗壮树干与湿润地面",
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


def default_slots(rain_mode: str | None = None) -> dict[str, list[str]]:
    mode = normalize_rain_mode(rain_mode)
    ae = _ACTION_ENV[mode]
    raw = {
        "subject": list(_SUBJECT_DEFAULT),
        "action": list(ae["action"]),
        "environment": list(ae["environment"]),
        "camera": list(_DEFAULT_CAMERA),
        "style": _default_style_atoms(mode),
        "constraints": list(_DEFAULT_CONSTRAINTS),
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


def _system_for_mode(rain_mode: str) -> str:
    mode = normalize_rain_mode(rain_mode)
    label = RAIN_MODE_LABELS[mode]
    return f"""你是即梦 Seedance 2.0 提示词工程师，专写「原始热带雨林 × {label}」。
遵循官方 6 步公式：主体→动作→环境→镜头→风格→约束。
参考指南：镜头与动作分离；只写一个主镜头指令；光线必写；约束用 avoid 类负面词。

只输出一个 JSON（不要 markdown），键：
subject, action, environment, camera, style, constraints
值为字符串数组。

【开放槽 — 可自写短句，须是可见结果】
- subject：雨林受雨体（蕉叶/树干/地面），禁止人物
- action：该雨档的密度/溅水/泄水/径流可见结果
- environment：雨林空间、水雾能见度、开场即满强度且全程恒定

【闭集槽 — 必须从池中原样复制字符串，禁止同义改写、禁止自造】
{format_pool_block(mode)}

选池硬规则：
1. camera：恰好「固定镜头」+「平视|仰视|俯视」各 1 条
2. style：官方风格关键词 1–3 条 + 官方光线 1 条 + 产品音频 1 条；禁止短拖影/自然重力等自造词
3. constraints：含全部核心必选（含「无慢动作」）；不要写「无运镜」
4. 正交：action=表面互动；environment=空间+空中雨/雾+恒定
5. 禁止 epic/amazing；禁止闪电狂风；禁止分时段「0–3秒」剧本

当前雨档基线参考：
{format_table(default_slots(mode))}
"""


def rewrite_atomic(
    draft: str,
    *,
    rain_mode: str | None = None,
    log_fn: LogFn | None = None,
) -> tuple[str, str]:
    """改写为六槽表格；镜头/风格/约束钳回闭集池。"""
    ensure_cli_path()
    from agy import generate_text_via_agy_accounts, has_agy_credentials
    from agy.client import AGY_PROMPT_LABELS

    if not has_agy_credentials():
        raise RuntimeError("未配置 agy 凭据，无法原子化改写")

    mode = normalize_rain_mode(rain_mode)
    label = RAIN_MODE_LABELS[mode]
    user = (
        f"请把草稿改写成「{label}」档六槽原子 JSON。"
        f"camera/style/constraints 必须从系统提示的池中原样选取。"
        f"若草稿为空，输出该档基线。\n\n"
        f"草稿：\n{(draft or '').strip() or '（空）'}"
    )
    text, email = generate_text_via_agy_accounts(
        user,
        model=_REWRITE_MODEL,
        effort="medium",
        system=_system_for_mode(mode),
        log_fn=log_fn,
        account_labels=AGY_PROMPT_LABELS,
    )
    slots = _parse_rewrite_json(text, fallback_mode=mode)
    slots = clamp_closed_slots(slots, rain_mode=mode)
    return format_table(slots), email


def _parse_rewrite_json(text: str, *, fallback_mode: str) -> dict[str, list[str]]:
    m = re.search(r"\{.*\}", text or "", re.DOTALL)
    if not m:
        return default_slots(fallback_mode)
    try:
        data = json.loads(m.group(0))
    except json.JSONDecodeError:
        parsed = parse_table(_strip_fence(text))
        if any(parsed.values()):
            return parsed
        return default_slots(fallback_mode)

    out: dict[str, list[str]] = {k: [] for k in SLOT_ORDER}
    for key in SLOT_ORDER:
        val = data.get(key)
        if isinstance(val, list):
            out[key] = [str(x).strip() for x in val if str(x).strip()]
        elif isinstance(val, str) and val.strip():
            out[key] = split_atoms(val)
    if not any(out.values()):
        return default_slots(fallback_mode)
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
    "RAIN_MODES",
    "RAIN_MODE_IDS",
    "RAIN_MODE_LABELS",
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
    "clamp_closed_slots",
    "compose_prompt",
    "constraints_pool",
    "default_atoms",
    "default_slots",
    "format_agy_account",
    "format_pool_block",
    "format_slot_line",
    "format_table",
    "normalize_rain_mode",
    "parse_table",
    "pools_doc_path",
    "rain_mode_brief",
    "rewrite_atomic",
    "split_atoms",
    "style_pool",
]
