"""解析 Reaper .rpp 与 asmr_config.lua，供 benchmark 修改建议。"""

from __future__ import annotations

import re
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
SCRIPTS_DIR = REPO_ROOT / "Reaper" / "scripts"

# theory.md §五 三层声景
LAYER_ROLE = {
    "1_rain": "background",
    "2_impact": "foreground",
    "3_environment": "mid",
    "4_water": "mid",
    "5_wildlife": "accent",
    "6_human": "foreground",
}

IDEAL_LAYER_ENERGY = {
    "foreground": 0.60,
    "mid": 0.30,
    "background": 0.10,
}

# 材质关键词 → theory §一 表
MATERIAL_HINTS = {
    "metal": ("tin", "metal", "steel", "铁皮", "金属"),
    "glass": ("glass", "window", "玻璃", "窗"),
    "tent": ("tent", "umbrella", "canvas", "伞", "帐篷"),
    "wood": ("wood", "cabin", "木", "cedar"),
}


def parse_rpp(rpp_path: Path) -> dict:
    text = rpp_path.read_text(encoding="utf-8", errors="replace")
    tracks: list[dict] = []
    group_fx: list[str] = []
    stack: list[str] = []
    current: dict | None = None

    for line in text.splitlines():
        stripped = line.strip()

        if stripped.startswith("<TRACK "):
            current = {"fx": [], "items": []}
            stack = ["track"]
            continue

        if stripped.startswith("<"):
            if stack:
                stack.append("nested")
            continue

        if stripped == ">":
            if not stack:
                continue
            stack.pop()
            if stack or current is None:
                continue
            name = current.get("name", "")
            if name.lower() == "group":
                group_fx.extend(current.get("fx", []))
            elif name.lower() != "video" and name:
                tracks.append(current)
            current = None
            continue

        if not stack or stack[0] != "track" or current is None:
            continue

        if stripped.startswith("FILE "):
            m = re.search(r'FILE "([^"]+)"', stripped)
            if m:
                current.setdefault("items", []).append(m.group(1))
        elif len(stack) == 1 and stripped.startswith("NAME "):
            current["name"] = stripped[5:].strip()
        elif len(stack) == 1 and stripped.startswith("VOLPAN "):
            parts = stripped.split()
            if len(parts) >= 2:
                try:
                    current["vol"] = float(parts[1])
                except ValueError:
                    pass
        elif len(stack) == 1 and stripped.startswith("ISBUS "):
            parts = stripped.split()
            if len(parts) >= 2:
                current["is_bus"] = parts[1]
        elif len(stack) == 1 and ("ReaEQ" in stripped or "ReaComp" in stripped):
            m = re.search(r'"VST: ([^"]+)"', stripped)
            if m:
                current.setdefault("fx", []).append(m.group(1))

    audio_tracks = [t for t in tracks if t.get("name", "").lower() not in ("video", "group")]
    return {
        "rpp": str(rpp_path),
        "tracks": audio_tracks,
        "group_fx": list(dict.fromkeys(group_fx)),
    }


def load_asmr_config(rpp_path: Path) -> dict | None:
    cfg = rpp_path.parent / "scripts" / "asmr_config.lua"
    if not cfg.is_file():
        return None
    if str(SCRIPTS_DIR) not in sys.path:
        sys.path.insert(0, str(SCRIPTS_DIR))
    try:
        from asmr_config_parser import load_asmr_config as load_cfg

        return load_cfg(cfg)
    except Exception:
        return None


def infer_layer_id(track_name: str) -> str:
    name = track_name.strip()
    if re.match(r"^[1-6]_[a-z]+", name):
        return name.split()[0] if " " in name else name
    return name


def _index_rpp_tracks(tracks: list[dict]) -> dict[str, dict]:
    """layer_id → RPP 轨（含 items / vol）。"""
    idx: dict[str, dict] = {}
    for t in tracks:
        lid = infer_layer_id(t.get("name", ""))
        if lid:
            idx[lid] = t
    return idx


def _sync_layer_with_rpp(layer: dict, rpp_track: dict | None) -> None:
    """以 RPP 实际 item 为准；空轨视为未参与混音（vol=0）。"""
    if not rpp_track:
        layer["active"] = False
        layer["vol"] = 0.0
        return

    items = rpp_track.get("items") or []
    if not items:
        layer["active"] = False
        layer["vol"] = 0.0
        layer["paths"] = []
        return

    layer["active"] = True
    rpp_vol = rpp_track.get("vol")
    if rpp_vol is not None:
        layer["vol"] = float(rpp_vol)
    layer["paths"] = items


def analyze_mix_structure(rpp_ctx: dict, cfg: dict | None) -> dict:
    tracks = rpp_ctx.get("tracks", [])
    rpp_by_id = _index_rpp_tracks(tracks)
    layers: list[dict] = []

    if cfg:
        for src, mode in (("loop_layers", "loop"), ("scatter_layers", "scatter")):
            for layer in cfg.get(src, []):
                lid = layer.get("id", "")
                vol = float(layer.get("vol", 0) or 0)
                role = LAYER_ROLE.get(lid, "accent")
                paths = layer.get("paths", [])
                entry = {
                    "id": lid,
                    "name": layer.get("name", lid),
                    "track": layer.get("track"),
                    "vol": vol,
                    "mode": mode,
                    "role": role,
                    "paths": list(paths),
                    "vol_envelope": layer.get("vol_envelope"),
                    "active": vol > 0,
                }
                _sync_layer_with_rpp(entry, rpp_by_id.get(lid))
                layers.append(entry)
    else:
        for t in tracks:
            lid = infer_layer_id(t.get("name", ""))
            vol = float(t.get("vol", 1.0))
            entry = {
                "id": lid,
                "name": t.get("name", lid),
                "track": None,
                "vol": vol,
                "mode": "rpp",
                "role": LAYER_ROLE.get(lid, "accent"),
                "paths": t.get("items", []),
                "active": bool(t.get("items")),
            }
            _sync_layer_with_rpp(entry, t)
            layers.append(entry)

    role_energy: dict[str, float] = {k: 0.0 for k in IDEAL_LAYER_ENERGY}
    for layer in layers:
        if not layer.get("active", True) or layer["vol"] <= 0:
            continue
        w = layer["vol"] ** 2
        if layer["mode"] == "scatter":
            w *= 0.35
        role = layer.get("role", "accent")
        if role in role_energy:
            role_energy[role] += w

    total = sum(role_energy.values()) or 1.0
    role_pct = {k: round(100 * v / total, 1) for k, v in role_energy.items()}

    materials: list[str] = []
    for layer in layers:
        if not layer.get("active", True):
            continue
        blob = " ".join(layer.get("paths", []) + [layer.get("name", "")])
        for mat in _detect_materials(blob):
            materials.append(mat)

    return {
        "layers": layers,
        "role_energy_pct": role_pct,
        "ideal_role_pct": {k: int(v * 100) for k, v in IDEAL_LAYER_ENERGY.items()},
        "materials_detected": sorted(set(materials)),
        "group_fx": rpp_ctx.get("group_fx", []),
        "scene_id": (cfg or {}).get("scene_id"),
        "series": (cfg or {}).get("series"),
    }


def _has_material_keyword(blob: str, keyword: str) -> bool:
    """避免 'tin' 误匹配 Vegetation 等子串。"""
    low = blob.lower()
    if keyword.isascii() and re.fullmatch(r"[a-z0-9_]+", keyword):
        return bool(re.search(rf"(?<![a-z0-9_]){re.escape(keyword)}(?![a-z0-9_])", low))
    return keyword.lower() in low


def _detect_materials(blob: str) -> list[str]:
    found: list[str] = []
    for mat, kws in MATERIAL_HINTS.items():
        if any(_has_material_keyword(blob, kw) for kw in kws):
            found.append(mat)
    return found


def find_rpp_for_media(media_path: Path) -> Path | None:
    """从 mp4/wav 路径推断同场景 .rpp。"""
    p = media_path.resolve()
    candidates: list[Path] = []
    stem = p.stem.replace("_4k", "").replace("_3h", "").replace("_gpu", "")
    for parent in [p.parent, p.parent.parent, p.parent.parent.parent]:
        if not parent.is_dir():
            continue
        candidates.extend(parent.glob("*.rpp"))
        candidates.extend(parent.glob("*.RPP"))
        scene_dir = parent / stem
        if scene_dir.is_dir():
            candidates.extend(scene_dir.glob("*.rpp"))
        named = parent / f"{stem}.rpp"
        if named.is_file():
            candidates.insert(0, named)
    seen: set[str] = set()
    for c in candidates:
        key = str(c.resolve())
        if key not in seen and c.is_file():
            seen.add(key)
            return c.resolve()
    return None


def load_project_context(rpp_path: Path | None, media_path: Path | None) -> dict | None:
    path = rpp_path
    if path is None and media_path is not None:
        path = find_rpp_for_media(media_path)
    if path is None or not path.is_file():
        return None
    rpp_ctx = parse_rpp(path)
    cfg = load_asmr_config(path)
    mix = analyze_mix_structure(rpp_ctx, cfg)
    return {
        "rpp_path": str(path),
        "config_path": str(path.parent / "scripts" / "asmr_config.lua")
        if (path.parent / "scripts" / "asmr_config.lua").is_file()
        else None,
        "mix": mix,
        "tracks": rpp_ctx.get("tracks", []),
    }
