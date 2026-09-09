#!/usr/bin/env bash
# Envato Elements 雨声分层音效批量下载（Top 15 / 关键词）
set -euo pipefail
cd "$(dirname "$0")"

if ! command -v curl >/dev/null 2>&1; then
  echo "Error: 需要 curl" >&2
  exit 1
fi

exec python3 download.py --all "$@"
