import os
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

# Get environment variables with error handling
DISCORD_TOKEN = os.getenv("DISCORD_TOKEN")
if not DISCORD_TOKEN:
    raise ValueError("DISCORD_TOKEN environment variable is not set. Please check your .env file.")

OPENROUTER_API_KEY = os.getenv("OPENROUTER_API_KEY")
if not OPENROUTER_API_KEY:
    raise ValueError("OPENROUTER_API_KEY environment variable is not set. Please check your .env file.")

SYSTEM_PROMPT = os.getenv("SYSTEM_PROMPT", "You are a helpful assistant in a Discord server. Provide concise, accurate responses.")

# Get allowed models
ALLOWED_MODELS = os.getenv('ALLOWED_MODELS', 'openai/gpt-4o-mini,openai/gpt-4o,anthropic/claude-3.7-sonnet,perplexity/sonar-pro,google/gemini-2.0-flash-exp:free')
ALLOWED_MODELS = [model.strip() for model in ALLOWED_MODELS.split(',')]

# Default model
DEFAULT_MODEL = os.getenv('DEFAULT_MODEL', 'google/gemini-2.0-flash-exp:free')
if DEFAULT_MODEL not in ALLOWED_MODELS:
    raise ValueError(f"DEFAULT_MODEL '{DEFAULT_MODEL}' is not in the list of ALLOWED_MODELS.")