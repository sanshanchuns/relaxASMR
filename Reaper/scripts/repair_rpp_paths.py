#!/usr/bin/env python3
"""修复已有 .rpp 中的 Linux 绝对路径 → 相对路径或 WSL UNC。"""

from __future__ import annotations

import argparse
import os
import re
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]


def media_path_for_rpp(asset: Path, rpp_dir: Path, path_mode: str) -> str:
    asset = asset.resolve()
    rpp_dir = rpp_dir.resolve()
    if path_mode == "wsl_unc":
        distro = os.environ.get("WSL_DISTRO_NAME", "Ubuntu")
        posix = asset.as_posix()
        if posix.startswith("/"):
            rest = posix[1:].replace("/", "\\")
            return f"\\\\wsl.localhost\\{distro}\\{rest}"
        return posix.replace("/", "\\")
    if path_mode == "absolute":
        return asset.as_posix()
    return os.path.relpath(asset, rpp_dir).replace("/", "\\")


def repair_rpp(rpp_path: Path, repo_root: Path, path_mode: str) -> int:
    text = rpp_path.read_text(encoding="utf-8")
    rpp_dir = rpp_path.parent
    count = 0

    def repl(match: re.Match[str]) -> str:
        nonlocal count
        old = match.group(1)
        # 已是相对路径或 UNC
        if not old.startswith("/") and not old.startswith("\\\\"):
            return match.group(0)
        p = Path(old)
        if not p.is_absolute() and old.startswith("/"):
            p = Path(old)
        try:
            rel_to_repo = p.relative_to(repo_root.resolve())
            new = media_path_for_rpp(repo_root / rel_to_repo, rpp_dir, path_mode)
        except ValueError:
            return match.group(0)
        count += 1
        return f'FILE "{new}"'

    new_text = re.sub(r'FILE "([^"]+)"', repl, text)
    if count:
        rpp_path.write_text(new_text, encoding="utf-8")
    return count


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("rpp", type=Path)
    parser.add_argument("--repo", type=Path, default=REPO_ROOT)
    parser.add_argument(
        "--path-mode",
        choices=("relative", "wsl_unc", "absolute"),
        default="relative",
    )
    args = parser.parse_args()
    n = repair_rpp(args.rpp, args.repo, args.path_mode)
    print(f"Updated {n} paths in {args.rpp}")


if __name__ == "__main__":
    main()
