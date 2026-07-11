#!/usr/bin/env python3
"""按直观雨量从小到大重命名气候编号（C1–C9）。

两阶段重命名避免编号冲突，例如旧 C9→新 C2 与旧 C2→新 C3。
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT))

from scripts.config.common_constants import (  # noqa: E402
    CLIMATE_FILE_TAGS,
    CLIMATE_LEGACY_FILE_TAGS,
    CLIMATE_LEGACY_TO_NEW,
)
from scripts.config.paths import audio_layer_dir  # noqa: E402

PLACEHOLDER_FMT = "__CLIM_L{legacy_id}__"


def _replace_file_content(path: Path, *, dry_run: bool) -> bool:
    try:
        text = path.read_text(encoding="utf-8", errors="surrogateescape")
    except OSError:
        return False
    orig = text
    for legacy_id, legacy_tag in CLIMATE_LEGACY_FILE_TAGS.items():
        new_tag = CLIMATE_FILE_TAGS[CLIMATE_LEGACY_TO_NEW[legacy_id]]
        if legacy_tag != new_tag:
            text = text.replace(legacy_tag, new_tag)
    if text == orig:
        return False
    if not dry_run:
        path.write_text(text, encoding="utf-8", errors="surrogateescape")
    print(f"  [content] {path.name}")
    return True


def _rename_dir(directory: Path, *, dry_run: bool, fix_content: bool) -> int:
    if not directory.is_dir():
        print(f"  跳过（目录不存在）: {directory}")
        return 0

    changed = 0
    files = sorted(directory.iterdir())
    if not files:
        print(f"  跳过（空目录）: {directory}")
        return 0

    # 阶段 1：旧标签 → 占位符
    for path in files:
        if not path.is_file():
            continue
        for legacy_id, legacy_tag in CLIMATE_LEGACY_FILE_TAGS.items():
            new_id = CLIMATE_LEGACY_TO_NEW[legacy_id]
            new_tag = CLIMATE_FILE_TAGS[new_id]
            if legacy_tag == new_tag or legacy_tag not in path.name:
                continue
            placeholder = PLACEHOLDER_FMT.format(legacy_id=legacy_id)
            new_name = path.name.replace(legacy_tag, placeholder)
            target = path.parent / new_name
            print(f"  {path.name} -> {new_name}")
            if not dry_run:
                path.rename(target)
            changed += 1
            break

    # 阶段 2：占位符 → 新标签
    for path in sorted(directory.iterdir()):
        if not path.is_file():
            continue
        for legacy_id in CLIMATE_LEGACY_FILE_TAGS:
            placeholder = PLACEHOLDER_FMT.format(legacy_id=legacy_id)
            if placeholder not in path.name:
                continue
            new_id = CLIMATE_LEGACY_TO_NEW[legacy_id]
            new_tag = CLIMATE_FILE_TAGS[new_id]
            new_name = path.name.replace(placeholder, new_tag)
            target = path.parent / new_name
            print(f"  {path.name} -> {new_name}")
            if not dry_run:
                path.rename(target)
            changed += 1
            break

    if fix_content:
        for path in sorted(directory.iterdir()):
            if path.is_file() and path.suffix.lower() in {".rpp", ".rain", ".lua"}:
                if _replace_file_content(path, dry_run=dry_run):
                    changed += 1

    return changed


def default_targets() -> list[Path]:
    preset_root = REPO_ROOT / "scripts/video_analysis/preset_db"
    rain_dir = audio_layer_dir("1_rain").parent  # .../audio/1_rain
    return [
        preset_root / "natural_rain_presets",
        preset_root / "natural_rain_rpps",
        rain_dir / "sounds",
        rain_dir / "dedup_removed",
        rain_dir / "sounds_bak",
    ]


def main() -> int:
    parser = argparse.ArgumentParser(description="重命名 C1–C9 气候编号")
    parser.add_argument("dirs", nargs="*", type=Path, help="目标目录（默认 preset + 声源库）")
    parser.add_argument("--dry-run", action="store_true", help="只打印，不实际重命名")
    parser.add_argument("--content-only", action="store_true", help="仅替换文件内容中的旧标签")
    args = parser.parse_args()

    targets = args.dirs or default_targets()
    total = 0
    for directory in targets:
        print(f"\n=== {directory} ===")
        if args.content_only:
            if not directory.is_dir():
                print(f"  跳过（目录不存在）: {directory}")
                continue
            for path in sorted(directory.iterdir()):
                if path.is_file() and path.suffix.lower() in {".rpp", ".rain", ".lua"}:
                    if _replace_file_content(path, dry_run=args.dry_run):
                        total += 1
        else:
            total += _rename_dir(directory.resolve(), dry_run=args.dry_run, fix_content=True)

    print(f"\n共处理 {total} 个文件" + ("（dry-run）" if args.dry_run else ""))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
