#!/usr/bin/env python3
"""Backend for the Anya Forger Documentation Zone panel.

Commands:
    state          -> JSON describing greeting, uptime, today's date, todos
    toggle <index> -> flip a todo's checkbox, rewrite ~/todo.md, return new state
"""

from __future__ import annotations

import json
import os
import re
import sys
import time
from pathlib import Path

TODO = Path(os.environ.get("ANYA_TODO", Path.home() / "todo.md"))

# Matches "- [ ] task", "- [] task", "- [X] - task", "* [x] task", etc.
LINE_RE = re.compile(r"^(\s*[-*]\s*)\[([ xX]?)\](\s*(?:[-:]\s*)?)(.*?)(\s*)$")

MONTHS = [
    "January", "February", "March", "April", "May", "June",
    "July", "August", "September", "October", "November", "December",
]


def split_ending(raw: str) -> tuple[str, str]:
    for ending in ("\r\n", "\n", "\r"):
        if raw.endswith(ending):
            return raw[: -len(ending)], ending
    return raw, ""


def read_raw_lines() -> list[str]:
    try:
        return TODO.read_text(encoding="utf-8").splitlines(keepends=True)
    except OSError:
        return []


def parse(lines: list[str]) -> list[dict]:
    todos = []
    for line_index, raw in enumerate(lines):
        body_line, ending = split_ending(raw)
        match = LINE_RE.match(body_line)
        if not match:
            continue
        prefix, marker, separator, text, trailing = match.groups()
        text = text.strip()
        if not text:
            continue
        todos.append(
            {
                "index": len(todos),
                "line_index": line_index,
                "prefix": prefix,
                "inner": marker,
                "separator": separator,
                "text": text,
                "trailing": trailing,
                "ending": ending,
                "done": marker.lower() == "x",
            }
        )
    return todos


def unchecked_inner(todos: list[dict]) -> str:
    """Preserve the file's own unchecked style, e.g. '[]' vs '[ ]'."""
    counts: dict[str, int] = {}
    for todo in todos:
        if not todo["done"]:
            counts[todo["inner"]] = counts.get(todo["inner"], 0) + 1
    if not counts:
        return ""
    return max(counts, key=counts.get)


def uptime_parts() -> tuple[int, int, int]:
    seconds = int(float(Path("/proc/uptime").read_text().split()[0]))
    return seconds // 86400, (seconds % 86400) // 3600, (seconds % 3600) // 60


def greeting() -> str:
    hour = time.localtime().tm_hour
    if 5 <= hour < 12:
        return "Good morning"
    if 12 <= hour < 17:
        return "Good afternoon"
    return "Good evening"


def build_state() -> dict:
    todos = parse(read_raw_lines())
    days, hours, minutes = uptime_parts()
    now = time.localtime()
    uptime = f"{days}d {hours}h {minutes}m"
    return {
        "greeting": greeting(),
        "message": f"Hallo, Anya has been working for {uptime}.",
        "uptime": uptime,
        "todos": [
            {"index": todo["index"], "text": todo["text"], "done": todo["done"]}
            for todo in todos
        ],
        "total": len(todos),
        "remaining": sum(1 for todo in todos if not todo["done"]),
        "todayDay": now.tm_mday,
        "todayMonth": now.tm_mon,
        "todayYear": now.tm_year,
        "dateLabel": time.strftime("%A, %d %B %Y", now),
        "monthName": MONTHS[now.tm_mon - 1],
    }


def toggle(index: int) -> dict:
    lines = read_raw_lines()
    todos = parse(lines)
    if index < 0 or index >= len(todos):
        raise ValueError("That task is no longer in todo.md")

    todo = todos[index]
    done = not todo["done"]
    inner = "X" if done else unchecked_inner(todos)
    lines[todo["line_index"]] = (
        f"{todo['prefix']}[{inner}]{todo['separator']}"
        f"{todo['text']}{todo['trailing']}{todo['ending']}"
    )

    temporary = TODO.with_name(TODO.name + ".tmp")
    temporary.write_text("".join(lines), encoding="utf-8")
    try:
        os.chmod(temporary, TODO.stat().st_mode)
    except OSError:
        pass
    os.replace(temporary, TODO)
    return build_state()


def main() -> int:
    command = sys.argv[1] if len(sys.argv) > 1 else "state"
    try:
        if command == "state":
            result = build_state()
        elif command == "toggle" and len(sys.argv) > 2:
            result = toggle(int(sys.argv[2]))
        else:
            result = {"error": f"Unknown command: {command}"}
    except (OSError, ValueError) as error:
        result = {"error": str(error)}
    print(json.dumps(result, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
