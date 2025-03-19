import asyncio
import logging
import socket
from discord.ext import commands
from utils.openrouter_client import OpenRouterClient
from config import OPENROUTER_API_KEY, SYSTEM_PROMPT

logger = logging.getLogger('llm_chat')

class LLMChat(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.openrouter_client = OpenRouterClient(OPENROUTER_API_KEY, SYSTEM_PROMPT)

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
            
        response = await self.openrouter_client.send_message(message)
        
        # Split response into chunks of 2000 characters or fewer
        max_length = 2000
        chunks = [response[i:i+max_length] for i in range(0, len(response), max_length)]
        
        # Send each chunk as a separate message
        for chunk in chunks:
            await ctx.send(chunk)
        
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

def setup(bot):
    bot.add_cog(LLMChat(bot))