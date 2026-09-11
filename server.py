import os
import json
import time
import urllib.request
import urllib.error
from datetime import datetime, timedelta, date, timezone
from typing import Any, Dict, List, Optional
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

try:
    from google.oauth2 import service_account
    from googleapiclient.discovery import build
    HAS_GOOGLE_CLIENT = True
except ImportError:
    HAS_GOOGLE_CLIENT = False

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

def _resolve_local_tz() -> ZoneInfo:
    """Lifted from Calendar, Schedule"""
    try:
        from app.tz_resolve import app_timezone

        resolved = app_timezone()
        if isinstance(resolved, ZoneInfo):
            return resolved
        key = getattr(resolved, "key", None)
        if isinstance(key, str) and key:
            return ZoneInfo(key)
    except Exception:
        pass
    try:
        store = current_app.config.get("SETTINGS_STORE")
        raw = ""
        if store is not None:
            raw = str(store.get_section("app").get("timezone") or "").strip()
        if not raw or raw.lower() == "system":
            return ZoneInfo("UTC")
        return ZoneInfo(raw)
    except (ZoneInfoNotFoundError, Exception):
        return ZoneInfo("UTC")

def _resolve_tesserae_environment(options: dict, ctx: dict):
    """
    Extracts latitude, longitude, and timezone from widget options,
    ctx fallbacks, or Flask's app settings.
    """
    app_settings = {}
    try:
        from flask import current_app
        if current_app:
            app_settings = (
                current_app.config.get("SETTINGS", {}).get("app", {})
                or current_app.config.get("APP_SETTINGS", {})
                or {}
            )
    except Exception:
        pass

    # 1. Resolve Latitude & Longitude
    lat = options.get("latitude") or ctx.get("home_lat") or ctx.get("latitude") or app_settings.get("latitude")
    lon = options.get("longitude") or ctx.get("home_lon") or ctx.get("longitude") or app_settings.get("longitude")

    lat = float(lat) if lat is not None else 37.7749
    lon = float(lon) if lon is not None else -122.4194

    # 2. Resolve Timezone
    tz_name = (
        options.get("timezone")
        or ctx.get("timezone")
        or ctx.get("tz")
        or app_settings.get("timezone")
    )

    target_tz = None
    if tz_name:
        try:
            target_tz = zoneinfo.ZoneInfo(str(tz_name).strip())
        except Exception:
            pass

    # Fallback to local server timezone
    if target_tz is None:
        target_tz = datetime.now().astimezone().tzinfo or timezone.utc

    return lat, lon, _resolve_local_tz(), (str(tz_name) if tz_name else "auto")

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

def _parse_icon_map(mapping_text: str) -> Dict[str, str]:
    mapping = {}
    if not mapping_text:
        return mapping
    for line in mapping_text.splitlines():
        line = line.strip()
        if "=" in line:
            cid, _, icon = line.partition("=")
            # Store lowercase so hexes (#FF2968) and CSS names (Turquoise) match case-insensitively
            mapping[cid.strip().lower()] = icon.strip()
    return mapping


def _format_time_parts(dt: datetime, time_fmt: str):
    ev_hour = dt.hour
    ev_min = dt.minute
    if time_fmt == "24h":
        return f"{ev_hour:02d}:{ev_min:02d}", f"{ev_hour:02d}", f"{ev_min:02d}", ""
    else:
        period = "AM" if ev_hour < 12 else "PM"
        display_hour = ev_hour % 12 or 12
        return f"{display_hour}:{ev_min:02d} {period}", str(display_hour), f"{ev_min:02d}", period

def _fetch_google_calendar_events(
    credentials_raw: str,
    calendar_ids_str: str,
    icon_map: Dict[str, str],
    days_ahead: int,
    time_fmt: str,
    target_tz: Any
) -> List[Dict[str, Any]]:
    """Fetches and deduplicates events across multiple Google Calendars via the REST API."""
    if not HAS_GOOGLE_CLIENT:
        raise RuntimeError("Missing google client libraries. Run: pip install google-api-python-client google-auth")

    # 1. Authorize via pasted JSON string or file path
    scopes = ["https://www.googleapis.com/auth/calendar.events"]
    creds_str = credentials_raw.strip()
    if creds_str.startswith("{"):
        creds_info = json.loads(creds_str)
        credentials = service_account.Credentials.from_service_account_info(creds_info, scopes=scopes)
    else:
        credentials = service_account.Credentials.from_service_account_file(creds_str, scopes=scopes)

    service = build("calendar", "v3", credentials=credentials, cache_discovery=False)

    # 2. Set boundary times
    now_local = datetime.now(target_tz)
    fetch_start = now_local.replace(hour=0, minute=0, second=0, microsecond=0).isoformat()
    fetch_end = (now_local + timedelta(days=days_ahead)).replace(hour=23, minute=59, second=59).isoformat()

    cal_ids = [c.strip() for c in calendar_ids_str.split(",") if c.strip()]
    if not cal_ids:
        cal_ids = ["primary"]

    events = []
    seen_ids = set()
    debug_raw_items = []
    debug_raw_items.append({"target_tz":str(target_tz)})

    # 3. Pull events from each calendar
    for cal_id in cal_ids:
        list_kwargs = {
            "calendarId": cal_id,
            "timeMin": fetch_start,
            "timeMax": fetch_end,
            "singleEvents": True,
            "orderBy": "startTime",
            "eventLabelVersion": 1,  # Enables the new eventLabelId palette
        }
        debug_raw_items.append({"starting":cal_id, "kwargs":list_kwargs})
        try:
            try:
                res = service.events().list(**list_kwargs).execute()
            except TypeError:
                # Fallback if local discovery doc schema lacks the eventLabelVersion argument
                del list_kwargs["eventLabelVersion"]
                res = service.events().list(**list_kwargs).execute()
        except Exception as exc:
            debug_raw_items.append({"error_cal":cal_id,"exception":str(exc)})
            continue
        
        items = res.get("items", [])
        debug_raw_items.append({"items":items})
        for item in items:
            if len(debug_raw_items) < 5:
                debug_raw_items.append({
                    "summary": item.get("summary"),
                    "colorId": item.get("colorId"),
                    "eventLabelId": item.get("eventLabelId"),
                    "keys": list(item.keys())
                })

            event_id = item.get("id")
            if event_id in seen_ids:
                continue
            seen_ids.add(event_id)

            summary = item.get("summary", "(No Title)")
            start = item.get("start", {})
            end = item.get("end", {})
            
            # Check the new eventLabelId first, then fall back to legacy colorId
            color_key = str(item.get("eventLabelId") or item.get("colorId") or cal_id or "").strip()
            icon = icon_map.get(color_key.lower(), "ph-calendar-blank")

            if "dateTime" in start:
                # Timed event
                dt_start = datetime.fromisoformat(start["dateTime"]).astimezone(target_tz)
                time_str, time_hr, time_min, time_period = _format_time_parts(dt_start, time_fmt)
                ev_date = dt_start.date()
                is_all_day = False
                sort_minutes = dt_start.hour * 60 + dt_start.minute

                time_end_str = ""
                if "dateTime" in end:
                    dt_end = datetime.fromisoformat(end["dateTime"]).astimezone(target_tz)
                    time_end_str, _, _, _ = _format_time_parts(dt_end, time_fmt)
            else:
                # All-day event (YYYY-MM-DD)
                ev_date = datetime.strptime(start.get("date")[:10], "%Y-%m-%d").date()
                time_str, time_hr, time_min, time_period = "All Day", "", "", ""
                time_end_str = ""
                is_all_day = True
                sort_minutes = -1

            events.append({
                "title": summary,
                "date_iso": ev_date.isoformat(),
                "time_str": time_str,
                "time_hr": time_hr,
                "time_min": time_min,
                "time_period": time_period,
                "time_end_str": time_end_str,
                "is_all_day": is_all_day,
                "sort_minutes": sort_minutes,
                "color_id": color_key,
                "icon": icon,
            })

    events.sort(key=lambda e: (e["date_iso"], e.get("sort_minutes", -1)))
    return events, {"sample_events": debug_raw_items}

def _parse_ics(ics_content: str, days_ahead: int, time_format: str, target_tz: Any, icon_map) -> List[Dict[str, Any]]:
    """A lightweight, zero-dependency iCalendar (RFC 5545) parser."""
    # Unfold wrapped lines in RFC 5545 (lines starting with space or tab)
    lines = []
    for raw_line in ics_content.splitlines():
        if raw_line.startswith((" ", "\t")) and lines:
            lines[-1] += raw_line[1:]
        else:
            lines.append(raw_line)

    now_local = datetime.now(target_tz)
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

                ev_date: Optional[date] = None
                time_str, time_hr, time_min, time_period, time_end_str = "All Day", "", "", "", ""
                is_all_day = True
                sort_minutes = -1

                try:
                    if "T" in dt_str:
                        clean_dt = dt_str.replace("-", "").replace(":", "")
                        date_part, time_part = clean_dt.split("T")
                        is_utc = time_part.endswith("Z")
                        time_part = time_part.replace("Z", "")[:6].ljust(6, "0")
                        naive_dt = datetime.strptime(f"{date_part[:8]}T{time_part}", "%Y%m%dT%H%M%S")

                        if is_utc:
                            dt_start = naive_dt.replace(tzinfo=timezone.utc).astimezone(target_tz)
                        else:
                            dt_start = naive_dt.replace(tzinfo=target_tz)

                        ev_date = dt_start.date()
                        is_all_day = False
                        sort_minutes = dt_start.hour * 60 + dt_start.minute
                        time_str, time_hr, time_min, time_period = _format_time_parts(dt_start, time_format)

                        # Parse DTEND if present
                        if "DTEND" in cur_event:
                            end_clean = cur_event["DTEND"].replace("-", "").replace(":", "")
                            if "T" in end_clean:
                                e_date, e_time = end_clean.split("T")
                                e_utc = e_time.endswith("Z")
                                e_time = e_time.replace("Z", "")[:6].ljust(6, "0")
                                naive_end = datetime.strptime(f"{e_date[:8]}T{e_time}", "%Y%m%dT%H%M%S")
                                if e_utc:
                                    dt_end = naive_end.replace(tzinfo=timezone.utc).astimezone(target_tz)
                                else:
                                    dt_end = naive_end.replace(tzinfo=target_tz)
                                time_end_str, _, _, _ = _format_time_parts(dt_end, time_format)
                    else:
                        ev_date = datetime.strptime(dt_str[:8], "%Y%m%d").date()
                except Exception:
                    continue

                # Read RFC 7986 COLOR (e.g. "turquoise") or Apple hex (e.g. "#FF2968")
                raw_color = (
                    cur_event.get("COLOR") 
                    or cur_event.get("X-APPLE-CALENDAR-COLOR") 
                    or ""
                ).strip().strip('"\'')

                icon = icon_map.get(raw_color.lower(), "ph-calendar-blank")

                if ev_date and today <= ev_date <= end_date:
                    events.append({
                        "title": summary,
                        "date_iso": ev_date.isoformat(),
                        "time_str": time_str,
                        "time_hr": time_hr,
                        "time_min": time_min,
                        "time_period": time_period,
                        "time_end_str": time_end_str,
                        "is_all_day": is_all_day,
                        "sort_minutes": sort_minutes,
                        "color_id": raw_color,
                        "icon": icon,
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
            "time_hr": "8",
            "time_min": "15",
            "time_period": "AM",
            "time_end_str": "8:45 AM",
            "is_all_day": False,
            "sort_minutes": 8 * 60 + 15,
            "color_id": "1",
            "icon": "ph-backpack",
        },
        {
            "title": "Dentist Appointment",
            "date_iso": today.isoformat(),
            "time_str": "2:00 PM",
            "time_hr": "2",
            "time_min": "00",
            "time_period": "PM",
            "time_end_str": "3:00 PM",
            "is_all_day": False,
            "sort_minutes": 14 * 60,
            "color_id": "2",
            "icon": "ph-first-aid",
        },
        {
            "title": "Trash & Recycling Pickup",
            "date_iso": (today + timedelta(days=1)).isoformat(),
            "time_str": "All Day",
            "time_hr": "",
            "time_min": "",
            "time_period": "",
            "time_end_str": "",
            "is_all_day": True,
            "sort_minutes": -1,
            "color_id": "3",
            "icon": "ph-trash",
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
        else:
            label = target_date.strftime("%A, %b %d").upper()

        day_events = [e for e in events if e["date_iso"] == target_iso]
        
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

    # Automatically resolve coordinates & local timezone
    lat, lon, target_tz, tz_str = _resolve_tesserae_environment(options, ctx)
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

    google_creds = options.get("google_credentials_json", "").strip()
    cal_ids = options.get("calendar_ids", "primary")
    icon_map = _parse_icon_map(options.get("color_icon_map", ""))
    debug_meta = []

    if google_creds:
        try:
            events, debug_meta = _fetch_google_calendar_events(
                google_creds, cal_ids, icon_map, days_ahead, time_fmt, target_tz
            )
        except Exception as exc:
            return {"error": f"Google Calendar API error: {str(exc)}"}
    elif ics_url:
        try:
            ics_raw = _fetch_url(ics_url)
            events = _parse_ics(ics_raw, days_ahead, time_fmt, target_tz, icon_map)
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
        "_debug": debug_meta
    }
