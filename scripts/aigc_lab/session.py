"""AIGC 实验台 GUI 会话持久化（原子表 + 红框 + 雨档 + 选中 run）。

路径：``aigc/t2v_lab/gui_session.json``
"""

from __future__ import annotations

import json
from pathlib import Path

from scripts.aigc_lab.prompt_atoms import DEFAULT_RAIN_MODE, SLOT_ORDER, normalize_rain_mode
from scripts.config.paths import t2v_lab_dir

_SESSION_NAME = "gui_session.json"
_VERSION = 1


def session_path() -> Path:
    return t2v_lab_dir() / _SESSION_NAME


def empty_session() -> dict:
    return {
        "version": _VERSION,
        "rain_mode": DEFAULT_RAIN_MODE,
        "slots": {key: [] for key in SLOT_ORDER},
        "fail_tags": {key: [] for key in SLOT_ORDER},
        "selected_run_id": "",
    }


def _clean_slot_map(raw: dict | None) -> dict[str, list[str]]:
    out = {key: [] for key in SLOT_ORDER}
    if not isinstance(raw, dict):
        return out
    for key in SLOT_ORDER:
        vals = raw.get(key) or []
        if not isinstance(vals, list):
            continue
        seen: set[str] = set()
        cleaned: list[str] = []
        for v in vals:
            t = str(v).strip()
            if t and t not in seen:
                seen.add(t)
                cleaned.append(t)
        out[key] = cleaned
    return out


def load_session() -> dict | None:
    path = session_path()
    if not path.is_file():
        return None
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None
    if not isinstance(raw, dict):
        return None
    out = empty_session()
    out["rain_mode"] = normalize_rain_mode(
        str(raw.get("rain_mode") or DEFAULT_RAIN_MODE)
    )
    out["slots"] = _clean_slot_map(raw.get("slots"))
    out["fail_tags"] = _clean_slot_map(raw.get("fail_tags"))
    out["selected_run_id"] = str(raw.get("selected_run_id") or "").strip()
    return out


def save_session(data: dict) -> Path:
    path = session_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = empty_session()
    payload["rain_mode"] = normalize_rain_mode(
        str(data.get("rain_mode") or DEFAULT_RAIN_MODE)
    )
    payload["slots"] = _clean_slot_map(data.get("slots"))
    payload["fail_tags"] = _clean_slot_map(data.get("fail_tags"))
    payload["selected_run_id"] = str(data.get("selected_run_id") or "").strip()
    path.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    return path
