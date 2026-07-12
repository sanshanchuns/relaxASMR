#!/usr/bin/env bash
# 1_rain/sounds 无缝循环素材再生（见 regenerate_rain_sounds.py）
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/../.." && pwd)"
cd "$ROOT"
exec python3 -m scripts.video_analysis.regenerate_rain_sounds "$@"
