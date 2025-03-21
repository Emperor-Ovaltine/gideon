"""Diagnostic commands for troubleshooting the bot."""
import discord
import socket
import platform
import sys
from discord.ext import commands
from ..utils.state_manager import BotStateManager
from ..utils.openrouter_client import OpenRouterClient
from ..utils.model_sync import sync_models
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
        
        # Check if cogs have consistent model settings
        embed.add_field(
            name="Model Consistency Check",
            value="Checking model consistency across cogs...",
            inline=False
        )
        
        # Send initial report
        report_msg = await ctx.respond(embed=embed)
        
        # Check model consistency across cogs
        consistent = True
        inconsistencies = []
        
        for cog_name, cog in self.bot.cogs.items():
            if hasattr(cog, 'openrouter_client'):
                if cog.openrouter_client.model != global_model:
                    consistent = False
                    inconsistencies.append(f"- {cog_name}: `{cog.openrouter_client.model}`")
        
        # Update the embed with consistency results
        embed.remove_field(-1)  # Remove the placeholder field
        
        if consistent:
            embed.add_field(
                name="Model Consistency Check",
                value="✅ All cogs using the correct model",
                inline=False
            )
        else:
            embed.add_field(
                name="Model Consistency Check",
                value=f"❌ Model inconsistencies detected:\n{''.join(inconsistencies)}\nRunning sync to fix...",
                inline=False
            )
            
            # Fix inconsistencies
            sync_models(self.bot)
            
            embed.add_field(
                name="Model Sync",
                value="✅ Models synchronized across all cogs",
                inline=False
            )
        
        # Update the message with the complete report
        await report_msg.edit(embed=embed)
    
    @discord.slash_command(
        name="syncmodels",
        description="Synchronize model settings across all cogs"
    )
    @commands.has_permissions(administrator=True)
    async def sync_models_slash(self, ctx):
        await ctx.defer()
        
        # Run the synchronization
        sync_models(self.bot)
        
        # Get the global model
        global_model = self.state.get_global_model()
        
        # Create an embed for displaying results
        embed = discord.Embed(
            title="Model Synchronization",
            description=f"✅ All cogs now using model: `{global_model}`",
            color=discord.Color.green()
        )
        
        await ctx.respond(embed=embed)
    
    @discord.slash_command(
        name="visionmodels",
        description="List all models that support image analysis"
    )
    async def vision_models_slash(self, ctx):
        await ctx.defer()
        
        # Get the list of models that support vision
        vision_fragments = self.openrouter_client.vision_models
        vision_models = [model for model in ALLOWED_MODELS if 
                         any(fragment in model.lower() for fragment in vision_fragments)]
        
        # Create an embed
        embed = discord.Embed(
            title="Vision-Capable Models",
            description="These models can analyze images:",
            color=discord.Color.blue()
        )
        
        if vision_models:
            model_list = "\n".join([f"• `{model}`" for model in vision_models])
            embed.add_field(
                name="Available Vision Models",
                value=model_list,
                inline=False
            )
        else:
            embed.add_field(
                name="Available Vision Models",
                value="No vision-capable models found in your allowed models list.",
                inline=False
            )
            
        current_model = self.state.get_global_model()
        supports_vision = any(fragment in current_model.lower() for fragment in vision_fragments)
        
        embed.add_field(
            name="Current Model",
            value=f"`{current_model}` {'✅ supports' if supports_vision else '❌ does not support'} image analysis",
            inline=False
        )
        
        await ctx.respond(embed=embed)

def setup(bot):
    bot.add_cog(DiagnosticCommands(bot))
