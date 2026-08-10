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


def cmd_generate_t2v(args: argparse.Namespace) -> int:
    client = JimengWebClient()
    try:
        out = client.generate_t2v(
            args.prompt,
            Path(args.out),
            duration_sec=args.duration,
            model=args.model,
            log=print,
        )
    except JimengWebError as exc:
        print(f"生成失败：{exc}", file=sys.stderr)
        return 1
    print(f"OK → {out}")
    return 0


def cmd_agentic(args: argparse.Namespace) -> int:
    client = JimengWebClient()
    images = [Path(p) for p in (args.image or [])]
    try:
        text = client.agentic_chat(
            args.prompt,
            images=images or None,
            timeout_s=args.timeout,
            new_chat=not args.continue_chat,
            log=print,
        )
    except JimengWebError as exc:
        print(f"Agent 失败：{exc}", file=sys.stderr)
        return 1
    print(text)
    if args.out:
        Path(args.out).write_text(text + "\n", encoding="utf-8")
        print(f"OK → {args.out}", file=sys.stderr)
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
    gen.add_argument("--model", default=None, help="默认 Seedance 2.0 Fast VIP")
    gen.add_argument("--ref-mode", default=None, help="默认 首尾帧")

    t2v = sub.add_parser("generate-t2v", help="文生视频（需先 login）")
    t2v.add_argument("--prompt", required=True)
    t2v.add_argument("--out", required=True)
    t2v.add_argument("--duration", type=int, default=4)
    t2v.add_argument("--model", default=None, help="默认 Seedance 2.0 Fast VIP")

    ag = sub.add_parser("agentic", help="即梦 Agent 对话（需先 login）")
    ag.add_argument("--prompt", required=True)
    ag.add_argument("--image", action="append", default=[], help="可重复；附图路径")
    ag.add_argument("--out", default=None, help="可选：把回复写入文件")
    ag.add_argument("--timeout", type=float, default=180.0)
    ag.add_argument("--continue-chat", action="store_true", help="不点「新对话」")

    args = parser.parse_args(argv)
    if args.cmd == "login":
        return cmd_login(args)
    if args.cmd == "status":
        return cmd_status(args)
    if args.cmd == "generate":
        return cmd_generate(args)
    if args.cmd == "generate-t2v":
        return cmd_generate_t2v(args)
    if args.cmd == "agentic":
        return cmd_agentic(args)
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
