#!/usr/bin/env python3
"""Small, secret-safe NetworkManager/BlueZ/PipeWire backend for Anya's system control."""

from __future__ import annotations

import json
import os
import re
import shutil
import subprocess
import sys
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path


WIFI = "wlo1"
HOTSPOT_PROFILE = "Anya Forger Hotspot"
BT_ADDRESS = re.compile(r"Device\s+([0-9A-Fa-f:]{17})\s+(.+)")
MAC_NAME = re.compile(r"^(?:[0-9A-Fa-f]{2}[:-]){5}[0-9A-Fa-f]{2}$")


def run(args: list[str], timeout: int = 8) -> str:
    try:
        result = subprocess.run(args, text=True, capture_output=True, timeout=timeout)
    except FileNotFoundError:
        raise RuntimeError(f"Required command is unavailable: {args[0]}")
    except subprocess.TimeoutExpired:
        raise RuntimeError(f"{args[0]} timed out")
    if result.returncode:
        message = result.stderr.strip() or result.stdout.strip() or f"{args[0]} failed"
        raise RuntimeError(message)
    return result.stdout.strip()


def quiet(args: list[str], timeout: int = 5) -> str:
    try:
        result = subprocess.run(args, text=True, capture_output=True, timeout=timeout)
        return result.stdout.strip() if result.returncode == 0 else ""
    except (FileNotFoundError, subprocess.TimeoutExpired):
        return ""


def nmcli_fields(output: str) -> list[list[str]]:
    rows: list[list[str]] = []
    for line in output.splitlines():
        fields, value, escaped = [], [], False
        for char in line:
            if escaped:
                value.append(char)
                escaped = False
            elif char == "\\":
                escaped = True
            elif char == ":":
                fields.append("".join(value))
                value = []
            else:
                value.append(char)
        fields.append("".join(value))
        rows.append(fields)
    return rows


def wifi_list(rescan: bool) -> list[dict]:
    command = ["nmcli", "--terse", "--escape", "yes", "--fields", "IN-USE,SSID,SECURITY,SIGNAL", "device", "wifi", "list"]
    if rescan:
        command.append("--rescan=yes")
    raw = run(command, timeout=25 if rescan else 8)
    networks = []
    for row in nmcli_fields(raw):
        if len(row) < 4 or not row[1]:
            continue
        networks.append({"inUse": row[0] == "*", "ssid": row[1], "security": row[2] or "Open", "signal": int(row[3] or 0)})
    networks.sort(key=lambda item: (not item["inUse"], -item["signal"], item["ssid"].casefold()))
    return networks


def bluetooth_devices() -> list[dict]:
    # One listing plus two cheap filters instead of a blocking `info` call per
    # device. This keeps the panel responsive with many paired devices.
    names: dict[str, str] = {}
    for line in quiet(["bluetoothctl", "devices"]).splitlines():
        match = BT_ADDRESS.match(line)
        if match:
            names[match.group(1)] = match.group(2)
    if not names:
        return []

    def listed(kind: str) -> set[str]:
        found = set()
        for line in quiet(["bluetoothctl", "devices", kind]).splitlines():
            match = BT_ADDRESS.match(line)
            if match:
                found.add(match.group(1))
        return found

    with ThreadPoolExecutor(max_workers=2) as pool:
        connected_future = pool.submit(listed, "Connected")
        paired_future = pool.submit(listed, "Paired")
        connected, paired = connected_future.result(), paired_future.result()

    devices = [
        {
            "address": address,
            "name": name,
            "connected": address in connected,
            "paired": address in paired or address in connected,
        }
        for address, name in names.items()
    ]
    # Put usable devices first, and hide unpaired scan noise whose advertised
    # name is just its MAC address (phones, watches, random BLE beacons).
    devices = [d for d in devices if d["connected"] or d["paired"] or not MAC_NAME.fullmatch(d["name"])]
    devices.sort(key=lambda d: (not d["connected"], not d["paired"], d["name"].casefold()))
    return devices


def bt_connected(address: str) -> bool:
    return "Connected: yes" in quiet(["bluetoothctl", "info", address])


def bt_wait_connected(address: str, timeout: float = 4.0) -> bool:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if bt_connected(address):
            return True
        time.sleep(0.3)
    return False


def pactl_json(kind: str) -> list[dict]:
    try:
        data = json.loads(run(["pactl", "-f", "json", "list", kind]))
    except (RuntimeError, json.JSONDecodeError):
        return []
    result = []
    for item in data:
        if kind == "sources" and (item.get("monitor_of_sink") is not None or item.get("name", "").endswith(".monitor")):
            continue
        props = item.get("properties") or {}
        result.append({
            "name": item.get("name", ""),
            "description": props.get("device.description") or item.get("description") or item.get("name", ""),
            "active": item.get("state") != "SUSPENDED",
            "muted": bool(item.get("mute", False)),
        })
    return result


def battery_status() -> str:
    for power in Path("/sys/class/power_supply").glob("*"):
        try:
            if (power / "type").read_text().strip() != "Battery":
                continue
            percent = (power / "capacity").read_text().strip()
            state_path = power / "status"
            state = state_path.read_text().strip() if state_path.exists() else ""
            return f"{percent}% battery" + (f" · {state.lower()}" if state else "")
        except OSError:
            continue
    return "No battery detected"


ANSI = re.compile(r"\x1b\[[0-9;]*m")


def plain(args: list[str], timeout: int = 5) -> str:
    """Run a command that may emit terminal colours and return clean text."""
    return ANSI.sub("", quiet(args, timeout))


def wlan_iface() -> str:
    for path in sorted(Path("/sys/class/net").glob("*")):
        if (path / "wireless").exists():
            return path.name
    return WIFI


def nm_wifi_device() -> str:
    for line in quiet(["nmcli", "-t", "-f", "DEVICE,TYPE", "device", "status"]).splitlines():
        fields = line.split(":")
        if len(fields) >= 2 and fields[1] == "wifi":
            return fields[0]
    return wlan_iface()


def network_backend() -> str:
    if quiet(["nmcli", "-g", "WIFI", "radio"]) in ("enabled", "disabled"):
        return "nm"
    if shutil.which("iwctl") and quiet(["iwctl", "--dont-ask", "station", "list"]):
        return "iwd"
    return "none"


def iwd_station() -> tuple[str, bool, bool, str]:
    iface = wlan_iface()
    device = plain(["iwctl", "--dont-ask", "device", iface, "show"])
    powered_match = re.search(r"Powered\s+(on|off)", device)
    station = plain(["iwctl", "--dont-ask", "station", iface, "show"])
    state_match = re.search(r"State\s+(\w+)", station)
    network_match = re.search(r"Connected network\s+(.+)", station)
    connected = bool(state_match and state_match.group(1) == "connected")
    ssid = network_match.group(1).strip() if connected and network_match else ""
    return iface, bool(powered_match and powered_match.group(1) == "on"), connected, ssid


def iwd_networks(rescan: bool, current: str = "") -> list[dict]:
    iface = wlan_iface()
    if rescan:
        quiet(["iwctl", "--dont-ask", "station", iface, "scan"], timeout=20)
        time.sleep(1.0)
    raw = plain(["iwctl", "--dont-ask", "station", iface, "get-networks"], timeout=15)
    lines = raw.splitlines()
    security_col = signal_col = -1
    for line in lines:
        if "Network name" in line and "Security" in line and "Signal" in line:
            security_col, signal_col = line.index("Security"), line.index("Signal")
            break
    if security_col < 0 or signal_col < 0:
        return []

    networks = []
    for line in lines:
        if len(line) <= signal_col:
            continue
        if "Network name" in line and "Security" in line:
            continue
        name = line[6:security_col].strip()
        if not name or set(name) <= set("- "):
            continue
        security = line[security_col:signal_col].strip() or "Open"
        if security.lower() == "8021x":
            security = "802.1X"
        networks.append({
            "inUse": bool(current and name == current),
            "ssid": name,
            "security": security,
            "signal": min(100, line[signal_col:].count("*") * 25),
        })
    networks.sort(key=lambda item: (not item["inUse"], -item["signal"], item["ssid"].casefold()))
    return networks


def network_status() -> dict:
    backend = network_backend()
    if backend == "nm":
        iface = nm_wifi_device()
        wifi_radio = quiet(["nmcli", "-g", "WIFI", "radio"]) == "enabled"
        connection = quiet(["nmcli", "-g", "GENERAL.CONNECTION", "device", "show", iface])
        active_connections = quiet(["nmcli", "-t", "-f", "NAME,TYPE", "connection", "show", "--active"])
        ap_capabilities = quiet(["nmcli", "-f", "WIFI-PROPERTIES.AP", "device", "show", iface])
        hotspot_active = any(line.split(":", 1)[0] == HOTSPOT_PROFILE for line in active_connections.splitlines())
        ap_supported = bool(re.search(r"WIFI-PROPERTIES\.AP:\s*yes\b", ap_capabilities))
        try:
            networks = wifi_list(False)
        except RuntimeError:
            networks = []
        return {
            "wifiEnabled": wifi_radio,
            "wifiConnected": bool(connection and connection != "--"),
            "wifiConnection": connection if connection != "--" else "",
            "wifiNetworks": networks,
            "hotspotActive": hotspot_active,
            "hotspotAvailable": ap_supported and shutil.which("dnsmasq") is not None,
            "hotspotReason": "" if shutil.which("dnsmasq") else "dnsmasq is required for NetworkManager hotspot sharing",
        }
    if backend == "iwd":
        _, powered, connected, ssid = iwd_station()
        return {
            "wifiEnabled": powered,
            "wifiConnected": connected,
            "wifiConnection": ssid,
            "wifiNetworks": iwd_networks(False, ssid),
            "hotspotActive": False,
            "hotspotAvailable": False,
            "hotspotReason": "Mobile hotspot needs NetworkManager; this system uses iwd",
        }
    return {
        "wifiEnabled": False,
        "wifiConnected": False,
        "wifiConnection": "",
        "wifiNetworks": [],
        "hotspotActive": False,
        "hotspotAvailable": False,
        "hotspotReason": "No Wi-Fi backend detected (NetworkManager or iwd)",
    }


def status() -> dict:
    # Probe everything in parallel. The old sequential version ran ~15 commands
    # back-to-back and made opening the panel feel sluggish.
    with ThreadPoolExecutor(max_workers=16) as pool:
        network_f = pool.submit(network_status)
        bluetooth_info_f = pool.submit(quiet, ["bluetoothctl", "show"])
        sinks_f = pool.submit(pactl_json, "sinks")
        sources_f = pool.submit(pactl_json, "sources")
        default_sink_f = pool.submit(quiet, ["pactl", "get-default-sink"])
        default_source_f = pool.submit(quiet, ["pactl", "get-default-source"])
        volume_f = pool.submit(quiet, ["wpctl", "get-volume", "@DEFAULT_AUDIO_SINK@"])
        input_f = pool.submit(quiet, ["wpctl", "get-volume", "@DEFAULT_AUDIO_SOURCE@"])
        brightness_f = pool.submit(quiet, ["brightnessctl", "-m"])
        theme_f = pool.submit(quiet, ["gsettings", "get", "org.gnome.desktop.interface", "color-scheme"])
        devices_f = pool.submit(bluetooth_devices)

        network = network_f.result()
        bluetooth_info = bluetooth_info_f.result()
        sinks, sources = sinks_f.result(), sources_f.result()
        default_sink = default_sink_f.result()
        default_source = default_source_f.result()
        volume_line = volume_f.result()
        input_line = input_f.result()
        brightness_line = brightness_f.result()
        theme = theme_f.result()
        bluetooth_enabled = "Powered: yes" in bluetooth_info
        bluetooth = devices_f.result() if bluetooth_enabled else []

    match = re.search(r"Volume:\s*([0-9.]+)", volume_line)
    input_match = re.search(r"Volume:\s*([0-9.]+)", input_line)
    brightness_match = re.search(r",([0-9]+)%", brightness_line)
    return {
        **network,
        "bluetoothEnabled": bluetooth_enabled,
        "bluetoothDevices": bluetooth,
        "sinks": sinks,
        "sources": sources,
        "defaultSink": default_sink,
        "defaultSource": default_source,
        "volume": min(1, float(match.group(1))) if match else 0,
        "muted": "[MUTED]" in volume_line,
        "inputVolume": min(1, float(input_match.group(1))) if input_match else 0,
        "inputMuted": "[MUTED]" in input_line,
        "brightnessAvailable": bool(brightness_match),
        "brightness": int(brightness_match.group(1)) / 100 if brightness_match else 0,
        "battery": battery_status(),
        "darkTheme": "dark" in theme,
        "notificationBackend": any(shutil.which(x) for x in ("swaync-client", "dunstctl", "makoctl")),
        "audioMixerAvailable": shutil.which("pavucontrol") is not None,
        "lockAvailable": shutil.which("hyprlock") is not None,
    }


def action(name: str, args: list[str]) -> str:
    if name == "wifi-scan":
        backend = network_backend()
        if backend == "iwd":
            _, _, _, ssid = iwd_station()
            return json.dumps({"networks": iwd_networks(True, ssid)})
        return json.dumps({"networks": wifi_list(True)})
    if name == "bt-scan":
        run(["bluetoothctl", "--timeout", "8", "scan", "on"], timeout=12)
        return "Bluetooth scan finished"
    if name == "wifi-toggle":
        backend = network_backend()
        if backend == "iwd":
            iface, powered, _, _ = iwd_station()
            run(["iwctl", "--dont-ask", "device", iface, "set-property", "Powered", "off" if powered else "on"])
            return "Wi-Fi turned " + ("off" if powered else "on")
        current = quiet(["nmcli", "-g", "WIFI", "radio"])
        run(["nmcli", "radio", "wifi", "off" if current == "enabled" else "on"])
        return "Wi-Fi turned " + ("off" if current == "enabled" else "on")
    if name == "wifi-disconnect":
        if network_backend() == "iwd":
            iface, _, _, _ = iwd_station()
            run(["iwctl", "--dont-ask", "station", iface, "disconnect"])
        else:
            run(["nmcli", "device", "disconnect", nm_wifi_device()])
        return "Wi-Fi disconnected"
    if name == "wifi-connect":
        ssid, security, password = (args + ["", "", ""])[:3]
        enterprise = "802.1X" in security.upper() or "WPA-EAP" in security.upper()
        if network_backend() == "iwd":
            if enterprise:
                raise RuntimeError(f"Enterprise Wi-Fi needs a terminal: iwctl station {wlan_iface()} connect \"{ssid}\"")
            command = ["iwctl", "--dont-ask"]
            if password:
                command += ["--passphrase", password]
            command += ["station", wlan_iface(), "connect", ssid]
            run(command, timeout=45)
            return f"Connected to {ssid}"
        if enterprise:
            return action("wifi-setup", [ssid])
        command = ["nmcli", "--wait", "30", "device", "wifi", "connect", ssid]
        if security != "Open":
            if not password:
                raise RuntimeError("Enter the Wi-Fi password to connect")
            command += ["password", password]
        run(command, timeout=35)
        return f"Connected to {ssid}"
    if name == "wifi-setup":
        if network_backend() == "iwd":
            raise RuntimeError(f"Enterprise Wi-Fi needs a terminal: iwctl station {wlan_iface()} connect \"{args[0]}\"")
        ssid = args[0]
        profile = f"Anya Wi-Fi — {ssid}"
        uuid = quiet(["nmcli", "-g", "connection.uuid", "connection", "show", "id", profile])
        if not uuid:
            run(["nmcli", "connection", "add", "type", "wifi", "ifname", "*", "con-name", profile, "ssid", ssid,
                 "wifi-sec.key-mgmt", "wpa-eap", "802-1x.eap", "peap", "802-1x.phase2-auth", "mschapv2"])
            uuid = run(["nmcli", "-g", "connection.uuid", "connection", "show", "id", profile])
        editor = shutil.which("nm-connection-editor")
        if not editor:
            raise RuntimeError("Install nm-connection-editor to configure the eduroam identity and EAP settings")

        identity = quiet(["nmcli", "-g", "802-1x.identity", "connection", "show", uuid])
        if identity:
            try:
                run(["nmcli", "--wait", "45", "connection", "up", "uuid", uuid], timeout=50)
                return f"Connected to {ssid}"
            except RuntimeError as error:
                subprocess.Popen([editor, f"--edit={uuid}"], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, start_new_session=True)
                raise RuntimeError(f"Could not connect to {ssid}: {error}. Check the institution identity, EAP method, CA certificate, and saved password in NetworkManager.") from error

        subprocess.Popen([editor, f"--edit={uuid}"], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, start_new_session=True)
        return "Enter your institution identity and EAP settings, save, then click Set up / connect again."
    if name == "bluetooth-toggle":
        enabled = "Powered: yes" in quiet(["bluetoothctl", "show"])
        run(["bluetoothctl", "power", "off" if enabled else "on"])
        return "Bluetooth turned " + ("off" if enabled else "on")
    if name in ("bt-connect", "bt-disconnect", "bt-pair"):
        address = args[0] if args else ""
        if not re.fullmatch(r"[0-9A-Fa-f:]{17}", address):
            raise RuntimeError("Invalid Bluetooth device address")
        label = args[1] if len(args) > 1 and args[1] else address
        if name == "bt-disconnect":
            run(["bluetoothctl", "disconnect", address])
            return f"Disconnected {label}"
        # A discovery run in progress can make connecting slow or flaky.
        quiet(["bluetoothctl", "scan", "off"])
        if name == "bt-pair":
            pairable = "Pairable: yes" in quiet(["bluetoothctl", "show"])
            if not pairable:
                run(["bluetoothctl", "pairable", "on"])
            try:
                run(["bluetoothctl", "--agent", "KeyboardDisplay", "--timeout", "45", "pair", address], timeout=50)
            except RuntimeError as error:
                raise RuntimeError(f"Could not pair with {label}: {error}") from error
            finally:
                if not pairable:
                    quiet(["bluetoothctl", "pairable", "off"])
        quiet(["bluetoothctl", "trust", address])
        if not bt_connected(address):
            try:
                run(["bluetoothctl", "connect", address], timeout=25)
            except RuntimeError as error:
                raise RuntimeError(f"Could not connect to {label}: {error}") from error
        if not bt_wait_connected(address):
            raise RuntimeError(f"Could not connect to {label}. Make sure it is powered on, in range, and not connected to another device.")
        return f"Connected to {label}"
    if name == "hotspot-toggle":
        if network_backend() != "nm":
            raise RuntimeError("Mobile hotspot needs NetworkManager; this system uses iwd. Use impala to start an AP.")
        active = quiet(["nmcli", "-t", "-f", "NAME", "connection", "show", "--active"]).splitlines()
        if HOTSPOT_PROFILE in active:
            run(["nmcli", "connection", "down", HOTSPOT_PROFILE])
            return "Hotspot disabled"
        state = quiet(["nmcli", "-g", "GENERAL.STATE", "device", "show", nm_wifi_device()])
        if state.startswith("100"):
            raise RuntimeError("Won't replace the active Wi-Fi connection. Switch to wired Ethernet first.")
        if not shutil.which("dnsmasq"):
            raise RuntimeError("Hotspot unavailable: install dnsmasq for NetworkManager IPv4 sharing.")
        profiles = quiet(["nmcli", "-g", "NAME", "connection", "show"]).splitlines()
        if HOTSPOT_PROFILE in profiles:
            run(["nmcli", "connection", "up", HOTSPOT_PROFILE, "ifname", nm_wifi_device()], timeout=30)
        else:
            run(["nmcli", "device", "wifi", "hotspot", "ifname", nm_wifi_device(), "con-name", HOTSPOT_PROFILE, "ssid", "AnyaForger"], timeout=30)
        return "Hotspot enabled"
    if name == "audio-sink":
        sink = args[0]
        run(["pactl", "set-default-sink", sink])
        inputs = quiet(["pactl", "list", "short", "sink-inputs"])
        for line in inputs.splitlines():
            ident = line.split()[0]
            quiet(["pactl", "move-sink-input", ident, sink])
        return "Default output changed"
    if name == "audio-source":
        run(["pactl", "set-default-source", args[0]])
        return "Default input changed"
    if name == "volume":
        value = str(max(0, min(1, float(args[0]))))
        run(["wpctl", "set-volume", "-l", "1", "@DEFAULT_AUDIO_SINK@", value])
        return "Output volume updated"
    if name == "mute":
        run(["wpctl", "set-mute", "@DEFAULT_AUDIO_SINK@", "toggle"])
        return "Output mute toggled"
    if name == "input-volume":
        run(["wpctl", "set-volume", "-l", "1", "@DEFAULT_AUDIO_SOURCE@", str(max(0, min(1, float(args[0]))))])
        return "Input volume updated"
    if name == "input-mute":
        run(["wpctl", "set-mute", "@DEFAULT_AUDIO_SOURCE@", "toggle"])
        return "Microphone mute toggled"
    if name == "brightness":
        run(["brightnessctl", "set", f"{max(1, min(100, int(float(args[0]) * 100)))}%"])
        return "Brightness updated"
    if name == "dark-theme":
        current = quiet(["gsettings", "get", "org.gnome.desktop.interface", "color-scheme"])
        run(["gsettings", "set", "org.gnome.desktop.interface", "color-scheme", "default" if "dark" in current else "prefer-dark"])
        return "GTK color scheme updated"
    if name == "open-network-settings":
        if network_backend() == "iwd":
            terminal = shutil.which("wezterm")
            if not terminal:
                raise RuntimeError("Open a terminal and run: iwctl")
            editor = shutil.which("impala")
            command = [terminal, "-e", editor] if editor else [terminal, "-e", "iwctl"]
            subprocess.Popen(command, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, start_new_session=True)
            return "Opened iwd network settings"
        subprocess.Popen(["nm-connection-editor"], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, start_new_session=True)
        return "Opened NetworkManager settings"
    if name == "open-audio-settings":
        if not shutil.which("pavucontrol"):
            raise RuntimeError("Install pavucontrol to open the full audio mixer")
        subprocess.Popen(["pavucontrol"], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, start_new_session=True)
        return "Opened audio settings"
    if name == "lock":
        if shutil.which("hyprlock"):
            subprocess.Popen(["hyprlock"], start_new_session=True)
            return "Lock screen started"
        raise RuntimeError("hyprlock is not installed")
    raise RuntimeError("Unknown control action")


def wired_connected() -> bool:
    for path in Path("/sys/class/net").glob("*"):
        name = path.name
        if name == "lo" or name.startswith(("tailscale", "docker", "veth", "br-", "virbr")) or (path / "wireless").exists():
            continue
        try:
            if (path / "operstate").read_text().strip() == "up" and (path / "carrier").read_text().strip() == "1":
                return True
        except OSError:
            continue
    return False


def waybar_network() -> dict:
    backend = network_backend()
    powered = connected = False
    ssid = ""
    if backend == "iwd":
        _, powered, connected, ssid = iwd_station()
    elif backend == "nm":
        iface = nm_wifi_device()
        powered = quiet(["nmcli", "-g", "WIFI", "radio"]) == "enabled"
        connection = quiet(["nmcli", "-g", "GENERAL.CONNECTION", "device", "show", iface])
        connected = bool(connection and connection != "--")
        ssid = connection if connected else ""

    if powered and connected:
        return {"text": f"\uf1eb  {ssid}", "tooltip": f"Wi-Fi · {ssid}\nClick for network settings", "class": "wifi"}
    if wired_connected():
        return {"text": "\uf0c1  Wired", "tooltip": "Wired connection\nClick for network settings", "class": "ethernet"}
    if powered:
        return {"text": "\uf1eb  Wi-Fi", "tooltip": "Wi-Fi ready · not connected\nClick for network settings", "class": "disconnected"}
    return {"text": "\uf05e  Offline", "tooltip": "No network connection\nClick for network settings", "class": "disconnected"}


def main() -> None:
    try:
        command = sys.argv[1] if len(sys.argv) > 1 else "status"
        if command == "waybar-network":
            try:
                payload = waybar_network()
            except Exception:
                payload = {"text": "  Offline", "tooltip": "Network status unavailable", "class": "disconnected"}
            print(json.dumps(payload, ensure_ascii=False))
            return
        if command == "status":
            payload = {"ok": True, "status": status()}
        elif command == "wifi-scan":
            # Keep scans out of status polling: scans take several seconds and
            # Quickshell consumes this top-level field.
            if network_backend() == "iwd":
                _, _, _, ssid = iwd_station()
                payload = {"ok": True, "networks": iwd_networks(True, ssid)}
            else:
                payload = {"ok": True, "networks": wifi_list(True)}
        else:
            message = action(command, sys.argv[2:])
            payload = {"ok": True, "message": message}
    except Exception as error:  # report short, actionable failures to the panel
        payload = {"ok": False, "error": str(error)}
    print(json.dumps(payload, ensure_ascii=False))
    if not payload["ok"]:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
