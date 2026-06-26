#!/usr/bin/env python3
"""修复已有 .rpp 中的媒体路径（WSL UNC / Audio Files → 当前环境可用路径）。"""

from __future__ import annotations

import argparse
import re
from pathlib import Path

from media_paths import describe_media_mode, media_path_for_rpp, resolve_media_mode

REPO_ROOT = Path(__file__).resolve().parents[2]


def unc_to_posix(unc: str) -> Path | None:
    m = re.match(r"^\\\\wsl\.localhost\\[^\\]+\\(.+)$", unc, re.I)
    if not m:
        return None
    return Path("/" + m.group(1).replace("\\", "/"))


def resolve_asset_path(old: str, repo_root: Path, rpp_dir: Path) -> Path | None:
    if old.startswith("\\\\wsl.localhost"):
        p = unc_to_posix(old)
        if p is None or not p.is_file():
            return None
        return p.resolve()

    if old.startswith("Audio Files/") or old.startswith("Audio Files\\"):
        name = Path(old).name
        matches = list(repo_root.glob(f"assets/**/{name}"))
        if matches:
            return matches[0].resolve()
        local = (rpp_dir / old).resolve()
        return local if local.is_file() else None

    p = Path(old)
    if p.is_absolute() and p.is_file():
        return p.resolve()

    local = (rpp_dir / old).resolve()
    if local.is_file():
        return local.resolve()

    return None


def repair_rpp(rpp_path: Path, repo_root: Path, path_mode: str) -> int:
    text = rpp_path.read_text(encoding="utf-8")
    rpp_dir = rpp_path.parent
    count = 0

    def repl(match: re.Match[str]) -> str:
        nonlocal count
        old = match.group(1)
        suffix = match.group(2) or ""

        asset = resolve_asset_path(old, repo_root, rpp_dir)
        if asset is None:
            return match.group(0)

        try:
            asset.relative_to(repo_root.resolve())
        except ValueError:
            if not (old.startswith("\\\\wsl.localhost") or old.startswith("Audio Files")):
                return match.group(0)

        new = media_path_for_rpp(asset, rpp_dir, path_mode, repo_root)
        if new == old:
            return match.group(0)
        count += 1
        return f'FILE "{new}"{suffix}'

    new_text = re.sub(r'FILE "([^"]+)"(\s*\d*)', repl, text)
    if count:
        rpp_path.write_text(new_text, encoding="utf-8")
    return count


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("rpp", type=Path)
    parser.add_argument("--repo", type=Path, default=REPO_ROOT)
    parser.add_argument(
        "--path-mode",
        choices=("auto", "relative", "wsl_unc", "absolute"),
        default="auto",
    )
    args = parser.parse_args()
    label = describe_media_mode(args.path_mode, args.repo)
    n = repair_rpp(args.rpp, args.repo, args.path_mode)
    print(f"Updated {n} paths in {args.rpp} ({label})")


if __name__ == "__main__":
    main()
