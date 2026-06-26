#!/usr/bin/env python3
"""从 loop 视频一键创建 Rain 子工程。

流程：探测视频 →（可选）内嵌音轨七层分析 → 首帧启发式 → 生成配方
→ 脚手架 → generate_subproject（Group ReaEQ+ReaComp · 6_life ReaVerbate）

用法（仓库根目录）：

  python3 Reaper/scripts/create_rain_subproject.py \\
    --video assets/loop_video/rain_video/MVI_6888/MVI_6888_loop_8_fade_0.5.mp4

打开 .rpp 后运行 asmr_apply_recipe.lua（铺 3h 循环/稀疏 + 轨 2 音量包络）。
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

SCRIPT_DIR = Path(__file__).resolve().parent
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))

from rain_subproject_lib import create_from_video, derive_scene_id, REPO_ROOT


def main() -> None:
    parser = argparse.ArgumentParser(
        description="从 loop 视频创建 Rain 子工程（分析 + 配方 + .rpp）",
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
        choices=("wsl_unc", "assets", "relative", "absolute"),
        default="wsl_unc",
    )
    parser.add_argument(
        "--skip-generate",
        action="store_true",
        help="只写配方/文档，不生成 .rpp",
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
    print(f"==> 子工程: {sub}")
    print(f"==> 配方:   {sub / 'scripts' / 'asmr_config.lua'}")
    print(f"==> 分析:   {sub / 'video_analysis.md'}")
    if not args.skip_generate:
        print(f"==> 工程:   {sub / f'{scene}.rpp'}")
    print()
    print("下一步：Reaper 打开 .rpp → 运行 asmr_apply_recipe.lua")
    print("  · 轨 2 长时音量包络（asmr_config vol_envelope）")
    print("  · Group 已含 ReaEQ + ReaComp · 6_life 已含 ReaVerbate")


if __name__ == "__main__":
    main()
