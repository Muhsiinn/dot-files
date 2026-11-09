#!/usr/bin/env bash
set -euo pipefail

if [[ "${1:-}" == "--delayed" ]]; then
  sleep 0.15
fi

script_dir="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
theme="$HOME/.config/rofi/anya-forger.rasi"

selection="$(
  python3 "$script_dir/keybindings.py" |
    rofi -dmenu -i -p "Keybindings" \
      -mesg "Type to filter · Enter copies the binding" \
      -theme "$theme" \
      -theme-str 'window {width: 56%;} listview {lines: 18;}'
)" || exit 0

if [[ -n "$selection" ]] && command -v wl-copy >/dev/null 2>&1; then
  printf '%s\n' "$selection" | wl-copy
fi
