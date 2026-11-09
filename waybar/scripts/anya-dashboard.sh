#!/usr/bin/env bash
set -euo pipefail

CONFIG=anya-documentation-zone

if qs ipc -c "$CONFIG" call dashboard toggle >/dev/null 2>&1; then
  exit 0
fi

if ! command -v qs >/dev/null 2>&1; then
  command -v rofi >/dev/null 2>&1 && rofi -e 'The Anya Forger Documentation Zone needs Quickshell. Install it with: sudo pacman -S quickshell'
  exit 0
fi

# First click: start the panel, then open it as soon as its IPC is ready.
qs -c "$CONFIG" --no-duplicate >/dev/null 2>&1 &
for _ in {1..30}; do
  sleep 0.1
  qs ipc -c "$CONFIG" call dashboard toggle >/dev/null 2>&1 && exit 0
done

command -v rofi >/dev/null 2>&1 && rofi -e 'Could not start the Anya Forger Documentation Zone. Check: qs -c anya-documentation-zone'
exit 0
