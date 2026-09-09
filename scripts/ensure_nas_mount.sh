#!/usr/bin/env bash
# Ensure //192.168.3.128/e is mounted at /mnt/e before GUI / tools run.
# Desktop shortcut uses bash (not zsh), so ~/.zshrc's ~/mount_e.sh never runs.
set -euo pipefail

MOUNT_POINT="/mnt/e"
TARGET="/mnt/e/自然之声/to_youtube"
MOUNT_SCRIPT="${HOME}/mount_e.sh"

already_ok() {
  mountpoint -q "$MOUNT_POINT" 2>/dev/null && [[ -d "$TARGET" ]]
}

if already_ok; then
  exit 0
fi

if [[ -x "$MOUNT_SCRIPT" ]]; then
  if sudo -n "$MOUNT_SCRIPT" 2>/dev/null; then
    :
  else
    # Fall back (may prompt); desktop/VBS usually has no TTY
    "$MOUNT_SCRIPT" 2>/dev/null || true
  fi
fi

for _ in $(seq 1 40); do
  if already_ok; then
    exit 0
  fi
  sleep 0.25
done

echo "WARN: NAS not available at $TARGET. Run once: bash /home/acele/workspace/relaxASMR/scripts/setup_nas_mount_sudoers.sh" >&2
exit 0
