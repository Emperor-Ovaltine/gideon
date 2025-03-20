import asyncio
import logging
import socket
from discord.ext import commands, tasks
import discord  # Correct import
from ..utils.openrouter_client import OpenRouterClient
from ..config import OPENROUTER_API_KEY, SYSTEM_PROMPT, ALLOWED_MODELS, DEFAULT_MODEL
from datetime import datetime, timedelta

logger = logging.getLogger('llm_chat')

class LLMChat(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.openrouter_client = OpenRouterClient(OPENROUTER_API_KEY, SYSTEM_PROMPT, DEFAULT_MODEL)
        # Dictionary to store conversation history for each channel
        self.channel_history = {}
        # Maximum number of messages to remember per channel
        self.max_channel_history = 35
        # Time window to include messages (in hours)
        self.time_window_hours = 48
        # Initialize the pruning task
        self.prune_task.start()

    async def check_internet_connection(self):
        """Check if the internet connection is working"""
        try:
            # Try to resolve a well-known domain
            await asyncio.get_event_loop().getaddrinfo('google.com', 443)
            return True
        except socket.gaierror:
            return False
    
    @commands.Cog.listener()
    async def on_message(self, message):
        """Listen for messages in channels to build context memory"""
        # Ignore messages from the bot itself
        if message.author == self.bot.user:
            return
            
        # Only track messages in text channels
        if not isinstance(message.channel, discord.TextChannel):
            return
            
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

    @commands.command(name='chat')
    @commands.cooldown(1, 5, commands.BucketType.user)  # 1 command every 5 seconds per user
    async def chat(self, ctx, *, message: str):
        await ctx.send(f"Thinking about: '{message}'...")
        
        # Check internet connection first
        if not await self.check_internet_connection():
            await ctx.send("⚠️ Network issue: Unable to connect to the internet. Please check your connection and try again.")
            return
        
        # Get channel ID to track conversation per channel
        channel_id = str(ctx.channel.id)
        
        # Initialize conversation history for this channel if it doesn't exist
        if channel_id not in self.channel_history:
            self.channel_history[channel_id] = []
        
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
        
        # Send conversation history to get contextual response
        response = await self.openrouter_client.send_message_with_history(
            conversation_context
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
        for chunk in chunks:
            await ctx.send(chunk)
    
    @commands.command(name='reset')
    async def reset_conversation(self, ctx):
        """Reset the conversation history for the channel"""
        channel_id = str(ctx.channel.id)
        if channel_id in self.channel_history:
            self.channel_history[channel_id] = []
            await ctx.send("The conversation history for this channel has been reset.")
        else:
            await ctx.send("No conversation history found for this channel.")

    @commands.command(name='channelmemory')
    async def show_channel_memory_size(self, ctx):
        """Show how many messages are stored for this channel"""
        channel_id = str(ctx.channel.id)
        if channel_id in self.channel_history:
            history_length = len(self.channel_history[channel_id])
            await ctx.send(f"Currently storing {history_length} messages for this channel, spanning up to {self.time_window_hours} hours.")
        else:
            await ctx.send("No conversation history found for this channel.")
            
    @commands.command(name='setmemory')
    @commands.has_permissions(administrator=True)
    async def set_memory_size(self, ctx, size: int):
        """Set the maximum number of messages to remember per channel"""
        if size < 5 or size > 100:
            await ctx.send("Memory size must be between 5 and 100 messages.")
            return
            
        self.max_channel_history = size
        await ctx.send(f"Channel memory size set to {size} messages.")
        
    @commands.command(name='setwindow')
    @commands.has_permissions(administrator=True)
    async def set_time_window(self, ctx, hours: int):
        """Set the time window for message history in hours"""
        if hours < 1 or hours > 96:
            await ctx.send("Time window must be between 1 and 96 hours.")
            return
            
        self.time_window_hours = hours
        await ctx.send(f"Channel memory time window set to {hours} hours.")
        
    @commands.command(name='summarize')
    async def summarize_conversation(self, ctx):
        """Summarize the current conversation history"""
        channel_id = str(ctx.channel.id)
        if channel_id not in self.channel_history or not self.channel_history[channel_id]:
            await ctx.send("No conversation history to summarize.")
            return
            
        await ctx.send("Generating conversation summary...")
        
        conversation_context = await self.get_channel_context(channel_id)
        summary_request = [
            {"role": "system", "content": "Summarize the following conversation in 3-5 bullet points:"},
            {"role": "user", "content": "\n".join([msg["content"] for msg in conversation_context])}
        ]
        
        summary = await self.openrouter_client.send_message_with_history(summary_request)
        await ctx.send(f"**Conversation Summary:**\n{summary}")

    async def prune_inactive_channels(self):
        """Remove history for channels inactive for more than 7 days"""
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

    @commands.command(name='setmodel')
    @commands.has_permissions(administrator=True)
    async def set_model(self, ctx, model_name: str):
        """Set the AI model to use from OpenRouter"""
        if model_name not in ALLOWED_MODELS:
            models_list = ", ".join(f"`{m}`" for m in ALLOWED_MODELS)
            await ctx.send(f"Invalid model. Allowed models: {models_list}")
            return
            
        self.openrouter_client.model = model_name
        await ctx.send(f"Model set to {model_name}")

    @commands.command(name='model')
    @commands.has_permissions(administrator=True)
    async def show_current_model(self, ctx):
        """Show the current AI model being used (admin only)"""
        await ctx.send(f"Current model: `{self.openrouter_client.model}`")

    @commands.command(name='diagnostic')
    async def diagnostic(self, ctx):
        """Run network diagnostics for the bot"""
        await ctx.send("Running network diagnostics...")
        
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
        await ctx.send("Diagnostic results:\n" + "\n".join(results))
        
        if not internet:
            await ctx.send("⚠️ Your internet connection appears to be down. Please check your network settings.")
        elif not all(results[1:]):  # If any domain resolution failed
            await ctx.send("⚠️ DNS resolution failed for some domains. Try using alternative DNS servers (e.g., 8.8.8.8 or 1.1.1.1).")

    @commands.command(name='showsystem')
    async def show_system(self, ctx):
        """Show the current system prompt"""
        # Split system prompt into chunks of 2000 characters or fewer
        max_length = 2000
        chunks = [self.openrouter_client.system_prompt[i:i+max_length] for i in range(0, len(self.openrouter_client.system_prompt), max_length)]
        
        # Send each chunk as a separate message
        for chunk in chunks:
            await ctx.send(f"Current system prompt: \n```\n{chunk}\n```")
    
    @commands.command(name='setsystem')
    @commands.has_permissions(administrator=True)  # Only allow administrators to change the system prompt
    async def set_system(self, ctx, *, new_prompt: str):
        self.openrouter_client.system_prompt = new_prompt
        await ctx.send(f"System prompt updated! New prompt: \n```\n{new_prompt}\n```")
        
    @commands.command(name='memory')
    async def show_memory_size(self, ctx):
        """Show how much conversation history is being stored (legacy - user-based)"""
        await ctx.send("This bot now uses channel-based memory instead of user-based memory. Use !channelmemory instead.")

    @commands.slash_command(
        name="chat",
        description="Send a message to the AI assistant"
    )
    @commands.cooldown(1, 5, commands.BucketType.user)
    async def chat_slash(self, ctx, message: discord.Option(str, description="Your message to the AI")):
        await ctx.defer()
        await ctx.respond(f"Thinking about: '{message}'...")
        
        # Check internet connection first
        if not await self.check_internet_connection():
            await ctx.respond("⚠️ Network issue: Unable to connect to the internet. Please check your connection and try again.")
            return
        
        # Get channel ID to track conversation per channel
        channel_id = str(ctx.channel.id)
        
        # Initialize conversation history for this channel if it doesn't exist
        if channel_id not in self.channel_history:
            self.channel_history[channel_id] = []
        
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
        
        # Send conversation history to get contextual response
        response = await self.openrouter_client.send_message_with_history(
            conversation_context
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
        await ctx.respond(chunks[0])
        for chunk in chunks[1:]:
            await ctx.channel.send(chunk)
    
    @commands.slash_command(
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

    @commands.slash_command(
        name="channelmemory",
        description="Show how many messages are stored for this channel"
    )
    async def channel_memory_slash(self, ctx):
        channel_id = str(ctx.channel.id)
        if channel_id in self.channel_history:
            history_length = len(self.channel_history[channel_id])
            await ctx.respond(f"Currently storing {history_length} messages for this channel, spanning up to {self.time_window_hours} hours.")
        else:
            await ctx.respond("No conversation history found for this channel.")
            
    @commands.slash_command(
        name="setmemory",
        description="Set the maximum number of messages to remember per channel"
    )
    @commands.has_permissions(administrator=True)
    async def set_memory_slash(self, ctx, size: discord.Option(int, description="Number of messages (5-100)", min_value=5, max_value=100)):
        self.max_channel_history = size
        await ctx.respond(f"Channel memory size set to {size} messages.")
        
    @commands.slash_command(
        name="setwindow",
        description="Set the time window for message history in hours"
    )
    @commands.has_permissions(administrator=True)
    async def set_window_slash(self, ctx, hours: discord.Option(int, description="Hours (1-96)", min_value=1, max_value=96)):
        if hours < 1 or hours > 96:
            await ctx.respond("Time window must be between 1 and 96 hours.")
            return
            
        self.time_window_hours = hours
        await ctx.respond(f"Channel memory time window set to {hours} hours.")
        
    @commands.slash_command(
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

    @commands.slash_command(
        name="setmodel",
        description="Set the AI model to use from OpenRouter"
    )
    @commands.has_permissions(administrator=True)
    async def set_model_slash(self, ctx, model_name: discord.Option(str, description="Model name", choices=ALLOWED_MODELS)):
        if model_name not in ALLOWED_MODELS:
            models_list = ", ".join(f"`{m}`" for m in ALLOWED_MODELS)
            await ctx.respond(f"Invalid model. Allowed models: {models_list}")
            return
            
        self.openrouter_client.model = model_name
        await ctx.respond(f"Model set to {model_name}")

    @commands.slash_command(
        name="model",
        description="Show the current AI model being used"
    )
    @commands.has_permissions(administrator=True)
    async def show_model_slash(self, ctx):
        await ctx.defer()
        await ctx.respond(f"Current model: `{self.openrouter_client.model}`")

    @commands.slash_command(
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

    @commands.slash_command(
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
    
    @commands.slash_command(
        name="setsystem",
        description="Set a new system prompt (admin only)"
    )
    @commands.has_permissions(administrator=True)
    async def set_system_slash(self, ctx, new_prompt: discord.Option(str, description="New system prompt")):
        self.openrouter_client.system_prompt = new_prompt
        await ctx.respond(f"System prompt updated! New prompt: \n```\n{new_prompt}\n```")

# The setup function needed for Cog loading
def setup(bot):
    bot.add_cog(LLMChat(bot))