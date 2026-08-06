"""经验证生效的原子标签学习池（按槽位存本地）。

路径：``aigc/t2v_lab/learned_pools.json``  
与官方闭集 ``atom_pools.md`` 正交：本文件收的是跑片验证过的开放/半开放标签。
"""

from __future__ import annotations

import json
from pathlib import Path

from scripts.aigc_lab.prompt_atoms import SLOT_LABELS, SLOT_ORDER
from scripts.config.paths import t2v_lab_dir

_POOL_NAME = "learned_pools.json"


def pools_path() -> Path:
    return t2v_lab_dir() / _POOL_NAME


def empty_pools() -> dict[str, list[str]]:
    return {key: [] for key in SLOT_ORDER}


def load_pools() -> dict[str, list[str]]:
    path = pools_path()
    out = empty_pools()
    if not path.is_file():
        return out
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return out
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


def save_pools(pools: dict[str, list[str]]) -> Path:
    path = pools_path()
    payload = empty_pools()
    for key in SLOT_ORDER:
        seen: set[str] = set()
        cleaned: list[str] = []
        for v in pools.get(key) or []:
            t = str(v).strip()
            if t and t not in seen:
                seen.add(t)
                cleaned.append(t)
        payload[key] = cleaned
    path.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    return path


def pool_for_slot(slot: str) -> list[str]:
    return list(load_pools().get(slot) or [])


def suggest_for_slot(slot: str, prefix: str = "") -> list[str]:
    """输入框候选：池子标签优先；prefix 非空时前缀过滤（不区分大小写）。"""
    tags = pool_for_slot(slot)
    p = (prefix or "").strip().lower()
    if not p:
        return tags
    starts = [t for t in tags if t.lower().startswith(p)]
    contains = [t for t in tags if p in t.lower() and t not in starts]
    return starts + contains


def merge_into_pools(
    tags_by_slot: dict[str, list[str]],
) -> tuple[dict[str, list[str]], dict[str, list[str]]]:
    """合入学习池。返回 (新增的标签, 合入后完整池)。"""
    pools = load_pools()
    added: dict[str, list[str]] = empty_pools()
    for key in SLOT_ORDER:
        existing = set(pools.get(key) or [])
        for tag in tags_by_slot.get(key) or []:
            t = str(tag).strip()
            if not t or t in existing:
                continue
            pools.setdefault(key, []).append(t)
            added[key].append(t)
            existing.add(t)
    if any(added.values()):
        save_pools(pools)
    return added, pools


def format_tags_by_slot(tags_by_slot: dict[str, list[str]]) -> str:
    lines: list[str] = []
    for key in SLOT_ORDER:
        tags = [t for t in (tags_by_slot.get(key) or []) if t.strip()]
        if not tags:
            continue
        label = SLOT_LABELS.get(key, key)
        lines.append(f"{label}：")
        for t in tags:
            lines.append(f"  · {t}")
    return "\n".join(lines) if lines else "（无）"


def verdicts_from_scores(scores: dict | None) -> dict[str, dict[str, str]]:
    """从 scores.json 汇总 slot→tag→最差 verdict（no > partial > yes）。"""
    rank = {"yes": 0, "partial": 1, "no": 2}
    out: dict[str, dict[str, str]] = {k: {} for k in SLOT_ORDER}
    if not scores:
        return out

    def ingest(layer: dict | None) -> None:
        if not isinstance(layer, dict):
            return
        for slot, tags in (layer.get("slots") or {}).items():
            if slot not in out:
                out[slot] = {}
            for entry in tags or []:
                if not isinstance(entry, dict):
                    continue
                tag = str(entry.get("tag") or "").strip()
                v = str(entry.get("verdict") or "no").lower()
                if not tag:
                    continue
                if v not in rank:
                    v = "no"
                prev = out[slot].get(tag)
                if prev is None or rank[v] > rank.get(prev, -1):
                    out[slot][tag] = v

    ingest(scores.get("l1") if isinstance(scores.get("l1"), dict) else None)
    ingest(scores.get("l2") if isinstance(scores.get("l2"), dict) else None)

    # 旧格式：槽位级 assertions → 整槽一条，无法拆标签，跳过
    return out


def qualified_tags_from_scores(scores: dict | None) -> dict[str, list[str]]:
    """仅 yes → 候选入池。"""
    verdicts = verdicts_from_scores(scores)
    out = empty_pools()
    for key in SLOT_ORDER:
        out[key] = [t for t, v in verdicts.get(key, {}).items() if v == "yes"]
    return out


def failed_tags_from_scores(scores: dict | None) -> dict[str, list[str]]:
    """no / partial → 红框不合格。"""
    verdicts = verdicts_from_scores(scores)
    out = empty_pools()
    for key in SLOT_ORDER:
        out[key] = [
            t for t, v in verdicts.get(key, {}).items() if v in ("no", "partial")
        ]
    return out
