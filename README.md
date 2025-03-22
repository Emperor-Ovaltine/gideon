# Gideon - Discord AI Assistant Bot

![Python 3.8+](https://img.shields.io/badge/python-3.8+-blue.svg)
![Py-Cord 2.4+](https://img.shields.io/badge/py--cord-2.4+-blue.svg)
![License MIT](https://img.shields.io/badge/license-MIT-green.svg)

> A powerful Discord bot that connects your server to advanced AI models through OpenRouter, enabling intelligent conversations, thread-based discussions, image analysis, and AI image generation.

## ✨ Features

### Intelligence
- **🤖 Multiple AI Models** - Access OpenAI, Anthropic Claude, Google Gemini, and more
- **🧠 Conversation Memory** - Bot remembers context for natural discussions
- **🌅 Image Analysis** - Upload and analyze images with vision-capable models
- **🎨 Image Generation** - Create AI-generated images with various Stable Diffusion models via AI Horde

### Organization
- **🧵 Conversation Threads** - Create dedicated topics with independent histories
- **🆔 Simple References** - Each thread gets a short, easy-to-reference ID
- **🔄 Auto-Responses** - Bot automatically answers all messages in AI threads

### Customization
- **🔄 Model Switching** - Change AI models on-the-fly with simple commands
- **🎭 Channel Personalities** - Set different system prompts per channel
- **🛠️ Admin Controls** - Comprehensive configuration options for server admins

## 🚀 Installation

### Prerequisites
- Python 3.8+
- Discord bot token with Message Content Intent enabled
- OpenRouter API key
- AI Horde API key (optional but recommended for better queue priority)

### Setup

```bash
# Clone and enter repository
git clone https://github.com/Emperor-Ovaltine/gideon
cd gideon

# Set up environment and dependencies
python3 -m venv venv
source venv/bin/activate  # On Windows: venv\Scripts\activate
pip install -r requirements.txt

# Configure bot
cp .env.example .env
# Edit .env with your Discord token, OpenRouter API key, and AI Horde API key

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
   - Permissions: Send Messages, Read Message History, Embed Links, Use Slash Commands

## 🤖 Commands

### Chat Commands
| Command | Description |
|---------|-------------|
| `/chat` | Talk with the AI (supports image attachments) |
| `/reset` | Clear conversation history |
| `/summarize` | Create a summary of the current conversation |
| `/memory` | Show conversation stats for this channel |

### Thread Management
| Command | Description |
|---------|-------------|
| `/thread new` | Create a conversation thread |
| `/thread message` | Send a message to a specific thread |
| `/thread list` | View all threads in this channel |
| `/thread delete` | Remove a thread |
| `/thread rename` | Change a thread's name |
| `/thread setmodel` | Set model for current thread |
| `/thread setsystem` | Set custom personality for thread |

### Image Generation
| Command | Description |
|---------|-------------|
| `/imagine` | Generate an image with AI Horde based on your text prompt |
| `/hordemodels` | List available image generation models on AI Horde |

### Configuration (Admin Only)
| Command | Description |
|---------|-------------|
| `/setmodel` | Change global AI model |
| `/model` | View/change current model |
| `/setsystem` | Customize AI personality |
| `/setchannelmodel` | Set model for current channel |
| `/setchannelsystem` | Set personality for current channel |
| `/setmemory` | Set message history limit |
| `/setwindow` | Set time window for memory |

### Diagnostics
| Command | Description |
|---------|-------------|
| `/diagnostic` | Test connections and configuration |
| `/visionmodels` | List models supporting image analysis |
| `/stateinfo` | Show memory usage statistics |

## 📚 Supported Models

### Text Models (via OpenRouter)
- **OpenAI**: GPT-4o, GPT-4o-mini
- **Anthropic**: Claude 3.7 Sonnet
- **Google**: Gemini 2.0 Flash
- **Perplexity**: Sonar Pro
- **And more!**

### Image Models (via AI Horde)
- **Stable Diffusion**: SD 2.1, SDXL, and more
- **Midjourney Diffusion**
- **Realistic Vision**
- **And many community models!**

Text models can be configured in the `.env` file using the `ALLOWED_MODELS` setting.

## 📁 Project Structure

```
gideon/
├── src/                    # Source code
│   ├── bot.py              # Bot initialization
│   ├── config.py           # Configuration
│   ├── cogs/               # Command modules
│   │   ├── chat_commands.py      # Basic chat functionality
│   │   ├── thread_commands.py    # Thread management
│   │   ├── image_commands.py     # Image generation
│   │   └── ...
│   └── utils/              # Utility functions
│       ├── openrouter_client.py  # API client for text models
│       ├── ai_horde_client.py    # API client for image generation
│       └── ...
├── .env.example            # Environment template
└── requirements.txt        # Dependencies
```

## ❓ Troubleshooting

- **Connection Issues**: Run `/diagnostic` to check network connectivity
- **Missing Commands**: Make sure the bot has proper permissions and try `/sync` (owner only)
- **Model Problems**: Some models require OpenRouter credits - check your account
- **State Issues**: Use `/savestate` to manually persist bot memory
- **Image Generation Issues**: If `/imagine` fails, try smaller dimensions (512×512), fewer steps, or a different model. Some models require more kudos on AI Horde.

## 📝 License

This project is licensed under the MIT License - see the [LICENSE](LICENSE) file for details.
