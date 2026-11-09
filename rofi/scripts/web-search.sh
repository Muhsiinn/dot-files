#!/usr/bin/env bash
set -euo pipefail

self="$HOME/.config/rofi/scripts/web-search.sh"
theme="$HOME/.config/rofi/anya-forger.rasi"

ask_and_open() {
  local prompt="$1"
  local base="$2"
  local query encoded

  query="$(
    rofi -dmenu -i -p "$prompt" \
      -mesg "Type a search and press Enter" \
      -theme "$theme" \
      -theme-str 'window {width: 44%;} listview {lines: 1;}' \
      < /dev/null
  )" || exit 0

  [[ -n "${query//[[:space:]]/}" ]] || exit 0

  encoded="$(python3 -c 'import sys, urllib.parse; print(urllib.parse.quote_plus(sys.argv[1]))' "$query")"
  xdg-open "${base}${encoded}" >/dev/null 2>&1 &
}

case "${1:-}" in
  --mode)
    sleep 0.15
    exec rofi -show web
    ;;
  --ask)
    case "${2:-google}" in
      youtube) ask_and_open "YouTube" "https://www.youtube.com/results?search_query=" ;;
      wiki) ask_and_open "Wikipedia" "https://en.wikipedia.org/w/index.php?search=" ;;
      books) ask_and_open "Books" "https://www.google.com/search?tbm=bks&q=" ;;
      *) ask_and_open "Google" "https://www.google.com/search?q=" ;;
    esac
    exit 0
    ;;
esac

if [[ "${ROFI_RETV:-0}" == "2" ]]; then
  exec env ROFI_RETV=2 python3 "$HOME/.config/rofi/scripts/launch.py" "${1:-}"
fi

if [[ "${ROFI_RETV:-0}" == "1" ]]; then
  selected="${1:-}"
  case "${selected,,}" in
    youtube) engine="youtube" ;;
    wikipedia|wiki) engine="wiki" ;;
    books) engine="books" ;;
    google) engine="google" ;;
    *) engine="${ROFI_INFO:-google}" ;;
  esac
  setsid bash -c 'sleep 0.12; exec "$1" --ask "$2"' _ "$self" "$engine" \
    >/dev/null 2>&1 &
  exit 0
fi

printf '\0prompt\x1fWeb search\n'
printf '\0message\x1fSelect an engine · plain text searches Google · tags: -y, -w, -b\n'
printf 'Google\0icon\x1fweb-browser\0info\x1fgoogle\n'
printf 'YouTube\0icon\x1fyoutube\0info\x1fyoutube\n'
printf 'Wikipedia\0icon\x1fhelp-browser\0info\x1fwiki\n'
printf 'Books\0icon\x1fx-office-document\0info\x1fbooks\n'
