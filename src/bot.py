import discord
from discord.ext import commands
import os
from dotenv import load_dotenv
import asyncio
import logging
from datetime import datetime
import signal
import sys
import traceback

# Import configuration 
from .config import DISCORD_TOKEN, OPENROUTER_API_KEY, SYSTEM_PROMPT, DEFAULT_MODEL, DATA_DIRECTORY
from .utils.model_sync import sync_models
from .utils.state_manager import BotStateManager
from .utils.persistence import StatePersistence

# Configure logger
logger = logging.getLogger(__name__)

# Load environment variables
load_dotenv()

# Create intents
intents = discord.Intents.default()
intents.message_content = True

# Create bot with proper command sync settings
bot = commands.Bot(
    command_prefix="unused!",
    intents=intents,
    sync_commands=False,
    # Add debug_guilds for testing slash commands in specific servers
    # debug_guilds=[123456789012345678]  # Replace with your test server ID(s)
)

# Properly import OpenRouterClient - direct import, no try/except
from .utils.openrouter_client import OpenRouterClient
from .utils.model_manager import ModelManager

# Create the persistence handler
persistence = StatePersistence()

def handle_exit(signum, frame):
    """Handle exit gracefully by saving state before shutdown."""
    print("Shutdown signal received. Saving state before exit...")
    try:
        state = BotStateManager()
        if persistence.save_state(state):
            print("State saved successfully!")
        else:
            print("Failed to save state!")
    except Exception as e:
        print(f"Error during shutdown save: {str(e)}")
    
    sys.exit(0)

# Register the signal handlers
signal.signal(signal.SIGINT, handle_exit)  # Ctrl+C
signal.signal(signal.SIGTERM, handle_exit)  # Termination signal

# Initialize OpenRouter client
openrouter_client = OpenRouterClient(
    api_key=OPENROUTER_API_KEY,
    system_prompt=SYSTEM_PROMPT,
    default_model=DEFAULT_MODEL
)

# Create model manager
model_manager = ModelManager(openrouter_client, DATA_DIRECTORY)

# Add to bot context or cogs as needed
bot.model_manager = model_manager

@bot.event
async def on_ready():
    print(f'Logged in as {bot.user.name} - {bot.user.id}')
    print('------')
    
    # Load saved state if available
    state = BotStateManager()
    state_loaded = persistence.load_state(state)
    if state_loaded:
        channels = len(state.channel_history)
        threads = len(state.discord_threads)  # Updated to use discord_threads
        messages = sum(len(msgs) for msgs in state.channel_history.values())
        print(f"Successfully loaded saved state: {channels} channels, {threads} threads, {messages}")
    else:
        print("No saved state found or error loading state, starting fresh")
    
    # Get set of existing command names
    try:
        print("Checking existing commands...")
        existing_commands = await bot.http.get_global_commands(bot.user.id)
        existing_command_names = {cmd['name'] for cmd in existing_commands}
        print(f"Found {len(existing_commands)} existing commands")
    except Exception as e:
        print(f"Warning: Could not fetch existing commands: {e}")
        existing_command_names = set()
    
    # Load modular cogs
    cogs = [
        "src.cogs.chat_commands",
        "src.cogs.thread_commands", 
        "src.cogs.config_commands",
        "src.cogs.diagnostic_commands",
        "src.cogs.mention_commands",
        "src.cogs.image_commands",
        "src.cogs.cloudflare_image_commands",
        "src.cogs.url_commands",
        "src.cogs.dungeon_master_commands"
    ]
    
    for cog in cogs:
        try:
            bot.load_extension(cog)
            print(f"{cog} loaded successfully.")
            
            # Additional debug info for dungeon master commands
            if cog == "src.cogs.dungeon_master_commands":
                print("DND cog commands being registered:")
                if hasattr(bot.cogs.get("DungeonMasterCommands", {}), "get_commands"):
                    commands = bot.cogs["DungeonMasterCommands"].get_commands()
                    for cmd in commands:
                        print(f"  - {cmd.name}: {type(cmd).__name__}")
        except Exception as e:
            print(f"Error loading {cog}: {e}")
            # Print full traceback for config_commands to debug issues
            if cog == "src.cogs.config_commands":
                print(f"Detailed error for config commands: {traceback.format_exc()}")
            if cog == "src.cogs.dungeon_master_commands":
                print(f"Detailed error for DND cog: {traceback.format_exc()}")
    
    # Skip command clearing and just sync
    try:
        print("Syncing commands to Discord...")
        
        # First sync to the specified guild(s) if debug_guilds is set
        if hasattr(bot, 'debug_guilds') and bot.debug_guilds:
            for guild_id in bot.debug_guilds:
                await bot.sync_commands(guild_ids=[guild_id])
            print(f"Synced commands to test guilds: {bot.debug_guilds}")
        
        # Then sync globally, but log what's happening
        current_command_names = {cmd.name for cmd in bot.application_commands}
        new_commands = current_command_names - existing_command_names
        removed_commands = existing_command_names - current_command_names
        
        if new_commands:
            print(f"Adding new commands: {', '.join(new_commands)}")
        if removed_commands:
            print(f"Removing commands: {', '.join(removed_commands)}")
            
        await bot.sync_commands()
        print("Synced commands globally")
    except Exception as e:
        print(f"Error syncing commands: {e}")
    
    print("Slash commands are now registered. They may take up to an hour to appear across all servers.")
    
    # Synchronize model settings across all cogs
    sync_models(bot)
    
    print('Model synchronization complete')
    
    # Check if ConfigCommands cog is loaded before accessing it
    if "ConfigCommands" in bot.cogs:
        print(f'Using global model: {bot.cogs["ConfigCommands"].state.get_global_model()}')
    else:
        # Print debug info about loaded cogs
        print(f"ConfigCommands cog not found. Available cogs: {list(bot.cogs.keys())}")
        print(f'Using default model: {DEFAULT_MODEL}')
    
    # Start the auto-save task after everything else is set up
    bot.loop.create_task(auto_save_state())
    print("Auto-save task started")
    
    # Load models (will use cached data if available)
    await bot.model_manager.get_models()
    logger.info(f"Logged in as {bot.user.name}")
    
    print('Ready to serve!')

async def auto_save_state():
    await bot.wait_until_ready()
    save_interval = 300  # 5 minutes
    prune_counter = 0
    
    print(f"Auto-save task started with interval {save_interval} seconds")
    
    while not bot.is_closed():
        try:
            state = BotStateManager()
            
            # Updated logging to include discord_threads
            channels = len(state.channel_history)
            threads = len(state.discord_threads)  # Updated to use discord_threads
            messages = sum(len(history) for history in state.channel_history.values())
            print(f"State before saving - Channels: {channels}, Threads: {threads}, Messages: {messages}, State ID: {id(state)}")
            
            # Prune old data every 4 save cycles (20 minutes)
            if prune_counter >= 3:
                print("Pruning old conversation data...")
                try:
                    prune_stats = state.prune_old_data()
                    print(f"Pruned: {prune_stats['channels_pruned']} channels, "
                          f"{prune_stats['threads_pruned']} threads, "
                          f"{prune_stats['messages_pruned']} messages")
                except Exception as prune_error:
                    print(f"Error during data pruning: {str(prune_error)}")
                    traceback.print_exc()
                prune_counter = 0
            else:
                prune_counter += 1
            
            # Save state
            if persistence.save_state(state):
                print(f"State auto-saved at {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
                
                # Log statistics about saved data
                channels = len(state.channel_history)
                threads = len(state.discord_threads)  # Updated to use discord_threads
                messages = sum(len(history) for history in state.channel_history.values())
                print(f"Saved data: {channels} channels, {threads} threads, {messages}")
                
                # Check if the file was actually written with data
                if os.path.exists(persistence.state_file):
                    file_size = os.path.getsize(persistence.state_file) / 1024
                    print(f"State file size after save: {file_size:.2f} KB")
        except Exception as e:
            print(f"Error during auto-save: {str(e)}")
            traceback.print_exc()
            
        await asyncio.sleep(save_interval)

@bot.slash_command(name="sync", description="Manually sync slash commands (owner only)")
@commands.is_owner()
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

@bot.slash_command(
    name="savestate", 
    description="Manually save the bot's current state (admin only)"
)
@commands.has_permissions(administrator=True)
async def save_state_command(ctx):
    await ctx.defer()
    
    try:
        state = BotStateManager()
        if persistence.save_state(state):
            # Count some stats for the response
            channels = len(state.channel_history)
            threads = len(state.discord_threads)  # Updated to use discord_threads
            messages = sum(len(history) for history in state.channel_history.values())
            
            # Get file size information
            file_size = "Unknown"
            if os.path.exists(persistence.state_file):
                file_size = f"{os.path.getsize(persistence.state_file) / 1024:.1f} KB"
            
            embed = discord.Embed(
                title="✅ State Saved Successfully",
                description="All conversation history and settings have been saved to disk.",
                color=discord.Color.green()
            )
            
            embed.add_field(
                name="Storage Statistics", 
                value=f"• Channels: {channels}\n• Threads: {threads}\n• Messages: {messages}\n• File size: {file_size}",
                inline=False
            )
            
            await ctx.respond(embed=embed)
        else:
            await ctx.respond("⚠️ Failed to save state. Check server logs for details.")
    except Exception as e:
        await ctx.respond(f"⚠️ Error: {str(e)}")
        traceback.print_exc()

@bot.slash_command(
    name="stateinfo", 
    description="Show information about the bot's saved state"
)
async def state_info_command(ctx):
    await ctx.defer()
    
    state = BotStateManager()
    embed = discord.Embed(
        title="Bot State Information",
        description="Current memory usage and settings",
        color=discord.Color.blue()
    )
    
    # Updated statistics to include discord_threads
    channels = len(state.channel_history)
    threads = len(state.discord_threads)
    messages = sum(len(history) for history in state.channel_history.values())
    thread_messages = sum(len(thread.get("messages", [])) for thread in state.discord_threads.values())
    
    embed.add_field(
        name="Memory Statistics",
        value=f"• Active channels: {channels}\n• Active threads: {threads}\n• Stored messages: {messages + thread_messages}",
        inline=False
    )
    
    # Add configuration
    embed.add_field(
        name="Current Settings",
        value=f"• Global model: `{state.global_model}`\n• Message history limit: {state.max_channel_history}\n• Time window: {state.time_window_hours} hours",
        inline=False
    )
    
    # Check if file exists and add file info
    if os.path.exists(persistence.state_file):
        file_size = os.path.getsize(persistence.state_file) / 1024  # Size in KB
        mod_time = datetime.fromtimestamp(os.path.getmtime(persistence.state_file))
        time_str = mod_time.strftime('%Y-%m-%d %H:%M:%S')
        
        embed.add_field(
            name="Storage Information",
            value=f"• Last saved: {time_str}\n• File size: {file_size:.1f} KB",
            inline=False
        )
    else:
        embed.add_field(
            name="Storage Information",
            value="No saved state file exists yet.",
            inline=False
        )
    
    await ctx.respond(embed=embed)

@bot.slash_command(name="test_dnd_cog", description="Test if the DND cog is loaded properly")
@commands.is_owner()
async def test_dnd_cog(ctx):
    await ctx.defer()
    
    if "DungeonMasterCommands" in bot.cogs:
        cog = bot.cogs["DungeonMasterCommands"]
        commands = []
        if hasattr(cog, "get_commands"):
            commands = [cmd.name for cmd in cog.get_commands()]
        
        # For application commands
        app_commands = []
        if hasattr(cog, "get_app_commands"):
            app_commands = [cmd.name for cmd in cog.get_app_commands()]
        
        await ctx.respond(
            f"✅ DungeonMasterCommands cog is loaded.\n"
            f"Regular commands: {commands}\n"
            f"App commands: {app_commands}\n"
            f"SlashCommandGroup: {hasattr(cog, 'adventure_group')}"
        )
    else:
        await ctx.respond("❌ DungeonMasterCommands cog is NOT loaded.")

if __name__ == "__main__":
    bot.run(DISCORD_TOKEN)