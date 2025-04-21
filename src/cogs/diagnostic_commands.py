"""Diagnostic commands for troubleshooting the bot."""
import discord
import socket
import platform
import sys
import os
import json
from datetime import datetime
from discord.ext import commands
from ..utils.state_manager import BotStateManager
from ..utils.openrouter_client import OpenRouterClient
# Removed: from ..utils.model_sync import sync_models
from ..config import OPENROUTER_API_KEY, SYSTEM_PROMPT, ALLOWED_MODELS, DEFAULT_MODEL

class DiagnosticCommands(commands.Cog):
    """Diagnostic and troubleshooting tools."""
    
    def __init__(self, bot):
        self.bot = bot
        self.state = BotStateManager()
        self.openrouter_client = OpenRouterClient(OPENROUTER_API_KEY, SYSTEM_PROMPT, DEFAULT_MODEL)
    
    @discord.slash_command(
        name="diagnostic",
        description="Run diagnostic tests to troubleshoot connection issues"
    )
    async def diagnostic_slash(self, ctx):
        await ctx.defer()
        
        # Create an embed for displaying diagnostics
        embed = discord.Embed(
            title="Gideon Diagnostic Report",
            description="Checking system status and connections...",
            color=discord.Color.blue()
        )
        
        # Check Python version
        embed.add_field(
            name="Python Version",
            value=f"Python {platform.python_version()}",
            inline=False
        )
        
        # Check internet connectivity
        try:
            socket.create_connection(("openrouter.ai", 443), timeout=5)
            embed.add_field(
                name="Internet Connectivity",
                value="✅ Connected to the internet",
                inline=False
            )
        except (socket.timeout, socket.error):
            embed.add_field(
                name="Internet Connectivity",
                value="❌ Failed to connect to the internet",
                inline=False
            )
        
        # Check API connectivity
        dns_resolved = await self.openrouter_client.verify_dns_resolution("openrouter.ai")
        if dns_resolved:
            embed.add_field(
                name="DNS Resolution",
                value="✅ DNS resolving correctly for openrouter.ai",
                inline=False
            )
        else:
            embed.add_field(
                name="DNS Resolution",
                value="❌ Failed to resolve DNS for openrouter.ai",
                inline=False
            )
        
        # Show active model
        global_model = self.state.get_global_model()
        embed.add_field(
            name="Current Global Model",
            value=f"`{global_model}`",
            inline=False
        )
        
        # Show channel-specific model if set
        channel_id = str(ctx.channel.id)
        if channel_id in self.state.channel_models:
            embed.add_field(
                name="Channel-Specific Model",
                value=f"`{self.state.channel_models[channel_id]}`",
                inline=False
            )

        # Removed model consistency check as it's no longer relevant
        # with the new provider switching logic.

        # Send the report
        await ctx.respond(embed=embed) # Corrected indentation

    # Removed /syncmodels command as it's obsolete
   # @discord.slash_command(
   #     name="syncmodels",
   #     description="Synchronize model settings across all cogs"
   # )
   # @commands.has_permissions(administrator=True)
   # async def sync_models_slash(self, ctx):
   #     await ctx.defer()
   #     # Run the synchronization
   #     # sync_models(self.bot) # Removed call
   #     # Get the global model
   #     global_model = self.state.get_global_model()
   #     # Create an embed for displaying results
   #     embed = discord.Embed(
   #         title="Model Synchronization",
   #         description=f"✅ Model sync is no longer needed. Provider selection is handled dynamically.",
   #         color=discord.Color.orange()
   #     )
   #     await ctx.respond(embed=embed)

    @discord.slash_command( # Corrected indentation
        name="visionmodels",
        description="List all models that support image analysis"
    )
    async def vision_models_slash(self, ctx): # Corrected indentation
        await ctx.defer()
        
        # Directly get the list of vision model IDs
        vision_models = await self.bot.model_manager.get_vision_models()
        
        embed = discord.Embed(
            title="Vision-Capable Models",
            description="These models, identified by OpenRouter, can analyze images:",
            color=discord.Color.blue()
        )

        if vision_models:
            # Helper function to add fields, respecting Discord limits
            def add_model_fields(embed, models):
                current_field_value = ""
                field_count = 0
                max_field_len = 1024 # Discord embed field value limit
                
                for i, model in enumerate(models):
                    model_line = f"• `{model}`\n"
                    
                    # Check if adding the next model exceeds the limit
                    if len(current_field_value) + len(model_line) > max_field_len:
                        # Add the current field
                        field_name = f"Available Vision Models ({field_count + 1})" if field_count > 0 else "Available Vision Models"
                        embed.add_field(name=field_name, value=current_field_value, inline=False)
                        current_field_value = model_line # Start new field
                        field_count += 1
                    else:
                        current_field_value += model_line
                        
                # Add the last remaining field if it has content
                if current_field_value:
                    field_name = f"Available Vision Models ({field_count + 1})" if field_count > 0 else "Available Vision Models"
                    embed.add_field(name=field_name, value=current_field_value, inline=False)

            add_model_fields(embed, vision_models)
        else:
            embed.add_field(
                name="Available Vision Models",
                value="No vision-capable models found.",
                inline=False
            )
            
        # Check current model (using the accurate list now)
        current_model = self.state.get_global_model()
        supports_vision = current_model in vision_models
        embed.add_field(
            name="Current Model",
            value=f"`{current_model}` {'✅ supports' if supports_vision else '❌ does not support'} image analysis",
            inline=False
        )
        await ctx.respond(embed=embed)
    

def setup(bot):
    bot.add_cog(DiagnosticCommands(bot))
