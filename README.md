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
* **Dual Command Systems** - Supports both prefix (!) and slash (/) commands  

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
Gideon supports both `!` prefix commands and `/` slash commands with auto-completion.

### Core Interactions
| Command | Description | Example |
|---------|-------------|---------|
| `!chat <message>`<br>`/chat message:<message>` | Start/resume conversation | `!chat Explain quantum computing` |
| `!reset`<br>`/reset` | Clear channel conversation history | - |
| `!summarize`<br>`/summarize` | Generate conversation summary | - |

### Configuration (Admin Only)
| Command | Parameters | Functionality |
|---------|------------|---------------|
| `!setmemory <5-100>` | Integer | Set message history limit |
| `!setwindow <1-96>` | Hours | Configure memory time window |
| `!setmodel <name>` | [Supported Models](#models) | Change AI model |
| `!setsystem <prompt>` | String | Customize AI personality |

### Diagnostics
```bash
!diagnostic   # Network connectivity check
!channelmemory  # Current message history count
```

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
- Use `!sync` to refresh slash commands (owner only)
