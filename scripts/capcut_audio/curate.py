#!/usr/bin/env python3
"""按设计文档规则筛选剪映音效/音乐库，删除不相关条目并更新 manifest。"""

from __future__ import annotations

import argparse
import json
import sys
from collections import defaultdict
from pathlib import Path

SCRIPT_DIR = Path(__file__).resolve().parent
REPO_ROOT = SCRIPT_DIR.parent.parent
RULES_PATH = SCRIPT_DIR / "curate_rules.json"

ASSET_TARGETS = {
    "rain": REPO_ROOT / "assets" / "rain_sound",
    "lake": REPO_ROOT / "assets" / "lake_sound",
}


def resolve_local_path(rel: str) -> Path:
    p = Path(rel)
    if p.is_absolute():
        return p
    if rel.startswith("assets/") or rel.startswith("output_"):
        return REPO_ROOT / rel if rel.startswith("assets/") else SCRIPT_DIR / rel
    return REPO_ROOT / rel


def load_rules() -> dict:
    return json.loads(RULES_PATH.read_text(encoding="utf-8"))


def group_key(entry: dict) -> str:
    return entry.get("group") or entry.get("keyword") or ""


def score_item(entry: dict, rules: dict, layer_id: str) -> tuple[int, list[str]]:
    title = entry.get("title") or ""
    duration = entry.get("duration")
    keyword = group_key(entry)
    layer_rules = rules["layer_rules"].get(layer_id, {})
    reasons: list[str] = []
    score = 0

    for pat in rules.get("global_reject", []):
        if pat.lower() in title.lower() or pat in title:
            return -100, [f"global_reject:{pat}"]

    kw_rules = layer_rules.get("keyword_rules", {}).get(keyword, {})
    reject_list = list(layer_rules.get("reject", [])) + list(kw_rules.get("reject", []))
    boost_list = list(rules.get("global_boost", [])) + list(layer_rules.get("boost", [])) + list(
        kw_rules.get("boost", [])
    )

    for pat in reject_list:
        if pat in title:
            return -100, [f"reject:{pat}"]

    for pat in boost_list:
        if pat.lower() in title.lower() or pat in title:
            score += 2
            reasons.append(f"+{pat}")

    min_dur = layer_rules.get("min_duration", 0)
    if duration is not None:
        if duration < min_dur:
            score -= 5
            reasons.append(f"short:{duration}s<{min_dur}s")
        elif duration >= min_dur * 2:
            score += 2
            reasons.append(f"long:{duration}s")
        elif duration >= min_dur:
            score += 1

    # 关键词字面匹配加分
    for part in keyword.replace(" ", "").split():
        if part and part in title:
            score += 1
            reasons.append(f"kw:{part}")

    return score, reasons


def curate_manifest(
    manifest_path: Path,
    rules: dict,
    *,
    dry_run: bool,
    min_score: int,
) -> dict:
    layer_id = manifest_path.parent.name
    layer_rules = rules["layer_rules"].get(layer_id)
    if not layer_rules:
        return {"skipped": True, "layer_id": layer_id}

    if manifest_path.parent.name == "7_music":
        entries = json.loads(manifest_path.read_text(encoding="utf-8"))
        # music manifest is flat list
        items = entries
    else:
        items = json.loads(manifest_path.read_text(encoding="utf-8"))

    max_keep = layer_rules.get("max_keep_per_keyword", 10)
    by_group: dict[str, list[tuple[dict, int, list[str]]]] = defaultdict(list)

    for entry in items:
        s, reasons = score_item(entry, rules, layer_id)
        by_group[group_key(entry)].append((entry, s, reasons))

    kept: list[dict] = []
    removed: list[dict] = []

    for group, scored in by_group.items():
        scored.sort(key=lambda x: x[1], reverse=True)
        for entry, s, reasons in scored:
            if s < min_score:
                entry_copy = dict(entry)
                entry_copy["curation_score"] = s
                entry_copy["curation_reason"] = "; ".join(reasons)
                removed.append(entry_copy)
                continue
            if sum(1 for k in kept if group_key(k) == group) >= max_keep:
                entry_copy = dict(entry)
                entry_copy["curation_score"] = s
                entry_copy["curation_reason"] = "over_limit"
                removed.append(entry_copy)
                continue
            entry_copy = dict(entry)
            entry_copy["curation_score"] = s
            kept.append(entry_copy)

    deleted_files = 0
    for entry in removed:
        rel = entry.get("local_path")
        if not rel:
            continue
        path = resolve_local_path(rel)
        if path.is_file():
            if dry_run:
                pass
            else:
                path.unlink()
                deleted_files += 1

    if not dry_run:
        manifest_path.write_text(
            json.dumps(kept, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )

    return {
        "layer_id": layer_id,
        "before": len(items),
        "kept": len(kept),
        "removed": len(removed),
        "deleted_files": deleted_files,
        "by_group": {
            g: {
                "kept": sum(1 for k in kept if group_key(k) == g),
                "removed": sum(1 for r in removed if group_key(r) == g),
            }
            for g in sorted(set(group_key(x) for x in items))
        },
    }


def curate_output(output_dir: Path, rules: dict, *, dry_run: bool, min_score: int) -> list[dict]:
    results = []
    for manifest in sorted(output_dir.glob("*/manifest.json")):
        r = curate_manifest(manifest, rules, dry_run=dry_run, min_score=min_score)
        if r.get("skipped"):
            print(f"  跳过(无规则): {r['layer_id']}")
            continue
        results.append(r)
        print(
            f"  {r['layer_id']}: {r['before']} → {r['kept']} "
            f"(删 {r['removed']}, 文件 {r['deleted_files']})"
        )
    return results


def cleanup_empty_dirs(root: Path, dry_run: bool) -> int:
    count = 0
    for d in sorted(root.rglob("*"), key=lambda p: len(p.parts), reverse=True):
        if d.is_dir() and not any(d.iterdir()):
            if not dry_run:
                d.rmdir()
            count += 1
    return count


def cleanup_orphans(output_dir: Path, dry_run: bool) -> int:
    """删除 manifest 中未引用的音频文件。"""
    referenced: set[Path] = set()
    for manifest in output_dir.glob("*/manifest.json"):
        items = json.loads(manifest.read_text(encoding="utf-8"))
        for entry in items:
            rel = entry.get("local_path")
            if rel:
                referenced.add(resolve_local_path(rel).resolve())

    removed = 0
    for ext in ("*.mp3", "*.m4a"):
        for path in output_dir.rglob(ext):
            if path.resolve() not in referenced:
                if not dry_run:
                    path.unlink()
                removed += 1
    return removed


def main() -> None:
    parser = argparse.ArgumentParser(description="筛选剪映音效/音乐库")
    parser.add_argument("--rain", action="store_true", help="整理 assets/rain_sound")
    parser.add_argument("--lake", action="store_true", help="整理 assets/lake_sound")
    parser.add_argument("--all", action="store_true", help="整理 rain + lake")
    parser.add_argument("--dry-run", action="store_true", help="只统计，不删除")
    parser.add_argument("--min-score", type=int, default=0, help="最低保留分数")
    args = parser.parse_args()

    if not RULES_PATH.is_file():
        print(f"Error: 找不到 {RULES_PATH}", file=sys.stderr)
        sys.exit(1)

    if args.all or (not args.rain and not args.lake):
        targets = list(ASSET_TARGETS.values())
    else:
        if args.rain:
            targets.append(ASSET_TARGETS["rain"])
        if args.lake:
            targets.append(ASSET_TARGETS["lake"])

    rules = load_rules()
    mode = "dry-run" if args.dry_run else "apply"
    print(f"剪映库整理 ({mode}), min_score={args.min_score}")

    total_before = 0
    total_kept = 0
    total_removed = 0

    for out in targets:
        if not out.is_dir():
            print(f"跳过(不存在): {out}")
            continue
        print(f"\n==> {out.relative_to(REPO_ROOT)}")
        results = curate_output(out, rules, dry_run=args.dry_run, min_score=args.min_score)
        for r in results:
            total_before += r["before"]
            total_kept += r["kept"]
            total_removed += r["removed"]
        empty = cleanup_empty_dirs(out, args.dry_run)
        if empty:
            print(f"  清理空目录: {empty}")
        orphans = cleanup_orphans(out, args.dry_run)
        if orphans:
            print(f"  孤立文件: {orphans}")

    print(f"\n合计: {total_before} → {total_kept} (移除 {total_removed})")
    if args.dry_run:
        print("未删除文件。确认后运行: python3 curate.py --all")


if __name__ == "__main__":
    main()
