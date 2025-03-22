"""Configuration for the bot."""
import os
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

# Bot token from Discord
DISCORD_TOKEN = os.getenv('DISCORD_TOKEN')

# OpenRouter API Key
OPENROUTER_API_KEY = os.getenv('OPENROUTER_API_KEY')

# Default system prompt
SYSTEM_PROMPT = os.getenv('SYSTEM_PROMPT', """You are a helpful AI assistant named Gideon. You provide clear, accurate, and thoughtful responses. You strive to be helpful, but you'll acknowledge when you don't know something. When users include their names in messages, address them by name in your responses.

You should adapt your tone to be conversational and friendly, while maintaining professionalism. You aim to be concise but thorough, providing sufficient context without unnecessary verbosity.

You are powered by the Openrouter API and have access to a variety of models to assist you in your responses. You can provide information, answer questions, and engage in conversation with users. You can also provide recommendations, summaries, and explanations on a wide range of topics.
""")

# Get allowed models from environment (comma-separated string)
allowed_models_str = os.getenv('ALLOWED_MODELS', "openai/gpt-4o-mini,openai/gpt-4o,anthropic/claude-3.7-sonnet,perplexity/sonar-pro,google/gemini-2.0-flash-exp:free")
ALLOWED_MODELS = [model.strip() for model in allowed_models_str.split(',') if model.strip()]

# Default model to use
DEFAULT_MODEL = os.getenv('DEFAULT_MODEL', 'google/gemini-2.0-flash-exp:free')

# Data storage configuration
DATA_DIRECTORY = os.getenv("DATA_DIRECTORY", os.path.join(os.path.dirname(os.path.dirname(__file__)), "data"))

# Ensure DATA_DIRECTORY is an absolute path
if not os.path.isabs(DATA_DIRECTORY):
    # If relative path is provided, make it absolute based on the script location
    DATA_DIRECTORY = os.path.abspath(os.path.join(os.path.dirname(os.path.dirname(__file__)), DATA_DIRECTORY))

# AI Horde Configuration
AI_HORDE_API_KEY = os.getenv('AI_HORDE_API_KEY', '')