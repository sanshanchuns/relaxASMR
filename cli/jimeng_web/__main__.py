"""CLI：python -m jimeng_web login | status | generate"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from .client import JimengWebClient, JimengWebError


def cmd_login(_args: argparse.Namespace) -> int:
    client = JimengWebClient()
    try:
        st = client.interactive_login(log=print)
    except JimengWebError as exc:
        print(f"登录失败：{exc}", file=sys.stderr)
        return 1
    print(f"登录成功：{st.detail}")
    return 0


def cmd_status(_args: argparse.Namespace) -> int:
    st = JimengWebClient().login_status(log=print)
    print(f"logged_in={st.is_logged_in}  {st.detail}")
    return 0 if st.is_logged_in else 1


def cmd_generate(args: argparse.Namespace) -> int:
    client = JimengWebClient()
    try:
        out = client.generate_i2v(
            Path(args.image),
            args.prompt,
            Path(args.out),
            duration_sec=args.duration,
            model=args.model,
            ref_mode=args.ref_mode,
            log=print,
        )
    except JimengWebError as exc:
        print(f"生成失败：{exc}", file=sys.stderr)
        return 1
    print(f"OK → {out}")
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="jimeng_web", description="即梦网页 Playwright 图生视频")
    sub = parser.add_subparsers(dest="cmd", required=True)

    sub.add_parser("login", help="有头浏览器登录并持久化 profile")
    sub.add_parser("status", help="检查 profile 登录态")

    gen = sub.add_parser("generate", help="图生视频（需先 login）")
    gen.add_argument("--image", required=True)
    gen.add_argument("--prompt", required=True)
    gen.add_argument("--out", required=True)
    gen.add_argument("--duration", type=int, default=5)
    gen.add_argument("--model", default=None, help="默认 Seedance 2.0 VIP")
    gen.add_argument("--ref-mode", default=None, help="默认 首尾帧")

    args = parser.parse_args(argv)
    if args.cmd == "login":
        return cmd_login(args)
    if args.cmd == "status":
        return cmd_status(args)
    if args.cmd == "generate":
        return cmd_generate(args)
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
