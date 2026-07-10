#!/usr/bin/env python3
"""从 loop 视频一键创建 Rain 子工程。

流程：探测视频 → 首帧启发式 → 写入 JSON 配置 → 生成 `.rpp`

用法（仓库根目录）：

  python3 Reaper/scripts/create_rain_subproject.py \\
    --video assets/loop_video/rain_video/MVI_6888/MVI_6888_loop_8_fade_0.5.mp4

打开 .rpp 后：asmr_loop_track → asmr_vol_envelope（1_rain）→ asmr_scatter_track。

媒体路径默认 `--media-mode auto`：按运行环境自动选择 absolute / wsl_unc（见 README）。
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

SCRIPT_DIR = Path(__file__).resolve().parent
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))

from rain_subproject_lib import create_from_video, derive_scene_id, REPO_ROOT
from scene_config import scene_config_path


def main() -> None:
    parser = argparse.ArgumentParser(
        description="从 loop 视频创建 Rain 子工程（分析 + JSON 配置 + .rpp）",
    )
    parser.add_argument(
        "--video",
        type=Path,
        required=True,
        help="循环 MP4（路径或 assets/loop_video/rain_video/<ID>/...）",
    )
    parser.add_argument(
        "--scene",
        help="场景 ID（默认从路径推断 MVI_xxxx）",
    )
    parser.add_argument(
        "--duration-hours",
        type=float,
        default=3,
        help="成片时长（默认 3）",
    )
    parser.add_argument(
        "--media-mode",
        choices=("auto", "wsl_unc", "assets", "relative", "absolute"),
        default="auto",
    )
    parser.add_argument(
        "--skip-generate",
        action="store_true",
        help="只写配置/文档，不生成 .rpp",
    )
    args = parser.parse_args()

    video = args.video
    if not video.is_absolute():
        video = (Path.cwd() / video).resolve()
    if not video.is_file():
        alt = REPO_ROOT / args.video
        if alt.is_file():
            video = alt.resolve()
        else:
            print(f"Error: 找不到视频 {args.video}", file=sys.stderr)
            sys.exit(1)

    scene = derive_scene_id(video, args.scene)
    sub = create_from_video(
        video,
        scene_id=scene,
        duration_hours=args.duration_hours,
        media_mode=args.media_mode,
        skip_generate=args.skip_generate,
    )

    print(f"==> 场景 ID: {scene}")
    print(f"==> Rain 工程目录: {sub}")
    print(f"==> 配置:   {scene_config_path(scene)}")
    print(f"==> 分析:   baseURL/material/{scene}_video_analysis.md")
    if not args.skip_generate:
        print(f"==> 工程:   {sub / f'{scene}.rpp'}")
    print()
    scripts = sub / "scripts"
    print("下一步（Reaper）：")
    print(f"  1. 打开 {sub / f'{scene}.rpp'}")
    print("  2. asmr_loop_track.lua — 循环层")
    print("  3. asmr_vol_envelope.lua — 1_rain 长时包络")
    print("  4. asmr_scatter_track.lua — 稀疏层逐轨散布")
    print(f"     脚本目录: {scripts}")


if __name__ == "__main__":
    main()
