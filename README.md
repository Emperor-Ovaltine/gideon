<div align="center">

# 🤖 Gideon - AI Assistant for Discord

<img src="assets/images/gideon-logo.jpeg" alt="Gideon Logo" width="400"/>

<a href="https://www.python.org/"><img src="https://img.shields.io/badge/python-3.8+-blue.svg?style=for-the-badge&logo=python&logoColor=white" alt="Python 3.8+"></a>
<a href="https://github.com/Pycord-Development/pycord"><img src="https://img.shields.io/badge/py--cord-2.4+-5865F2.svg?style=for-the-badge&logo=discord&logoColor=white" alt="Py-Cord 2.4+"></a>
<a href="LICENSE"><img src="https://img.shields.io/badge/license-MIT-green.svg?style=for-the-badge" alt="License MIT"></a>

*Your server's intelligent companion powered by cutting-edge AI models*

[Installation](#-installation) • 
[Features](#-features) • 
[Commands](#-commands) • 
[Models](#-supported-models) • 
[Troubleshooting](#-troubleshooting) •
[Documentation](documentation.md)

</div>

## 🌟 Overview

Gideon transforms your Discord server into an AI-powered hub, connecting members to state-of-the-art language and image models. With Gideon, users can have intelligent conversations, generate creative images, analyze visual content, summarize news feeds, manage URLs, create fantasy adventures, and organize discussions through an intuitive thread system.

## ✨ Features

### 🧠 Intelligence
- **Multiple AI Models** - Access OpenAI, Anthropic Claude, Google Gemini, and more through OpenRouter

<p align="center">
  <img src="assets/images/dynamic-model-search.png" alt="dynamic-model-search" width="1200"/>
</p>

- **Conversation Memory** - Natural conversations with context across messages

- **Web Search** - Search the web for current information through conversational AI responses

<img src="assets/images/web-search1.png" alt="web-search-demo" width="800"/>
<img src="assets/images/web-search2.png" alt="web-search-demo" width="800"/>
<img src="assets/images/web-search3.png" alt="web-search-demo" width="800"/>

- **Image Analysis** - Upload and analyze images with vision-capable AI models

<p align="center">
  <img src="assets/images/image-analyze-screenshot.png" alt="analyze-demo" width="1200"/>
</p>

<p align="center">
  <img src="assets/images/replys-to-at-tags.png" alt="analyze-demo" width="1200"/>
</p>

- **Image Generation** - Create stunning visuals using a unified command (`/dream`) with support for multiple backend providers (AI Horde, Cloudflare Worker, OpenAI DALL-E). Admins can configure the active provider and its default settings.

<p align="center">
  <img src="assets/images/imagine-screenshot.png" alt="imagine-queue" width="1200"/>
</p>

<p align="center">
  <img src="assets/images/imagine-queue-screenshot.png" alt="imagine-queue" width="1200"/>
</p>

<p align="center">
  <img src="assets/images/imagine-tea-screenshot.png" alt="imagine-queue" width="1200"/>
</p>

### 🧵 Organization
- **Conversation Threads** - Create dedicated topics with independent histories using Discord's native threads
- **Auto-Responses** - Bot automatically responds to all messages in AI threads

<p align="center">
  <img src="assets/images/ai-chat-threads.png" alt="ai-thread-demo" width="1200"/>
</p>

<p align="center">
  <img src="assets/images/ai-chat-threads-2.png" alt="ai-thread-demo" width="1200"/>
</p>

<p align="center">
  <img src="assets/images/ai-threads-3.png" alt="ai-thread-demo" width="1200"/>
</p>

- **Dynamic URL Summarization** - Instantly extracts and distills key information from any shared webpage, providing concise, up-to-date summaries directly in your chat.

<p align="center">
  <img src="assets/images/url-summarize-entry-screenshot.png" alt="url-summary-demo" width="1200"/>
</p>

<p align="center">
  <img src="assets/images/url-summary-screenshot.png" alt="url-summary-demo" width="1200"/>
</p>


### 🎲 Adventure System
- **Interactive Adventures** - Create and explore AI-driven tabletop RPG campaigns
- **Multiple Settings** - Choose from Fantasy, Sci-Fi, Horror, Modern, or Custom worlds
- **Dice Rolling** - Integrated dice mechanics with automatic result narration
- **Campaign State Tracking** - Track progress and character actions throughout your adventure
- **Automatic Scene Visualization** - Generate images of key moments in your adventure (requires Cloudflare Worker)

### 🛠️ Customization
- **Model Switching** - Change AI models on-the-fly with simple commands
- **Channel Personalities** - Set different system prompts per channel
- **Admin Controls** - Comprehensive configuration options for server admins

## 🚀 Installation

There are two ways to install and run Gideon: using Docker (recommended for ease of deployment and management) or directly with Python.

### Prerequisites

**For both methods:**
- Git installed
- Discord bot token with Message Content Intent enabled ([Discord Developer Portal](https://discord.com/developers/applications))
- OpenRouter API key ([OpenRouter.ai](https://openrouter.ai/))
- AI Horde API key (optional, for `/imagine` command - [AI Horde](https://aihorde.net/register))
- Cloudflare Worker URL & API Key (optional, for `/dream` command and Adventure scene visualization - requires self-setup, see [Cloudflare Worker Configuration](#cloudflare-worker-configuration-optional))

**For Docker Installation:**
- Docker installed
- Docker Compose installed (usually included with Docker Desktop)

**For Python Installation:**
- Python 3.8+

### Docker Installation (Recommended)

1.  **Clone the Repository:**
    ```bash
    git clone https://github.com/Emperor-Ovaltine/gideon
    cd gideon
    ```

2.  **Configure Environment:**
    *   Copy the example environment file:
        ```bash
        cp .env.example .env
        ```
    *   **Edit the `.env` file** with your actual API keys and tokens (`DISCORD_TOKEN`, `OPENROUTER_API_KEY`, etc.). Leave `DATA_DIRECTORY` blank or commented out when using Docker Compose with the provided configuration, as the volume mount handles data persistence.

3.  **Build the Docker Image:**
    *   Build the image using the included Dockerfile. This command builds the image and tags it as `gideon-bot:latest`.
        ```bash
        docker build -t gideon-bot:latest .
        ```
    *   *(Optional)* If you plan to distribute the image or use a registry like Docker Hub or GHCR, you would tag and push the image here.

4.  **Configure Docker Compose:**
    *   Open the `docker-compose.yml` file.
    *   **Verify the `volumes` section.** The default `docker-compose.yml` is set up to use a bind mount. It maps a directory from your host machine to the `/app/data` directory inside the container.
        ```yaml
        # Example docker-compose.yml volume section:
        volumes:
          # This maps a host directory to the container's data directory
          - ./gideon_data:/app/data # Example: Creates 'gideon_data' in the current directory
        ```
    *   **Important:** Ensure the host path part (`./gideon_data` in the example) points to a location where Docker has permission to create/write files. Using a relative path like `./gideon_data` will create the directory within your `gideon` project folder.
    *   *(Optional)* If you pushed your image to a registry in step 3, update the `image:` line to point to your registry image (e.g., `image: your-dockerhub-username/gideon:latest` or `image: ghcr.io/your-github-username/gideon:latest`). Otherwise, leave it as `image: gideon-bot:latest` to use the locally built image.

5.  **Run the Container:**
    *   Start the bot using Docker Compose in detached mode (runs in the background):
        ```bash
        docker-compose up -d
        ```
    *   To view logs: `docker-compose logs -f`
    *   To stop the bot: `docker-compose down`

### Python Installation

```bash
# Clone and enter repository (if not already done)
# git clone https://github.com/Emperor-Ovaltine/gideon
# cd gideon

# Set up environment and dependencies
python3 -m venv venv
source venv/bin/activate  # On Windows: venv\Scripts\activate
pip install -r requirements.txt

# Configure bot
cp .env.example .env
# Edit .env with your Discord token, OpenRouter API key, AI Horde API key,
# AND set the DATA_DIRECTORY to an absolute path where the bot can write data.
# Example: DATA_DIRECTORY=/home/user/gideon_data
# If DATA_DIRECTORY is not set, data (including the SQLite database file, typically 'gideon.db')
# will be stored in a 'data' subdirectory within the project.

# Launch
python3 -m src
```

### Discord Configuration

1. Create an application at [Discord Developer Portal](https://discord.com/developers/applications)
2. Under "Bot" tab:
   - Enable "Message Content Intent"
   - Copy your bot token for the `.env` file
3. Generate invite URL in "OAuth2 > URL Generator":
   - Scopes: `bot`, `applications.commands`
   - Permissions: Send Messages, Read Message History, Embed Links, Use Slash Commands, Manage Threads (for `/thread` commands)

### Image Generation Provider Configuration (Optional)

Gideon's unified `/dream` command supports multiple backend providers. To enable providers other than the default AI Horde, you need to configure their respective API keys or endpoints in your `.env` file.

**Cloudflare Worker (Optional)**

**⚠️ IMPORTANT:** Setting up and deploying the Cloudflare Worker is the responsibility of the end user. Gideon does not provide support for configuring or troubleshooting Cloudflare Workers.

If you want to use your own Cloudflare Worker as an image generation provider or enable Adventure scene visualization via a worker:

1. Create and deploy your own Cloudflare Worker that can generate images (e.g., using Cloudflare's AI platform or another service).
2. The worker should accept a JSON payload with at least a `prompt` field and return image data.
3. Set the `CLOUDFLARE_WORKER_URL` in your `.env` file to your worker's URL.
4. Optionally set `CLOUDFLARE_API_KEY` if your worker requires authentication (e.g., via a header like `Authorization: Bearer YOUR_KEY`).

An example Cloudflare worker that has been tested with Gideon can be found here: [flux1-cloudflare-worker](https://github.com/Emperor-Ovaltine/flux1-cloudflare-worker)

**OpenAI (Optional)**

If you want to use OpenAI's DALL-E models for image generation:

1. Obtain an OpenAI API key from the [OpenAI platform](https://platform.openai.com/).
2. Set the `OPENAI_API_KEY` in your `.env` file to your OpenAI API key.

**Example /dream output**

<p align="center">
  <img src="assets/images/dream-tea-screenshot.png" alt="dream-output" width="1080"/>
</p>


## 🤖 Commands

### General Commands
| Command | Description |
|:-------:|:------------|
| `/chat` | Start a conversation with the AI (supports image uploads for vision models) |
| `/search` | Search the web for current information using the AI |
| `/reset` | Clear the conversation history for the current channel |
| `/summarize` | Summarize the current conversation history |
| `/memory` | Show conversation statistics (message count, history window) |

### URL Commands
| Command | Description |
|:-------:|:------------|
| `/summarizeurl` | Fetch and summarize the content of a given URL |

### Settings Commands (Admin)
Manage global bot configuration settings.

| Command | Description |
|:-------:|:------------|
| `/settings show` | View all current global settings |
| `/settings model` | Set global AI model (format: provider/model) |
| `/settings system` | Set global system prompt |
| `/settings provider` | Set global AI provider (openrouter/openai) |
| `/settings memory` | Set message history limit |
| `/settings window` | Set time window for history (hours) |
| `/settings restore` | Reset all settings to defaults |

### Channel Commands (Admin)
Configure channel-specific overrides for AI behavior.

| Command | Description |
|:-------:|:------------|
| `/channel show` | View current channel settings |
| `/channel model` | Set AI model for this channel |
| `/channel system` | Set system prompt for this channel |
| `/channel provider` | Set AI provider for this channel |
| `/channel reset` | Clear all channel overrides |
| `/channel list` | List all channels with custom settings |

### Thread Commands
Gideon leverages Discord's native thread system to organize conversations and create dedicated AI chat spaces.

| Command | Description |
|:-------:|:------------|
| `/thread new` | Create a new AI conversation thread |
| `/thread message` | Send a message to a specific thread |
| `/thread list` | View all active AI threads in the channel |
| `/thread show` | View thread configuration settings |
| `/thread model` | Set AI model for this thread |
| `/thread system` | Set system prompt for this thread |
| `/thread rename` | Change the name of an AI thread |
| `/thread delete` | Remove an AI thread and its history |

### Admin Commands
Administrative tools and diagnostics (Admin/Owner only).

| Command | Description |
|:-------:|:------------|
| `/admin sync` | Sync slash commands with Discord (Owner only) |
| `/admin debug` | Show debug information |
| `/admin state` | Display database state information |
| `/admin diagnostic` | Run system diagnostics |
| `/admin vision_models` | List all vision-capable AI models |

### Image Commands
Gideon now uses a unified command for image generation with support for multiple backend providers.

| Command | Description | Permissions |
|:-------:|:------------|:------------|
| `/dream prompt:... [negative_prompt:...]` | Generate an image using the currently configured AI backend. | All Users |
| `/dream manage set_provider provider:<Choice>` | Set the active image generation provider (AI Horde, Cloudflare, OpenAI). | Admin |
| `/dream manage configure <provider> [options...]` | Configure default settings for a specific provider (e.g., model, size, steps). | Admin |
| `/dream manage view_config` | View the current active provider and configuration for all providers. | Admin |

## 📚 Supported Models

### Text Models (via OpenRouter)
- **OpenAI**: GPT-4o, GPT-4o-mini, GPT-4 Turbo, etc.
- **Anthropic**: Claude 3.7 Sonnet, Claude 3 Opus, Claude 3 Haiku, etc.
- **Google**: Gemini 2.0 Flash, Gemini Pro 1.5, etc.
- **Meta**: Llama 3 70B, 8B, etc.
- **Mistral**: Mistral Large, Mixtral 8x22B, etc.
- **Perplexity**: Sonar Large, Sonar Small
- **And many more!** Check [OpenRouter.ai](https://openrouter.ai/models) for the full list.

### Image Models
#### Via AI Horde
- **Stable Diffusion**: SD 2.1, SDXL, and various fine-tuned community models.
- Check `/hordemodels` for currently available options.

#### Via Cloudflare Worker (requires self-setup)
- **Custom model implementation** - Your Cloudflare Worker can integrate any image generation model you choose (e.g., Stable Diffusion via Cloudflare's platform).

## 📁 Project Structure

```
gideon/
├── src/                    # Source code
│   ├── bot.py              # Bot initialization & core logic
│   ├── config.py           # Configuration loading (.env)
│   ├── __main__.py         # Entry point for running the bot
│   ├── cogs/               # Command modules (features)
│   │   ├── admin_commands.py        # Admin tools (/admin group)
│   │   ├── channel_commands.py      # Channel settings (/channel group)
│   │   ├── chat_commands.py         # AI chat commands (/chat, /reset, etc.)
│   │   ├── config_commands.py       # Legacy commands (deprecated)
│   │   ├── diagnostic_commands.py   # Diagnostic utilities
│   │   ├── mention_commands.py      # Bot mention handling
│   │   ├── settings_commands.py     # Global settings (/settings group)
│   │   ├── thread_commands.py       # Thread management (/thread group)
│   │   ├── unified_image_commands.py # Image generation (/dream)
│   │   └── url_commands.py          # URL summarization
│   └── utils/              # Utility classes and functions
│       ├── ai_horde_client.py    # API client for AI Horde
│       ├── cloudflare_client.py  # API client for Cloudflare Worker
│       ├── database.py           # SQLite database interactions
│       ├── model_manager.py      # AI model management
│       ├── openai_client.py      # API client for OpenAI
│       ├── openrouter_client.py  # API client for OpenRouter
│       ├── permissions.py        # Permission checks
│       ├── state_manager.py      # Centralized state management
│       └── ...
├── .env.example            # Environment variables template
├── Dockerfile              # For building the Docker image
├── docker-compose.yml      # For running with Docker Compose
├── requirements.txt        # Python dependencies
├── README.md               # This file
├── documentation.md        # Detailed technical documentation
└── index.md                # GitHub Pages source file
```

## ❓ Troubleshooting

*   **Bot Offline/Unresponsive:**
    *   **Python:** Check if the `python src/__main__.py` process is running. Check console logs for startup errors.
    *   **Docker:** Check container status (`docker ps`). Check container logs (`docker-compose logs -f` or `docker logs <container_id>`).
    *   Verify `DISCORD_TOKEN` in `.env` is correct.
    *   Ensure the bot has necessary permissions (`Send Messages`, `Read History`, `Use Slash Commands`, etc.) in the server. Discord might take time to register commands after startup.
*   **Commands Not Working:**
    *   **Permissions:** Ensure you have the required permissions (e.g., Admin for config commands).
    *   **API Keys:** Verify API keys (`OPENROUTER_API_KEY`, `OPENAI_API_KEY`, `AI_HORDE_API_KEY`, `CLOUDFLARE_API_KEY`) in `.env` are correct for the features you're using. Check `/model` for the active chat provider. Check `/dream manage view_config` for the active image provider.
    *   **Provider Issues:** Check the status of external services (OpenRouter, OpenAI, AI Horde). Check your account balance/credits if applicable.
    *   **Logs:** Check the bot's console/container logs for specific error messages from the API or internal processes.
*   **Image Generation (`/dream`) Failures:**
    *   Verify provider configuration (`/dream manage view_config`) and API keys/URLs in `.env`.
    *   Ensure the bot has `Attach Files` and `Embed Links` permissions.
    *   Try simpler prompts, different models, or smaller dimensions/fewer steps via `/dream configure`.
    *   Check AI Horde status/kudos if using that provider.
    *   If using Cloudflare, ensure your worker is deployed and running correctly.
*   **Database/State Issues:**
    *   Ensure the `DATA_DIRECTORY` path (Python) or Docker volume mount (`./gideon_data:/app/data` in `docker-compose.yml`) is correct and writable by the bot process.
    *   Check logs for SQLite errors (e.g., "database is locked", "unable to open database file").

## 📖 Documentation

For detailed technical information about Gideon's architecture, implementation details, and advanced setup instructions, please refer to the [Technical Documentation](documentation.md).

<div align="center">
Made with ❤️ by <a href="https://github.com/eoko-dev">eoko</a>
</div>
