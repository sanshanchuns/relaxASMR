from __future__ import annotations

import xml.etree.ElementTree as ET
from pathlib import Path


def parse_rain_file(path: Path) -> dict[str, float]:
    """Parse a .rain XML file into a dictionary of parameters."""
    if not path.is_file():
        return {}
    
    try:
        tree = ET.parse(path)
        root = tree.getroot()
        params = {}
        # Parse root attributes (l1, l2, l3)
        for key in ["l1", "l2", "l3"]:
            if key in root.attrib:
                val = float(root.attrib[key])
                params[key] = val / 1000.0  # Normalize to 0-1 range roughly

        # Parse <PARAM> tags
        for param in root.findall("PARAM"):
            pid = param.get("id")
            pval = param.get("value")
            if pid and pval:
                params[pid] = float(pval)
                
        return params
    except Exception as e:
        print(f"Failed to parse {path}: {e}")
        return {}


def compute_similarity(dict1: dict[str, float], dict2: dict[str, float]) -> float:
    """Calculate similarity (0 to 1) based on inverted Mean Squared Error."""
    keys = set(dict1.keys()).intersection(dict2.keys())
    if not keys:
        return 0.0
        
    mse = 0.0
    for k in keys:
        diff = dict1[k] - dict2[k]
        mse += diff * diff
        
    mse /= len(keys)
    return 1.0 / (1.0 + mse)


def find_best_match(target_rain: Path, vst_dir: Path) -> tuple[Path, float] | None:
    """Scan preset and extend directories to find the best match for target_rain."""
    if not target_rain.is_file() or not vst_dir.is_dir():
        return None
        
    target_params = parse_rain_file(target_rain)
    if not target_params:
        return None

    best_match = None
    best_score = -1.0

    dirs_to_scan = [vst_dir / "preset", vst_dir / "extend"]
    for d in dirs_to_scan:
        if not d.is_dir():
            continue
        for p in d.rglob("*.rain"):
            # Avoid comparing to itself if somehow it's in the same folder
            try:
                if p.samefile(target_rain):
                    continue
            except Exception:
                pass
                
            params = parse_rain_file(p)
            if not params:
                continue
                
            score = compute_similarity(target_params, params)
            if score > best_score:
                best_score = score
                best_match = p

    if best_match:
        return best_match, best_score
    return None
