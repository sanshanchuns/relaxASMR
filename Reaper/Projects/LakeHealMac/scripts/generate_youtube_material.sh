#!/usr/bin/env bash
# Generate YouTube metadata (youtube.md) + thumbnail for an exported MP4.
#
# Usage:
#   ./scripts/generate_youtube_material.sh "output/LakeHealMac_2026-06-17 16_49_07.mp4"
#   ./scripts/generate_youtube_material.sh output/foo.mp4 --thumb-time 15

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
exec python3 "$SCRIPT_DIR/generate_youtube_material.py" "$@"
