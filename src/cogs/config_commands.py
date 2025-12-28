"""
Legacy configuration commands - ALL COMMANDS MOVED TO NEW GROUPED STRUCTURE

This cog has been deprecated as part of the command consolidation refactor.
All commands have been moved to the following new command groups:

Global Settings (was /setmodel, /model, /setsystem, etc.):
  - Use /settings group commands instead
  - See settings_commands.py

Channel Settings (was /setchannelmodel, /channelmodel, etc.):
  - Use /channel group commands instead
  - See channel_commands.py

Admin Tools (was /setprunefrequency, /setsummaryretention, etc.):
  - Use /admin group commands instead
  - See admin_commands.py

This file is kept to avoid breaking imports but contains no active commands.
It can be safely removed once all references are updated.
"""
import discord
from discord.ext import commands

class ConfigCommands(commands.Cog, name="ConfigCommands"):
    """Legacy configuration commands - deprecated."""

    def __init__(self, bot):
        self.bot = bot
        self.state = bot.state_manager

def setup(bot):
    # Don't register the cog - no commands to add
    print("ConfigCommands cog skipped - all commands moved to grouped structure (/settings, /channel, /admin)")
