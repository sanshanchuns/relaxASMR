"""GUI：子工程 output MP4 → YouTube 物料。"""

from __future__ import annotations

from pathlib import Path

# GUI 封面固定文案
RAIN_THUMB_TITLE = "Rain Sounds for Sleep"

_MIN_MP4_BYTES = 1_000_000  # 跳过空文件/未完成导出


def subproject_output_dir(scene_id: str, repo_root: Path) -> Path:
    return repo_root / "Reaper" / "Projects" / "Rain" / "subprojects" / scene_id / "output"


def _is_valid_mp4(path: Path) -> bool:
    try:
        return path.is_file() and path.stat().st_size >= _MIN_MP4_BYTES
    except OSError:
        return False


def _is_loop_preview(stem: str) -> bool:
    s = stem.lower()
    return "_loop_" in s or s.endswith("_loop") or s.startswith("loop_")


def _export_score(path: Path, scene_id: str) -> int:
    """成片 MP4 优先级打分（越高越优先）。"""
    if not _is_valid_mp4(path):
        return -1
    stem = path.stem.lower()
    sid = scene_id.lower()
    if _is_loop_preview(stem):
        return 0
    score = 10
    if sid in stem:
        score += 20
    if any(tok in stem for tok in ("_fhd_", "_4k", "_3h", "_gpu")):
        score += 30
    if "_loop" in stem:
        score -= 50
    return score


def find_subproject_mp4(scene_id: str, repo_root: Path, *, preferred: Path | None = None) -> Path | None:
    """在子工程 output/ 下找成片 MP4；排除 loop 预览与空文件。"""
    if preferred and _is_valid_mp4(preferred.resolve()):
        return preferred.resolve()

    output_dir = subproject_output_dir(scene_id, repo_root)
    if not output_dir.is_dir():
        return None

    mp4s = [p for p in output_dir.glob("*.mp4") if _is_valid_mp4(p)]
    if not mp4s:
        return None

    mp4s.sort(
        key=lambda p: (_export_score(p, scene_id), p.stat().st_mtime),
        reverse=True,
    )
    return mp4s[0]


def loop_material_dir(subproject_dir: Path, loop_video: Path) -> Path:
    """子工程内、基于 loop 视频文件名的物料目录。"""
    return subproject_dir / "output" / "material" / loop_video.stem


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
