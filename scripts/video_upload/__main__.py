#!/usr/bin/env python3
"""CLI：从物料目录上传到 YouTube。"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

_SCRIPTS = Path(__file__).resolve().parents[1]
if str(_SCRIPTS) not in sys.path:
    sys.path.insert(0, str(_SCRIPTS))

from video_upload.youtube_upload import DEFAULT_ACCOUNT, resolve_account_paths, upload_from_material


def main() -> None:
    parser = argparse.ArgumentParser(description="上传子工程物料到 YouTube")
    parser.add_argument("material_dir", type=Path, help="含 youtube.md / thumbnail.jpg 的目录")
    parser.add_argument(
        "--privacy",
        choices=("private", "unlisted", "public"),
        default="unlisted",
        help="可见性（默认 unlisted）",
    )
    parser.add_argument(
        "--language",
        choices=("en", "zh"),
        default="en",
        help="标题/描述语言（默认英文）",
    )
    parser.add_argument(
        "--account",
        choices=("leo", "leo_usa"),
        default=DEFAULT_ACCOUNT,
        help="YouTube 账号（默认 leo）",
    )
    parser.add_argument(
        "--credentials",
        type=Path,
        default=None,
        help="OAuth client secrets（默认按 --account 从 config/ 读取）",
    )
    parser.add_argument(
        "--token",
        type=Path,
        default=None,
        help="OAuth token 缓存（默认按 --account 从 config/ 读取）",
    )
    args = parser.parse_args()

    if not args.material_dir.is_dir():
        print(f"Error: 目录不存在 {args.material_dir}", file=sys.stderr)
        sys.exit(1)

    creds_path, token_path, account = resolve_account_paths(
        args.account,
        credentials_path=args.credentials,
        token_path=args.token,
    )
    if not creds_path.is_file():
        print(f"Error: 找不到 OAuth 凭据 {creds_path}", file=sys.stderr)
        sys.exit(1)

    try:
        record = upload_from_material(
            args.material_dir,
            language=args.language,
            privacy_status=args.privacy,
            account=account,
            credentials_path=creds_path,
            token_path=token_path,
        )
        print(f"\n完成：{record['url']}")
    except Exception as exc:
        print(f"Error: {exc}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
