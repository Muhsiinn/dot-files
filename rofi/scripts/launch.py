#!/usr/bin/env python3
"""Anya Forger Rofi launcher.

Rofi script-mode contract:
  ROFI_RETV=0  -> print desktop applications
  ROFI_RETV=1  -> launch the selected application
  ROFI_RETV=2  -> search the typed text with Google, or with a tag:
                    -y <query>  YouTube
                    -w <query>  Wikipedia
                    -b <query>  Google Books
                    -g <query>  Google (explicit)
"""

from __future__ import annotations

import os
import re
import shlex
import shutil
import subprocess
import sys
from pathlib import Path
from urllib.parse import quote_plus

HOME = Path.home()
DEVNULL = subprocess.DEVNULL

ENGINES: dict[str, tuple[str, str]] = {
    "g": ("google", "https://www.google.com/search?q="),
    "google": ("google", "https://www.google.com/search?q="),
    "y": ("youtube", "https://www.youtube.com/results?search_query="),
    "yt": ("youtube", "https://www.youtube.com/results?search_query="),
    "youtube": ("youtube", "https://www.youtube.com/results?search_query="),
    "w": ("wiki", "https://en.wikipedia.org/w/index.php?search="),
    "wiki": ("wiki", "https://en.wikipedia.org/w/index.php?search="),
    "wikipedia": ("wiki", "https://en.wikipedia.org/w/index.php?search="),
    "b": ("books", "https://www.google.com/search?tbm=bks&q="),
    "book": ("books", "https://www.google.com/search?tbm=bks&q="),
    "books": ("books", "https://www.google.com/search?tbm=bks&q="),
}

FIELD_CODE = re.compile(r"%[a-zA-Z]")


def clean(value: str) -> str:
    """Keep one Rofi row option on one line."""
    value = value.replace("\0", " ").replace("\t", " ").replace("\x1f", " ")
    return " ".join(value.splitlines()).strip()


def trueish(value: str | None) -> bool:
    return (value or "").strip().lower() in {"1", "true", "yes"}


def localized(data: dict[str, str], key: str) -> str:
    locale = (
        os.environ.get("LC_ALL")
        or os.environ.get("LC_MESSAGES")
        or os.environ.get("LANG")
        or ""
    ).split(".")[0]
    if locale and locale != "C":
        candidates = [locale]
        if "_" in locale:
            candidates.append(locale.split("_", 1)[0])
        for candidate in candidates:
            localized_key = f"{key}[{candidate}]"
            if localized_key in data:
                return data[localized_key]
    return data.get(key, "")


def read_desktop(path: Path) -> dict[str, str]:
    data: dict[str, str] = {}
    section = ""
    try:
        with path.open(encoding="utf-8-sig", errors="replace") as stream:
            for raw_line in stream:
                line = raw_line.strip()
                if not line or line.startswith("#"):
                    continue
                if line.startswith("[") and line.endswith("]"):
                    section = line[1:-1]
                    continue
                if section != "Desktop Entry" or "=" not in line:
                    continue
                key, value = line.split("=", 1)
                data[key.strip()] = value.strip()
    except OSError:
        return {}
    return data


def desktop_dirs() -> list[Path]:
    data_home = Path(os.environ.get("XDG_DATA_HOME") or HOME / ".local" / "share")
    data_dirs = os.environ.get("XDG_DATA_DIRS") or "/usr/local/share:/usr/share"

    candidates = [
        data_home / "applications",
        HOME / ".local/share/flatpak/exports/share/applications",
        *(Path(entry) / "applications" for entry in data_dirs.split(":") if entry),
        Path("/var/lib/flatpak/exports/share/applications"),
        Path("/var/lib/snapd/desktop/applications"),
    ]

    result: list[Path] = []
    seen: set[Path] = set()
    for directory in candidates:
        try:
            resolved = directory.resolve()
        except OSError:
            continue
        if resolved in seen or not resolved.is_dir():
            continue
        seen.add(resolved)
        result.append(resolved)
    return result


def current_desktops() -> set[str]:
    value = os.environ.get("XDG_CURRENT_DESKTOP", "")
    return {part for part in value.split(":") if part}


def executable_available(command: str) -> bool:
    if "/" in command:
        return Path(command).is_file() and os.access(command, os.X_OK)
    return shutil.which(command) is not None


def app_entry(path: Path, data: dict[str, str], desktops: set[str]) -> str | None:
    if data.get("Type") != "Application":
        return None
    if trueish(data.get("NoDisplay")) or trueish(data.get("Hidden")):
        return None

    only_show_in = {part for part in data.get("OnlyShowIn", "").split(";") if part}
    if only_show_in and not (only_show_in & desktops):
        return None

    not_show_in = {part for part in data.get("NotShowIn", "").split(";") if part}
    if not_show_in & desktops:
        return None

    try_exec = data.get("TryExec", "").strip()
    if try_exec and not executable_available(try_exec):
        return None

    name = localized(data, "Name")
    command = data.get("Exec", "").strip()
    if not name or not command:
        return None

    icon = data.get("Icon", "").strip() or "application-x-executable"
    meta_parts = [
        localized(data, "GenericName"),
        data.get("Keywords", ""),
        data.get("Categories", ""),
        command,
    ]
    meta = clean(" ".join(part for part in meta_parts if part))[:800]
    info = clean(str(path))
    # Rofi row options use one NUL prefix, then unit separators between options.
    return f"{clean(name)}\0icon\x1f{clean(icon)}\x1finfo\x1f{info}\x1fmeta\x1f{meta}"


def entries() -> list[tuple[str, str]]:
    desktops = current_desktops()
    seen_ids: set[str] = set()
    apps: list[tuple[str, str]] = []

    for directory in desktop_dirs():
        try:
            paths = sorted(directory.glob("*.desktop"), key=lambda item: item.name.casefold())
        except OSError:
            continue

        for path in paths:
            if path.name in seen_ids:
                continue
            seen_ids.add(path.name)

            data = read_desktop(path)
            row = app_entry(path, data, desktops)
            if row is not None:
                apps.append((clean(localized(data, "Name")).casefold(), row))

    apps.sort(key=lambda item: item[0])
    return apps


def parse_search(text: str) -> tuple[str, str] | None:
    text = text.strip()
    if not text:
        return None

    engine = "google"
    query = text

    if text.startswith("-"):
        parts = text[1:].split(None, 1)
        if parts:
            candidate = parts[0].strip().lower().replace(":", "")
            if candidate in ENGINES:
                engine, _ = ENGINES[candidate]
                query = parts[1].strip() if len(parts) > 1 else ""

    if not query:
        return None
    return engine, query


def open_search(text: str) -> None:
    parsed = parse_search(text)
    if parsed is None:
        return

    engine, query = parsed
    _, base = ENGINES[engine]
    url = base + quote_plus(query)
    try:
        subprocess.Popen(
            ["xdg-open", url],
            stdin=DEVNULL,
            stdout=DEVNULL,
            stderr=DEVNULL,
            start_new_session=True,
        )
    except OSError:
        pass


def exec_arguments(data: dict[str, str], desktop_file: Path) -> list[str]:
    command = data.get("Exec", "").strip()
    try:
        parts = shlex.split(command)
    except ValueError:
        parts = command.split()

    name = localized(data, "Name")
    cleaned: list[str] = []
    for part in parts:
        if part in {"%f", "%F", "%u", "%U", "%i", "%c", "%k", "%d", "%D", "%n", "%N"}:
            continue
        part = part.replace("%%", "\0PERCENT\0")
        part = part.replace("%c", name)
        part = part.replace("%k", str(desktop_file))
        part = FIELD_CODE.sub("", part)
        part = part.replace("\0PERCENT\0", "%")
        if part:
            cleaned.append(part)
    return cleaned


def launch_app(desktop_file: Path) -> None:
    data = read_desktop(desktop_file)
    terminal = trueish(data.get("Terminal"))

    if not terminal:
        try:
            result = subprocess.run(
                ["gio", "launch", str(desktop_file)],
                stdin=DEVNULL,
                stdout=DEVNULL,
                stderr=DEVNULL,
                timeout=4,
                check=False,
                # Detach the launched app so it survives rofi exiting.
                start_new_session=True,
            )
            if result.returncode == 0:
                return
        except (OSError, subprocess.SubprocessError):
            pass

    arguments = exec_arguments(data, desktop_file)
    if not arguments:
        return

    if terminal:
        arguments = ["wezterm", "start", "--"] + arguments

    try:
        subprocess.Popen(
            arguments,
            cwd=str(HOME),
            stdin=DEVNULL,
            stdout=DEVNULL,
            stderr=DEVNULL,
            start_new_session=True,
        )
    except OSError:
        pass


def main() -> None:
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except AttributeError:
        pass

    return_value = os.environ.get("ROFI_RETV", "0")
    typed = sys.argv[1] if len(sys.argv) > 1 else os.environ.get("ROFI_INPUT", "")

    if return_value == "1":
        info = os.environ.get("ROFI_INFO", "").strip()
        if info:
            path = Path(info)
            if path.is_file():
                launch_app(path)
        return

    if return_value == "2":
        open_search(typed)
        return

    output = ["\0prompt\x1fApps", "\0message\x1fEnter on plain text searches Google  ·  -y YouTube  ·  -w Wikipedia  ·  -b Books"]
    output.extend(row for _, row in entries())
    sys.stdout.write("\n".join(output) + "\n")


if __name__ == "__main__":
    main()
