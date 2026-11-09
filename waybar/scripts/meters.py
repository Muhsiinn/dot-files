#!/usr/bin/env python3
"""Anya Forger caffeine and mood meters.

Commands:
  caffeine +1        increase caffeine by one
  caffeine -1        decrease caffeine by one
  caffeine 7         set caffeine to 7
  caffeine reset     reset caffeine to its default
  caffeine           show the current caffeine level
  mood +1 / -1 / 7 / reset / (no argument)

The command names are provided by symlinks in ~/.local/bin. Rofi/Waybar use
the `waybar` subcommand to receive JSON for the two custom modules.
"""

from __future__ import annotations

import fcntl
import json
import os
import re
import sys
import tempfile
from pathlib import Path

MAX_LEVEL = 10
DEFAULTS = {"caffeine": 0, "mood": 5}
LABELS = {"caffeine": "Caffeine", "mood": "Mood"}
ALIASES = {"caffine": "caffeine"}

STATE_DIR = Path(
    os.environ.get("XDG_STATE_HOME") or Path.home() / ".local" / "state"
) / "crimson-glass"
STATE_FILE = STATE_DIR / "meters.json"
LOCK_FILE = STATE_DIR / "meters.lock"

FILLED = "█"
EMPTY = "░"


def clamp(value: int) -> int:
    return max(0, min(MAX_LEVEL, value))


def load_state() -> dict[str, int]:
    try:
        data = json.loads(STATE_FILE.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        data = {}

    if not isinstance(data, dict):
        data = {}

    state: dict[str, int] = {}
    for name, default in DEFAULTS.items():
        value = data.get(name, default)
        if isinstance(value, bool) or not isinstance(value, int):
            value = default
        state[name] = clamp(value)
    return state


def save_state(state: dict[str, int]) -> None:
    STATE_DIR.mkdir(parents=True, exist_ok=True)
    descriptor, temporary = tempfile.mkstemp(prefix=".meters-", dir=STATE_DIR)
    try:
        with os.fdopen(descriptor, "w", encoding="utf-8") as stream:
            json.dump(state, stream, ensure_ascii=False)
            stream.write("\n")
        os.replace(temporary, STATE_FILE)
    except Exception:
        try:
            os.unlink(temporary)
        except OSError:
            pass
        raise


def mutate(name: str, amount: int | None = None, absolute: int | None = None) -> int:
    STATE_DIR.mkdir(parents=True, exist_ok=True)
    with LOCK_FILE.open("a+", encoding="utf-8") as lock:
        fcntl.flock(lock, fcntl.LOCK_EX)
        state = load_state()
        if absolute is not None:
            state[name] = clamp(absolute)
        else:
            state[name] = clamp(state[name] + (amount or 0))
        save_state(state)
        fcntl.flock(lock, fcntl.LOCK_UN)
        return state[name]


def bar(value: int) -> str:
    return FILLED * value + EMPTY * (MAX_LEVEL - value)


def glyph(name: str, value: int) -> str:
    if name == "caffeine":
        return "󰾪" if value == 0 else "󰅶"
    if value <= 3:
        return "󰱶"
    if value <= 7:
        return "󰱴"
    return "󰱱"


def status_line(name: str, value: int) -> str:
    return f"{LABELS[name]}: {glyph(name, value)} {bar(value)} {value}/{MAX_LEVEL}"


def waybar_json(name: str) -> None:
    value = load_state()[name]
    payload = {
        "text": f"{glyph(name, value)} {bar(value)}",
        "class": f"level-{value}",
        "tooltip": f"{LABELS[name]} · {value}/{MAX_LEVEL}\nAdjust: {name} +1 / {name} -1",
    }
    print(json.dumps(payload, ensure_ascii=False))


def show_both() -> None:
    state = load_state()
    for name in DEFAULTS:
        print(status_line(name, state[name]))


def usage() -> None:
    print(
        "Usage:\n"
        "  caffeine +1 | -1 | 0-10 | reset | (no argument)\n"
        "  mood +1 | -1 | 0-10 | reset | (no argument)\n"
        "\n"
        "Examples:\n"
        "  caffeine +1      increase caffeine by one\n"
        "  mood -1          decrease mood by one\n"
        "  caffeine 7       set caffeine to seven",
        file=sys.stderr,
    )


def meter_from_executable() -> str | None:
    name = Path(sys.argv[0]).name
    name = ALIASES.get(name, name)
    return name if name in DEFAULTS else None


def main() -> None:
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except AttributeError:
        pass

    arguments = sys.argv[1:]

    if arguments and arguments[0] == "waybar":
        if len(arguments) < 2 or arguments[1] not in DEFAULTS:
            usage()
            raise SystemExit(2)
        waybar_json(arguments[1])
        return

    meter = meter_from_executable()
    if meter is None:
        if arguments and arguments[0] in DEFAULTS:
            meter = arguments.pop(0)
        else:
            if arguments and arguments[0].lower() in {"-h", "--help", "help"}:
                usage()
            else:
                show_both()
            return

    if not arguments:
        print(status_line(meter, load_state()[meter]))
        return

    action = arguments[0].strip().lower()

    if action in {"-h", "--help", "help"}:
        usage()
        return
    if action in {"show", "status"}:
        print(status_line(meter, load_state()[meter]))
        return
    if action in {"reset", "default"}:
        value = mutate(meter, absolute=DEFAULTS[meter])
        print(status_line(meter, value))
        return
    if action in {"+", "++", "up", "inc", "increment"}:
        value = mutate(meter, amount=1)
        print(status_line(meter, value))
        return
    if action in {"-", "--", "down", "dec", "decrement"}:
        value = mutate(meter, amount=-1)
        print(status_line(meter, value))
        return
    if re.fullmatch(r"[+-]?\d+", action):
        number = int(action)
        if action.startswith(("+", "-")):
            value = mutate(meter, amount=number)
        else:
            value = mutate(meter, absolute=number)
        print(status_line(meter, value))
        return
    if action == "set" and len(arguments) > 1:
        try:
            number = int(arguments[1])
        except ValueError:
            usage()
            raise SystemExit(2)
        value = mutate(meter, absolute=number)
        print(status_line(meter, value))
        return

    usage()
    raise SystemExit(2)


if __name__ == "__main__":
    main()
