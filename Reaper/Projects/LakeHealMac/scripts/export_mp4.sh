#!/usr/bin/env bash
exec "$(cd "$(dirname "${BASH_SOURCE[0]}")/../../../.." && pwd)/scripts/video_render/export_mp4.sh" "$@"
