import discord
from discord.ext import commands
import os
from dotenv import load_dotenv
from .config import DISCORD_TOKEN
from .cogs.llm_chat import LLMChat

# Load environment variables
load_dotenv()

# IMPORTANT: The message_content intent is privileged and must be enabled in
# the Discord Developer Portal: https://discord.com/developers/applications/
# Select your application, go to "Bot" tab, and enable "Message Content Intent"
intents = discord.Intents.default()
intents.message_content = True  # This requires privileged intent enabled in Discord Developer Portal

# Uncomment below and comment out the above if you don't have privileged intents enabled
# intents = discord.Intents.default()
# intents.message_content = False

bot = commands.Bot(command_prefix='!', intents=intents)

@bot.event
async def on_ready():
    print(f'Logged in as {bot.user.name} - {bot.user.id}')
    print('------')
    
    # Load cogs - must use await with async methods
    await bot.add_cog(LLMChat(bot))

if __name__ == "__main__":
    bot.run(DISCORD_TOKEN)