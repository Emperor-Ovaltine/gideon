"""Global bot settings commands."""
import discord
import logging
from discord.ext import commands
from discord import Option
from ..utils.state_manager import BotStateManager
from ..config import DEFAULT_MODEL, SYSTEM_PROMPT

logger = logging.getLogger(__name__)

class SettingsCommands(commands.Cog, name="SettingsCommands"):
    """Commands for global bot configuration."""

    def __init__(self, bot):
        self.bot = bot
        self.state = bot.state_manager

    # Create command group
    settings = discord.SlashCommandGroup(
        "settings",
        "Global bot configuration (admin only)"
    )

    async def model_autocomplete(self, ctx):
        """Dynamic model autocomplete using ModelManager."""
        current_input = ctx.value.lower() if ctx.value else ""
        channel_id = str(ctx.interaction.channel_id)

        # Get the provider for the current channel
        current_provider = self.state.get_channel_provider(channel_id)

        # Get current global model for highlighting
        current_model = self.state.get_global_model()

        # Get models for the current channel's provider
        model_ids = await self.bot.model_manager.get_models(current_provider)

        # Format models as provider/model_id
        all_models_formatted = []
        for model_id in model_ids:
            full_model = f"{current_provider}/{model_id}"
            # Highlight current selection
            if full_model == current_model:
                all_models_formatted.append(f"✓ {full_model} (current)")
            else:
                all_models_formatted.append(full_model)

        if not current_input:
            return all_models_formatted[:25]

        # Match against the full provider/model_id string
        matching_models = [model for model in all_models_formatted if current_input in model.lower()]

        return matching_models[:25] or all_models_formatted[:25]

    @settings.command(
        name="show",
        description="View all current bot settings"
    )
    async def show(self, ctx):
        """Display all current global settings."""
        await ctx.defer()

        # Get all settings
        global_model = self.state.get_global_model() or DEFAULT_MODEL
        global_provider = self.state.get_global_provider()
        memory_limit = self.state.get_max_channel_history()
        time_window = self.state.get_time_window_hours()

        # Build hierarchical view
        embed = discord.Embed(
            title="⚙️ Current Bot Settings",
            description="Global defaults that apply everywhere unless overridden",
            color=discord.Color.blue()
        )

        embed.add_field(
            name="🌍 Global Configuration",
            value=(
                f"**Provider:** `{global_provider}`\n"
                f"**Model:** `{global_model}`\n"
                f"**Memory Limit:** `{memory_limit}` messages\n"
                f"**Time Window:** `{time_window}` hours"
            ),
            inline=False
        )

        embed.add_field(
            name="💡 Configuration Hierarchy",
            value="Settings follow this order: **Thread > Channel > Global**",
            inline=False
        )

        embed.set_footer(text="Use /channel show to see channel-specific settings")

        await ctx.respond(embed=embed)

    @settings.command(
        name="model",
        description="Set global AI model (format: provider/model, e.g., openrouter/gpt-4)"
    )
    @commands.has_permissions(administrator=True)
    async def model(
        self,
        ctx,
        model_name: Option(str, "Select the AI model to use", autocomplete=model_autocomplete)
    ):
        """Set the global default AI model."""
        await ctx.defer()
        try:
            await self.state.set_global_model(model_name)
            await ctx.respond(f"✅ Global model set to `{model_name}`")
        except ValueError as e:
            error_msg = str(e)
            # Add helpful hints
            if "not found" in error_msg and "/" not in model_name:
                error_msg += "\n\n💡 **Tip:** Use format `provider/model` (e.g., `openrouter/gpt-4`)"
            elif "not found" in error_msg:
                error_msg += "\n\n💡 **Tip:** Use autocomplete to see available models"
            await ctx.respond(f"⚠️ Error: {error_msg}", ephemeral=True)
        except Exception as e:
            logger.error(f"Unexpected error in /settings model: {e}", exc_info=True)
            await ctx.respond(
                f"❌ Unexpected error occurred.\n\n"
                f"Please contact an administrator or check `/admin diagnostic`.",
                ephemeral=True
            )

    @settings.command(
        name="system",
        description="Set global system prompt for AI responses"
    )
    @commands.has_permissions(administrator=True)
    async def system(self, ctx, prompt: str):
        """Set the global system prompt."""
        await ctx.defer()
        try:
            await self.state.set_global_system_prompt(prompt)
            await ctx.respond(f"✅ Global system prompt updated:\n```\n{prompt}\n```")
        except Exception as e:
            logger.error(f"Error setting system prompt: {e}", exc_info=True)
            await ctx.respond(f"❌ Error: {e}", ephemeral=True)

    @settings.command(
        name="provider",
        description="Set global AI provider (openrouter, openai, etc.)"
    )
    @commands.has_permissions(administrator=True)
    async def provider(
        self,
        ctx,
        provider_name: Option(
            str,
            "Select AI provider",
            choices=["openrouter", "openai"]
        )
    ):
        """Set the global AI provider."""
        await ctx.defer()
        try:
            await self.state.set_global_provider(provider_name)
            await ctx.respond(f"✅ Global provider set to `{provider_name}`")
        except Exception as e:
            logger.error(f"Error setting provider: {e}", exc_info=True)
            await ctx.respond(f"❌ Error: {e}", ephemeral=True)

    @settings.command(
        name="memory",
        description="Set maximum number of messages to remember per channel"
    )
    @commands.has_permissions(administrator=True)
    async def memory(self, ctx, size: int):
        """Set the global memory limit."""
        await ctx.defer()
        try:
            if size < 1 or size > 100:
                await ctx.respond("⚠️ Memory size must be between 1 and 100 messages.", ephemeral=True)
                return

            await self.state.set_max_channel_history(size)
            await ctx.respond(f"✅ Global memory limit set to {size} messages")
        except Exception as e:
            logger.error(f"Error setting memory: {e}", exc_info=True)
            await ctx.respond(f"❌ Error: {e}", ephemeral=True)

    @settings.command(
        name="window",
        description="Set time window for message history (in hours)"
    )
    @commands.has_permissions(administrator=True)
    async def window(self, ctx, hours: int):
        """Set the global time window."""
        await ctx.defer()
        try:
            if hours < 1 or hours > 96:
                await ctx.respond("⚠️ Time window must be between 1 and 96 hours.", ephemeral=True)
                return

            await self.state.set_time_window_hours(hours)
            await ctx.respond(f"✅ Global time window set to {hours} hours")
        except Exception as e:
            logger.error(f"Error setting time window: {e}", exc_info=True)
            await ctx.respond(f"❌ Error: {e}", ephemeral=True)

    @settings.command(
        name="restore",
        description="Reset all global settings to defaults"
    )
    @commands.has_permissions(administrator=True)
    async def restore(self, ctx):
        """Restore default global settings."""
        await ctx.defer()
        try:
            # Reset to defaults
            await self.state.set_global_model(DEFAULT_MODEL)
            await self.state.set_global_system_prompt(SYSTEM_PROMPT)
            await self.state.set_max_channel_history(50)
            await self.state.set_time_window_hours(24)

            await ctx.respond(
                f"✅ Global settings restored to defaults:\n"
                f"• Model: `{DEFAULT_MODEL}`\n"
                f"• Memory: 50 messages\n"
                f"• Time window: 24 hours\n"
                f"• System prompt: Default"
            )
        except Exception as e:
            logger.error(f"Error restoring defaults: {e}", exc_info=True)
            await ctx.respond(f"❌ Error: {e}", ephemeral=True)

    @settings.command(
        name="info",
        description="Get detailed information about bot configuration"
    )
    async def info(self, ctx):
        """Display help information about settings."""
        embed = discord.Embed(
            title="📚 Settings Information",
            description="Understanding Gideon's configuration system",
            color=discord.Color.green()
        )

        embed.add_field(
            name="Configuration Hierarchy",
            value=(
                "Settings are applied in this order:\n"
                "1. **Thread settings** (highest priority)\n"
                "2. **Channel settings** (overrides global)\n"
                "3. **Global settings** (defaults)\n\n"
                "This means thread settings override channel settings, "
                "which override global settings."
            ),
            inline=False
        )

        embed.add_field(
            name="Model Format",
            value=(
                "Models must be specified as `provider/model`\n"
                "Examples:\n"
                "• `openrouter/gpt-4`\n"
                "• `openrouter/claude-3.5-sonnet`\n"
                "• `openai/gpt-4o`\n\n"
                "Use autocomplete to see available models!"
            ),
            inline=False
        )

        embed.add_field(
            name="Commands",
            value=(
                "`/settings show` - View current settings\n"
                "`/settings model` - Change AI model\n"
                "`/settings system` - Change system prompt\n"
                "`/settings provider` - Change AI provider\n"
                "`/settings memory` - Change memory limit\n"
                "`/settings window` - Change time window\n"
                "`/settings restore` - Reset to defaults"
            ),
            inline=False
        )

        embed.set_footer(text="Admin permissions required for most settings commands")

        await ctx.respond(embed=embed)


def setup(bot):
    bot.add_cog(SettingsCommands(bot))
