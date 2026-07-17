#!/usr/bin/env python3
"""修复已有 .rpp 中的媒体路径（WSL UNC / Audio Files → 当前环境可用路径）。"""

from __future__ import annotations

import argparse
import re
from pathlib import Path

from media_paths import describe_media_mode, media_path_for_rpp, resolve_media_mode

REPO_ROOT = Path(__file__).resolve().parents[2]
import sys

if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from scripts.config.paths import migrate_stored_path


def unc_to_posix(unc: str) -> Path | None:
    m = re.match(r"^\\\\wsl\.localhost\\[^\\]+\\(.+)$", unc, re.I)
    if not m:
        return None
    return Path("/" + m.group(1).replace("\\", "/"))


def win_drive_to_posix(win: str) -> Path | None:
    m = re.match(r"^([A-Za-z]):\\(.*)$", win)
    if not m:
        return None
    return Path(f"/mnt/{m.group(1).lower()}/{m.group(2).replace(chr(92), '/')}")


def resolve_asset_path(
    old: str,
    repo_root: Path,
    rpp_dir: Path,
    *,
    allow_dir: bool = False,
) -> Path | None:
    if old.startswith("Audio Files/") or old.startswith("Audio Files\\"):
        name = Path(old).name
        matches = list(repo_root.glob(f"assets/**/{name}"))
        if matches:
            return matches[0].resolve()
        local = (rpp_dir / old).resolve()
        if local.is_file() or (allow_dir and local.is_dir()):
            return local

    def ok(p: Path) -> bool:
        try:
            return p.is_file() or (allow_dir and p.is_dir())
        except OSError:
            return False

    candidates: list[Path] = []
    if old.startswith("\\\\wsl.localhost"):
        p = unc_to_posix(old)
        if p is not None:
            candidates.append(p)
    if re.match(r"^[A-Za-z]:\\", old):
        p = win_drive_to_posix(old)
        if p is not None:
            candidates.append(p)
    candidates.append(Path(old))

    seen: set[str] = set()
    for cand in candidates:
        for attempt in (cand, migrate_stored_path(cand)):
            key = str(attempt)
            if key in seen:
                continue
            seen.add(key)
            if ok(attempt):
                return attempt.resolve()

    p = Path(old)
    if p.is_absolute():
        try:
            remapped = migrate_stored_path(p)
            if ok(remapped):
                return remapped.resolve()
        except OSError:
            pass

    local = (rpp_dir / old).resolve()
    if ok(local):
        return local.resolve()

    return None


def _rewrite_media_path(
    old: str,
    rpp_dir: Path,
    repo_root: Path,
    path_mode: str,
    *,
    allow_dir: bool = False,
) -> str | None:
    asset = resolve_asset_path(old, repo_root, rpp_dir, allow_dir=allow_dir)
    if asset is None:
        return None

    try:
        asset.relative_to(repo_root.resolve())
    except ValueError:
        if not (
            old.startswith("\\\\wsl.localhost")
            or old.startswith("Audio Files")
            or re.match(r"^[A-Za-z]:\\", old)
        ):
            return None

    return media_path_for_rpp(asset, rpp_dir, path_mode, repo_root)


def repair_rpp(rpp_path: Path, repo_root: Path, path_mode: str) -> int:
    text = rpp_path.read_text(encoding="utf-8")
    rpp_dir = rpp_path.parent
    count = 0

    def repl_file(match: re.Match[str]) -> str:
        nonlocal count
        old = match.group(1)
        suffix = match.group(2) or ""
        new = _rewrite_media_path(old, rpp_dir, repo_root, path_mode)
        if new is None or new == old:
            return match.group(0)
        count += 1
        return f'FILE "{new}"{suffix}'

    def repl_render(match: re.Match[str]) -> str:
        nonlocal count
        old = match.group(1).strip().strip('"')
        new = _rewrite_media_path(old, rpp_dir, repo_root, path_mode, allow_dir=True)
        if new is None or new == old:
            return match.group(0)
        count += 1
        if " " in new:
            return f'  RENDER_FILE "{new}"'
        return f"  RENDER_FILE {new}"

    new_text = re.sub(r'FILE "([^"]+)"(\s*\d*)', repl_file, text)
    new_text = re.sub(r"^\s*RENDER_FILE\s+(.+)$", repl_render, new_text, flags=re.MULTILINE)
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
