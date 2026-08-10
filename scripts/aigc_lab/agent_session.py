"""Agent 文生/图生子 Tab GUI 会话持久化。"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Literal

from scripts.aigc_lab.prompt_atoms import (
    DEFAULT_RAIN_MODE,
    SLOT_ORDER,
    normalize_rain_mode,
)
from scripts.config.paths import agent_i2v_lab_dir, agent_t2v_lab_dir

Kind = Literal["t2v", "i2v"]
_VERSION = 1


def _lab_dir(kind: Kind) -> Path:
    return agent_t2v_lab_dir() if kind == "t2v" else agent_i2v_lab_dir()


def session_path(kind: Kind) -> Path:
    return _lab_dir(kind) / "gui_session.json"


def empty_session() -> dict:
    return {
        "version": _VERSION,
        "rain_mode": DEFAULT_RAIN_MODE,
        "scene_keywords": "原始热带雨林",
        "ref_image": "",
        "slots": {key: [] for key in SLOT_ORDER},
        "fail_tags": {key: [] for key in SLOT_ORDER},
        "selected_run_id": "",
        "status": "待草稿",
        "round_label": "轮次 —",
        "review_agreed": None,
        "unresolved_conflicts": [],
        "loop_review": None,
        "confirmed": False,
    }


def _clean_tag_list(raw) -> list[str]:
    if not isinstance(raw, list):
        return []
    seen: set[str] = set()
    out: list[str] = []
    for v in raw:
        t = str(v).strip()
        if t and t not in seen:
            seen.add(t)
            out.append(t)
    return out


def _clean_slot_map(raw: dict | None) -> dict[str, list[str]]:
    out = {key: [] for key in SLOT_ORDER}
    if not isinstance(raw, dict):
        return out
    for key in SLOT_ORDER:
        out[key] = _clean_tag_list(raw.get(key) or [])
    return out


def load_agent_session(kind: Kind) -> dict | None:
    path = session_path(kind)
    if not path.is_file():
        return None
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None
    if not isinstance(raw, dict):
        return None
    out = empty_session()
    out["rain_mode"] = normalize_rain_mode(str(raw.get("rain_mode") or DEFAULT_RAIN_MODE))
    out["scene_keywords"] = str(raw.get("scene_keywords") or out["scene_keywords"]).strip()
    ref = str(raw.get("ref_image") or "").strip()
    out["ref_image"] = ref
    out["slots"] = _clean_slot_map(raw.get("slots"))
    out["fail_tags"] = _clean_slot_map(raw.get("fail_tags"))
    out["selected_run_id"] = str(raw.get("selected_run_id") or "").strip()
    out["status"] = str(raw.get("status") or out["status"]).strip()
    out["round_label"] = str(raw.get("round_label") or out["round_label"]).strip()
    agreed = raw.get("review_agreed")
    out["review_agreed"] = agreed if isinstance(agreed, bool) else None
    conflicts = raw.get("unresolved_conflicts")
    if isinstance(conflicts, list):
        out["unresolved_conflicts"] = [
            {"slot": str(c.get("slot") or ""), "tag": str(c.get("tag") or "")}
            for c in conflicts
            if isinstance(c, dict) and (c.get("tag") or c.get("slot"))
        ]
    loop_review = raw.get("loop_review")
    out["loop_review"] = loop_review if isinstance(loop_review, dict) else None
    out["confirmed"] = bool(raw.get("confirmed"))
    return out


def save_agent_session(kind: Kind, data: dict) -> Path:
    path = session_path(kind)
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = empty_session()
    payload["rain_mode"] = normalize_rain_mode(str(data.get("rain_mode") or DEFAULT_RAIN_MODE))
    payload["scene_keywords"] = str(data.get("scene_keywords") or "").strip()
    payload["ref_image"] = str(data.get("ref_image") or "").strip()
    payload["slots"] = _clean_slot_map(data.get("slots"))
    payload["fail_tags"] = _clean_slot_map(data.get("fail_tags"))
    payload["selected_run_id"] = str(data.get("selected_run_id") or "").strip()
    payload["status"] = str(data.get("status") or payload["status"]).strip()
    payload["round_label"] = str(data.get("round_label") or payload["round_label"]).strip()
    agreed = data.get("review_agreed")
    payload["review_agreed"] = agreed if isinstance(agreed, bool) else None
    conflicts = data.get("unresolved_conflicts")
    if isinstance(conflicts, list):
        payload["unresolved_conflicts"] = conflicts
    loop_review = data.get("loop_review")
    payload["loop_review"] = loop_review if isinstance(loop_review, dict) else None
    payload["confirmed"] = bool(data.get("confirmed"))
    path.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    return path
