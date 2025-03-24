"""Configuration commands for the bot."""
import discord
from discord.ext import commands
from discord import Option
from ..utils.state_manager import BotStateManager
from ..utils.openrouter_client import OpenRouterClient
from ..config import OPENROUTER_API_KEY, SYSTEM_PROMPT, ALLOWED_MODELS, DEFAULT_MODEL
from ..utils.model_sync import sync_models
from ..utils.model_manager import get_model_choices

class ConfigCommands(commands.Cog, name="ConfigCommands"):
    """Commands for bot configuration."""
    
    def __init__(self, bot):
        self.bot = bot
        self.state = BotStateManager()
        self.openrouter_client = OpenRouterClient(OPENROUTER_API_KEY, SYSTEM_PROMPT, DEFAULT_MODEL)
    
    async def model_autocomplete(self, ctx):
        """Dynamic model autocomplete using ModelManager"""
        current_input = ctx.value.lower() if ctx.value else ""
        all_models = await self.bot.model_manager.get_models()
        if not current_input:
            return all_models[:25]
        matching_models = [model for model in all_models if current_input in model.lower()]
        return matching_models[:25] or all_models[:25]

    @discord.slash_command(
        name="setmodel",
        description="Set the AI model to use from OpenRouter"
    )
    @commands.has_permissions(administrator=True)
    async def set_model_slash(
        self, 
        ctx, 
        model_name: discord.Option(str, "Select the AI model to use", autocomplete=model_autocomplete)
    ):
        self.openrouter_client.model = model_name
        self.state.set_global_model(model_name)
        sync_models(self.bot)
        await ctx.respond(f"Model set to {model_name}")
    
    @discord.slash_command(
        name="model",
        description="Show the current AI model being used or change to a new model"
    )
    async def show_model_slash(
        self, 
        ctx, 
        new_model: discord.Option(str, "Select a new model to use (optional)", autocomplete=model_autocomplete, required=False)
    ):
        await ctx.defer()
        
        if new_model:
            if ctx.author.guild_permissions.administrator:
                self.openrouter_client.model = new_model
                self.state.set_global_model(new_model)
                sync_models(self.bot)
                await ctx.respond(f"✅ Model changed to: `{new_model}`")
            else:
                await ctx.respond("⚠️ Only administrators can change the model. Use `/setmodel` if you have admin permissions.")
        else:
            current_model = self.state.get_global_model() or DEFAULT_MODEL
            self.state.set_global_model(current_model)
            models = await self.bot.model_manager.get_models()
            models_list = "\n".join([f"• `{model}`" for model in models[:5]])
            if len(models) > 5:
                models_list += f"\n• ... and {len(models) - 5} more models"
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
    async def set_channel_model_slash(
        self, 
        ctx, 
        model_name: discord.Option(str, "Select the AI model to use for this channel", autocomplete=model_autocomplete)
    ):
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
            max_length = 1950
            chunks = [prompt[i:i+max_length] for i in range(0, len(prompt), max_length)]
            
            await ctx.respond(f"Custom system prompt for this channel: \n```\n{chunks[0]}\n```")
            for chunk in chunks[1:]:
                await ctx.followup.send(f"```\n{chunk}\n```")
        else:
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

    @commands.slash_command(name="select_model", description="Select a model")
    async def select_model(self, ctx, model: Option(str, "Choose a model", autocomplete=model_autocomplete)):
        """Select a model from available options."""
        if ctx.author.guild_permissions.administrator:
            self.openrouter_client.model = model
            self.state.set_global_model(model)
            sync_models(self.bot)
            await ctx.respond(f"✅ Model changed to: `{model}`")
        else:
            await ctx.respond("⚠️ Only administrators can change the model.")
    
def setup(bot):
    config_cog = ConfigCommands(bot)
    bot.add_cog(config_cog)
    print(f"ConfigCommands cog registered successfully as '{config_cog.__class__.__name__}'!")
