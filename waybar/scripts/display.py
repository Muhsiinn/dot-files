#!/usr/bin/env python3
"""External display indicator and mirror/extend switcher for Waybar.

The Waybar module calls `display.py waybar`. It is silent unless at least one
external monitor is connected. Clicking the icon runs `display.py menu`, which
opens a small Rofi menu for mirror/extend.

Hyprland 0.55+ uses Lua configuration, so runtime changes go through
`hyprctl repl` rather than the legacy `hyprctl keyword monitor` parser.
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

STATE_DIR = Path(
    os.environ.get("XDG_STATE_HOME") or Path.home() / ".local" / "state"
) / "crimson-glass"
STATE_FILE = STATE_DIR / "display.json"

INTERNAL_PREFIXES = ("edp", "lvds", "dsi")
ICON_EXTEND = "󰍺"
ICON_MIRROR = "󱇽"


def run(arguments: list[str], **kwargs) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        arguments,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        **kwargs,
    )


def get_monitors() -> list[dict]:
    try:
        result = run(["hyprctl", "monitors", "all", "-j"])
        if result.returncode != 0:
            return []
        data = json.loads(result.stdout)
    except (OSError, json.JSONDecodeError):
        return []
    return data if isinstance(data, list) else []


def is_internal(monitor: dict) -> bool:
    return monitor.get("name", "").lower().startswith(INTERNAL_PREFIXES)


def display_info() -> tuple[dict | None, dict | None, list[dict]]:
    monitors = get_monitors()
    if not monitors:
        return None, None, []

    active = [monitor for monitor in monitors if not monitor.get("disabled")]
    internal = next((monitor for monitor in active if is_internal(monitor)), None)
    if internal is None:
        internal = active[0] if active else next(
            (monitor for monitor in monitors if is_internal(monitor)), None
        )

    if internal is None:
        return None, None, []

    external = [
        monitor
        for monitor in monitors
        if monitor.get("name") != internal.get("name")
        and not is_internal(monitor)
    ]
    return internal, next(iter(external), None), external


def load_state() -> dict:
    try:
        data = json.loads(STATE_FILE.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}
    return data if isinstance(data, dict) else {}


def save_state(mode: str, output: str) -> None:
    STATE_DIR.mkdir(parents=True, exist_ok=True)
    temporary = STATE_FILE.with_suffix(".tmp")
    try:
        temporary.write_text(
            json.dumps({"mode": mode, "output": output}, ensure_ascii=False) + "\n",
            encoding="utf-8",
        )
        os.replace(temporary, STATE_FILE)
    except OSError:
        try:
            temporary.unlink()
        except OSError:
            pass


def current_mode(external: dict) -> str:
    mirror_of = str(external.get("mirrorOf", "none")).strip()
    if mirror_of and mirror_of.lower() != "none":
        return "mirror"
    if external.get("disabled"):
        saved = load_state().get("mode")
        if saved in {"mirror", "extend"}:
            return saved
    return "extend"


def lua_string(value: str) -> str:
    return json.dumps(value, ensure_ascii=False)


def apply_mode(mode: str, internal: dict, external: dict) -> bool:
    output = str(external.get("name", ""))
    source = str(internal.get("name", ""))
    if not output or not source:
        return False

    if mode == "mirror":
        scale = internal.get("scale", 1.0)
        lua = (
            "hl.monitor({ "
            f"output = {lua_string(output)}, "
            'mode = "preferred", '
            'position = "auto", '
            f"scale = {scale}, "
            f"mirror = {lua_string(source)}"
            " })"
        )
    else:
        lua = (
            "hl.monitor({ "
            f"output = {lua_string(output)}, "
            'mode = "preferred", '
            'position = "auto-right", '
            "scale = 1.0, "
            'mirror = ""'
            " })"
        )

    try:
        result = run(["hyprctl", "repl", lua])
    except OSError:
        return False

    if result.returncode != 0:
        return False
    if "error" in (result.stdout + result.stderr).lower():
        return False

    save_state(mode, output)
    return True


def waybar() -> None:
    internal, external, externals = display_info()
    if internal is None or external is None:
        print(json.dumps({"text": "", "tooltip": "", "class": "hidden"}))
        return

    mode = current_mode(external)
    names = ", ".join(str(monitor.get("name", "external")) for monitor in externals)
    icon = ICON_MIRROR if mode == "mirror" else ICON_EXTEND
    tooltip = (
        f"External display · {names}\n"
        f"Layout: {mode.title()}\n"
        "Click to switch Mirror / Extend"
    )
    print(json.dumps({"text": icon, "tooltip": tooltip, "class": mode}, ensure_ascii=False))


def menu() -> None:
    internal, external, externals = display_info()
    if internal is None or external is None:
        return

    mode = current_mode(external)
    names = ", ".join(str(monitor.get("name", "external")) for monitor in externals)
    options = [
        f"{ICON_EXTEND}  Extend" + ("  ✓" if mode == "extend" else ""),
        f"{ICON_MIRROR}  Mirror" + ("  ✓" if mode == "mirror" else ""),
    ]

    try:
        result = run(
            [
                "rofi",
                "-dmenu",
                "-i",
                "-no-custom",
                "-p",
                "Display layout",
                "-mesg",
                f"External: {names}",
            ],
            input="\n".join(options) + "\n",
        )
    except OSError:
        return

    if result.returncode != 0:
        return

    choice = result.stdout.strip().lower()
    if "mirror" in choice:
        apply_mode("mirror", internal, external)
    elif "extend" in choice:
        apply_mode("extend", internal, external)


def status() -> None:
    internal, external, externals = display_info()
    if internal is None:
        print("No monitors found")
        return
    if external is None:
        print(f"Internal: {internal.get('name')} · no external display")
        return
    print(
        f"Internal: {internal.get('name')}\n"
        f"External: {', '.join(str(m.get('name')) for m in externals)}\n"
        f"Layout: {current_mode(external).title()}"
    )


def usage() -> None:
    print(
        "Usage: display.py [waybar|menu|status|mirror|extend]\n"
        "  waybar  emit the Waybar JSON indicator\n"
        "  menu    open the mirror/extend Rofi menu\n"
        "  status  print the detected layout\n"
        "  mirror  mirror the external display\n"
        "  extend  extend the desktop to the right",
        file=sys.stderr,
    )


def main() -> None:
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except AttributeError:
        pass

    action = sys.argv[1].lower() if len(sys.argv) > 1 else "waybar"

    if action == "waybar":
        waybar()
        return
    if action == "menu":
        menu()
        return
    if action == "status":
        status()
        return
    if action in {"mirror", "extend"}:
        internal, external, _ = display_info()
        if internal is not None and external is not None:
            if not apply_mode(action, internal, external):
                raise SystemExit(1)
        return
    if action in {"-h", "--help", "help"}:
        usage()
        return

    usage()
    raise SystemExit(2)


if __name__ == "__main__":
    main()
