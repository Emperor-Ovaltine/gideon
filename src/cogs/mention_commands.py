"""Functionality for responding to @mentions in messages."""
import discord
import asyncio # Added for iscoroutinefunction
import logging # Added
from discord.ext import commands
from ..utils.state_manager import BotStateManager
# Removed import for conversation, now handled by state_manager
# Removed OpenRouterClient import as we use clients dict
from ..config import SYSTEM_PROMPT, DEFAULT_MODEL, INTENT_DISCOVERY, INTENT_DETECTION_MODEL, INTENT_CONFIDENCE_THRESHOLD
from datetime import datetime, timedelta
import pytz
import os
import json
from typing import Optional, Dict, Any

# Set up logging
logger = logging.getLogger('mention_commands') # Added logger

class MentionCommands(commands.Cog):
    """Handles responses when the bot is @mentioned in messages."""

    def __init__(self, bot):
        self.bot = bot
        # Use the shared state manager from the bot instance
        self.state = bot.state_manager # Use bot's state_manager
        # Store references to all provider clients (assuming they are attached to bot)
        self.clients = {
            "openrouter": getattr(bot, 'openrouter_client', None),
            "openai": getattr(bot, 'openai_client', None),
            "ai_horde": getattr(bot, 'ai_horde_client', None)
        }
        # Removed direct openrouter_client attribute initialization

    def get_model_for_channel(self, channel_id):
        """Get the appropriate model for this channel"""
        # Ensure state manager is available
        if not self.state:
             logger.error("[Mention] State manager not available in MentionCommands.")
             # Fallback or raise error? Let's return default for now.
             # This assumes DEFAULT_MODEL includes a provider prefix like 'openrouter/...'
             # Or handle this upstream in get_effective_model
             return DEFAULT_MODEL
        return self.state.get_effective_model(channel_id)

    async def detect_user_intent(self, message_content: str, channel_id: str) -> Optional[Dict[str, Any]]:
        """
        Detect user intent using a fast, dedicated model.

        Args:
            message_content: The cleaned message content (without mention)
            channel_id: Channel ID for logging purposes

        Returns:
            Dict with keys: {
                "intent": str ("reminder" | "conversation" | "unknown"),
                "confidence": float (0.0-1.0),
                "data": dict (intent-specific extracted data)
            }
            Or None if detection fails
        """
        # Parse the INTENT_DETECTION_MODEL (provider/model format)
        try:
            provider, model_name = INTENT_DETECTION_MODEL.split('/', 1)
        except ValueError:
            logger.error(f"[Intent] Invalid INTENT_DETECTION_MODEL format: {INTENT_DETECTION_MODEL}")
            return None

        # Get the appropriate client for this provider
        client = self.clients.get(provider)
        if not client:
            logger.error(f"[Intent] Client for provider '{provider}' not available for intent detection")
            return None

        # System prompt for intent detection
        system_prompt = """You are an intent classifier for a Discord bot. Analyze user messages and determine the intent.

INTENTS:

1. "reminder" - User wants to set a future reminder/notification
   Indicators:
   - Direct: "remind me to...", "set a reminder for...", "remind me in..."
   - Indirect: "I need to remember to...", "don't let me forget..."
   - Implicit: "in X hours/minutes, remind me..."

   Extract:
   - reminder_message: What to remind about
   - time_expression: When (e.g., "in 2 hours", "tomorrow at 3pm")

   NOT reminders:
   - "remind me what you said" (asking for information)
   - "what's my reminder" (querying existing reminders)
   - "can you remind me of..." (asking for explanation)

2. "conversation" - General chat, questions, casual interaction
   - Everything that doesn't fit other intents

3. "unknown" - Ambiguous or unclear intent
   - Use when genuinely uncertain

CONFIDENCE LEVELS:
- 0.9-1.0: Very clear intent (explicit keywords)
- 0.7-0.8: Likely intent (strong indicators)
- 0.5-0.6: Uncertain (ambiguous phrasing)
- Below 0.5: Use "unknown"

Return ONLY valid JSON:
{
  "intent": "reminder|conversation|unknown",
  "confidence": 0.85,
  "data": {...}
}

EXAMPLES:

Input: "remind me in 2 hours to check the oven"
Output: {"intent": "reminder", "confidence": 0.95, "data": {"reminder_message": "check the oven", "time_expression": "in 2 hours"}}

Input: "what's the weather like?"
Output: {"intent": "conversation", "confidence": 1.0, "data": {}}

Input: "remind me what you said about Python earlier"
Output: {"intent": "conversation", "confidence": 0.9, "data": {}}

Input: "remind me later"
Output: {"intent": "unknown", "confidence": 0.4, "data": {"reminder_message": "", "time_expression": "later"}}

Input: "in 30 minutes tell me to call mom"
Output: {"intent": "reminder", "confidence": 0.9, "data": {"reminder_message": "call mom", "time_expression": "in 30 minutes"}}"""

        try:
            # Prepare message for AI
            messages = [
                {"role": "user", "content": f"Parse this message: {message_content}"}
            ]

            # Call AI with response_format for structured output
            response_format = {"type": "json_object"}

            response = await client.send_message_with_history(
                messages=messages,
                model=model_name,
                system_prompt=system_prompt,
                response_format=response_format
            )

            # Clean response (remove markdown code blocks if present)
            cleaned_response = response.strip()
            if cleaned_response.startswith("```json"):
                cleaned_response = cleaned_response[7:]
            if cleaned_response.startswith("```"):
                cleaned_response = cleaned_response[3:]
            if cleaned_response.endswith("```"):
                cleaned_response = cleaned_response[:-3]
            cleaned_response = cleaned_response.strip()

            # Parse the JSON response
            result = json.loads(cleaned_response)

            # Validate required fields
            if "intent" not in result or "confidence" not in result:
                logger.error(f"[Intent] AI response missing required fields: {result}")
                return None

            logger.debug(f"[Intent] Raw detection result: {result}")
            return result

        except json.JSONDecodeError as e:
            logger.error(f"[Intent] Failed to parse AI JSON response: {e}. Response: {response}")
            return None
        except Exception as e:
            logger.error(f"[Intent] Error in intent detection: {e}", exc_info=True)
            return None

    async def handle_reminder_request(
        self,
        message: discord.Message,
        channel_id: str,
        reminder_message: str,
        time_expression: str
    ):
        """
        Handle a reminder request detected from a mention.

        Args:
            message: Original Discord message object
            channel_id: Channel ID as string
            reminder_message: What to remind about
            time_expression: Natural language time expression
        """
        # Validate inputs
        if not reminder_message or not reminder_message.strip():
            await message.channel.send(
                "❌ I detected you want a reminder, but I'm not sure what to remind you about. "
                "Please try something like: '@Gideon remind me in 2 hours to check the oven'"
            )
            logger.warning(f"[Intent] Missing reminder message for user {message.author.id}")
            return

        if not time_expression or not time_expression.strip():
            await message.channel.send(
                "❌ I detected you want a reminder, but I'm not sure when. "
                "Please specify a time like 'in 2 hours', 'tomorrow at 3pm', or 'at 5pm'"
            )
            logger.warning(f"[Intent] Missing time expression for user {message.author.id}")
            return

        # Get ReminderCommands cog
        reminder_cog = self.bot.get_cog('ReminderCommands')
        if not reminder_cog:
            await message.channel.send("⚠️ Reminder system not available.")
            logger.error("[Intent] ReminderCommands cog not found")
            return

        # Parse time using existing method
        try:
            parsed_time = await reminder_cog.parse_time_with_ai(time_expression, channel_id)
        except Exception as e:
            logger.error(f"[Intent] Error parsing time: {e}", exc_info=True)
            await message.channel.send(
                f"❌ Failed to parse time expression '{time_expression}'. "
                f"Please try something like 'in 2 hours', 'tomorrow at 3pm', or 'at 5pm'"
            )
            return

        if parsed_time is None:
            await message.channel.send(
                f"❌ I couldn't understand the time '{time_expression}'. "
                f"Please try something like 'in 2 hours', 'tomorrow at 3pm', or 'at 5pm'"
            )
            logger.warning(f"[Intent] Failed to parse time expression: {time_expression}")
            return

        # Validate time is not too far in the future (max 1 year)
        max_future = datetime.now() + timedelta(days=365)
        if parsed_time > max_future:
            await message.channel.send(
                "❌ Reminder time is too far in the future (max 1 year)."
            )
            logger.warning(f"[Intent] Reminder time too far in future: {parsed_time}")
            return

        # Save reminder to database
        try:
            user_id = str(message.author.id)
            reminder_id = self.state.add_reminder(
                user_id=user_id,
                channel_id=channel_id,
                message=reminder_message,
                due_timestamp=parsed_time
            )

            # Create Discord timestamp (shows in user's timezone)
            tz_str = os.environ.get('TZ', 'America/New_York')
            try:
                local_tz = pytz.timezone(tz_str)
            except pytz.exceptions.UnknownTimeZoneError:
                local_tz = pytz.timezone('America/New_York')

            # Localize the naive datetime to the local timezone
            aware_time = local_tz.localize(parsed_time)
            discord_timestamp = int(aware_time.timestamp())

            # Format confirmation matching /remind command
            confirmation_message = (
                f"✅ Reminder set!\n"
                f"**Message:** {reminder_message}\n"
                f"**When:** <t:{discord_timestamp}:F> (<t:{discord_timestamp}:R>)\n"
                f"**Reminder ID:** {reminder_id}"
            )

            # Send confirmation
            await message.channel.send(confirmation_message)

            # Add confirmation to channel history
            await self.state.add_to_channel_history(channel_id, {
                "role": "assistant",
                "content": confirmation_message,
                "timestamp": datetime.now()
            })

            logger.info(f"[Intent] User {user_id} set reminder {reminder_id} for {parsed_time} via mention")

        except Exception as e:
            logger.exception(f"[Intent] Error setting reminder: {e}")
            await message.channel.send(f"❌ Failed to save reminder: {str(e)}")

    @commands.Cog.listener()
    async def on_message(self, message):
        """Listen for messages in channels and respond to @mentions."""
        # Ignore messages from the bot itself
        if message.author == self.bot.user:
            return

        # Ignore messages in threads as they're handled by ThreadCommands
        if isinstance(message.channel, discord.Thread):
            return

        channel_id = str(message.channel.id)

        # Add all regular user messages to history (if state manager is available)
        if self.state and not message.content.startswith('/'):  # Ignore slash commands
            try:
                await self.state.add_to_channel_history(channel_id, {
                    "role": "user",
                    "name": message.author.display_name,
                    "content": message.content,
                    "timestamp": datetime.now()
                })
            except Exception as e:
                 logger.error(f"[Mention] Error adding message to history for channel {channel_id}: {e}", exc_info=True)


        # Process mentions - improved detection method
        is_mentioned = False
        if message.mentions:
            for mention in message.mentions:
                if mention.id == self.bot.user.id:
                    is_mentioned = True
                    break

        if not is_mentioned and f'<@{self.bot.user.id}>' in message.content or f'<@!{self.bot.user.id}>' in message.content:
            is_mentioned = True

        if is_mentioned and not message.mention_everyone:
            # Ensure state manager is available before proceeding
            if not self.state:
                 logger.error("[Mention] State manager not available when processing mention.")
                 await message.channel.send("⚠️ Internal error: State manager not available.")
                 return

            logger.info(f"[Mention] Detected mention from {message.author.id} in channel {channel_id}")

            # Determine which provider and model to use for this channel
            model_id_full = self.get_model_for_channel(channel_id)
            logger.info(f"[Mention] Effective model ID from state = '{model_id_full}'")

            # Parse provider and model name
            try:
                provider, model_name = model_id_full.split('/', 1)
            except ValueError:
                logger.warning(f"[Mention] Invalid model format '{model_id_full}' for channel {channel_id}. Defaulting to global provider.")
                # Use global provider from state manager if available
                provider = self.state.global_provider if self.state else "openrouter"
                model_name = model_id_full
                model_id_full = f"{provider}/{model_name}"

            # Select the appropriate client
            client_to_use = self.clients.get(provider)
            logger.info(f"[Mention] Parsed Provider='{provider}', Model='{model_name}'. Found client object: {client_to_use is not None}")

            try:
                # Get the message content without the mention
                content = message.content
                content = content.replace(f'<@{self.bot.user.id}>', '').replace(f'<@!{self.bot.user.id}>', '')
                content = content.strip()
                if not content:
                    content = "Hello!"

                # Intent-based routing (if intent discovery is enabled)
                if INTENT_DISCOVERY:
                    try:
                        intent_result = await self.detect_user_intent(content, channel_id)

                        if intent_result:
                            intent_type = intent_result.get("intent")
                            confidence = intent_result.get("confidence", 0.0)
                            data = intent_result.get("data", {})

                            logger.info(f"[Intent] Detected intent='{intent_type}' confidence={confidence:.2f} (threshold={INTENT_CONFIDENCE_THRESHOLD})")

                            # Only act on high-confidence intents (>= configured threshold)
                            if confidence >= INTENT_CONFIDENCE_THRESHOLD:
                                if intent_type == "reminder":
                                    # Route to reminder handler
                                    await self.handle_reminder_request(
                                        message, channel_id,
                                        data.get("reminder_message", ""),
                                        data.get("time_expression", "")
                                    )
                                    return  # Exit early, skip normal AI flow

                                # Future intents can be added here:
                                # elif intent_type == "channel_settings":
                                #     await self.handle_channel_settings(message, channel_id, data)
                                #     return
                            else:
                                logger.info(f"[Intent] Low confidence ({confidence:.2f} < {INTENT_CONFIDENCE_THRESHOLD}), falling back to conversation")

                    except Exception as e:
                        logger.error(f"[Intent] Error in intent detection: {e}", exc_info=True)
                        # Fall through to normal conversation on error

                # Process images if any are attached
                images = []
                client_supports_vision = False # Default
                if client_to_use and hasattr(client_to_use, 'model_supports_vision') and message.attachments:
                    # Check if the specific model within the provider supports vision
                    if asyncio.iscoroutinefunction(client_to_use.model_supports_vision):
                        client_supports_vision = await client_to_use.model_supports_vision(model_name)
                    else:
                        client_supports_vision = client_to_use.model_supports_vision(model_name)
                    logger.info(f"[Mention] Client '{provider}' model '{model_name}' vision support: {client_supports_vision}")

                    if client_supports_vision:
                         for attachment in message.attachments:
                             if any(attachment.filename.lower().endswith(ext) for ext in ['.jpg', '.jpeg', '.png', '.gif', '.webp']):
                                try:
                                    image_data = await attachment.read()
                                    images.append({
                                        'data': image_data,
                                        'type': attachment.content_type or 'image/jpeg'
                                    })
                                except Exception as e:
                                    await message.channel.send(f"⚠️ Failed to process image {attachment.filename}: {str(e)}")

                # Get channel-specific system prompt if it exists
                channel_system_prompt = self.state.get_channel_system_prompt(channel_id)

                # Get recent channel context from state manager
                conversation_context = self.state.get_channel_history(channel_id)

                # Format the final query with the current user's message
                # Ensure the mention message itself isn't added twice if already added above
                # Check if the last message in context is the same as the current one
                last_msg_in_context = conversation_context[-1]['content'] if conversation_context else None
                current_user_formatted_msg = f"{message.author.display_name}: {content}"

                if not conversation_context or last_msg_in_context != current_user_formatted_msg:
                     # Add the user's current message to the context being sent to the API
                     # Note: We already added the raw message earlier for history purposes.
                     # This appends the potentially cleaned-up version for the API call.
                     conversation_context.append({
                         "role": "user",
                         "content": current_user_formatted_msg
                     })


                # Send "thinking" message with typing indicator
                async with message.channel.typing():
                    # --- Select and Call Correct Client ---
                    logger.debug(f"[Mention] Attempting to select client. Provider='{provider}', Client Object='{client_to_use}', Has Send Method='{hasattr(client_to_use, 'send_message_with_history') if client_to_use else 'N/A'}'")
                    if client_to_use and hasattr(client_to_use, 'send_message_with_history'):
                        logger.info(f"[Mention] ✅ Calling send_message_with_history on client for provider '{provider}' ({type(client_to_use).__name__}) with model '{model_name}'")
                        response = await client_to_use.send_message_with_history(
                            messages=conversation_context,
                            model=model_name, # Pass only the model name part
                            system_prompt=channel_system_prompt,
                            images=images # Pass processed images (will be empty if not supported/present)
                        )
                    elif client_to_use:
                         logger.error(f"[Mention] ❌ Client for provider '{provider}' exists but does not have 'send_message_with_history' method.")
                         response = f"⚠️ Error: Client for provider '{provider}' does not support chat ('send_message_with_history' missing)."
                    else:
                         logger.error(f"[Mention] ❌ Client for provider '{provider}' not found or not initialized in self.clients.")
                         response = f"⚠️ Error: Client for provider '{provider}' not available or not initialized."
                    # --- End Client Call ---

                # Check if response is an error
                if response.startswith("⚠️"):
                    # If it's an error, don't split chunks and don't add to history
                    await message.channel.send(response)
                else:
                    # Add assistant's response to history
                    await self.state.add_to_channel_history(channel_id, {
                        "role": "assistant",
                        "content": response,
                        "timestamp": datetime.now()
                    })

                    # Split response into chunks of 2000 characters or fewer
                    max_length = 2000
                    chunks = [response[i:i+max_length] for i in range(0, len(response), max_length)]

                    # Send each chunk as a separate message
                    for chunk in chunks:
                        await message.channel.send(chunk)

            except Exception as e:
                 logger.exception(f"[Mention] Error processing mention in channel {channel_id}: {e}")
                 try:
                     await message.channel.send(f"⚠️ An unexpected error occurred while processing your mention: {str(e)}")
                 except Exception as followup_e:
                     logger.error(f"[Mention] Failed to send error message to channel {channel_id}: {followup_e}")

            # Removed finally block

def setup(bot):
    # Ensure state_manager is available on bot before adding cog
    if not hasattr(bot, 'state_manager'):
        logger.error("State manager not found on bot object. Cannot load MentionCommands cog.")
        return
    # Ensure clients are available (or handle None gracefully in __init__)
    if not getattr(bot, 'openrouter_client', None):
         logger.warning("OpenRouter client not found on bot object. MentionCommands might have limited functionality.")
    # Add other client checks if strictly necessary for this cog

    try:
        bot.add_cog(MentionCommands(bot))
        logger.info("MentionCommands cog loaded successfully.")
    except Exception as e:
        logger.exception(f"Failed to initialize or add MentionCommands cog: {e}")
