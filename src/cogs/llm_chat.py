import asyncio
import logging
import socket
from discord.ext import commands
from utils.openrouter_client import OpenRouterClient
from config import OPENROUTER_API_KEY, SYSTEM_PROMPT
import discord

logger = logging.getLogger('llm_chat')

class LLMChat(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.openrouter_client = OpenRouterClient(OPENROUTER_API_KEY, SYSTEM_PROMPT)
        # Dictionary to store conversation history for each user
        self.conversation_history = {}
        # Maximum number of conversation turns to remember
        self.max_history = 10

    async def check_internet_connection(self):
        """Check if the internet connection is working"""
        try:
            # Try to resolve a well-known domain
            await asyncio.get_event_loop().getaddrinfo('google.com', 443)
            return True
        except socket.gaierror:
            return False

    @commands.command(name='chat')
    async def chat(self, ctx, *, message: str):
        await ctx.send(f"Thinking about: '{message}'...")
        
        # Check internet connection first
        if not await self.check_internet_connection():
            await ctx.send("⚠️ Network issue: Unable to connect to the internet. Please check your connection and try again.")
            return
        
        # Get user ID to track conversation per user
        user_id = str(ctx.author.id)
        
        # Initialize conversation history for this user if it doesn't exist
        if user_id not in self.conversation_history:
            self.conversation_history[user_id] = []
        
        # Add user message to history
        self.conversation_history[user_id].append({
            "role": "user",
            "content": message
        })
        
        # Send conversation history to get contextual response
        response = await self.openrouter_client.send_message_with_history(
            self.conversation_history[user_id]
        )
        
        # Add assistant's response to history
        self.conversation_history[user_id].append({
            "role": "assistant",
            "content": response
        })
        
        # Trim history if it gets too long (keep most recent interactions)
        if len(self.conversation_history[user_id]) > self.max_history * 2:  # *2 because each turn has 2 messages
            self.conversation_history[user_id] = self.conversation_history[user_id][-self.max_history*2:]
        
        # Split response into chunks of 2000 characters or fewer
        max_length = 2000
        chunks = [response[i:i+max_length] for i in range(0, len(response), max_length)]
        
        # Send each chunk as a separate message
        for chunk in chunks:
            await ctx.send(chunk)
    
    @commands.command(name='reset')
    async def reset_conversation(self, ctx):
        """Reset the conversation history for the user"""
        user_id = str(ctx.author.id)
        if user_id in self.conversation_history:
            self.conversation_history[user_id] = []
            await ctx.send("Your conversation history has been reset.")
        else:
            await ctx.send("No conversation history found.")
        
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
        """Set a new system prompt (admin only)"""
        self.openrouter_client.system_prompt = new_prompt
        await ctx.send(f"System prompt updated! New prompt: \n```\n{new_prompt}\n```")
        
    @commands.command(name='memory')
    async def show_memory_size(self, ctx):
        """Show how much conversation history is being stored"""
        user_id = str(ctx.author.id)
        if user_id in self.conversation_history:
            history_length = len(self.conversation_history[user_id])
            turns = history_length // 2
            await ctx.send(f"Currently storing {turns} conversation turns ({history_length} messages) for you.")
        else:
            await ctx.send("No conversation history found for you.")

def setup(bot):
    bot.add_cog(LLMChat(bot))