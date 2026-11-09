#!/usr/bin/env python3
"""Anya's infiltration watcher.

Watches for new external displays, Wi-Fi connections, and Bluetooth devices,
then announces each one through the Anya notification daemon:

    Anya successfully infiltrated <device> :)

The initial state is seeded so logging in does not spam notifications for
devices that were already connected.
"""

from __future__ import annotations

import fcntl
import json
import os
import re
import shutil
import subprocess
import sys
import time
from pathlib import Path

STATE_DIR = Path(
    os.environ.get("XDG_STATE_HOME") or Path.home() / ".local" / "state"
) / "anya"
LOCK_FILE = STATE_DIR / "infiltrations.lock"
LOG_FILE = STATE_DIR / "infiltrations.log"

ICON = Path.home() / ".config/waybar/assets/anya/happy.png"
APP_NAME = "Anya Forger"
TITLE = "ANYA // INFILTRATION COMPLETE"
POLL_SECONDS = 2.5
INTERNAL_PREFIXES = ("edp", "lvds", "dsi")
ANSI = re.compile(r"\x1b\[[0-9;]*m")


def run(arguments: list[str], timeout: int = 5) -> str:
    """Run a command and return clean stdout, or an empty string on failure."""
    try:
        result = subprocess.run(
            arguments,
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.DEVNULL,
            timeout=timeout,
        )
    except (OSError, subprocess.TimeoutExpired):
        return ""
    if result.returncode != 0:
        return ""
    return ANSI.sub("", result.stdout)


def log(message: str) -> None:
    try:
        STATE_DIR.mkdir(parents=True, exist_ok=True)
        with LOG_FILE.open("a", encoding="utf-8") as handle:
            handle.write(f"{time.strftime('%Y-%m-%d %H:%M:%S')} {message}\n")
    except OSError:
        pass


def notify(device: str) -> None:
    device = device.strip()
    if not device:
        return
    if shutil.which("notify-send") is None:
        log("notify-send is not installed")
        return
    result = subprocess.run(
        [
            "notify-send",
            "--app-name",
            APP_NAME,
            "--icon",
            str(ICON),
            "--expire-time",
            "7000",
            "--urgency",
            "normal",
            TITLE,
            f"Anya successfully infiltrated {device} :)",
        ],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        timeout=5,
    )
    if result.returncode != 0:
        log(f"notify-send failed for {device!r}")


def external_displays() -> set[str]:
    raw = run(["hyprctl", "monitors", "all", "-j"])
    try:
        monitors = json.loads(raw)
    except (json.JSONDecodeError, TypeError):
        return set()
    if not isinstance(monitors, list):
        return set()
    names: set[str] = set()
    for monitor in monitors:
        name = str(monitor.get("name", ""))
        if name and not name.lower().startswith(INTERNAL_PREFIXES):
            names.add(name)
    return names


def wlan_iface() -> str:
    for path in sorted(Path("/sys/class/net").glob("*")):
        if (path / "wireless").exists():
            return path.name
    return ""


def network_backend() -> str:
    radio = run(["nmcli", "-g", "WIFI", "radio"])
    if radio in ("enabled", "disabled"):
        return "nm"
    if shutil.which("iwctl") and run(["iwctl", "--dont-ask", "station", "list"]):
        return "iwd"
    return "none"


def wifi_name() -> str:
    backend = network_backend()
    if backend == "nm":
        device = ""
        for line in run(["nmcli", "-t", "-f", "DEVICE,TYPE", "device", "status"]).splitlines():
            fields = line.split(":")
            if len(fields) >= 2 and fields[1] == "wifi":
                device = fields[0]
                break
        if not device:
            return ""
        state = run(["nmcli", "-g", "GENERAL.STATE", "device", "show", device])
        if not state.startswith("100"):
            return ""
        active = run(["nmcli", "-t", "-f", "ACTIVE,SSID", "device", "wifi", "list"])
        for line in active.splitlines():
            if line.startswith("yes:"):
                ssid = line[4:].replace("\\:", ":").replace("\\\\", "\\")
                if ssid:
                    return ssid
        connection = run(["nmcli", "-g", "GENERAL.CONNECTION", "device", "show", device])
        if connection.startswith("Anya Wi-Fi — "):
            return connection.split(" — ", 1)[1]
        return connection

    if backend == "iwd":
        iface = wlan_iface()
        if not iface:
            return ""
        station = run(["iwctl", "--dont-ask", "station", iface, "show"])
        state = re.search(r"State\s+(\w+)", station)
        if not state or state.group(1) != "connected":
            return ""
        network = re.search(r"Connected network\s+(.+)", station)
        return network.group(1).strip() if network else ""

    return ""


def bluetooth_devices() -> set[str]:
    devices: set[str] = set()
    for line in run(["bluetoothctl", "devices", "Connected"]).splitlines():
        parts = line.split(" ", 2)
        if len(parts) >= 3 and parts[0] == "Device":
            name = parts[2].strip()
            if name:
                devices.add(name)
    return devices


def acquire_lock():
    STATE_DIR.mkdir(parents=True, exist_ok=True)
    handle = LOCK_FILE.open("w", encoding="utf-8")
    try:
        fcntl.flock(handle, fcntl.LOCK_EX | fcntl.LOCK_NB)
    except BlockingIOError:
        handle.close()
        return None
    return handle


def main() -> int:
    lock = acquire_lock()
    if lock is None:
        return 0

    # Let the compositor and notification server settle after login.
    time.sleep(1.5)

    displays = external_displays()
    wifi = wifi_name()
    bluetooth = bluetooth_devices()
    log(f"seeded displays={sorted(displays)} wifi={wifi!r} bluetooth={sorted(bluetooth)}")

    while True:
        time.sleep(POLL_SECONDS)

        current_displays = external_displays()
        for name in sorted(current_displays - displays):
            notify(name)
        displays = current_displays

        current_wifi = wifi_name()
        if current_wifi and current_wifi != wifi:
            notify(current_wifi)
        wifi = current_wifi

        current_bluetooth = bluetooth_devices()
        for name in sorted(current_bluetooth - bluetooth):
            notify(name)
        bluetooth = current_bluetooth


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except KeyboardInterrupt:
        raise SystemExit(0)
