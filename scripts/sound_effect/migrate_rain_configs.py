#!/usr/bin/env python3
"""将 asmr_config / scenes 配方迁移到六层架构。"""

from __future__ import annotations

import re
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
RAIN_ROOT = REPO_ROOT / "assets/sound_effect/rain_sound"
SCENES_ROOT = REPO_ROOT / "Reaper" / "Projects" / "Rain"


def find_by_filename(name: str) -> str | None:
    for mp3 in RAIN_ROOT.rglob(name):
        if "before_backup" in mp3.parts:
            continue
        rel = mp3.relative_to(REPO_ROOT / "assets")
        return "assets/" + rel.as_posix()
    return None


def remap_path(old: str) -> str:
    name = Path(old).name
    found = find_by_filename(name)
    return found or old


def migrate_content(text: str) -> str:
    text = text.replace("track = 8,", "track = 7,")
    text = text.replace("track = 8\n", "track = 7\n")

    # 移除 1_base loop 块（合并进 3_environment）
    text = re.sub(
        r"\s*\{\s*track = 1,\s*id = \"1_base\",.*?\},\s*",
        "",
        text,
        count=1,
        flags=re.S,
    )
    text = re.sub(r"loop_layers = \{\s*,", "loop_layers = {", text)

    subs = [
        (r"track = 2,\s*id = \"2_rain\"", "track = 1,\n      id = \"1_rain\""),
        (r"track = 3,\s*id = \"3_impact\"", "track = 2,\n      id = \"2_impact\""),
        (r"track = 5,\s*id = \"5_env\"", "track = 3,\n      id = \"3_environment\""),
        (r"track = 7,\s*id = \"7_comfort\"", "track = 6,\n      id = \"6_human\""),
        (r"track = 6,\s*id = \"6_life\"", "track = 5,\n      id = \"5_wildlife\""),
        (r'id = "2_rain"', 'id = "1_rain"'),
        (r'id = "3_impact"', 'id = "2_impact"'),
        (r'id = "5_env"', 'id = "3_environment"'),
        (r'id = "7_comfort"', 'id = "6_human"'),
        (r'id = "6_life"', 'id = "5_wildlife"'),
        (r'id = "1_base"', 'id = "3_environment"'),
    ]
    for pat, repl in subs:
        text = re.sub(pat, repl, text)

    for m in re.finditer(r'"assets/sound_effect/[^"]+\.mp3"', text):
        old = m.group(0)[1:-1]
        new = remap_path(old)
        if new != old:
            text = text.replace(old, new)
    return text


def main() -> None:
    n = 0
    for pattern in ("scripts/scenes/*.lua", "subprojects/*/scripts/asmr_config.lua"):
        for p in SCENES_ROOT.glob(pattern):
            new = migrate_content(p.read_text(encoding="utf-8"))
            if new != p.read_text(encoding="utf-8"):
                p.write_text(new, encoding="utf-8")
                print(f"updated {p.relative_to(REPO_ROOT)}")
                n += 1
    print(f"==> {n} files updated")


if __name__ == "__main__":
    main()
