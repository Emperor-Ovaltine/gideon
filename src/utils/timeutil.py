"""Shared timezone helpers.

Reminders and events are stored as naive datetimes in the server's local
timezone (the ``TZ`` env var, default ``America/New_York``). These helpers
centralize that convention so it lives in exactly one place.
"""
import logging
import os
from datetime import datetime
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

logger = logging.getLogger(__name__)

_DEFAULT_TZ = "America/New_York"


def local_tz() -> ZoneInfo:
    """Returns the server-local timezone from the TZ env var."""
    tz_str = os.environ.get("TZ", _DEFAULT_TZ)
    try:
        return ZoneInfo(tz_str)
    except (ZoneInfoNotFoundError, ValueError):
        logger.warning(f"Unknown timezone '{tz_str}', defaulting to {_DEFAULT_TZ}")
        return ZoneInfo(_DEFAULT_TZ)


def now_local() -> datetime:
    """Current aware datetime in the server-local timezone."""
    return datetime.now(local_tz())


def now_local_naive() -> datetime:
    """Current naive datetime in the server-local timezone (storage format)."""
    return now_local().replace(tzinfo=None)


def to_epoch(naive_local_dt: datetime) -> int:
    """Converts a stored naive local datetime to a Unix timestamp.

    Discord's ``<t:...>`` tags render epoch seconds in each viewer's own
    timezone, so this is all the display logic reminders need.
    """
    return int(naive_local_dt.replace(tzinfo=local_tz()).timestamp())


def to_aware(naive_local_dt: datetime) -> datetime:
    """Attaches the server-local timezone to a stored naive datetime."""
    return naive_local_dt.replace(tzinfo=local_tz())
