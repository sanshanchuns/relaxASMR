"""Boom WAV 16-bit 持久化：booms/ 与 booms_16bit/ 同名镜像。

L2 磁盘缓存供 GUI 试听；可用 ``python3 -m scripts.audio.booms_16bit`` 一次性预热。
"""

from __future__ import annotations

import argparse
import subprocess
import sys
from collections.abc import Callable
from pathlib import Path
from shutil import which

REPO = Path(__file__).resolve().parents[2]
if str(REPO) not in sys.path:
    sys.path.insert(0, str(REPO))

from scripts.config.paths import audio_dir  # noqa: E402


def booms_16bit_path_for(wav_path: Path) -> Path | None:
    """若 wav 位于 .../booms/ 下，返回对应 booms_16bit/ 同名路径。"""
    wav_path = wav_path.resolve()
    if wav_path.parent.name != "booms":
        return None
    return wav_path.parent.parent / "booms_16bit" / wav_path.name


def is_booms_16bit_fresh(src: Path, dst: Path) -> bool:
    return dst.is_file() and dst.stat().st_mtime >= src.stat().st_mtime


def wav_bits_per_sample(wav_path: Path) -> int:
    if not which("ffprobe"):
        return 16
    try:
        out = subprocess.check_output(
            [
                "ffprobe",
                "-v",
                "error",
                "-select_streams",
                "a:0",
                "-show_entries",
                "stream=bits_per_sample",
                "-of",
                "default=nw=1:nk=1",
                str(wav_path),
            ],
            text=True,
            stderr=subprocess.DEVNULL,
        ).strip()
        return int(out) if out.isdigit() else 16
    except (subprocess.CalledProcessError, ValueError, OSError):
        return 16


def transcode_wav_to_s16le(src: Path, dst: Path) -> None:
    if not which("ffmpeg"):
        raise RuntimeError("未找到 ffmpeg，无法转码 booms_16bit")
    dst.parent.mkdir(parents=True, exist_ok=True)
    subprocess.run(
        [
            "ffmpeg",
            "-y",
            "-loglevel",
            "error",
            "-i",
            str(src),
            "-c:a",
            "pcm_s16le",
            str(dst),
        ],
        check=True,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )


def ensure_booms_16bit(wav_path: Path, *, force: bool = False) -> Path | None:
    """确保 booms 源文件有可用 16-bit 副本；非 booms 或已是 16-bit 则返回 None。"""
    wav_path = wav_path.resolve()
    if not wav_path.is_file():
        raise FileNotFoundError(wav_path)
    dst = booms_16bit_path_for(wav_path)
    if dst is None:
        return None
    if wav_bits_per_sample(wav_path) <= 16:
        return None
    if not force and is_booms_16bit_fresh(wav_path, dst):
        return dst
    transcode_wav_to_s16le(wav_path, dst)
    return dst


def iter_booms_wavs() -> list[Path]:
    root = audio_dir()
    if not root.is_dir():
        return []
    wavs: list[Path] = []
    for layer_dir in sorted(root.iterdir()):
        if not layer_dir.is_dir():
            continue
        booms = layer_dir / "booms"
        if not booms.is_dir():
            continue
        wavs.extend(sorted(p for p in booms.glob("*.wav") if p.is_file()))
    return wavs


def prewarm_booms_16bit(
    *,
    force: bool = False,
    on_progress: Callable[[str], None] | None = None,
) -> tuple[int, int, int]:
    """预热全部 booms → booms_16bit。返回 (skipped, converted, failed)。"""
    log = on_progress or (lambda _msg: None)
    skipped = converted = failed = 0
    for wav in iter_booms_wavs():
        rel = wav.relative_to(audio_dir())
        dst = booms_16bit_path_for(wav)
        assert dst is not None
        if wav_bits_per_sample(wav) <= 16:
            log(f"跳过（已是 16-bit）: {rel}")
            skipped += 1
            continue
        if not force and is_booms_16bit_fresh(wav, dst):
            log(f"跳过（已缓存）: {rel}")
            skipped += 1
            continue
        try:
            transcode_wav_to_s16le(wav, dst)
            log(f"转码: {rel} → {dst.relative_to(audio_dir())}")
            converted += 1
        except (OSError, subprocess.CalledProcessError) as exc:
            log(f"失败: {rel} ({exc})")
            failed += 1
    return skipped, converted, failed


def _main() -> int:
    parser = argparse.ArgumentParser(description="预热 baseURL/audio/*/booms → booms_16bit")
    parser.add_argument(
        "--force",
        action="store_true",
        help="忽略已有缓存，全部重新转码",
    )
    args = parser.parse_args()
    if not which("ffmpeg"):
        print("错误：未找到 ffmpeg", file=sys.stderr)
        return 1
    print(f"baseURL/audio: {audio_dir()}")
    skipped, converted, failed = prewarm_booms_16bit(force=args.force, on_progress=print)
    print(f"完成：跳过 {skipped}，转码 {converted}，失败 {failed}")
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(_main())
