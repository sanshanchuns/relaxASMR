#!/usr/bin/env python3
"""Wrapper for Real-ESRGAN image / video upscaling (local install).

Examples:
  ./upscale.sh video.mp4                          # → video_4k.mp4 (same dir)
  ./upscale.sh video.mp4 -o /path/4k_SR.mp4 -s 3
  ./upscale.sh cover.png -s 2 -o upscaled/
  ./upscale.sh assets/*.png -o upscaled/ -s 4

Env:
  REAL_ESRGAN_HOME  default: /home/leo/workspace/Real-ESRGAN
"""

from __future__ import annotations

import argparse
import os
import shutil
import subprocess
import sys
from pathlib import Path

SCRIPT_DIR = Path(__file__).resolve().parent
DEFAULT_ESRGAN_HOME = Path("/home/leo/workspace/Real-ESRGAN")

IMAGE_EXT = {".png", ".jpg", ".jpeg", ".webp", ".bmp", ".tif", ".tiff"}
VIDEO_EXT = {".mp4", ".mov", ".mkv", ".webm", ".avi", ".flv", ".m4v"}


def esrgan_home() -> Path:
    return Path(os.environ.get("REAL_ESRGAN_HOME", DEFAULT_ESRGAN_HOME)).expanduser().resolve()


def is_video(path: Path) -> bool:
    return path.suffix.lower() in VIDEO_EXT


def is_image(path: Path) -> bool:
    return path.suffix.lower() in IMAGE_EXT


def resolve_paths(
    input_path: Path,
    output: Path | None,
    suffix: str,
) -> tuple[Path, Path | None, str]:
    """Return (output_dir, final_file_or_none, suffix)."""
    if output is None:
        return input_path.parent, None, suffix

    output = output.expanduser()
    if output.suffix.lower() in IMAGE_EXT | VIDEO_EXT:
        output.parent.mkdir(parents=True, exist_ok=True)
        return output.parent, output.resolve(), suffix

    output.mkdir(parents=True, exist_ok=True)
    return output.resolve(), None, suffix


def run_cmd(cmd: list[str], cwd: Path) -> None:
    print("→", " ".join(cmd), file=sys.stderr)
    subprocess.run(cmd, cwd=cwd, check=True)


def upscale_one(
    input_path: Path,
    *,
    home: Path,
    output: Path | None,
    model: str,
    scale: float,
    tile: int,
    suffix: str,
    ext: str,
    fp32: bool,
    face_enhance: bool,
    force_mode: str | None,
) -> Path:
    input_path = input_path.expanduser().resolve()
    if not input_path.is_file():
        raise SystemExit(f"Input not found: {input_path}")

    video = force_mode == "video" or (force_mode != "image" and is_video(input_path))
    if not video and not is_image(input_path):
        raise SystemExit(f"Unsupported extension: {input_path.suffix}")

    out_dir, final_path, suffix = resolve_paths(input_path, output, suffix)
    stem = input_path.stem

    args_list = [
        "-i",
        str(input_path),
        "-o",
        str(out_dir),
        "-n",
        model,
        "-s",
        str(scale),
        "-t",
        str(tile),
        "--suffix",
        suffix,
    ]
    if fp32:
        args_list.append("--fp32")
    if face_enhance:
        args_list.append("--face_enhance")

    if video:
        script = home / "inference_realesrgan_video.py"
        run_cmd([sys.executable, str(script), *args_list], home)
        produced = out_dir / f"{stem}_{suffix}.mp4"
    else:
        script = home / "inference_realesrgan.py"
        args_list.extend(["--ext", ext])
        run_cmd([sys.executable, str(script), *args_list], home)
        out_ext = ext if ext != "auto" else input_path.suffix.lstrip(".") or "png"
        produced = out_dir / f"{stem}_{suffix}.{out_ext}"

    if not produced.is_file():
        raise SystemExit(f"Expected output missing: {produced}")

    if final_path and produced.resolve() != final_path.resolve():
        final_path.parent.mkdir(parents=True, exist_ok=True)
        shutil.move(str(produced), str(final_path))
        produced = final_path

    print(produced)
    return produced


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Upscale image or video via local Real-ESRGAN.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__,
    )
    parser.add_argument("input", nargs="+", help="Input file(s)")
    parser.add_argument(
        "-o",
        "--output",
        type=Path,
        default=None,
        help="Output file or directory (default: same dir as input, suffix _4k)",
    )
    parser.add_argument(
        "-n",
        "--model",
        default="RealESRGAN_x4plus",
        help="Model name (default: RealESRGAN_x4plus)",
    )
    parser.add_argument(
        "-s",
        "--scale",
        type=float,
        default=None,
        help="Outscale (default: 3 for video, 4 for image)",
    )
    parser.add_argument(
        "-t",
        "--tile",
        type=int,
        default=512,
        help="Tile size, 0=off (default: 512)",
    )
    parser.add_argument(
        "--suffix",
        default="4k",
        help="Output suffix before extension (default: 4k)",
    )
    parser.add_argument(
        "--ext",
        default="auto",
        choices=["auto", "png", "jpg"],
        help="Image output format (default: auto)",
    )
    parser.add_argument("--fp32", action="store_true", help="Use fp32 (fix half-precision errors)")
    parser.add_argument("--face-enhance", action="store_true", help="GFPGAN face enhance")
    parser.add_argument("--image", action="store_true", help="Force image pipeline")
    parser.add_argument("--video", action="store_true", help="Force video pipeline")
    args = parser.parse_args()

    if args.image and args.video:
        raise SystemExit("Use only one of --image / --video")

    home = esrgan_home()
    if not home.is_dir():
        raise SystemExit(f"REAL_ESRGAN_HOME not found: {home}")
    for name in ("inference_realesrgan.py", "inference_realesrgan_video.py"):
        if not (home / name).is_file():
            raise SystemExit(f"Missing {home / name}")

    force_mode = "image" if args.image else ("video" if args.video else None)
    inputs = [Path(p) for p in args.input]
    multi = len(inputs) > 1

    if multi and args.output and args.output.suffix.lower() in IMAGE_EXT | VIDEO_EXT:
        raise SystemExit("Batch input requires -o to be a directory")

    last: Path | None = None
    for i, inp in enumerate(inputs):
        out = args.output
        if multi and out is not None and out.suffix.lower() not in IMAGE_EXT | VIDEO_EXT:
            pass  # directory for all
        elif multi:
            out = None

        scale = args.scale
        if scale is None:
            scale = 3.0 if (force_mode == "video" or is_video(inp)) else 4.0

        last = upscale_one(
            inp,
            home=home,
            output=out,
            model=args.model,
            scale=scale,
            tile=args.tile,
            suffix=args.suffix,
            ext=args.ext,
            fp32=args.fp32,
            face_enhance=args.face_enhance,
            force_mode=force_mode,
        )

    if last and len(inputs) == 1:
        return
    if last:
        print(f"Done: {len(inputs)} file(s)", file=sys.stderr)


if __name__ == "__main__":
    main()
