"""步骤 5 上传状态文案（纯函数，便于测试）。"""

from __future__ import annotations

from pathlib import Path


def is_uploaded_cfg_entry(value: object) -> bool:
    if isinstance(value, dict):
        return True
    return bool(value)


def mp4_path_from_upload_entry(value: object) -> str | None:
    if isinstance(value, dict):
        raw = value.get("mp4")
        if isinstance(raw, str) and raw.strip():
            return raw.strip()
    return None


def format_media_rel_path(path: Path, *, export_root: Path, base_root: Path) -> str:
    try:
        rel = path.relative_to(export_root)
        return f"export/{rel}"
    except ValueError:
        try:
            return str(path.relative_to(base_root))
        except ValueError:
            return str(path)


def format_step5_upload_label(*, uploaded: bool, rel_path: str, custom: bool = False) -> str:
    state = "已上传" if uploaded else "待上传"
    suffix = "（自定义）" if custom else ""
    return f"{state}：{rel_path}{suffix}"
