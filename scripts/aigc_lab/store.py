"""``aigc/t2v_lab/`` 样本入库与索引。"""

from __future__ import annotations

import csv
import hashlib
import json
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path

from scripts.config.paths import t2v_lab_dir, t2v_runs_dir

_INDEX_HEADERS = (
    "run_id",
    "prompt_path",
    "video_path",
    "model",
    "duration",
    "aspect",
    "res",
    "created_at",
    "notes",
)


@dataclass
class T2vRun:
    run_id: str
    dir: Path
    prompt: str = ""
    meta: dict = field(default_factory=dict)
    scores: dict = field(default_factory=dict)

    @property
    def prompt_path(self) -> Path:
        return self.dir / "prompt.txt"

    @property
    def video_path(self) -> Path:
        return self.dir / "video.mp4"

    @property
    def meta_path(self) -> Path:
        return self.dir / "meta.json"

    @property
    def scores_path(self) -> Path:
        return self.dir / "scores.json"

    def save_prompt(self, text: str) -> None:
        self.dir.mkdir(parents=True, exist_ok=True)
        self.prompt_path.write_text(text.strip() + "\n", encoding="utf-8")
        self.prompt = text.strip()

    def save_meta(self, data: dict) -> None:
        self.dir.mkdir(parents=True, exist_ok=True)
        self.meta_path.write_text(
            json.dumps(data, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )
        self.meta = dict(data)

    def save_scores(self, data: dict) -> None:
        self.scores_path.write_text(
            json.dumps(data, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )
        self.scores = dict(data)


def lab_params() -> dict:
    path = t2v_lab_dir() / "params.json"
    if not path.is_file():
        return {}
    return json.loads(path.read_text(encoding="utf-8"))


def save_lab_params(updates: dict) -> Path:
    """更新 params.json 中的字段（如 duration_sec）。"""
    path = t2v_lab_dir() / "params.json"
    data = lab_params()
    data.update(updates)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(data, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    return path


def _index_path() -> Path:
    return t2v_lab_dir() / "index.csv"


def _now_iso() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _make_run_id(prompt: str, *, suffix: str = "") -> str:
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    h = hashlib.sha256(prompt.encode()).hexdigest()[:8]
    tail = f"_{suffix}" if suffix else ""
    return f"{ts}_{h}{tail}"


def create_run(
    prompt: str,
    *,
    rain_mode: str | None = None,
    prompt_table: str = "",
    slots: dict | None = None,
    repeat_index: int | None = None,
    duration_sec: int | None = None,
) -> T2vRun:
    """新建 run 目录并写入 **送模正文** prompt；表格另存 meta。"""
    from scripts.aigc_lab.prompt_atoms import (
        DEFAULT_RAIN_MODE,
        RAIN_MODE_LABELS,
        normalize_rain_mode,
    )

    mode = normalize_rain_mode(rain_mode or DEFAULT_RAIN_MODE)
    suffix = f"{repeat_index:02d}" if repeat_index is not None else ""
    run_id = _make_run_id(prompt, suffix=suffix)
    run_dir = t2v_runs_dir() / run_id
    run_dir.mkdir(parents=True, exist_ok=True)
    params = lab_params()
    dur = int(duration_sec if duration_sec is not None else params.get("duration_sec", 4))
    run = T2vRun(run_id=run_id, dir=run_dir)
    run.save_prompt(prompt)
    run.save_meta(
        {
            "run_id": run_id,
            "created_at": _now_iso(),
            "model": params.get("model", "Seedance 2.0 VIP"),
            "aspect_ratio": params.get("aspect_ratio", "16:9"),
            "resolution": params.get("resolution", "720P"),
            "duration_sec": dur,
            "rain_mode": mode,
            "rain_label": RAIN_MODE_LABELS.get(mode, mode),
            "prompt_table": prompt_table,
            "slots": slots or {},
            "repeat_index": repeat_index,
        }
    )
    _append_index(run)
    return run


def _append_index(run: T2vRun) -> None:
    path = _index_path()
    write_header = not path.is_file() or path.stat().st_size == 0
    meta = run.meta or {}
    with path.open("a", encoding="utf-8", newline="") as fh:
        writer = csv.DictWriter(fh, fieldnames=_INDEX_HEADERS)
        if write_header:
            writer.writeheader()
        writer.writerow(
            {
                "run_id": run.run_id,
                "prompt_path": str(run.prompt_path.relative_to(t2v_lab_dir())),
                "video_path": str(run.video_path.relative_to(t2v_lab_dir())),
                "model": meta.get("model", ""),
                "duration": meta.get("duration_sec", ""),
                "aspect": meta.get("aspect_ratio", ""),
                "res": meta.get("resolution", ""),
                "created_at": meta.get("created_at", ""),
                "notes": meta.get("import_note", ""),
            }
        )


def attach_run_video(
    run_id: str,
    source: Path,
    *,
    import_note: str = "",
) -> T2vRun:
    """把外部 mp4 挂到已有 run 的 ``video.mp4``（手动从即梦下载后入库）。"""
    import shutil

    run = load_run(run_id)
    src = Path(source)
    if not src.is_file():
        raise FileNotFoundError(f"视频不存在：{src}")
    run.dir.mkdir(parents=True, exist_ok=True)
    shutil.copy2(src, run.video_path)
    meta = dict(run.meta or {})
    meta["generated_at"] = _now_iso()
    if import_note:
        meta["import_note"] = import_note
    meta["import_source"] = str(src)
    run.save_meta(meta)
    return run


def load_run(run_id: str) -> T2vRun:
    run_dir = t2v_runs_dir() / run_id
    if not run_dir.is_dir():
        raise FileNotFoundError(f"run 不存在：{run_id}")
    run = T2vRun(run_id=run_id, dir=run_dir)
    if run.prompt_path.is_file():
        run.prompt = run.prompt_path.read_text(encoding="utf-8").strip()
    if run.meta_path.is_file():
        run.meta = json.loads(run.meta_path.read_text(encoding="utf-8"))
    if run.scores_path.is_file():
        run.scores = json.loads(run.scores_path.read_text(encoding="utf-8"))
    return run


def slots_from_run(run: T2vRun) -> dict[str, list[str]]:
    """从 run meta.slots 或 prompt_table 解析六槽原子列表。"""
    from scripts.aigc_lab.prompt_atoms import SLOT_ORDER, parse_table

    meta = run.meta or {}
    raw = meta.get("slots") or {}
    if isinstance(raw, dict) and any(raw.values()):
        out: dict[str, list[str]] = {}
        for key in SLOT_ORDER:
            vals = raw.get(key) or []
            out[key] = [str(x).strip() for x in vals if str(x).strip()]
        return out
    table = str(meta.get("prompt_table") or "")
    if table.strip():
        return parse_table(table)
    return {key: [] for key in SLOT_ORDER}


def list_runs(*, newest_first: bool = True) -> list[T2vRun]:
    root = t2v_runs_dir()
    if not root.is_dir():
        return []
    ids = sorted(
        (p.name for p in root.iterdir() if p.is_dir()),
        reverse=newest_first,
    )
    out: list[T2vRun] = []
    for rid in ids:
        try:
            out.append(load_run(rid))
        except Exception:  # noqa: BLE001
            continue
    return out
