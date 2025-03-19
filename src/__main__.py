"""
Main entry point for the Gideon Discord bot.
Run with: python -m src
"""

from .bot import bot
from .config import DISCORD_TOKEN  # Import the token

if __name__ == "__main__":
    bot.run(DISCORD_TOKEN)  # Pass the token to run()
