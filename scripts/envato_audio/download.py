#!/usr/bin/env python3
"""从 Envato Elements 按分层英文关键词搜索音效，下载 Top N 预览音频。

参考 envato_API.yaml 两种取数方式：
1. 直接 GET 搜索结果页 HTML
2. GET data-api/page/items-neue-page（响应内嵌同款 HTML）

从 HTML 的 <source src="...preview.m4a|mp3"> 解析当前页全部预览音频。
"""

from __future__ import annotations

import argparse
import html as html_module
import json
import os
import re
import subprocess
import sys
import time
import urllib.error
import urllib.parse
from pathlib import Path

_SCRIPTS_ROOT = Path(__file__).resolve().parents[1]
if str(_SCRIPTS_ROOT) not in sys.path:
    sys.path.insert(0, str(_SCRIPTS_ROOT))

from cloak_browser import CloakBrowserSession, is_cloudflare_challenge

SCRIPT_DIR = Path(__file__).resolve().parent
REPO_ROOT = SCRIPT_DIR.parent.parent
DEFAULT_CONFIG = SCRIPT_DIR / "rain_layers.json"
DEFAULT_CREDENTIALS = SCRIPT_DIR / "envato_API.yaml"

PREVIEW_HOST = "public-assets.content-platform.envatousercontent.com"
PAGE_BASE = "https://elements.envato.com"
API_BASE = "https://elements.envato.com/data-api/page/items-neue-page"

M4A_RE = re.compile(
    rf'src="(https://{re.escape(PREVIEW_HOST)}/[^"]+/preview\.m4a)"',
    re.I,
)
MP3_RE = re.compile(
    rf'src="(https://{re.escape(PREVIEW_HOST)}/[^"]+/preview\.mp3)"',
    re.I,
)
TITLE_LINK_RE = re.compile(
    r'title="([^"]*)"[^>]*data-testid="title-link"[^>]*href="/([^"]+)"'
    r'|data-testid="title-link"[^>]*href="/([^"]+)"[^>]*title="([^"]*)"',
    re.I,
)
AUTHOR_RE = re.compile(r'data-testid="author-link"[^>]*href="/user/([^"]+)"', re.I)
SPAN_TITLE_RE = re.compile(
    r'data-testid="title-link"[^>]*href="/[^"]+"[^>]*>.*?<span[^>]*>([^<]+)</span>',
    re.S | re.I,
)
BUILD_VERSION_RE = re.compile(r'build-version" content="([^"]+)"', re.I)


def load_config(config_path: Path) -> dict:
    data = json.loads(config_path.read_text(encoding="utf-8"))
    return {"defaults": data.get("defaults", {}), "layers": data.get("layers", {})}


def resolve_output_root(defaults: dict) -> Path:
    raw = defaults.get("output_dir", "assets/rain_sound")
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
    cookie = os.environ.get("ENVATO_COOKIE", "").strip()
    user_agent = os.environ.get(
        "ENVATO_USER_AGENT",
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/149.0.0.0 Safari/537.36",
    )
    referer = f"{PAGE_BASE}/"
    client_version = os.environ.get("ENVATO_CLIENT_VERSION", "").strip()
    enrollments = os.environ.get("ENVATO_ENROLLMENTS", "").strip()

    if path.is_file():
        text = path.read_text(encoding="utf-8")
        if not cookie:
            # Cookie 内含 g_state={\"...\"}，不能用 [^"]+ 截断
            m = re.search(r'-H "Cookie: (.+?)" -H "sec-ch', text)
            if m:
                cookie = m.group(1)
        m = re.search(r'-H "user-agent: ([^"]+)"', text, re.I)
        if m:
            user_agent = m.group(1)
        m = re.search(r'-H "referer: ([^"]+)"', text, re.I)
        if m:
            referer = m.group(1)
        if not client_version:
            m = re.search(r"clientVersion=([^&\"]+)", text)
            if m:
                client_version = m.group(1)
        if not enrollments:
            m = re.search(r"enrollments=([^&\"]+)", text)
            if m:
                enrollments = urllib.parse.unquote(m.group(1))

    if not cookie:
        raise RuntimeError(
            "未找到 Envato Cookie。请在 envato_API.yaml 中更新 curl 示例，"
            "或设置环境变量 ENVATO_COOKIE。"
        )
    if not client_version:
        client_version = "fb36693f1b2e247962fc998b2393e78211e3a56f"

    return {
        "cookie": cookie,
        "user_agent": user_agent,
        "referer": referer,
        "client_version": client_version,
        "enrollments": enrollments,
    }


def keyword_to_path(prefix: str, keyword: str) -> str:
    slug = keyword.strip().replace(" ", "+")
    return f"{prefix.rstrip('/')}/{slug}"


def page_url(path: str) -> str:
    return f"{PAGE_BASE}{path}"


def api_url(path: str, creds: dict) -> str:
    params = {
        "path": path,
        "languageCode": "en",
        "clientVersion": creds["client_version"],
    }
    if creds.get("enrollments"):
        params["enrollments"] = creds["enrollments"]
    return f"{API_BASE}?{urllib.parse.urlencode(params)}"


ENVATO_ORIGIN = "https://elements.envato.com"
ENVATO_PREVIEW_MARKERS = ("preview.m4a", "preview.mp3")


def envato_browser_session(
    creds: dict,
    *,
    profile_dir: Path | None = None,
    headless: bool = True,
) -> CloakBrowserSession:
    return CloakBrowserSession(
        profile_name="envato",
        profile_dir=profile_dir,
        headless=headless,
        cookies=creds.get("cookie"),
        cookie_domain=".elements.envato.com",
        warm_up_url=f"{ENVATO_ORIGIN}/",
        warm_up_wait_for="envato",
    )


def envato_preview_ok(text: str) -> bool:
    return any(m in text for m in ENVATO_PREVIEW_MARKERS)


class CloudflareChallenge(RuntimeError):
    """curl 命中 Cloudflare 验证页。"""


def curl_fetch(url: str, creds: dict, *, accept: str, timeout: int = 60) -> str:
    cmd = [
        "curl",
        "-sL",
        "--max-time",
        str(timeout),
        url,
        "-H",
        f"Cookie: {creds['cookie']}",
        "-H",
        f"User-Agent: {creds['user_agent']}",
        "-H",
        f"Accept: {accept}",
        "-H",
        "Accept-Language: en-US,en;q=0.9",
    ]
    if "elements.envato.com" in url:
        cmd.extend(["-H", f"Referer: {creds['referer']}"])
    proc = subprocess.run(cmd, capture_output=True, text=True)
    if proc.returncode != 0:
        raise RuntimeError(f"curl failed ({proc.returncode}): {proc.stderr.strip() or url}")
    return proc.stdout


def fetch_page_html(
    url: str,
    creds: dict,
    browser: CloakBrowserSession | None = None,
) -> str:
    if browser is not None:
        return browser.fetch(
            url,
            wait_for="preview.m4a",
            success_check=envato_preview_ok,
        )
    body = curl_fetch(
        url,
        creds,
        accept="text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    )
    if is_cloudflare_challenge(body):
        raise CloudflareChallenge("Cloudflare 验证页（HTML）")
    return body


def fetch_api_payload(
    url: str,
    creds: dict,
    browser: CloakBrowserSession | None = None,
) -> dict | str:
    if browser is not None:
        body = browser.fetch_json_or_html(url, html_marker="preview.m4a")
    else:
        body = curl_fetch(url, creds, accept="application/json")
    if is_cloudflare_challenge(body):
        raise CloudflareChallenge("Cloudflare 验证页（data-api）")
    try:
        return json.loads(body)
    except json.JSONDecodeError:
        return body


def extract_html_from_payload(payload: dict | str) -> str:
    if isinstance(payload, str):
        return payload

    def walk(obj) -> str | None:
        if isinstance(obj, str) and "preview.m4a" in obj and "<" in obj:
            return obj
        if isinstance(obj, dict):
            for key in ("html", "content", "body", "pageContent", "renderedPage", "markup"):
                val = obj.get(key)
                if isinstance(val, str) and "preview.m4a" in val:
                    return val
            for val in obj.values():
                found = walk(val)
                if found:
                    return found
        elif isinstance(obj, list):
            for val in obj:
                found = walk(val)
                if found:
                    return found
        return None

    return walk(payload) or ""


def parse_search_html(page_html: str) -> list[dict]:
    """从搜索结果页 HTML 解析当前页全部 preview.m4a / preview.mp3。"""
    parts = page_html.split('data-testid="audio-element"')
    if len(parts) <= 1:
        return []

    items: list[dict] = []
    seen: set[str] = set()

    for i in range(1, len(parts)):
        before = parts[i - 1]
        block = parts[i]

        m4a_m = M4A_RE.search(block)
        if not m4a_m:
            continue
        preview_m4a = m4a_m.group(1)
        mp3_m = MP3_RE.search(block)
        preview_mp3 = mp3_m.group(1) if mp3_m else None

        title, slug = "", ""
        title_matches = list(TITLE_LINK_RE.finditer(before))
        if title_matches:
            m = title_matches[-1]
            if m.group(1) is not None:
                title, slug = m.group(1), m.group(2)
            else:
                slug, title = m.group(3), m.group(4)

        span_matches = list(SPAN_TITLE_RE.finditer(before))
        if span_matches:
            title = span_matches[-1].group(1).strip() or title

        author_matches = list(AUTHOR_RE.finditer(before))
        author = author_matches[-1].group(1) if author_matches else None

        humane = slug.rsplit("-", 1)[-1] if slug else preview_m4a.split("/")[3]
        item_id = (
            humane
            if re.fullmatch(r"[A-Z0-9]{5,12}", humane or "")
            else preview_m4a.split("/")[3]
        )
        if item_id in seen:
            continue
        seen.add(item_id)

        items.append(
            {
                "id": item_id,
                "title": html_module.unescape(title or item_id),
                "url": preview_m4a,
                "preview_m4a": preview_m4a,
                "preview_mp3": preview_mp3,
                "item_url": f"{PAGE_BASE}/{slug}" if slug else "",
                "author": author,
                "ext": "m4a",
            }
        )
    return items


def pick_download_url(item: dict, prefer: str) -> tuple[str, str]:
    m4a = item.get("preview_m4a") or item.get("url")
    mp3 = item.get("preview_mp3")
    if prefer == "mp3" and mp3:
        return mp3, "mp3"
    if m4a:
        return m4a, "m4a"
    if mp3:
        return mp3, "mp3"
    raise RuntimeError("无可用预览 URL")


def fetch_search_html(
    keyword: str,
    creds: dict,
    defaults: dict,
    *,
    mode: str,
    browser: CloakBrowserSession | None = None,
    browser_fallback: bool = True,
) -> tuple[str, str]:
    prefix = defaults.get("search_path_prefix", "/sound-effects/nature-sounds")
    path = keyword_to_path(prefix, keyword)
    page = page_url(path)
    api = api_url(path, creds)
    modes = ["html", "api"] if mode == "auto" else [mode]
    errors: list[str] = []
    cf_hit = False

    for current in modes:
        try:
            if current == "html":
                html = fetch_page_html(page, creds, browser=browser)
                if is_cloudflare_challenge(html):
                    raise CloudflareChallenge("Cloudflare 验证页（HTML）")
                if "preview.m4a" in html or "preview.mp3" in html:
                    via = "browser-html" if browser else "html"
                    return html, via
                raise RuntimeError("HTML 中未找到 preview 音频")
            payload = fetch_api_payload(api, creds, browser=browser)
            html = extract_html_from_payload(payload)
            if not html:
                raise RuntimeError("data-api 响应中未找到 HTML 片段")
            if is_cloudflare_challenge(html):
                raise CloudflareChallenge("Cloudflare 验证页（data-api HTML）")
            via = "browser-api" if browser else "api"
            return html, via
        except CloudflareChallenge as exc:
            cf_hit = True
            errors.append(f"{current}: {exc}")
        except RuntimeError as exc:
            errors.append(f"{current}: {exc}")

    if cf_hit and browser_fallback and browser is None:
        fb = envato_browser_session(creds)
        try:
            return fetch_search_html(
                keyword,
                creds,
                defaults,
                mode=mode,
                browser=fb,
                browser_fallback=False,
            )
        finally:
            fb.close()

    raise RuntimeError("；".join(errors))


def search_items(
    keyword: str,
    creds: dict,
    defaults: dict,
    *,
    limit: int,
    mode: str,
    browser: CloakBrowserSession | None = None,
    browser_fallback: bool = True,
) -> list[dict]:
    html, via = fetch_search_html(
        keyword,
        creds,
        defaults,
        mode=mode,
        browser=browser,
        browser_fallback=browser_fallback,
    )
    items = parse_search_html(html)
    if not items:
        raise RuntimeError(f"解析失败（via={via}），页面中无 preview.m4a/mp3")

    if len(items) > limit:
        items = items[:limit]
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
        f"Referer: {creds['referer']}",
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
        key = (entry.get("source", "envato_elements"), str(entry.get("id")))
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
    fetch_mode: str,
    audio_format: str,
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
                mode=fetch_mode,
                browser=browser,
                browser_fallback=browser_fallback,
            )
        except RuntimeError as exc:
            print(f"    ✗ 搜索失败: {exc}", file=sys.stderr)
            continue

        via = items[0].get("fetch_via", "?") if items else "?"
        print(f"    命中: {len(items)} 条 (via {via})")
        for item in items:
            if item["id"] in global_seen:
                continue
            global_seen.add(item["id"])

            dl_url, ext = pick_download_url(item, audio_format)
            item = {**item, "url": dl_url, "ext": ext}
            local_path = local_path_for(output_root, layer_id, keyword, item)
            entry = {
                "layer_id": layer_id,
                "layer_name": name,
                "layer_type": "envato",
                "source": "envato_elements",
                "group": keyword,
                "id": item["id"],
                "title": item["title"],
                "author": item.get("author"),
                "url": dl_url,
                "preview_m4a": item.get("preview_m4a"),
                "preview_mp3": item.get("preview_mp3"),
                "item_url": item.get("item_url"),
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
                    print(f"    下载: {item['title'][:50]}... ({ext})")
                    download_file(dl_url, local_path, creds)
                    entry["status"] = "downloaded"
                    time.sleep(0.2)
                except (RuntimeError, urllib.error.URLError, OSError) as exc:
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


def cmd_parse_html(html_path: Path, limit: int, audio_format: str) -> None:
    html = html_path.read_text(encoding="utf-8")
    items = parse_search_html(html)
    print(f"解析 {html_path.name}: {len(items)} 条 preview")
    for item in items[:limit]:
        url, ext = pick_download_url(item, audio_format)
        print(
            f"  {item['id']:8} {item['title'][:30]:30} "
            f"{item.get('author') or '-':16} {ext} {url[-36:]}"
        )


def main() -> None:
    parser = argparse.ArgumentParser(description="Envato Elements 雨声分层音效下载")
    parser.add_argument("--config", default=str(DEFAULT_CONFIG), help="分层配置 JSON")
    parser.add_argument(
        "--credentials",
        default=str(DEFAULT_CREDENTIALS),
        help="凭据文件（envato_API.yaml）",
    )
    parser.add_argument("--layer", action="append", help="指定层级 ID（可多次）")
    parser.add_argument("--all", action="store_true", help="下载全部层级")
    parser.add_argument("--list", action="store_true", help="列出可用层级")
    parser.add_argument("--dry-run", action="store_true", help="只搜索，不下载")
    parser.add_argument("--target", type=int, help="每关键词条数（默认 15）")
    parser.add_argument(
        "--fetch-mode",
        choices=("auto", "html", "api"),
        default="auto",
        help="取数方式：HTML 直抓 / data-api / 自动 fallback（默认 auto）",
    )
    parser.add_argument(
        "--format",
        choices=("m4a", "mp3"),
        default="m4a",
        help="下载预览格式（默认 m4a）",
    )
    parser.add_argument(
        "--parse-html",
        metavar="FILE",
        help="离线解析本地搜索结果 HTML（如 rain.html），不下载",
    )
    parser.add_argument(
        "--browser",
        action="store_true",
        help="始终用 CloakBrowser 抓取（绕过 Cloudflare）",
    )
    parser.add_argument(
        "--no-browser-fallback",
        action="store_true",
        help="curl 遇 Cloudflare 时不自动切换浏览器",
    )
    parser.add_argument(
        "--headed",
        action="store_true",
        help="浏览器有界面模式（部分站点比 headless 更稳）",
    )
    parser.add_argument(
        "--browser-profile",
        metavar="DIR",
        help="CloakBrowser profile 目录（默认 scripts/cloak_browser/.profiles/envato）",
    )
    args = parser.parse_args()

    if args.parse_html:
        path = Path(args.parse_html)
        if not path.is_absolute():
            path = (Path.cwd() / path).resolve()
        if not path.is_file():
            path = SCRIPT_DIR / args.parse_html
        if not path.is_file():
            print(f"Error: 找不到 {args.parse_html}", file=sys.stderr)
            sys.exit(1)
        cmd_parse_html(path, args.target or 15, args.format)
        return

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
        prefix = defaults.get("search_path_prefix", "/sound-effects/nature-sounds")
        print(f"  search_path_prefix: {prefix}")
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
        browser = envato_browser_session(
            creds,
            profile_dir=profile,
            headless=not args.headed,
        )
        print(
            "==> 使用 CloakBrowser 抓取（profile: {})".format(
                profile or "scripts/cloak_browser/.profiles/envato"
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
                fetch_mode=args.fetch_mode,
                audio_format=args.format,
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
