#!/usr/bin/env bash
# Generate YouTube metadata (youtube.md) + thumbnail for an exported MP4.
#
# Usage:
#   ./scripts/generate_youtube_material.sh output/stream_heal_3h_4k_gpu.mp4
#   ./scripts/generate_youtube_material.sh output/foo.mp4 --thumb-time 15
#   ./scripts/generate_youtube_material.sh output/foo.mp4 --thumb-title "RAIN ASMR" --thumb-subtitle "Misty forest park by the pond"

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
exec python3 "$SCRIPT_DIR/generate_youtube_material.py" "$@"
