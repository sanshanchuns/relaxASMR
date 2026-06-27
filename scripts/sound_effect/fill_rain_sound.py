#!/usr/bin/env python3
"""初始化 / 填充 Rain 六层声源库。

单一性原则：文件名含 ≥3 类声源或混合关键词 → 拒绝（见 sound_purity.py）。

用法（仓库根目录）：
  python3 scripts/sound_effect/fill_rain_sound.py --init-dirs
  python3 scripts/sound_effect/fill_rain_sound.py --from-boom      # Boom 优先，每目录上限 10
  python3 scripts/sound_effect/fill_rain_sound.py --from-backup    # 仅补 Boom 未满目录
  python3 scripts/sound_effect/fill_rain_sound.py --refill         # 完整重填
  python3 scripts/sound_effect/fill_rain_sound.py --from-stores   # Epidemic/Envato 补足<10 的目录
  python3 scripts/sound_effect/fill_rain_sound.py --stores-dry-run
  python3 scripts/sound_effect/fill_rain_sound.py --purge-mixed
"""

from __future__ import annotations

import argparse
import json
import re
import shutil
import subprocess
import sys
from pathlib import Path

from sound_purity import is_pure_single_source, purity_check

SCRIPT_DIR = Path(__file__).resolve().parent
REPO_ROOT = SCRIPT_DIR.parent.parent
SCHEMA_PATH = SCRIPT_DIR / "rain_library_schema.json"
REJECTED_DIR = "_rejected_mixed"
RECYCLED_SUBDIR = "_recycled"
BOOM_STEM_RE = re.compile(r"(?:^|_)qp\d+|ambtrop|b00m", re.IGNORECASE)
CANONICAL_SUFFIX_RE = re.compile(r"_(\d+)$")


def load_schema() -> dict:
    return json.loads(SCHEMA_PATH.read_text(encoding="utf-8"))


def rain_root(schema: dict) -> Path:
    return REPO_ROOT / schema["root"]


def init_dirs(schema: dict) -> int:
    root = rain_root(schema)
    count = 0
    for layer, cats in schema["layers"].items():
        for cat, subs in cats.items():
            if isinstance(subs, list):
                for sub in subs:
                    (root / layer / cat / sub).mkdir(parents=True, exist_ok=True)
                    count += 1
            else:
                (root / layer / cat).mkdir(parents=True, exist_ok=True)
                count += 1
    (root / schema["backup_dir"]).mkdir(parents=True, exist_ok=True)
    print(f"==> 创建目录 {count} 个 under {root}")
    return count


def normalize(text: str) -> str:
    return re.sub(r"[_\s]+", " ", text.lower())


def classify_boom(name: str, schema: dict) -> str | None:
    n = normalize(name)
    for rule in schema["boom_rules"]:
        for pat in rule["patterns"]:
            if pat in n:
                return rule["path"]
    return None


def count_mp3(dir_path: Path) -> int:
    if not dir_path.is_dir():
        return 0
    return sum(1 for _ in dir_path.glob("*.mp3"))


def sanitize_stem(src: Path) -> str:
    stem = re.sub(r'[<>:"/\\|?*\x00-\x1f]', "_", src.stem)
    return re.sub(r"\s+", "_", stem.strip())[:120] or "sound"


def canonical_stem(filename: str) -> str:
    """同一素材多次入库时 safe_dest_name 会加 _2/_3，归并为同一 canonical。"""
    stem = Path(filename).stem
    while True:
        m = CANONICAL_SUFFIX_RE.search(stem)
        if not m or int(m.group(1)) < 2:
            break
        stem = stem[:m.start()]
    return stem


def dest_dir_has_canonical(dest_dir: Path, canon: str) -> bool:
    if not dest_dir.is_dir():
        return False
    return any(canonical_stem(p.name) == canon for p in dest_dir.glob("*.mp3"))


def dest_for_import(src: Path, dest_dir: Path) -> Path | None:
    """目标目录尚无同 canonical 素材时返回写入路径；已存在则跳过（不生成 _2 副本）。"""
    stem = sanitize_stem(src)
    canon = canonical_stem(f"{stem}.mp3")
    if dest_dir_has_canonical(dest_dir, canon):
        return None
    dest = dest_dir / f"{stem}.mp3"
    return dest if not dest.exists() else None


def safe_dest_name(src: Path, dest_dir: Path) -> Path:
    stem = sanitize_stem(src)
    dest = dest_dir / f"{stem}.mp3"
    if not dest.exists():
        return dest
    i = 2
    while True:
        cand = dest_dir / f"{stem}_{i}.mp3"
        if not cand.exists():
            return cand
        i += 1


def convert_to_mp3(src: Path, dest: Path) -> bool:
    dest.parent.mkdir(parents=True, exist_ok=True)
    cmd = [
        "ffmpeg", "-y", "-loglevel", "error", "-i", str(src),
        "-codec:a", "libmp3lame", "-q:a", "2", str(dest),
    ]
    try:
        subprocess.run(cmd, check=True, capture_output=True)
        return dest.is_file()
    except subprocess.CalledProcessError:
        return False


def copy_mp3(src: Path, dest: Path, move: bool = False) -> bool:
    dest.parent.mkdir(parents=True, exist_ok=True)
    if dest.exists():
        return False
    if move:
        shutil.move(str(src), str(dest))
    else:
        shutil.copy2(src, dest)
    return True


def skip_mixed(name: str, label: str) -> bool:
    if is_pure_single_source(name):
        return False
    ok, reason = purity_check(name)
    print(f"  pass ({label}): {name} — {reason}")
    return not ok


def iter_boom_wavs(schema: dict):
    """按 boom_libraries 优先级遍历 wav（先 Nature Essentials 等）。"""
    seen: set[Path] = set()
    for boom_root in schema.get("boom_roots", []):
        base = Path(boom_root)
        if not base.is_dir():
            print(f"Warning: boom root missing: {base}", file=sys.stderr)
            continue
        listed = schema.get("boom_libraries", [])
        for lib_name in listed:
            lib_path = base / lib_name
            if not lib_path.is_dir():
                continue
            for wav in sorted(lib_path.rglob("*.wav")) + sorted(lib_path.rglob("*.WAV")):
                key = wav.resolve()
                if key not in seen:
                    seen.add(key)
                    yield wav, lib_name
        for d in sorted(base.iterdir()):
            if not d.is_dir() or d.name in listed:
                continue
            for wav in sorted(d.rglob("*.wav")) + sorted(d.rglob("*.WAV")):
                key = wav.resolve()
                if key not in seen:
                    seen.add(key)
                    yield wav, d.name


def from_boom(schema: dict, limit: int) -> tuple[int, int, int]:
    root = rain_root(schema)
    added, skipped, rejected = 0, 0, 0
    for wav, lib_name in iter_boom_wavs(schema):
        if skip_mixed(wav.name, "boom"):
            rejected += 1
            continue
        rel = classify_boom(wav.name, schema)
        if not rel:
            skipped += 1
            continue
        leaf = classified_leaf(rel, schema)
        if not leaf:
            skipped += 1
            continue
        dest_dir = leaf
        if count_mp3(dest_dir) >= limit:
            continue
        dest = dest_for_import(wav, dest_dir)
        if dest is None:
            skipped += 1
            continue
        if convert_to_mp3(wav, dest):
            added += 1
            print(f"  boom [{lib_name}] → {leaf.relative_to(root)}/{dest.name}")
    print(f"==> Boom: +{added} mp3, 未匹配 {skipped} wav, 单一性拒绝 {rejected}")
    return added, skipped, rejected


def backup_target(rel_sub: str, schema: dict) -> str:
    mapping = schema.get("backup_subfolder_map", {})
    for key, target in mapping.items():
        if rel_sub == key or rel_sub.startswith(key + "/"):
            return target
    top = rel_sub.split("/")[0] if rel_sub else ""
    if top in schema.get("layers", {}):
        return rel_sub
    parts = rel_sub.split("/")
    old_layer = parts[0] if parts else ""
    layer_map = {
        "1_base": "3_environment/air",
        "2_rain": "1_rain/intensity/light",
        "4_water": "4_water/dripping",
        "5_env": "3_environment/ambience/forest",
        "6_life": "5_wildlife/birds",
        "7_accent": "6_human",
    }
    return layer_map.get(old_layer, rel_sub if top in schema.get("layers", {}) else rel_sub)


def backup_dest_leaf(mp3: Path, rel_sub: str, schema: dict) -> Path | None:
    """文件名分类优先于 backup 子目录路径（避免 rain_on_wood 等未映射目录误落 leaves）。"""
    root = rain_root(schema)
    by_name = classify_boom(mp3.name, schema)
    if by_name:
        return classified_leaf(by_name, schema)
    target = backup_target(rel_sub, schema)
    return classified_leaf(target, schema) or nearest_leaf(target, schema)


def from_backup(schema: dict, limit: int, move: bool = True) -> tuple[int, int, int]:
    """仅填补 Boom 未填满的目录（每目录 < limit）；扫描 before_backup 含 _recycled。"""
    root = rain_root(schema)
    backup = root / schema["backup_dir"]
    if not backup.is_dir():
        print(f"Warning: no backup dir {backup}", file=sys.stderr)
        return 0, 0, 0
    added, rejected, skipped_full = 0, 0, 0
    for mp3 in sorted(backup.rglob("*.mp3")):
        if skip_mixed(mp3.name, "backup"):
            rejected += 1
            continue
        try:
            rel_sub = str(mp3.relative_to(backup).parent).replace("\\", "/")
        except ValueError:
            continue
        if rel_sub.startswith(RECYCLED_SUBDIR + "/"):
            rel_sub = rel_sub[len(RECYCLED_SUBDIR) + 1:]
        leaf = backup_dest_leaf(mp3, rel_sub, schema)
        if not leaf:
            continue
        dest_dir = leaf
        if count_mp3(dest_dir) >= limit:
            skipped_full += 1
            continue
        dest = dest_for_import(mp3, dest_dir)
        if dest is None:
            skipped_full += 1
            continue
        if copy_mp3(mp3, dest, move=move):
            added += 1
    print(
        f"==> Backup: {'移动' if move else '复制'} {added} mp3, "
        f"单一性拒绝 {rejected}, 目录已满跳过 {skipped_full}"
    )
    return added, rejected, skipped_full


def is_boom_sourced(filename: str) -> bool:
    stem = Path(filename).stem
    return bool(BOOM_STEM_RE.search(stem.replace("-", "_")))


def iter_leaf_dirs(schema: dict) -> list[Path]:
    root = rain_root(schema)
    dirs: list[Path] = []
    for layer, cats in schema["layers"].items():
        for cat, subs in cats.items():
            if isinstance(subs, list):
                for sub in subs:
                    dirs.append(root / layer / cat / sub)
            else:
                dirs.append(root / layer / cat)
    return dirs


def nearest_leaf(rel_str: str, schema: dict) -> Path | None:
    root = rain_root(schema)
    rel_str = rel_str.replace("\\", "/")
    leaves = iter_leaf_dirs(schema)
    for leaf in leaves:
        leaf_rel = str(leaf.relative_to(root)).replace("\\", "/")
        if leaf_rel == rel_str:
            return leaf
    under = sorted(
        [l for l in leaves if str(l.relative_to(root)).replace("\\", "/").startswith(rel_str + "/")],
        key=lambda p: str(p),
    )
    return under[0] if under else None


def classified_leaf(classified: str, schema: dict) -> Path | None:
    return nearest_leaf(classified, schema)


def resolve_dest_dir(mp3: Path, schema: dict) -> Path | None:
    """将库内 mp3 归到 schema 叶子目录。"""
    root = rain_root(schema)
    try:
        rel_parent = mp3.parent.relative_to(root)
    except ValueError:
        return None
    rel_str = str(rel_parent).replace("\\", "/")
    for leaf in iter_leaf_dirs(schema):
        if mp3.parent == leaf:
            return leaf
    classified = classify_boom(mp3.name, schema)
    if classified:
        leaf = classified_leaf(classified, schema)
        if leaf:
            return leaf
    return nearest_leaf(rel_str, schema)


def rebalance_dirs(schema: dict, limit: int) -> int:
    """每叶子目录仅保留 Boom 素材（≤limit），其余移回 before_backup/_recycled。"""
    root = rain_root(schema)
    recycled_root = root / schema["backup_dir"] / RECYCLED_SUBDIR
    groups: dict[Path, list[Path]] = {}
    for mp3 in iter_library_mp3(root):
        dest_dir = resolve_dest_dir(mp3, schema)
        if dest_dir is None:
            continue
        groups.setdefault(dest_dir, []).append(mp3)

    moved, consolidated = 0, 0
    for dest_dir, mp3s in sorted(groups.items(), key=lambda x: str(x[0])):
        boom = sorted([p for p in mp3s if is_boom_sourced(p.name)], key=lambda p: p.name)
        keep = boom[:limit]
        drop = [p for p in mp3s if p not in keep]
        rel_dir = dest_dir.relative_to(root)
        for p in keep:
            if p.parent != dest_dir:
                target = dest_dir / p.name
                if not target.exists():
                    dest_dir.mkdir(parents=True, exist_ok=True)
                    shutil.move(str(p), str(target))
                    consolidated += 1
        for p in drop:
            dest = recycled_root / rel_dir / p.name
            dest.parent.mkdir(parents=True, exist_ok=True)
            if dest.exists():
                dest = safe_dest_name(p, dest.parent)
            shutil.move(str(p), str(dest))
            moved += 1
        if drop or consolidated:
            print(f"  rebalance {rel_dir}: keep {len(keep)} boom, recycled {len(drop)}")
    print(
        f"==> 回收 {moved} 条至 before_backup/{RECYCLED_SUBDIR}/，"
        f"归并 {consolidated} 条（每目录 Boom 上限 {limit}）"
    )
    return moved


def iter_library_mp3(root: Path) -> list[Path]:
    out: list[Path] = []
    for mp3 in root.rglob("*.mp3"):
        if REJECTED_DIR in mp3.parts or schema_backup_part(mp3):
            continue
        out.append(mp3)
    return out


def schema_backup_part(mp3: Path) -> bool:
    return "before_backup" in mp3.parts


def audit_purity(schema: dict) -> int:
    root = rain_root(schema)
    mixed: list[tuple[Path, str]] = []
    for mp3 in iter_library_mp3(root):
        ok, reason = purity_check(mp3.name)
        if not ok:
            mixed.append((mp3, reason))
    print(f"==> 审计: {len(mixed)} / {len(iter_library_mp3(root))} 条不符合单一性")
    for p, reason in mixed[:30]:
        print(f"  {p.relative_to(root)} — {reason}")
    if len(mixed) > 30:
        print(f"  ... 另有 {len(mixed) - 30} 条")
    return len(mixed)


def purge_mixed(schema: dict) -> int:
    root = rain_root(schema)
    reject_root = root / REJECTED_DIR
    n = 0
    for mp3 in iter_library_mp3(root):
        ok, reason = purity_check(mp3.name)
        if ok:
            continue
        rel = mp3.relative_to(root)
        dest = reject_root / rel
        dest.parent.mkdir(parents=True, exist_ok=True)
        shutil.move(str(mp3), str(dest))
        n += 1
        print(f"  purge → {REJECTED_DIR}/{rel} ({reason})")
    print(f"==> 已移出 {n} 条至 {REJECTED_DIR}/")
    return n


def pick_canonical_keep(files: list[Path]) -> Path:
    def rank(p: Path) -> tuple:
        stem = p.stem
        exact = 0 if stem == canonical_stem(p.name) else 1
        boom = 0 if is_boom_sourced(p.name) else 1
        return (exact, boom, len(stem), p.name)

    return min(files, key=rank)


def dedupe_dirs(schema: dict) -> int:
    """同目录内 canonical 重复的 mp3 只保留一条，其余移入 _recycled。"""
    root = rain_root(schema)
    recycled_root = root / schema["backup_dir"] / RECYCLED_SUBDIR
    removed = 0
    for dest_dir in iter_leaf_dirs(schema):
        mp3s = list(dest_dir.glob("*.mp3"))
        if len(mp3s) < 2:
            continue
        groups: dict[str, list[Path]] = {}
        for p in mp3s:
            groups.setdefault(canonical_stem(p.name), []).append(p)
        rel_dir = dest_dir.relative_to(root)
        for canon, files in groups.items():
            if len(files) < 2:
                continue
            keep = pick_canonical_keep(files)
            for p in files:
                if p == keep:
                    continue
                dest = recycled_root / rel_dir / p.name
                dest.parent.mkdir(parents=True, exist_ok=True)
                if dest.exists():
                    dest = safe_dest_name(p, dest.parent)
                shutil.move(str(p), str(dest))
                removed += 1
            print(f"  dedupe {rel_dir}/{canon}: keep {keep.name}, -{len(files) - 1}")
    print(f"==> 去重移出 {removed} 条至 before_backup/{RECYCLED_SUBDIR}/")
    return removed


def relocate_misplaced(schema: dict) -> int:
    """按文件名重新分类，纠正误入目录的 backup 素材。"""
    root = rain_root(schema)
    recycled_root = root / schema["backup_dir"] / RECYCLED_SUBDIR
    moved = 0
    for mp3 in iter_library_mp3(root):
        classified = classify_boom(mp3.name, schema)
        if not classified:
            continue
        target = classified_leaf(classified, schema)
        if not target or mp3.parent == target:
            continue
        if dest_dir_has_canonical(target, canonical_stem(mp3.name)):
            rel = mp3.relative_to(root)
            dest = recycled_root / rel
            dest.parent.mkdir(parents=True, exist_ok=True)
            if dest.exists():
                dest = safe_dest_name(mp3, dest.parent)
            shutil.move(str(mp3), str(dest))
            moved += 1
            print(f"  relocate dup → recycled {rel}")
            continue
        dest = dest_for_import(mp3, target)
        if dest is None:
            continue
        dest.parent.mkdir(parents=True, exist_ok=True)
        shutil.move(str(mp3), str(dest))
        moved += 1
        print(f"  relocate {mp3.name} → {target.relative_to(root)}/{dest.name}")
    print(f"==> 重新归类 {moved} 条")
    return moved


def main() -> None:
    parser = argparse.ArgumentParser(description="Fill rain_sound six-layer library")
    parser.add_argument("--init-dirs", action="store_true", help="创建六层目录树")
    parser.add_argument("--from-boom", action="store_true", help="从 Boom 库转 mp3")
    parser.add_argument("--from-backup", action="store_true", help="从 before_backup 迁入")
    parser.add_argument("--all", action="store_true", help="init + boom（优先）+ backup 补缺")
    parser.add_argument(
        "--refill",
        action="store_true",
        help="purge → rebalance（Boom 保留）→ boom → backup 补缺",
    )
    parser.add_argument(
        "--rebalance",
        action="store_true",
        help="非 Boom 素材回收到 before_backup/_recycled，每目录仅留 Boom≤limit",
    )
    parser.add_argument("--limit", type=int, default=0, help="每目录上限（0=用 schema 默认）")
    parser.add_argument("--copy-backup", action="store_true", help="backup 复制而非移动")
    parser.add_argument("--audit-purity", action="store_true", help="审计库内混合素材")
    parser.add_argument("--purge-mixed", action="store_true", help="移出混合素材到 _rejected_mixed")
    parser.add_argument("--dedupe", action="store_true", help="同目录 canonical 重复素材只保留一条")
    parser.add_argument("--relocate", action="store_true", help="按文件名重新归类误放目录的素材")
    parser.add_argument(
        "--from-stores",
        action="store_true",
        help="Epidemic/Envato 按关键字补足每目录不足 limit 的条目",
    )
    parser.add_argument(
        "--stores-dry-run",
        action="store_true",
        help="仅列出需补足的目录与关键字，不下载",
    )
    parser.add_argument(
        "--stores-source",
        choices=("both", "epidemic", "envato"),
        default="both",
        help="补充来源（默认 both）",
    )
    parser.add_argument(
        "--fill-vegetation-stores",
        action="store_true",
        help="vegetation 各关键词目录各补 10 Epidemic + 10 Envato",
    )
    parser.add_argument(
        "--vegetation-stores-dry-run",
        action="store_true",
        help="预览 vegetation 各目录缺口",
    )
    parser.add_argument(
        "--fill-impact-water-stores",
        action="store_true",
        help="2_impact/water 各关键词各补 10 Epidemic + 10 Envato",
    )
    parser.add_argument(
        "--impact-water-stores-dry-run",
        action="store_true",
        help="预览 2_impact/water 各目录缺口",
    )
    parser.add_argument(
        "--per-source",
        type=int,
        default=10,
        help="每来源目标条数（vegetation / impact water，默认 10）",
    )
    args = parser.parse_args()

    schema = load_schema()
    limit = args.limit or schema.get("per_dir_limit", 10)

    if args.audit_purity:
        audit_purity(schema)
        return
    if args.purge_mixed:
        purge_mixed(schema)
        return
    if args.rebalance:
        rebalance_dirs(schema, limit)
        return
    if args.dedupe:
        dedupe_dirs(schema)
        return
    if args.relocate:
        relocate_misplaced(schema)
        return

    from supplement_stores import (
        fill_impact_water_stores,
        fill_vegetation_stores,
        supplement_from_stores,
    )

    store_sources = {
        "both": ("epidemic", "envato"),
        "epidemic": ("epidemic",),
        "envato": ("envato",),
    }[args.stores_source]

    if args.vegetation_stores_dry_run:
        fill_vegetation_stores(schema, args.per_source, dry_run=True)
        return
    if args.fill_vegetation_stores:
        fill_vegetation_stores(schema, args.per_source)
        dedupe_dirs(schema)
        return
    if args.impact_water_stores_dry_run:
        fill_impact_water_stores(schema, args.per_source, dry_run=True)
        return
    if args.fill_impact_water_stores:
        fill_impact_water_stores(schema, args.per_source)
        dedupe_dirs(schema)
        return

    if args.stores_dry_run:
        supplement_from_stores(schema, limit, sources=store_sources, dry_run=True)
        return
    if args.from_stores:
        supplement_from_stores(schema, limit, sources=store_sources)
        dedupe_dirs(schema)
        return

    if args.refill:
        print("==> refill: purge → dedupe → rebalance → boom → backup → stores → dedupe → relocate")
        purge_mixed(schema)
        dedupe_dirs(schema)
        rebalance_dirs(schema, limit)
        from_boom(schema, limit)
        dedupe_dirs(schema)
        from_backup(schema, limit, move=not args.copy_backup)
        dedupe_dirs(schema)
        supplement_from_stores(schema, limit, sources=store_sources)
        dedupe_dirs(schema)
        relocate_misplaced(schema)
        return

    if args.all:
        args.init_dirs = True
        args.from_boom = True
        args.from_backup = True

    if not (args.init_dirs or args.from_backup or args.from_boom or args.from_stores):
        parser.print_help()
        sys.exit(1)

    if args.init_dirs:
        init_dirs(schema)
    # 填充顺序：Boom 优先，backup 只补未满目录
    if args.from_boom:
        from_boom(schema, limit)
    if args.from_backup:
        from_backup(schema, limit, move=not args.copy_backup)
    if args.from_boom or args.from_backup:
        dedupe_dirs(schema)


if __name__ == "__main__":
    main()
