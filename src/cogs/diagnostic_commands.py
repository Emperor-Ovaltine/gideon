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
    
    @discord.slash_command(
        name="debugstate", 
        description="Show detailed information about state file"
    )
    @commands.has_permissions(administrator=True)
    async def debug_state_command(self, ctx):
        await ctx.defer()
        
        from ..utils.persistence import StatePersistence
        persistence = StatePersistence()
        # Ensure file exists before trying to examine it
        persistence.ensure_state_file_exists()
        
        embed = discord.Embed(
            title="State File Debug",
            description=f"Examining state file at: `{persistence.state_file}`",
            color=discord.Color.blue()
        )
        
        # Check if file exists
        if not os.path.exists(persistence.state_file):
            embed.add_field(
                name="File Status",
                value="❌ State file does not exist",
                inline=False
            )
        else:
            file_size = os.path.getsize(persistence.state_file) / 1024  # KB
            mod_time = datetime.fromtimestamp(os.path.getmtime(persistence.state_file))
            
            embed.add_field(
                name="File Status",
                value=f"✅ File exists\n• Size: {file_size:.2f} KB\n• Modified: {mod_time.strftime('%Y-%m-%d %H:%M:%S')}",
                inline=False
            )
            
            # Try to load the file and check its structure
            try:
                with open(persistence.state_file, 'r') as f:
                    data = json.load(f)
                    
                embed.add_field(
                    name="Content Overview",
                    value=f"• Version: {data.get('version', 'Missing')}\n• Saved at: {data.get('saved_at', 'Missing')}\n• Keys: {', '.join(data.keys())[:1000]}",
                    inline=False
                )
                
                # Count items
                channels = len(data.get('channel_history', {}))
                threads = sum(len(threads) for channel, threads in data.get('threads', {}).items())
                
                embed.add_field(
                    name="Data Counts",
                    value=f"• Channels: {channels}\n• Threads: {threads}",
                    inline=False
                )
            except Exception as e:
                embed.add_field(
                    name="Error Reading File",
                    value=f"❌ Failed to parse file: {str(e)}",
                    inline=False
                )
        
        await ctx.respond(embed=embed)
    
    @discord.slash_command(
        name="statedebug", 
        description="Debug state manager memory contents"
    )
    async def state_debug_command(self, ctx):
        await ctx.defer()
        
        state = BotStateManager()
        
        embed = discord.Embed(
            title="State Manager Memory Debug",
            description=f"State manager instance ID: {id(state)}",
            color=discord.Color.blue()
        )
        
        # Count actual objects in memory
        channels = len(state.channel_history)
        channel_items = sum(len(history) for history in state.channel_history.values())
        threads = sum(len(threads) for threads in state.threads.values())
        
        embed.add_field(
            name="Memory Contents",
            value=f"• Channels: {channels} (with {channel_items} messages)\n• Thread mappings: {len(state.simple_id_mapping)}\n• Discord threads: {len(state.discord_threads)}\n• Channel models: {len(state.channel_models)}",
            inline=False
        )
        
        # Show a sample of actual data if it exists
        if state.channel_history:
            sample_channel = next(iter(state.channel_history))
            sample_data = f"Channel ID: {sample_channel}\nMessages: {len(state.channel_history[sample_channel])}"
            embed.add_field(
                name="Sample Channel Data",
                value=f"```\n{sample_data}\n```",
                inline=False
            )
        
        if state.threads:
            sample_channel = next(iter(state.threads))
            sample_thread = next(iter(state.threads[sample_channel]))
            thread_data = state.threads[sample_channel][sample_thread]
            sample_data = f"Thread: {thread_data.get('name', 'Unknown')}\nMessages: {len(thread_data.get('messages', []))}"
            embed.add_field(
                name="Sample Thread Data",
                value=f"```\n{sample_data}\n```",
                inline=False
            )
        
        await ctx.respond(embed=embed)

def setup(bot):
    bot.add_cog(DiagnosticCommands(bot))
