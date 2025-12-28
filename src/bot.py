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
from .config import DISCORD_TOKEN, OPENROUTER_API_KEY, SYSTEM_PROMPT, DEFAULT_MODEL, DATA_DIRECTORY, OPENAI_API_KEY, AI_HORDE_API_KEY
# Removed: from .utils.model_sync import sync_models
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

# Properly import client classes and ProviderManager
from .utils.openrouter_client import OpenRouterClient
from .utils.openai_client import OpenAIClient # Ensure this import is present
from .utils.ai_horde_client import AIHordeClient # Ensure this import is present
from .utils.model_manager import ProviderManager # Import ProviderManager


# Initialize provider clients
openrouter_client = OpenRouterClient(
    api_key=OPENROUTER_API_KEY,
    system_prompt=SYSTEM_PROMPT,
    default_model=DEFAULT_MODEL
)

# Initialize other clients (handle missing keys gracefully if needed)
openai_client = None
if OPENAI_API_KEY:
    openai_client = OpenAIClient(api_key=OPENAI_API_KEY)
    logger.info("OpenAI client initialized.")
else:
    logger.warning("OPENAI_API_KEY not found. OpenAI provider will not be available.")

ai_horde_client = None
if AI_HORDE_API_KEY:
    ai_horde_client = AIHordeClient(api_key=AI_HORDE_API_KEY)
    logger.info("AI Horde client initialized.")
else:
    logger.warning("AI_HORDE_API_KEY not found. AI Horde provider will not be available.")


# Create provider manager with all clients
provider_manager = ProviderManager(openrouter_client, openai_client, ai_horde_client, DATA_DIRECTORY)

# Add manager and individual clients to bot context
bot.model_manager = provider_manager # Use provider_manager here (already ProviderManager)
bot.openrouter_client = openrouter_client
bot.openai_client = openai_client
bot.ai_horde_client = ai_horde_client

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
        # "src.cogs.image_commands", # Replaced by unified_image_commands
        # "src.cogs.cloudflare_image_commands", # Replaced by unified_image_commands
        "src.cogs.unified_image_commands", # New unified image cog
        "src.cogs.url_commands",
        # New grouped command cogs
        "src.cogs.settings_commands",
        "src.cogs.channel_commands",
        "src.cogs.admin_commands"
    ]

    for cog in cogs:
        try:
            bot.load_extension(cog)
            print(f"{cog} loaded successfully.")
        except Exception as e:
            print(f"Error loading {cog}: {e}")
            # Print full traceback for config_commands to debug issues
            if cog == "src.cogs.config_commands":
                print(f"Detailed error for config commands: {traceback.format_exc()}")

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

    # Removed model synchronization call - handled by state manager and client selection now
    # sync_models(bot)
    # print('Model synchronization complete') # Removed log

    # Check if ConfigCommands cog is loaded before accessing it
    if "ConfigCommands" in bot.cogs:
        print(f'Using global model: {bot.cogs["ConfigCommands"].state.get_global_model()}')
    else:
        # Print debug info about loaded cogs
        print(f"ConfigCommands cog not found. Available cogs: {list(bot.cogs.keys())}")
        print(f'Using default model: {DEFAULT_MODEL}')


    # Load models for the global provider (will use cached data if available)
    # Ensure state_manager is available before accessing it
    if hasattr(bot, 'state_manager'):
        # Access the global_provider attribute directly
        global_provider = bot.state_manager.global_provider
        await bot.model_manager.get_models(global_provider)
        logger.info(f"Loaded models for global provider: {global_provider}")
    else:
        logger.warning("State manager not available, skipping initial model load.")

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
# Note: Admin commands (/sync, /debug, /stateinfo) have been moved to admin_commands.py
# They are now accessed as /admin sync, /admin debug, /admin state

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