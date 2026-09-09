#!/usr/bin/env bash
# One-time: allow desktop shortcut to mount NAS without an interactive sudo password.
# Run: bash scripts/setup_nas_mount_sudoers.sh
set -euo pipefail

MOUNT_SCRIPT="/home/acele/mount_e.sh"
DROP_IN="/etc/sudoers.d/relaxasmr-mount-e"

if [[ ! -x "$MOUNT_SCRIPT" ]]; then
  echo "missing executable: $MOUNT_SCRIPT" >&2
  exit 1
fi

TMP="$(mktemp)"
printf 'acele ALL=(root) NOPASSWD: %s\n' "$MOUNT_SCRIPT" >"$TMP"
echo "Will install:"
cat "$TMP"
sudo install -m 440 "$TMP" "$DROP_IN"
rm -f "$TMP"
echo "OK: $DROP_IN"
echo "Test: sudo -n $MOUNT_SCRIPT"
