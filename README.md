# Gideon - Discord OpenRouter AI Bot

Gideon is a feature-rich Discord bot that integrates with OpenRouter AI to provide intelligent conversations and assistance for your Discord server.

## Features

- Powerful AI-powered conversations using OpenRouter's language models
- Conversation memory that allows Gideon to remember previous interactions
- Easy setup and configuration with environment variables
- Modular design with Discord.py cogs for maintainability
- Customizable system prompt to control AI personality and behavior
- Network diagnostics for quick troubleshooting of connection issues
- Role-based permissions for administrative commands
- Support for both traditional prefix commands and Discord slash commands

## Requirements

- Python 3.8 or higher (recommended)
- Discord Bot Token with Message Content Intent enabled
- OpenRouter API Key

## Setup Instructions

1. **Create and activate a virtual environment**:
   ```bash
   # Create a virtual environment
   python3 -m venv venv
   
   # Activate it (Linux/Mac)
   source venv/bin/activate
   
   # Or on Windows
   venv\Scripts\activate
   ```

2. **Install dependencies**:
   ```bash
   pip install -r requirements.txt
   ```

3. **Configure environment variables**:
   ```bash
   # Copy the example file
   cp .env.example .env
   
   # Edit the .env file with your tokens
   nano .env  # or use any text editor
   ```

## Discord Bot Setup

1. Go to [Discord Developer Portal](https://discord.com/developers/applications)
2. Create a "New Application" and name it "Gideon"
3. Navigate to the "Bot" tab and click "Add Bot"
4. Under "Privileged Gateway Intents", enable "Message Content Intent"
5. Copy the bot token and add it to your .env file

## Invite Gideon to Your Server

1. In the Discord Developer Portal, go to the "OAuth2" tab
2. In "URL Generator", select the "bot" and "applications.commands" scopes
3. Select these bot permissions:
   - Send Messages
   - Read Message History
   - Embed Links
   - Use Slash Commands
4. Copy the generated URL and open it in your browser to invite Gideon

## Running Gideon

```bash
# Activate the virtual environment (if not already activated)
source venv/bin/activate  # Linux/Mac
# OR
venv\Scripts\activate  # Windows

# Start the bot
python -m src
```

## Commands

Gideon supports both traditional prefix commands (starting with `!`) and Discord slash commands. Slash commands provide auto-completion and parameter hints.

### Chat Commands

- **Chat with Gideon**:
  ```
  !chat [your message]
  ```
  or use the slash command `/chat message:[your message]`
  
  Example: `!chat What's the best programming language for beginners?`
  
  Note: This command has a 5-second cooldown per user to prevent spam.

### Memory Management

- **Reset conversation history**:
  ```
  !reset
  ```
  or `/reset`
  
  Clears the conversation history for the current channel.

- **Check channel memory usage**:
  ```
  !channelmemory
  ```
  or `/channelmemory`
  
  Shows how many messages are currently stored for the current channel.

- **Set memory size** (admin only):
  ```
  !setmemory [number]
  ```
  or `/setmemory size:[number]`
  
  Sets the maximum number of messages to remember per channel (between 5-100).
  
- **Set time window** (admin only):
  ```
  !setwindow [hours]
  ```
  or `/setwindow hours:[hours]`
  
  Sets the time window for message history in hours (between 1-96).

- **Summarize conversation**:
  ```
  !summarize
  ```
  or `/summarize`
  
  Generates a concise summary of the current conversation in bullet points.

### Model Management

- **Set AI model** (admin only):
  ```
  !setmodel [model_name]
  ```
  or `/setmodel model_name:[model_name]`
  
  Changes the AI model used by OpenRouter. Available models are defined in your `.env` file and typically include:
  `openai/gpt-4o-mini`, `openai/gpt-4o`, `anthropic/claude-3.7-sonnet`, `perplexity/sonar-pro`, `google/gemini-2.0-flash-exp:free`, `microsoft/wizardlm-2-8x22b`

- **Show current model** (admin only):
  ```
  !model
  ```
  or `/model`
  
  Shows which AI model is currently in use.

### System Configuration

- **View current system prompt**:
  ```
  !showsystem
  ```
  or `/showsystem`
  
  Displays the current system prompt being used for the AI.

- **Change system prompt** (admin only):
  ```
  !setsystem [new system prompt]
  ```
  or `/setsystem new_prompt:[new system prompt]`
  
  Example: `!setsystem You are Gideon, a helpful programming assistant.`

### Diagnostics

- **Run network diagnostics**:
  ```
  !diagnostic
  ```
  or `/diagnostic`
  
  Checks internet connection and DNS resolution to the OpenRouter API.

- **Check legacy memory usage**:
  ```
  !memory
  ```
  
  Shows deprecation message for the legacy user-based memory system.

## Troubleshooting

### Connection Issues

If Gideon can't connect to OpenRouter:

1. Check your internet connection
2. Run `!diagnostic` or `/diagnostic` to check DNS resolution
3. Verify your OpenRouter API key is correct in the .env file
4. Try using alternative DNS servers if OpenRouter domains can't be resolved

### Authentication Errors

1. Ensure your Discord token is correct in the .env file
2. Verify that your OpenRouter API key is valid and has sufficient credits

### Bot Not Responding to Messages

1. Verify that Message Content Intent is enabled in the Discord Developer Portal
2. Make sure the bot has the necessary permissions in your Discord server
3. If slash commands aren't appearing, try running the `!sync` command (bot owner only)

## License

This project is licensed under the MIT License.