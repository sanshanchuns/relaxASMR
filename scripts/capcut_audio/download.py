#!/usr/bin/env python3
"""从剪映（ulikecam）音效/音乐 API 按分层关键词批量下载素材库。

支持两类层级（layer.type）：
- effect：调用 effect/search 关键词搜索音效
- music ：调用 lv/v1/get_collection_songs 拉取音乐歌单

可按配置仅下载可商用素材（commercial_only）。
"""

from __future__ import annotations

import argparse
import json
import re
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path

SCRIPT_DIR = Path(__file__).resolve().parent
REPO_ROOT = SCRIPT_DIR.parent.parent
DEFAULT_CONFIG = SCRIPT_DIR / "rain_layers.json"

def resolve_output_root(defaults: dict) -> Path:
    raw = defaults.get("output_dir", "output")
    p = Path(raw)
    if p.is_absolute():
        return p
    if raw.startswith("assets/"):
        return REPO_ROOT / raw
    return SCRIPT_DIR / raw


EFFECT_SEARCH_URL = (
    "https://lv-api-sinfonlinec.ulikecam.com/artist/v1/effect/search"
    "?aid=3704&device_platform=mac&region=CN&app_name=JianyingPro&language=zh-Hans"
)
MUSIC_COLLECTION_URL = (
    "https://lv-pc-api-sinfonlinec.ulikecam.com/lv/v1/get_collection_songs"
    "?aid=3704&device_platform=mac&region=CN&app_name=JianyingPro&language=zh-Hans"
    "&version_code=10.7.8&channel=jianyingpro_beta"
)

EFFECT_HEADERS = {
    "Host": "lv-api-sinfonlinec.ulikecam.com",
    "content-type": "application/json",
    "user-agent": "Cronet/TTNetVersion:906739f5 2024-12-18",
}
MUSIC_HEADERS = {
    "Host": "lv-pc-api-sinfonlinec.ulikecam.com",
    "content-type": "application/json",
    "appvr": "10.7.8-beta1",
    "lan": "zh-Hans",
    "loc": "CN",
    "pf": "3",
    "user-agent": "Cronet/TTNetVersion:906739f5 2024-12-18",
}


def load_config(config_path: Path) -> dict:
    data = json.loads(config_path.read_text(encoding="utf-8"))
    return {
        "defaults": data.get("defaults", {}),
        "layers": data.get("layers", {}),
    }


def safe_filename(text: str, max_len: int = 60) -> str:
    cleaned = re.sub(r'[<>:"/\\|?*\x00-\x1f]', "_", text.strip())
    cleaned = re.sub(r"\s+", "_", cleaned)
    cleaned = cleaned.strip("._") or "untitled"
    return cleaned[:max_len]


def parse_business_info(business_info: dict | None) -> dict:
    """返回 {paid_type, paid_modes}。"""
    result = {"paid_type": "unknown", "paid_modes": []}
    if not business_info:
        return result
    raw = business_info.get("json_str", "")
    if not raw:
        return result
    try:
        info = json.loads(raw)
    except json.JSONDecodeError:
        return result
    result["paid_type"] = info.get("paid_type", "unknown")
    strategies = (
        info.get("commercial_strategy", {})
        .get("resource_export", {})
        .get("paid_strategy_list", [])
    )
    result["paid_modes"] = [s.get("paid_mode") for s in strategies if s.get("paid_mode")]
    return result


def http_post_json(url: str, headers: dict, body: dict) -> dict:
    payload = json.dumps(body).encode("utf-8")
    req = urllib.request.Request(url, data=payload, headers=headers, method="POST")
    with urllib.request.urlopen(req, timeout=30) as resp:
        data = json.loads(resp.read().decode("utf-8"))
    if data.get("ret") != "0":
        raise RuntimeError(f"API error: {data.get('errmsg', data)}")
    return data.get("data", {})


# ---------------------------------------------------------------------------
# Effect（音效）
# ---------------------------------------------------------------------------

def search_effects(query: str, offset: int, count: int) -> dict:
    body = {
        "app_id": 3704,
        "count": count,
        "effect_type": 3,
        "filter_optional": {
            "filter_paid_type": [],
            "filter_uncommercial": False,
            "no_copyrighted": False,
            "no_tuchong_order": False,
            "only_enterprise_commercial": False,
        },
        "need_recommend": False,
        "offset": offset,
        "pack_optional": {
            "need_collection_id": False,
            "need_contract": True,
            "need_favorite_info": False,
            "only_commercial": False,
        },
        "query": query,
        "replicate_sdk_version": "",
        "search_id": "",
        "search_option": {
            "aspect_ratio": "",
            "category_list": [],
            "effect_segment_type": None,
            "filter_uncommercial": False,
            "scene": "",
            "sticker_type": 0,
        },
        "statistics_optional": {
            "need_add_count": False,
            "need_favorite_count": False,
            "need_usage_count": False,
        },
        "strategy_extra": "",
    }
    return http_post_json(EFFECT_SEARCH_URL, EFFECT_HEADERS, body)


def parse_effect_item(item: dict) -> dict | None:
    common = item.get("common_attr") or {}
    audio = item.get("audio_effect") or {}
    effect_id = common.get("effect_id") or common.get("id")
    title = common.get("title") or ""
    download_info = common.get("download_info") or {}
    url = download_info.get("url") or (common.get("item_urls") or [None])[0]
    if not effect_id or not url:
        return None
    biz = parse_business_info(common.get("business_info"))
    return {
        "id": str(effect_id),
        "title": title,
        "url": url,
        "md5": common.get("md5", ""),
        "duration": audio.get("duration"),
        "duration_ms": audio.get("duration_ms"),
        "paid_type": biz["paid_type"],
        "paid_modes": biz["paid_modes"],
        "ext": "mp3",
    }


def effect_is_commercial(effect: dict) -> bool:
    """音效可免费商用：paid_type 为 free，或导出策略含 free。"""
    if effect["paid_type"] == "free":
        return True
    return "free" in (effect.get("paid_modes") or [])


def collect_for_keyword(
    query: str,
    target: int,
    commercial_only: bool,
    page_size: int,
    global_seen: set[str],
) -> list[dict]:
    results: list[dict] = []
    offset = 0
    while len(results) < target:
        data = search_effects(query, offset, page_size)
        items = data.get("effect_item_list") or []
        if not items:
            break
        for item in items:
            parsed = parse_effect_item(item)
            if not parsed:
                continue
            dedupe_key = parsed["md5"] or parsed["id"]
            if dedupe_key in global_seen:
                continue
            if commercial_only and not effect_is_commercial(parsed):
                continue
            global_seen.add(dedupe_key)
            parsed["source"] = query
            results.append(parsed)
            if len(results) >= target:
                break
        if not data.get("has_more"):
            break
        offset = data.get("next_offset", offset + len(items))
        time.sleep(0.3)
    return results


# ---------------------------------------------------------------------------
# Music（音乐）
# ---------------------------------------------------------------------------

def fetch_collection_songs(collection_id: str, offset: int, count: int) -> dict:
    body = {
        "count": count,
        "filter_commercial": False,
        "filter_paid_type": [],
        "id": int(collection_id),
        "offset": offset,
        "only_enterprise_commercial": False,
        "scene": 0,
        "strategy_extra": "",
    }
    return http_post_json(MUSIC_COLLECTION_URL, MUSIC_HEADERS, body)


def parse_song_item(song: dict) -> dict | None:
    song_id = song.get("id")
    url = song.get("preview_url")
    if not song_id or not url:
        return None
    return {
        "id": str(song_id),
        "title": song.get("title") or "",
        "author": song.get("author") or "",
        "url": url,
        "md5": "",
        "duration": song.get("duration"),
        "duration_ms": (song.get("duration") or 0) * 1000,
        "paid_type": song.get("paid_type", "unknown"),
        "is_commerce": bool(song.get("is_commerce")),
        "ext": "m4a",
    }


def collect_for_collection(
    collection_id: str,
    target: int,
    commercial_only: bool,
    page_size: int,
    global_seen: set[str],
) -> list[dict]:
    results: list[dict] = []
    offset = 0
    while len(results) < target:
        data = fetch_collection_songs(collection_id, offset, page_size)
        songs = data.get("songs") or []
        if not songs:
            break
        for song in songs:
            parsed = parse_song_item(song)
            if not parsed:
                continue
            if parsed["id"] in global_seen:
                continue
            if commercial_only and not parsed["is_commerce"]:
                continue
            global_seen.add(parsed["id"])
            results.append(parsed)
            if len(results) >= target:
                break
        if not data.get("has_more"):
            break
        offset += len(songs)
        time.sleep(0.3)
    return results


# ---------------------------------------------------------------------------
# 下载 / 落地
# ---------------------------------------------------------------------------

def download_file(url: str, dest: Path) -> None:
    dest.parent.mkdir(parents=True, exist_ok=True)
    req = urllib.request.Request(url, headers={"User-Agent": EFFECT_HEADERS["user-agent"]})
    with urllib.request.urlopen(req, timeout=120) as resp:
        dest.write_bytes(resp.read())


def local_path_for(output_root: Path, layer_id: str, group: str, item: dict) -> Path:
    group_dir = safe_filename(group.replace(" ", "_"))
    fname = f"{item['id']}_{safe_filename(item['title'])}.{item['ext']}"
    return output_root / layer_id / group_dir / fname


def resolve_manifest_dest(entry: dict, asset_root: Path) -> Path:
    """将 manifest 中的 local_path 解析为 assets 目录下的实际路径。"""
    rel = entry.get("local_path") or ""
    if rel.startswith("assets/"):
        return REPO_ROOT / rel
    legacy_prefixes = ("output_rain/", "output_lake/", "output/")
    for prefix in legacy_prefixes:
        if rel.startswith(prefix):
            sub = rel[len(prefix):]
            if prefix == "output_rain/":
                return REPO_ROOT / "assets" / "rain_sound" / sub
            if prefix == "output_lake/":
                return REPO_ROOT / "assets" / "lake_sound" / sub
            return asset_root / sub
    if rel:
        return REPO_ROOT / rel
    ext = "m4a" if entry.get("layer_type") == "music" else "mp3"
    group = entry.get("group") or "misc"
    return local_path_for(
        asset_root,
        entry.get("layer_id", "unknown"),
        group,
        {"id": entry["id"], "title": entry.get("title", ""), "ext": ext},
    )


def restore_from_manifest(
    asset_root: Path,
    *,
    layer_ids: list[str] | None = None,
    force: bool = False,
    fix_paths: bool = True,
) -> dict:
    """按已有 manifest.json 重新下载缺失的音频文件。"""
    stats = {"downloaded": 0, "skipped": 0, "failed": 0, "fixed_paths": 0}
    manifests = sorted(asset_root.glob("*/manifest.json"))
    for manifest_path in manifests:
        layer_id = manifest_path.parent.name
        if layer_ids and layer_id not in layer_ids:
            continue
        items = json.loads(manifest_path.read_text(encoding="utf-8"))
        print(f"\n==> 恢复: {layer_id} ({len(items)} 条)")
        for entry in items:
            url = entry.get("url")
            if not url:
                print(f"    跳过(无 URL): {entry.get('id')}")
                stats["skipped"] += 1
                continue
            dest = resolve_manifest_dest(entry, asset_root)
            if dest.is_file() and not force:
                stats["skipped"] += 1
                continue
            title = (entry.get("title") or entry.get("id") or "")[:40]
            try:
                print(f"    下载: {title}...")
                download_file(url, dest)
                entry["status"] = "downloaded"
                stats["downloaded"] += 1
                time.sleep(0.15)
            except (urllib.error.URLError, TimeoutError, OSError) as exc:
                print(f"    ✗ 失败: {title} — {exc}", file=sys.stderr)
                entry["status"] = "failed"
                entry["error"] = str(exc)
                stats["failed"] += 1
            if fix_paths:
                new_rel = str(dest.relative_to(REPO_ROOT))
                if entry.get("local_path") != new_rel:
                    entry["local_path"] = new_rel
                    stats["fixed_paths"] += 1
        if fix_paths:
            manifest_path.write_text(
                json.dumps(items, ensure_ascii=False, indent=2),
                encoding="utf-8",
            )
    return stats


def process_layer(
    layer_id: str,
    spec: dict,
    defaults: dict,
    output_root: Path,
    *,
    dry_run: bool,
    target_override: int | None,
    commercial_only: bool,
    page_size: int,
    global_seen: set[str],
) -> list[dict]:
    name = spec.get("name", layer_id)
    layer_type = spec.get("type", "effect")

    print(f"\n==> 层级: {name} ({layer_id}) [{layer_type}]")
    layer_manifest: list[dict] = []

    if layer_type == "music":
        target = target_override if target_override is not None else int(
            defaults.get("per_collection", 30)
        )
        groups = [
            (c.get("name", str(c.get("id"))), str(c.get("id")), "collection")
            for c in spec.get("collections", [])
        ]
        collector = collect_for_collection
    else:
        target = target_override if target_override is not None else int(
            defaults.get("per_keyword", 15)
        )
        groups = [(kw, kw, "keyword") for kw in spec.get("keywords", [])]
        collector = collect_for_keyword

    for group_label, group_key, group_kind in groups:
        print(f"  {group_kind}: {group_label} (目标 {target} 条)")
        items = collector(group_key, target, commercial_only, page_size, global_seen)
        print(f"    命中: {len(items)} 条")

        for item in items:
            local_path = local_path_for(output_root, layer_id, group_label, item)
            entry = {
                "layer_id": layer_id,
                "layer_name": name,
                "layer_type": layer_type,
                "group": group_label,
                "id": item["id"],
                "title": item["title"],
                "duration": item.get("duration"),
                "paid_type": item.get("paid_type"),
                "url": item["url"],
                "local_path": str(local_path.relative_to(REPO_ROOT)),
            }
            if layer_type == "music":
                entry["author"] = item.get("author")
                entry["is_commerce"] = item.get("is_commerce")

            if dry_run:
                entry["status"] = "dry_run"
                layer_manifest.append(entry)
                continue

            if local_path.is_file():
                print(f"    跳过(已存在): {local_path.name}")
                entry["status"] = "skipped"
            else:
                try:
                    print(f"    下载: {item['title'][:40]}...")
                    download_file(item["url"], local_path)
                    entry["status"] = "downloaded"
                    time.sleep(0.2)
                except (urllib.error.URLError, TimeoutError, OSError) as exc:
                    print(f"    ✗ 失败: {item['title'][:40]} — {exc}", file=sys.stderr)
                    entry["status"] = "failed"
                    entry["error"] = str(exc)

            layer_manifest.append(entry)

    layer_dir = output_root / layer_id
    layer_dir.mkdir(parents=True, exist_ok=True)
    manifest_path = layer_dir / "manifest.json"
    manifest_path.write_text(
        json.dumps(layer_manifest, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    print(f"  manifest: {manifest_path}")
    return layer_manifest


def download_keyword(
    keyword: str,
    layer_id: str,
    output_root: Path,
    defaults: dict,
    *,
    group_label: str | None,
    dry_run: bool,
    target: int,
    commercial_only: bool,
    page_size: int,
) -> list[dict]:
    """按单个关键词搜索并下载到 output_root/<layer_id>/<group>/。"""
    group = group_label or keyword
    layer_name = defaults.get("layer_names", {}).get(layer_id, layer_id)
    print(f"\n==> 关键词: {keyword} → {layer_id}/{group} (目标 {target} 条)")
    items = collect_for_keyword(keyword, target, commercial_only, page_size, set())
    print(f"    命中: {len(items)} 条")

    manifest_path = output_root / layer_id / "manifest.json"
    existing: list[dict] = []
    if manifest_path.is_file():
        existing = json.loads(manifest_path.read_text(encoding="utf-8"))
    seen_ids = {e.get("id") for e in existing}

    new_entries: list[dict] = []
    for item in items:
        if item["id"] in seen_ids:
            print(f"    跳过(manifest 已有): {item['title'][:40]}")
            continue
        local_path = local_path_for(output_root, layer_id, group, item)
        entry = {
            "layer_id": layer_id,
            "layer_name": layer_name,
            "layer_type": "effect",
            "group": group,
            "id": item["id"],
            "title": item["title"],
            "duration": item.get("duration"),
            "paid_type": item.get("paid_type"),
            "url": item["url"],
            "local_path": str(local_path.relative_to(REPO_ROOT)),
        }
        if dry_run:
            entry["status"] = "dry_run"
            new_entries.append(entry)
            continue
        if local_path.is_file():
            print(f"    跳过(已存在): {local_path.name}")
            entry["status"] = "skipped"
        else:
            try:
                print(f"    下载: {item['title'][:40]}...")
                download_file(item["url"], local_path)
                entry["status"] = "downloaded"
                time.sleep(0.2)
            except (urllib.error.URLError, TimeoutError, OSError) as exc:
                print(f"    ✗ 失败: {item['title'][:40]} — {exc}", file=sys.stderr)
                entry["status"] = "failed"
                entry["error"] = str(exc)
        new_entries.append(entry)

    if not dry_run and new_entries:
        merged = existing + new_entries
        manifest_path.parent.mkdir(parents=True, exist_ok=True)
        manifest_path.write_text(
            json.dumps(merged, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        print(f"  manifest: {manifest_path} (+{len(new_entries)} 条)")
    return new_entries


def main() -> None:
    parser = argparse.ArgumentParser(description="剪映音效/音乐分层批量下载")
    parser.add_argument("--config", default=str(DEFAULT_CONFIG), help="配置文件路径")
    parser.add_argument("--layer", action="append", help="指定层级 ID（可多次）")
    parser.add_argument("--all", action="store_true", help="下载全部层级")
    parser.add_argument("--list", action="store_true", help="列出可用层级")
    parser.add_argument("--dry-run", action="store_true", help="只搜索，不下载")
    parser.add_argument("--target", type=int, help="每关键词/歌单下载条数（覆盖配置）")
    parser.add_argument("--keyword", help="单关键词搜索下载（需配合 --layer）")
    parser.add_argument("--group", help="关键词下载时的子目录名（默认与 keyword 相同）")
    parser.add_argument("--all-licenses", action="store_true", help="不限商用，下载全部")
    parser.add_argument(
        "--restore",
        action="store_true",
        help="按已有 manifest 重新下载缺失文件（不调用搜索 API）",
    )
    parser.add_argument(
        "--force",
        action="store_true",
        help="与 --restore 合用：覆盖已存在的文件",
    )
    args = parser.parse_args()

    config_path = Path(args.config)
    if not config_path.is_absolute():
        config_path = (Path.cwd() / config_path).resolve()
    if not config_path.is_file():
        config_path = SCRIPT_DIR / Path(args.config).name
    if not config_path.is_file():
        print(f"Error: 找不到配置 {args.config}", file=sys.stderr)
        sys.exit(1)

    cfg = load_config(config_path)
    all_layers = cfg["layers"]
    defaults = cfg["defaults"]
    page_size = int(defaults.get("page_size", 50))
    output_root = resolve_output_root(defaults)
    commercial_only = not args.all_licenses and bool(defaults.get("commercial_only", False))

    if args.restore:
        print("按 manifest 恢复下载")
        print(f"配置: {config_path}")
        print(f"输出: {output_root}")
        stats = restore_from_manifest(
            output_root,
            layer_ids=args.layer if args.layer else None,
            force=args.force,
        )
        print(
            f"\n完成。下载 {stats['downloaded']}，跳过 {stats['skipped']}，"
            f"失败 {stats['failed']}，修正路径 {stats['fixed_paths']}"
        )
        return

    if args.keyword:
        layer_id = (args.layer and args.layer[0]) or "6_life"
        target = args.target if args.target is not None else 20
        print("剪映音效 · 单关键词下载")
        print(f"关键词: {args.keyword}")
        print(f"输出: {output_root}/{layer_id}/{args.group or args.keyword}")
        print(f"商用过滤: {'是' if commercial_only else '否'}")
        entries = download_keyword(
            args.keyword,
            layer_id,
            output_root,
            defaults,
            group_label=args.group,
            dry_run=args.dry_run,
            target=target,
            commercial_only=commercial_only,
            page_size=page_size,
        )
        print(f"\n完成。处理 {len(entries)} 条。")
        return

    if args.list:
        for lid, spec in all_layers.items():
            if spec.get("type") == "music":
                detail = ", ".join(c.get("name", "") for c in spec.get("collections", []))
            else:
                detail = ", ".join(spec.get("keywords", []))
            print(f"  {lid}: {spec.get('name', lid)} [{spec.get('type', 'effect')}] — {detail}")
        return

    if args.all or not args.layer:
        targets = list(all_layers.keys())
    else:
        targets = args.layer
        unknown = [t for t in targets if t not in all_layers]
        if unknown:
            print(f"Error: 未知层级: {', '.join(unknown)}", file=sys.stderr)
            print("可用:", ", ".join(all_layers.keys()), file=sys.stderr)
            sys.exit(1)

    print("剪映音效/音乐分层下载")
    print(f"配置: {config_path}")
    print(f"输出: {output_root}")
    print(f"商用过滤: {'是（仅可商用）' if commercial_only else '否'}")
    if args.dry_run:
        print("模式: dry-run（仅搜索）")

    global_seen: set[str] = set()
    total = 0
    for lid in targets:
        manifest = process_layer(
            lid,
            all_layers[lid],
            defaults,
            output_root,
            dry_run=args.dry_run,
            target_override=args.target,
            commercial_only=commercial_only,
            page_size=page_size,
            global_seen=global_seen,
        )
        total += len(manifest)

    print(f"\n完成。共处理 {total} 条记录。")


if __name__ == "__main__":
    main()
