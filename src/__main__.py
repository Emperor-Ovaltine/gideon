"""
Main entry point for the Gideon Discord bot.
Run with: python -m src
"""

from .bot import bot
from .config import DISCORD_TOKEN

if __name__ == "__main__":
    # No longer start the auto-save task here; it's started in on_ready
    bot.run(DISCORD_TOKEN)
