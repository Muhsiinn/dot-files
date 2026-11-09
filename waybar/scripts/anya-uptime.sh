#!/bin/bash

# First argument chooses the output:
#   (none)  -> JSON for the custom/anya-uptime text module
#   image   -> "$path\n$tooltip" for the image/anya module
MODE="${1:-text}"

UPTIME=$(awk '{print int($1)}' /proc/uptime)

DAYS=$((UPTIME / 86400))
HOURS=$((UPTIME % 86400 / 3600))
MINUTES=$((UPTIME % 3600 / 60))

ASSETS="$HOME/.config/waybar/assets/anya"

if ((DAYS >= 7)); then
  IMAGE="$ASSETS/exausted.png"
  MOOD="Exhausted Anya"
elif ((DAYS >= 3)); then
  IMAGE="$ASSETS/sleepy.png"
  MOOD="Sleepy Anya"
elif ((DAYS >= 1)); then
  IMAGE="$ASSETS/normal.png"
  MOOD="Normal Anya"
else
  IMAGE="$ASSETS/happy.png"
  MOOD="Happy Anya"
fi

if [[ "$MODE" == "image" ]]; then
  printf '%s\n%s\n' "$IMAGE" "$MOOD | Uptime: ${DAYS}d ${HOURS}h ${MINUTES}m · Anya Forger Documentation Zone · click to open"
else
  echo "{\"text\":\"${DAYS}d ${HOURS}h ${MINUTES}m\", \"tooltip\":\"${MOOD} | System uptime: ${DAYS} days, ${HOURS} hours\"}"
fi
