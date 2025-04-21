# Gideon Discord Bot - Technical Documentation

## Table of Contents

1. [Overview](#overview)
2. [Architecture](#architecture)
3. [Core Components](#core-components)
4. [Bot Initialization and Lifecycle](#bot-initialization-and-lifecycle)
5. [State Management](#state-management)
6. [Command System](#command-system)
7. [Cogs (Command Modules)](#cogs-command-modules)
8. [API Integrations](#api-integrations)
9. [Adventure System](#adventure-system)
10. [Error Handling and Logging](#error-handling-and-logging)
11. [Security Considerations](#security-considerations)
12. [Configuration System](#configuration-system)
13. [Unified Image Commands](#unified-image-commands)

## Overview

Gideon is a feature-rich Discord bot that leverages AI capabilities to provide conversation, image generation, thread management, and tabletop RPG features. It integrates with multiple AI services through OpenRouter, AI Horde, and custom Cloudflare Workers to deliver a comprehensive AI assistant experience within Discord.

The bot follows a modular architecture using Py-Cord's cogs system, with state management via a singleton pattern that provides persistence across restarts. It supports multiple AI models and maintains conversation context for natural interactions.

## Architecture

### High-Level Structure

```
gideon/
├── src/                    # Source code
│   ├── bot.py              # Bot initialization
│   ├── config.py           # Configuration management
│   ├── __main__.py         # Entry point
│   ├── cogs/               # Command modules
│   │   ├── chat_commands.py            # AI conversation
│   │   ├── thread_commands.py          # Thread management
│   │   ├── config_commands.py          # Configuration commands
│   │   ├── diagnostic_commands.py      # Diagnostic tools
│   │   ├── mention_commands.py         # Mention handling
│   │   ├── unified_image_commands.py   # Unified image generation
│   │   ├── url_commands.py             # URL handling
│   │   ├── dungeon_master_commands.py  # RPG adventure system
│   │   └── news_feeds_commands.py      # RSS News Feed Summaries
│   └── utils/              # Utility functions
│       ├── openrouter_client.py  # OpenRouter API wrapper
│       ├── ai_horde_client.py    # AI Horde API wrapper
│       ├── cloudflare_client.py  # Cloudflare Worker API wrapper
│       ├── state_manager.py      # Conversation state management (uses database)
│       ├── database.py           # SQLite database interactions
│       ├── model_manager.py      # AI model management
│       ├── permissions.py        # Discord permissions utilities
│       └── model_sync.py         # Model synchronization
├── .env.example            # Environment variables template
└── requirements.txt        # Project dependencies
```

### Component Interactions

The bot is structured around these key interactions:

1. Py-Cord handles events and command dispatching
2. Cogs encapsulate related commands and functionality
3. The BotStateManager maintains conversation state and settings
4. API clients handle communication with external AI services
5. The database ensures data survives between restarts

## Core Components

### `bot.py`

The central component that initializes the Discord bot, sets up intents, loads cogs, handles signal interrupts, and manages the bot lifecycle.

Key responsibilities:
- Discord API connection
- Command registration and syncing
- Cog loading and management
- Signal handling for graceful shutdown
- Auto-save task scheduling
- Global error handling
- Debug/admin commands

### `BotStateManager` (`state_manager.py`)

A singleton class that stores and manages the bot's runtime state in memory. It interacts with the `Database` component for persistence. Responsibilities include managing:
- Conversation histories by channel/thread
- Thread metadata
- User configuration settings (models, prompts, etc.)
- News feed configurations and history
- Adventure game states

### `Database` (`database.py`)

Handles all interactions with the SQLite database (`gideon.db` by default). Responsibilities include:
- Initializing the database schema.
- Saving and loading bot state (configurations, histories, etc.).
- Providing methods for CRUD operations on various data types (feeds, threads, adventures).
- Ensuring data integrity and persistence across restarts.

### `OpenRouterClient` (`openrouter_client.py`)

Manages communication with the OpenRouter API, which provides access to various AI models. Handles:
- Sending messages with history context
- Managing model-specific parameters
- Processing responses
- Handling images when applicable

### `ModelManager` (`model_manager.py`)

Retrieves, caches, and provides information about available AI models through the OpenRouter API.

## Bot Initialization and Lifecycle

1. **Startup Sequence**
   - Load environment variables
   - Initialize intents and bot instance
   - Set up signal handlers for graceful shutdown
   - Create API clients and model manager
   - Register on_ready handler

2. **on_ready Execution**
   - Initialize and connect to the SQLite database
   - Load persistent state from the database into BotStateManager
   - Clear existing commands on Discord API
   - Load all cogs
   - Sync commands to Discord
   - Synchronize model settings across cogs
   - Start background tasks (e.g., auto-save, news checks)
   - Load available models from API

3. **Auto-save Task**
   - Runs on a 5-minute interval
   - Pruning old data every 4 save cycles
   - Logs detailed state information
   - Persists state to the database with error handling

4. **Shutdown Handling**
   - Captures SIGINT and SIGTERM signals
   - Saves state to the database before exit
   - Performs graceful database closure

## State Management

The `BotStateManager` manages the bot's operational state *in memory*. This state is loaded from and saved to the SQLite database by the `Database` component to ensure persistence.

### In-Memory Data Structures

The `BotStateManager` holds data structures similar to these (simplified examples):

1. **Channel History**
   ```python
   channel_history = {
       "channel_id_1": [
           {"role": "user", "content": "user message"},
           {"role": "assistant", "content": "bot response"}
       ],
       "channel_id_2": [ ... ]
   }
   ```

2. **Threads** (Deprecated Custom Implementation - Gideon now uses Discord Threads)
   *This structure is no longer actively used but might remain in older state files.*

3. **Discord Threads**
   ```python
   discord_threads = {
       "channel_id_1": {
           "thread_id_1": {
               "name": "Thread Name",
               "history": [ ... message objects ... ],
               "model": "specific-model-id",
               "system_prompt": "Custom prompt for this thread"
           }
       }
   }
   ```
   Note: Gideon uses Discord's native thread system. The older custom thread implementation has been deprecated.

4. **Configuration**
   ```python
   # General Config
   channel_models = {
       "channel_id_1": "model-id-for-channel",
       "channel_id_2": "different-model-id"
   }
   channel_system_prompts = {
       "channel_id_1": "Custom prompt for this channel"
   }
   global_model = "default-model-id"
   global_system_prompt = "Default system prompt"
   max_history_length = 100 # Example
   history_prune_window_hours = 24 # Example

   # News Feed Configuration
   news_feeds = {
       "feed_id_1": {
           "url": "http://example.com/rss",
           "name": "Example News",
           "category": "tech",
           "added_at": 1678886400.0,
           "last_checked": 1678890000.0
       }
   }
   news_channel_config = {
       "channel_id_1": {"categories": ["tech", "world"]},
       "channel_id_2": {"categories": ["all"]}
   }
   news_article_history = {
       "feed_id_1": {
           "article_guid_1": 1678890000.0,
           "article_guid_2": 1678890000.0
       }
   }
   news_update_frequency = 6 # Default hours

   # Adventure Configuration
   adventure_states = {
       "channel_id_1": { # AdventureState object data
           "setting": "Fantasy",
           "history": [...], # Conversation history for the adventure
           "scene_image_frequency": 5, # Generate image every 5 turns
           # ... other adventure-specific state
       }
   }
   ```

### Persistence and Pruning

- **Persistence:** The `Database` class handles writing the state held by `BotStateManager` to the SQLite file (`gideon.db`). This typically happens during the auto-save cycle and on shutdown.
- **Pruning:** The `BotStateManager` implements automatic pruning *before* saving to prevent excessive database growth and manage memory:

1. Applies time-window based pruning (default: 24 hours)
2. Enforces maximum history count per channel
3. Runs periodically during auto-save cycle
4. Returns statistics about pruned data

## Command System

Gideon uses Py-Cord's application commands (slash commands) exclusively. Commands are organized into logical cogs and registered globally with Discord.

### Command Registration

1. Commands are defined within cogs using decorators:
   ```python
   @discord.slash_command(
       name="command_name",
       description="Command description"
   )
   ```

2. During startup, commands are synced to Discord:
   ```python
   await bot.sync_commands()
   ```

3. For development, commands can be synced to specific guilds:
   ```python
   await bot.sync_commands(guild_ids=[guild_id])
   ```

### Permission System

Commands use Discord's permission system for access control:

1. Owner-only commands:
   ```python
   @commands.is_owner()
   ```

2. Administrator commands:
   ```python
   @commands.has_permissions(administrator=True)
   ```

## Cogs (Command Modules)

### ChatCommands (`chat_commands.py`)

Handles core AI conversation features:
- `/chat` - Main conversation command with image support
- `/search` - Web search command for current information
- `/reset` - Clears conversation history
- `/summarize` - Creates summary of current conversation
- `/memory` - Shows conversation statistics

Implementation details:
- Manages conversation context for OpenRouter
- Processes image attachments for vision models
- Handles streaming responses from AI models
- Implements markdown and code block formatting
- Integrates web search functionality

### ThreadCommands (`thread_commands.py`)

Manages conversations within Discord's native thread system:
- `/thread new` - Create new AI conversation thread
- `/thread message` - Send to specific thread
- `/thread list` - View all threads
- `/thread delete` - Remove thread
- `/thread rename` - Change thread name
- `/thread setmodel` - Set model for thread
- `/thread setsystem` - Set prompt for thread

Implementation details:
- Leverages Discord's built-in thread functionality
- Maintains separate configuration per thread
- Tracks thread state through BotStateManager

### ConfigCommands (`config_commands.py`)

Manages bot configuration:
- `/setmodel` - Change global model
- `/model` - View/change model
- `/setsystem` - Customize AI personality
- `/setchannelmodel` - Set model for current channel
- `/setchannelsystem` - Set prompt for channel
- `/setmemory` - Set message history limit
- `/setwindow` - Set time window for memory

Implementation details:
- Updates BotStateManager with new settings
- Ensures settings persist across restarts
- Provides validation for input parameters

### UnifiedImageCommands (`unified_image_commands.py`)

Handles unified AI image generation with support for multiple backend providers (AI Horde, Cloudflare Worker, OpenAI DALL-E).

- `/dream prompt:... [negative_prompt:...]`: Generate an image using the currently configured AI backend.
- `/dream manage set_provider provider:<Choice>` (Admin): Set the active image generation provider.
- `/dream manage configure <provider> [options...]` (Admin): Configure default settings for a specific provider.
- `/dream manage view_config` (Admin): View the current active provider and configuration.

Implementation details:
- Selects the appropriate API client based on the active provider configuration.
- Reads provider-specific default settings from the database.
- Passes user prompts and default settings to the selected client's generation method.
- Handles response formatting and error reporting for different providers.
- Provides admin commands for managing the active provider and its configuration, persisting settings to the database.

### DungeonMasterCommands (`dungeon_master_commands.py`)

Implements the tabletop RPG adventure system:
- `/adventure new` - Start new RPG adventure (Fantasy, Sci-Fi, Horror, Modern, Custom)
- `/adventure action` - Describe the action you want to take in the adventure.
- `/adventure roll` - Roll dice with narration (e.g., `1d20`, `2d6+3`).
- `/adventure status` - Check adventure status (setting, turn count, etc.).
- `/adventure end` - Conclude the adventure.
- `/adventure config_images` (Admin) - Configure scene image frequency (requires Cloudflare Worker).

Implementation details:
- Maintains adventure state per channel using `BotStateManager`.
- Uses the channel's configured AI model for narrative generation.
- Player interaction primarily happens through regular messages in the channel after starting an adventure, or using `/adventure action`.
- Implements dice rolling mechanism with parsing and narration.
- Manages adventure story progression and history.
- Integrates with Cloudflare image generation for optional scene visualization based on `config_images` setting.

### NewsFeedsCommands (`news_feeds_commands.py`)

Handles fetching, summarizing, and distributing news articles from RSS feeds.

- `/addfeed` (Admin): Adds a new RSS feed URL to monitor, assigning it a name and category.
- `/removefeed` (Admin): Removes a previously added RSS feed using its unique ID.
- `/listfeeds`: Lists all currently configured RSS feeds, grouped by category.
- `/subscribechannel` (Admin): Subscribes the current channel to receive updates from specified news categories (or 'all').
- `/unsubscribechannel` (Admin): Unsubscribes the current channel from all news updates.
- `/feedupdate` (Admin): Manually triggers a check for new articles across all feeds and posts updates to subscribed channels. Supports a `force_refresh` option.
- `/getnews`: Fetches and displays the latest news articles (up to 5 per feed) directly in the current channel, optionally filtering by category. Supports a `force_refresh` option.
- `/setfeedfrequency` (Admin): Sets how often (in hours) the bot automatically checks for new articles (1-24 hours).
- `/feedstatus`: Displays the status of configured feeds, including the last check time, channel subscriptions, and the next scheduled update time.
- `/myfeeds list`: (User) Show your saved personal RSS feeds.
- `/myfeeds add`: (User) Add an RSS feed URL to your personal list.
- `/myfeeds remove`: (User) Remove an RSS feed URL from your personal list.
- `/mynews`: (User) Get a personalized news digest from your saved feeds.

Implementation details:
- Uses `feedparser` library to parse RSS/Atom feeds.
- Integrates with `OpenRouterClient` to summarize article content using a configured AI model.
- Maintains state via `BotStateManager` and `Database` for:
    - `news_feeds`: Configured feeds (URL, name, category, last checked time).
    - `news_channel_config`: Channel subscriptions to feeds.
    - `news_article_history`: Seen article IDs per feed.
    - `news_update_frequency`: Hours between automatic checks.
    - `user_preferences`: Stores personal feed URLs per user for `/mynews`.
- Runs a background task (`check_news_feeds`) using `discord.ext.tasks` to periodically fetch and distribute updates.
- Handles potential errors during feed fetching, parsing, summarization, and posting.
- Truncates summaries to fit Discord embed limits.
- Provides user-specific feed management (`/myfeeds`) and personalized digests (`/mynews`).

## API Integrations

### OpenRouter Integration

Provides access to multiple AI models through a unified API:
- Supports various models (OpenAI, Claude, Gemini, Llama, Mistral, etc.)
- Handles context window limitations
- Manages rate limiting and retry logic
- Processes vision inputs for compatible models
- Supports web search capabilities for certain models (Note: This feature may incur additional costs on OpenRouter - see [OpenRouter Web Search Docs](https://openrouter.ai/docs/features/web-search) for details).

Implementation details:
- Formats messages according to model requirements
- Handles streaming responses
- Controls token usage and costs
- Manages model-specific parameters

### AI Horde Integration

Enables access to community-hosted image generation via the unified `/dream` command:
- Supports multiple Stable Diffusion variants
- Handles generation queue management
- Provides progress indicators
- Manages kudos/credits system

Implementation details:
- Forms proper image generation requests
- Polls for generation status
- Handles image download and processing
- Manages error states and timeouts

### Cloudflare Worker Integration

Provides Cloudflare Worker-based image generation via the unified `/dream` command:
- Allows for custom model implementations
- Can be configured for different backends

Implementation details:
- Handles worker authentication
- Processes API responses
- Manages timeouts and error states
- Provides diagnostics

### OpenAI Integration

Enables access to OpenAI's DALL-E models via the unified `/dream` command:
- Supports DALL-E 2 and DALL-E 3 models.
- Requires an `OPENAI_API_KEY`.

Implementation details:
- Communicates with the OpenAI API.
- Handles model-specific parameters (e.g., quality, style for DALL-E 3).
- Processes responses and image URLs.

## Adventure System

The tabletop RPG system is a complex feature combining:

1. **State Management**
   - Adventure progress tracking per channel (`adventure_states` in `BotStateManager`).
   - Character actions and narrative stored in adventure history.
   - Scene and narrative continuity maintained by the AI model.

2. **Narrative Generation**
   - Dynamic storytelling based on player actions (sent as messages or via `/adventure action`).
   - Setting-appropriate responses driven by the selected adventure setting and system prompt.
   - Context-aware narrative progression using conversation history.

3. **Dice System**
   - Standard RPG notation parsing (e.g., `1d20`, `2d6+3`).
   - Outcome narration based on roll results integrated into the AI response.

4. **Scene Visualization** (Optional)
   - Integration with Cloudflare image generation.
   - Dynamic prompt formation based on the narrative context.
   - Configurable generation frequency via `/adventure config_images`.
 
 5. **Game Mechanics**
   - Implicit character state and world state managed by the AI.
   - Action outcome determination handled by the AI based on narrative and dice rolls.

### Adventure Commands

- `/adventure new`: Start a new adventure in the current channel.
- `/adventure action`: Explicitly describe an action for the AI to process.
- `/adventure roll`: Perform a dice roll relevant to the adventure.
- `/adventure status`: Check the current state of the adventure.
- `/adventure end`: Conclude the adventure.
- `/adventure config_images`: Set how often scene images are generated.

*Note: Primary interaction after starting is typically done by sending messages directly in the channel.*

## Error Handling and Logging

### Error Handling Strategy

The bot implements multi-layered error handling:
1. Command-level try/except blocks
2. Cog-level error handlers
3. Global exception handling
4. Signal interrupt handlers

### Logging System

Implements Python's logging module:
- Configurable log levels
- Console and file logging
- Detailed tracebacks for critical errors

Implementation details:
- Structured logging for key operations
- Debug vs. production logging configuration
- Error reporting to administrators

### Error Response Examples

The bot formats error responses consistently:
```python
await ctx.send(f"⚠️ Error: {str(e)}")
```

## Security Considerations

### API Key Management

- All sensitive keys stored in environment variables
- No hardcoded credentials in source code
- Runtime-only access to credentials

### Permission Controls

- Owner-only commands for sensitive operations
- Administrator permission checks for configuration
- Regular user commands have appropriate limitations

### Data Protection

- The SQLite database file (`gideon.db`) contains conversation history and configurations.
- The database file itself is not encrypted by the bot (filesystem encryption may apply).
- Automatic pruning helps manage the size of the stored data.

### Input Validation

- Command inputs validated before processing
- API responses sanitized before display
- Error handling prevents information leakage

## Configuration System

### Environment Variables

Configured through `.env` file:
- `DISCORD_TOKEN` - Bot authentication
- `OPENROUTER_API_KEY` - OpenRouter access
- `SYSTEM_PROMPT` - Default AI personality
- `DEFAULT_MODEL` - Fallback AI model
- `DATA_DIRECTORY` - Storage location
- `AI_HORDE_API_KEY` - Optional for AI Horde image generation
- `CLOUDFLARE_WORKER_URL` - Optional for Cloudflare Worker image generation
- `CLOUDFLARE_API_KEY` - Optional authentication for Cloudflare Worker
- `OPENAI_API_KEY` - Optional for OpenAI image generation
- `OPENAI_API_KEY` - Optional for OpenAI image generation

### Runtime Configuration

Dynamic settings stored in `BotStateManager`:
- Global model selection
- Channel-specific models
- Thread-specific configurations
- System prompts for different contexts
- Memory limits and time windows
- User preferences (e.g., personal RSS feeds)
