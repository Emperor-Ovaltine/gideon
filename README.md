# Gideon - Discord OpenRouter AI Bot  
Gideon is a feature-rich Discord bot that integrates with OpenRouter AI to provide intelligent conversations and assistance for your Discord server.

## Features
* **AI-Powered Conversations** - Leverages OpenRouter's language models for dynamic interactions  
* **Conversation Memory** - Maintains context across multiple interactions  
* **Easy Configuration** - Simple setup using environment variables  
* **Modular Architecture** - Built with Discord.py cogs for easy maintenance  
* **Customizable Personality** - Adjustable system prompt for tailored AI behavior  
* **Network Diagnostics** - Built-in troubleshooting tools for connection issues  
* **Role-Based Access** - Administrative commands with permission controls  
* **Thread Support** - Create dedicated conversation threads with independent histories
* **Multi-Model Access** - Switch between different LLMs for different use cases

## Requirements
* Python 3.8+ (recommended)
* Discord bot token with Message Content Intent enabled
* OpenRouter API key

## Setup Instructions
1. **Create and activate a virtual environment**  
   ```bash
   # Create environment
   python3 -m venv venv

   # Activate (Linux/Mac)
   source venv/bin/activate

   # Activate (Windows)
   venv\Scripts\activate
   ```

2. **Install dependencies**  
   ```bash
   pip install -r requirements.txt
   ```

3. **Configure environment variables**  
   ```bash
   # Copy example file
   cp .env.example .env  # Use 'copy' on Windows

   # Edit configuration
   nano .env  # Or your preferred text editor
   ```

## Discord Bot Configuration
1. Create a new application in the [Discord Developer Portal](https://discord.com/developers/applications)
2. Under the **Bot** tab:
  - Enable "Message Content Intent"
  - Copy your bot token to `.env`
3. Generate invite URL in **OAuth2 > URL Generator**:
  - Scopes: `bot` and `applications.commands`
  - Permissions:
    - Send Messages
    - Read Message History
    - Embed Links
    - Use Slash Commands

## Launching the Bot
```bash
# Activate virtual environment
source venv/bin/activate  # Linux/Mac
venv\Scripts\activate    # Windows

# Start Gideon
python -m src
```

## Command Reference
Gideon uses slash commands with auto-completion.

### Core Commands
| Command | Description | Example |
|---------|-------------|---------|
| `/chat message:<message> [image:<file>]` | Chat with the AI | `/chat message:Explain quantum computing` |
| `/reset` | Clear channel conversation history | `/reset` |
| `/summarize` | Generate conversation summary | `/summarize` |
| `/memory` | Show message history stats | `/memory` |

### Thread Commands
| Command | Description | Example |
|---------|-------------|---------|
| `/thread create name:<name>` | Create a conversation thread | `/thread create name:Physics Discussion` |
| `/thread message id:<id> message:<text>` | Chat in a specific thread | `/thread message id:123 message:Tell me more` |
| `/thread list` | Show available threads | `/thread list` |
| `/thread delete id:<id>` | Delete a thread | `/thread delete id:123` |

### Configuration (Admin Only)
| Command | Description | Example |
|---------|-------------|---------|
| `/setmemory size:<5-100>` | Set message history limit | `/setmemory size:50` |
| `/setwindow hours:<1-96>` | Configure memory time window | `/setwindow hours:24` |
| `/setmodel model_name:<name>` | Change global AI model | `/setmodel model_name:openai/gpt-4o` |
| `/setsystem new_prompt:<prompt>` | Customize AI personality | `/setsystem new_prompt:You are a helpful assistant...` |
| `/setchannelmodel model_name:<name>` | Set channel-specific model | `/setchannelmodel model_name:anthropic/claude-3.7-sonnet` |

### Diagnostic Commands
| Command | Description | Example |
|---------|-------------|---------|
| `/diagnostic` | Check network connectivity | `/diagnostic` |
| `/model` | Show current AI model | `/model` |
| `/channelmodel` | Show channel's AI model | `/channelmodel` |
| `/visionmodels` | List models supporting images | `/visionmodels` |
| `/showsystem` | Display current system prompt | `/showsystem` |

## Supported Models <a name="models"></a>
- `openai/gpt-4o-mini`
- `anthropic/claude-3.7-sonnet`  
- `google/gemini-2.0-flash-exp:free`  
- `microsoft/wizardlm-2-8x22b`

## Troubleshooting
**Connection Issues**  
1. Verify internet connectivity
2. Run `/diagnostic` for network checks
3. Confirm OpenRouter API key validity

**Authentication Problems**  
- Double-check Discord token in `.env`
- Ensure OpenRouter account has sufficient credits

**Unresponsive Bot**  
- Confirm Message Content Intent activation
- Check server permission settings
- Use `/sync` to refresh slash commands (owner only)
