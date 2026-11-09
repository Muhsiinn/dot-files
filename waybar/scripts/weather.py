#!/usr/bin/env python3
"""Waybar weather module using Open-Meteo (no API key required).

Location is detected from the current public IP and cached for a week. To pin
it manually, create ~/.config/waybar/weather-location containing:

    48.29,14.30,Hagenberg im Muehlkreis

The weather itself is cached for ten minutes so reloading Waybar does not
hammer the API.
"""

from __future__ import annotations

import json
import os
import sys
import time
from pathlib import Path
from urllib.parse import urlencode
from urllib.request import Request, urlopen

HOME = Path.home()
CACHE_DIR = Path(os.environ.get("XDG_CACHE_HOME", HOME / ".cache")) / "waybar"
WEATHER_CACHE = CACHE_DIR / "weather.json"
LOCATION_CACHE = CACHE_DIR / "weather-location.json"
LOCATION_OVERRIDE = HOME / ".config" / "waybar" / "weather-location"

WEATHER_TTL = 10 * 60
LOCATION_TTL = 7 * 24 * 60 * 60

ICONS = {
    "sunny": chr(0xF0599),
    "night": chr(0xF0594),
    "partly": chr(0xF0595),
    "cloudy": chr(0xF0590),
    "fog": chr(0xF0591),
    "rain": chr(0xF0597),
    "pouring": chr(0xF0596),
    "snow": chr(0xF0598),
    "snow_rain": chr(0xF067F),
    "lightning": chr(0xF0593),
    "lightning_rain": chr(0xF067E),
}


def fetch_json(url: str, timeout: int = 8) -> dict:
    request = Request(
        url,
        headers={
            "User-Agent": "anya-forger-waybar/1.0",
            "Accept": "application/json",
        },
    )
    with urlopen(request, timeout=timeout) as response:
        return json.load(response)


def read_json(path: Path) -> dict | None:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None


def write_json(path: Path, value: dict) -> None:
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        temporary = path.with_name(path.name + ".tmp")
        temporary.write_text(
            json.dumps(value, ensure_ascii=False), encoding="utf-8"
        )
        os.replace(temporary, path)
    except OSError:
        pass


def clean_label(*parts: object) -> str:
    values: list[str] = []
    for part in parts:
        text = str(part).strip() if part else ""
        if text and text not in values:
            values.append(text)
    return ", ".join(values) or "Current location"


def location_from_override() -> dict | None:
    try:
        raw = LOCATION_OVERRIDE.read_text(encoding="utf-8")
    except OSError:
        return None

    line = next(
        (row.strip() for row in raw.splitlines() if row.strip() and not row.lstrip().startswith("#")),
        "",
    )
    if not line:
        return None

    parts = [part.strip() for part in line.split(",", 2)]
    try:
        latitude = float(parts[0])
        longitude = float(parts[1])
    except (IndexError, ValueError):
        return None

    label = parts[2] if len(parts) > 2 and parts[2] else "Custom location"
    return {"lat": latitude, "lon": longitude, "label": label}


def fetch_ip_location() -> dict:
    try:
        data = fetch_json("https://ipapi.co/json/")
        if not data.get("error") and data.get("latitude") is not None:
            return {
                "lat": float(data["latitude"]),
                "lon": float(data["longitude"]),
                "label": clean_label(data.get("city"), data.get("country_name")),
            }
    except (OSError, TypeError, ValueError, KeyError):
        pass

    data = fetch_json("https://ipinfo.io/json")
    try:
        latitude, longitude = (float(part) for part in data["loc"].split(",", 1))
    except (KeyError, TypeError, ValueError) as error:
        raise RuntimeError("Could not determine location") from error
    return {
        "lat": latitude,
        "lon": longitude,
        "label": clean_label(data.get("city"), data.get("region"), data.get("country")),
    }


def get_location() -> dict | None:
    override = location_from_override()
    if override:
        return override

    cached = read_json(LOCATION_CACHE)
    if cached and time.time() - cached.get("fetched_at", 0) < LOCATION_TTL:
        return cached

    try:
        location = fetch_ip_location()
        location["fetched_at"] = time.time()
        write_json(LOCATION_CACHE, location)
        return location
    except (OSError, TypeError, ValueError, KeyError, RuntimeError):
        return cached


def fetch_weather(location: dict) -> dict:
    query = urlencode(
        {
            "latitude": location["lat"],
            "longitude": location["lon"],
            "current": (
                "temperature_2m,relative_humidity_2m,apparent_temperature,"
                "is_day,precipitation,weather_code,cloud_cover,wind_speed_10m"
            ),
            "timezone": "auto",
        }
    )
    return fetch_json(f"https://api.open-meteo.com/v1/forecast?{query}")


def describe(code: int, is_day: bool) -> tuple[str, str, str]:
    if code == 0:
        return ("Clear", "clear", ICONS["sunny" if is_day else "night"])
    if code == 1:
        return ("Mainly clear", "clear", ICONS["sunny" if is_day else "night"])
    if code == 2:
        return ("Partly cloudy", "cloudy", ICONS["partly"])
    if code == 3:
        return ("Overcast", "cloudy", ICONS["cloudy"])
    if code in (45, 48):
        return ("Fog", "fog", ICONS["fog"])
    if code in (51, 53, 55):
        return ("Drizzle", "rain", ICONS["rain"])
    if code in (56, 57):
        return ("Freezing drizzle", "rain", ICONS["snow_rain"])
    if code in (61, 63):
        return ("Rain", "rain", ICONS["rain"])
    if code == 65:
        return ("Heavy rain", "rain", ICONS["pouring"])
    if code in (66, 67):
        return ("Freezing rain", "rain", ICONS["snow_rain"])
    if code in (71, 73, 75, 77):
        return ("Snow", "snow", ICONS["snow"])
    if code in (80, 81):
        return ("Showers", "rain", ICONS["rain"])
    if code == 82:
        return ("Heavy showers", "rain", ICONS["pouring"])
    if code in (85, 86):
        return ("Snow showers", "snow", ICONS["snow"])
    if code == 95:
        return ("Thunderstorm", "storm", ICONS["lightning"])
    if code in (96, 99):
        return ("Thunderstorm with hail", "storm", ICONS["lightning_rain"])
    return ("Cloudy", "cloudy", ICONS["cloudy"])


def number(value: object, digits: int = 0) -> str:
    try:
        if value is None:
            return "--"
        return f"{float(value):.{digits}f}"
    except (TypeError, ValueError):
        return "--"


def build_payload(entry: dict, stale: bool = False) -> dict:
    weather = entry.get("weather") or {}
    current = weather.get("current") or {}
    units = weather.get("current_units") or {}
    location = entry.get("location") or {}

    code_raw = current.get("weather_code")
    try:
        code = int(code_raw)
    except (TypeError, ValueError):
        code = -1
    is_day = str(current.get("is_day", 1)) not in ("0", "False", "false")

    description, condition, icon = describe(code, is_day)
    temperature = number(current.get("temperature_2m"))
    apparent = number(current.get("apparent_temperature"))
    humidity = number(current.get("relative_humidity_2m"))
    wind = number(current.get("wind_speed_10m"))
    temp_unit = units.get("temperature_2m", "°C")
    wind_unit = units.get("wind_speed_10m", "km/h")

    observed = str(current.get("time", ""))
    updated = observed[11:16] if len(observed) >= 16 else time.strftime("%H:%M")
    cached_note = " · cached" if stale else ""

    tooltip = "\n".join(
        [
            location.get("label", "Current location"),
            f"{description} · {temperature}{temp_unit} (feels {apparent}{temp_unit})",
            f"Humidity {humidity}% · Wind {wind} {wind_unit}",
            f"Updated {updated}{cached_note}",
        ]
    )
    classes = ["unavailable"] if code < 0 else [condition]
    if stale:
        classes.append("stale")

    return {
        "text": f"{icon} {temperature}°",
        "tooltip": tooltip,
        "class": " ".join(classes),
    }


def emit(payload: dict) -> None:
    print(json.dumps(payload, ensure_ascii=False), flush=True)


def unavailable() -> None:
    emit(
        {
            "text": f"{ICONS['cloudy']} --°",
            "tooltip": "Weather unavailable\nNo network connection or API error.",
            "class": "unavailable",
        }
    )


def main() -> None:
    cached = read_json(WEATHER_CACHE)
    if cached and time.time() - cached.get("fetched_at", 0) < WEATHER_TTL:
        emit(build_payload(cached))
        return

    location = get_location()
    if location is None:
        if cached:
            emit(build_payload(cached, stale=True))
        else:
            unavailable()
        return

    try:
        weather = fetch_weather(location)
        entry = {
            "fetched_at": time.time(),
            "location": location,
            "weather": weather,
        }
        write_json(WEATHER_CACHE, entry)
        emit(build_payload(entry))
    except (OSError, TypeError, ValueError, KeyError, RuntimeError):
        if cached:
            emit(build_payload(cached, stale=True))
        else:
            unavailable()


if __name__ == "__main__":
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except AttributeError:
        pass
    main()
