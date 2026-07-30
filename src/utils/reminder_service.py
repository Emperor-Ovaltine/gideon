"""Delivery of due reminders (runs from the bot's minutely background task)."""
import logging
from datetime import datetime

import discord

from .timeutil import now_local_naive
from ..config import DEFAULT_MODEL

logger = logging.getLogger(__name__)

_DELIVERY_SYSTEM_PROMPT = """You are Gideon, a helpful AI assistant. You are delivering a reminder to a user.
Be conversational, friendly, and in-character. Keep it brief but personable."""


async def deliver_due_reminders(bot) -> None:
    """Finds due reminders and delivers them to their channels.

    Reminders are stored as naive datetimes in the server-local timezone,
    so the comparison uses the same convention.
    """
    state = bot.state_manager
    current_time = now_local_naive()

    due_reminders = state.get_due_reminders(current_time)
    if not due_reminders:
        return

    logger.info(f"Found {len(due_reminders)} due reminder(s)")

    for reminder in due_reminders:
        reminder_id = reminder['reminder_id']
        user_id = reminder['user_id']
        channel_id = reminder['channel_id']
        message = reminder['message']
        due_timestamp = reminder['due_timestamp']

        try:
            channel = bot.get_channel(int(channel_id))
            if channel is None:
                logger.warning(f"Channel {channel_id} not found for reminder {reminder_id}. Marking as sent.")
                state.mark_reminder_sent(reminder_id)
                continue

            # Handle datetime conversion if stored as string
            if isinstance(due_timestamp, str):
                try:
                    due_timestamp = datetime.fromisoformat(due_timestamp)
                except ValueError:
                    due_timestamp = datetime.strptime(due_timestamp, '%Y-%m-%d %H:%M:%S')

            from .timeutil import to_epoch
            discord_timestamp = to_epoch(due_timestamp)

            await _send_reminder(bot, state, channel, user_id, channel_id,
                                 message, discord_timestamp)

            state.mark_reminder_sent(reminder_id)
            logger.info(f"Sent reminder {reminder_id} to user {user_id} in channel {channel_id}")

        except discord.Forbidden:
            logger.warning(f"No permission to send reminder {reminder_id} in channel {channel_id}. Marking as sent.")
            state.mark_reminder_sent(reminder_id)
        except discord.HTTPException as e:
            logger.error(f"Discord API error sending reminder {reminder_id}: {e}")
            # Don't mark as sent - will retry next cycle
        except Exception as e:
            logger.error(f"Error sending reminder {reminder_id}: {e}", exc_info=True)
            # Don't mark as sent - will retry next cycle


async def _send_reminder(bot, state, channel, user_id, channel_id, message,
                         discord_timestamp) -> None:
    """Sends one reminder, using an AI-personalized message when possible."""
    fallback = (f"<@{user_id}> ⏰ **Reminder:** {message}\n"
                f"_Originally set for <t:{discord_timestamp}:F>_")

    provider, model_name = state.resolve_model(str(channel_id))
    client_map = {
        "openrouter": getattr(bot, 'openrouter_client', None),
        "openai": getattr(bot, 'openai_client', None),
        "ai_horde": getattr(bot, 'ai_horde_client', None),
    }
    client_to_use = client_map.get(provider)

    if not client_to_use:
        logger.error(f"Client for provider '{provider}' not available for reminder delivery")
        await channel.send(content=fallback)
        return

    user_prompt = f"""The user asked to be reminded about: "{message}"
This reminder was set for <t:{discord_timestamp}:F>.

Deliver this reminder in a friendly, conversational way. Keep it brief (2-3 sentences max).
Make sure to include the reminder content clearly."""

    try:
        ai_response = await client_to_use.send_message_with_history(
            messages=[{"role": "user", "content": user_prompt}],
            model=model_name,
            system_prompt=_DELIVERY_SYSTEM_PROMPT
        )
        if not isinstance(ai_response, str) or ai_response.startswith("⚠️"):
            raise ValueError(f"Provider error: {ai_response}")
        await channel.send(content=f"<@{user_id}> {ai_response}")
    except Exception as ai_error:
        logger.error(f"AI error generating reminder message: {ai_error}")
        await channel.send(content=fallback)
