"""AIGC 父 Tab：上次选中的子 Tab。"""

from __future__ import annotations

import json
from pathlib import Path

from scripts.config.paths import aigc_dir

_VERSION = 1
_NAME = "aigc_shell_session.json"


def session_path() -> Path:
    return aigc_dir() / _NAME


def load_shell_session() -> dict | None:
    path = session_path()
    if not path.is_file():
        return None
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None
    if not isinstance(raw, dict):
        return None
    sub = str(raw.get("selected_subtab") or "i2v").strip()
    if sub not in {"i2v", "t2v", "old"}:
        sub = "i2v"
    return {"version": _VERSION, "selected_subtab": sub}


def save_shell_session(*, selected_subtab: str) -> Path:
    sub = selected_subtab if selected_subtab in {"i2v", "t2v", "old"} else "i2v"
    path = session_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(
            {"version": _VERSION, "selected_subtab": sub},
            ensure_ascii=False,
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )
    return path
