#!/usr/bin/env python3
"""Turn the Hyprland Lua keybinds into a searchable rofi list."""

from __future__ import annotations

import re
from pathlib import Path

CONFIG = Path.home() / ".config" / "hypr" / "hyprland.lua"

MODIFIERS = {
    "SUPER": "Super",
    "SHIFT": "Shift",
    "CTRL": "Ctrl",
    "CONTROL": "Ctrl",
    "ALT": "Alt",
    "ALTGR": "AltGr",
    "META": "Meta",
}

SPECIAL_KEYS = {
    "RETURN": "Enter",
    "ENTER": "Enter",
    "SPACE": "Space",
    "TAB": "Tab",
    "ESC": "Esc",
    "ESCAPE": "Esc",
    "BACKSPACE": "Backspace",
    "DELETE": "Delete",
    "SLASH": "/",
    "PERIOD": ".",
    "COMMA": ",",
    "MINUS": "-",
    "EQUAL": "=",
    "SEMICOLON": ";",
    "APOSTROPHE": "'",
    "GRAVE": "`",
    "BRACKETLEFT": "[",
    "BRACKETRIGHT": "]",
    "BACKSLASH": "\\",
    "PAGEUP": "PageUp",
    "PAGEDOWN": "PageDown",
    "HOME": "Home",
    "END": "End",
    "INSERT": "Insert",
    "PRINT": "Print",
    "XF86AudioRaiseVolume": "Volume Up",
    "XF86AudioLowerVolume": "Volume Down",
    "XF86AudioMute": "Mute",
    "XF86MonBrightnessUp": "Brightness Up",
    "XF86MonBrightnessDown": "Brightness Down",
}

DIRECTIONS = {
    "left": "left",
    "right": "right",
    "up": "up",
    "down": "down",
    "l": "left",
    "r": "right",
    "u": "up",
    "d": "down",
}


def collect_bind_bodies(source: str) -> list[str]:
    """Return the argument text of each hl.bind(...) call."""
    bodies: list[str] = []
    needle = "hl.bind("
    cursor = 0

    while True:
        start = source.find(needle, cursor)
        if start < 0:
            break

        line_start = source.rfind("\n", 0, start) + 1
        if "--" in source[line_start:start]:
            cursor = start + len(needle)
            continue

        depth = 0
        quote = ""
        escaped = False
        index = start + len(needle) - 1

        while index < len(source):
            char = source[index]
            if quote:
                if escaped:
                    escaped = False
                elif char == "\\":
                    escaped = True
                elif char == quote:
                    quote = ""
            else:
                if char in ("'", '"'):
                    quote = char
                elif char == "(":
                    depth += 1
                elif char == ")":
                    depth -= 1
                    if depth == 0:
                        bodies.append(source[start + len(needle):index])
                        cursor = index + 1
                        break
                elif char == "-" and source.startswith("--", index):
                    newline = source.find("\n", index)
                    index = len(source) if newline < 0 else newline
            index += 1
        else:
            break

    return bodies


def split_top_level(text: str) -> list[str]:
    args: list[str] = []
    start = 0
    depth = 0
    quote = ""
    escaped = False

    for index, char in enumerate(text):
        if quote:
            if escaped:
                escaped = False
            elif char == "\\":
                escaped = True
            elif char == quote:
                quote = ""
        else:
            if char in ("'", '"'):
                quote = char
            elif char in "([{":
                depth += 1
            elif char in ")]}":
                depth -= 1
            elif char == "," and depth == 0:
                args.append(text[start:index].strip())
                start = index + 1

    args.append(text[start:].strip())
    return args


def split_concat(text: str) -> list[str]:
    parts: list[str] = []
    start = 0
    depth = 0
    quote = ""
    escaped = False
    index = 0

    while index < len(text):
        char = text[index]
        if quote:
            if escaped:
                escaped = False
            elif char == "\\":
                escaped = True
            elif char == quote:
                quote = ""
        else:
            if char in ("'", '"'):
                quote = char
            elif char in "([{":
                depth += 1
            elif char in ")]}":
                depth -= 1
            elif char == "." and text.startswith("..", index) and depth == 0:
                parts.append(text[start:index].strip())
                start = index + 2
                index += 1
        index += 1

    parts.append(text[start:].strip())
    return parts


def eval_expr(expression: str, variables: dict[str, object]) -> str:
    result: list[str] = []
    for part in split_concat(expression):
        if len(part) >= 2 and part[0] == part[-1] and part[0] in ("'", '"'):
            result.append(part[1:-1])
        elif part in variables:
            result.append(str(variables[part]))
        elif part.startswith("tostring(") and part.endswith(")"):
            result.append(eval_expr(part[9:-1], variables))
        else:
            result.append(part)
    return "".join(result)


def pretty_key(key: str) -> str:
    pieces = [piece.strip() for piece in key.split("+") if piece.strip()]
    pretty: list[str] = []
    for piece in pieces:
        if piece in MODIFIERS:
            pretty.append(MODIFIERS[piece])
        elif piece in SPECIAL_KEYS:
            pretty.append(SPECIAL_KEYS[piece])
        else:
            pretty.append(piece)
    return " + ".join(pretty)


def describe(command: str, workspace: int | None = None) -> str:
    compact = " ".join(command.split())

    if "window.move" in compact and "workspace" in compact:
        return (
            f"Move window to workspace {workspace}"
            if workspace is not None
            else "Move window to another workspace"
        )
    if "window.move" in compact:
        match = re.search(r'direction\s*=\s*"([^"]+)"', compact)
        if match:
            direction = DIRECTIONS.get(match.group(1), match.group(1))
            return f"Move window {direction}"

    if "focus" in compact and "workspace" in compact:
        return (
            f"Switch to workspace {workspace}"
            if workspace is not None
            else "Switch workspace"
        )
    if "focus" in compact:
        match = re.search(r'direction\s*=\s*"([^"]+)"', compact)
        if match:
            direction = DIRECTIONS.get(match.group(1), match.group(1))
            return f"Focus {direction}"

    if "window.close" in compact:
        return "Close window"
    if "window.float" in compact:
        return "Toggle floating"
    if "window.fullscreen" in compact:
        return "Toggle fullscreen"
    if "hl.dsp.exit" in compact:
        return "Exit Hyprland"

    if "exec_cmd" in compact:
        match = re.search(r"exec_cmd\((.*)\)\s*$", compact, re.S)
        inner = match.group(1).strip() if match else compact
        if len(inner) >= 2 and inner[0] == inner[-1] and inner[0] in ("'", '"'):
            inner = inner[1:-1]

        known = {
            "terminal": "Open terminal",
            "launcher": "Open launcher / web search (-y / -w / -b)",
            "browser": "Open browser",
            "wezterm start -- yazi": "Open file manager (Yazi)",
            "~/.config/waybar/quick-settings.sh": "Open quick settings",
            "rofi -show launch": "Open launcher / web search (-y / -w / -b)",
            "rofi -show web": "Web search (Google, YouTube, Wikipedia, Books)",
            "~/.config/rofi/scripts/show-keybindings.sh": "Show keybindings",
        }
        if inner in known:
            return known[inner]
        if "grim" in inner and "slurp" in inner:
            return "Screenshot selection"
        if "quick-settings.sh" in inner:
            return "Open quick settings"
        if "wpctl" in inner and "set-mute" in inner:
            return "Toggle mute"
        if "wpctl" in inner and "5%+" in inner:
            return "Volume up"
        if "wpctl" in inner and "5%-" in inner:
            return "Volume down"
        if "brightnessctl" in inner and "5%+" in inner:
            return "Brightness up"
        if "brightnessctl" in inner and "5%-" in inner:
            return "Brightness down"
        if "rofi -show web" in inner:
            return "Web search (Google, YouTube, Wikipedia, Books)"
        if inner.startswith("~") or inner.startswith("/"):
            return f"Run {inner}"
        return f"Run {inner[:64]}"

    return "Custom action"


def main() -> None:
    source = CONFIG.read_text(encoding="utf-8")
    rows: list[tuple[str, str]] = []

    for body in collect_bind_bodies(source):
        args = split_top_level(body)
        if len(args) < 2:
            continue

        key_expression, command = args[0], args[1]

        if re.search(r"\bkey\b", key_expression) and "tostring(i)" in command:
            for workspace in range(1, 11):
                key = "0" if workspace == 10 else str(workspace)
                variables = {"mainMod": "SUPER", "key": key, "i": workspace}
                key_name = pretty_key(eval_expr(key_expression, variables))
                rows.append((key_name, describe(command, workspace)))
            continue

        variables = {"mainMod": "SUPER"}
        key_name = pretty_key(eval_expr(key_expression, variables))
        rows.append((key_name, describe(command)))

    if not rows:
        print("No keybindings found")
        return

    for key_name, description in rows:
        print(f"{key_name:<30}  {description}")


if __name__ == "__main__":
    main()
