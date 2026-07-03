"""从 generate_youtube_material 输出的 youtube.md 解析元数据。"""

from __future__ import annotations

import re
from pathlib import Path


def _section(text: str, heading: str) -> str:
    pattern = rf"^## {re.escape(heading)}\s*\n\n(.*?)(?=\n## |\Z)"
    m = re.search(pattern, text, re.MULTILINE | re.DOTALL)
    return m.group(1).strip() if m else ""


def _first_line(block: str) -> str:
    for line in block.splitlines():
        s = line.strip()
        if s and not s.startswith("**") and not s.startswith("!["):
            return s
    return ""


def parse_tags(block: str) -> list[str]:
    line = _first_line(block)
    if not line or line.startswith("（"):
        return []
    tags = [t.strip() for t in line.split(",") if t.strip()]
    return tags


def parse_youtube_md(path: Path) -> dict:
    text = path.read_text(encoding="utf-8")
    title_zh = _first_line(_section(text, "中文标题"))
    title_en = _first_line(_section(text, "English Title"))
    desc_zh = _section(text, "中文说明")
    desc_en = _section(text, "English Description")
    tags = parse_tags(_section(text, "标签 Tags"))

    video_name = ""
    m = re.search(r"\| 文件 \| `([^`]+)` \|", text)
    if m:
        video_name = m.group(1)

    return {
        "title_zh": title_zh,
        "title_en": title_en,
        "description_zh": desc_zh,
        "description_en": desc_en,
        "tags": tags,
        "video_name": video_name,
    }


def pick_title(meta: dict, language: str = "en") -> str:
    if language == "zh":
        return meta.get("title_zh") or meta.get("title_en", "")
    return meta.get("title_en") or meta.get("title_zh", "")


def pick_description(meta: dict, language: str = "en") -> str:
    if language == "zh":
        return meta.get("description_zh") or meta.get("description_en", "")
    return meta.get("description_en") or meta.get("description_zh", "")
