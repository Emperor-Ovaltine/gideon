"""Thread-based conversation commands."""
import discord
import random
import logging
from discord.ext import commands
from ..utils.state_manager import BotStateManager
from ..utils.openrouter_client import OpenRouterClient
from ..config import OPENROUTER_API_KEY, SYSTEM_PROMPT, ALLOWED_MODELS, DEFAULT_MODEL
from datetime import datetime, timedelta

# Create logger
logger = logging.getLogger(__name__)

class ThreadCommands(commands.Cog):
    """Commands for managing AI conversation threads."""
    
    def __init__(self, bot):
        self.bot = bot
        self.state = BotStateManager()
        self.openrouter_client = OpenRouterClient(OPENROUTER_API_KEY, SYSTEM_PROMPT, DEFAULT_MODEL)
        
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
        all_models = await self.bot.model_manager.get_models()
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
            
            # Store basic thread information in our tracking dict
            self.state.discord_threads[str(thread.id)] = {
                "name": name,
                "channel_id": str(ctx.channel.id),
                "created_at": datetime.now(),
                "model": self.state.get_effective_model(str(ctx.channel.id))
            }
            
            # Add to thread tracking if we also use the old system
            channel_id = str(ctx.channel.id)
            thread_id = f"{channel_id}-{thread.id}"
            
            # Create simple ID for easier reference
            simple_id = ''.join(random.choices('abcdefghijklmnopqrstuvwxyz0123456789', k=5))
            
            # Initialize channel in threads dict if needed
            if channel_id not in self.state.threads:
                self.state.threads[channel_id] = {}
                
            # Add thread to threads dict
            self.state.threads[channel_id][thread_id] = {
                "name": name,
                "messages": [],
                "created_at": datetime.now(),
                "simple_id": simple_id,
                "model": self.state.get_effective_model(channel_id)
            }
            
            # Map simple ID to full thread ID
            self.state.simple_id_mapping[simple_id] = thread_id
            
            # Welcome message in the thread
            welcome_msg = f"✅ Thread created! You can chat with the AI by just sending regular messages in this thread. I'll respond to everything automatically."
            await thread.send(welcome_msg)
            
            # If a message was provided, process it immediately in the new thread
            if message:
                # Add user message to thread history
                self.state.threads[channel_id][thread_id]["messages"].append({
                    "role": "user",
                    "name": ctx.author.display_name,
                    "content": message,
                    "timestamp": datetime.now()
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
                
                # Send thinking message in the thread
                thinking_msg = await thread.send(f"**{ctx.author.display_name}**: {message}\n\n_Processing response..._")
                
                # Format conversation context - just the first message in this case
                conversation_context = [{
                    "role": "user",
                    "content": f"{ctx.author.display_name}: {message}"
                }]
                
                # Get response from AI
                response = await self.openrouter_client.send_message_with_history(
                    conversation_context,
                    images=images if model_supports_images else []
                )
                
                # Add AI response to thread history
                self.state.threads[channel_id][thread_id]["messages"].append({
                    "role": "assistant",
                    "content": response,
                    "timestamp": datetime.now()
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
            else:
                # Just confirm thread creation
                success_msg = f"✅ Created new thread: **{name}**\nThe thread is now ready for conversation. All messages in the thread will receive AI responses."
            
            # Reply to the slash command
            await ctx.respond(success_msg)
            
        except discord.Forbidden:
            await ctx.respond("⚠️ I don't have permission to create threads in this channel.")
        except discord.HTTPException as e:
            await ctx.respond(f"⚠️ Failed to create thread: {str(e)}")

    async def thread_chat_slash(self, ctx,
                         id: str,
                         message: str,
                         image: discord.Attachment = None):
        await ctx.defer()
        
        # Check if this is a simple ID or a full thread ID
        thread_id = None
        if id in self.state.simple_id_mapping:
            # This is a simple ID, get the full thread ID
            thread_id = self.state.simple_id_mapping[id]
            channel_id = thread_id.split('-')[0]
        else:
            # Try to parse as a full thread ID
            try:
                channel_id = id.split('-')[0]
                # Search through threads to find the matching ID
                found = False
                for thread_key in self.state.threads.get(channel_id, {}):
                    if id == thread_key or (
                        "simple_id" in self.state.threads[channel_id][thread_key] and 
                        self.state.threads[channel_id][thread_key]["simple_id"] == id
                    ):
                        thread_id = thread_key
                        found = True
                        break
                
                if not found:
                    await ctx.respond("⚠️ Thread not found. Use `/thread list` to see available threads.")
                    return
            except:
                await ctx.respond("⚠️ Invalid thread ID format. Use `/thread list` to see available threads.")
                return
        
        # Check if thread exists
        if channel_id not in self.state.threads or thread_id not in self.state.threads[channel_id]:
            await ctx.respond("⚠️ Thread not found. Use `/thread list` to see available threads.")
            return
        
        thread_data = self.state.threads[channel_id][thread_id]
        thread_name = thread_data["name"]
        
        # Set model for this thread if different from current
        current_model = self.openrouter_client.model
        thread_model = thread_data.get("model")
        
        if thread_model:
            self.openrouter_client.model = thread_model
        
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
            # Add user message to thread
            thread_data["messages"].append({
                "role": "user",
                "name": ctx.author.display_name,
                "content": message,
                "timestamp": datetime.now()
            })
            
            # Format conversation context
            conversation_context = []
            # Add only messages from this thread
            for msg in thread_data["messages"]:
                if "timestamp" not in msg or datetime.now() - msg["timestamp"] <= timedelta(hours=self.state.time_window_hours):
                    conversation_context.append({
                        "role": msg["role"],
                        "content": f"{msg['name']}: {msg['content']}" if "name" in msg else msg["content"]
                    })
            
            # First response - show the user's message
            if image_embed:
                await ctx.respond(f"**{ctx.author.display_name}** in **{thread_name}**: {message}", embed=image_embed)
                # Follow up with processing message
                processing_msg = await ctx.followup.send(f"Processing response for thread **{thread_name}**...")
            else:
                # Show user's message before processing for text-only messages too
                await ctx.respond(f"**{ctx.author.display_name}** in **{thread_name}**: {message}\n\n_Processing response..._")
                processing_msg = None
            
            # Get thread-specific system prompt
            thread_system_prompt = None
            if thread_id in self.state.discord_threads:
                thread_system_prompt = self.state.discord_threads[thread_id].get("system_prompt")
            
            # Or fall back to channel-specific prompt
            if not thread_system_prompt:
                thread_system_prompt = self.state.get_channel_system_prompt(channel_id)
            
            response = await self.openrouter_client.send_message_with_history(
                conversation_context,
                images=images if model_supports_images else [],
                system_prompt=thread_system_prompt
            )
            
            # Add AI response to thread
            thread_data["messages"].append({
                "role": "assistant",
                "content": response,
                "timestamp": datetime.now()
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
            if thread_model:
                self.openrouter_client.model = current_model

    async def list_threads_slash(self, ctx):
        channel_id = str(ctx.channel.id)
        
        if channel_id not in self.state.threads or not self.state.threads[channel_id]:
            await ctx.respond("No active threads in this channel. Create one with `/thread new`")
            return
        
        threads_list = []
        for thread_id, thread_data in self.state.threads[channel_id].items():
            thread_name = thread_data["name"]
            message_count = len(thread_data["messages"])
            created_time = thread_data["created_at"].strftime("%Y-%m-%d %H:%M")
            simple_id = thread_data.get("simple_id", thread_id.split('-')[1] if '-' in thread_id else "???")
            threads_list.append(f"• **{thread_name}** (ID: `{simple_id}`)\n  Created: {created_time} | Messages: {message_count}")
        
        await ctx.respond(f"**Active Conversation Threads:**\n\n" + "\n".join(threads_list) + 
                          "\n\nUse `/thread message id:<thread_id> message:<your message>` to continue a conversation.")

    async def delete_thread_slash(self, ctx, 
                           id: str):
        # Check if this is a simple ID
        thread_id = None
        channel_id = None
        
        if id in self.state.simple_id_mapping:
            # This is a simple ID, get the full thread ID
            thread_id = self.state.simple_id_mapping[id]
            channel_id = thread_id.split('-')[0]
            
            # Clean up the mapping when deleting
            del self.state.simple_id_mapping[id]
        else:
            # Try to parse as a full thread ID
            try:
                channel_id = id.split('-')[0]
                # Search through threads to find the matching ID
                for thread_key in list(self.state.threads.get(channel_id, {}).keys()):
                    if id == thread_key or (
                        "simple_id" in self.state.threads[channel_id][thread_key] and 
                        self.state.threads[channel_id][thread_key]["simple_id"] == id
                    ):
                        thread_id = thread_key
                        # Also clean up the mapping
                        simple_id = self.state.threads[channel_id][thread_key].get("simple_id")
                        if simple_id in self.state.simple_id_mapping:
                            del self.state.simple_id_mapping[simple_id]
                        break
            except:
                await ctx.respond("⚠️ Invalid thread ID format. Use `/thread list` to see available threads.")
                return
        
        if not thread_id or channel_id not in self.state.threads or thread_id not in self.state.threads[channel_id]:
            await ctx.respond("⚠️ Thread not found. Use `/thread list` to see available threads.")
            return
        
        thread_name = self.state.threads[channel_id][thread_id]["name"]
        del self.state.threads[channel_id][thread_id]
        
        # Clean up empty channel entries
        if not self.state.threads[channel_id]:
            del self.state.threads[channel_id]
            
        await ctx.respond(f"✅ Deleted thread: **{thread_name}**")

    async def rename_thread_slash(self, ctx, 
                           id: str,
                           name: str):
        # Check if this is a simple ID
        thread_id = None
        channel_id = None
        
        if id in self.state.simple_id_mapping:
            # This is a simple ID, get the full thread ID
            thread_id = self.state.simple_id_mapping[id]
            channel_id = thread_id.split('-')[0]
        else:
            # Try to parse as a full thread ID
            try:
                channel_id = id.split('-')[0]
                # Search through threads to find the matching ID
                for thread_key in self.state.threads.get(channel_id, {}).keys():
                    if id == thread_key or (
                        "simple_id" in self.state.threads[channel_id][thread_key] and 
                        self.state.threads[channel_id][thread_key]["simple_id"] == id
                    ):
                        thread_id = thread_key
                        break
            except:
                await ctx.respond("⚠️ Invalid thread ID format. Use `/thread list` to see available threads.")
                return
        
        if not thread_id or channel_id not in self.state.threads or thread_id not in self.state.threads[channel_id]:
            await ctx.respond("⚠️ Thread not found. Use `/thread list` to see available threads.")
            return
        
        old_name = self.state.threads[channel_id][thread_id]["name"]
        self.state.threads[channel_id][thread_id]["name"] = name
        
        await ctx.respond(f"✅ Renamed thread from **{old_name}** to **{name}**")

    async def set_thread_model_slash(self, ctx, model_name: str):
        # Check if we're in a thread
        if not isinstance(ctx.channel, discord.Thread):
            await ctx.respond("⚠️ This command can only be used within a thread.")
            return
            
        try:
            # Get all available models
            all_models = await self.bot.model_manager.get_models()
            
            # Case-insensitive model validation
            model_found = False
            valid_model_name = model_name  # Default to the provided name
            
            for model in all_models:
                # Handle both string models and model objects
                model_str = str(model)
                if model_str.lower() == model_name.lower():
                    valid_model_name = model_str  # Use the correctly cased model name
                    model_found = True
                    break
                    
            if not model_found:
                # Show available models in the error message
                model_list = "\n".join([str(m) for m in all_models[:10]])
                await ctx.respond(f"⚠️ Model `{model_name}` not found. Available models include:\n```\n{model_list}\n```")
                return
                
            # Use the validated model name
            model_name = valid_model_name
                
        except Exception as e:
            await ctx.respond(f"⚠️ Error validating model: {str(e)}")
            return
        
        thread_id = str(ctx.channel.id)
        channel_id = str(ctx.channel.parent_id)
        full_thread_id = f"{channel_id}-{thread_id}"
        
        # Initialize discord_threads if it doesn't exist
        if not hasattr(self.state, 'discord_threads'):
            self.state.discord_threads = {}
            
        # Create or update thread entry in discord_threads
        if thread_id not in self.state.discord_threads:
            self.state.discord_threads[thread_id] = {
                "name": ctx.channel.name,
                "channel_id": channel_id,
                "created_at": datetime.now()
            }
        
        # Set the model in discord_threads
        self.state.discord_threads[thread_id]["model"] = model_name
        
        # Also update in the threads dictionary if it exists
        if channel_id in self.state.threads and full_thread_id in self.state.threads[channel_id]:
            self.state.threads[channel_id][full_thread_id]["model"] = model_name
        
        await ctx.respond(f"✅ Model for this thread set to `{model_name}`")

    async def set_thread_system_slash(self, ctx, new_prompt: str):
        # Check if we're in a thread
        if not isinstance(ctx.channel, discord.Thread):
            await ctx.respond("⚠️ This command can only be used within a thread.")
            return
            
        thread_id = str(ctx.channel.id)
        
        # Initialize discord_threads if it doesn't exist
        if not hasattr(self.state, 'discord_threads'):
            self.state.discord_threads = {}
            
        # Create or update thread entry
        if thread_id not in self.state.discord_threads:
            self.state.discord_threads[thread_id] = {
                "name": ctx.channel.name,
                "channel_id": str(ctx.channel.parent_id),
                "created_at": datetime.now()
            }
        
        # Set the system prompt
        self.state.discord_threads[thread_id]["system_prompt"] = new_prompt
        
        # Split system prompt into chunks if very long
        max_length = 1950
        chunks = [new_prompt[i:i+max_length] for i in range(0, len(new_prompt), max_length)]
        
        await ctx.respond(f"System prompt for this thread updated!")
        if len(chunks) > 1:
            await ctx.followup.send("System prompt preview (first part):\n```\n" + chunks[0] + "\n```")
        else:
            await ctx.followup.send("System prompt set to:\n```\n" + new_prompt + "\n```")

    @commands.Cog.listener()
    async def on_message(self, message):
        """Listen for messages in threads to build context memory"""
        # Ignore messages from the bot itself
        if message.author == self.bot.user:
            return
            
        # Check if this is in a thread
        if isinstance(message.channel, discord.Thread):
            thread_id = str(message.channel.id)
            
            # Skip if this is an adventure thread (handled by DungeonMasterCommands)
            if hasattr(self.bot, 'cogs') and 'DungeonMasterCommands' in self.bot.cogs:
                dnd_cog = self.bot.cogs['DungeonMasterCommands']
                if hasattr(dnd_cog, 'adventures') and thread_id in dnd_cog.adventures:
                    return  # Skip processing adventure threads
            
            # Only process thread messages if:
            # 1. We have the thread in our tracking dict, or
            # 2. The thread was created from a message by the bot
            is_bot_thread = message.channel.owner_id == self.bot.user.id
            is_tracked_thread = thread_id in self.state.discord_threads
            
            if is_tracked_thread or is_bot_thread:
                # Get recent history
                async for msg in message.channel.history(limit=self.state.max_channel_history):
                    if msg.author == self.bot.user:
                        continue  # Skip the bot's own messages when looking for the last response
                    
                    # We found a user message, now we should respond
                    if msg.id == message.id:
                        thread_model = None
                        if thread_id in self.state.discord_threads:
                            thread_model = self.state.discord_threads[thread_id].get("model")
                        
                        # Set thread-specific model if available, otherwise use global
                        current_model = self.openrouter_client.model
                        if thread_model:
                            logger.debug(f"Using thread-specific model: {thread_model} for thread {thread_id}")
                            self.openrouter_client.model = thread_model
                        else:
                            channel_id = str(message.channel.parent_id)
                            model = self.get_model_for_channel(channel_id)
                            logger.debug(f"Using channel model: {model} for thread {thread_id}")
                            self.openrouter_client.model = model
                        
                        try:
                            # Get thread history for context
                            history = []
                            async for hist_msg in message.channel.history(limit=self.state.max_channel_history):
                                if hist_msg.author == self.bot.user:
                                    history.append({
                                        "role": "assistant",
                                        "content": hist_msg.content
                                    })
                                else:
                                    history.append({
                                        "role": "user",
                                        "content": f"{hist_msg.author.display_name}: {hist_msg.content}"
                                    })
                            
                            # Reverse to get chronological order
                            history.reverse()
                            
                            # Send "thinking" message
                            thinking_msg = await message.channel.send(f"Thinking about: '{message.content}'...")
                            
                            # Process images if any are attached
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
                                            await message.channel.send(f"⚠️ Failed to process image {attachment.filename}: {str(e)}")
                            
                            # Send to API
                            response = await self.openrouter_client.send_message_with_history(history, images=images)
                            
                            # Check if the response is an error
                            if response.startswith("⚠️"):
                                # For errors, don't split into chunks, just show the error
                                await thinking_msg.edit(content=response)
                            else:
                                # Split response into chunks
                                max_length = 2000
                                chunks = [response[i:i+max_length] for i in range(0, len(response), max_length)]
                                
                                # Update thinking message with first chunk
                                await thinking_msg.edit(content=chunks[0])
                                
                                # Send remaining chunks
                                for chunk in chunks[1:]:
                                    await message.channel.send(chunk)
                                
                                # Add both the user's message and the bot's response to thread storage
                                # Let's find the appropriate thread ID in our threads dictionary
                                channel_id = str(message.channel.parent_id)
                                full_thread_id = f"{channel_id}-{thread_id}"
                                
                                # Ensure thread exists in our data
                                if channel_id in self.state.threads and full_thread_id in self.state.threads[channel_id]:
                                    # Add user message
                                    self.state.threads[channel_id][full_thread_id]["messages"].append({
                                        "role": "user",
                                        "name": message.author.display_name,
                                        "content": message.content,
                                        "timestamp": datetime.now()
                                    })
                                    
                                    # Add assistant response
                                    self.state.threads[channel_id][full_thread_id]["messages"].append({
                                        "role": "assistant",
                                        "content": response,
                                        "timestamp": datetime.now()
                                    })
                                    
                                # Also record messages in simple discord_threads dict if needed
                                if thread_id in self.state.discord_threads:
                                    if "messages" not in self.state.discord_threads[thread_id]:
                                        self.state.discord_threads[thread_id]["messages"] = []
                                    
                                    # Add user message
                                    self.state.discord_threads[thread_id]["messages"].append({
                                        "role": "user",
                                        "name": message.author.display_name,
                                        "content": message.content,
                                        "timestamp": datetime.now()
                                    })
                                    
                                    # Add assistant response
                                    self.state.discord_threads[thread_id]["messages"].append({
                                        "role": "assistant",
                                        "content": response,
                                        "timestamp": datetime.now()
                                    })
                        
                        finally:
                            # Restore original model
                            if thread_model:
                                self.openrouter_client.model = current_model
                        
                        break  # We've processed this message, no need to continue the loop

def setup(bot):
    bot.add_cog(ThreadCommands(bot))