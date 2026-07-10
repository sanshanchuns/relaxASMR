"""Rain 场景工程配置（JSON）；兼容读取旧 .lua 配方。"""

from __future__ import annotations

import json
import sys
from pathlib import Path

_REPO = Path(__file__).resolve().parents[2]
if str(_REPO) not in sys.path:
    sys.path.insert(0, str(_REPO))

from scripts.config.paths import RAIN_SCENES_DIR, SUBPROJECTS_DIR  # noqa: E402

from asmr_config_parser import load_asmr_config  # noqa: E402


def scene_config_path(scene_id: str) -> Path:
    return RAIN_SCENES_DIR / f"{scene_id}.json"


def save_scene_config(cfg: dict, *, scene_id: str | None = None) -> Path:
    sid = scene_id or cfg.get("scene_id")
    if not sid:
        raise ValueError("scene_id required")
    path = scene_config_path(sid)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(cfg, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    return path


def load_scene_config(path: Path) -> dict:
    path = path.resolve()
    if not path.is_file():
        raise FileNotFoundError(path)
    suffix = path.suffix.lower()
    if suffix == ".json":
        return json.loads(path.read_text(encoding="utf-8"))
    if suffix == ".lua":
        return load_asmr_config(path)
    raise ValueError(f"不支持的配置文件: {path}")


def resolve_scene_config_path(scene_id: str) -> Path | None:
    """优先 JSON，回退 scenes/*.lua 与旧 subprojects/*/asmr_config.lua。"""
    for candidate in (
        scene_config_path(scene_id),
        RAIN_SCENES_DIR / f"{scene_id}.lua",
        SUBPROJECTS_DIR / scene_id / "scripts" / "asmr_config.lua",
    ):
        if candidate.is_file():
            return candidate
    return None
