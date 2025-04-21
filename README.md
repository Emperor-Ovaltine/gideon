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

### 📰 News Feed Summaries
- **RSS Feed Monitoring** - Add and manage RSS feeds by category (tech, world, finance, etc.)

<p align="center">
  <img src="assets/images/rss-feed1.png" alt="rss-feed-setup" width="1200"/>
</p>

- **AI Summarization** - Automatically summarize new articles using configured AI models

<p align="center">
  <img src="assets/images/rss-feed2.png" alt="rss-feed-summary" width="1200"/>
</p>

- **Channel Subscriptions** - Subscribe channels to specific news categories or all feeds
- **Scheduled Updates** - Configure how often the bot checks for and posts news updates
- **Manual Fetching** - Manually trigger news updates or fetch news on demand

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


### 🎲 Fantasy Game Master
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

### News Feed Commands
| Command | Description | Permissions |
|:-------:|:------------|:------------|
| `/addfeed` | Add a new RSS feed to monitor | Admin |
| `/removefeed` | Remove an RSS feed | Admin |
| `/listfeeds` | List all configured RSS feeds | All Users |
| `/subscribechannel` | Subscribe the current channel to news categories | Admin |
| `/unsubscribechannel` | Unsubscribe the current channel from news updates | Admin |
| `/feedupdate` | Manually trigger an update for all feeds | Admin |
| `/getnews` | Fetch and display the latest news in the current channel | All Users |
| `/setfeedfrequency` | Set how often the bot checks for news (in hours) | Admin |
| `/feedstatus` | Show the status of news feeds and subscriptions | All Users |
| `/newsdigest` | Display the most recently generated AI news digest | All Users |

### User Feed Commands
| Command | Description | Permissions |
|:-------:|:------------|:------------|
| `/myfeeds list` | Show your saved personal RSS feeds | All Users |
| `/myfeeds add` | Add an RSS feed URL to your personal list | All Users |
| `/myfeeds remove` | Remove an RSS feed URL from your personal list | All Users |
| `/mynews` | Get a personalized news digest from your saved feeds | All Users |

### Thread Commands
Gideon leverages Discord's native thread system to organize conversations and create dedicated AI chat spaces.
| Command | Description |
|:-------:|:------------|
| `/thread new` | Create a new AI conversation thread |
| `/thread message` | Send a message to a specific thread |
| `/thread list` | View all active AI threads in the channel |
| `/thread delete` | Remove an AI thread and its history |
| `/thread rename` | Change the name of an AI thread |
| `/thread setmodel` | Set the AI model specifically for a thread |
| `/thread setsystem` | Set the system prompt specifically for a thread |

### Configuration Commands
| Command | Description | Permissions |
|:-------:|:------------|:------------|
| `/setmodel` | Change the default AI model for the server | Admin |
| `/model` | View or change the current model for the channel/thread | All Users |
| `/setsystem` | Customize the default AI personality (system prompt) | Admin |
| `/setchannelmodel` | Set the AI model for the current channel | Admin |
| `/setchannelsystem` | Set the system prompt for the current channel | Admin |
| `/setmemory` | Set the message history limit (max messages) | Admin |
| `/setwindow` | Set the time window for memory (in hours) | Admin |

### Image Commands
Gideon now uses a unified command for image generation with support for multiple backend providers.

| Command | Description | Permissions |
|:-------:|:------------|:------------|
| `/dream prompt:... [negative_prompt:...]` | Generate an image using the currently configured AI backend. | All Users |
| `/dream manage set_provider provider:<Choice>` | Set the active image generation provider (AI Horde, Cloudflare, OpenAI). | Admin |
| `/dream manage configure <provider> [options...]` | Configure default settings for a specific provider (e.g., model, size, steps). | Admin |
| `/dream manage view_config` | View the current active provider and configuration for all providers. | Admin |

### Adventure Commands
| Command | Description |
|:-------:|:------------|
| `/adventure new` | Start a new tabletop RPG adventure (Fantasy, Sci-Fi, Horror, Modern, or Custom) |
| `/adventure action` | Describe the action you want to take in the adventure |
| `/adventure roll` | Roll dice (e.g., 1d20, 2d6, 3d8+2) with narrated results |
| `/adventure status` | Check the status of the current adventure |
| `/adventure end` | End the current adventure with summary |
| `/adventure config_images` | Configure frequency of scene image generation (requires Cloudflare Worker) | Admin |

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
│   │   ├── chat_commands.py
│   │   ├── cloudflare_image_commands.py
│   │   ├── config_commands.py
│   │   ├── diagnostic_commands.py
│   │   ├── dungeon_master_commands.py
│   │   ├── image_commands.py
│   │   ├── mention_commands.py
│   │   ├── news_feeds_commands.py
│   │   ├── thread_commands.py
│   │   └── url_commands.py
│   └── utils/              # Utility classes and functions
│       ├── openrouter_client.py  # API client for text models
│       ├── ai_horde_client.py    # API client for AI Horde images
│       ├── cloudflare_client.py  # API client for Cloudflare images
│       ├── state_manager.py      # In-memory state management (uses database)
│       ├── database.py           # SQLite database interactions
│       ├── model_manager.py      # Handling model info
│       ├── permissions.py        # Permission checks
│       └── ...
├── .env.example            # Environment variables template
├── Dockerfile              # For building the Docker image
├── docker-compose.yml      # For running with Docker Compose
├── requirements.txt        # Python dependencies
├── README.md               # This file
├── documentation.md        # Detailed technical documentation
└── index.md                # GitHub Pages source file
```

## 🎲 Adventure System

The Adventure System transforms Gideon into an AI Game Master for immersive tabletop roleplaying experiences:

### Features
- **AI-Powered Storytelling**: Dynamic narratives adapt to player actions
- **Multiple Settings**: Fantasy worlds, sci-fi universes, horror scenarios, and more
- **Persistent State**: Adventure progress is saved between sessions
- **Integrated Dice System**: Roll dice with standard RPG notation (1d20, 2d6+3, etc.)
- **Campaign Management**: Check status and track adventure progress
- **Scene Visualization**: Automatically generate images of key moments (requires Cloudflare Worker)

### Using the Adventure System
1. Start an adventure with `/adventure new` (select a setting).
2. Interact with the adventure by sending messages in the channel or using `/adventure action [your action]`.
3. Roll dice when needed with `/adventure roll [dice notation]`.
4. Check your progress with `/adventure status`.
5. End your adventure when complete with `/adventure end`.
6. Adjust image generation frequency with `/adventure config_images [frequency]` (0 to disable, requires Admin perms and Cloudflare Worker setup).

Each adventure is channel-specific and uses the channel's configured AI model unless overridden.

## ❓ Troubleshooting

- **Connection Issues**: Run `/diagnostic` to check network connectivity to Discord and APIs.
- **Missing Commands**: Ensure the bot has `applications.commands` scope and necessary permissions (Send Messages, Read History, Embed Links, Manage Threads). Try re-inviting if needed. Use `/sync` (owner only) as a last resort.
- **Model Problems**: Some models require OpenRouter credits - check your account balance. Ensure the model ID used is correct.
- **State Issues**: Check logs for errors related to database operations. Ensure the `DATA_DIRECTORY` (Python) or Docker volume mount is writable and contains the `gideon.db` file (or the configured database file). The bot automatically saves state to the database periodically and on shutdown.
- **Image Generation Issues**: If `/imagine` fails, try smaller dimensions (e.g., 512x512), fewer steps, or a different model via `/hordemodels`. Check AI Horde status.
- **Cloudflare Worker Issues**: Use `/cftest` (Admin) to diagnose connectivity. Verify your `CLOUDFLARE_WORKER_URL` and `CLOUDFLARE_API_KEY` in `.env` are correct and your worker is running.
- **Adventure Issues**: If an adventure gets stuck or unresponsive, try ending it with `/adventure end` and starting a new one. Check logs for errors.
- **News Feed Issues**: Use `/feedstatus` to check configuration. Use `/feedupdate force_refresh:True` (Admin) to test fetching. Check logs for feed parsing or summarization errors.

## 📖 Documentation

For detailed technical information about Gideon's architecture, implementation details, and advanced setup instructions, please refer to the [Technical Documentation](documentation.md).

<div align="center">
Made with ❤️ by <a href="https://github.com/Emperor-Ovaltine">Emperor-Ovaltine</a>
</div>
