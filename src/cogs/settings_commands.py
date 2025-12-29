"""Global bot settings commands."""
import discord
import logging
from discord.ext import commands
from discord import Option
from ..utils.state_manager import BotStateManager
from ..config import (
    DEFAULT_MODEL, SYSTEM_PROMPT,
    INTENT_DISCOVERY, INTENT_DETECTION_MODEL, INTENT_CONFIDENCE_THRESHOLD
)

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

        # Get intent settings
        intent_enabled = self.state.get_intent_enabled()
        intent_model = self.state.get_intent_model()
        intent_threshold = self.state.get_intent_threshold()

        # Build hierarchical view
        embed = discord.Embed(
            title="Current Bot Settings",
            description="Global defaults that apply everywhere unless overridden",
            color=discord.Color.blue()
        )

        embed.add_field(
            name="Global Configuration",
            value=(
                f"**Provider:** `{global_provider}`\n"
                f"**Model:** `{global_model}`\n"
                f"**Memory Limit:** `{memory_limit}` messages\n"
                f"**Time Window:** `{time_window}` hours"
            ),
            inline=False
        )

        # Intent detection field
        intent_status = "Enabled" if intent_enabled else "Disabled"
        embed.add_field(
            name="Intent Detection",
            value=(
                f"**Status:** {intent_status}\n"
                f"**Model:** `{intent_model}`\n"
                f"**Threshold:** `{intent_threshold:.2f}` ({int(intent_threshold * 100)}%)"
            ),
            inline=False
        )

        embed.add_field(
            name="Configuration Hierarchy",
            value="Settings follow this order: **Thread > Channel > Global**",
            inline=False
        )

        embed.set_footer(text="Use /settings intent show for more intent details")

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
        name="reload",
        description="Reload all settings from .env file (resets to defaults)"
    )
    @commands.has_permissions(administrator=True)
    async def reload(self, ctx):
        """Reload all settings from environment variables."""
        await ctx.defer()
        try:
            reloaded = await self.state.reload_all_from_env(SYSTEM_PROMPT)

            intent_status = "Enabled" if reloaded["intent_enabled"] else "Disabled"
            await ctx.respond(
                f"✅ All settings reloaded from `.env`:\n"
                f"**Global:**\n"
                f"• Model: `{reloaded['global_model']}`\n"
                f"• Memory: `{reloaded['max_channel_history']}` messages\n"
                f"• Time window: `{reloaded['time_window_hours']}` hours\n"
                f"• System prompt: Default\n\n"
                f"**Intent Detection:**\n"
                f"• Status: {intent_status}\n"
                f"• Model: `{reloaded['intent_model']}`\n"
                f"• Threshold: `{reloaded['intent_threshold']:.2f}`"
            )
        except Exception as e:
            logger.error(f"Error reloading settings: {e}", exc_info=True)
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
                "`/settings reload` - Reset all to .env defaults"
            ),
            inline=False
        )

        embed.add_field(
            name="Intent Detection Commands",
            value=(
                "`/settings intent show` - View intent settings\n"
                "`/settings intent toggle` - Enable/disable intent detection\n"
                "`/settings intent model` - Change intent detection model\n"
                "`/settings intent threshold` - Change confidence threshold\n"
                "`/settings intent reload` - Reload from .env file"
            ),
            inline=False
        )

        embed.set_footer(text="Admin permissions required for most settings commands")

        await ctx.respond(embed=embed)

    # --- Intent Settings Subgroup ---
    intent = settings.create_subgroup(
        "intent",
        "Configure AI-powered intent detection for @mentions"
    )

    async def intent_model_autocomplete(self, ctx):
        """Dynamic model autocomplete for intent detection model."""
        current_input = ctx.value.lower() if ctx.value else ""

        # Get models from common fast providers
        all_models = []
        for provider in ["openai", "google", "anthropic"]:
            try:
                model_ids = await self.bot.model_manager.get_models(provider)
                for model_id in model_ids:
                    full_model = f"{provider}/{model_id}"
                    all_models.append(full_model)
            except Exception:
                pass

        # Get current intent model for highlighting
        current_model = self.state.get_intent_model()

        # Format with current marker
        formatted = []
        for model in all_models:
            if model == current_model:
                formatted.append(f"* {model} (current)")
            else:
                formatted.append(model)

        if not current_input:
            return formatted[:25]

        matching = [m for m in formatted if current_input in m.lower()]
        return matching[:25] or formatted[:25]

    @intent.command(
        name="show",
        description="View current intent detection settings"
    )
    async def intent_show(self, ctx):
        """Display current intent detection configuration."""
        await ctx.defer()

        enabled = self.state.get_intent_enabled()
        model = self.state.get_intent_model()
        threshold = self.state.get_intent_threshold()

        status_emoji = "**Enabled**" if enabled else "Disabled"
        status_color = discord.Color.green() if enabled else discord.Color.greyple()

        embed = discord.Embed(
            title="Intent Detection Settings",
            description="AI-powered intent detection for @mentions",
            color=status_color
        )

        embed.add_field(
            name="Status",
            value=status_emoji,
            inline=True
        )

        embed.add_field(
            name="Model",
            value=f"`{model}`",
            inline=True
        )

        embed.add_field(
            name="Confidence Threshold",
            value=f"`{threshold:.2f}` ({int(threshold * 100)}%)",
            inline=True
        )

        embed.add_field(
            name="What is Intent Detection?",
            value=(
                "When enabled, @mentions are analyzed to detect user intent "
                "(reminders, image generation, searches, calculations, etc.) "
                "and handled automatically.\n\n"
                "**Cost:** ~$0.00003 per mention\n"
                "**Latency:** ~300ms additional"
            ),
            inline=False
        )

        embed.set_footer(text="Use /settings intent toggle to enable/disable")

        await ctx.respond(embed=embed)

    @intent.command(
        name="toggle",
        description="Enable or disable intent detection"
    )
    @commands.has_permissions(administrator=True)
    async def intent_toggle(
        self,
        ctx,
        enabled: Option(
            bool,
            "Enable or disable intent detection",
            choices=[
                discord.OptionChoice(name="Enable", value=True),
                discord.OptionChoice(name="Disable", value=False)
            ]
        )
    ):
        """Toggle intent detection on or off."""
        await ctx.defer()
        try:
            await self.state.set_intent_enabled(enabled)
            status = "enabled" if enabled else "disabled"
            await ctx.respond(f"Intent detection {status}")
        except Exception as e:
            logger.error(f"Error toggling intent detection: {e}", exc_info=True)
            await ctx.respond(f"Error: {e}", ephemeral=True)

    @intent.command(
        name="model",
        description="Set the AI model for intent detection (format: provider/model)"
    )
    @commands.has_permissions(administrator=True)
    async def intent_model(
        self,
        ctx,
        model_name: Option(str, "Select the AI model for intent detection", autocomplete=intent_model_autocomplete)
    ):
        """Set the intent detection model."""
        await ctx.defer()
        try:
            # Clean up autocomplete marker if present
            if model_name.startswith("* "):
                model_name = model_name[2:]
            if model_name.endswith(" (current)"):
                model_name = model_name[:-10]

            await self.state.set_intent_model(model_name)
            await ctx.respond(f"Intent detection model set to `{model_name}`")
        except ValueError as e:
            error_msg = str(e)
            if "not found" in error_msg and "/" not in model_name:
                error_msg += "\n\n**Tip:** Use format `provider/model` (e.g., `openai/gpt-4o-mini`)"
            await ctx.respond(f"Error: {error_msg}", ephemeral=True)
        except Exception as e:
            logger.error(f"Error setting intent model: {e}", exc_info=True)
            await ctx.respond(f"Error: {e}", ephemeral=True)

    @intent.command(
        name="threshold",
        description="Set the confidence threshold for intent detection (0.0-1.0)"
    )
    @commands.has_permissions(administrator=True)
    async def intent_threshold(
        self,
        ctx,
        threshold: Option(
            float,
            "Confidence threshold (0.0-1.0). Lower = more triggers, Higher = fewer triggers",
            min_value=0.0,
            max_value=1.0
        )
    ):
        """Set the intent confidence threshold."""
        await ctx.defer()
        try:
            await self.state.set_intent_threshold(threshold)
            level = "aggressive" if threshold < 0.6 else "balanced" if threshold < 0.8 else "conservative"
            await ctx.respond(
                f"Intent confidence threshold set to `{threshold:.2f}` ({int(threshold * 100)}%)\n"
                f"Mode: **{level}**"
            )
        except ValueError as e:
            await ctx.respond(f"Error: {e}", ephemeral=True)
        except Exception as e:
            logger.error(f"Error setting intent threshold: {e}", exc_info=True)
            await ctx.respond(f"Error: {e}", ephemeral=True)

    @intent.command(
        name="reload",
        description="Reload intent settings from .env file"
    )
    @commands.has_permissions(administrator=True)
    async def intent_reload(self, ctx):
        """Reload intent settings from environment variables."""
        await ctx.defer()
        try:
            await self.state.reload_intent_from_env()
            enabled = self.state.get_intent_enabled()
            model = self.state.get_intent_model()
            threshold = self.state.get_intent_threshold()

            await ctx.respond(
                f"Intent settings reloaded from `.env`:\n"
                f"- **Enabled:** {enabled}\n"
                f"- **Model:** `{model}`\n"
                f"- **Threshold:** `{threshold:.2f}`"
            )
        except Exception as e:
            logger.error(f"Error reloading intent settings: {e}", exc_info=True)
            await ctx.respond(f"Error: {e}", ephemeral=True)


def setup(bot):
    bot.add_cog(SettingsCommands(bot))
