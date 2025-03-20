import discord
from discord.ext import commands
import os
from dotenv import load_dotenv
from .config import DISCORD_TOKEN

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

# Create bot with proper command sync settings
bot = commands.Bot(
    command_prefix='!', 
    intents=intents,
    sync_commands=True,
    # Optional: you can specify guild IDs for faster development testing
    # sync_commands_debug=True,
    # debug_guilds=[123456789]  # Replace with your guild ID for testing
)

@bot.event
async def on_ready():
    print(f'Logged in as {bot.user.name} - {bot.user.id}')
    print('------')
    
    # Load cogs - properly loading the extension
    try:
        # Use load_extension without await - it's not an async function in py-cord
        bot.load_extension("src.cogs.llm_chat")
        print("LLM Chat extension loaded successfully.")
        
        # Add this section for better debugging
        try:
            print(f"Attempting to sync commands to guilds: {bot.debug_guilds}")
            synced = await bot.sync_commands()
            # Handle None return value
            command_count = len(synced) if synced is not None else 0
            print(f"Synced {command_count} commands")
        except Exception as e:
            print(f"Error syncing commands: {e}")
            
    except Exception as e:
        print(f"Error loading LLM Chat extension: {e}")
    
    print("Slash commands should now be registered. They may take up to an hour to appear across all servers.")

@bot.command(name="sync")
@commands.is_owner()  # Only you can run this
async def sync_command(ctx):
    """Manually sync slash commands"""
    try:
        await ctx.send("Syncing commands...")
        synced = await bot.sync_commands()
        
        # Properly handle None return value
        if synced is None:
            await ctx.send("Commands synced globally. No direct count available, but sync completed.")
        else:
            await ctx.send(f"Synced {len(synced)} commands globally")
        
        # For guild-specific sync
        if bot.debug_guilds:
            guild_synced = await bot.sync_commands(guild_ids=bot.debug_guilds)
            
            if guild_synced is None:
                await ctx.send(f"Commands synced to test guilds: {bot.debug_guilds}")
            else:
                await ctx.send(f"Synced {len(guild_synced)} commands to test guilds: {bot.debug_guilds}")
    except Exception as e:
        await ctx.send(f"Error syncing commands: {str(e)}")

if __name__ == "__main__":
    bot.run(DISCORD_TOKEN)