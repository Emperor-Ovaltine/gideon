"""Timezone conversion (convert_timezone tool)."""

import logging
from datetime import datetime
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

logger = logging.getLogger('timezone_handler')


# Common timezone abbreviations mapping
TZ_ABBREVIATIONS = {
    'EST': 'US/Eastern',
    'EDT': 'US/Eastern',
    'CST': 'US/Central',
    'CDT': 'US/Central',
    'MST': 'US/Mountain',
    'MDT': 'US/Mountain',
    'PST': 'US/Pacific',
    'PDT': 'US/Pacific',
    'GMT': 'GMT',
    'UTC': 'UTC',
    'BST': 'Europe/London',
    'CET': 'Europe/Paris',
    'CEST': 'Europe/Paris',
    'JST': 'Asia/Tokyo',
    'KST': 'Asia/Seoul',
    'IST': 'Asia/Kolkata',
    'AEST': 'Australia/Sydney',
    'AEDT': 'Australia/Sydney',
}

_CITY_MAPPINGS = {
    'tokyo': 'Asia/Tokyo',
    'london': 'Europe/London',
    'paris': 'Europe/Paris',
    'new york': 'America/New_York',
    'los angeles': 'America/Los_Angeles',
    'chicago': 'America/Chicago',
    'sydney': 'Australia/Sydney',
    'seoul': 'Asia/Seoul',
    'beijing': 'Asia/Shanghai',
    'mumbai': 'Asia/Kolkata',
}


def normalize_timezone(tz_str):
    """Normalizes a timezone string (abbreviation, IANA name, or city) to a ZoneInfo, or None."""
    if not tz_str:
        return None

    tz_str = tz_str.strip()
    tz_name = TZ_ABBREVIATIONS.get(tz_str.upper(), tz_str)

    try:
        return ZoneInfo(tz_name)
    except (ZoneInfoNotFoundError, ValueError):
        tz_lower = tz_name.lower()
        for city, tz in _CITY_MAPPINGS.items():
            if city in tz_lower:
                try:
                    return ZoneInfo(tz)
                except (ZoneInfoNotFoundError, ValueError):
                    pass
        return None


def parse_time_string(time_str):
    """Parses a time string like '3pm', '14:00', '9:30am' to (hour, minute), or None."""
    time_str = time_str.strip().lower().replace(' ', '')

    if 'pm' in time_str or 'am' in time_str:
        is_pm = 'pm' in time_str
        time_str = time_str.replace('pm', '').replace('am', '')

        if ':' in time_str:
            parts = time_str.split(':')
            try:
                hour = int(parts[0])
                minute = int(parts[1]) if len(parts) > 1 else 0
            except ValueError:
                return None
        else:
            try:
                hour = int(time_str)
                minute = 0
            except ValueError:
                return None

        # Convert to 24-hour
        if is_pm and hour != 12:
            hour += 12
        elif not is_pm and hour == 12:
            hour = 0

    elif ':' in time_str:
        parts = time_str.split(':')
        try:
            hour = int(parts[0])
            minute = int(parts[1]) if len(parts) > 1 else 0
        except ValueError:
            return None
    else:
        try:
            hour = int(time_str)
            minute = 0
        except ValueError:
            return None

    if hour < 0 or hour > 23 or minute < 0 or minute > 59:
        return None

    return (hour, minute)


def convert_time(time: str, source_timezone: str, target_timezone: str) -> str:
    """Converts a wall-clock time between timezones.

    Returns a human-readable result string. Raises ValueError on bad input.
    """
    if not time or not time.strip():
        raise ValueError("No time provided to convert.")
    if not source_timezone or not source_timezone.strip():
        raise ValueError("No source timezone provided.")
    if not target_timezone or not target_timezone.strip():
        raise ValueError("No target timezone provided.")

    source_tz = normalize_timezone(source_timezone)
    if not source_tz:
        raise ValueError(
            f"Unrecognized timezone '{source_timezone}'. "
            f"Use standard abbreviations like EST, PST, UTC, or city names like Tokyo, London."
        )
    target_tz = normalize_timezone(target_timezone)
    if not target_tz:
        raise ValueError(
            f"Unrecognized timezone '{target_timezone}'. "
            f"Use standard abbreviations like EST, PST, UTC, or city names like Tokyo, London."
        )

    time_parts = parse_time_string(time)
    if not time_parts:
        raise ValueError(f"Could not parse the time '{time}'. Use formats like '3pm', '14:00', or '9:30am'.")
    hour, minute = time_parts

    # Create datetime in source timezone (use today's date)
    now = datetime.now(source_tz)
    source_dt = datetime(now.year, now.month, now.day, hour, minute, tzinfo=source_tz)
    target_dt = source_dt.astimezone(target_tz)

    source_time_str = source_dt.strftime("%I:%M %p").lstrip('0')
    target_time_str = target_dt.strftime("%I:%M %p").lstrip('0')

    if source_dt.date() != target_dt.date():
        day_diff = (target_dt.date() - source_dt.date()).days
        if day_diff == 1:
            day_note = " (next day)"
        elif day_diff == -1:
            day_note = " (previous day)"
        else:
            day_note = f" ({target_dt.strftime('%B %d, %Y')})"
    else:
        day_note = ""

    return f"{source_time_str} {source_dt.tzinfo.key} = {target_time_str} {target_dt.tzinfo.key}{day_note}"
