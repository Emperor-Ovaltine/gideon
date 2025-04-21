"""Configuration commands for the bot."""
import discord
import logging # Add logging import
from discord.ext import commands, tasks # Import tasks
from discord import Option
from ..utils.state_manager import BotStateManager
from ..utils.openrouter_client import OpenRouterClient
from ..config import OPENROUTER_API_KEY, SYSTEM_PROMPT, ALLOWED_MODELS, DEFAULT_MODEL
# Removed: from ..utils.model_sync import sync_models
from ..utils.model_manager import get_model_choices

logger = logging.getLogger(__name__) # Define logger

class ConfigCommands(commands.Cog, name="ConfigCommands"):
    """Commands for bot configuration."""
    
    def __init__(self, bot):
        self.bot = bot
        # Use the shared state manager from the bot instance
        self.state = bot.state_manager
        self.openrouter_client = OpenRouterClient(OPENROUTER_API_KEY, SYSTEM_PROMPT, DEFAULT_MODEL)
    
    async def model_autocomplete(self, ctx):
        """Dynamic model autocomplete using ModelManager, filtered by channel provider."""
        current_input = ctx.value.lower() if ctx.value else ""
        # Access channel ID via interaction in autocomplete context
        channel_id = str(ctx.interaction.channel_id)
        
        # Get the provider for the current channel
        current_provider = self.state.get_channel_provider(channel_id)
        
        # Get models for the current channel's provider
        model_ids = await self.bot.model_manager.get_models(current_provider)
        
        # Format models as provider/model_id for the autocomplete list
        all_models_formatted = [f"{current_provider}/{model_id}" for model_id in model_ids]
        
        if not current_input:
            # Return first 25 formatted models
            return all_models_formatted[:25]
            
        # Match against the full provider/model_id string
        matching_models = [model for model in all_models_formatted if current_input in model.lower()]
        
        # If no matches, return the first 25 formatted models for the provider
        return matching_models[:25] or all_models_formatted[:25]

    @discord.slash_command(
        name="setmodel",
        description="Set the AI model to use from OpenRouter"
    )
    @commands.has_permissions(administrator=True)
    async def set_model_slash(
        self, 
        ctx, 
        model_name: Option(str, "Select the AI model to use", autocomplete=model_autocomplete)
    ):
        await ctx.defer() # Defer response as validation is now async
        try:
            # self.openrouter_client.model = model_name # This is handled by sync_models
            await self.state.set_global_model(model_name)
            # sync_models(self.bot) # Removed - state manager handles source of truth
            await ctx.respond(f"✅ Global model set to `{model_name}`")
        except ValueError as e:
            await ctx.respond(f"⚠️ Error: {e}")
        except Exception as e:
            await ctx.respond(f"⚠️ An unexpected error occurred: {e}")
    
    @discord.slash_command(
        name="model",
        description="Show the current AI model being used or change to a new model"
    )
    async def show_model_slash(
        self, 
        ctx, 
        new_model: Option(str, "Select a new model to use (optional)", autocomplete=model_autocomplete, required=False)
    ):
        await ctx.defer()
        
        if new_model:
            if ctx.author.guild_permissions.administrator:
                try:
                    # self.openrouter_client.model = new_model # Removed - state manager handles source of truth
                    await self.state.set_global_model(new_model)
                    # sync_models(self.bot) # Removed - state manager handles source of truth
                    await ctx.respond(f"✅ Global model changed to: `{new_model}`")
                except ValueError as e:
                    await ctx.respond(f"⚠️ Error: {e}")
                except Exception as e:
                    await ctx.respond(f"⚠️ An unexpected error occurred: {e}")
            else:
                await ctx.respond("⚠️ Only administrators can change the model. Use `/setmodel` if you have admin permissions.")
        else:
            current_model = self.state.get_global_model() or DEFAULT_MODEL
            # Ensure the current global model is valid on startup/load
            try:
                await self.state.set_global_model(current_model)
            except ValueError:
                # If the saved/default model is somehow invalid, reset to the absolute default
                current_model = DEFAULT_MODEL
                await self.state.set_global_model(current_model) # This should always work if DEFAULT_MODEL is valid initially
                # sync_models(self.bot) # Removed - state manager handles source of truth
                await ctx.followup.send(f"⚠️ Warning: Previous global model was invalid. Resetting to default: `{current_model}`")

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
        model_name: Option(str, "Select the AI model to use for this channel", autocomplete=model_autocomplete)
    ):
        await ctx.defer() # Defer response as validation is now async
        channel_id = str(ctx.channel.id)
        try:
            await self.state.set_channel_model(channel_id, model_name)
            await ctx.respond(f"✅ Model for this channel set to `{model_name}`")
        except ValueError as e:
            await ctx.respond(f"⚠️ Error: {e}")
        except Exception as e:
            await ctx.respond(f"⚠️ An unexpected error occurred: {e}")

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


    @discord.slash_command(
        name="showsettings",
        description="Show current global, channel, and thread AI configurations"
    )
    @commands.has_permissions(administrator=True)
    async def show_settings_slash(self, ctx):
        """Displays all current AI configuration overrides."""
        await ctx.defer(ephemeral=True)

        try:
            # Global Settings
            global_provider = self.state.global_provider
            global_model = self.state.get_global_model() # Removed await

            embed = discord.Embed(title="⚙️ Current AI Settings", color=discord.Color.blue())
            embed.add_field(
                name="🌍 Global Defaults",
                value=f"**Provider:** `{global_provider}`\n**Model:** `{global_model}`",
                inline=False
            )

            # Channel Overrides
            channel_configs = self.state.get_all_channel_configs()
            channel_text = ""
            if channel_configs:
                for config in channel_configs:
                    channel_id = config['channel_id']
                    provider = config.get('provider')
                    model = config.get('model')
                    prompt = config.get('system_prompt')
                    channel_text += f"\n**<#{channel_id}>:**"
                    if provider:
                        channel_text += f"\n  Provider: `{provider}`"
                    if model:
                        channel_text += f"\n  Model: `{model}`"
                    if prompt:
                        prompt_short = (prompt[:75] + '...') if len(prompt) > 75 else prompt
                        channel_text += f"\n  System Prompt: `\"{prompt_short}\"`"
                    channel_text += "\n" # Add spacing
            else:
                channel_text = "No channel overrides set."

            # Truncate if too long for embed field
            if len(channel_text) > 1020:
                channel_text = channel_text[:1020] + "\n... (list truncated)"
            embed.add_field(name="🔧 Channel Overrides", value=channel_text, inline=False)

            # Thread Overrides
            thread_configs = self.state.get_all_thread_configs()
            thread_text = ""
            if thread_configs:
                for config in thread_configs:
                    thread_id = config['thread_id']
                    thread_name = config.get('name', 'Unknown Name')
                    model = config.get('model')
                    prompt = config.get('system_prompt')
                    # Try to make thread name clickable if possible (might not work reliably everywhere)
                    thread_text += f"\n**<#{thread_id}> ({thread_name}):**"
                    if model:
                        thread_text += f"\n  Model: `{model}`"
                    if prompt:
                        prompt_short = (prompt[:75] + '...') if len(prompt) > 75 else prompt
                        thread_text += f"\n  System Prompt: `\"{prompt_short}\"`"
                    thread_text += "\n" # Add spacing
            else:
                thread_text = "No thread overrides set."

            # Truncate if too long for embed field
            if len(thread_text) > 1020:
                thread_text = thread_text[:1020] + "\n... (list truncated)"
            embed.add_field(name="🧵 Thread Overrides", value=thread_text, inline=False)

            await ctx.respond(embed=embed)

        except Exception as e:
            logger.error(f"Error in /showsettings: {e}", exc_info=True)
            await ctx.respond(f"⚠️ An error occurred while fetching settings: {e}", ephemeral=True)


    @discord.slash_command(
        name="restoredefaults",
        description="Restore all AI configurations to default (OpenRouter, default model)"
    )
    @commands.has_permissions(administrator=True)
    async def restore_defaults_slash(self, ctx):
        """Resets global, channel, and thread AI settings to application defaults."""
        await ctx.defer(ephemeral=True)
        try:
            # Import DEFAULT_MODEL here to ensure it's fresh if config changes
            from ..config import DEFAULT_MODEL

            # 1. Reset Global Settings
            await self.state.set_global_provider("openrouter")
            await self.state.set_global_model(DEFAULT_MODEL)
            logger.info(f"Global settings reset to provider 'openrouter', model '{DEFAULT_MODEL}' by {ctx.author}")

            # 2. Reset Channel Overrides
            channel_ids_to_reset = self.state.db_manager.get_all_configured_channel_ids()
            channels_reset_count = 0
            for channel_id in channel_ids_to_reset:
                try:
                    # reset_channel_config handles model, provider, and system prompt
                    success = self.state.db_manager.reset_channel_config(channel_id)
                    if success:
                        channels_reset_count += 1
                        logger.debug(f"Reset config for channel {channel_id}")
                except Exception as e:
                    logger.error(f"Error resetting channel {channel_id} config: {e}", exc_info=True)

            # 3. Reset Thread Overrides
            thread_ids_to_reset = self.state.db_manager.get_all_configured_thread_ids()
            threads_reset_count = 0
            for thread_id in thread_ids_to_reset:
                try:
                    # Reset model and system prompt individually for threads
                    model_reset = self.state.db_manager.set_thread_model(thread_id, None)
                    prompt_reset = self.state.db_manager.set_thread_system_prompt(thread_id, None)
                    if model_reset or prompt_reset: # Count if either was actually changed (or existed)
                        threads_reset_count += 1
                        logger.debug(f"Reset config for thread {thread_id}")
                except Exception as e:
                    logger.error(f"Error resetting thread {thread_id} config: {e}", exc_info=True)

            await ctx.respond(
                f"✅ All configurations restored to defaults.\n"
                f"Provider: `openrouter`\n"
                f"Model: `{DEFAULT_MODEL}`\n"
                f"Reset {channels_reset_count} channel configurations.\n"
                f"Reset {threads_reset_count} thread configurations.",
                ephemeral=True
            )

        except Exception as e:
            logger.error(f"Error in /restoredefaults: {e}", exc_info=True)
            await ctx.respond(f"⚠️ An error occurred while restoring defaults: {e}", ephemeral=True)


    @commands.slash_command(name="select_model", description="Select a model")
    async def select_model(self, ctx, model: Option(str, "Choose a model", autocomplete=model_autocomplete)):
        """Select a model from available options."""
        await ctx.defer() # Defer response as validation is now async
        if ctx.author.guild_permissions.administrator:
            try:
                # self.openrouter_client.model = model # Removed - state manager handles source of truth
                await self.state.set_global_model(model)
                # sync_models(self.bot) # Removed - state manager handles source of truth
                await ctx.respond(f"✅ Global model changed to: `{model}`")
            except ValueError as e:
                await ctx.respond(f"⚠️ Error: {e}")
            except Exception as e:
                await ctx.respond(f"⚠️ An unexpected error occurred: {e}")
        else:
            await ctx.respond("⚠️ Only administrators can change the model.")

    @discord.slash_command(
        name="setprunefrequency",
        description="Set how often old data is pruned (in hours)"
    )
    @commands.has_permissions(administrator=True)
    async def set_prune_frequency_slash(self, ctx, hours: Option(int, "Frequency in hours (minimum 1)", min_value=1)):
        """Sets how often old messages, threads, summaries, etc., are pruned."""
        await ctx.defer(ephemeral=True)
        try:
            await self.state.set_prune_frequency_hours(hours)

            # Attempt to update the running task's interval
            if hasattr(self.bot, 'prune_data_task') and isinstance(self.bot.prune_data_task, tasks.Loop):
                try:
                    self.bot.prune_data_task.change_interval(hours=hours)
                    await ctx.respond(f"✅ Pruning frequency set to **{hours} hours**. The task interval has been updated.")
                except Exception as task_err:
                    logger.error(f"Error updating prune task interval: {task_err}", exc_info=True)
                    await ctx.respond(f"✅ Pruning frequency set to **{hours} hours**. Restart the bot for the new schedule to take effect.")
            else:
                logger.warning("Could not find prune_data_task on bot object to update interval.")
                await ctx.respond(f"✅ Pruning frequency set to **{hours} hours**. Restart the bot for the new schedule to take effect.")

        except ValueError as e:
            await ctx.respond(f"⚠️ Error: {e}")
        except Exception as e:
            logger.error(f"Error setting prune frequency: {e}", exc_info=True)
            await ctx.respond(f"⚠️ An unexpected error occurred.")


    @discord.slash_command(
        name="setsummaryretention",
        description="Set how long news summaries are kept (in days)"
    )
    @commands.has_permissions(administrator=True)
    async def set_summary_retention_slash(self, ctx, days: Option(int, "Retention period in days (minimum 1)", min_value=1)):
        """Sets how long cached news article summaries are kept before pruning."""
        await ctx.defer(ephemeral=True)
        try:
            await self.state.set_summary_retention_days(days)
            await ctx.respond(f"✅ News summary retention period set to **{days} days**.")
        except ValueError as e:
            await ctx.respond(f"⚠️ Error: {e}")
        except Exception as e:
            logger.error(f"Error setting summary retention: {e}", exc_info=True)
            await ctx.respond(f"⚠️ An unexpected error occurred.")


    @discord.slash_command(
        name="setpersonalfeedfrequency",
        description="Set how often personal news feeds are checked (in hours)"
    )
    @commands.has_permissions(administrator=True)
    async def set_personal_feed_frequency_slash(self, ctx, hours: Option(int, "Frequency in hours (minimum 1)", min_value=1)):
        """Sets how often personal news feeds are checked and summaries cached."""
        await ctx.defer(ephemeral=True)
        try:
            await self.state.set_personal_feed_frequency(hours)

            # Attempt to update the running task's interval
            # Note: The task name 'check_personal_feeds' is assumed based on the plan.
            # It will be defined in the NewsFeedsCommands cog.
            news_cog = self.bot.get_cog("NewsFeedsCommands")
            if news_cog and hasattr(news_cog, 'check_personal_feeds') and isinstance(news_cog.check_personal_feeds, tasks.Loop):
                try:
                    news_cog.check_personal_feeds.change_interval(hours=hours)
                    await ctx.respond(f"✅ Personal feed check frequency set to **{hours} hours**. The task interval has been updated.")
                except Exception as task_err:
                    logger.error(f"Error updating personal feed task interval: {task_err}", exc_info=True)
                    await ctx.respond(f"✅ Personal feed check frequency set to **{hours} hours**. Restart the bot for the new schedule to take effect.")
            else:
                logger.warning("Could not find check_personal_feeds task on NewsFeedsCommands cog to update interval.")
                await ctx.respond(f"✅ Personal feed check frequency set to **{hours} hours**. Restart the bot for the new schedule to take effect.")

        except ValueError as e:
            await ctx.respond(f"⚠️ Error: {e}")
        except Exception as e:
            logger.error(f"Error setting personal feed frequency: {e}", exc_info=True)
            await ctx.respond(f"⚠️ An unexpected error occurred.")


def setup(bot):
    config_cog = ConfigCommands(bot)
    bot.add_cog(config_cog)
    print(f"ConfigCommands cog registered successfully as '{config_cog.__class__.__name__}'!")
