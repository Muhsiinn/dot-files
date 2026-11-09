#!/usr/bin/env bash
set -uo pipefail

# Start one awww daemon per user session and restore the existing wallpaper.
image="/home/anya/Downloads/megan_fox_boohoo_girl_model_is_posing_for_a_photo_standing_in_red_background_wearing_black_dress_4k_hd_girls.jpg"
runtime_dir="${XDG_RUNTIME_DIR:-/tmp}"
log_file="$runtime_dir/awww-daemon.log"

command -v awww >/dev/null 2>&1 || exit 0
[[ -r "$image" ]] || {
    printf 'awww startup: wallpaper image is missing: %s\n' "$image" >>"$log_file"
    exit 0
}

if ! pgrep -u "$UID" -x awww-daemon >/dev/null 2>&1; then
    (awww-daemon --quiet >>"$log_file" 2>&1 &)
fi

# Wait briefly for the Wayland socket before sending the wallpaper command.
for _ in {1..50}; do
    if awww query >/dev/null 2>&1; then
        awww img --transition-type fade --transition-duration 1.2 "$image" >>"$log_file" 2>&1
        exit $?
    fi
    sleep 0.1
done

printf 'awww startup: daemon did not become ready within 5 seconds\n' >>"$log_file"
exit 0
