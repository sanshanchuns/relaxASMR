"""出图：文生图（待选种子图）与图生图（同系列图），都走 agy Gemini。

调用链：

* ``generate_seed_candidates`` → 文生图，一个 idea 出 N 张候选 → ``seed_candidates/NNN.png``
* ``generate_series_images``   → 图生图（带 ``images=[种子图]``，走 inlineData）→ ``series_image/series_NNN.png``

每张图独立提交、独立失败：某一张挂了不影响其余，失败信息记录在条目的 ``error`` 上，
GUI 里能直接看到是哪一张、为什么失败。

**两道闸门**（详见 ``review.py`` 的模块文档）：

1. 提示词发给模型**之前**过 ``instructions/rain_asmr_image_prompt.md`` + 子系列覆盖层的
   机器校验，不通过就不消耗额度；
2. 图出来之后交给 Gemini 看图评审 —— 种子图判它属于哪个子系列，系列图判它有没有守住
   本批次的系列意图。agy 挂了直接抛错，不继续往下走。
"""

from __future__ import annotations

import mimetypes
from collections.abc import Callable
from pathlib import Path

from scripts.config.paths import series_seed_image_dir, series_series_image_dir
from scripts.series_video.prompt_rules import ensure_image_prompt
from scripts.series_video.series_prompt_gen import generate_series_image_prompts
from scripts.series_video.seed_prompt_gen import generate_seed_prompts_from_keywords
from scripts.series_video.prompts import IMAGE_SYSTEM_PROMPT, ImageVariant
from scripts.series_video.review import classify_seed_image, review_image
from scripts.series_video.store import (
    BatchMeta,
    SeedCandidate,
    SeriesItem,
    seed_raw_name,
    series_image_name,
)

LogFn = Callable[[str], None]
ProgressFn = Callable[[int, int, SeriesItem], None]
CandidateProgressFn = Callable[[int, int, SeedCandidate], None]

_EXT_BY_MIME = {
    "image/png": ".png",
    "image/jpeg": ".jpg",
    "image/webp": ".webp",
}


def _guess_mime(path: Path) -> str:
    mime, _ = mimetypes.guess_type(path.name)
    return mime or "image/png"


def generate_seed_candidates(
    meta: BatchMeta,
    *,
    count: int,
    idea: str = "",
    series_id: str = "",
    log_fn: LogFn | None = None,
    on_item: CandidateProgressFn | None = None,
    should_stop: Callable[[], bool] | None = None,
) -> list[SeedCandidate]:
    """用文生图产出 *count* 张待选种子图，追加进 ``meta.seed_candidates``。

    ``idea`` 是用户输入的几个**关键字**（不是完整 prompt）；Gemini 会结合子系列约束
    随机产出 *count* 条四段式 prompt，再逐张文生图。

    每张出图后都会让 Gemini 看图判它**实际**落在哪个子系列 —— 提示词写的是暴雨，
    出来是细雨也是常事，以画面为准。判不出来的（三个都不适合）标成不合格，
    候选图不会自动成为种子图，用户在 GUI 里挑一张再由
    :func:`store.adopt_seed_candidate` 定稿。
    """
    log = log_fn or (lambda _m: None)

    from scripts.config.paths import ensure_cli_path

    ensure_cli_path()
    from agy.image import generate_image_via_agy_accounts

    plan = generate_seed_prompts_from_keywords(
        keywords=idea,
        series_id=series_id,
        count=count,
        log_fn=log_fn,
    )
    out_dir = series_seed_image_dir(meta.batch_id)
    out_dir.mkdir(parents=True, exist_ok=True)
    if idea.strip():
        meta.seed_idea = idea.strip()

    created: list[SeedCandidate] = []
    for n, variant in enumerate(plan, start=1):
        if should_stop is not None and should_stop():
            log(f"[种子图] 已取消，完成 {len(created)}/{len(plan)} 张")
            break

        index = meta.next_raw_index()
        cand = SeedCandidate(
            name=seed_raw_name(meta.seed_index, index, ".png"),
            prompt=variant.to_prompt(),
            summary=variant.summary(),
        )
        log(f"[种子图] {n}/{len(plan)} 生成中：{cand.summary} …")
        try:
            ensure_image_prompt(cand.prompt, variant.series_id)
            data, mime, email = generate_image_via_agy_accounts(
                cand.prompt,
                aspect_ratio=meta.aspect_ratio,
                system=variant.system_prompt(),
                log_fn=log_fn,
            )
        except Exception as exc:  # noqa: BLE001 - 单张失败不应中断整批
            cand.error = str(exc)
            log(f"[种子图] {n}/{len(plan)} 失败：{exc}")
        else:
            cand.name = seed_raw_name(meta.seed_index, index, _EXT_BY_MIME.get(mime, ".png"))
            (out_dir / cand.name).write_bytes(data)
            log(f"[种子图] {n}/{len(plan)} 完成：{cand.name}（{len(data)} bytes，{email}）")
            verdict = classify_seed_image(
                out_dir / cand.name, prompt=cand.prompt, log_fn=log_fn
            )
            cand.series_id = verdict.series_id
            cand.review = verdict.to_dict()
            if verdict.blocked:
                cand.error = f"系列判定不合格：{'；'.join(verdict.issues) or '未给出理由'}"

        meta.seed_candidates.append(cand)
        meta.save()
        created.append(cand)
        if on_item is not None:
            on_item(n, len(plan), cand)

    return created


def classify_batch_seed(meta: BatchMeta, *, log_fn: LogFn | None = None):
    """给已定稿的种子图判子系列，写进 ``meta.series_id``。

    外部导入的种子图没走过文生图那条链路，也就没经过分类；这里补上，
    保证「不论种子图从哪来，整批的系列都是看图判出来的」。
    """
    log = log_fn or (lambda _m: None)
    seed = meta.seed_path
    if not seed.is_file():
        raise FileNotFoundError(f"种子图不存在：{seed}")
    verdict = classify_seed_image(seed, prompt=meta.seed_prompt, log_fn=log_fn)
    meta.seed_review = verdict.to_dict()
    if verdict.series_id:
        meta.series_id = verdict.series_id
        log(f"[种子图] 判定为子系列：{verdict.series_id}")
    else:
        log(f"[种子图] 三个子系列都不适合：{'；'.join(verdict.issues) or '未给出理由'}")
    meta.save()
    return verdict


def generate_series_images(
    meta: BatchMeta,
    *,
    count: int,
    constraints: str = "",
    log_fn: LogFn | None = None,
    on_item: ProgressFn | None = None,
    variants: list[ImageVariant] | None = None,
    should_stop: Callable[[], bool] | None = None,
) -> list[SeriesItem]:
    """基于 ``meta`` 的种子图生成 *count* 张同系列图，追加进 ``meta.items``。

    每条 prompt 由 Gemini 根据种子图 + ``constraints``（限定词）+ 子系列约束生成；
    再图生图出片并评审。
    """
    log = log_fn or (lambda _m: None)
    seed = meta.seed_path
    if not seed.is_file():
        raise FileNotFoundError(f"种子图不存在：{seed}")

    if constraints.strip():
        meta.series_constraints = constraints.strip()
        meta.save()

    from scripts.config.paths import ensure_cli_path

    ensure_cli_path()
    from agy.image import generate_image_via_agy_accounts

    seed_ref = [(_guess_mime(seed), seed.read_bytes())]
    plan = variants or generate_series_image_prompts(
        meta, count=count, constraints=constraints or meta.series_constraints, log_fn=log_fn
    )
    out_dir = series_series_image_dir(meta.batch_id)
    out_dir.mkdir(parents=True, exist_ok=True)

    created: list[SeriesItem] = []
    for n, variant in enumerate(plan, start=1):
        if should_stop is not None and should_stop():
            log(f"[系列图] 已取消，完成 {len(created)}/{len(plan)} 张")
            break

        index = meta.next_index()
        item = SeriesItem(
            index=index,
            image_name=series_image_name(index, ".png"),
            prompt=variant.to_prompt(),
            summary=variant.summary(),
        )
        log(f"[系列图] {n}/{len(plan)} 生成中：{item.summary} …")
        try:
            ensure_image_prompt(item.prompt, meta.series_id)
            data, mime, email = generate_image_via_agy_accounts(
                item.prompt,
                aspect_ratio=meta.aspect_ratio,
                system=IMAGE_SYSTEM_PROMPT,
                images=seed_ref,
                log_fn=log_fn,
            )
        except Exception as exc:  # noqa: BLE001 - 单张失败不应中断整批
            item.image_error = str(exc)
            meta.items.append(item)
            meta.save()
            created.append(item)
            log(f"[系列图] {n}/{len(plan)} 失败：{exc}")
            if on_item is not None:
                on_item(n, len(plan), item)
            continue

        suffix = _EXT_BY_MIME.get(mime, ".png")
        item.image_name = series_image_name(index, suffix)
        (out_dir / item.image_name).write_bytes(data)
        log(f"[系列图] {n}/{len(plan)} 完成：{item.image_name}（{len(data)} bytes，{email}）")
        _review_series_image(meta, item, out_dir / item.image_name, log_fn=log_fn)
        meta.items.append(item)
        meta.save()
        created.append(item)
        if on_item is not None:
            on_item(n, len(plan), item)

    return created


def _review_series_image(
    meta: BatchMeta,
    item: SeriesItem,
    image_path: Path,
    *,
    log_fn: LogFn | None = None,
) -> None:
    """系列图产物评审：不合格只标记不删文件，留给人决定重生成还是将就。"""
    verdict = review_image(
        image_path, meta.series_id, prompt=item.prompt, log_fn=log_fn
    )
    item.image_review = verdict.to_dict()
    if verdict.blocked:
        item.image_error = f"系列评审不合格：{'；'.join(verdict.issues) or '未给出理由'}"
    elif verdict.ok:
        item.image_error = ""


def regenerate_image(
    meta: BatchMeta,
    item: SeriesItem,
    *,
    log_fn: LogFn | None = None,
) -> SeriesItem:
    """用同一条提示词重新生成某张系列图，覆盖原文件。"""
    log = log_fn or (lambda _m: None)
    seed = meta.seed_path
    if not seed.is_file():
        raise FileNotFoundError(f"种子图不存在：{seed}")
    if not item.prompt:
        raise ValueError("该图缺少提示词记录，无法重新生成")

    from scripts.config.paths import ensure_cli_path

    ensure_cli_path()
    from agy.image import generate_image_via_agy_accounts

    log(f"[系列图] 重新生成 {item.image_name} …")
    ensure_image_prompt(item.prompt, meta.series_id)
    data, mime, email = generate_image_via_agy_accounts(
        item.prompt,
        aspect_ratio=meta.aspect_ratio,
        system=IMAGE_SYSTEM_PROMPT,
        images=[(_guess_mime(seed), seed.read_bytes())],
        log_fn=log_fn,
    )
    suffix = _EXT_BY_MIME.get(mime, ".png")
    old = item.image_path(meta.batch_id)
    item.image_name = series_image_name(item.index, suffix)
    new = series_series_image_dir(meta.batch_id) / item.image_name
    if old.is_file() and old != new:
        old.unlink(missing_ok=True)
    new.write_bytes(data)
    item.image_error = ""
    log(f"[系列图] 重新生成完成：{item.image_name}（{email}）")
    _review_series_image(meta, item, new, log_fn=log_fn)
    meta.save()
    return item
