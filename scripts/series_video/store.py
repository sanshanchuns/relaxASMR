"""系列视频批次的磁盘结构与元数据。

一个「批次」= 一张种子图 + 一组系列图 + 每张系列图对应的视频：

    aigc/<batch_id>/
        seed_image/seed_001.png           种子图
        seed_image/seed_001_raw_001.png   文生图待选种子
        series_image/series_001.png …     系列图
        series_video/series_001.mp4 …     对应 5s loop
        batch.json                        系列图元数据
        seed.json                         种子 prompt / 评审
        video_series_001.json …           各系列图 video prompt
"""

from __future__ import annotations

import json
import re
import shutil
import time
from dataclasses import asdict, dataclass, field
from pathlib import Path

from scripts.config.paths import (
    series_batch_dir,
    series_dir,
    series_image_read_paths,
    series_seed_image_dir,
    series_seed_meta_path,
    series_seed_path,
    series_series_image_dir,
    series_video_dir,
    series_video_prompt_path,
    series_video_prompt_read_paths,
    series_video_read_paths,
)

_IMAGE_SUFFIXES = {".png", ".jpg", ".jpeg", ".webp"}
_SERIES_STEM = re.compile(r"^series_(\d+)$", re.I)
_LEGACY_DERIVE_STEM = re.compile(r"^derive_(\d+)$", re.I)
_LEGACY_STEM = re.compile(r"^(\d+)$")


def seed_image_name(seed_index: int, suffix: str = ".png") -> str:
    return f"seed_{seed_index:03d}{suffix}"


def seed_raw_name(seed_index: int, raw_index: int, suffix: str = ".png") -> str:
    return f"seed_{seed_index:03d}_raw_{raw_index:03d}{suffix}"


def series_image_name(index: int, suffix: str = ".png") -> str:
    return f"series_{index:03d}{suffix}"


def series_video_name(index: int) -> str:
    return f"series_{index:03d}.mp4"


def _resolve_existing(*candidates: Path) -> Path:
    for p in candidates:
        if p.is_file():
            return p
    return candidates[0]


@dataclass
class SeriesItem:
    """一张系列图及其视频产物。

    ``*_review`` 存 :class:`review.Review` 的 ``to_dict()``：Gemini 产物评审结论。
    ``video_motion`` 是 :mod:`video_probe` 量出来的客观运动量（0–100），用来拦慢镜头。
    """

    index: int
    image_name: str
    prompt: str = ""
    summary: str = ""
    video_name: str = ""
    video_prompt: str = ""
    video_provider: str = ""
    image_error: str = ""
    video_error: str = ""
    image_review: dict = field(default_factory=dict)
    video_review: dict = field(default_factory=dict)
    video_motion: float = 0.0
    error: str = ""  # 旧字段，加载后迁移到 image_error / video_error

    def image_path(self, batch_id: str) -> Path:
        candidates = series_image_read_paths(batch_id, self.image_name)
        return _resolve_existing(*candidates) if candidates else (
            series_series_image_dir(batch_id) / self.image_name
        )

    def video_path(self, batch_id: str) -> Path | None:
        if not self.video_name:
            return None
        candidates = series_video_read_paths(batch_id, self.video_name)
        return _resolve_existing(*candidates) if candidates else (
            series_video_dir(batch_id) / self.video_name
        )


@dataclass
class SeedCandidate:
    """文生图产出的一张待选种子图。

    ``series_id`` 是 Gemini 看图判出来的子系列（空 = 三个都不适合），
    ``review`` 存判断依据；定稿时这个系列会写进 :class:`BatchMeta`，锁定整批。
    """

    name: str
    prompt: str = ""
    summary: str = ""
    error: str = ""
    series_id: str = ""
    review: dict = field(default_factory=dict)

    def path(self, batch_id: str) -> Path:
        root = series_batch_dir(batch_id)
        return _resolve_existing(
            root / "seed_image" / self.name,
            root / self.name,
        )


def _write_json_atomic(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    tmp.replace(path)


def save_seed_json(meta: BatchMeta) -> None:
    """种子图 prompt 落盘：``<batch>/seed.json``。"""
    payload = {
        "batch_id": meta.batch_id,
        "seed_index": meta.seed_index,
        "seed_name": meta.seed_name,
        "seed_source": meta.seed_source,
        "seed_idea": meta.seed_idea,
        "seed_prompt": meta.seed_prompt,
        "series_id": meta.series_id,
        "series_constraints": meta.series_constraints,
        "seed_review": meta.seed_review,
        "candidates": [asdict(c) for c in meta.seed_candidates],
    }
    _write_json_atomic(series_batch_dir(meta.batch_id) / "seed.json", payload)


def save_video_prompt_json(meta: BatchMeta, item: SeriesItem) -> None:
    """单条视频 prompt 落盘：``<batch>/video_series_001.json`` …"""
    if not (item.video_prompt or "").strip():
        return
    payload = {
        "index": item.index,
        "image_name": item.image_name,
        "video_name": item.video_name,
        "summary": item.summary,
        "series_id": meta.series_id,
        "image_prompt": item.prompt,
        "video_prompt": item.video_prompt,
        "video_provider": item.video_provider,
        "image_review": item.image_review,
        "video_review": item.video_review,
        "video_motion": item.video_motion,
    }
    _write_json_atomic(series_video_prompt_path(meta.batch_id, item.index), payload)


def _merge_sidecar_prompts(meta: BatchMeta) -> None:
    """从 ``seed.json`` / ``video_series_*.json`` 合并 prompt（sidecar 优先）。"""
    seed_path = series_seed_meta_path(meta.batch_id)
    if seed_path.is_file():
        try:
            raw = json.loads(seed_path.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            raw = {}
        else:
            for key in (
                "seed_idea", "seed_prompt", "seed_source", "seed_name",
                "seed_index", "series_id", "seed_review", "series_constraints",
            ):
                val = raw.get(key)
                if val not in (None, "", {}):
                    setattr(meta, key, val)
            if isinstance(raw.get("candidates"), list):
                if raw["candidates"] and not meta.seed_candidates:
                    meta.seed_candidates = [
                        SeedCandidate(**c)
                        for c in raw["candidates"]
                        if isinstance(c, dict)
                    ]

    for item in meta.items:
        vp_path = None
        for candidate in series_video_prompt_read_paths(meta.batch_id, item.index):
            if candidate.is_file():
                vp_path = candidate
                break
        if vp_path is None:
            continue
        try:
            raw = json.loads(vp_path.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            continue
        if raw.get("video_prompt"):
            item.video_prompt = str(raw["video_prompt"])
        if raw.get("video_provider"):
            item.video_provider = str(raw["video_provider"])
        for key in ("image_review", "video_review"):
            if isinstance(raw.get(key), dict) and raw[key]:
                setattr(item, key, raw[key])
        if raw.get("video_motion"):
            item.video_motion = float(raw["video_motion"])
        # sidecar 里也记了系列，老 batch.json 缺字段时从这里补回来。
        if raw.get("series_id") and not meta.series_id:
            meta.series_id = str(raw["series_id"])


def _migrate_item_errors(meta: BatchMeta) -> None:
    """把旧版单一 ``error`` 拆到 image_error / video_error。"""
    for item in meta.items:
        legacy = (item.error or "").strip()
        if legacy and not item.image_error and not item.video_error:
            if item.image_path(meta.batch_id).is_file():
                item.video_error = legacy
            else:
                item.image_error = legacy
        item.error = ""


@dataclass
class BatchMeta:
    batch_id: str
    created_at: float = field(default_factory=time.time)
    seed_source: str = ""
    seed_name: str = "seed_001.png"
    seed_index: int = 1
    seed_idea: str = ""
    seed_prompt: str = ""
    #: 系列图生成时的限定词（主体/角度/环境等要保持一致的部分）。
    series_constraints: str = ""
    #: 整批锁定的子系列（暴雨助眠 / 中雨专注 / 轻雨冥想），种子图定稿时写入。
    #: 老批次没有这个字段，读到空串时按 ``series.default_series_id()`` 处理。
    series_id: str = ""
    seed_review: dict = field(default_factory=dict)
    aspect_ratio: str = "16:9"
    resolution: str = "480p"
    duration_sec: int = 5
    items: list[SeriesItem] = field(default_factory=list)
    seed_candidates: list[SeedCandidate] = field(default_factory=list)

    @property
    def dir(self) -> Path:
        return series_batch_dir(self.batch_id)

    @property
    def seed_path(self) -> Path:
        root = self.dir
        if self.seed_name:
            found = _resolve_existing(
                root / "seed_image" / self.seed_name,
                root / self.seed_name,
            )
            if found.is_file():
                return found
        legacy = root / "seed.png"
        if legacy.is_file():
            return legacy
        return series_seed_image_dir(self.batch_id) / seed_image_name(self.seed_index)

    @property
    def has_seed(self) -> bool:
        return bool(self.seed_name) and self.seed_path.is_file()

    def next_candidate_index(self) -> int:
        return len(self.seed_candidates) + 1

    def next_raw_index(self) -> int:
        return self.next_candidate_index()

    def next_index(self) -> int:
        return max((it.index for it in self.items), default=0) + 1

    def item_by_image(self, name: str) -> SeriesItem | None:
        for it in self.items:
            if it.image_name == name:
                return it
        return None

    def save(self) -> None:
        batch_dir = series_batch_dir(self.batch_id)
        path = batch_dir / "batch.json"
        batch_dir.mkdir(parents=True, exist_ok=True)
        payload = asdict(self)
        tmp = path.with_suffix(".json.tmp")
        tmp.write_text(
            json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
        )
        tmp.replace(path)
        save_seed_json(self)
        for item in self.items:
            save_video_prompt_json(self, item)

    @classmethod
    def load(cls, batch_id: str) -> BatchMeta | None:
        path = series_batch_dir(batch_id) / "batch.json"
        if not path.is_file():
            return None
        try:
            raw = json.loads(path.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            return None
        items = [SeriesItem(**it) for it in raw.pop("items", []) if isinstance(it, dict)]
        cands = [
            SeedCandidate(**c)
            for c in raw.pop("seed_candidates", [])
            if isinstance(c, dict)
        ]
        skip = {"items", "seed_candidates"}
        known = {f for f in cls.__dataclass_fields__ if f not in skip}
        meta = cls(
            items=items,
            seed_candidates=cands,
            **{k: v for k, v in raw.items() if k in known},
        )
        if meta.seed_index < 1:
            meta.seed_index = 1
        _migrate_item_errors(meta)
        _migrate_legacy_names(meta)
        _dedupe_items(meta)
        _merge_sidecar_prompts(meta)
        return meta


def new_batch_id() -> str:
    return time.strftime("%Y%m%d_%H%M%S")


def _prepare_batch_dirs(batch_id: str) -> None:
    series_seed_image_dir(batch_id).mkdir(parents=True, exist_ok=True)
    series_series_image_dir(batch_id).mkdir(parents=True, exist_ok=True)
    series_video_dir(batch_id).mkdir(parents=True, exist_ok=True)


def create_batch(seed_image: Path, *, batch_id: str | None = None) -> BatchMeta:
    """把 *seed_image* 复制进新批次目录并写好元数据。"""
    bid = batch_id or new_batch_id()
    _prepare_batch_dirs(bid)

    meta = BatchMeta(batch_id=bid, seed_index=1)
    set_batch_seed(meta, seed_image, source=str(seed_image))
    return meta


def set_batch_seed(
    meta: BatchMeta,
    seed_image: Path,
    *,
    source: str = "",
) -> Path:
    """把外部图片设为当前批次的种子图（覆盖原种子）。"""
    if not seed_image.is_file():
        raise FileNotFoundError(f"种子图不存在：{seed_image}")

    seed_dir = series_seed_image_dir(meta.batch_id)
    seed_dir.mkdir(parents=True, exist_ok=True)
    prefix = f"seed_{meta.seed_index:03d}."
    for old in seed_dir.glob(f"seed_{meta.seed_index:03d}.*"):
        if old.is_file() and "_raw_" not in old.name:
            old.unlink(missing_ok=True)
    for old in meta.dir.glob("seed.*"):
        if old.is_file():
            old.unlink(missing_ok=True)

    suffix = seed_image.suffix.lower() or ".png"
    seed_name = seed_image_name(meta.seed_index, suffix)
    dest = seed_dir / seed_name
    shutil.copy2(seed_image, dest)
    meta.seed_name = seed_name
    meta.seed_source = source or str(seed_image)
    meta.seed_prompt = ""
    meta.seed_review = {}
    meta.save()
    return dest


def create_empty_batch(*, idea: str = "", batch_id: str | None = None) -> BatchMeta:
    """建一个还没有种子图的批次，等文生图产出候选后再选定。"""
    bid = batch_id or new_batch_id()
    _prepare_batch_dirs(bid)
    meta = BatchMeta(
        batch_id=bid,
        seed_source="prompt",
        seed_name="",
        seed_index=1,
        seed_idea=idea,
    )
    meta.save()
    return meta


def clear_batch_seed(meta: BatchMeta) -> None:
    """取消已定稿的种子图，回到待选状态（候选图保留）。"""
    seed_dir = series_seed_image_dir(meta.batch_id)
    if meta.seed_name:
        p = seed_dir / meta.seed_name
        if p.is_file() and "_raw_" not in meta.seed_name:
            p.unlink(missing_ok=True)
    meta.seed_name = ""
    meta.seed_prompt = ""
    meta.seed_review = {}
    if meta.seed_candidates:
        meta.seed_source = "prompt"
    meta.save()


def delete_item_video(meta: BatchMeta, item: SeriesItem) -> None:
    """删除某格的视频文件，保留系列图。"""
    path = item.video_path(meta.batch_id)
    if path is not None and path.is_file():
        path.unlink(missing_ok=True)
    item.video_name = ""
    item.video_provider = ""
    item.video_error = ""
    item.video_review = {}
    item.video_motion = 0.0
    meta.save()


def adopt_seed_candidate(meta: BatchMeta, candidate: SeedCandidate) -> Path:
    """把某张候选图定为这一批的种子图。

    候选图的子系列（Gemini 看图判的）在这一刻锁进批次，后面系列图和视频全部继承。
    """
    src = candidate.path(meta.batch_id)
    if not src.is_file():
        raise FileNotFoundError(f"候选种子图不存在：{src}")

    seed_dir = series_seed_image_dir(meta.batch_id)
    prefix = f"seed_{meta.seed_index:03d}."
    for old in seed_dir.glob(f"seed_{meta.seed_index:03d}.*"):
        if old.is_file() and "_raw_" not in old.name:
            old.unlink(missing_ok=True)
    for old in meta.dir.glob("seed.*"):
        if old.is_file():
            old.unlink(missing_ok=True)

    suffix = src.suffix.lower() or ".png"
    seed_name = seed_image_name(meta.seed_index, suffix)
    dest = seed_dir / seed_name
    shutil.copy2(src, dest)
    meta.seed_name = seed_name
    meta.seed_source = f"candidate:{candidate.name}"
    meta.seed_prompt = candidate.prompt
    if candidate.series_id:
        meta.series_id = candidate.series_id
    if candidate.review:
        meta.seed_review = dict(candidate.review)
    meta.save()
    return dest


def list_batches() -> list[str]:
    """按时间倒序列出 ``aigc/`` 下已有批次 id。"""
    root = series_dir()
    if not root.is_dir():
        return []
    ids = [p.name for p in root.iterdir() if p.is_dir() and (p / "batch.json").is_file()]
    return sorted(ids, reverse=True)


def latest_batch() -> BatchMeta | None:
    for bid in list_batches():
        meta = BatchMeta.load(bid)
        if meta is not None:
            return meta
    return None


def _stem_index(stem: str) -> int | None:
    for pat in (_SERIES_STEM, _LEGACY_DERIVE_STEM, _LEGACY_STEM):
        m = pat.match(stem)
        if m:
            return int(m.group(1))
    return None


def _rename_if_exists(src: Path, dest: Path) -> bool:
    if not src.is_file() or src == dest:
        return False
    dest.parent.mkdir(parents=True, exist_ok=True)
    if dest.is_file():
        src.unlink(missing_ok=True)
        return True
    src.rename(dest)
    return True


def _migrate_legacy_names(meta: BatchMeta) -> bool:
    """把 ``derive_*`` 文件与 ``video_derive_*.json`` 迁移为 ``series_*`` 命名。"""
    changed = False
    root = series_batch_dir(meta.batch_id)

    for item in meta.items:
        stem = Path(item.image_name).stem
        if _LEGACY_DERIVE_STEM.match(stem):
            idx = _stem_index(stem) or item.index
            suffix = Path(item.image_name).suffix or ".png"
            new_name = series_image_name(idx, suffix)
            if new_name != item.image_name:
                old_path = item.image_path(meta.batch_id)
                new_path = series_series_image_dir(meta.batch_id) / new_name
                if _rename_if_exists(old_path, new_path) or new_path.is_file():
                    item.image_name = new_name
                    changed = True

        if item.video_name and _LEGACY_DERIVE_STEM.match(Path(item.video_name).stem):
            idx = _stem_index(Path(item.video_name).stem) or item.index
            new_vname = series_video_name(idx)
            if new_vname != item.video_name:
                old_vpath = item.video_path(meta.batch_id)
                new_vpath = series_video_dir(meta.batch_id) / new_vname
                if old_vpath is not None and _rename_if_exists(old_vpath, new_vpath):
                    item.video_name = new_vname
                    changed = True
                elif new_vpath.is_file():
                    item.video_name = new_vname
                    changed = True

        old_sidecar = root / f"video_derive_{item.index:03d}.json"
        new_sidecar = series_video_prompt_path(meta.batch_id, item.index)
        if _rename_if_exists(old_sidecar, new_sidecar):
            changed = True

    if changed:
        meta.save()
    return changed


def _item_richness(item: SeriesItem) -> int:
    score = len(item.prompt or "")
    if item.image_review:
        score += 200
    if item.summary and not item.summary.startswith("series_"):
        score += 50
    return score


def _dedupe_items(meta: BatchMeta) -> bool:
    """同一 ``index`` 出现多条时合并：保留元数据更全的一条，文件名指向磁盘上真实文件。"""
    by_index: dict[int, list[SeriesItem]] = {}
    for it in meta.items:
        by_index.setdefault(it.index, []).append(it)

    if all(len(group) == 1 for group in by_index.values()):
        return False

    merged: list[SeriesItem] = []
    for idx in sorted(by_index):
        group = by_index[idx]
        if len(group) == 1:
            merged.append(group[0])
            continue
        group.sort(key=_item_richness, reverse=True)
        primary = group[0]
        for it in group:
            if it.image_path(meta.batch_id).is_file():
                primary.image_name = it.image_name
                break
        merged.append(primary)

    meta.items = merged
    meta.save()
    return True


def adopt_orphan_images(meta: BatchMeta) -> bool:
    """把目录里存在但 ``batch.json`` 没记录的图片/视频补进元数据。"""
    root = series_batch_dir(meta.batch_id)
    scan_dirs = [
        root / sub
        for sub in ("series_image", "derive_image", "images")
        if (root / sub).is_dir()
    ]

    known = {it.image_name for it in meta.items}
    by_index = {it.index: it for it in meta.items}
    changed = False
    for d in scan_dirs:
        for p in sorted(d.iterdir()):
            if p.suffix.lower() not in _IMAGE_SUFFIXES or p.name in known:
                continue
            idx = _stem_index(p.stem) or meta.next_index()
            name = p.name
            if _LEGACY_DERIVE_STEM.match(p.stem):
                new_name = series_image_name(idx, p.suffix.lower() or ".png")
                new_path = d / new_name
                if _rename_if_exists(p, new_path):
                    name = new_name
            existing = by_index.get(idx)
            if existing is not None and not existing.image_path(meta.batch_id).is_file():
                existing.image_name = name
                known.add(name)
                changed = True
                continue
            if existing is not None and existing.image_path(meta.batch_id).is_file():
                known.add(name)
                continue
            item = SeriesItem(index=idx, image_name=name, summary=Path(name).stem)
            meta.items.append(item)
            by_index[idx] = item
            known.add(name)
            changed = True

    vid_dirs = [
        root / sub
        for sub in ("series_video", "video", "clips")
        if (root / sub).is_dir()
    ]

    for it in meta.items:
        if it.video_name:
            continue
        stem = Path(it.image_name).stem
        idx = _stem_index(stem) or it.index
        candidates = [
            series_video_name(idx),
            f"{stem}.mp4",
            f"derive_{idx:03d}.mp4",
        ]
        for vdir in vid_dirs:
            if not vdir.is_dir():
                continue
            for name in candidates:
                candidate = vdir / name
                if candidate.is_file():
                    it.video_name = candidate.name
                    changed = True
                    break
            if it.video_name:
                break

    if changed:
        meta.save()
    return changed


def seed_path_for(meta: BatchMeta) -> Path:
    p = meta.seed_path
    return p if p.is_file() else series_seed_path(meta.batch_id)
