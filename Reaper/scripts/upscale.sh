#!/usr/bin/env bash
# Real-ESRGAN wrapper — image / video super-resolution
#
#   ./upscale.sh INPUT [OUTPUT] [options]
#
# Examples:
#   ./upscale.sh /mnt/c/Users/acele/Downloads/720p.mp4 -o /mnt/c/Users/acele/Downloads/4k_SR.mp4 -s 3
#   ./upscale.sh ../../VisualDesign/forest/assets/CN-299_duanqiao_medium_rain_day_v1.png -s 2
#   ./upscale.sh loop.mp4 -s 3 -t 512 --suffix 4k
#
# Env: REAL_ESRGAN_HOME (default: /home/leo/workspace/Real-ESRGAN)

set -euo pipefail
DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
exec python3 "$DIR/upscale.py" "$@"
