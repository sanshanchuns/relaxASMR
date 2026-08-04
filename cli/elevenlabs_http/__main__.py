"""ElevenLabs 网页鉴权 CLI。

用法::

    PYTHONPATH=cli:. python -m elevenlabs_http status
    PYTHONPATH=cli:. python -m elevenlabs_http login          # 有头浏览器，一次登录
    PYTHONPATH=cli:. python -m elevenlabs_http connect --cdp http://127.0.0.1:9222
    PYTHONPATH=cli:. python -m elevenlabs_http refresh        # 用 refresh_token 换 Bearer
    PYTHONPATH=cli:. python -m elevenlabs_http watch          # 后台每 10 分钟续期
"""

from __future__ import annotations

import argparse
import sys
import time


def _cmd_status(_: argparse.Namespace) -> int:
    from .auth import auth_status_message, ensure_fresh_auth, load_web_auth
    from .web_client import ElevenLabsWebClient

    auth = load_web_auth()
    print(auth_status_message(auth))
    if auth.refresh_token:
        print(f"refresh_token: 已配置（{len(auth.refresh_token)} chars）")
    else:
        print("refresh_token: 未配置 → 请先 `python -m elevenlabs_http login`")
    client = ElevenLabsWebClient()
    ok, msg = client.available()
    print(f"models probe: {'OK' if ok else 'FAIL'} · {msg}")
    try:
        usage = client.fetch_usage()
        print(
            f"credits: used={usage.character_count} / limit={usage.character_limit} "
            f"(remain={usage.remaining})"
            + (f" · tier={usage.tier}" if usage.tier else "")
        )
    except Exception as exc:  # noqa: BLE001
        print(f"credits: FAIL · {exc}")
    if auth.ok and auth.refresh_token:
        # 顺手确保不太快过期
        fresh = ensure_fresh_auth(min_ttl_sec=120)
        print(f"ensure_fresh: source={fresh.source} email={fresh.email or '?'}")
    return 0 if ok else 1


def _cmd_login(args: argparse.Namespace) -> int:
    from .browser_sync import (
        BrowserSyncError,
        resolve_browser_proxy,
        sync_with_persistent_profile,
    )

    proxy_opt = resolve_browser_proxy(proxy=args.proxy, no_proxy=args.no_proxy)
    if args.no_proxy or (args.proxy and str(args.proxy).lower() in {"0", "none", "off", "direct"}):
        print("浏览器代理：直连（--no-proxy）")
    elif proxy_opt:
        print(f"浏览器代理：{proxy_opt['server']}")
    else:
        print("浏览器代理：无（环境未设置）")
    if args.force:
        print("已启用 --force：若有占用 .profile 的 Chromium 会先结束。")
    print("打开 Chromium，请在窗口里完成 ElevenLabs / Google 登录…")
    print("登录成功并进入 Image & Video 后会自动导出 refresh_token。")
    try:
        synced = sync_with_persistent_profile(
            headless=False,
            timeout_sec=args.timeout,
            proxy=args.proxy,
            no_proxy=args.no_proxy,
            force=args.force,
        )
    except BrowserSyncError as exc:
        print(f"失败：{exc}", file=sys.stderr)
        return 1
    except Exception as exc:  # noqa: BLE001
        print(f"失败：{exc}", file=sys.stderr)
        return 1
    print(
        f"已保存 · email={synced.email or '?'} · source={synced.source} · "
        f"refresh={len(synced.refresh_token)} chars"
    )
    return 0


def _cmd_connect(args: argparse.Namespace) -> int:
    from .browser_sync import BrowserSyncError, sync_via_cdp

    print(f"连接 CDP {args.cdp} …")
    try:
        synced = sync_via_cdp(args.cdp, timeout_sec=args.timeout)
    except BrowserSyncError as exc:
        print(f"失败：{exc}", file=sys.stderr)
        print(
            "提示：用 Chrome 启动远程调试，例如：\n"
            '  chrome.exe --remote-debugging-port=9222 --user-data-dir="%TEMP%\\el-debug"',
            file=sys.stderr,
        )
        return 1
    print(
        f"已保存 · email={synced.email or '?'} · source={synced.source} · "
        f"refresh={len(synced.refresh_token)} chars"
    )
    return 0


def _cmd_refresh(_: argparse.Namespace) -> int:
    from .auth import REFRESH_PATH, auth_status_message, ensure_fresh_auth

    if not REFRESH_PATH.is_file() and not __import__("os").environ.get(
        "ELEVENLABS_FIREBASE_REFRESH_TOKEN"
    ):
        print(
            f"没有 {REFRESH_PATH.name}。先运行：python -m elevenlabs_http login",
            file=sys.stderr,
        )
        return 1
    try:
        auth = ensure_fresh_auth(min_ttl_sec=3500, force_refresh=True)
    except Exception as exc:  # noqa: BLE001
        print(f"刷新失败：{exc}", file=sys.stderr)
        return 1
    print(auth_status_message(auth))
    return 0 if auth.ok else 1


def _cmd_watch(args: argparse.Namespace) -> int:
    from .auth import auth_status_message, ensure_fresh_auth

    interval = max(60, int(args.interval))
    min_ttl = max(120, int(args.min_ttl))
    print(f"watch：每 {interval}s 检查，Bearer 剩余 < {min_ttl}s 时自动续期（Ctrl+C 退出）")
    while True:
        try:
            auth = ensure_fresh_auth(min_ttl_sec=min_ttl)
            print(f"[{time.strftime('%H:%M:%S')}] {auth_status_message(auth)}", flush=True)
        except Exception as exc:  # noqa: BLE001
            print(f"[{time.strftime('%H:%M:%S')}] 续期失败：{exc}", flush=True)
        time.sleep(interval)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="elevenlabs_http", description="ElevenLabs 网页鉴权")
    sub = parser.add_subparsers(dest="cmd", required=True)

    p_status = sub.add_parser("status", help="查看当前 Bearer / refresh 状态")
    p_status.set_defaults(func=_cmd_status)

    p_login = sub.add_parser("login", help="有头浏览器登录并导出 refresh_token")
    p_login.add_argument("--timeout", type=float, default=300, help="等待登录秒数")
    p_login.add_argument(
        "--proxy",
        default=None,
        help="浏览器代理，如 http://127.0.0.1:7890；默认用 HTTP(S)_PROXY（忽略坏掉的 ALL_PROXY socks）",
    )
    p_login.add_argument(
        "--no-proxy",
        action="store_true",
        help="直连，忽略环境代理（ALL_PROXY socks 挂掉时用这个）",
    )
    p_login.add_argument(
        "--force",
        action="store_true",
        help="结束仍占用 .profile 的 Chromium，并清掉残留 SingletonLock",
    )
    p_login.set_defaults(func=_cmd_login)

    p_connect = sub.add_parser("connect", help="挂到已开远程调试的 Chrome (CDP)")
    p_connect.add_argument("--cdp", default="http://127.0.0.1:9222")
    p_connect.add_argument("--timeout", type=float, default=120)
    p_connect.set_defaults(func=_cmd_connect)

    p_refresh = sub.add_parser("refresh", help="立即用 refresh_token 换新 Bearer")
    p_refresh.set_defaults(func=_cmd_refresh)

    p_watch = sub.add_parser("watch", help="后台循环自动续期")
    p_watch.add_argument("--interval", type=int, default=600, help="检查间隔秒")
    p_watch.add_argument("--min-ttl", type=int, default=600, help="Bearer 最少剩余秒")
    p_watch.set_defaults(func=_cmd_watch)

    args = parser.parse_args(argv)
    return int(args.func(args) or 0)


if __name__ == "__main__":
    raise SystemExit(main())
