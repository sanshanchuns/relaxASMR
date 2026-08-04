"""CLI：python -m elevenlabs_web login | status | generate"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from .client import ElevenLabsWebUiClient, ElevenLabsWebUiError


def cmd_login(_args: argparse.Namespace) -> int:
    try:
        st = ElevenLabsWebUiClient().interactive_login(log=print)
    except ElevenLabsWebUiError as exc:
        print(f"登录失败：{exc}", file=sys.stderr)
        return 1
    print(f"登录成功：{st.detail}")
    return 0


def cmd_status(_args: argparse.Namespace) -> int:
    st = ElevenLabsWebUiClient().login_status(log=print)
    print(f"logged_in={st.is_logged_in}  {st.detail}")
    return 0 if st.is_logged_in else 1


def cmd_generate(args: argparse.Namespace) -> int:
    try:
        out = ElevenLabsWebUiClient().generate_i2v(
            Path(args.image),
            args.prompt,
            Path(args.out),
            duration_sec=args.duration,
            resolution=args.resolution,
            log=print,
        )
    except ElevenLabsWebUiError as exc:
        print(f"生成失败：{exc}", file=sys.stderr)
        return 1
    print(f"OK → {out}")
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="elevenlabs_web",
        description="ElevenLabs Image&Video 网页 Playwright 图生视频",
    )
    sub = parser.add_subparsers(dest="cmd", required=True)
    sub.add_parser("login")
    sub.add_parser("status")
    gen = sub.add_parser("generate")
    gen.add_argument("--image", required=True)
    gen.add_argument("--prompt", required=True)
    gen.add_argument("--out", required=True)
    gen.add_argument("--duration", type=int, default=5)
    gen.add_argument("--resolution", default="480p")
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
