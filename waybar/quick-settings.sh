#!/usr/bin/env bash
set -euo pipefail

if ! command -v qs >/dev/null 2>&1; then
  command -v rofi >/dev/null 2>&1 && rofi -e 'Quick Settings needs Quickshell. Install it with: sudo pacman -S quickshell'
  exit 0
fi

if qs ipc -c anya-headquarters call anya openPanel >/dev/null 2>&1; then
  exit 0
fi

# The session may have started before Quickshell was installed, or its panel
# may have exited. Quickshell avoids starting a second copy of the same config.
qs -c anya-headquarters --no-duplicate >/dev/null 2>&1 &
for _ in {1..12}; do
  sleep 0.15
  qs ipc -c anya-headquarters call anya openPanel >/dev/null 2>&1 && exit 0
done

command -v rofi >/dev/null 2>&1 && rofi -e "Could not start Anya's system control. Check: qs -c anya-headquarters"
exit 0
