"""Channel-specific settings commands."""
import discord
import logging
from discord.ext import commands
from discord import Option
from ..utils.state_manager import BotStateManager
from ..config import DEFAULT_MODEL, SYSTEM_PROMPT

logger = logging.getLogger(__name__)

class ChannelCommands(commands.Cog, name="ChannelCommands"):
    """Commands for channel-specific configuration."""

    def __init__(self, bot):
        self.bot = bot
        self.state = bot.state_manager

    # Create command group
    channel = discord.SlashCommandGroup(
        "channel",
        "Channel-specific settings (admin only)"
    )

    async def model_autocomplete(self, ctx):
        """Dynamic model autocomplete using ModelManager."""
        current_input = ctx.value.lower() if ctx.value else ""
        channel_id = str(ctx.interaction.channel_id)

        # Get the provider for the current channel
        current_provider = self.state.get_channel_provider(channel_id)

        # Get current channel model for highlighting
        current_model = self.state.get_channel_model(channel_id) or self.state.get_global_model()

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

    @channel.command(
        name="show",
        description="View current channel settings"
    )
    async def show(self, ctx):
        """Display channel-specific settings."""
        await ctx.defer()

        channel_id = str(ctx.channel.id)
        channel_model = self.state.get_channel_model(channel_id)
        channel_system = self.state.get_channel_system_prompt(channel_id)
        channel_provider = self.state.get_channel_provider(channel_id)

        # Get global settings for comparison
        global_model = self.state.get_global_model() or DEFAULT_MODEL
        global_provider = self.state.get_global_provider()

        embed = discord.Embed(
            title=f"⚙️ Settings for #{ctx.channel.name}",
            description="Channel-specific overrides",
            color=discord.Color.blue()
        )

        # Model info
        if channel_model:
            model_text = f"**Override:** `{channel_model}`\n_(Global: `{global_model}`)_"
        else:
            model_text = f"**Using Global:** `{global_model}`"

        embed.add_field(
            name="🤖 AI Model",
            value=model_text,
            inline=False
        )

        # Provider info
        if channel_provider and channel_provider != global_provider:
            provider_text = f"**Override:** `{channel_provider}`\n_(Global: `{global_provider}`)_"
        else:
            provider_text = f"**Using Global:** `{global_provider}`"

        embed.add_field(
            name="🔌 Provider",
            value=provider_text,
            inline=False
        )

        # System prompt info
        if channel_system:
            prompt_preview = channel_system[:100] + "..." if len(channel_system) > 100 else channel_system
            prompt_text = f"**Custom:** {prompt_preview}"
        else:
            prompt_text = "**Using Global**"

        embed.add_field(
            name="📝 System Prompt",
            value=prompt_text,
            inline=False
        )

        embed.set_footer(text="Use /channel reset to clear all overrides")

        await ctx.respond(embed=embed)

    @channel.command(
        name="model",
        description="Set AI model for this channel (format: provider/model)"
    )
    @commands.has_permissions(administrator=True)
    async def model(
        self,
        ctx,
        model_name: Option(str, "Select the AI model", autocomplete=model_autocomplete)
    ):
        """Set channel-specific AI model."""
        await ctx.defer()
        channel_id = str(ctx.channel.id)

        try:
            await self.state.set_channel_model(channel_id, model_name)
            await ctx.respond(f"✅ Model for #{ctx.channel.name} set to `{model_name}`")
        except ValueError as e:
            error_msg = str(e)
            if "not found" in error_msg and "/" not in model_name:
                error_msg += "\n\n💡 **Tip:** Use format `provider/model` (e.g., `openrouter/gpt-4`)"
            elif "not found" in error_msg:
                error_msg += "\n\n💡 **Tip:** Use autocomplete to see available models"
            await ctx.respond(f"⚠️ Error: {error_msg}", ephemeral=True)
        except Exception as e:
            logger.error(f"Unexpected error in /channel model: {e}", exc_info=True)
            await ctx.respond(
                f"❌ Unexpected error occurred.\n\n"
                f"Please contact an administrator or check `/admin diagnostic`.",
                ephemeral=True
            )

    @channel.command(
        name="system",
        description="Set custom system prompt for this channel"
    )
    @commands.has_permissions(administrator=True)
    async def system(self, ctx, prompt: str):
        """Set channel-specific system prompt."""
        await ctx.defer()
        channel_id = str(ctx.channel.id)

        try:
            self.state.set_channel_system_prompt(channel_id, prompt)

            # Handle long prompts by chunking
            max_length = 1950
            chunks = [prompt[i:i+max_length] for i in range(0, len(prompt), max_length)]

            await ctx.respond(f"✅ System prompt for #{ctx.channel.name} updated:\n```\n{chunks[0]}\n```")
            for chunk in chunks[1:]:
                await ctx.followup.send(f"```\n{chunk}\n```")
        except Exception as e:
            logger.error(f"Error setting channel system prompt: {e}", exc_info=True)
            await ctx.respond(f"❌ Error: {e}", ephemeral=True)

    @channel.command(
        name="provider",
        description="Set AI provider for this channel"
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
        """Set channel-specific AI provider."""
        await ctx.defer()
        channel_id = str(ctx.channel.id)

        try:
            await self.state.set_channel_provider(channel_id, provider_name)
            await ctx.respond(f"✅ Provider for #{ctx.channel.name} set to `{provider_name}`")
        except Exception as e:
            logger.error(f"Error setting channel provider: {e}", exc_info=True)
            await ctx.respond(f"❌ Error: {e}", ephemeral=True)

    @channel.command(
        name="reset",
        description="Clear all channel-specific overrides"
    )
    @commands.has_permissions(administrator=True)
    async def reset(self, ctx):
        """Reset channel to use global settings."""
        await ctx.defer()
        channel_id = str(ctx.channel.id)

        try:
            # Reset all channel config (model, provider, system prompt)
            was_reset = self.state.reset_channel_config(channel_id)

            if was_reset:
                await ctx.respond(
                    f"✅ Channel overrides cleared\n"
                    f"#{ctx.channel.name} will now use global settings."
                )
            else:
                await ctx.respond(f"ℹ️ #{ctx.channel.name} is already using global settings.")
        except Exception as e:
            logger.error(f"Error resetting channel: {e}", exc_info=True)
            await ctx.respond(f"❌ Error: {e}", ephemeral=True)

    @channel.command(
        name="list",
        description="List all channels with custom overrides"
    )
    @commands.has_permissions(administrator=True)
    async def list(self, ctx):
        """Display all channels with overrides."""
        await ctx.defer()

        # Get all channel configs from database
        channel_configs = self.state.get_all_channel_configs()

        if not channel_configs:
            await ctx.respond("ℹ️ No channels have custom overrides.")
            return

        embed = discord.Embed(
            title="📋 Channels with Custom Settings",
            description=f"Found {len(channel_configs)} channel(s) with overrides",
            color=discord.Color.green()
        )

        for config in sorted(channel_configs, key=lambda x: x['channel_id']):
            channel_id = config['channel_id']
            channel = self.bot.get_channel(int(channel_id))
            channel_name = channel.mention if channel else f"ID:{channel_id}"

            overrides = []
            if config.get('model'):
                overrides.append(f"Model: `{config['model']}`")
            if config.get('provider'):
                overrides.append(f"Provider: `{config['provider']}`")
            if config.get('system_prompt'):
                overrides.append("Custom system prompt")

            if overrides:  # Only add if there are actual overrides
                embed.add_field(
                    name=channel_name,
                    value="\n".join(overrides),
                    inline=False
                )

        embed.set_footer(text="Use /channel show in a channel to see its settings")

        await ctx.respond(embed=embed)


def setup(bot):
    bot.add_cog(ChannelCommands(bot))
