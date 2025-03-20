"""
Main entry point for the Gideon Discord bot.
Run with: python -m src
"""

import asyncio
from .bot import bot
from .config import DISCORD_TOKEN

if __name__ == "__main__":
    bot.run(DISCORD_TOKEN)
