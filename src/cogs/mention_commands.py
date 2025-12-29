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

2. "image_generation" - User wants to generate an AI image
   Indicators:
   - Direct: "draw...", "generate an image...", "create a picture...", "make an image..."
   - Keywords: "draw", "generate", "create", "paint", "illustrate", "sketch", "render", "show me" (visual)
   - Implicit: "I want to see...", "can you make..." (when referring to visual content)

   Extract:
   - prompt: The main description of what to generate (required)
   - negative_prompt: What to exclude (optional, look for "no", "without", "avoid", "but not")
   - size: Dimensions if specified (optional, e.g., "512x512", "1024x1024", "landscape", "portrait")
   - quality: Quality setting (optional, "hd", "high quality", "standard")
   - style: Style preference (optional, "vivid", "natural", "realistic", "artistic")

   Examples of size extraction:
   - "512x512" or "512 x 512" → size: "512x512"
   - "1024 by 1024" → size: "1024x1024"
   - "landscape" or "wide" → size: "1024x768"
   - "portrait" or "tall" → size: "768x1024"
   - Not specified → size: "" (empty string)

   Examples of negative_prompt extraction:
   - "no clouds" → negative_prompt: "clouds"
   - "without people" → negative_prompt: "people"
   - "avoid red colors" → negative_prompt: "red colors"
   - "but not scary" → negative_prompt: "scary"
   - Not specified → negative_prompt: "" (empty string)

   NOT image generation:
   - "show me my images" (querying existing images)
   - "explain this image" (image analysis, needs attachment)
   - "what does this picture show" (asking about existing image)

3. "conversation" - General chat, questions, casual interaction
   - Everything that doesn't fit other intents

4. "unknown" - Ambiguous or unclear intent
   - Use when genuinely uncertain

CONFIDENCE LEVELS:
- 0.9-1.0: Very clear intent (explicit keywords)
- 0.7-0.8: Likely intent (strong indicators)
- 0.5-0.6: Uncertain (ambiguous phrasing)
- Below 0.5: Use "unknown"

Return ONLY valid JSON:
{
  "intent": "reminder|image_generation|conversation|unknown",
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
Output: {"intent": "reminder", "confidence": 0.9, "data": {"reminder_message": "call mom", "time_expression": "in 30 minutes"}}

Input: "draw a sunset over mountains"
Output: {"intent": "image_generation", "confidence": 0.95, "data": {"prompt": "a sunset over mountains", "negative_prompt": "", "size": "", "quality": "", "style": ""}}

Input: "generate a cat 512x512, no dogs"
Output: {"intent": "image_generation", "confidence": 0.95, "data": {"prompt": "a cat", "negative_prompt": "dogs", "size": "512x512", "quality": "", "style": ""}}

Input: "create a landscape painting, high quality, vivid style, without people"
Output: {"intent": "image_generation", "confidence": 0.9, "data": {"prompt": "a landscape painting", "negative_prompt": "people", "size": "", "quality": "hd", "style": "vivid"}}

Input: "make me a picture of a robot, portrait size"
Output: {"intent": "image_generation", "confidence": 0.85, "data": {"prompt": "a robot", "negative_prompt": "", "size": "768x1024", "quality": "", "style": ""}}"""

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

    async def handle_image_generation_request(
        self,
        message: discord.Message,
        channel_id: str,
        prompt: str,
        negative_prompt: str = "",
        size: str = "",
        quality: str = "",
        style: str = ""
    ):
        """
        Handle an image generation request detected from a mention.

        Args:
            message: Original Discord message object
            channel_id: Channel ID as string
            prompt: Image description/prompt
            negative_prompt: What to exclude from the image
            size: Requested size (e.g., "512x512")
            quality: Quality setting for OpenAI ("hd" or "standard")
            style: Style setting for OpenAI ("vivid" or "natural")
        """
        # Validate prompt
        if not prompt or not prompt.strip():
            await message.channel.send(
                "❌ I detected you want to generate an image, but I'm not sure what to create. "
                "Please try something like: '@Gideon draw a sunset over mountains'"
            )
            logger.warning(f"[Intent] Missing image prompt for user {message.author.id}")
            return

        # Get UnifiedImageCommands cog
        image_cog = self.bot.get_cog('UnifiedImageCommands')
        if not image_cog:
            await self._handle_image_generation_fallback(
                message, channel_id,
                "Image generation failed. The image generation system is not available. "
            )
            logger.error("[Intent] UnifiedImageCommands cog not found")
            return

        # Get active provider and config from database
        try:
            from ..cogs.unified_image_commands import DEFAULT_CONFIGS

            active_provider = image_cog.db.get_global_config("image_active_provider", "ai_horde")
            config_key = f"image_config_{active_provider}"
            config_json = image_cog.db.get_global_config(config_key)

            # Parse provider config
            if config_json:
                try:
                    provider_config = json.loads(config_json)
                except json.JSONDecodeError:
                    logger.warning(f"[Intent] Failed to parse config for {active_provider}, using defaults")
                    provider_config = DEFAULT_CONFIGS.get(active_provider, {})
            else:
                provider_config = DEFAULT_CONFIGS.get(active_provider, {})

        except Exception as e:
            await self._handle_image_generation_fallback(
                message, channel_id,
                "Image generation failed. Could not retrieve image provider configuration. "
            )
            logger.error(f"[Intent] Error getting image provider config: {e}")
            return

        # Select and validate client
        client = None
        provider_display_name = "Unknown"
        params = {"prompt": prompt}

        if active_provider == 'ai_horde':
            client = image_cog.horde_client
            provider_display_name = "AI Horde"
            if client:
                # Parse size or use default
                target_size = size if size else provider_config.get("size", "512x512")
                try:
                    width, height = map(int, target_size.split('x'))
                    width = round(width / 64) * 64  # Ensure multiple of 64
                    height = round(height / 64) * 64
                except (ValueError, AttributeError):
                    width, height = 512, 512
                    logger.warning(f"[Intent] Invalid size '{target_size}', using 512x512")

                params.update({
                    "negative_prompt": negative_prompt,
                    "width": width,
                    "height": height,
                    "steps": provider_config.get("steps", 30),
                    "model": provider_config.get("model", "stable_diffusion_xl")
                })

        elif active_provider == 'cloudflare':
            client = image_cog.cf_client
            provider_display_name = "Cloudflare"
            if client:
                target_size = size if size else provider_config.get("size", "768x768")
                try:
                    width, height = map(int, target_size.split('x'))
                except (ValueError, AttributeError):
                    width, height = 768, 768
                    logger.warning(f"[Intent] Invalid size '{target_size}', using 768x768")

                params.update({
                    "negative_prompt": negative_prompt,
                    "width": width,
                    "height": height,
                    "steps": provider_config.get("steps", 25),
                    "seed": provider_config.get("seed")
                })

        elif active_provider == 'openai':
            client = image_cog.openai_client
            provider_display_name = "OpenAI"
            if client:
                # Map quality variations to OpenAI values
                openai_quality = None
                if quality:
                    quality_lower = quality.lower()
                    if "hd" in quality_lower or "high" in quality_lower:
                        openai_quality = "hd"
                    else:
                        openai_quality = "standard"
                else:
                    openai_quality = provider_config.get("quality", "standard")

                # Map style to OpenAI values
                openai_style = None
                if style:
                    style_lower = style.lower()
                    if "vivid" in style_lower:
                        openai_style = "vivid"
                    elif "natural" in style_lower:
                        openai_style = "natural"
                else:
                    openai_style = provider_config.get("style", "vivid")

                params.update({
                    "model": provider_config.get("model", "dall-e-3"),
                    "size": "1024x1024",  # Fixed for OpenAI
                    "quality": openai_quality if provider_config.get("model", "dall-e-3") == "dall-e-3" else None,
                    "style": openai_style if provider_config.get("model", "dall-e-3") == "dall-e-3" else None
                })
                # Note: OpenAI doesn't support negative_prompt, so we ignore it

        if not client:
            await self._handle_image_generation_fallback(
                message, channel_id,
                f"Image generation failed. The {provider_display_name} client is not configured. "
            )
            logger.error(f"[Intent] {provider_display_name} client not available")
            return

        # Send "generating" message with typing indicator
        async with message.channel.typing():
            thinking_msg = await message.channel.send(
                f"🎨 Generating image with **{provider_display_name}**: `{prompt}`\n*Please wait...*"
            )

        # Call generate_image
        try:
            result = await client.generate_image(**params)
        except Exception as e:
            logger.exception(f"[Intent] Exception during image generation with {active_provider}: {e}")
            await thinking_msg.delete()
            await self._handle_image_generation_fallback(
                message, channel_id,
                f"Image generation failed. An unexpected error occurred: {str(e)}. "
            )
            return

        # Handle result
        if result.get("success"):
            # Build embed
            embed = discord.Embed(
                title="Generated Image",
                description=f"**Prompt:** {prompt}",
                color=discord.Color.blue()
            )

            if negative_prompt and active_provider != 'openai':
                embed.add_field(name="Negative Prompt", value=negative_prompt, inline=False)

            # Footer with metadata
            footer_parts = [f"Provider: {provider_display_name}"]
            if result.get("model_used"):
                footer_parts.append(f"Model: {result.get('model_used')}")
            if result.get("seed"):
                footer_parts.append(f"Seed: {result.get('seed')}")
            if params.get("steps"):
                footer_parts.append(f"Steps: {params.get('steps')}")
            if params.get("size"):
                footer_parts.append(f"Size: {params.get('size')}")
            elif params.get("width"):
                footer_parts.append(f"Size: {params.get('width')}x{params.get('height')}")

            embed.set_footer(text=" | ".join(footer_parts))

            if result.get("revised_prompt"):
                embed.add_field(name="Revised Prompt (DALL-E 3)", value=result["revised_prompt"], inline=False)

            # Send image
            if "image_url" in result:
                embed.set_image(url=result["image_url"])
                await thinking_msg.edit(content=None, embed=embed)
            elif "local_path" in result:
                file = discord.File(result["local_path"], filename="generated_image.png")
                embed.set_image(url="attachment://generated_image.png")
                await thinking_msg.delete()
                await message.channel.send(embed=embed, file=file)
            else:
                await thinking_msg.delete()
                await self._handle_image_generation_fallback(
                    message, channel_id,
                    "Image generation failed. No image data returned. "
                )
                return

            # Add to conversation history (assistant response)
            await self.state.add_to_channel_history(channel_id, {
                "role": "assistant",
                "content": f"[Generated image: {prompt}]",
                "timestamp": datetime.now()
            })

            logger.info(f"[Intent] User {message.author.id} generated image via mention: '{prompt}' using {provider_display_name}")

        else:
            # Generation failed
            error_msg = result.get("error", "Unknown error")
            await thinking_msg.delete()
            await self._handle_image_generation_fallback(
                message, channel_id,
                f"Image generation failed. {error_msg}. "
            )
            logger.warning(f"[Intent] Image generation failed for user {message.author.id}: {error_msg}")

    async def _handle_image_generation_fallback(
        self,
        message: discord.Message,
        channel_id: str,
        error_prefix: str
    ):
        """
        Handle failed image generation by falling back to conversation with error prefix.

        Args:
            message: Original Discord message object
            channel_id: Channel ID as string
            error_prefix: Error message to prefix (e.g., "Image generation failed. API error. ")
        """
        # Get the user's original message content
        content = message.content
        content = content.replace(f'<@{self.bot.user.id}>', '').replace(f'<@!{self.bot.user.id}>', '')
        content = content.strip()
        if not content:
            content = "Hello!"

        # Get model and client for conversation
        model_id_full = self.get_model_for_channel(channel_id)
        try:
            provider, model_name = model_id_full.split('/', 1)
        except ValueError:
            provider = self.state.global_provider if self.state else "openrouter"
            model_name = model_id_full

        client_to_use = self.clients.get(provider)

        if not client_to_use or not hasattr(client_to_use, 'send_message_with_history'):
            # Can't even do conversation fallback
            await message.channel.send(
                f"{error_prefix}Additionally, the conversation system is unavailable."
            )
            return

        # Get conversation context
        channel_system_prompt = self.state.get_channel_system_prompt(channel_id)
        conversation_context = self.state.get_channel_history(channel_id)

        # Add current message to context
        conversation_context.append({
            "role": "user",
            "content": f"{message.author.display_name}: {content}"
        })

        # Get AI response
        try:
            async with message.channel.typing():
                response = await client_to_use.send_message_with_history(
                    messages=conversation_context,
                    model=model_name,
                    system_prompt=channel_system_prompt
                )

            # Prefix response with error
            full_response = f"{error_prefix}{response}"

            # Add to history
            await self.state.add_to_channel_history(channel_id, {
                "role": "assistant",
                "content": full_response,
                "timestamp": datetime.now()
            })

            # Send in chunks
            max_length = 2000
            chunks = [full_response[i:i+max_length] for i in range(0, len(full_response), max_length)]
            for chunk in chunks:
                await message.channel.send(chunk)

        except Exception as e:
            logger.exception(f"[Intent] Error in fallback conversation: {e}")
            await message.channel.send(
                f"{error_prefix}Additionally, failed to generate a conversation response."
            )

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

                                elif intent_type == "image_generation":
                                    # Route to image generation handler
                                    await self.handle_image_generation_request(
                                        message, channel_id,
                                        data.get("prompt", ""),
                                        data.get("negative_prompt", ""),
                                        data.get("size", ""),
                                        data.get("quality", ""),
                                        data.get("style", "")
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
