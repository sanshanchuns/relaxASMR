"""导出 staging：baseURL 为网络挂载时，先写本地再搬运到 export/。"""

from __future__ import annotations

import json
import os
import re
import shutil
import sys
from contextlib import contextmanager
from pathlib import Path
from typing import Iterator

from scripts.config.paths import REPO_ROOT, base_url

REMOTE_FS_TYPES = frozenset(
    {
        "cifs",
        "smbfs",
        "nfs",
        "nfs4",
        "fuse.sshfs",
        "smb3",
        "ceph",
        "fuseblk",
    }
)

_IP_IN_PATH_RE = re.compile(r"(?<![0-9.])(?:\d{1,3}\.){3}\d{1,3}(?![0-9.])")
RENDER_FILE_LINE_RE = re.compile(r"^(\s*RENDER_FILE\s+.+)\s*$", re.MULTILINE)
FILE_QUOTED_RE = re.compile(r'FILE "([^"]+)"')


def local_staging_dir() -> Path:
    env = os.environ.get("RELAXASMR_STAGING_DIR", "").strip()
    if env:
        return Path(env)
    return REPO_ROOT / "tmp" / "export"


def _read_user_config() -> dict:
    cfg_path = REPO_ROOT / "gui" / "user_config.json"
    if not cfg_path.is_file():
        return {}
    try:
        data = json.loads(cfg_path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return {}
    return data if isinstance(data, dict) else {}


def _filesystem_type(path: Path) -> str | None:
    try:
        resolved = path.resolve()
    except OSError:
        return None

    if sys.platform == "darwin":
        import subprocess

        proc = subprocess.run(
            ["stat", "-f", "%T", str(resolved)],
            capture_output=True,
            text=True,
            check=False,
        )
        if proc.returncode == 0:
            return proc.stdout.strip()
        return None

    try:
        mounts_text = Path("/proc/mounts").read_text(encoding="utf-8")
    except OSError:
        return None

    target = resolved.as_posix()
    best_match = ""
    best_fstype: str | None = None
    for line in mounts_text.splitlines():
        parts = line.split()
        if len(parts) < 3:
            continue
        mount_point = parts[1].replace("\\040", " ")
        if target == mount_point or target.startswith(mount_point.rstrip("/") + "/"):
            if len(mount_point) >= len(best_match):
                best_match = mount_point
                best_fstype = parts[2]
    return best_fstype


def base_url_is_network_mount() -> bool:
    """baseURL 是否经局域网/远程文件系统挂载（写入较慢）。"""
    bu = base_url()
    if _IP_IN_PATH_RE.search(bu.as_posix()):
        return True
    fstype = _filesystem_type(bu)
    if fstype and fstype.lower() in REMOTE_FS_TYPES:
        return True
    return False


def use_export_staging() -> bool:
    """是否启用本地 staging（环境变量 > user_config「协作机器」勾选）。"""
    env = os.environ.get("RELAXASMR_STAGING", "").strip().lower()
    if env in ("1", "true", "yes", "on"):
        return True
    if env in ("0", "false", "no", "off"):
        return False

    cfg = _read_user_config()
    if cfg.get("collaboration_machine") is True:
        return True
    # 兼容旧配置键
    if cfg.get("render_to_staging") is True:
        return True
    return False


def _rpp_render_file_line(render_dir: str) -> str:
    if " " in render_dir:
        return f'  RENDER_FILE "{render_dir}"'
    return f"  RENDER_FILE {render_dir}"


def render_dir_for_rpp(repo_root: Path | None = None) -> str:
    """Reaper RENDER_FILE 目录（本地 staging；WSL 下为 UNC）。"""
    out = local_staging_dir()
    out.mkdir(parents=True, exist_ok=True)
    repo = repo_root or REPO_ROOT
    reaper_scripts = repo / "Reaper" / "scripts"
    if str(reaper_scripts) not in sys.path:
        sys.path.insert(0, str(reaper_scripts))
    from media_paths import resolve_media_mode, wsl_unc_path

    mode = resolve_media_mode("auto", repo)
    if mode == "wsl_unc":
        return wsl_unc_path(out)
    return out.resolve().as_posix()


def _replace_render_file_line(text: str, render_dir: str) -> str:
    """替换 RENDER_FILE 行（不用 re.sub 字符串替换，避免 UNC 路径 \\U 被当成转义）。"""
    match = RENDER_FILE_LINE_RE.search(text)
    if not match:
        raise ValueError("未找到 RENDER_FILE")
    new_line = _rpp_render_file_line(render_dir)
    return text[: match.start()] + new_line + text[match.end() :]


def patch_rpp_render_file(rpp_path: Path, render_dir: str) -> str:
    """将 RPP 的 RENDER_FILE 改为 staging 目录，返回原始行以便恢复。"""
    text = rpp_path.read_text(encoding="utf-8")
    match = RENDER_FILE_LINE_RE.search(text)
    if not match:
        raise ValueError(f"未找到 RENDER_FILE: {rpp_path}")
    original = match.group(0).rstrip("\r\n")
    new_text = _replace_render_file_line(text, render_dir)
    rpp_path.write_text(new_text, encoding="utf-8")
    return original


def restore_rpp_render_file(rpp_path: Path, original_line: str) -> None:
    text = rpp_path.read_text(encoding="utf-8")
    match = RENDER_FILE_LINE_RE.search(text)
    if not match:
        return
    new_text = text[: match.start()] + original_line + text[match.end() :]
    rpp_path.write_text(new_text, encoding="utf-8")


def _reaper_scripts_on_path(repo_root: Path | None = None) -> Path:
    repo = repo_root or REPO_ROOT
    reaper_scripts = repo / "Reaper" / "scripts"
    if str(reaper_scripts) not in sys.path:
        sys.path.insert(0, str(reaper_scripts))
    return reaper_scripts


def staged_path_for_rpp(local_file: Path, repo_root: Path | None = None) -> str:
    """本地 staging 文件 → RPP 内 FILE 路径（WSL 下 UNC）。"""
    _reaper_scripts_on_path(repo_root)
    from media_paths import resolve_media_mode, wsl_unc_path

    repo = repo_root or REPO_ROOT
    mode = resolve_media_mode("auto", repo)
    resolved = local_file.resolve()
    if mode == "wsl_unc":
        return wsl_unc_path(resolved)
    return resolved.as_posix()


def unique_wav_paths_from_rpp(text: str) -> list[str]:
    """RPP 中去重后的 WAV FILE 路径（原始字符串，顺序稳定）。"""
    seen: set[str] = set()
    result: list[str] = []
    for match in FILE_QUOTED_RE.finditer(text):
        path = match.group(1)
        if not path.lower().endswith(".wav"):
            continue
        if path in seen:
            continue
        seen.add(path)
        result.append(path)
    return result


def resolve_rpp_file_path(old: str, rpp_path: Path, repo_root: Path | None = None) -> Path:
    _reaper_scripts_on_path(repo_root)
    from repair_rpp_paths import resolve_asset_path

    repo = repo_root or REPO_ROOT
    asset = resolve_asset_path(old, repo, rpp_path.parent)
    if asset is None or not asset.is_file():
        raise FileNotFoundError(f"找不到 RPP 素材: {old}")
    return asset.resolve()


def _local_sources_dir() -> Path:
    return local_staging_dir() / "sources"


def stage_source_wav(src: Path) -> Path:
    """复制/硬链单个 WAV 到 staging/sources/（文件名不变）。"""
    src = src.resolve()
    if not src.is_file():
        raise FileNotFoundError(f"素材不存在: {src}")

    staging = _local_sources_dir()
    staging.mkdir(parents=True, exist_ok=True)
    dest = staging / src.name
    if dest.is_file():
        try:
            if dest.stat().st_size == src.stat().st_size:
                return dest
        except OSError:
            pass
        dest.unlink()

    try:
        os.link(src, dest)
    except OSError:
        shutil.copy2(src, dest)
    return dest


def patch_rpp_for_local_render(
    text: str,
    *,
    wav_replacements: dict[str, str],
    render_dir: str,
) -> str:
    """将 RPP 文本中的 WAV 路径与 RENDER_FILE 指向本地 staging。"""
    patched = text
    for old, new in wav_replacements.items():
        patched = patched.replace(f'FILE "{old}"', f'FILE "{new}"')
    return _replace_render_file_line(patched, render_dir)


@contextmanager
def rpp_staging_for_render(rpp_path: Path, repo_root: Path | None = None) -> Iterator[Path]:
    """协作机器：素材 WAV 与渲染输出均走本地 staging，结束后恢复 RPP。"""
    repo = repo_root or REPO_ROOT
    rpp_path = rpp_path.resolve()
    original_text = rpp_path.read_text(encoding="utf-8")
    staged_wavs: list[Path] = []

    wav_old_paths = unique_wav_paths_from_rpp(original_text)
    wav_replacements: dict[str, str] = {}
    for old in wav_old_paths:
        src = resolve_rpp_file_path(old, rpp_path, repo)
        local = stage_source_wav(src)
        staged_wavs.append(local)
        wav_replacements[old] = staged_path_for_rpp(local, repo)

    render_dir = render_dir_for_rpp(repo)
    patched = patch_rpp_for_local_render(
        original_text,
        wav_replacements=wav_replacements,
        render_dir=render_dir,
    )
    rpp_path.write_text(patched, encoding="utf-8")

    try:
        yield local_staging_dir()
    finally:
        rpp_path.write_text(original_text, encoding="utf-8")
        for path in staged_wavs:
            try:
                if path.is_file():
                    path.unlink()
            except OSError:
                pass


@contextmanager
def rpp_staging_render_dir(rpp_path: Path, repo_root: Path | None = None) -> Iterator[Path]:
    """兼容旧名：仅改 RENDER_FILE（请优先用 rpp_staging_for_render）。"""
    render_dir = render_dir_for_rpp(repo_root)
    original = patch_rpp_render_file(rpp_path, render_dir)
    try:
        yield local_staging_dir()
    finally:
        restore_rpp_render_file(rpp_path, original)


def finalize_export(local_path: Path, final_path: Path) -> Path:
    """校验后将 staging 产物移动到最终 export 路径。"""
    local_path = local_path.resolve()
    final_path = final_path.resolve()
    if not local_path.is_file():
        raise FileNotFoundError(f"staging 产物不存在: {local_path}")

    final_path.parent.mkdir(parents=True, exist_ok=True)
    if final_path.is_file():
        final_path.unlink()

    try:
        shutil.move(str(local_path), str(final_path))
    except OSError:
        shutil.copy2(local_path, final_path)
        local_path.unlink()
    return final_path


def _local_inputs_dir() -> Path:
    return local_staging_dir() / "inputs"


def stage_input_file(src: Path, *, dest_name: str | None = None) -> Path:
    """将 NAS 上的输入文件复制/硬链到 staging/inputs/，供 FFmpeg 本地读取。"""
    src = src.resolve()
    if not src.is_file():
        raise FileNotFoundError(f"输入文件不存在: {src}")

    staging = _local_inputs_dir()
    staging.mkdir(parents=True, exist_ok=True)
    dest = staging / (dest_name or src.name)
    if dest.is_file():
        try:
            if dest.stat().st_size == src.stat().st_size:
                return dest
        except OSError:
            pass
        dest.unlink()

    try:
        os.link(src, dest)
    except OSError:
        shutil.copy2(src, dest)
    return dest


@contextmanager
def staged_mp4_inputs(audio: Path, video: Path) -> Iterator[tuple[Path, Path]]:
    """协作机器：混音 WAV + loop 视频先落到本地 inputs/，编码结束后删除。"""
    local_audio = stage_input_file(audio)
    local_video = stage_input_file(video)
    try:
        yield local_audio, local_video
    finally:
        for path in (local_audio, local_video):
            try:
                if path.is_file():
                    path.unlink()
            except OSError:
                pass
