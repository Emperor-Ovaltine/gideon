import discord
from discord.ext import commands, tasks # Import tasks
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

    # Initialize State Manager (connects to DB, loads config)
    print("Initializing state manager and database...")
    try:
        state = BotStateManager()
        # Initialize state FIRST (this connects to DB and loads config)
        await state.initialize_state()
        # NOW inject the ModelManager
        state.set_model_manager(bot.model_manager)
        bot.state_manager = state # Attach the initialized state manager to the bot
        print("State manager initialized successfully.")
        # Log initial state from DB if needed (e.g., global model)
        print(f"Loaded global model from DB: {bot.state_manager.get_global_model()}")
    except Exception as e:
        print(f"FATAL: Failed to initialize state manager or database: {e}", file=sys.stderr)
        traceback.print_exc()
        # Optionally, exit if DB connection fails critically
        # await bot.close()
        # return # Stop further execution in on_ready

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
        "src.cogs.dungeon_master_commands",
        "src.cogs.news_feeds_commands"  # Add our new cog here
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


    # Load models (will use cached data if available)
    await bot.model_manager.get_models()
    logger.info(f"Logged in as {bot.user.name}")

    # Start background tasks after everything is ready
    if not prune_data_task.is_running():
        # Set initial interval from loaded config
        try:
            # Ensure state_manager is available before accessing it
            if hasattr(bot, 'state_manager'):
                prune_hours = bot.state_manager.get_prune_frequency_hours()
                prune_data_task.change_interval(hours=prune_hours)
                prune_data_task.start()
                print(f"Started data pruning task to run every {prune_hours} hours.")
            else:
                print("Error: State manager not initialized before starting pruning task.", file=sys.stderr)
        except Exception as e:
            print(f"Error starting pruning task: {e}", file=sys.stderr)
            traceback.print_exc()

    print('Ready to serve!')


# --- Background Tasks ---

@tasks.loop(hours=24) # Default interval, will be changed in on_ready
async def prune_data_task():
    """Periodically prunes old data from the database."""
    if not bot.is_ready() or not hasattr(bot, 'state_manager'):
        logger.debug("Pruning task: Bot not ready or state manager not available yet.")
        return # Wait until bot is ready and state_manager is attached

    logger.info("Running periodic data pruning...")
    try:
        state = bot.state_manager # Get the initialized state manager
        prune_stats = state.prune_old_data()
        logger.info(f"Data pruning finished: {prune_stats}")
    except Exception as e:
        logger.error(f"Error during scheduled data pruning: {e}", exc_info=True)

@prune_data_task.before_loop
async def before_prune_data_task():
    """Wait until the bot is ready before starting the pruning task."""
    await bot.wait_until_ready()
    # Ensure state manager is initialized (redundant check, but safe)
    while not hasattr(bot, 'state_manager'):
        logger.debug("before_prune_data_task: Waiting for state_manager...")
        await asyncio.sleep(5)
    logger.info("Pruning task ready.")

# Attach the task to the bot instance so cogs can access it
bot.prune_data_task = prune_data_task


# --- Bot Commands ---

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
    name="stateinfo",
    description="Show information about the bot's saved state"
)
@commands.has_permissions(administrator=True)
async def state_info_command(ctx):
    await ctx.defer()

    state = BotStateManager() # Get instance
    embed = discord.Embed(
        title="Bot State Information",
        description="Current database statistics and settings",
        color=discord.Color.blue()
    )

    # Get statistics from the database via state manager methods
    try:
        total_messages = state.get_message_count()
        total_threads = state.get_thread_count()
        total_feeds = state.get_news_feeds_count()
        total_subscriptions = state.get_news_channel_config_count()
        # Note: Getting active channel count isn't straightforward without querying messages/config
        # We can report total messages and threads instead.

        embed.add_field(
            name="Database Statistics",
            value=(f"• Stored Messages: {total_messages if total_messages >= 0 else 'Error'}\n"
                   f"• Stored Threads: {total_threads if total_threads >= 0 else 'Error'}"),
            inline=False
        )

        embed.add_field(
            name="News Feed Statistics",
            value=(f"• Configured Feeds: {total_feeds if total_feeds >= 0 else 'Error'}\n"
                   f"• Channel Subscriptions: {total_subscriptions if total_subscriptions >= 0 else 'Error'}"),
            # Add tracked articles count if needed (requires another DB query)
            inline=False
        )

    except Exception as e:
        logger.error(f"Error fetching stats for /stateinfo: {e}", exc_info=True)
        embed.add_field(name="Statistics Error", value="Could not retrieve database statistics.", inline=False)


    # Add configuration (fetched from state manager's cached values)
    embed.add_field(
        name="Current Settings",
        value=(f"• Global model: `{state.get_global_model()}`\n"
               f"• Message history limit: {state.get_max_channel_history()}\n"
               f"• Pruning time window: {state.get_time_window_hours()} hours\n"
               f"• News Update Frequency: {state.get_news_update_frequency()} hours\n"
               f"• News Broadcast Channel: {state.get_news_broadcast_channel_id() or 'Not Set'}"),
        inline=False
    )

    # Add database file info
    db_path = state.db_manager.db_path
    db_size_kb = "N/A"
    db_mod_time = "N/A"
    if os.path.exists(db_path):
        try:
            db_size_kb = f"{os.path.getsize(db_path) / 1024:.1f} KB"
            mod_time = datetime.fromtimestamp(os.path.getmtime(db_path))
            db_mod_time = mod_time.strftime('%Y-%m-%d %H:%M:%S')
        except Exception as e:
            logger.warning(f"Could not get DB file info: {e}")

    embed.add_field(
        name="Storage Information",
        value=(f"• Database File: `{db_path}`\n"
               f"• File Size: {db_size_kb}\n"
               f"• Last Modified: {db_mod_time}"),
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

# --- Bot Events ---

@bot.event
async def on_close():
    """Clean up resources when the bot is shutting down."""
    print("Bot closing down...")
    try:
        state = BotStateManager()
        state.close_db() # Close the database connection
        print("Database connection closed.")
    except Exception as e:
        print(f"Error closing database connection: {e}")
    print("Shutdown complete.")


if __name__ == "__main__":
    # Setup logging
    logging.basicConfig(level=logging.INFO, format='%(asctime)s:%(levelname)s:%(name)s: %(message)s')
    # Optionally set higher level for noisy libraries
    logging.getLogger('discord').setLevel(logging.WARNING)
    logging.getLogger('websockets').setLevel(logging.WARNING)

    # Run the bot
    try:
        bot.run(DISCORD_TOKEN)
    except Exception as e:
        print(f"FATAL: Error running bot: {e}", file=sys.stderr)
        traceback.print_exc()