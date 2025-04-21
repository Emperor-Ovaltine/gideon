"""Functionality for responding to @mentions in messages."""
import discord
import asyncio # Added for iscoroutinefunction
import logging # Added
from discord.ext import commands
from ..utils.state_manager import BotStateManager
# Removed import for conversation, now handled by state_manager
# Removed OpenRouterClient import as we use clients dict
from ..config import SYSTEM_PROMPT, DEFAULT_MODEL # Keep for defaults if needed
from datetime import datetime

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
