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