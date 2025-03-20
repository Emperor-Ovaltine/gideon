import asyncio
import logging
import socket
import random
from discord.ext import commands, tasks
import discord  # Correct import
from ..utils.openrouter_client import OpenRouterClient
from ..config import OPENROUTER_API_KEY, SYSTEM_PROMPT, ALLOWED_MODELS, DEFAULT_MODEL
from datetime import datetime, timedelta

logger = logging.getLogger('llm_chat')

# Create a group for AI-related commands
ai_group = discord.SlashCommandGroup(
    "ai", 
    "AI chat commands and utilities"
)

# Create a group for thread-related commands
thread_group = discord.SlashCommandGroup(
    "thread", 
    "Thread conversation commands"
)

class LLMChat(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.openrouter_client = OpenRouterClient(OPENROUTER_API_KEY, SYSTEM_PROMPT, DEFAULT_MODEL)
        self.channel_history = {}
        self.channel_models = {}
        self.threads = {}
        self.max_channel_history = 35
        self.max_threads_per_channel = 10
        self.time_window_hours = 48
        self.prune_task.start()
        self.simple_id_mapping = {}
        self.discord_threads = {}
        
    # Register the command groups with the cog
    ai = ai_group
    thread = thread_group

    async def check_internet_connection(self):
        try:
            # Try to resolve a well-known domain
            await asyncio.get_event_loop().getaddrinfo('google.com', 443)
            return True
        except socket.gaierror:
            return False
    
    @commands.Cog.listener()
    async def on_message(self, message):
        """Listen for messages in channels and threads to build context memory"""
        # Ignore messages from the bot itself
        if message.author == self.bot.user:
            return
            
        # Check if this is in a thread
        if isinstance(message.channel, discord.Thread):
            thread_id = str(message.channel.id)
            
            # Only process thread messages if:
            # 1. We have the thread in our tracking dict, or
            # 2. The thread was created from a message by the bot
            is_bot_thread = message.channel.owner_id == self.bot.user.id
            is_tracked_thread = thread_id in self.discord_threads
            
            if is_tracked_thread or is_bot_thread:
                # Get recent history
                async for msg in message.channel.history(limit=self.max_channel_history):
                    if msg.author == self.bot.user:
                        continue  # Skip the bot's own messages when looking for the last response
                    
                    # We found a user message, now we should respond
                    if msg.id == message.id:
                        # This is the message we're currently processing
                        thread_model = None
                        if thread_id in self.discord_threads:
                            thread_model = self.discord_threads[thread_id].get("model")
                        
                        # Set thread-specific model if available
                        current_model = self.openrouter_client.model
                        if thread_model:
                            self.openrouter_client.model = thread_model
                        
                        try:
                            # Get thread history for context
                            history = []
                            async for hist_msg in message.channel.history(limit=self.max_channel_history):
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
                            
                            # Split response into chunks
                            max_length = 2000
                            chunks = [response[i:i+max_length] for i in range(0, len(response), max_length)]
                            
                            # Update thinking message with first chunk
                            await thinking_msg.edit(content=chunks[0])
                            
                            # Send remaining chunks
                            for chunk in chunks[1:]:
                                await message.channel.send(chunk)
                                
                        finally:
                            # Restore original model
                            if thread_model:
                                self.openrouter_client.model = current_model
                        
                        break  # We've processed this message, no need to continue the loop
        
        # Continue with existing channel message processing...
        elif isinstance(message.channel, discord.TextChannel):
            # Your existing channel history tracking code...
            channel_id = str(message.channel.id)
            
            # Initialize this channel's history if it doesn't exist
            if channel_id not in self.channel_history:
                self.channel_history[channel_id] = []
                
            # Add the message to the channel history
            self.channel_history[channel_id].append({
                "role": "user",
                "name": message.author.display_name,
                "content": message.content,
                "timestamp": datetime.now()
            })
            
            # Keep history within size limits
            if len(self.channel_history[channel_id]) > self.max_channel_history:
                self.channel_history[channel_id] = self.channel_history[channel_id][-self.max_channel_history:]

    async def get_channel_context(self, channel_id):
        """Get the conversation context for a channel"""
        if channel_id not in self.channel_history:
            return []
            
        # Get messages from the past X hours
        cutoff_time = datetime.now() - timedelta(hours=self.time_window_hours)
        recent_messages = [
            {
                "role": msg["role"],
                "content": f"{msg['name']}: {msg['content']}" if "name" in msg else msg["content"]
            }
            for msg in self.channel_history[channel_id]
            if msg["timestamp"] > cutoff_time
        ]
        
        # Limit to max_channel_history most recent messages
        return recent_messages[-self.max_channel_history:]

    async def prune_inactive_channels(self):
        """Remove history and model settings for channels inactive for more than 7 days"""
        cutoff = datetime.now() - timedelta(days=7)
        inactive_channels = []
        
        for channel_id, history in self.channel_history.items():
            if not history:
                continue
            last_message = history[-1]["timestamp"]
            if last_message < cutoff:
                inactive_channels.append(channel_id)
        
        for channel_id in inactive_channels:
            del self.channel_history[channel_id]
            # Also remove channel model settings if they exist
            if channel_id in self.channel_models:
                del self.channel_models[channel_id]
        
        # Also prune inactive threads
        for channel_id in list(self.threads.keys()):
            inactive_threads = []
            for thread_id, thread_data in self.threads[channel_id].items():
                if not thread_data["messages"]:
                    continue
                last_message_time = thread_data["messages"][-1]["timestamp"]
                # Prune threads after 14 days of inactivity
                if last_message_time < datetime.now() - timedelta(days=14):
                    inactive_threads.append(thread_id)
            
            # Remove inactive threads
            for thread_id in inactive_threads:
                del self.threads[channel_id][thread_id]
                
            # Clean up empty channel entries
            if not self.threads[channel_id]:
                del self.threads[channel_id]
    
    @tasks.loop(hours=24)
    async def prune_task(self):
        await self.prune_inactive_channels()
    
    @prune_task.before_loop
    async def before_prune_task(self):
        await self.bot.wait_until_ready()

    async def cog_load(self):
        self.prune_task.start()
       
    def cog_unload(self):
        self.prune_task.cancel()

    # AI GROUP COMMANDS
    @ai_group.command(
        name="chat",
        description="Send a message to the AI assistant"
    )
    async def chat_slash(self, ctx, 
                          message: str,
                          image: discord.Attachment = None):
        await ctx.defer()
        
        # Check internet connection first
        if not await self.check_internet_connection():
            await ctx.respond("⚠️ Network issue: Unable to connect to the internet. Please check your connection and try again.")
            return
        
        # Get channel ID to track conversation per channel
        channel_id = str(ctx.channel.id)
        
        # Initialize this channel's history if it doesn't exist
        if channel_id not in self.channel_history:
            self.channel_history[channel_id] = []
        
        # Determine which model to use for this channel
        current_model = self.openrouter_client.model  # Store original model
        channel_model = self.channel_models.get(channel_id)  # Get channel-specific model if it exists
        
        # Set the model to use for this request
        if channel_model:
            self.openrouter_client.model = channel_model

        # Check if the model supports images
        model_supports_images = self.openrouter_client.model_supports_vision()
        
        # Process image if provided and model supports it
        images = []
        image_embed = None
        
        if image:
            # Check if it's an image file
            if any(image.filename.lower().endswith(ext) for ext in ['.jpg', '.jpeg', '.png', '.gif', '.webp']):
                # Create an embed to display the image
                image_embed = discord.Embed(title="Analyzing Image", color=discord.Color.blue())
                image_embed.set_image(url=image.url)
                image_embed.add_field(name="File", value=image.filename)
                
                if model_supports_images:
                    try:
                        # Download the image data
                        image_data = await image.read()
                        images.append({
                            'data': image_data,
                            'type': image.content_type or 'image/jpeg'  # Default to jpeg if not specified
                        })
                    except Exception as e:
                        await ctx.respond(f"⚠️ Failed to process image {image.filename}: {str(e)}")
                        return
                else:
                    image_embed.description = "⚠️ Current model doesn't support image analysis. Consider switching to a vision-capable model."
        
        try:
            # Get recent channel context
            conversation_context = await self.get_channel_context(channel_id)
            
            # Add this new message
            self.channel_history[channel_id].append({
                "role": "user",
                "name": ctx.author.display_name,
                "content": message,
                "timestamp": datetime.now()
            })
            
            # Format the final query with the current user's question
            conversation_context.append({
                "role": "user", 
                "content": f"{ctx.author.display_name}: {message}"
            })
            
            # First response - show the image if there is one
            if image_embed:
                await ctx.respond(f"**{ctx.author.display_name}**: {message}", embed=image_embed)
                # Follow up with processing message
                processing_msg = await ctx.followup.send("Processing response...")
            else:
                # Regular processing message if no image
                await ctx.respond(f"Processing message...")
                processing_msg = None
                
            # Send to API with images if applicable
            response = await self.openrouter_client.send_message_with_history(
                conversation_context,
                images=images if model_supports_images else []
            )
            
            # Add assistant's response to history
            self.channel_history[channel_id].append({
                "role": "assistant",
                "content": response,
                "timestamp": datetime.now()
            })
            
            # Split response into chunks of 2000 characters or fewer
            max_length = 2000
            chunks = [response[i:i+max_length] for i in range(0, len(response), max_length)]
            
            # Send each chunk as a separate message
            for i, chunk in enumerate(chunks):
                if i == 0:
                    if processing_msg:
                        await processing_msg.edit(content=chunk)
                    else:
                        await ctx.followup.send(chunk)
                else:
                    await ctx.channel.send(chunk)
        finally:
            # Always restore the original model
            if channel_model:
                self.openrouter_client.model = current_model

    @ai_group.command(
        name="reset",
        description="Reset the conversation history for this channel"
    )
    async def reset_slash(self, ctx):
        channel_id = str(ctx.channel.id)
        if channel_id in self.channel_history:
            self.channel_history[channel_id] = []
            await ctx.respond("The conversation history for this channel has been reset.")
        else:
            await ctx.respond("No conversation history found for this channel.")

    @ai_group.command(
        name="memory",
        description="Show how many messages are stored for this channel"
    )
    async def channel_memory_slash(self, ctx):
        channel_id = str(ctx.channel.id)
        if channel_id in self.channel_history:
            history_length = len(self.channel_history[channel_id])
            await ctx.respond(f"Currently storing {history_length} messages for this channel, spanning up to {self.time_window_hours} hours.")
        else:
            await ctx.respond("No conversation history found for this channel.")
            
    @ai_group.command(
        name="setmemory",
        description="Set the maximum number of messages to remember per channel"
    )
    @commands.has_permissions(administrator=True)
    async def set_memory_slash(self, ctx, size: int):
        self.max_channel_history = size
        await ctx.respond(f"Channel memory size set to {size} messages.")
        
    @ai_group.command(
        name="setwindow",
        description="Set the time window for message history in hours"
    )
    @commands.has_permissions(administrator=True)
    async def set_window_slash(self, ctx, hours: int):
        if hours < 1 or hours > 96:
            await ctx.respond("Time window must be between 1 and 96 hours.")
            return
            
        self.time_window_hours = hours
        await ctx.respond(f"Channel memory time window set to {hours} hours.")
        
    @ai_group.command(
        name="summarize",
        description="Summarize the current conversation history"
    )
    async def summarize_slash(self, ctx):
        await ctx.defer()
        channel_id = str(ctx.channel.id)
        if channel_id not in self.channel_history or not self.channel_history[channel_id]:
            await ctx.respond("No conversation history to summarize.")
            return
            
        await ctx.respond("Generating conversation summary...")
        
        conversation_context = await self.get_channel_context(channel_id)
        summary_request = [
            {"role": "system", "content": "Summarize the following conversation in 3-5 bullet points:"},
            {"role": "user", "content": "\n".join([msg["content"] for msg in conversation_context])}
        ]
        
        summary = await self.openrouter_client.send_message_with_history(summary_request)
        await ctx.respond(f"**Conversation Summary:**\n{summary}")

    @ai_group.command(
        name="setmodel",
        description="Set the AI model to use from OpenRouter"
    )
    @commands.has_permissions(administrator=True)
    async def set_model_slash(self, ctx, model_name: str):
        if model_name not in ALLOWED_MODELS:
            models_list = ", ".join(f"`{m}`" for m in ALLOWED_MODELS)
            await ctx.respond(f"Invalid model. Allowed models: {models_list}")
            return
            
        self.openrouter_client.model = model_name
        await ctx.respond(f"Model set to {model_name}")

    @ai_group.command(
        name="model",
        description="Show the current AI model being used"
    )
    @commands.has_permissions(administrator=True)
    async def show_model_slash(self, ctx):
        await ctx.defer()
        await ctx.respond(f"Current model: `{self.openrouter_client.model}`")

    @ai_group.command(
        name="diagnostic",
        description="Run network diagnostics for the bot"
    )
    async def diagnostic_slash(self, ctx):
        await ctx.defer()
        await ctx.respond("Running network diagnostics...")
        
        results = []
        
        # Check internet connection
        internet = await self.check_internet_connection()
        results.append(f"Internet connection: {'✅' if internet else '❌'}")
        
        # Check OpenRouter API domains
        domains = [
            "openrouter.ai",
            "api.openrouter.ai"
        ]
        
        for domain in domains:
            result = await self.openrouter_client.verify_dns_resolution(domain)
            results.append(f"DNS resolution for {domain}: {'✅' if result else '❌'}")
        
        # Send results
        message = "Diagnostic results:\n" + "\n".join(results)
        await ctx.followup.send(message)
        
        if not internet:
            await ctx.followup.send("⚠️ Your internet connection appears to be down. Please check your network settings.")
        elif not all([result.endswith('✅') for result in results[1:]]):  # If any domain resolution failed
            await ctx.followup.send("⚠️ DNS resolution failed for some domains. Try using alternative DNS servers (e.g., 8.8.8.8 or 1.1.1.1).")

    @ai_group.command(
        name="showsystem",
        description="Show the current system prompt"
    )
    async def show_system_slash(self, ctx):
        await ctx.defer()
        # Split system prompt into chunks of 2000 characters or fewer
        max_length = 2000
        chunks = [self.openrouter_client.system_prompt[i:i+max_length] for i in range(0, len(self.openrouter_client.system_prompt), max_length)]
        
        # Send each chunk as a separate message
        await ctx.respond(f"Current system prompt: \n```\n{chunks[0]}\n```")
        for chunk in chunks[1:]:
            await ctx.channel.send(f"```\n{chunk}\n```")
    
    @ai_group.command(
        name="setsystem",
        description="Set a new system prompt (admin only)"
    )
    @commands.has_permissions(administrator=True)
    async def set_system_slash(self, ctx, new_prompt: str):
        self.openrouter_client.system_prompt = new_prompt
        await ctx.respond(f"System prompt updated! New prompt: \n```\n{new_prompt}\n```")

    @ai_group.command(
        name="setchannelmodel",
        description="Set the AI model to use for this specific channel"
    )
    @commands.has_permissions(administrator=True)
    async def set_channel_model_slash(self, ctx, model_name: str):
        if model_name not in ALLOWED_MODELS:
            models_list = ", ".join(f"`{m}`" for m in ALLOWED_MODELS)
            await ctx.respond(f"Invalid model. Allowed models: {models_list}")
            return
            
        channel_id = str(ctx.channel.id)
        self.channel_models[channel_id] = model_name
        await ctx.respond(f"Model for this channel set to `{model_name}`")

    @ai_group.command(
        name="channelmodel",
        description="Show the current AI model being used for this channel"
    )
    async def show_channel_model_slash(self, ctx):
        await ctx.defer()
        channel_id = str(ctx.channel.id)
        if channel_id in self.channel_models:
            await ctx.respond(f"Current model for this channel: `{self.channel_models[channel_id]}`")
        else:
            await ctx.respond(f"This channel uses the default model: `{self.openrouter_client.model}`")

    @ai_group.command(
        name="resetchannelmodel",
        description="Reset this channel to use the default model"
    )
    @commands.has_permissions(administrator=True)
    async def reset_channel_model_slash(self, ctx):
        channel_id = str(ctx.channel.id)
        if channel_id in self.channel_models:
            del self.channel_models[channel_id]
            await ctx.respond(f"This channel will now use the default model: `{self.openrouter_client.model}`")
        else:
            await ctx.respond(f"This channel is already using the default model: `{self.openrouter_client.model}`")

    @ai_group.command(
        name="visionmodels",
        description="Show which models support image analysis"
    )
    async def vision_models_slash(self, ctx):
        await ctx.defer()
        vision_models = [model for model in ALLOWED_MODELS if any(vm in model for vm in self.openrouter_client.vision_models)]
        
        if not vision_models:
            await ctx.respond("No vision-capable models are currently configured.")
            return
            
        current_model = self.openrouter_client.model
        channel_id = str(ctx.channel.id)
        channel_model = self.channel_models.get(channel_id, current_model)
        
        supports_vision = any(vm in channel_model for vm in self.openrouter_client.vision_models)
        status = "✅ supports" if supports_vision else "❌ does not support"
        
        await ctx.respond(f"**Vision-capable models:**\n" + 
                          "\n".join([f"• `{m}`" for m in vision_models]) + 
                          f"\n\nCurrent model for this channel (`{channel_model}`) {status} images.")

    # THREAD GROUP COMMANDS
    @thread_group.command(
        name="create",
        description="Create a new Discord thread for conversation"
    )
    async def create_thread_slash(self, ctx, 
                          name: str):
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
                auto_archive_duration=1440  # Auto-archive after 24 hours of inactivity (use 4320 for 3 days or 10080 for 7 days)
            )
            
            # Store basic thread information in our tracking dict
            self.discord_threads[str(thread.id)] = {
                "name": name,
                "channel_id": str(ctx.channel.id),
                "created_at": datetime.now(),
                "model": self.channel_models.get(str(ctx.channel.id), self.openrouter_client.model)
            }
            
            # Welcome message in the thread
            await thread.send(f"✅ Thread created! You can chat with the AI in this thread using regular messages or `/ai chat` commands.")
            
            # Reply to the slash command
            await ctx.respond(f"✅ Created new Discord thread: **{name}**\nThe thread is now ready for conversation.")
            
        except discord.Forbidden:
            await ctx.respond("⚠️ I don't have permission to create threads in this channel.")
        except discord.HTTPException as e:
            await ctx.respond(f"⚠️ Failed to create thread: {str(e)}")

    @thread_group.command(
        name="message",  # Changed from "chat" to "message"
        description="Chat within a specific conversation thread"
    )
    @commands.cooldown(1, 5, commands.BucketType.user)
    async def thread_chat_slash(self, ctx,
                         id: str,
                         message: str,
                         image: discord.Attachment = None):
        await ctx.defer()
        
        # Check if this is a simple ID or a full thread ID
        thread_id = None
        if id in self.simple_id_mapping:
            # This is a simple ID, get the full thread ID
            thread_id = self.simple_id_mapping[id]
            channel_id = thread_id.split('-')[0]
        else:
            # Try to parse as a full thread ID
            try:
                channel_id = id.split('-')[0]
                # Search through threads to find the matching ID
                found = False
                for thread_key in self.threads.get(channel_id, {}):
                    if id == thread_key or (
                        "simple_id" in self.threads[channel_id][thread_key] and 
                        self.threads[channel_id][thread_key]["simple_id"] == id
                    ):
                        thread_id = thread_key
                        found = True
                        break
                
                if not found:
                    await ctx.respond("⚠️ Thread not found. Use `/threads` to see available threads.")
                    return
            except:
                await ctx.respond("⚠️ Invalid thread ID format. Use `/threads` to see available threads.")
                return
        
        # Check if thread exists
        if channel_id not in self.threads or thread_id not in self.threads[channel_id]:
            await ctx.respond("⚠️ Thread not found. Use `/threads` to see available threads.")
            return
        
        thread_data = self.threads[channel_id][thread_id]
        thread_name = thread_data["name"]
        
        # Set model for this thread if different from current
        current_model = self.openrouter_client.model
        thread_model = thread_data.get("model")
        
        if thread_model:
            self.openrouter_client.model = thread_model
        
        # Handle image processing similarly to regular chat
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
                if "timestamp" not in msg or datetime.now() - msg["timestamp"] <= timedelta(hours=self.time_window_hours):
                    conversation_context.append({
                        "role": msg["role"],
                        "content": f"{msg['name']}: {msg['content']}" if "name" in msg else msg["content"]
                    })
            
            # First response - show the image if there is one
            if image_embed:
                await ctx.respond(f"**{ctx.author.display_name}** in **{thread_name}**: {message}", embed=image_embed)
                # Follow up with processing message
                processing_msg = await ctx.followup.send(f"Processing response for thread **{thread_name}**...")
            else:
                # Regular processing message if no image
                await ctx.respond(f"Processing message in thread **{thread_name}**...")
                processing_msg = None
            
            response = await self.openrouter_client.send_message_with_history(
                conversation_context,
                images=images if model_supports_images else []
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

    @thread_group.command(
        name="list",
        description="List all active conversation threads in this channel"
    )
    async def list_threads_slash(self, ctx):
        channel_id = str(ctx.channel.id)
        
        if channel_id not in self.threads or not self.threads[channel_id]:
            await ctx.respond("No active threads in this channel. Create one with `/newthread`")
            return
        
        threads_list = []
        for thread_id, thread_data in self.threads[channel_id].items():
            thread_name = thread_data["name"]
            message_count = len(thread_data["messages"])
            created_time = thread_data["created_at"].strftime("%Y-%m-%d %H:%M")
            simple_id = thread_data.get("simple_id", thread_id.split('-')[1] if '-' in thread_id else "???")
            threads_list.append(f"• **{thread_name}** (ID: `{simple_id}`)\n  Created: {created_time} | Messages: {message_count}")
        
        await ctx.respond(f"**Active Conversation Threads:**\n\n" + "\n".join(threads_list) + 
                          "\n\nUse `/thread chat id:<thread_id> message:<your message>` to continue a conversation.")

    @thread_group.command(
        name="delete",
        description="Delete a conversation thread"
    )
    async def delete_thread_slash(self, ctx, 
                           id: str):
        # Check if this is a simple ID
        thread_id = None
        channel_id = None
        
        if id in self.simple_id_mapping:
            # This is a simple ID, get the full thread ID
            thread_id = self.simple_id_mapping[id]
            channel_id = thread_id.split('-')[0]
            
            # Clean up the mapping when deleting
            del self.simple_id_mapping[id]
        else:
            # Try to parse as a full thread ID
            try:
                channel_id = id.split('-')[0]
                # Search through threads to find the matching ID
                for thread_key in list(self.threads.get(channel_id, {}).keys()):
                    if id == thread_key or (
                        "simple_id" in self.threads[channel_id][thread_key] and 
                        self.threads[channel_id][thread_key]["simple_id"] == id
                    ):
                        thread_id = thread_key
                        # Also clean up the mapping
                        simple_id = self.threads[channel_id][thread_key].get("simple_id")
                        if simple_id in self.simple_id_mapping:
                            del self.simple_id_mapping[simple_id]
                        break
            except:
                await ctx.respond("⚠️ Invalid thread ID format. Use `/threads` to see available threads.")
                return
        
        if not thread_id or channel_id not in self.threads or thread_id not in self.threads[channel_id]:
            await ctx.respond("⚠️ Thread not found. Use `/threads` to see available threads.")
            return
        
        thread_name = self.threads[channel_id][thread_id]["name"]
        del self.threads[channel_id][thread_id]
        
        # Clean up empty channel entries
        if not self.threads[channel_id]:
            del self.threads[channel_id]
            
        await ctx.respond(f"✅ Deleted thread: **{thread_name}**")

    @thread_group.command(
        name="rename",
        description="Rename a conversation thread"
    )
    async def rename_thread_slash(self, ctx, 
                           id: str,
                           name: str):
        # Check if this is a simple ID
        thread_id = None
        channel_id = None
        
        if id in self.simple_id_mapping:
            # This is a simple ID, get the full thread ID
            thread_id = self.simple_id_mapping[id]
            channel_id = thread_id.split('-')[0]
        else:
            # Try to parse as a full thread ID
            try:
                channel_id = id.split('-')[0]
                # Search through threads to find the matching ID
                for thread_key in self.threads.get(channel_id, {}).keys():
                    if id == thread_key or (
                        "simple_id" in self.threads[channel_id][thread_key] and 
                        self.threads[channel_id][thread_key]["simple_id"] == id
                    ):
                        thread_id = thread_key
                        break
            except:
                await ctx.respond("⚠️ Invalid thread ID format. Use `/threads` to see available threads.")
                return
        
        if not thread_id or channel_id not in self.threads or thread_id not in self.threads[channel_id]:
            await ctx.respond("⚠️ Thread not found. Use `/threads` to see available threads.")
            return
        
        old_name = self.threads[channel_id][thread_id]["name"]
        self.threads[channel_id][thread_id]["name"] = name
        
        await ctx.respond(f"✅ Renamed thread from **{old_name}** to **{name}**")

    @thread_group.command(
        name="threadmodel",
        description="Set the AI model for the current thread"
    )
    @commands.has_permissions(administrator=True)
    async def set_thread_model_slash(self, ctx, 
                         model_name: str):
        # Check if we're in a thread
        if not isinstance(ctx.channel, discord.Thread):
            await ctx.respond("⚠️ This command can only be used within a thread.")
            return
            
        thread_id = str(ctx.channel.id)
        
        # Initialize discord_threads if it doesn't exist
        if not hasattr(self, 'discord_threads'):
            self.discord_threads = {}
            
        # Create or update thread entry
        if thread_id not in self.discord_threads:
            self.discord_threads[thread_id] = {
                "name": ctx.channel.name,
                "channel_id": str(ctx.channel.parent_id),
                "created_at": datetime.now()
            }
        
        # Set the model
        self.discord_threads[thread_id]["model"] = model_name
        await ctx.respond(f"Model for this thread set to `{model_name}`")

# The setup function needed for Cog loading
def setup(bot):
    cog = LLMChat(bot)
    bot.add_cog(cog)
  #  bot.add_application_command(ai_group)
  #  bot.add_application_command(thread_group)