#!/usr/bin/env python3
"""从剪映（ulikecam）音效 API 按分层关键词批量下载雨声音效库。"""

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
LAYERS_PATH = SCRIPT_DIR / "layers.json"
OUTPUT_ROOT = SCRIPT_DIR / "output"

SEARCH_URL = (
    "https://lv-api-sinfonlinec.ulikecam.com/artist/v1/effect/search"
    "?aid=3704&device_platform=mac&region=CN&app_name=JianyingPro&language=zh-Hans"
)

REQUEST_HEADERS = {
    "Host": "lv-api-sinfonlinec.ulikecam.com",
    "content-type": "application/json",
    "user-agent": "Cronet/TTNetVersion:906739f5 2024-12-18",
}


def load_config() -> dict:
    data = json.loads(LAYERS_PATH.read_text(encoding="utf-8"))
    return {
        "defaults": data.get("defaults", {}),
        "layers": data.get("layers", {}),
    }


def safe_filename(text: str, max_len: int = 60) -> str:
    cleaned = re.sub(r'[<>:"/\\|?*\x00-\x1f]', "_", text.strip())
    cleaned = re.sub(r"\s+", "_", cleaned)
    cleaned = cleaned.strip("._") or "untitled"
    return cleaned[:max_len]


def parse_paid_type(business_info: dict | None) -> str:
    if not business_info:
        return "unknown"
    raw = business_info.get("json_str", "")
    if not raw:
        return "unknown"
    try:
        info = json.loads(raw)
        return info.get("paid_type", "unknown")
    except json.JSONDecodeError:
        return "unknown"


def search_effects(
    query: str,
    offset: int,
    count: int,
) -> dict:
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
            "fav_scene": None,
            "image_pack_param": None,
            "large_image_formats": [],
            "need_collection_id": False,
            "need_contract": True,
            "need_favorite_info": False,
            "need_operation_tag": False,
            "need_parent_tag": False,
            "need_tag": False,
            "need_thumb": False,
            "only_commercial": False,
            "tag_one_level": None,
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
    payload = json.dumps(body).encode("utf-8")
    req = urllib.request.Request(
        SEARCH_URL,
        data=payload,
        headers=REQUEST_HEADERS,
        method="POST",
    )
    with urllib.request.urlopen(req, timeout=30) as resp:
        data = json.loads(resp.read().decode("utf-8"))

    if data.get("ret") != "0":
        raise RuntimeError(f"API error: {data.get('errmsg', data)}")

    return data.get("data", {})


def parse_effect_item(item: dict) -> dict | None:
    common = item.get("common_attr") or {}
    audio = item.get("audio_effect") or {}
    effect_id = common.get("effect_id") or common.get("id")
    title = common.get("title") or ""
    download_info = common.get("download_info") or {}
    url = download_info.get("url") or (common.get("item_urls") or [None])[0]

    if not effect_id or not url:
        return None

    return {
        "id": str(effect_id),
        "title": title,
        "url": url,
        "md5": common.get("md5", ""),
        "duration": audio.get("duration"),
        "duration_ms": audio.get("duration_ms"),
        "paid_type": parse_paid_type(common.get("business_info")),
    }


def collect_for_keyword(
    query: str,
    per_keyword: int,
    include_paid: bool,
    page_size: int,
    global_seen: set[str],
) -> list[dict]:
    results: list[dict] = []
    offset = 0

    while len(results) < per_keyword:
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

            if not include_paid and parsed["paid_type"] not in ("free", "unknown"):
                continue

            global_seen.add(dedupe_key)
            parsed["keyword"] = query
            results.append(parsed)
            if len(results) >= per_keyword:
                break

        if not data.get("has_more"):
            break
        offset = data.get("next_offset", offset + len(items))
        time.sleep(0.3)

    return results


def download_file(url: str, dest: Path) -> None:
    dest.parent.mkdir(parents=True, exist_ok=True)
    req = urllib.request.Request(url, headers={"User-Agent": REQUEST_HEADERS["user-agent"]})
    with urllib.request.urlopen(req, timeout=120) as resp:
        dest.write_bytes(resp.read())


def local_path_for(layer_id: str, keyword: str, effect: dict) -> Path:
    kw_dir = safe_filename(keyword.replace(" ", "_"))
    fname = f"{effect['id']}_{safe_filename(effect['title'])}.mp3"
    return OUTPUT_ROOT / layer_id / kw_dir / fname


def process_layer(
    layer_id: str,
    spec: dict,
    defaults: dict,
    *,
    dry_run: bool,
    per_keyword: int | None,
    include_paid: bool | None,
    page_size: int,
    global_seen: set[str],
) -> list[dict]:
    name = spec.get("name", layer_id)
    keywords = spec.get("keywords", [])
    pk = per_keyword if per_keyword is not None else int(defaults.get("per_keyword", 15))
    paid = include_paid if include_paid is not None else bool(defaults.get("include_paid", True))

    print(f"\n==> 层级: {name} ({layer_id})")
    layer_manifest: list[dict] = []

    for keyword in keywords:
        print(f"  搜索: {keyword} (目标 {pk} 条)")
        effects = collect_for_keyword(keyword, pk, paid, page_size, global_seen)
        print(f"    命中: {len(effects)} 条")

        for effect in effects:
            local_path = local_path_for(layer_id, keyword, effect)
            entry = {
                "layer_id": layer_id,
                "layer_name": name,
                "keyword": keyword,
                "id": effect["id"],
                "title": effect["title"],
                "duration": effect["duration"],
                "duration_ms": effect["duration_ms"],
                "paid_type": effect["paid_type"],
                "url": effect["url"],
                "local_path": str(local_path.relative_to(SCRIPT_DIR)),
            }

            if dry_run:
                entry["status"] = "dry_run"
                layer_manifest.append(entry)
                continue

            if local_path.is_file():
                print(f"    跳过(已存在): {local_path.name}")
                entry["status"] = "skipped"
            else:
                try:
                    print(f"    下载: {effect['title'][:40]}...")
                    download_file(effect["url"], local_path)
                    entry["status"] = "downloaded"
                    time.sleep(0.2)
                except (urllib.error.URLError, TimeoutError, OSError) as exc:
                    print(f"    ✗ 失败: {effect['title'][:40]} — {exc}", file=sys.stderr)
                    entry["status"] = "failed"
                    entry["error"] = str(exc)

            layer_manifest.append(entry)

    layer_dir = OUTPUT_ROOT / layer_id
    layer_dir.mkdir(parents=True, exist_ok=True)
    manifest_path = layer_dir / "manifest.json"
    manifest_path.write_text(
        json.dumps(layer_manifest, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    print(f"  manifest: {manifest_path}")

    return layer_manifest


def main() -> None:
    parser = argparse.ArgumentParser(description="剪映音效分层批量下载（雨声库）")
    parser.add_argument("--layer", action="append", help="指定层级 ID（可多次）")
    parser.add_argument("--all", action="store_true", help="下载全部层级")
    parser.add_argument("--list", action="store_true", help="列出可用层级")
    parser.add_argument("--dry-run", action="store_true", help="只搜索，不下载")
    parser.add_argument("--per-keyword", type=int, help="每个关键词下载条数")
    parser.add_argument(
        "--include-paid",
        action="store_true",
        default=None,
        help="包含付费素材",
    )
    parser.add_argument(
        "--free-only",
        action="store_true",
        help="仅下载免费素材",
    )
    args = parser.parse_args()

    if not LAYERS_PATH.is_file():
        print(f"Error: 找不到配置 {LAYERS_PATH}", file=sys.stderr)
        sys.exit(1)

    cfg = load_config()
    all_layers = cfg["layers"]
    defaults = cfg["defaults"]
    page_size = int(defaults.get("page_size", 50))

    if args.list:
        for lid, spec in all_layers.items():
            kw = ", ".join(spec.get("keywords", []))
            print(f"  {lid}: {spec.get('name', lid)} — {kw}")
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

    include_paid: bool | None = None
    if args.free_only:
        include_paid = False
    elif args.include_paid:
        include_paid = True

    print("剪映音效分层下载")
    print(f"配置: {LAYERS_PATH}")
    if args.dry_run:
        print("模式: dry-run（仅搜索）")

    global_seen: set[str] = set()
    total = 0

    for lid in targets:
        manifest = process_layer(
            lid,
            all_layers[lid],
            defaults,
            dry_run=args.dry_run,
            per_keyword=args.per_keyword,
            include_paid=include_paid,
            page_size=page_size,
            global_seen=global_seen,
        )
        total += len(manifest)

    print(f"\n完成。共处理 {total} 条记录。")


if __name__ == "__main__":
    main()
