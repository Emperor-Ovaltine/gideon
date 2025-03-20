# Gideon - Discord AI Assistant Bot

![Python 3.8+](https://img.shields.io/badge/python-3.8+-blue.svg)
![Py-Cord 2.4+](https://img.shields.io/badge/py--cord-2.4+-blue.svg)
![License MIT](https://img.shields.io/badge/license-MIT-green.svg)

> A powerful Discord bot that integrates with OpenRouter to provide intelligent AI conversations and assistance in your Discord server.

## ✨ Features

- **🤖 AI-Powered Chat** - Access multiple LLMs through OpenRouter including GPT-4o, Claude 3.7, and Gemini
- **🧠 Conversation Memory** - Maintains context across multiple interactions
- **🧵 Thread Support** - Create dedicated conversation threads with independent histories
- **🔄 Multi-Model Switching** - Seamlessly switch between different AI models (OpenAI, Anthropic, Google, etc.)
- **📊 Vision Capabilities** - Analyze and respond to images with compatible models
- **🛠️ Admin Controls** - Customize settings with administrator-only commands
- **📱 Easy Setup** - Simple configuration using environment variables

## 🚀 Quick Start

```bash
# Clone the repository
git clone https://github.com/Emperor-Ovaltine/gideon
cd gideon

# Set up virtual environment and install dependencies
python -m venv venv
source venv/bin/activate  # On Windows: venv\Scripts\activate
pip install -r requirements.txt

# Configure environment
cp .env.example .env
# Edit .env with your Discord token and OpenRouter API key

# Launch the bot
python -m src
```

## 📋 Requirements

- Python 3.8 or higher
- Discord bot token with Message Content Intent enabled
- OpenRouter API key

## 💻 Detailed Installation

### 1. Setting Up Your Environment

```bash
# Create a virtual environment
python -m venv venv

# Activate the environment
# On macOS/Linux:
source venv/bin/activate
# On Windows:
venv\Scripts\activate

# Install dependencies
pip install -r requirements.txt
```

### 2. Configuring the Bot

```bash
# Copy the example configuration
cp .env.example .env

# Edit the configuration file with your credentials
# DISCORD_TOKEN: Your Discord bot token
# OPENROUTER_API_KEY: Your OpenRouter API key
# SYSTEM_PROMPT: Customize the bot's personality
```

### 3. Discord Developer Portal Setup

1. Create a new application at [Discord Developer Portal](https://discord.com/developers/applications)
2. Navigate to the "Bot" tab and:
   - Enable "Message Content Intent"
   - Copy your bot token to the `.env` file
3. Generate an invite URL in "OAuth2 > URL Generator":
   - Required scopes: `bot`, `applications.commands`
   - Required permissions:
     - Send Messages
     - Read Message History
     - Embed Links
     - Use Slash Commands

### 4. Starting Gideon

```bash
# With your virtual environment activated:
python -m src
```

## 🤖 Command Reference

### Core Chat Commands

| Command | Description | Example |
|---------|-------------|---------|
| `/chat` | Chat with the AI | `/chat message:Explain quantum computing` |
| `/reset` | Clear conversation history | `/reset` |
| `/summarize` | Generate conversation summary | `/summarize` |
| `/memory` | Show message history stats | `/memory` |

### Thread Management

| Command | Description | Example |
|---------|-------------|---------|
| `/thread new` | Create a conversation thread | `/thread new name:Physics Discussion` |
| `/thread message` | Chat in a specific thread | `/thread message id:123 message:Tell me more` |
| `/thread list` | Show available threads | `/thread list` |
| `/thread delete` | Delete a thread | `/thread delete id:123` |

### Model & System Configuration (Admin Only)

| Command | Description | Example |
|---------|-------------|---------|
| `/setmodel` | Change global AI model | `/setmodel model_name:openai/gpt-4o` |
| `/setsystem` | Customize AI personality | `/setsystem new_prompt:You are Gideon...` |
| `/setchannelmodel` | Set channel-specific model | `/setchannelmodel model_name:anthropic/claude-3.7-sonnet` |
| `/setmemory` | Set history message limit | `/setmemory size:50` |
| `/setwindow` | Configure memory time window | `/setwindow hours:24` |

### Diagnostic Tools

| Command | Description | Example |
|---------|-------------|---------|
| `/diagnostic` | Check network connectivity | `/diagnostic` |
| `/model` | Show current AI model | `/model` |
| `/channelmodel` | Show channel's AI model | `/channelmodel` |
| `/visionmodels` | List models supporting images | `/visionmodels` |
| `/showsystem` | Display current system prompt | `/showsystem` |

## 📚 Supported Models

Gideon supports various AI models through OpenRouter, including:

- OpenAI: `openai/gpt-4o-mini`, `openai/gpt-4o`
- Anthropic: `anthropic/claude-3.7-sonnet`
- Google: `google/gemini-2.0-flash-exp:free`
- Microsoft: `microsoft/wizardlm-2-8x22b`
- Perplexity: `perplexity/sonar-pro`

## 📁 Project Structure

```
gideon/
├── src/                    # Main source code
│   ├── __init__.py         # Package initializer 
│   ├── __main__.py         # Entry point
│   ├── bot.py              # Bot initialization and events
│   ├── config.py           # Configuration handling
│   ├── cogs/               # Bot command modules
│   │   └── llm_chat.py     # Chat functionality
│   └── utils/              # Utility functions
│       ├── openrouter_client.py  # OpenRouter API client
│       └── permissions.py  # Discord permissions handling
├── .env.example            # Example environment variables
├── LICENSE                 # MIT License
├── README.md               # This file
└── requirements.txt        # Dependencies
```

## ❓ FAQ & Troubleshooting

### Connection Issues

**Q: Why can't my bot connect to OpenRouter?**
- Run the `/diagnostic` command to check network connectivity
- Verify your OpenRouter API key is valid and has available credits
- Check if your network blocks API requests

**Q: The bot is online but doesn't respond to commands**
- Ensure you've enabled the Message Content Intent in Discord Developer Portal
- Check if the bot has the correct permissions in your server
- Try the `/sync` command (bot owner only) to refresh slash commands

**Q: Some AI models aren't working**
- Certain models may require credits on your OpenRouter account
- Check if the model is listed in your ALLOWED_MODELS in the .env file
- Run `/visionmodels` to check which models support image processing

## 📝 License

This project is licensed under the MIT License - see the [LICENSE](LICENSE) file for details.
