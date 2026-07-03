#!/usr/bin/env bash
# Upload YouTube material from a subproject output/material/ folder.
#
# Usage:
#   ./scripts/video_upload/upload.sh Reaper/Projects/Rain/subprojects/MVI_6991/output/material/MVI_6991_3h_4k

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
exec python3 "$SCRIPT_DIR/__main__.py" "$@"
