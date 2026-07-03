"""GUI：子工程 output MP4 → YouTube 物料。"""

from __future__ import annotations

from pathlib import Path


def subproject_output_dir(scene_id: str, repo_root: Path) -> Path:
    return repo_root / "Reaper" / "Projects" / "Rain" / "subprojects" / scene_id / "output"


def find_subproject_mp4(scene_id: str, repo_root: Path) -> Path | None:
    """在子工程 output/ 下找最新 MP4，优先含 4k 的文件名。"""
    output_dir = subproject_output_dir(scene_id, repo_root)
    if not output_dir.is_dir():
        return None
    mp4s = sorted(output_dir.glob("*.mp4"), key=lambda p: p.stat().st_mtime, reverse=True)
    if not mp4s:
        return None
    for p in mp4s:
        if "4k" in p.stem.lower():
            return p
    return mp4s[0]


def material_output_dir(mp4: Path) -> Path:
    return mp4.parent / "material" / mp4.stem


def material_root_dir(scene_id: str, repo_root: Path) -> Path:
    return subproject_output_dir(scene_id, repo_root) / "material"


def find_material_dir(scene_id: str, repo_root: Path) -> Path | None:
    """定位物料目录：优先当前 MP4 对应子目录，否则 output/material 下最新子目录。"""
    mp4 = find_subproject_mp4(scene_id, repo_root)
    if mp4:
        specific = material_output_dir(mp4)
        if specific.is_dir():
            return specific
    root = material_root_dir(scene_id, repo_root)
    if not root.is_dir():
        return None
    subdirs = sorted(
        [p for p in root.iterdir() if p.is_dir()],
        key=lambda p: p.stat().st_mtime,
        reverse=True,
    )
    if subdirs:
        return subdirs[0]
    return root
