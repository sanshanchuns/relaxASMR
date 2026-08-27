"""参考图 / 主体关键词 → 三档雨强的送模 prompt。

送模正文四段：画面 · 光影 · 动态 · 约束。
约束即原来的断言，并进 prompt；后验仍从【约束】抽出逐条核对。
"""

from __future__ import annotations

import json
import mimetypes
import re
from collections.abc import Callable
from dataclasses import dataclass, field
from pathlib import Path

from scripts.aigc_lab.rain_modes import RAIN_MODES, normalize_rain_mode
from scripts.aigc_lab.subject_pool import format_subjects
from scripts.config.paths import ensure_cli_path

LogFn = Callable[[str], None]

_MODEL = "gemini-3.7-flash"
_JSON_BLOCK = re.compile(r"\{.*\}", re.DOTALL)

#: 送模正文的固定顺序。约束 = 原断言。
PROMPT_PARTS: tuple[tuple[str, str], ...] = (
    ("visual", "画面"),
    ("lighting", "光影"),
    ("motion", "动态"),
    ("constraints", "约束"),
)
_PART_LABELS = tuple(label for _key, label in PROMPT_PARTS)
_LABEL_TO_KEY = {label: key for key, label in PROMPT_PARTS}
_PART_SPLIT = re.compile(
    r"【(" + "|".join(_PART_LABELS) + r")】"
)

#: Seedance 2.0 Fast 的经验性避坑规则。
#:
#: 这些是人为经验，不是模型的真实行为说明——后验手册攒够样本后应当回来修正这里。
SEEDANCE_GUARDRAILS: tuple[str, ...] = (
    "写具体物理事件和可见结果，不要堆形容词。"
    "「暴雨如注」是形容词，「雨水沿屋檐连成水柱砸进积水、溅起水花冠」才是模型能执行的指令。",
    "不要要求剧烈、舞蹈式的规律晃动——"
    "需要动感时写小幅平滑摆动即可，雨丝保持匀速下落。",
    "不写分时段剧本（「0–3 秒…3–6 秒…」）。片长只有几秒，撑不起分镜。",
    "只给一条镜头指令，且必须是固定机位。镜头运动会毁掉素材的可用性。",
    "禁止 epic / amazing / cinematic masterpiece 这类空泛评价词，它们不携带画面信息。",
    "禁止人物、人脸、人手入画。",
    "雨势开场即满、全程恒定，不要渐入渐强。",
    "不写闪电、狂风、剧烈天气事件——雨 ASMR 要的是稳定的白噪声质感。",
    "光线必须写明（例如阴天漫射光），否则模型自由发挥容易忽明忽暗。",
    "构图硬规则：必须写清纵深三层「前景/中景/远景」。"
    "每层用「专业词（白话位置+具体物）」双标注，例如「前景（近处海芋阔叶）」。"
    "只写近处/远处不够。构图可与参考图不同，但不能缺层、不能只堆主体名词。",
    "虚实必须落在层上：写明哪一层唯一清晰（通常中景对焦），前景/远景如何虚化；"
    "禁止只用「朦胧」代替光学浅景深。",
    "三档共用同一构图（同一景别、同一前景中景远景布局、同一对焦点），只改雨强与受雨结果。",
)


class PromptGenError(RuntimeError):
    pass


def _clean_lines(items: list[str] | tuple[str, ...] | None) -> list[str]:
    out: list[str] = []
    for raw in items or []:
        text = str(raw).strip().strip("。").lstrip("·- ")
        if text:
            out.append(text)
    return out


def constraints_to_assertions(raw: str) -> list[str]:
    """把【约束】段拆成后验用的一条一事。"""
    return _clean_lines(re.split(r"[。\n]+", raw or ""))


def compose_prompt(
    *,
    visual: str = "",
    lighting: str = "",
    motion: str = "",
    constraints: list[str] | tuple[str, ...] | None = None,
) -> str:
    """四段拼成送模正文。空段省略。"""
    values = {
        "visual": (visual or "").strip(),
        "lighting": (lighting or "").strip(),
        "motion": (motion or "").strip(),
        "constraints": "。".join(_clean_lines(list(constraints or []))),
    }
    if values["constraints"]:
        values["constraints"] += "。"
    blocks = [
        f"【{label}】{values[key]}"
        for key, label in PROMPT_PARTS
        if values[key]
    ]
    return "\n".join(blocks)


def parse_prompt_parts(text: str) -> dict[str, str]:
    """从送模正文拆回四段；无标签则全部空。"""
    parts = {key: "" for key, _label in PROMPT_PARTS}
    matches = list(_PART_SPLIT.finditer(text or ""))
    if not matches:
        return parts
    for i, match in enumerate(matches):
        end = matches[i + 1].start() if i + 1 < len(matches) else len(text)
        key = _LABEL_TO_KEY[match.group(1)]
        parts[key] = (text or "")[match.end() : end].strip()
    return parts


def assertions_from_prompt(
    prompt: str, *, fallback: list[str] | None = None
) -> list[str]:
    found = constraints_to_assertions(parse_prompt_parts(prompt).get("constraints", ""))
    if found:
        return found
    return _clean_lines(fallback)


@dataclass
class RainPrompt:
    """一档雨强的送模文本；assertions 与【约束】同源。"""

    rain_mode: str
    prompt: str
    assertions: list[str] = field(default_factory=list)

    def to_dict(self) -> dict:
        return {
            "rain_mode": self.rain_mode,
            "prompt": self.prompt,
            "assertions": list(self.assertions),
        }

    @classmethod
    def from_dict(cls, data: dict) -> RainPrompt:
        mode = normalize_rain_mode(data.get("rain_mode"))
        visual = str(data.get("visual") or data.get("scene") or "").strip()
        lighting = str(data.get("lighting") or data.get("light") or "").strip()
        motion = str(data.get("motion") or data.get("dynamics") or "").strip()
        if not (visual or lighting or motion):
            visual = str(data.get("multi") or "").strip()
            lighting = str(data.get("effect") or "").strip()
            motion = str(data.get("action") or "").strip()
            rhythm = str(data.get("rhythm") or "").strip()
            if rhythm and visual:
                visual = f"{rhythm}。{visual}"
            elif rhythm:
                visual = rhythm
        constraints = data.get("constraints")
        if isinstance(constraints, str):
            constraint_items = constraints_to_assertions(constraints)
        else:
            constraint_items = _clean_lines(
                list(constraints or data.get("assertions") or [])
            )
        prompt = str(data.get("prompt") or "").strip()
        if visual or lighting or motion:
            prompt = compose_prompt(
                visual=visual,
                lighting=lighting,
                motion=motion,
                constraints=constraint_items,
            )
        elif prompt and constraint_items and "【约束】" not in prompt:
            prompt = f"{prompt.rstrip()}\n【约束】{'。'.join(constraint_items)}。"
        assertions = assertions_from_prompt(prompt, fallback=constraint_items)
        return cls(rain_mode=mode, prompt=prompt, assertions=assertions)


@dataclass
class PromptSet:
    """一次生成的完整产物：三档 prompt + 主体锚点。"""

    subjects: list[str] = field(default_factory=list)
    prompts: list[RainPrompt] = field(default_factory=list)
    reviewer: str = ""

    def by_mode(self, mode: str) -> RainPrompt | None:
        target = normalize_rain_mode(mode)
        for p in self.prompts:
            if p.rain_mode == target:
                return p
        return None


def _guardrails_block(extra: tuple[str, ...] | list[str] | None = None) -> str:
    rules = list(SEEDANCE_GUARDRAILS) + [str(x).strip() for x in (extra or []) if str(x).strip()]
    return "\n".join(f"{i}. {r}" for i, r in enumerate(rules, start=1))


def _rain_block() -> str:
    lines: list[str] = []
    for m in RAIN_MODES:
        lines.append(f"- {m.mode_id}（{m.display}）：{m.baseline}")
    return "\n".join(lines)


def build_system(*, extra_rules: tuple[str, ...] | list[str] | None = None) -> str:
    return f"""你是即梦 Seedance 2.0 Fast 的提示词工程师，为「雨 ASMR」长视频生产素材。
素材会被剪成长时段环境视频，所以每条都要是固定机位、恒定雨势的稳定空镜。
题材不限于纯自然：小船、木屋、栈道这类人造物同样是合格主体。
Seedance 吃得动细约束；缺构图才会漂。宁可把层次写死，也不要只列主体。

【模型避坑规则 — 必须全部遵守】
{_guardrails_block(extra_rules)}

【构图精度（即梦确认：专业词优先，双标注最稳）】
纵深层次用「前景 / 中景 / 远景」，识别优先级高于「近处 / 远处」。
每层写法：专业词（白话位置 + 具体元素），例如「前景（近处阔叶，画面右侧约三分之一）」。
再写左右或占比、谁清晰谁虚，避免主体套错层。
镜头景别（大远景/全景/中景/近景/特写）≠ 纵深中景。景别和层次都写在【画面】段。

【三档雨强的语义基线】
{_rain_block()}
三档必须共用同一个主体、同一套构图和同一套光影布局，只让雨强与它引发的物理结果发生变化。
档与档之间要有肉眼可分辨的差距，不能只是换形容词。

【输出】
只输出一个 JSON（不要 markdown 代码块），结构：
{{"subjects": ["主体1", "主体2"],
  "modes": [
    {{"rain_mode": "light_mod",
      "visual": "固定机位+景别+写实浅景深。前景（…）…；中景（…）…；远景（…）…",
      "lighting": "基调、光源位置与冷暖、谁被照亮、无溢光",
      "motion": "该档雨丝、叶面流水、绿植轻微平滑摆动",
      "constraints": ["断言1", "断言2"]}},
    {{"rain_mode": "heavy", "visual": "…", "lighting": "…", "motion": "…", "constraints": []}},
    {{"rain_mode": "storm", "visual": "…", "lighting": "…", "motion": "…", "constraints": []}}
  ]}}

四段会按固定顺序拼成送模正文：【画面】【光影】【动态】【约束】。
- 画面：固定机位 + 镜头景别（格式「景别：中景」）+ 写实、浅景深、不裁切主体。必须覆盖前景、中景、远景三层；每层「专业词（白话位置+具体物+左右占比）」+ 该层虚实。通常中景唯一清晰。三档同一景别、同一构图。不要把雨丝或光源写进本段。
- 光影：基调（冷暗雨夜 / 阴天漫射等）；光源数量、位置、冷暖；哪一层被照亮、其余自然暗下去；明确无其它光源、无溢光。不要把雨丝写进本段。
- 动态：该档雨丝密度与下落方式；水沿叶面/檐口如何流动；绿植轻微平滑摆动（可写约 3 秒一周期）；雾气若有则同步缓流。首尾帧位置与运动状态吻合，便于无缝循环。不要人物、不要台词、不要「宁静/治愈」这类情绪词。禁止剧烈/舞蹈式晃动、禁止慢动作。
- constraints：4–6 条，后验核对用，会原样写入【约束】。一条一事、可从画面判真假；至少一条该档雨强可见证据；至少一条否定式（无人物、镜头全程固定、无运镜无切镜无慢动作）；至少一条构图/虚实（例如中景唯一清晰、前景呈虚化剪影）；至少一条「不要生成音乐」。"""


def _build_user(
    *,
    subjects: list[str],
    has_image: bool,
    note: str,
) -> str:
    parts: list[str] = []
    if has_image:
        parts.append(
            "参考原图的主体纹理、色调与雨夜氛围，严格执行以下约束。"
            "只借用受雨主体与材质，不要复制参考图的左右占比、摆位或原构图；"
            "必须自拟一套完整纵深构图（前景/中景/远景双标注 + 对焦点），三档共用。"
        )
    if subjects:
        parts.append(f"指定主体：{format_subjects(subjects)}。")
    if not subjects and not has_image:
        raise PromptGenError("既没有参考图也没有主体关键词，无法生成")
    if note.strip():
        parts.append(f"补充要求：{note.strip()}")
    parts.append("请输出三档 JSON。")
    return "\n".join(parts)


def _load_image(path: Path) -> list[tuple[str, bytes]]:
    mime, _ = mimetypes.guess_type(path.name)
    return [(mime or "image/png", path.read_bytes())]


def _parse(text: str) -> tuple[list[str], list[RainPrompt]]:
    m = _JSON_BLOCK.search(text or "")
    if not m:
        raise PromptGenError(f"模型输出里没有 JSON：{(text or '')[:200]}")
    try:
        data = json.loads(m.group(0))
    except json.JSONDecodeError as exc:
        raise PromptGenError(f"JSON 解析失败：{exc}") from exc

    subjects = [str(s).strip() for s in (data.get("subjects") or []) if str(s).strip()]
    by_mode: dict[str, RainPrompt] = {}
    for entry in data.get("modes") or []:
        if not isinstance(entry, dict):
            continue
        item = RainPrompt.from_dict(entry)
        if item.prompt:
            by_mode[item.rain_mode] = item

    missing = [m.mode_id for m in RAIN_MODES if m.mode_id not in by_mode]
    if missing:
        raise PromptGenError(f"模型漏了雨档：{'/'.join(missing)}")
    return subjects, [by_mode[m.mode_id] for m in RAIN_MODES]


def generate_rain_prompts(
    *,
    subjects: list[str] | None = None,
    ref_image: Path | None = None,
    note: str = "",
    extra_rules: tuple[str, ...] | list[str] | None = None,
    log_fn: LogFn | None = None,
) -> PromptSet:
    """一次调用产出三档四段 prompt；约束即断言。

    ``ref_image`` 只作主体/材质锚点，不做图生视频——构图仍由文生视频决定。
    """
    log = log_fn or (lambda _m: None)
    ensure_cli_path()
    from agy import generate_text_via_agy_accounts, has_agy_credentials
    from agy.client import AGY_IMAGE_LABELS, AGY_PROMPT_LABELS

    if not has_agy_credentials():
        raise PromptGenError("未配置 agy 凭据（cli/agy/credentials.json）")

    picked = [str(s).strip() for s in (subjects or []) if str(s).strip()]
    image = ref_image if ref_image and Path(ref_image).is_file() else None
    user = _build_user(subjects=picked, has_image=image is not None, note=note)

    log(f"[AIGC] 生成三档提示词（主体：{format_subjects(picked) or '看图'}）…")
    text, email = generate_text_via_agy_accounts(
        user,
        model=_MODEL,
        effort="medium",
        system=build_system(extra_rules=extra_rules),
        images=_load_image(Path(image)) if image else None,
        log_fn=log_fn,
        account_labels=AGY_IMAGE_LABELS if image else AGY_PROMPT_LABELS,
    )
    detected, prompts = _parse(text)
    result = PromptSet(
        subjects=picked or detected,
        prompts=prompts,
        reviewer=email,
    )
    log(
        f"[AIGC] 三档就绪 · 主体 {format_subjects(result.subjects) or '—'} · "
        + " / ".join(f"{p.rain_mode}:{len(p.assertions)}条断言" for p in prompts)
    )
    return result
