#!/usr/bin/env python3
"""从 Epidemic Sound 按分层英文关键词搜索音效，下载 Top N 预览 MP3。

API 参考 reference.yaml：
  GET https://www.epidemicsound.com/json/search/sfx/?term=...&page=1
响应 entities.tracks + meta.hits；预览 URL 在 stems.full.lqMp3Url
"""

from __future__ import annotations

import argparse
import json
import os
import re
import subprocess
import sys
import time
import urllib.parse
from pathlib import Path

_SCRIPTS_ROOT = Path(__file__).resolve().parents[1]
if str(_SCRIPTS_ROOT) not in sys.path:
    sys.path.insert(0, str(_SCRIPTS_ROOT))

from cloak_browser import CloakBrowserSession, is_cloudflare_challenge

SCRIPT_DIR = Path(__file__).resolve().parent
REPO_ROOT = SCRIPT_DIR.parent.parent
DEFAULT_CONFIG = SCRIPT_DIR / "rain_layers.json"
DEFAULT_CREDENTIALS = SCRIPT_DIR / "reference.yaml"

SITE_ORIGIN = "https://www.epidemicsound.com"
SEARCH_API = f"{SITE_ORIGIN}/json/search/sfx/"
AUDIO_CDN_HOST = "audiocdn.epidemicsound.com"

DEFAULT_SEGMENT_TYPES = [
    "music-structure@v2",
    "predicted-popular-15sec",
    "soundly-sfx",
]


def load_config(config_path: Path) -> dict:
    data = json.loads(config_path.read_text(encoding="utf-8"))
    return {"defaults": data.get("defaults", {}), "layers": data.get("layers", {})}


def resolve_output_root(defaults: dict) -> Path:
    raw = defaults.get("output_dir", "assets/sound_effect/rain_sound")
    p = Path(raw)
    if p.is_absolute():
        return p
    if raw.startswith("assets/"):
        return REPO_ROOT / raw
    return SCRIPT_DIR / raw


def safe_filename(text: str, max_len: int = 60) -> str:
    cleaned = re.sub(r'[<>:"/\\|?*\x00-\x1f]', "_", text.strip())
    cleaned = re.sub(r"\s+", "_", cleaned)
    cleaned = cleaned.strip("._") or "untitled"
    return cleaned[:max_len]


def load_credentials(path: Path) -> dict:
    cookie = os.environ.get("EPIDEMIC_COOKIE", "").strip()
    user_agent = os.environ.get(
        "EPIDEMIC_USER_AGENT",
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/149.0.0.0 Safari/537.36",
    )
    workspace_id = os.environ.get("EPIDEMIC_WORKSPACE_ID", "").strip()
    csrf_token = os.environ.get("EPIDEMIC_CSRF_TOKEN", "").strip()
    app_version = os.environ.get("EPIDEMIC_APP_VERSION", "").strip()
    referer = f"{SITE_ORIGIN}/sound-effects/"

    if path.is_file():
        text = path.read_text(encoding="utf-8")
        if not cookie:
            m = re.search(r'-H "Cookie: (.+?)" -H "epidemic-workspace-id', text)
            if m:
                cookie = m.group(1)
        m = re.search(r'-H "user-agent: ([^"]+)"', text, re.I)
        if m:
            user_agent = m.group(1)
        m = re.search(r'-H "referer: ([^"]+)"', text, re.I)
        if m:
            referer = m.group(1)
        if not workspace_id:
            m = re.search(r'-H "epidemic-workspace-id: ([^"]+)"', text)
            if m:
                workspace_id = m.group(1)
        if not csrf_token:
            m = re.search(r'-H "x-csrftoken: ([^"]+)"', text)
            if m:
                csrf_token = m.group(1)
        if not app_version:
            m = re.search(r'-H "app-version: ([^"]+)"', text)
            if m:
                app_version = m.group(1)

    if not csrf_token and cookie:
        m = re.search(r"csrftoken=([^;]+)", cookie)
        if m:
            csrf_token = m.group(1)

    if not cookie:
        raise RuntimeError(
            "未找到 Epidemic Cookie。请更新 reference.yaml 中的 curl 示例，"
            "或设置环境变量 EPIDEMIC_COOKIE。"
        )
    if not workspace_id:
        raise RuntimeError(
            "未找到 epidemic-workspace-id。请更新 reference.yaml 或设置 EPIDEMIC_WORKSPACE_ID。"
        )
    if not csrf_token:
        raise RuntimeError(
            "未找到 x-csrftoken。请更新 reference.yaml 或设置 EPIDEMIC_CSRF_TOKEN。"
        )
    if not app_version:
        app_version = "v2026.06.25-rel4"

    return {
        "cookie": cookie,
        "user_agent": user_agent,
        "referer": referer,
        "workspace_id": workspace_id,
        "csrf_token": csrf_token,
        "app_version": app_version,
    }


def epidemic_browser_session(
    creds: dict,
    *,
    profile_dir: Path | None = None,
    headless: bool = True,
) -> CloakBrowserSession:
    return CloakBrowserSession(
        profile_name="epidemic",
        profile_dir=profile_dir,
        headless=headless,
        cookies=creds.get("cookie"),
        cookie_domain=".epidemicsound.com",
        warm_up_url=f"{SITE_ORIGIN}/sound-effects/",
        warm_up_wait_for="epidemic",
    )


def epidemic_json_ok(text: str) -> bool:
    t = text.strip()
    return t.startswith("{") and '"entities"' in t and '"hits"' in t


class CloudflareChallenge(RuntimeError):
    pass


def search_referer(keyword: str, search_path: str) -> str:
    term = urllib.parse.quote(keyword.strip())
    return f"{SITE_ORIGIN}{search_path.rstrip('/')}/?term={term}"


def build_search_url(keyword: str, page: int) -> str:
    params: list[tuple[str, str]] = [
        ("order", "desc"),
        ("page", str(page)),
        ("sort", "relevance"),
        ("term", keyword.strip()),
    ]
    for seg in DEFAULT_SEGMENT_TYPES:
        params.append(("segment_types", seg))
    return f"{SEARCH_API}?{urllib.parse.urlencode(params)}"


def api_headers(creds: dict, keyword: str, search_path: str) -> list[str]:
    return [
        f"Cookie: {creds['cookie']}",
        f"User-Agent: {creds['user_agent']}",
        "Accept: application/json",
        "Content-Type: application/json",
        f"epidemic-workspace-id: {creds['workspace_id']}",
        f"x-csrftoken: {creds['csrf_token']}",
        f"app-version: {creds['app_version']}",
        "x-requested-with: XMLHttpRequest",
        f"Referer: {search_referer(keyword, search_path)}",
        "Accept-Language: en-US,en;q=0.9",
    ]


def curl_fetch(url: str, creds: dict, keyword: str, search_path: str, timeout: int = 60) -> str:
    cmd = ["curl", "-sL", "--max-time", str(timeout), url]
    for header in api_headers(creds, keyword, search_path):
        cmd.extend(["-H", header])
    proc = subprocess.run(cmd, capture_output=True, text=True)
    if proc.returncode != 0:
        raise RuntimeError(f"curl failed ({proc.returncode}): {proc.stderr.strip() or url}")
    return proc.stdout


def fetch_search_json(
    keyword: str,
    creds: dict,
    search_path: str,
    *,
    page: int = 1,
    browser: CloakBrowserSession | None = None,
) -> dict:
    url = build_search_url(keyword, page)
    if browser is not None:
        body = browser.fetch(
            url,
            wait_for="entities",
            success_check=epidemic_json_ok,
        )
    else:
        body = curl_fetch(url, creds, keyword, search_path)
    if is_cloudflare_challenge(body):
        raise CloudflareChallenge("Cloudflare 验证页（search API）")
    try:
        return json.loads(body)
    except json.JSONDecodeError as exc:
        raise RuntimeError(f"API 响应非 JSON: {body[:200]}") from exc


def parse_search_response(data: dict) -> list[dict]:
    hits = data.get("meta", {}).get("hits", [])
    tracks = data.get("entities", {}).get("tracks", {})
    items: list[dict] = []
    seen: set[str] = set()

    for hit in hits:
        tid = str(hit.get("trackId", ""))
        if not tid or tid in seen:
            continue
        track = tracks.get(tid) or tracks.get(int(tid)) if tid.isdigit() else None
        if not track:
            continue
        stem = track.get("stems", {}).get("full", {})
        url = stem.get("lqMp3Url")
        if not url:
            continue
        seen.add(tid)
        slug = track.get("publicSlug") or ""
        items.append(
            {
                "id": tid,
                "title": track.get("title") or tid,
                "url": url,
                "public_slug": slug,
                "item_url": f"{SITE_ORIGIN}/track/{slug}" if slug else "",
                "duration_ms": track.get("durationMs"),
                "ext": "mp3",
            }
        )
    return items


def search_items(
    keyword: str,
    creds: dict,
    defaults: dict,
    *,
    limit: int,
    browser: CloakBrowserSession | None = None,
    browser_fallback: bool = True,
) -> list[dict]:
    search_path = defaults.get("search_path", "/sound-effects/search/")
    try:
        data = fetch_search_json(
            keyword, creds, search_path, browser=browser,
        )
    except CloudflareChallenge:
        if browser_fallback and browser is None:
            fb = epidemic_browser_session(creds)
            try:
                data = fetch_search_json(
                    keyword, creds, search_path, browser=fb,
                )
            finally:
                fb.close()
        else:
            raise

    items = parse_search_response(data)
    if not items:
        raise RuntimeError("搜索结果为空或无可用 lqMp3Url")
    if len(items) > limit:
        items = items[:limit]
    via = "browser-api" if browser else "api"
    for item in items:
        item["fetch_via"] = via
    return items


def download_file(url: str, dest: Path, creds: dict) -> None:
    dest.parent.mkdir(parents=True, exist_ok=True)
    cmd = [
        "curl",
        "-sL",
        "--fail",
        "--max-time",
        "180",
        url,
        "-o",
        str(dest),
        "-H",
        f"User-Agent: {creds['user_agent']}",
        "-H",
        "Accept: */*",
    ]
    proc = subprocess.run(cmd, capture_output=True, text=True)
    if proc.returncode != 0:
        raise RuntimeError(proc.stderr.strip() or f"download failed: {url}")


def local_path_for(output_root: Path, layer_id: str, group: str, item: dict) -> Path:
    group_dir = safe_filename(group)
    fname = f"{item['id']}_{safe_filename(item['title'])}.{item['ext']}"
    return output_root / layer_id / group_dir / fname


def load_manifest(path: Path) -> list[dict]:
    if not path.is_file():
        return []
    return json.loads(path.read_text(encoding="utf-8"))


def merge_manifest(existing: list[dict], new_entries: list[dict]) -> list[dict]:
    index = {
        (entry.get("source", "capcut"), str(entry.get("id"))): i
        for i, entry in enumerate(existing)
    }
    for entry in new_entries:
        key = (entry.get("source", "epidemic_sound"), str(entry.get("id")))
        if key in index:
            existing[index[key]].update(entry)
        else:
            existing.append(entry)
    return existing


def process_layer(
    layer_id: str,
    spec: dict,
    defaults: dict,
    output_root: Path,
    creds: dict,
    *,
    dry_run: bool,
    target_override: int | None,
    global_seen: set[str],
    browser: CloakBrowserSession | None = None,
    browser_fallback: bool = True,
) -> list[dict]:
    name = spec.get("name", layer_id)
    target = target_override if target_override is not None else int(
        defaults.get("per_keyword", 15)
    )
    layer_entries: list[dict] = []

    print(f"\n==> 层级: {name} ({layer_id})")
    for keyword in spec.get("keywords", []):
        print(f"  keyword: {keyword} (Top {target})")
        try:
            items = search_items(
                keyword,
                creds,
                defaults,
                limit=target,
                browser=browser,
                browser_fallback=browser_fallback,
            )
        except (RuntimeError, CloudflareChallenge) as exc:
            print(f"    ✗ 搜索失败: {exc}", file=sys.stderr)
            continue

        via = items[0].get("fetch_via", "?") if items else "?"
        print(f"    命中: {len(items)} 条 (via {via})")
        for item in items:
            key = f"epidemic:{item['id']}"
            if key in global_seen:
                continue
            global_seen.add(key)

            local_path = local_path_for(output_root, layer_id, keyword, item)
            entry = {
                "layer_id": layer_id,
                "layer_name": name,
                "layer_type": "epidemic",
                "source": "epidemic_sound",
                "group": keyword,
                "id": item["id"],
                "title": item["title"],
                "url": item["url"],
                "public_slug": item.get("public_slug"),
                "item_url": item.get("item_url"),
                "duration_ms": item.get("duration_ms"),
                "fetch_via": item.get("fetch_via"),
                "local_path": str(local_path.relative_to(REPO_ROOT)),
            }

            if dry_run:
                entry["status"] = "dry_run"
                layer_entries.append(entry)
                continue

            if local_path.is_file():
                print(f"    跳过(已存在): {local_path.name}")
                entry["status"] = "skipped"
            else:
                try:
                    print(f"    下载: {item['title'][:50]}...")
                    download_file(item["url"], local_path, creds)
                    entry["status"] = "downloaded"
                    time.sleep(0.15)
                except RuntimeError as exc:
                    print(f"    ✗ 失败: {item['title'][:50]} — {exc}", file=sys.stderr)
                    entry["status"] = "failed"
                    entry["error"] = str(exc)

            layer_entries.append(entry)

    layer_dir = output_root / layer_id
    layer_dir.mkdir(parents=True, exist_ok=True)
    manifest_path = layer_dir / "manifest.json"
    merged = merge_manifest(load_manifest(manifest_path), layer_entries)
    if not dry_run:
        manifest_path.write_text(
            json.dumps(merged, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        print(f"  manifest: {manifest_path} ({len(merged)} 条)")
    else:
        print(f"  dry-run: 本层新增 {len(layer_entries)} 条（未写入 manifest）")
    return layer_entries


def main() -> None:
    parser = argparse.ArgumentParser(description="Epidemic Sound 雨声分层音效下载")
    parser.add_argument("--config", default=str(DEFAULT_CONFIG), help="分层配置 JSON")
    parser.add_argument(
        "--credentials",
        default=str(DEFAULT_CREDENTIALS),
        help="凭据文件（reference.yaml）",
    )
    parser.add_argument("--layer", action="append", help="指定层级 ID（可多次）")
    parser.add_argument("--all", action="store_true", help="下载全部层级")
    parser.add_argument("--list", action="store_true", help="列出可用层级")
    parser.add_argument("--dry-run", action="store_true", help="只搜索，不下载")
    parser.add_argument("--target", type=int, help="每关键词条数（默认 15）")
    parser.add_argument(
        "--browser",
        action="store_true",
        help="始终用 CloakBrowser 请求 API（绕过 Cloudflare）",
    )
    parser.add_argument(
        "--no-browser-fallback",
        action="store_true",
        help="curl 遇 Cloudflare 时不自动切换浏览器",
    )
    parser.add_argument(
        "--headed",
        action="store_true",
        help="浏览器有界面模式",
    )
    parser.add_argument(
        "--browser-profile",
        metavar="DIR",
        help="CloakBrowser profile 目录",
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
    layers = cfg["layers"]
    defaults = cfg["defaults"]
    output_root = resolve_output_root(defaults)

    if args.list:
        for layer_id, spec in layers.items():
            kws = ", ".join(spec.get("keywords", []))
            print(f"  {layer_id}: {spec.get('name', layer_id)} — {kws}")
        return

    if not args.layer and not args.all:
        parser.print_help()
        sys.exit(1)

    cred_path = Path(args.credentials)
    if not cred_path.is_absolute():
        cred_path = (Path.cwd() / cred_path).resolve()
    if not cred_path.is_file():
        cred_path = SCRIPT_DIR / Path(args.credentials).name

    try:
        creds = load_credentials(cred_path)
    except RuntimeError as exc:
        print(f"Error: {exc}", file=sys.stderr)
        sys.exit(1)

    selected = list(layers.keys()) if args.all else (args.layer or [])
    unknown = [x for x in selected if x not in layers]
    if unknown:
        print(f"Error: 未知层级 {unknown}", file=sys.stderr)
        sys.exit(1)

    global_seen: set[str] = set()
    total = 0
    browser: CloakBrowserSession | None = None
    browser_fallback = not args.no_browser_fallback

    if args.browser:
        profile = None
        if args.browser_profile:
            profile = Path(args.browser_profile)
            if not profile.is_absolute():
                profile = SCRIPT_DIR / profile
        browser = epidemic_browser_session(
            creds,
            profile_dir=profile,
            headless=not args.headed,
        )
        print(
            "==> 使用 CloakBrowser（profile: {})".format(
                profile or "scripts/cloak_browser/.profiles/epidemic"
            )
        )

    try:
        for layer_id in selected:
            entries = process_layer(
                layer_id,
                layers[layer_id],
                defaults,
                output_root,
                creds,
                dry_run=args.dry_run,
                target_override=args.target,
                global_seen=global_seen,
                browser=browser,
                browser_fallback=browser_fallback,
            )
            total += len(entries)
    finally:
        if browser is not None:
            browser.close()

    print(f"\n完成。本 run 处理 {total} 条。")


if __name__ == "__main__":
    main()
