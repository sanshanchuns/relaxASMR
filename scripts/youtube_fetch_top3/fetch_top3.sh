#!/usr/bin/env bash
# 按主题系列抓取 YouTube Top3（近30天·3万+播放）并下载前300s
#
# Usage:
#   ./fetch_top3.sh --list
#   ./fetch_top3.sh --series morning_mist_lake
#   ./fetch_top3.sh --all
#   ./fetch_top3.sh --series morning_mist_lake --dry-run

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

if ! command -v yt-dlp >/dev/null 2>&1; then
  echo "Error: 需要 yt-dlp。安装: pip install -r $SCRIPT_DIR/requirements.txt" >&2
  exit 1
fi

if ! command -v ffmpeg >/dev/null 2>&1; then
  echo "Error: 需要 ffmpeg（yt-dlp 裁切片段用）" >&2
  exit 1
fi

exec python3 "$SCRIPT_DIR/fetch_top3.py" "$@"
