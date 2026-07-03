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

    # Create command group with admin-only visibility
    settings = discord.SlashCommandGroup(
        "settings",
        "Global bot configuration (admin only)",
        default_member_permissions=discord.Permissions(administrator=True)
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

        # Get tool calling settings
        tool_calling_enabled = self.state.get_tool_calling_enabled()
        tool_calling_max_iterations = self.state.get_tool_calling_max_iterations()

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

        # Tool calling field
        tool_status = "Enabled" if tool_calling_enabled else "Disabled"
        embed.add_field(
            name="Native Tool Calling",
            value=(
                f"**Status:** {tool_status}\n"
                f"**Max iterations:** `{tool_calling_max_iterations}`"
            ),
            inline=False
        )

        embed.add_field(
            name="Configuration Hierarchy",
            value="Settings follow this order: **Thread > Channel > Global**",
            inline=False
        )

        embed.set_footer(text="Use /settings tools show for tool calling details")

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

            tool_status = "Enabled" if reloaded["tool_calling_enabled"] else "Disabled"
            await ctx.respond(
                f"✅ All settings reloaded from `.env`:\n"
                f"**Global:**\n"
                f"• Model: `{reloaded['global_model']}`\n"
                f"• Memory: `{reloaded['max_channel_history']}` messages\n"
                f"• Time window: `{reloaded['time_window_hours']}` hours\n"
                f"• System prompt: Default\n\n"
                f"**Native Tool Calling:**\n"
                f"• Status: {tool_status}\n"
                f"• Max iterations: `{reloaded['tool_calling_max_iterations']}`"
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

    # --- Tool Calling Subgroup ---
    tools = settings.create_subgroup(
        "tools",
        "Configure native LLM tool calling for @mentions"
    )

    @tools.command(
        name="show",
        description="View current tool calling settings"
    )
    async def tools_show(self, ctx):
        """Display current tool calling configuration."""
        await ctx.defer()

        enabled = self.state.get_tool_calling_enabled()
        max_iterations = self.state.get_tool_calling_max_iterations()

        status_color = discord.Color.green() if enabled else discord.Color.greyple()
        embed = discord.Embed(
            title="Native Tool Calling Settings",
            description="The primary model decides when to call tools (reminders, images, search, etc.)",
            color=status_color
        )
        embed.add_field(name="Status", value="**Enabled**" if enabled else "Disabled", inline=True)
        embed.add_field(name="Max iterations", value=f"`{max_iterations}`", inline=True)
        embed.add_field(
            name="What is Tool Calling?",
            value=(
                "When enabled, @mentions are answered by the primary model with tool "
                "definitions attached. The model natively decides whether to call a tool "
                "(set a reminder, generate an image, search the web, calculate, etc.) "
                "or reply conversationally. Requires a model with function-calling support."
            ),
            inline=False
        )
        embed.set_footer(text="Use /settings tools toggle to enable/disable")
        await ctx.respond(embed=embed)

    @tools.command(
        name="toggle",
        description="Enable or disable native tool calling"
    )
    @commands.has_permissions(administrator=True)
    async def tools_toggle(
        self,
        ctx,
        enabled: Option(
            bool,
            "Enable or disable tool calling",
            choices=[
                discord.OptionChoice(name="Enable", value=True),
                discord.OptionChoice(name="Disable", value=False)
            ]
        )
    ):
        """Toggle native tool calling on or off."""
        await ctx.defer()
        try:
            await self.state.set_tool_calling_enabled(enabled)
            status = "enabled" if enabled else "disabled"
            await ctx.respond(f"Native tool calling {status}")
        except Exception as e:
            logger.error(f"Error toggling tool calling: {e}", exc_info=True)
            await ctx.respond(f"Error: {e}", ephemeral=True)

    @tools.command(
        name="max_iterations",
        description="Set the maximum tool-call round-trips before forcing a text response (1-10)"
    )
    @commands.has_permissions(administrator=True)
    async def tools_max_iterations(
        self,
        ctx,
        value: Option(int, "Maximum tool-call iterations", min_value=1, max_value=10)
    ):
        """Set the tool-calling iteration budget."""
        await ctx.defer()
        try:
            await self.state.set_tool_calling_max_iterations(value)
            await ctx.respond(f"Tool calling max iterations set to `{value}`")
        except ValueError as e:
            await ctx.respond(f"Error: {e}", ephemeral=True)
        except Exception as e:
            logger.error(f"Error setting tool calling max iterations: {e}", exc_info=True)
            await ctx.respond(f"Error: {e}", ephemeral=True)


def setup(bot):
    bot.add_cog(SettingsCommands(bot))
