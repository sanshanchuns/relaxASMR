"""将 ``aigc/t2v_fast/`` 历史样本迁入 ``aigc/t2v_lab/runs/``。"""

from __future__ import annotations

import csv
import hashlib
import json
import re
import shutil
import subprocess
from datetime import datetime, timezone
from pathlib import Path

from scripts.aigc_lab.prompt_atoms import DEFAULT_RAIN_MODE, RAIN_MODE_LABELS
from scripts.aigc_lab.store import T2vRun, _append_index
from scripts.config.paths import aigc_dir, t2v_lab_dir, t2v_runs_dir

_MODEL_LINE = re.compile(r"^Seedance 2\.0 Fast VIP\s*$", re.M)
_IMAGE_LINE = re.compile(r"(?m)^image\s*\n?")


def _fast_dir() -> Path:
    return aigc_dir() / "t2v_fast"


def _parse_fast_prompt(path: Path) -> str:
    raw = path.read_text(encoding="utf-8")
    raw = _IMAGE_LINE.sub("", raw)
    raw = _MODEL_LINE.sub("", raw)
    return raw.strip()


def _video_duration_sec(path: Path) -> int:
    try:
        out = subprocess.check_output(
            [
                "ffprobe",
                "-v",
                "error",
                "-show_entries",
                "format=duration",
                "-of",
                "default=noprint_wrappers=1:nokey=1",
                str(path),
            ],
            text=True,
        ).strip()
        return max(1, round(float(out)))
    except (subprocess.CalledProcessError, ValueError, FileNotFoundError):
        return 4


def _run_id_for(mvi_id: str, mtime: int) -> str:
    ts = datetime.fromtimestamp(mtime, tz=timezone.utc).strftime("%Y%m%d_%H%M%S")
    h = hashlib.sha256(mvi_id.encode()).hexdigest()[:8]
    return f"{ts}_{h}"


def _iso_from_mtime(mtime: int) -> str:
    return datetime.fromtimestamp(mtime, tz=timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _existing_import_notes() -> set[str]:
    notes: set[str] = set()
    for run in t2v_runs_dir().iterdir():
        meta_path = run / "meta.json"
        if not meta_path.is_file():
            continue
        meta = json.loads(meta_path.read_text(encoding="utf-8"))
        note = str(meta.get("import_note") or "").strip()
        if note:
            notes.add(note)
    path = t2v_lab_dir() / "index.csv"
    if path.is_file():
        with path.open(encoding="utf-8", newline="") as fh:
            for row in csv.DictReader(fh):
                note = str(row.get("notes") or "").strip()
                if note:
                    notes.add(note)
    return notes


def import_fast_runs(*, dry_run: bool = False) -> list[str]:
    """迁入 ``t2v_fast/MVI_*``；返回新建 run_id 列表。"""
    fast = _fast_dir()
    if not fast.is_dir():
        raise FileNotFoundError(f"目录不存在：{fast}")

    done = _existing_import_notes()
    created: list[str] = []

    for mp4 in sorted(fast.glob("MVI_*.mp4")):
        mvi_id = mp4.stem
        if mvi_id in done:
            continue

        json_path = fast / f"{mvi_id}.json"
        if not json_path.is_file():
            continue

        prompt = _parse_fast_prompt(json_path)
        mtime = int(mp4.stat().st_mtime)
        run_id = _run_id_for(mvi_id, mtime)
        run_dir = t2v_runs_dir() / run_id
        if run_dir.exists():
            continue

        ref_src = fast / f"{mvi_id}.jpg"
        gen_mode = "i2v" if ref_src.is_file() else "t2v"
        duration = _video_duration_sec(mp4)
        created_at = _iso_from_mtime(mtime)

        meta = {
            "run_id": run_id,
            "created_at": created_at,
            "generated_at": created_at,
            "model": "Seedance 2.0 Fast VIP",
            "aspect_ratio": "16:9",
            "resolution": "720P",
            "duration_sec": duration,
            "gen_mode": gen_mode,
            "rain_mode": DEFAULT_RAIN_MODE,
            "rain_label": RAIN_MODE_LABELS[DEFAULT_RAIN_MODE],
            "prompt_table": "",
            "slots": {},
            "repeat_index": None,
            "import_source": str(mp4.relative_to(aigc_dir().parent)),
            "import_note": mvi_id,
        }
        if gen_mode == "i2v":
            meta["reference_image"] = "ref.jpg"

        if dry_run:
            created.append(run_id)
            continue

        run = T2vRun(run_id=run_id, dir=run_dir)
        run_dir.mkdir(parents=True, exist_ok=True)
        run.save_prompt(prompt)
        run.save_meta(meta)
        shutil.copy2(mp4, run.video_path)
        if ref_src.is_file():
            shutil.copy2(ref_src, run_dir / "ref.jpg")
        _append_index(run)
        created.append(run_id)

    return created


def main() -> None:
    import argparse

    ap = argparse.ArgumentParser(description="迁入 aigc/t2v_fast 历史样本到 t2v_lab")
    ap.add_argument("--dry-run", action="store_true", help="只列出将创建的 run_id")
    args = ap.parse_args()
    ids = import_fast_runs(dry_run=args.dry_run)
    action = "将创建" if args.dry_run else "已创建"
    print(f"{action} {len(ids)} 条 run：")
    for rid in ids:
        print(f"  {rid}")


if __name__ == "__main__":
    main()
