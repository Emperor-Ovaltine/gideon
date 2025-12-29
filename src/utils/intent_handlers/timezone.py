"""Handler for timezone conversion intent."""

import logging
from datetime import datetime, timedelta
from datetime import time as dt_time
import pytz

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


def normalize_timezone(tz_str):
    """
    Normalize timezone string to pytz timezone.

    Args:
        tz_str: Timezone string (abbreviation or name)

    Returns:
        pytz timezone object or None if invalid
    """
    if not tz_str:
        return None

    tz_str = tz_str.strip()

    # Check abbreviations first
    if tz_str.upper() in TZ_ABBREVIATIONS:
        tz_name = TZ_ABBREVIATIONS[tz_str.upper()]
    else:
        tz_name = tz_str

    # Try to get timezone
    try:
        return pytz.timezone(tz_name)
    except pytz.exceptions.UnknownTimeZoneError:
        # Try common city names
        city_mappings = {
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

        tz_lower = tz_name.lower()
        for city, tz in city_mappings.items():
            if city in tz_lower:
                try:
                    return pytz.timezone(tz)
                except:
                    pass

        return None


def parse_time_string(time_str):
    """
    Parse time string to hour and minute.

    Args:
        time_str: Time string (e.g., "3pm", "14:00", "9:30am")

    Returns:
        tuple of (hour, minute) or None if invalid
    """
    time_str = time_str.strip().lower().replace(' ', '')

    # Handle "Xpm" or "Xam"
    if 'pm' in time_str or 'am' in time_str:
        is_pm = 'pm' in time_str
        time_str = time_str.replace('pm', '').replace('am', '')

        # Handle "X:YY" or just "X"
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

    # Handle 24-hour format "HH:MM"
    elif ':' in time_str:
        parts = time_str.split(':')
        try:
            hour = int(parts[0])
            minute = int(parts[1]) if len(parts) > 1 else 0
        except ValueError:
            return None
    else:
        # Just a number, assume hour
        try:
            hour = int(time_str)
            minute = 0
        except ValueError:
            return None

    # Validate
    if hour < 0 or hour > 23 or minute < 0 or minute > 59:
        return None

    return (hour, minute)


async def handle_timezone_conversion(cog, message, channel_id, time, source_timezone, target_timezone):
    """
    Handle timezone conversion requests.

    Args:
        cog: The MentionCommands cog instance
        message: Discord message object
        channel_id: Channel ID as string
        time: Time to convert (e.g., "3pm", "14:00")
        source_timezone: Source timezone
        target_timezone: Target timezone
    """
    # Validate inputs
    if not time or not time.strip():
        await message.channel.send(
            "❌ I need a time to convert. "
            "Try something like: '@Gideon what time is 3pm EST in Tokyo?'"
        )
        logger.warning(f"[Timezone] Missing time for user {message.author.id}")
        return

    if not source_timezone or not source_timezone.strip():
        await message.channel.send(
            "❌ I need to know the source timezone. "
            "Try something like: '@Gideon what time is 3pm EST in Tokyo?'"
        )
        logger.warning(f"[Timezone] Missing source timezone for user {message.author.id}")
        return

    if not target_timezone or not target_timezone.strip():
        await message.channel.send(
            "❌ I need to know the target timezone. "
            "Try something like: '@Gideon what time is 3pm EST in Tokyo?'"
        )
        logger.warning(f"[Timezone] Missing target timezone for user {message.author.id}")
        return

    try:
        # Parse timezones
        source_tz = normalize_timezone(source_timezone)
        target_tz = normalize_timezone(target_timezone)

        if not source_tz:
            await message.channel.send(
                f"❌ I don't recognize the timezone '{source_timezone}'. "
                f"Try using standard abbreviations like EST, PST, UTC, or city names like Tokyo, London."
            )
            return

        if not target_tz:
            await message.channel.send(
                f"❌ I don't recognize the timezone '{target_timezone}'. "
                f"Try using standard abbreviations like EST, PST, UTC, or city names like Tokyo, London."
            )
            return

        # Parse time
        time_parts = parse_time_string(time)
        if not time_parts:
            await message.channel.send(
                f"❌ I couldn't parse the time '{time}'. "
                f"Try formats like '3pm', '14:00', or '9:30am'."
            )
            return

        hour, minute = time_parts

        # Create datetime in source timezone (use today's date)
        now = datetime.now(source_tz)
        source_dt = source_tz.localize(datetime(now.year, now.month, now.day, hour, minute))

        # Convert to target timezone
        target_dt = source_dt.astimezone(target_tz)

        # Format times for display
        source_time_str = source_dt.strftime("%I:%M %p").lstrip('0')
        target_time_str = target_dt.strftime("%I:%M %p").lstrip('0')

        # Check if date changed
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

        # Build response
        response = (
            f"**Timezone Conversion:**\n"
            f"{source_time_str} {source_tz.zone} = **{target_time_str} {target_tz.zone}**{day_note}"
        )

        await message.channel.send(response)

        # Add to conversation history
        await cog.state.add_to_channel_history(channel_id, {
            "role": "assistant",
            "content": f"Converted {time} from {source_timezone} to {target_timezone}: {target_time_str}{day_note}",
            "timestamp": datetime.now()
        })

        logger.info(f"[Timezone] User {message.author.id} converted {time} from {source_timezone} to {target_timezone}")

    except Exception as e:
        logger.exception(f"[Timezone] Error for user {message.author.id}: {e}")
        await message.channel.send(f"❌ Timezone conversion failed: {str(e)}")
