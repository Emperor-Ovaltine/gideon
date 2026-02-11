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
allowed_models_str = os.getenv('ALLOWED_MODELS', "openai:gpt-4o-mini,openai:gpt-4o,anthropic:claude-3.7-sonnet,perplexity:sonar-pro,google:gemini-2.0-flash-exp")
ALLOWED_MODELS = [model.strip().replace('/', ':') for model in allowed_models_str.split(',') if model.strip()]

# Default model to use (must include provider in provider/model_name format)
DEFAULT_MODEL = os.getenv('DEFAULT_MODEL', 'google/gemini-2.0-flash-exp') # Use slash separator

# Data storage configuration
DATA_DIRECTORY = os.getenv("DATA_DIRECTORY", os.path.join(os.path.dirname(os.path.dirname(__file__)), "data"))

# Ensure DATA_DIRECTORY is an absolute path
if not os.path.isabs(DATA_DIRECTORY):
    # If relative path is provided, make it absolute based on the script location
    DATA_DIRECTORY = os.path.abspath(os.path.join(os.path.dirname(os.path.dirname(__file__)), DATA_DIRECTORY))

# AI Horde Configuration
AI_HORDE_API_KEY = os.getenv('AI_HORDE_API_KEY', '')

# Cloudflare Worker Configuration
CLOUDFLARE_WORKER_URL = os.getenv('CLOUDFLARE_WORKER_URL', 'https://your-worker-url.workers.dev/')
CLOUDFLARE_API_KEY = os.getenv('CLOUDFLARE_API_KEY', '')

# OpenAI Configuration
OPENAI_API_KEY = os.getenv('OPENAI_API_KEY', '')

# ComfyUI Configuration
# URL of your ComfyUI server (local or remote)
# Examples: http://127.0.0.1:8188 or http://your-server.com:8188
COMFYUI_URL = os.getenv('COMFYUI_URL', '')

# Intent Discovery - Enable AI-powered intent detection for @mentions (opt-in feature)
# When enabled, adds AI call on every mention to detect intents (reminders, etc.)
# Default: FALSE (users must opt-in due to additional API calls)
INTENT_DISCOVERY = os.getenv('INTENT_DISCOVERY', 'FALSE').upper() == 'TRUE'

# Intent Detection Model (fast, lightweight model for intent classification)
# Only used when INTENT_DISCOVERY=TRUE
# Format: "provider/model_name" - should be a fast, cheap model
INTENT_DETECTION_MODEL = os.getenv('INTENT_DETECTION_MODEL', 'openai/gpt-4o-mini')

# Intent Confidence Threshold (minimum confidence to execute intent handlers)
# Only used when INTENT_DISCOVERY=TRUE
# Range: 0.0-1.0, Default: 0.7
# Lower = more aggressive (more false positives), Higher = more conservative (more false negatives)
try:
    INTENT_CONFIDENCE_THRESHOLD = float(os.getenv('INTENT_CONFIDENCE_THRESHOLD', '0.7'))
    # Clamp to valid range
    if INTENT_CONFIDENCE_THRESHOLD < 0.0:
        INTENT_CONFIDENCE_THRESHOLD = 0.0
    elif INTENT_CONFIDENCE_THRESHOLD > 1.0:
        INTENT_CONFIDENCE_THRESHOLD = 1.0
except ValueError:
    INTENT_CONFIDENCE_THRESHOLD = 0.7

# Dashboard Configuration
DASHBOARD_ENABLED = os.getenv('DASHBOARD_ENABLED', 'FALSE').upper() == 'TRUE'
DASHBOARD_PORT = int(os.getenv('DASHBOARD_PORT', '8080'))
DASHBOARD_SECRET = os.getenv('DASHBOARD_SECRET', '')

# Encryption Master Key for API key storage (required for dashboard key management)
ENCRYPTION_MASTER_KEY = os.getenv('ENCRYPTION_MASTER_KEY', '')