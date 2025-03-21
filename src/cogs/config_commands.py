"""Configuration commands for the bot."""
import discord
from discord.ext import commands
from ..utils.state_manager import BotStateManager
from ..utils.openrouter_client import OpenRouterClient
from ..config import OPENROUTER_API_KEY, SYSTEM_PROMPT, ALLOWED_MODELS, DEFAULT_MODEL
from ..utils.model_sync import sync_models

class ConfigCommands(commands.Cog):
    """Commands for bot configuration."""
    
    def __init__(self, bot):
        self.bot = bot
        self.state = BotStateManager()
        self.openrouter_client = OpenRouterClient(OPENROUTER_API_KEY, SYSTEM_PROMPT, DEFAULT_MODEL)
    
    @discord.slash_command(
        name="setmodel",
        description="Set the AI model to use from OpenRouter"
    )
    @commands.has_permissions(administrator=True)
    async def set_model_slash(self, ctx, 
                             model_name: discord.Option(
                                 str,
                                 "Select the AI model to use",
                                 choices=ALLOWED_MODELS
                             )):
        # Update both the client and the state manager
        self.openrouter_client.model = model_name
        self.state.set_global_model(model_name)
        
        # Sync the model change across all cogs
        sync_models(self.bot)
        
        await ctx.respond(f"Model set to {model_name}")
    
    @discord.slash_command(
        name="model",
        description="Show the current AI model being used or change to a new model"
    )
    async def show_model_slash(self, ctx, 
                              new_model: discord.Option(
                                  str,
                                  "Select a new model to use (optional)",
                                  choices=ALLOWED_MODELS,
                                  required=False
                              )):
        await ctx.defer()
        
        if new_model:
            # User provided a new model, so change to it (same as setmodel)
            if ctx.author.guild_permissions.administrator:
                # Update both the client and the state manager
                self.openrouter_client.model = new_model
                self.state.set_global_model(new_model)
                
                # Sync the model change across all cogs
                sync_models(self.bot)
                
                await ctx.respond(f"✅ Model changed to: `{new_model}`")
            else:
                await ctx.respond("⚠️ Only administrators can change the model. Use `/setmodel` if you have admin permissions.")
        else:
            # Just show current model info and instructions
            current_model = self.state.get_global_model()
            
            # Check if the model is empty and provide a fallback
            if not current_model:
                current_model = DEFAULT_MODEL
                # Update the state with the default model to fix this for future calls
                self.state.set_global_model(current_model)
                
            models_list = "\n".join([f"• `{model}`" for model in ALLOWED_MODELS[:5]])  # Show first 5 models
            if len(ALLOWED_MODELS) > 5:
                models_list += f"\n• ... and {len(ALLOWED_MODELS) - 5} more models"
                
            await ctx.respond(f"**Current model**: `{current_model}`\n\n"
                             f"To change models, use `/setmodel` (admin only) or add the 'new_model' parameter to this command.\n\n"
                             f"**Available models include**:\n{models_list}")
        
    @discord.slash_command(
        name="setsystem",
        description="Set a new system prompt (admin only)"
    )
    @commands.has_permissions(administrator=True)
    async def set_system_slash(self, ctx, new_prompt: str):
        self.openrouter_client.system_prompt = new_prompt
        await ctx.respond(f"System prompt updated! New prompt: \n```\n{new_prompt}\n```")
        
    @discord.slash_command(
        name="setmemory",
        description="Set the maximum number of messages to remember per channel"
    )
    @commands.has_permissions(administrator=True)
    async def set_memory_slash(self, ctx, size: int):
        self.state.max_channel_history = size
        await ctx.respond(f"Channel memory size set to {size} messages.")
        
    @discord.slash_command(
        name="setwindow",
        description="Set the time window for message history in hours"
    )
    @commands.has_permissions(administrator=True)
    async def set_window_slash(self, ctx, hours: int):
        if hours < 1 or hours > 96:
            await ctx.respond("Time window must be between 1 and 96 hours.")
            return
            
        self.state.time_window_hours = hours
        await ctx.respond(f"Channel memory time window set to {hours} hours.")
    
    @discord.slash_command(
        name="setchannelmodel",
        description="Set the AI model to use for this specific channel"
    )
    @commands.has_permissions(administrator=True)
    async def set_channel_model_slash(self, ctx, 
                                     model_name: discord.Option(
                                         str,
                                         "Select the AI model to use for this channel",
                                         choices=ALLOWED_MODELS
                                     )):
        channel_id = str(ctx.channel.id)
        self.state.channel_models[channel_id] = model_name
        await ctx.respond(f"Model for this channel set to `{model_name}`")

    @discord.slash_command(
        name="channelmodel",
        description="Show the current AI model being used for this channel"
    )
    async def show_channel_model_slash(self, ctx):
        await ctx.defer()
        channel_id = str(ctx.channel.id)
        if channel_id in self.state.channel_models:
            await ctx.respond(f"Current model for this channel: `{self.state.channel_models[channel_id]}`")
        else:
            await ctx.respond(f"This channel uses the default model: `{self.state.get_global_model()}`")

    @discord.slash_command(
        name="resetchannelmodel",
        description="Reset this channel to use the default model"
    )
    @commands.has_permissions(administrator=True)
    async def reset_channel_model_slash(self, ctx):
        channel_id = str(ctx.channel.id)
        if channel_id in self.state.channel_models:
            del self.state.channel_models[channel_id]
            await ctx.respond(f"This channel will now use the default model: `{self.openrouter_client.model}`")
        else:
            await ctx.respond(f"This channel is already using the default model: `{self.openrouter_client.model}`")

    @discord.slash_command(
        name="setchannelsystem",
        description="Set a custom system prompt for this channel"
    )
    @commands.has_permissions(administrator=True)
    async def set_channel_system_slash(self, ctx, new_prompt: str):
        channel_id = str(ctx.channel.id)
        self.state.set_channel_system_prompt(channel_id, new_prompt)
        # Split system prompt into chunks if very long
        max_length = 1950
        chunks = [new_prompt[i:i+max_length] for i in range(0, len(new_prompt), max_length)]
        
        await ctx.respond(f"System prompt for this channel updated! New prompt: \n```\n{chunks[0]}\n```")
        for chunk in chunks[1:]:
            await ctx.followup.send(f"```\n{chunk}\n```")

    @discord.slash_command(
        name="channelsystem",
        description="Show the current system prompt for this channel"
    )
    async def show_channel_system_slash(self, ctx):
        await ctx.defer()
        channel_id = str(ctx.channel.id)
        prompt = self.state.get_channel_system_prompt(channel_id)
        
        if prompt:
            # Split system prompt into chunks of 1950 characters or fewer
            max_length = 1950
            chunks = [prompt[i:i+max_length] for i in range(0, len(prompt), max_length)]
            
            await ctx.respond(f"Custom system prompt for this channel: \n```\n{chunks[0]}\n```")
            for chunk in chunks[1:]:
                await ctx.followup.send(f"```\n{chunk}\n```")
        else:
            # Show default prompt
            from ..config import SYSTEM_PROMPT
            max_length = 1950
            chunks = [SYSTEM_PROMPT[i:i+max_length] for i in range(0, len(SYSTEM_PROMPT), max_length)]
            
            await ctx.respond(f"This channel uses the default system prompt: \n```\n{chunks[0]}\n```")
            for chunk in chunks[1:]:
                await ctx.followup.send(f"```\n{chunk}\n```")

    @discord.slash_command(
        name="resetchannelsystem",
        description="Reset this channel to use the default system prompt"
    )
    @commands.has_permissions(administrator=True)
    async def reset_channel_system_slash(self, ctx):
        channel_id = str(ctx.channel.id)
        if self.state.reset_channel_system_prompt(channel_id):
            await ctx.respond(f"✅ This channel will now use the default system prompt.")
        else:
            await ctx.respond(f"ℹ️ This channel is already using the default system prompt.")

def setup(bot):
    bot.add_cog(ConfigCommands(bot))
