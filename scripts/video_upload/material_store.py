"""YouTube 物料 JSON 读写；兼容 legacy *_material.md / youtube.md。"""

from __future__ import annotations

import json
import re
from pathlib import Path

from .parse_youtube_md import parse_youtube_md

SCHEMA_VERSION = 1


def build_material_record(
    *,
    scene_id: str,
    video_name: str,
    youtube_copy: dict,
    meta: dict | None = None,
    thumb_title: str = "",
    thumb_subtitle: str = "",
    scene_key: str = "",
) -> dict:
    record: dict = {
        "schema_version": SCHEMA_VERSION,
        "scene_id": scene_id,
        "video_name": video_name,
        "title_zh": youtube_copy.get("title_zh", ""),
        "title_en": youtube_copy.get("title_en", ""),
        "subtitle_zh": youtube_copy.get("subtitle_zh", ""),
        "subtitle_en": youtube_copy.get("subtitle_en", ""),
        "description_zh": youtube_copy.get("description_zh", ""),
        "description_en": youtube_copy.get("description_en", ""),
        "tags": list(youtube_copy.get("tags") or []),
        "thumb_title_en": thumb_title,
        "thumb_subtitle_en": thumb_subtitle,
    }
    if scene_key:
        record["scene_key"] = scene_key
    src = youtube_copy.get("metadata_source")
    if src:
        record["metadata_source"] = src
    tmpl = youtube_copy.get("template_id")
    if tmpl:
        record["template_id"] = tmpl
    if meta:
        record["video"] = {
            "duration_s": meta.get("duration_s"),
            "duration_human": meta.get("duration_human"),
            "duration_en": meta.get("duration_en"),
            "width": meta.get("width"),
            "height": meta.get("height"),
            "fps": meta.get("fps"),
            "codec": meta.get("codec"),
            "size_mb": meta.get("size_mb"),
            "bitrate_mbps": meta.get("bitrate_mbps"),
        }
    return record


def write_material_json(path: Path, record: dict) -> None:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(record, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )


def _normalize_json_record(data: dict) -> dict:
    return {
        "schema_version": data.get("schema_version", SCHEMA_VERSION),
        "scene_id": data.get("scene_id", ""),
        "title_zh": data.get("title_zh", ""),
        "title_en": data.get("title_en", ""),
        "subtitle_zh": data.get("subtitle_zh", ""),
        "subtitle_en": data.get("subtitle_en", ""),
        "description_zh": data.get("description_zh", ""),
        "description_en": data.get("description_en", ""),
        "tags": list(data.get("tags") or []),
        "video_name": data.get("video_name", ""),
        "thumb_title_en": data.get("thumb_title_en", ""),
        "thumb_subtitle_en": data.get("thumb_subtitle_en", ""),
        "scene_key": data.get("scene_key", ""),
        "metadata_source": data.get("metadata_source", ""),
        "template_id": data.get("template_id", ""),
        "video": data.get("video") or {},
    }


def load_material_metadata(path: Path) -> dict:
    """从 .json 或 legacy .md 加载统一元数据 dict。"""
    path = Path(path)
    if not path.is_file():
        raise FileNotFoundError(f"找不到物料文件：{path}")
    if path.suffix.lower() == ".json":
        data = json.loads(path.read_text(encoding="utf-8"))
        return _normalize_json_record(data)
    if path.suffix.lower() == ".md":
        return parse_youtube_md(path)
    raise ValueError(f"不支持的物料格式：{path.suffix}")


def scene_id_from_material_path(path: Path) -> str:
    m = re.match(r"(.+)_material\.(?:json|md)$", path.name, re.IGNORECASE)
    if m:
        return m.group(1)
    return ""


def resolve_material_path_for_scene(material_dir: Path, scene_id: str) -> Path | None:
    material_dir = Path(material_dir)
    for name in (f"{scene_id}_material.json", f"{scene_id}_material.md"):
        candidate = material_dir / name
        if candidate.is_file():
            return candidate
    return None


def resolve_material_in_dir(material_dir: Path) -> Path | None:
    material_dir = Path(material_dir)
    if material_dir.is_file():
        return material_dir if material_dir.suffix.lower() in (".json", ".md") else None
    for pattern in ("*_material.json", "*_material.md", "youtube.md"):
        matches = sorted(material_dir.glob(pattern))
        if matches:
            return matches[0]
    return None
