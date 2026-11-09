#!/usr/bin/env bash
set -euo pipefail

# Brain + neural pulse for the Waybar clock group. Every frame is the same
# width, so the centered clock never shifts while the animation runs. The
# class selects one of eight crimson shades in style.css.
brain="󰧑"
pulse=("▁" "▂" "▃" "▄" "▅" "▆" "▇" "█" "▇" "▆" "▅" "▄" "▃" "▂")
levels=(1 2 3 4 5 6 7 8 7 6 5 4 3 2)

while true; do
  for i in "${!pulse[@]}"; do
    printf '{"text":"%s %s","tooltip":"Brain activity · all systems nominal","class":"level-%s"}\n' \
      "$brain" "${pulse[i]}" "${levels[i]}"
    sleep 0.14
  done
done
