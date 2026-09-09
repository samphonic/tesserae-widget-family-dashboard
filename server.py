import os
import json
import time
import urllib.request
import urllib.error
from datetime import datetime, timedelta, date
from typing import Any, Dict, List, Optional

# WMO Weather code mapper to Phosphor bold icons and human-friendly labels
WMO_MAP = {
    0: ("ph-sun", "Clear Sky"),
    1: ("ph-cloud-sun", "Mostly Clear"),
    2: ("ph-cloud-sun", "Partly Cloudy"),
    3: ("ph-cloud", "Overcast"),
    45: ("ph-cloud-fog", "Foggy"),
    48: ("ph-cloud-fog", "Rime Fog"),
    51: ("ph-cloud-drizzle", "Light Drizzle"),
    53: ("ph-cloud-drizzle", "Drizzle"),
    55: ("ph-cloud-drizzle", "Heavy Drizzle"),
    61: ("ph-cloud-rain", "Slight Rain"),
    63: ("ph-cloud-rain", "Moderate Rain"),
    65: ("ph-cloud-rain", "Heavy Rain"),
    71: ("ph-snowflake", "Slight Snow"),
    73: ("ph-snowflake", "Moderate Snow"),
    75: ("ph-snowflake", "Heavy Snow"),
    80: ("ph-cloud-rain", "Rain Showers"),
    81: ("ph-cloud-rain", "Heavy Showers"),
    82: ("ph-cloud-rain", "Violent Showers"),
    95: ("ph-cloud-lightning", "Thunderstorm"),
    96: ("ph-cloud-lightning", "Thunderstorm & Hail"),
    99: ("ph-cloud-lightning", "Heavy Hailstorm"),
}


def _fetch_url(url: str, timeout: int = 8) -> str:
    """Standardized HTTP GET request with custom User-Agent."""
    req = urllib.request.Request(
        url,
        headers={"User-Agent": "tesserae/1.0 (+family_dashboard)"},
    )
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return resp.read().decode("utf-8", errors="replace")


def _get_weather(lat: float, lon: float, units: str, cache_dir: str) -> Dict[str, Any]:
    """Fetch forecast from Open-Meteo (cached for 15 minutes)."""
    cache_file = os.path.join(cache_dir, "weather_cache.json")
    if os.path.exists(cache_file):
        try:
            with open(cache_file, "r") as f:
                cached = json.load(f)
            if time.time() - cached.get("timestamp", 0) < 900:  # 15 min cache
                return cached["data"]
        except Exception:
            pass

    temp_unit_param = "fahrenheit" if units == "fahrenheit" else "celsius"
    unit_sym = "°F" if units == "fahrenheit" else "°C"
    url = (
        f"https://api.open-meteo.com/v1/forecast?"
        f"latitude={lat}&longitude={lon}"
        f"&current=temperature_2m,weather_code"
        f"&daily=weather_code,temperature_2m_max,temperature_2m_min"
        f"&temperature_unit={temp_unit_param}"
        f"&timezone=auto"
    )

    raw = _fetch_url(url)
    payload = json.loads(raw)

    forecast_code = payload.get("daily", {}).get("weather_code", [0])[0]
    icon, condition = WMO_MAP.get(forecast_code, ("ph-sun", "Clear"))

    data = {
        "current_temp": round(payload.get("current", {}).get("temperature_2m", 0)),
        "high": round(payload.get("daily", {}).get("temperature_2m_max", [0])[0]),
        "low": round(payload.get("daily", {}).get("temperature_2m_min", [0])[0]),
        "condition": condition,
        "icon": icon,
        "unit": unit_sym,
    }

    try:
        with open(cache_file, "w") as f:
            json.dump({"timestamp": time.time(), "data": data}, f)
    except Exception:
        pass

    return data


def _parse_ics(ics_content: str, days_ahead: int, time_format: str) -> List[Dict[str, Any]]:
    """A lightweight, zero-dependency iCalendar (RFC 5545) parser."""
    # Unfold wrapped lines in RFC 5545 (lines starting with space or tab)
    lines = []
    for raw_line in ics_content.splitlines():
        if raw_line.startswith((" ", "\t")) and lines:
            lines[-1] += raw_line[1:]
        else:
            lines.append(raw_line)

    today = date.today()
    end_date = today + timedelta(days=days_ahead)

    events: List[Dict[str, Any]] = []
    in_event = False
    cur_event: Dict[str, str] = {}

    for line in lines:
        line = line.strip()
        if line == "BEGIN:VEVENT":
            in_event = True
            cur_event = {}
            continue
        elif line == "END:VEVENT":
            in_event = False
            if "SUMMARY" in cur_event and "DTSTART" in cur_event:
                dt_str = cur_event["DTSTART"]
                summary = cur_event.get("SUMMARY", "Busy")

                # Parse date / datetime
                ev_date: Optional[date] = None
                time_str = "All Day"
                is_all_day = True
                sort_minutes = -1  # -1 guarantees all-day events appear first

                try:
                    if "T" in dt_str:
                        # e.g., 20260909T143000Z or 20260909T143000
                        clean_dt = dt_str.split("T")[0]
                        clean_time = dt_str.split("T")[1].replace("Z", "")[:4]
                        ev_date = datetime.strptime(clean_dt, "%Y%m%d").date()
                        ev_hour = int(clean_time[:2])
                        ev_min = int(clean_time[2:4])
                        is_all_day = False
                        sort_minutes = ev_hour * 60 + ev_min

                        if time_format == "24h":
                            time_str = f"{ev_hour:02d}:{ev_min:02d}"
                        else:
                            period = "AM" if ev_hour < 12 else "PM"
                            display_hour = ev_hour % 12
                            if display_hour == 0:
                                display_hour = 12
                            time_str = f"{display_hour}:{ev_min:02d} {period}"
                    else:
                        # Date only: YYYYMMDD
                        ev_date = datetime.strptime(dt_str[:8], "%Y%m%d").date()
                except Exception:
                    continue

                if ev_date and today <= ev_date <= end_date:
                    events.append({
                        "title": summary,
                        "date_iso": ev_date.isoformat(),
                        "time_str": time_str,
                        "is_all_day": is_all_day,
                        "sort_minutes": sort_minutes,
                        # Slots ready for native Google Calendar API migration:
                        "color_id": cur_event.get("COLOR_ID", "default"),
                        "icon": "ph-calendar-blank",
                    })
            continue

        if in_event and ":" in line:
            prop, _, val = line.partition(":")
            prop_name = prop.split(";")[0]
            cur_event[prop_name] = val

    # Sort events chronologically (date, then all-day first, then by time)
    events.sort(key=lambda e: (e["date_iso"], e.get("sort_minutes", -1)))
    return events


def _get_mock_events(days_ahead: int) -> List[Dict[str, Any]]:
    """Preview mock events displayed when no ICS URL is supplied."""
    today = date.today()
    return [
        {
            "title": "School Drop-off",
            "date_iso": today.isoformat(),
            "time_str": "8:15 AM",
            "is_all_day": False,
            "color_id": "1",
            "icon": "ph-backpack",
        },
        {
            "title": "Dentist Appointment",
            "date_iso": today.isoformat(),
            "time_str": "2:00 PM",
            "is_all_day": False,
            "color_id": "2",
            "icon": "ph-first-aid",
        },
        {
            "title": "Trash & Recycling Pickup",
            "date_iso": (today + timedelta(days=1)).isoformat(),
            "time_str": "All Day",
            "is_all_day": True,
            "color_id": "3",
            "icon": "ph-trash",
        },
        {
            "title": "Soccer Tournament",
            "date_iso": (today + timedelta(days=2)).isoformat(),
            "time_str": "10:00 AM",
            "is_all_day": False,
            "color_id": "1",
            "icon": "ph-trophy",
        },
    ]


def _group_events_by_day(events: List[Dict[str, Any]], days_ahead: int) -> List[Dict[str, Any]]:
    """Group flat events list into days."""
    today = date.today()
    grouped = []

    for i in range(days_ahead + 1):
        target_date = today + timedelta(days=i)
        target_iso = target_date.isoformat()

        if i == 0:
            label = "TODAY"
        elif i == 1:
            label = "TOMORROW"
        else:
            label = target_date.strftime("%A, %b %d").upper()

        day_events = [e for e in events if e["date_iso"] == target_iso]
        if day_events:
            grouped.append({
                "date_str": target_iso,
                "label": label,
                "events": day_events,
            })

    return grouped


def fetch(options: dict, settings: dict, *, ctx: dict) -> dict:
    """Tesserae widget data entrypoint."""
    data_dir = ctx.get("data_dir", "/tmp")
    os.makedirs(data_dir, exist_ok=True)

    lat = float(options.get("latitude") or 37.7749)
    lon = float(options.get("longitude") or -122.4194)
    units = options.get("units") or "fahrenheit"
    time_fmt = options.get("time_format") or "12h"
    days_ahead = int(options.get("days_ahead") or 5)
    ics_url = options.get("ics_url", "").strip()

    # 1. Fetch Weather
    try:
        weather_data = _get_weather(lat, lon, units, data_dir)
    except Exception as exc:
        weather_data = {
            "current_temp": "--",
            "high": "--",
            "low": "--",
            "condition": "Weather unavailable",
            "icon": "ph-cloud",
            "unit": "°F" if units == "fahrenheit" else "°C",
            "error": str(exc),
        }

    # 2. Fetch Calendar Events
    events: List[Dict[str, Any]] = []
    is_sample_data = False

    if ics_url:
        try:
            ics_raw = _fetch_url(ics_url)
            events = _parse_ics(ics_raw, days_ahead, time_fmt)
        except Exception as exc:
            return {"error": f"Failed to load calendar: {str(exc)}"}
    else:
        events = _get_mock_events(days_ahead)
        is_sample_data = True

    grouped_agenda = _group_events_by_day(events, days_ahead)

    # 3. Wall Clock Information
    now = datetime.now()
    return {
        "date_info": {
            "weekday": now.strftime("%A"),
            "day": str(now.day),
            "month_year": now.strftime("%B %Y"),
        },
        "weather": weather_data,
        "agenda": grouped_agenda,
        "is_sample_data": is_sample_data,
    }
