#!/usr/bin/env bash
# Generate YouTube metadata (youtube.md) + thumbnail for an exported MP4.
#
# Usage:
#   ./scripts/video_export/generate_youtube_material.sh material/stream_heal_3h_4k_gpu.mp4
#   ./scripts/video_export/generate_youtube_material.sh material/foo.mp4 --thumb-time 15

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
exec python3 "$SCRIPT_DIR/generate_youtube_material.py" "$@"
