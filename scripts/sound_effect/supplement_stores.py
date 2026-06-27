"""Envato / Epidemic 按叶子目录关键字补足声源库（Boom + backup 仍不足时）。"""

from __future__ import annotations

import importlib.util
import json
import shutil
import sys
import tempfile
import time
from pathlib import Path

SCRIPT_DIR = Path(__file__).resolve().parent
REPO_ROOT = SCRIPT_DIR.parent.parent
SCRIPTS_ROOT = REPO_ROOT / "scripts"
STORE_META = ".store_sources.json"
VEGETATION_PREFIX = "2_impact/vegetation"
IMPACT_WATER_PREFIX = "2_impact/water"


def _load_module(name: str, path: Path):
    if str(SCRIPTS_ROOT) not in sys.path:
        sys.path.insert(0, str(SCRIPTS_ROOT))
    spec = importlib.util.spec_from_file_location(name, path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def keywords_for_leaf(rel: str, schema: dict) -> list[str]:
    rel = rel.replace("\\", "/")
    kws: list[str] = []
    best_len = -1
    for rule in schema.get("boom_rules", []):
        p = rule["path"]
        if rel == p or rel.startswith(p + "/"):
            if len(p) > best_len:
                best_len = len(p)
                kws = list(rule["patterns"])
    parts = [p.replace("_", " ") for p in rel.split("/")]
    leaf, cat = parts[-1], parts[-2] if len(parts) >= 2 else ""
    if rel.startswith("1_rain/intensity/"):
        kws.insert(0, f"{leaf} rain")
    elif rel.startswith("1_rain/distance/"):
        kws.insert(0, f"{leaf} rain")
    elif rel.startswith("1_rain/perspective/"):
        kws.insert(0, f"{leaf} rain")
    elif rel.startswith("2_impact/"):
        kws.insert(0, f"rain on {leaf}")
        if cat and cat != leaf:
            kws.append(f"rain on {cat}")
    elif rel.startswith("3_environment/air/"):
        kws.insert(0, f"{leaf}")
    elif rel.startswith("3_environment/wind/"):
        kws.insert(0, f"{leaf}")
    elif rel.startswith("3_environment/ambience/"):
        kws.insert(0, f"{leaf} ambience")
    elif rel.startswith("3_environment/room_tone/"):
        kws.insert(0, f"{leaf}")
    elif rel.startswith("4_water/"):
        kws.insert(0, leaf)
        if cat:
            kws.append(f"{cat} {leaf}")
    elif rel.startswith("5_wildlife/birds/"):
        kws.insert(0, f"{leaf} bird")
    elif rel.startswith("5_wildlife/insects/"):
        kws.insert(0, leaf)
    elif rel.startswith("5_wildlife/amphibians/"):
        kws.insert(0, f"{leaf} frog" if "frog" not in leaf else leaf)
    elif rel.startswith("5_wildlife/mammals/"):
        kws.insert(0, leaf)
    elif rel.startswith("6_human/"):
        kws.insert(0, leaf.replace("_", " "))
    seen: set[str] = set()
    out: list[str] = []
    for k in kws:
        kl = k.lower().strip()
        if kl and kl not in seen:
            seen.add(kl)
            out.append(k)
    return out[:6]


def load_store_meta(leaf_dir: Path) -> dict[str, list[str]]:
    path = leaf_dir / STORE_META
    if not path.is_file():
        return {"epidemic": [], "envato": []}
    data = json.loads(path.read_text(encoding="utf-8"))
    return {
        "epidemic": list(data.get("epidemic", [])),
        "envato": list(data.get("envato", [])),
    }


def save_store_meta(leaf_dir: Path, meta: dict[str, list[str]]) -> None:
    path = leaf_dir / STORE_META
    path.write_text(json.dumps(meta, ensure_ascii=False, indent=2), encoding="utf-8")


def prune_store_meta(leaf_dir: Path, meta: dict[str, list[str]]) -> dict[str, list[str]]:
    pruned = {"epidemic": [], "envato": []}
    for source in ("epidemic", "envato"):
        for name in meta.get(source, []):
            if (leaf_dir / name).is_file():
                pruned[source].append(name)
    return pruned


def count_store_source(leaf_dir: Path, source: str) -> int:
    meta = prune_store_meta(leaf_dir, load_store_meta(leaf_dir))
    return len(meta.get(source, []))


def register_store_file(leaf_dir: Path, source: str, filename: str) -> None:
    meta = prune_store_meta(leaf_dir, load_store_meta(leaf_dir))
    names = meta.setdefault(source, [])
    if filename not in names:
        names.append(filename)
    save_store_meta(leaf_dir, meta)


def list_gaps(schema: dict, limit: int) -> list[tuple[Path, dict[str, int], list[str]]]:
    from fill_rain_sound import count_mp3, iter_leaf_dirs, rain_root

    gaps: list[tuple[Path, dict[str, int], list[str]]] = []
    root = rain_root(schema)
    for leaf in iter_leaf_dirs(schema):
        n = count_mp3(leaf)
        if n >= limit:
            continue
        rel = str(leaf.relative_to(root)).replace("\\", "/")
        gaps.append((leaf, {"_total": limit - n, "_target": limit}, keywords_for_leaf(rel, schema)))
    return gaps


def list_category_targets(
    schema: dict, category_rel: str, per_source: int
) -> list[tuple[Path, dict[str, int], list[str]]]:
    from fill_rain_sound import rain_root

    category_rel = category_rel.replace("\\", "/").strip("/")
    parts = category_rel.split("/")
    if len(parts) < 2:
        raise ValueError(f"category_rel 需为 layer/category: {category_rel}")
    layer, cat = parts[0], parts[1]
    subs = schema["layers"][layer][cat]
    root = rain_root(schema)
    targets: list[tuple[Path, dict[str, int], list[str]]] = []
    for sub in subs:
        leaf = root / layer / cat / sub
        leaf.mkdir(parents=True, exist_ok=True)
        rel = f"{layer}/{cat}/{sub}"
        need = {
            "epidemic": max(0, per_source - count_store_source(leaf, "epidemic")),
            "envato": max(0, per_source - count_store_source(leaf, "envato")),
            "_per_source": per_source,
        }
        if need["epidemic"] or need["envato"]:
            targets.append((leaf, need, keywords_for_leaf(rel, schema)))
    return targets


def list_vegetation_targets(
    schema: dict, per_source: int
) -> list[tuple[Path, dict[str, int], list[str]]]:
    return list_category_targets(schema, VEGETATION_PREFIX, per_source)


def _load_store_clients(sources: tuple[str, ...]):
    epidemic_mod = envato_mod = None
    epidemic_creds = envato_creds = None
    epidemic_defaults = envato_defaults = {}

    if "epidemic" in sources:
        epath = SCRIPTS_ROOT / "epidemic_audio" / "download.py"
        ecfg = SCRIPTS_ROOT / "epidemic_audio" / "rain_layers.json"
        if epath.is_file():
            epidemic_mod = _load_module("epidemic_download", epath)
            epidemic_defaults = epidemic_mod.load_config(ecfg).get("defaults", {})
            cred_path = SCRIPTS_ROOT / "epidemic_audio" / "reference.yaml"
            try:
                epidemic_creds = epidemic_mod.load_credentials(cred_path)
            except RuntimeError as exc:
                print(f"Warning: Epidemic 跳过 — {exc}", file=sys.stderr)

    if "envato" in sources:
        vpath = SCRIPTS_ROOT / "envato_audio" / "download.py"
        vcfg = SCRIPTS_ROOT / "envato_audio" / "rain_layers.json"
        if vpath.is_file():
            envato_mod = _load_module("envato_download", vpath)
            envato_defaults = envato_mod.load_config(vcfg).get("defaults", {})
            cred_path = SCRIPTS_ROOT / "envato_audio" / "envato_API.yaml"
            try:
                envato_creds = envato_mod.load_credentials(cred_path)
            except RuntimeError as exc:
                print(f"Warning: Envato 跳过 — {exc}", file=sys.stderr)

    return epidemic_mod, epidemic_creds, epidemic_defaults, envato_mod, envato_creds, envato_defaults


def _run_store_fill(
    schema: dict,
    jobs: list[tuple[Path, dict[str, int], list[str]]],
    *,
    dry_run: bool = False,
) -> tuple[int, int, int]:
    from fill_rain_sound import (
        classified_leaf,
        classify_boom,
        canonical_stem,
        convert_to_mp3,
        dest_dir_has_canonical,
        dest_for_import,
        rain_root,
    )
    from sound_purity import purity_check

    if not jobs:
        print("==> Stores: 无需补充")
        return 0, 0, 0

    if dry_run:
        for leaf, need, kws in jobs:
            rel = leaf.relative_to(rain_root(schema))
            if "_total" in need:
                print(f"  {rel}: 缺 {need['_total']} 条 — {kws}")
            elif "_per_source" in need:
                print(
                    f"  {rel}: epidemic {need.get('epidemic', 0)}, "
                    f"envato {need.get('envato', 0)} "
                    f"(目标各 {need['_per_source']}) — {kws}"
                )
            else:
                print(
                    f"  {rel}: epidemic {need.get('epidemic', 0)}, "
                    f"envato {need.get('envato', 0)} — {kws}"
                )
        return 0, 0, len(jobs)

    (
        epidemic_mod,
        epidemic_creds,
        epidemic_defaults,
        envato_mod,
        envato_creds,
        envato_defaults,
    ) = _load_store_clients(("epidemic", "envato"))

    added, rejected = 0, 0
    global_seen: set[str] = set()

    def title_ok(title: str, item_id: str, target_leaf: Path) -> bool:
        fake = f"{item_id}_{title}.mp3"
        ok, _ = purity_check(fake)
        if not ok:
            return False
        classified = classify_boom(fake, schema)
        if classified:
            leaf = classified_leaf(classified, schema)
            if leaf and leaf != target_leaf:
                return False
        return True

    def import_mp3(
        src: Path, title: str, item_id: str, target_leaf: Path, source: str
    ) -> bool:
        nonlocal added, rejected
        fake = Path(f"{item_id}_{title}.mp3")
        if dest_dir_has_canonical(target_leaf, canonical_stem(fake.name)):
            return False
        dest = dest_for_import(fake, target_leaf)
        if dest is None:
            return False
        dest.parent.mkdir(parents=True, exist_ok=True)
        if src.suffix.lower() == ".mp3":
            shutil.move(str(src), str(dest))
        elif not convert_to_mp3(src, dest):
            rejected += 1
            return False
        register_store_file(target_leaf, source, dest.name)
        added += 1
        print(
            f"  {source} → {target_leaf.relative_to(rain_root(schema))}/{dest.name}"
        )
        return True

    for leaf, need, kws in jobs:
        rel = str(leaf.relative_to(rain_root(schema))).replace("\\", "/")
        combined_total = need.get("_total")
        if combined_total is not None:
            print(f"\n  [{rel}] 缺 {combined_total} 条, keywords: {kws}")
            remaining = {"epidemic": combined_total, "envato": combined_total}
            mode_combined = True
        else:
            print(
                f"\n  [{rel}] need epidemic {need.get('epidemic', 0)}, "
                f"envato {need.get('envato', 0)} — {kws}"
            )
            remaining = {
                "epidemic": need.get("epidemic", 0),
                "envato": need.get("envato", 0),
            }
            mode_combined = False

        for keyword in kws:
            if mode_combined:
                if remaining["epidemic"] <= 0:
                    break
            elif remaining["epidemic"] <= 0 and remaining["envato"] <= 0:
                break

            if remaining["epidemic"] > 0 and epidemic_creds and epidemic_mod:
                try:
                    items = epidemic_mod.search_items(
                        keyword,
                        epidemic_creds,
                        epidemic_defaults,
                        limit=max(remaining["epidemic"] * 4, 20),
                        browser=None,
                        browser_fallback=True,
                    )
                except Exception as exc:
                    print(f"    epidemic '{keyword}' 失败: {exc}", file=sys.stderr)
                    items = []
                for item in items:
                    if remaining["epidemic"] <= 0:
                        break
                    key = f"epidemic:{item['id']}"
                    if key in global_seen:
                        continue
                    global_seen.add(key)
                    if not title_ok(item["title"], str(item["id"]), leaf):
                        rejected += 1
                        continue
                        with tempfile.TemporaryDirectory() as tmp:
                            tmp_path = Path(tmp) / f"{item['id']}.mp3"
                            try:
                                epidemic_mod.download_file(
                                    item["url"], tmp_path, epidemic_creds
                                )
                            except Exception as exc:
                                print(
                                    f"    epidemic 下载失败 {item['id']}: {exc}",
                                    file=sys.stderr,
                                )
                                continue
                            if import_mp3(
                                tmp_path, item["title"], str(item["id"]), leaf, "epidemic"
                            ):
                                remaining["epidemic"] -= 1
                                if mode_combined:
                                    remaining["envato"] = remaining["epidemic"]
                        time.sleep(0.15)

            if mode_combined:
                if remaining["epidemic"] <= 0:
                    continue
            elif remaining["envato"] <= 0 or not envato_creds or not envato_mod:
                continue

            if not envato_creds or not envato_mod:
                continue
            if not mode_combined and remaining["envato"] <= 0:
                continue

            try:
                items = envato_mod.search_items(
                    keyword,
                    envato_creds,
                    envato_defaults,
                    limit=max(remaining["envato"] * 4, 20),
                    mode="auto",
                    browser=None,
                    browser_fallback=True,
                )
            except Exception as exc:
                print(f"    envato '{keyword}' 失败: {exc}", file=sys.stderr)
                items = []
            for item in items:
                if mode_combined:
                    if remaining["epidemic"] <= 0:
                        break
                elif remaining["envato"] <= 0:
                    break
                key = f"envato:{item['id']}"
                if key in global_seen:
                    continue
                global_seen.add(key)
                if not title_ok(item["title"], str(item["id"]), leaf):
                    rejected += 1
                    continue
                url, ext = envato_mod.pick_download_url(item, "mp3")
                with tempfile.TemporaryDirectory() as tmp:
                    tmp_path = Path(tmp) / f"{item['id']}.{ext}"
                    try:
                        envato_mod.download_file(url, tmp_path, envato_creds)
                    except Exception as exc:
                        print(
                            f"    envato 下载失败 {item['id']}: {exc}",
                            file=sys.stderr,
                        )
                        continue
                    if import_mp3(
                        tmp_path, item["title"], str(item["id"]), leaf, "envato"
                    ):
                        if mode_combined:
                            remaining["epidemic"] -= 1
                            remaining["envato"] = remaining["epidemic"]
                        else:
                            remaining["envato"] -= 1
                time.sleep(0.2)

    still_short = 0
    for leaf, need, _ in jobs:
        if "_total" in need:
            from fill_rain_sound import count_mp3
            target = need.get("_target", 10)
            if count_mp3(leaf) < target:
                still_short += 1
            continue
        if "_per_source" in need:
            per = need["_per_source"]
            if (
                count_store_source(leaf, "epidemic") < per
                or count_store_source(leaf, "envato") < per
            ):
                still_short += 1
            continue
        for source in ("epidemic", "envato"):
            target = need.get(source, 0)
            if target and count_store_source(leaf, source) < target:
                still_short += 1
                break

    print(f"\n==> Stores: +{added} mp3, 拒绝 {rejected}, 未达标目录 {still_short}")
    return added, rejected, still_short


def supplement_from_stores(
    schema: dict,
    limit: int,
    *,
    sources: tuple[str, ...] = ("epidemic", "envato"),
    dry_run: bool = False,
) -> tuple[int, int, int]:
    """不足 limit 的叶子目录用 Epidemic / Envato 关键字搜索并入库。"""
    jobs = list_gaps(schema, limit)
    if not jobs:
        print("==> Stores: 所有目录已满，无需补充")
        return 0, 0, 0
    print(f"==> Stores: {len(jobs)} 个目录不足 {limit} 条")
    return _run_store_fill(schema, jobs, dry_run=dry_run)


def fill_category_stores(
    schema: dict,
    category_rel: str,
    per_source: int = 10,
    *,
    dry_run: bool = False,
) -> tuple[int, int, int]:
    jobs = list_category_targets(schema, category_rel, per_source)
    label = category_rel.replace("/", " / ")
    print(
        f"==> {label}: {len(jobs)} 个关键词待补 "
        f"(各 epidemic×{per_source}, envato×{per_source})"
    )
    if dry_run and not jobs:
        parts = category_rel.split("/")
        n = len(schema["layers"][parts[0]][parts[1]])
        print(f"  全部 {n} 个关键词已达标")
    return _run_store_fill(schema, jobs, dry_run=dry_run)


def fill_vegetation_stores(
    schema: dict,
    per_source: int = 10,
    *,
    dry_run: bool = False,
) -> tuple[int, int, int]:
    return fill_category_stores(schema, VEGETATION_PREFIX, per_source, dry_run=dry_run)


def fill_impact_water_stores(
    schema: dict,
    per_source: int = 10,
    *,
    dry_run: bool = False,
) -> tuple[int, int, int]:
    return fill_category_stores(schema, IMPACT_WATER_PREFIX, per_source, dry_run=dry_run)
