import discord
from discord.ext import commands
import os
from dotenv import load_dotenv
from .config import DISCORD_TOKEN
from .utils.model_sync import sync_models

# Load environment variables
load_dotenv()

# IMPORTANT: The message_content intent is privileged and must be enabled in
# the Discord Developer Portal: https://discord.com/developers/applications/
# Select your application, go to "Bot" tab, and enable "Message Content Intent"
intents = discord.Intents.default()
intents.message_content = True  # This requires privileged intent enabled in Discord Developer Portal

# Create bot with proper command sync settings
bot = commands.Bot(
    command_prefix="unused!",
    intents=intents,
    # Important: Set this to False initially to avoid duplicate command registration
    sync_commands=False,
    # Add debug_guilds for testing slash commands in specific servers
    # debug_guilds=[123456789012345678]  # Replace with your test server ID(s)
)

@bot.event
async def on_ready():
    print(f'Logged in as {bot.user.name} - {bot.user.id}')
    print('------')
    
    # First try to clear all existing commands to start fresh
    try:
        print("Clearing existing commands...")
        # For Py-Cord, we should use application_commands property
        commands_to_remove = await bot.http.get_global_commands(bot.user.id)
        for cmd in commands_to_remove:
            print(f"Removing command: {cmd['name']}")
            # Delete the command
            await bot.http.delete_global_command(bot.user.id, cmd['id'])
        print("Existing commands cleared.")
    except Exception as e:
        print(f"Warning: Could not clear existing commands: {e}")
    
    # Load modular cogs
    cogs = [
        "src.cogs.chat_commands",
        "src.cogs.thread_commands", 
        "src.cogs.config_commands",
        "src.cogs.diagnostic_commands"
    ]
    
    for cog in cogs:
        try:
            bot.load_extension(cog)
            print(f"{cog} loaded successfully.")
        except Exception as e:
            print(f"Error loading {cog}: {e}")
    
    # Sync commands after loading extensions
    try:
        print("Syncing commands to Discord...")
        
        # First sync to the specified guild(s) if debug_guilds is set
        if hasattr(bot, 'debug_guilds') and bot.debug_guilds:
            # For guild specific commands
            for guild_id in bot.debug_guilds:
                await bot.sync_commands(guild_ids=[guild_id])
            print(f"Synced commands to test guilds: {bot.debug_guilds}")
        
        # Then sync globally
        await bot.sync_commands()
        print("Synced commands globally")
    except Exception as e:
        print(f"Error syncing commands: {e}")
    
    print("Slash commands are now registered. They may take up to an hour to appear across all servers.")
    
    # Synchronize model settings across all cogs
    sync_models(bot)
    
    print('Model synchronization complete')
    print(f'Using global model: {bot.cogs["ConfigCommands"].state.get_global_model()}')
    print('Ready to serve!')

@bot.slash_command(name="sync", description="Manually sync slash commands (owner only)")
@commands.is_owner()  # Only you can run this
async def sync_command_slash(ctx):
    await ctx.defer()
    try:
        await ctx.respond("Syncing commands...")
        
        # Clean existing commands first
        try:
            await ctx.followup.send("Clearing existing commands...")
            commands_to_remove = await bot.http.get_global_commands(bot.user.id)
            for cmd in commands_to_remove:
                if cmd['name'] != "sync":  # Don't delete the sync command we're using
                    await bot.http.delete_global_command(bot.user.id, cmd['id'])
            await ctx.followup.send("Existing commands cleared.")
        except Exception as e:
            await ctx.followup.send(f"Warning: Could not clear existing commands: {e}")
        
        # First to guilds
        if hasattr(bot, 'debug_guilds') and bot.debug_guilds:
            for guild_id in bot.debug_guilds:
                await bot.sync_commands(guild_ids=[guild_id])
            await ctx.followup.send(f"Commands synced to test guilds: {bot.debug_guilds}")
        
        # Then globally
        await bot.sync_commands()
        await ctx.followup.send("Commands synced globally")
            
    except Exception as e:
        await ctx.followup.send(f"Error syncing commands: {str(e)}")

# Debug function to help identify command registration issues
@bot.slash_command(name="debug", description="Show registered commands")
@commands.is_owner()
async def debug_commands(ctx):
    await ctx.defer()
    
    # Build debug information
    debug_info = ["**Registered Application Commands:**"]
    
    # Get global commands
    try:
        global_commands = await bot.http.get_global_commands(bot.user.id)
        debug_info.append(f"\n**Global Commands:** {len(global_commands)}")
        for cmd in global_commands:
            debug_info.append(f"- `/{cmd['name']}`: ID={cmd['id']}")
    except Exception as e:
        debug_info.append(f"Error fetching global commands: {str(e)}")
    
    # Get guild commands for the current guild
    try:
        guild_commands = await bot.http.get_guild_commands(bot.user.id, ctx.guild.id)
        debug_info.append(f"\n**Guild Commands ({ctx.guild.name}):** {len(guild_commands)}")
        for cmd in guild_commands:
            debug_info.append(f"- `/{cmd['name']}`: ID={cmd['id']}")
    except Exception as e:
        debug_info.append(f"Error fetching guild commands: {str(e)}")
    
    # Send debug info
    await ctx.respond("\n".join(debug_info))

if __name__ == "__main__":
    bot.run(DISCORD_TOKEN)
