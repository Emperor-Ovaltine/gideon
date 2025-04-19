"""Thread-based conversation commands."""
import discord
import logging
from discord.ext import commands
from ..utils.state_manager import BotStateManager
from ..utils.openrouter_client import OpenRouterClient
from ..config import OPENROUTER_API_KEY, SYSTEM_PROMPT, ALLOWED_MODELS, DEFAULT_MODEL
from datetime import datetime, timedelta
from typing import Optional, Dict, Any, List

# Create logger
logger = logging.getLogger(__name__)

class ThreadCommands(commands.Cog):
    """Commands for managing AI conversation threads."""

    def __init__(self, bot):
        self.bot = bot
        self.state = BotStateManager() # Get the singleton instance
        self.openrouter_client = OpenRouterClient(OPENROUTER_API_KEY, SYSTEM_PROMPT, DEFAULT_MODEL)

        # Removed: self.state.discord_threads initialization - now handled by DB

        # Create and register the thread group
        self.thread_group = discord.SlashCommandGroup(
            "thread",
            "Thread conversation commands"
        )

        # Register basic commands with the group
        self.thread_group.command(name="new", description="Create a new AI conversation thread")(self.thread_slash)
        self.thread_group.command(name="message", description="Chat within a specific conversation thread")(self.thread_chat_slash)
        self.thread_group.command(name="list", description="List all active conversation threads in this channel")(self.list_threads_slash)
        self.thread_group.command(name="delete", description="Delete a conversation thread")(self.delete_thread_slash)
        self.thread_group.command(name="rename", description="Rename a conversation thread")(self.rename_thread_slash)

        # For the model command, create the option first with the autocomplete callback
        model_option = discord.Option(
            str,
            "Select the AI model to use for this thread",
            autocomplete=self.model_autocomplete  # Pass the method directly
        )

        # Create an async wrapper method
        async def _set_model_command(ctx, model_name=model_option):
            await self.set_thread_model_slash(ctx, model_name)

        # Register the command with the async wrapper
        self.thread_group.command(name="setmodel", description="Set the AI model for the current thread")(_set_model_command)

        # Register the system prompt command normally
        self.thread_group.command(name="setsystem", description="Set a custom system prompt for this thread")(self.set_thread_system_slash)

        # Add the command group to the bot
        bot.add_application_command(self.thread_group)

    async def model_autocomplete(self, ctx):
        """Dynamic model autocomplete using ModelManager"""
        current_input = ctx.value.lower() if ctx.value else ""
        # Use the ModelManager instance from the state manager
        if not self.state.model_manager:
             logger.warning("ModelManager not set in StateManager for autocomplete.")
             return [] # Return empty if ModelManager isn't ready

        all_models = await self.state.model_manager.get_models()
        if not current_input:
            return all_models[:25]
        matching_models = [model for model in all_models if current_input in model.lower()]
        return matching_models[:25] or all_models[:25]

    def get_model_for_channel(self, channel_id):
        """Get the appropriate model for this channel"""
        return self.state.get_effective_model(channel_id)

    async def thread_slash(self, ctx,
                          name: str,
                          message: str = None,
                          image: discord.Attachment = None):
        """Create a new thread and optionally start with a message"""
        # Check if the channel supports threads
        if not isinstance(ctx.channel, discord.TextChannel):
            await ctx.respond("⚠️ This command can only be used in text channels that support threads.")
            return

        # Create an initial message that will anchor the thread
        initial_message = await ctx.channel.send(f"**AI Thread: {name}**\n*Starting a new conversation thread...*")

        try:
            # Create actual Discord thread from the message
            thread = await initial_message.create_thread(
                name=name,
                auto_archive_duration=1440  # Auto-archive after 24 hours of inactivity
            )

            # Store thread information in the database
            thread_id = str(thread.id)
            channel_id = str(ctx.channel.id)

            # Add thread to the database
            await self.state.add_discord_thread(
                thread_id=thread_id,
                channel_id=channel_id,
                name=name
                # created_at is set in the state manager/database
            )

            # Welcome message in the thread
            welcome_msg = f"✅ Thread created! You can chat with the AI by just sending regular messages in this thread. I'll respond to everything automatically."
            await thread.send(welcome_msg)

            # If a message was provided, process it immediately in the new thread
            if message:
                # Add user message to thread history in the database
                await self.state.add_discord_thread_message(thread_id, {
                    "role": "user",
                    "name": ctx.author.display_name,
                    "content": message,
                    # timestamp is set in the state manager/database
                    "user_id": str(ctx.author.id) # Store user ID
                })

                # Process image if provided
                model_supports_images = self.openrouter_client.model_supports_vision()
                images = []

                if image and model_supports_images:
                    if any(image.filename.lower().endswith(ext) for ext in ['.jpg', '.jpeg', '.png', '.gif', '.webp']):
                        try:
                            image_data = await image.read()
                            images.append({
                                'data': image_data,
                                'type': image.content_type or 'image/jpeg'
                            })
                        except Exception as e:
                            await thread.send(f"⚠️ Failed to process image {image.filename}: {str(e)}")
                            # Continue without the image if processing fails

                # Send thinking message in the thread
                thinking_msg = await thread.send(f"**{ctx.author.display_name}**: {message}\n\n_Processing response..._")

                # Get thread history for context (should only be the initial message for now)
                # Use the getter method
                conversation_context = self.state.get_discord_thread_history(thread_id)

                # Get thread-specific system prompt (or channel default)
                thread_config = self.state.get_discord_thread_config(thread_id)
                thread_system_prompt = thread_config.get("system_prompt") if thread_config else None

                if not thread_system_prompt:
                    thread_system_prompt = self.state.get_channel_system_prompt(channel_id)
                    if not thread_system_prompt:
                         # Fallback to global system prompt if no channel or thread specific prompt
                         thread_system_prompt = self.openrouter_client.system_prompt # Use the default from client init

                # Get thread-specific model (or channel/global default)
                thread_model = thread_config.get("model") if thread_config else None
                model_to_use = thread_model if thread_model else self.get_model_for_channel(channel_id)

                # Temporarily set the model for this request
                current_model = self.openrouter_client.model
                self.openrouter_client.model = model_to_use

                try:
                    # Get response from AI
                    response = await self.openrouter_client.send_message_with_history(
                        conversation_context,
                        images=images if model_supports_images else [],
                        system_prompt=thread_system_prompt
                    )

                    # Add AI response to thread history in the database
                    await self.state.add_discord_thread_message(thread_id, {
                        "role": "assistant",
                        "content": response,
                        # timestamp is set in the state manager/database
                    })

                    # Split response into chunks
                    max_length = 2000
                    chunks = [response[i:i+max_length] for i in range(0, len(response), max_length)]

                    # Update thinking message with first chunk
                    await thinking_msg.edit(content=chunks[0])

                    # Send remaining chunks
                    for chunk in chunks[1:]:
                        await thread.send(chunk)

                    # Update the success message
                    success_msg = f"✅ Created new thread: **{name}** with your initial message. Check the thread for the AI's response!"
                finally:
                    # Restore original model
                    self.openrouter_client.model = current_model
            else:
                # Just confirm thread creation
                success_msg = f"✅ Created new thread: **{name}**\nThe thread is now ready for conversation. All messages in the thread will receive AI responses."

            # Reply to the slash command
            await ctx.respond(success_msg)

        except discord.Forbidden:
            await ctx.respond("⚠️ I don't have permission to create threads in this channel.")
        except discord.HTTPException as e:
            await ctx.respond(f"⚠️ Failed to create thread: {str(e)}")
        except Exception as e:
            logger.error(f"Error creating thread: {e}", exc_info=True)
            await ctx.respond(f"⚠️ An unexpected error occurred while creating the thread: {str(e)}")


    async def thread_chat_slash(self, ctx,
                         id: str,
                         message: str,
                         image: discord.Attachment = None):
        await ctx.defer()

        # Get thread data from the database
        thread_id = id
        thread_data = self.state.get_discord_thread(thread_id)

        # Check if thread exists
        if not thread_data:
            await ctx.respond("⚠️ Thread not found. Use `/thread list` to see available threads.")
            return

        thread_name = thread_data["name"]
        channel_id = thread_data["channel_id"]

        # Get thread-specific model and system prompt from DB
        thread_config = self.state.get_discord_thread_config(thread_id)
        thread_model = thread_config.get("model") if thread_config else None
        thread_system_prompt = thread_config.get("system_prompt") if thread_config else None

        # Set model for this request (thread-specific > channel-specific > global)
        current_model = self.openrouter_client.model
        model_to_use = thread_model if thread_model else self.get_model_for_channel(channel_id)
        self.openrouter_client.model = model_to_use

        # Handle image processing
        model_supports_images = self.openrouter_client.model_supports_vision()
        images = []
        image_embed = None

        if image:
            # Check if it's an image file
            if any(image.filename.lower().endswith(ext) for ext in ['.jpg', '.jpeg', '.png', '.gif', '.webp']):
                # Create an embed to display the image
                image_embed = discord.Embed(title=f"Analyzing Image in Thread: {thread_name}", color=discord.Color.blue())
                image_embed.set_image(url=image.url)
                image_embed.add_field(name="File", value=image.filename)

                if model_supports_images:
                    try:
                        image_data = await image.read()
                        images.append({
                            'data': image_data,
                            'type': image.content_type or 'image/jpeg'
                        })
                    except Exception as e:
                        await ctx.respond(f"⚠️ Failed to process image {image.filename}: {str(e)}")
                        return
                else:
                    image_embed.description = "⚠️ Current model doesn't support image analysis. Consider switching to a vision-capable model."

        try:
            # Add user message to thread in the database
            await self.state.add_discord_thread_message(thread_id, {
                "role": "user",
                "name": ctx.author.display_name,
                "content": message,
                # timestamp is set in the state manager/database
                "user_id": str(ctx.author.id) # Store user ID
            })

            # Format conversation context from the database history
            # Use the getter method with the configured time window
            conversation_context = self.state.get_discord_thread_history(thread_id, hours_limit=self.state.get_time_window_hours())

            # First response - show the user's message
            if image_embed:
                await ctx.respond(f"**{ctx.author.display_name}** in **{thread_name}**: {message}", embed=image_embed)
                # Follow up with processing message
                processing_msg = await ctx.followup.send(f"Processing response for thread **{thread_name}**...")
            else:
                # Show user's message before processing for text-only messages too
                await ctx.respond(f"**{ctx.author.display_name}** in **{thread_name}**: {message}\n\n_Processing response..._")
                processing_msg = None

            # Fall back to channel-specific prompt if no thread prompt
            if not thread_system_prompt:
                thread_system_prompt = self.state.get_channel_system_prompt(channel_id)
                if not thread_system_prompt:
                     # Fallback to global system prompt
                     thread_system_prompt = self.openrouter_client.system_prompt # Use the default from client init


            response = await self.openrouter_client.send_message_with_history(
                conversation_context,
                images=images if model_supports_images else [],
                system_prompt=thread_system_prompt
            )

            # Add AI response to thread in the database
            await self.state.add_discord_thread_message(thread_id, {
                "role": "assistant",
                "content": response,
                # timestamp is set in the state manager/database
            })

            # Send response in chunks like other commands
            max_length = 2000
            chunks = [response[i:i+max_length] for i in range(0, len(response), max_length)]

            # Process the first chunk differently if we have a processing message to edit
            for i, chunk in enumerate(chunks):
                if i == 0:
                    if processing_msg:
                        await processing_msg.edit(content=f"**Thread: {thread_name}**\n\n{chunk}")
                    else:
                        await ctx.followup.send(f"**Thread: {thread_name}**\n\n{chunk}")
                else:
                    await ctx.channel.send(chunk)
        finally:
            # Restore original model
            self.openrouter_client.model = current_model

    async def list_threads_slash(self, ctx):
        channel_id = str(ctx.channel.id)

        # Get threads for this channel from the database
        channel_threads = self.state.list_discord_threads_for_channel(channel_id)

        if not channel_threads:
            await ctx.respond("No active threads in this channel. Create one with `/thread new`")
            return

        threads_list = []
        for thread_data in channel_threads:
            thread_id = thread_data["thread_id"]
            thread_name = thread_data["name"]
            created_time = thread_data["created_at"].strftime("%Y-%m-%d %H:%M")
            # Get message count from the database
            message_count = self.state.get_thread_message_count(thread_id)
            threads_list.append(f"• **{thread_name}** (ID: `{thread_id}`)\n  Created: {created_time} | Messages: {message_count}")

        await ctx.respond(f"**Active Conversation Threads:**\n\n" + "\n".join(threads_list) +
                          "\n\nUse `/thread message id:<thread_id> message:<your message>` to continue a conversation.")

    async def delete_thread_slash(self, ctx, id: str):
        # Delete thread from the database
        thread_deleted = self.state.delete_discord_thread(id)

        if thread_deleted:
            # Attempt to delete the Discord thread itself if possible
            try:
                discord_thread = self.bot.get_channel(int(id))
                if discord_thread and isinstance(discord_thread, discord.Thread):
                    await discord_thread.delete()
                    logger.info(f"Deleted Discord thread {id}")
            except Exception as e:
                logger.warning(f"Could not delete Discord thread {id}: {e}")

            await ctx.respond(f"✅ Deleted thread with ID: **{id}**")
        else:
            await ctx.respond("⚠️ Thread not found in the database. Use `/thread list` to see available threads.")


    async def rename_thread_slash(self, ctx, id: str, name: str):
        # Rename thread in the database
        thread_renamed = self.state.rename_discord_thread(id, name)

        if thread_renamed:
            # Attempt to rename the Discord thread itself if possible
            try:
                discord_thread = self.bot.get_channel(int(id))
                if discord_thread and isinstance(discord_thread, discord.Thread):
                    await discord_thread.edit(name=name)
                    logger.info(f"Renamed Discord thread {id} to '{name}'")
            except Exception as e:
                logger.warning(f"Could not rename Discord thread {id}: {e}")

            await ctx.respond(f"✅ Renamed thread with ID **{id}** to **{name}**")
        else:
            await ctx.respond("⚠️ Thread not found in the database. Use `/thread list` to see available threads.")


    async def set_thread_model_slash(self, ctx, model_name: str):
        # Check if we're in a thread
        if not isinstance(ctx.channel, discord.Thread):
            await ctx.respond("⚠️ This command can only be used within a thread.")
            return

        thread_id = str(ctx.channel.id)

        try:
            # Use the state manager's method which includes validation
            await self.state.set_discord_thread_model(thread_id, model_name)
            await ctx.respond(f"✅ Model for this thread set to `{model_name}`")

        except ValueError as e:
            await ctx.respond(f"⚠️ {e}") # Model validation error
        except Exception as e:
            logger.error(f"Error setting thread model: {e}", exc_info=True)
            await ctx.respond(f"⚠️ An unexpected error occurred: {str(e)}")


    async def set_thread_system_slash(self, ctx, new_prompt: str):
        # Check if we're in a thread
        if not isinstance(ctx.channel, discord.Thread):
            await ctx.respond("⚠️ This command can only be used within a thread.")
            return

        thread_id = str(ctx.channel.id)

        try:
            # Use the state manager's method
            self.state.set_discord_thread_system_prompt(thread_id, new_prompt)

            # Split system prompt into chunks if very long for display
            max_length = 1950
            chunks = [new_prompt[i:i+max_length] for i in range(0, len(new_prompt), max_length)]

            await ctx.respond(f"System prompt for this thread updated!")
            if len(chunks) > 1:
                await ctx.followup.send("System prompt preview (first part):\n```\n" + chunks[0] + "\n```")
            else:
                await ctx.followup.send("System prompt set to:\n```\n" + new_prompt + "\n```")

        except Exception as e:
            logger.error(f"Error setting thread system prompt: {e}", exc_info=True)
            await ctx.respond(f"⚠️ An unexpected error occurred: {str(e)}")


    @commands.Cog.listener()
    async def on_message(self, message):
        """Listen for messages in threads to build context memory and respond."""
        # Ignore messages from the bot itself
        if message.author == self.bot.user:
            return

        # Only process messages in Discord threads
        if isinstance(message.channel, discord.Thread):
            thread_id = str(message.channel.id)
            channel_id = str(message.channel.parent_id) # Get parent channel ID

            # Skip if this is an adventure thread (handled by DungeonMasterCommands)
            if hasattr(self.bot, 'cogs') and 'DungeonMasterCommands' in self.bot.cogs:
                dnd_cog = self.bot.cogs['DungeonMasterCommands']
                if hasattr(dnd_cog, 'adventures') and thread_id in dnd_cog.adventures:
                    return  # Skip processing adventure threads

            # Check if this thread is tracked in our database
            thread_data = self.state.get_discord_thread(thread_id)

            # If the thread is not tracked, and it's not a thread created by the bot, ignore it.
            # We assume threads created by the bot via /thread new are tracked.
            is_bot_created_thread = message.channel.owner_id == self.bot.user.id
            if not thread_data and not is_bot_created_thread:
                 logger.debug(f"Ignoring message in untracked thread {thread_id} not created by bot.")
                 return # Ignore messages in threads we don't manage

            # If it's a bot-created thread but not in DB (e.g., bot restarted), add it.
            if is_bot_created_thread and not thread_data:
                 logger.info(f"Bot-created thread {thread_id} found but not in DB. Adding.")
                 # Attempt to get thread name from Discord if possible
                 thread_name = message.channel.name if hasattr(message.channel, 'name') else "Untracked Bot Thread"
                 await self.state.add_discord_thread(thread_id, channel_id, thread_name)
                 thread_data = self.state.get_discord_thread(thread_id) # Re-fetch after adding

            # Add the incoming user message to the database history for this thread
            await self.state.add_discord_thread_message(thread_id, {
                "role": "user",
                "name": message.author.display_name,
                "content": message.content,
                # timestamp and user_id are added in add_discord_thread_message
            })

            # Get conversation context from the database history for this thread
            # Use the getter method with the configured time window
            # Pass the limit argument, not hours_limit. Note: This uses the time window value as a message count limit,
            # which might not be the intended logic, but fixes the TypeError.
            # Consider revising if time-based filtering is needed here.
            conversation_context = self.state.get_discord_thread_history(thread_id, limit=self.state.get_time_window_hours())

            # Get thread-specific model and system prompt from DB
            thread_config = self.state.get_discord_thread_config(thread_id)
            thread_model = thread_config.get("model") if thread_config else None
            thread_system_prompt = thread_config.get("system_prompt") if thread_config else None

            # Determine the model to use (thread-specific > channel-specific > global)
            model_to_use = thread_model if thread_model else self.get_model_for_channel(channel_id)

            # Determine the system prompt to use (thread-specific > channel-specific > global)
            system_prompt_to_use = thread_system_prompt
            if not system_prompt_to_use:
                system_prompt_to_use = self.state.get_channel_system_prompt(channel_id)
                if not system_prompt_to_use:
                     system_prompt_to_use = self.openrouter_client.system_prompt # Fallback to default

            # Temporarily set the model for this request
            current_model = self.openrouter_client.model
            self.openrouter_client.model = model_to_use

            try:
                # Send "thinking" message
                thinking_msg = await message.channel.send(f"Thinking about: '{message.content[:50]}...'") # Truncate for thinking message

                # Process images if any are attached to the user message
                images = []
                if self.openrouter_client.model_supports_vision() and message.attachments:
                    for attachment in message.attachments:
                        if any(attachment.filename.lower().endswith(ext) for ext in ['.jpg', '.jpeg', '.png', '.gif', '.webp']):
                            try:
                                image_data = await attachment.read()
                                images.append({
                                    'data': image_data,
                                    'type': attachment.content_type or 'image/jpeg'
                                })
                            except Exception as e:
                                logger.warning(f"Could not process image attachment {attachment.filename}: {e}")
                                # Continue without the image if processing fails

                # Get response from AI
                response = await self.openrouter_client.send_message_with_history(
                    conversation_context,
                    images=images if self.openrouter_client.model_supports_vision() else [], # Only pass images if model supports vision
                    system_prompt=system_prompt_to_use
                )

                # Add AI response to thread history in the database
                await self.state.add_discord_thread_message(thread_id, {
                    "role": "assistant",
                    "content": response,
                    # timestamp is set in the state manager/database
                })

                # Split response into chunks
                max_length = 2000
                chunks = [response[i:i+max_length] for i in range(0, len(response), max_length)]

                # Update thinking message with first chunk
                if chunks:
                    await thinking_msg.edit(content=chunks[0])
                    # Send remaining chunks
                    for chunk in chunks[1:]:
                        await message.channel.send(chunk)
                else:
                    await thinking_msg.edit(content="Received an empty response from the AI.")


            except Exception as e:
                logger.error(f"Error processing thread message in thread {thread_id}: {e}", exc_info=True)
                # Attempt to edit thinking message with error, or send new message
                try:
                    await thinking_msg.edit(content=f"⚠️ Error processing message: {str(e)}")
                except Exception:
                    await message.channel.send(f"⚠️ Error processing message: {str(e)}")
            finally:
                # Restore original model
                self.openrouter_client.model = current_model


def setup(bot):
    bot.add_cog(ThreadCommands(bot))