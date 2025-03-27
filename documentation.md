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
│   │   ├── image_commands.py           # AI Horde image generation
│   │   ├── cloudflare_image_commands.py # Cloudflare-based image generation
│   │   ├── url_commands.py             # URL handling
│   │   └── dungeon_master_commands.py  # RPG adventure system
│   └── utils/              # Utility functions
│       ├── openrouter_client.py  # OpenRouter API wrapper
│       ├── ai_horde_client.py    # AI Horde API wrapper
│       ├── cloudflare_client.py  # Cloudflare Worker API wrapper
│       ├── state_manager.py      # Conversation state management
│       ├── persistence.py        # State persistence
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
5. State persistence ensures data survives between restarts

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

A singleton class that stores and manages:
- Conversation histories by channel
- Thread metadata and conversations
- User configuration settings
- Channel-specific model settings
- System prompts for different contexts
- Discord threads

### `StatePersistence` (`persistence.py`)

Handles saving and loading state data to/from disk, ensuring conversation continuity across bot restarts.

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
   - Load persistent state from disk
   - Clear existing commands on Discord API
   - Load all cogs
   - Sync commands to Discord
   - Synchronize model settings across cogs
   - Start auto-save task
   - Load available models from API

3. **Auto-save Task**
   - Runs on a 5-minute interval
   - Pruning old data every 4 save cycles
   - Logs detailed state information
   - Persists state to disk with error handling

4. **Shutdown Handling**
   - Captures SIGINT and SIGTERM signals
   - Saves state before exit
   - Performs graceful database closure if applicable

## State Management

### Data Structure

The `BotStateManager` maintains these key data structures:

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

2. **Threads**
   ```python
   threads = {
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
   channel_models = {
       "channel_id_1": "model-id-for-channel",
       "channel_id_2": "different-model-id"
   }
   
   channel_system_prompts = {
       "channel_id_1": "Custom prompt for this channel"
   }
   ```

### Pruning Mechanism

The bot implements automatic pruning to prevent excessive memory usage:

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
- `/reset` - Clears conversation history
- `/summarize` - Creates summary of current conversation
- `/memory` - Shows conversation statistics

Implementation details:
- Manages conversation context for OpenRouter
- Processes image attachments for vision models
- Handles streaming responses from AI models
- Implements markdown and code block formatting

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

### ImageCommands (`image_commands.py`)

Handles AI Horde image generation:
- `/imagine` - Generate images from text
- `/hordemodels` - List available models

Implementation details:
- Communicates with AI Horde API
- Manages generation settings (dimensions, steps, etc.)
- Handles generation queuing and waiting
- Provides progress updates

### CloudflareImageCommands (`cloudflare_image_commands.py`)

Provides Cloudflare Worker-based image generation:
- `/dream` - Generate images using Cloudflare
- `/cftest` - Test connection to Cloudflare Worker

Implementation details:
- Handles authentication with Cloudflare Worker
- Manages request formatting and response parsing
- Implements error handling for worker connectivity

### DungeonMasterCommands (`dungeon_master_commands.py`)

Implements the tabletop RPG adventure system:
- `/adventure start` - Start new RPG adventure
- `/adventure action` - Take action in adventure
- `/adventure roll` - Roll dice with narration
- `/adventure status` - Check adventure status
- `/adventure end` - End current adventure
- `/adventure config_images` - Configure scene image frequency

Implementation details:
- Maintains adventure state with character tracking
- Implements dice rolling mechanism
- Manages adventure story progression
- Integrates with image generation for scene visualization

## API Integrations

### OpenRouter Integration

Provides access to multiple AI models through a unified API:
- Supports various models (OpenAI, Claude, Gemini, etc.)
- Handles context window limitations
- Manages rate limiting and retry logic
- Processes vision inputs for compatible models

Implementation details:
- Formats messages according to model requirements
- Handles streaming responses
- Controls token usage and costs
- Manages model-specific parameters

### AI Horde Integration

Enables access to community-hosted image generation:
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

Custom implementation for additional image generation:
- Provides alternative to AI Horde when available
- Allows for custom model implementations
- Can be configured for different backends

Implementation details:
- Handles worker authentication
- Processes API responses
- Manages timeouts and error states
- Provides diagnostics

### Cloudflare Worker Setup

To configure Cloudflare Worker for image generation:
1. Create a Cloudflare Worker and deploy your custom image generation script.
2. Set the `CLOUDFLARE_WORKER_URL` and `CLOUDFLARE_API_KEY` in the `.env` file.
3. Test the connection using the `/cftest` command.

## Adventure System

The tabletop RPG system is a complex feature combining:

1. **State Management**
   - Adventure progress tracking
   - Character state persistence
   - Scene and narrative continuity

2. **Narrative Generation**
   - Dynamic storytelling based on player actions
   - Setting-appropriate responses (fantasy, sci-fi, etc.)
   - Context-aware narrative progression

3. **Dice System**
   - Standard RPG notation (1d20, 2d6+3, etc.)
   - Outcome narration based on roll results
   - Statistical distribution handling

4. **Scene Visualization**
   - Integration with image generation
   - Dynamic prompt formation from narrative
   - Configurable generation frequency

5. **Game Mechanics**
   - Implicit character stats tracking
   - Action outcome determination
   - Game balance considerations

### Adventure Commands

Use `/adventure new` to start a new adventure.

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

- State file contains conversation history
- No encryption of state file (potential improvement)
- Automatic pruning of old conversations

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
- `AI_HORDE_API_KEY` - Optional for image generation
- `CLOUDFLARE_WORKER_URL` - Optional for custom image generation
- `CLOUDFLARE_API_KEY` - Optional authentication

### Runtime Configuration

Dynamic settings stored in `BotStateManager`:
- Global model selection
- Channel-specific models
- Thread-specific configurations
- System prompts for different contexts
- Memory limits and time windows
