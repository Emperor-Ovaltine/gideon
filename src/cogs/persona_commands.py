"""Per-channel persona management commands."""
import discord
import logging
from discord.ext import commands
from discord import Option
from ..utils.state_manager import BotStateManager

logger = logging.getLogger(__name__)


class PersonaCommands(commands.Cog, name="PersonaCommands"):
    """Commands for per-channel persona management."""

    def __init__(self, bot):
        self.bot = bot
        self.state = bot.state_manager

    persona = discord.SlashCommandGroup(
        "persona",
        "Per-channel persona settings (admin only)",
        default_member_permissions=discord.Permissions(administrator=True)
    )

    async def template_autocomplete(self, ctx):
        """Autocomplete for persona template names."""
        current_input = ctx.value.lower() if ctx.value else ""
        templates = self.state.get_all_persona_templates()
        choices = []
        for t in templates:
            label = f"{t['name']} ({t['display_name']})"
            if not current_input or current_input in label.lower():
                choices.append(label)
        return choices[:25]

    @persona.command(name="show", description="View the active persona for this channel")
    async def show(self, ctx):
        """Display the persona configured for the current channel."""
        await ctx.defer(ephemeral=True)
        channel_id = str(ctx.channel.id)
        persona = self.state.get_channel_persona(channel_id)

        if not persona:
            await ctx.respond("No persona configured for this channel. Use `/persona set` or `/persona template` to configure one.")
            return

        embed = discord.Embed(
            title=f"Persona for #{ctx.channel.name}",
            color=discord.Color.purple()
        )
        embed.add_field(name="Display Name", value=persona['display_name'], inline=True)
        embed.add_field(name="Active", value="Yes" if persona.get('is_active') else "No", inline=True)

        if persona.get('template_id'):
            template = self.state.get_persona_template(persona['template_id'])
            template_name = template['name'] if template else persona['template_id']
            embed.add_field(name="Template", value=template_name, inline=True)

        if persona.get('avatar_url'):
            embed.set_thumbnail(url=persona['avatar_url'])
            embed.add_field(name="Avatar URL", value=persona['avatar_url'][:100], inline=False)

        if persona.get('system_prompt'):
            prompt_preview = persona['system_prompt'][:200]
            if len(persona['system_prompt']) > 200:
                prompt_preview += "..."
            embed.add_field(name="System Prompt", value=prompt_preview, inline=False)

        if persona.get('model'):
            embed.add_field(name="Model Override", value=f"`{persona['model']}`", inline=True)
        if persona.get('provider'):
            embed.add_field(name="Provider Override", value=f"`{persona['provider']}`", inline=True)

        webhook_status = "Configured" if persona.get('webhook_id') else "Will be created on first message"
        embed.add_field(name="Webhook", value=webhook_status, inline=False)

        embed.set_footer(text="Use /persona remove to clear, /persona toggle to enable/disable")
        await ctx.respond(embed=embed)

    @persona.command(name="set", description="Set a custom persona for this channel")
    @commands.has_permissions(administrator=True)
    async def set(
        self,
        ctx,
        display_name: Option(str, "Display name for the persona (shown in Discord)"),
        avatar_url: Option(str, "URL to avatar image (must be public HTTP/HTTPS URL)", required=False, default=None),
        system_prompt: Option(str, "Custom system prompt for this persona", required=False, default=None),
    ):
        """Set a custom persona for the current channel."""
        await ctx.defer(ephemeral=True)
        channel_id = str(ctx.channel.id)

        # Validate display name
        if len(display_name) < 1 or len(display_name) > 80:
            await ctx.respond("Display name must be between 1 and 80 characters.")
            return

        # Validate avatar URL
        if avatar_url and not (avatar_url.startswith('http://') or avatar_url.startswith('https://')):
            await ctx.respond("Avatar URL must be a valid HTTP or HTTPS URL.")
            return

        try:
            self.state.set_channel_persona(
                channel_id,
                display_name=display_name,
                avatar_url=avatar_url,
                system_prompt=system_prompt,
            )

            # Invalidate webhook cache for this channel
            if hasattr(self.bot, 'webhook_sender'):
                self.bot.webhook_sender.invalidate_cache(channel_id)

            embed = discord.Embed(
                title="Persona Set",
                description=f"Persona **{display_name}** configured for #{ctx.channel.name}",
                color=discord.Color.green()
            )
            if avatar_url:
                embed.set_thumbnail(url=avatar_url)
            if system_prompt:
                prompt_preview = system_prompt[:100] + "..." if len(system_prompt) > 100 else system_prompt
                embed.add_field(name="System Prompt", value=prompt_preview, inline=False)

            await ctx.respond(embed=embed)
        except Exception as e:
            logger.error(f"Error setting persona: {e}", exc_info=True)
            await ctx.respond(f"Error setting persona: {e}")

    @persona.command(name="template", description="Apply a persona template to this channel")
    @commands.has_permissions(administrator=True)
    async def template(
        self,
        ctx,
        template_name: Option(str, "Select a persona template", autocomplete=template_autocomplete),
    ):
        """Apply a persona template to the current channel."""
        await ctx.defer(ephemeral=True)
        channel_id = str(ctx.channel.id)

        # Find template by matching the autocomplete format "Name (DisplayName)"
        templates = self.state.get_all_persona_templates()
        matched_template = None
        for t in templates:
            label = f"{t['name']} ({t['display_name']})"
            if label == template_name or t['name'].lower() == template_name.lower() or t['template_id'] == template_name:
                matched_template = t
                break

        if not matched_template:
            available = ", ".join(t['name'] for t in templates)
            await ctx.respond(f"Template not found. Available templates: {available}")
            return

        try:
            self.state.set_channel_persona(
                channel_id,
                display_name=matched_template['display_name'],
                avatar_url=matched_template.get('avatar_url'),
                system_prompt=matched_template.get('system_prompt'),
                model=matched_template.get('model'),
                provider=matched_template.get('provider'),
                response_style=matched_template.get('response_style'),
                template_id=matched_template['template_id'],
            )

            if hasattr(self.bot, 'webhook_sender'):
                self.bot.webhook_sender.invalidate_cache(channel_id)

            embed = discord.Embed(
                title="Template Applied",
                description=f"**{matched_template['name']}** persona applied to #{ctx.channel.name}",
                color=discord.Color.green()
            )
            embed.add_field(name="Display Name", value=matched_template['display_name'], inline=True)
            if matched_template.get('description'):
                embed.add_field(name="Description", value=matched_template['description'], inline=False)
            if matched_template.get('avatar_url'):
                embed.set_thumbnail(url=matched_template['avatar_url'])

            await ctx.respond(embed=embed)
        except Exception as e:
            logger.error(f"Error applying template: {e}", exc_info=True)
            await ctx.respond(f"Error applying template: {e}")

    @persona.command(name="remove", description="Remove persona from this channel")
    @commands.has_permissions(administrator=True)
    async def remove(self, ctx):
        """Remove the persona from the current channel."""
        await ctx.defer(ephemeral=True)
        channel_id = str(ctx.channel.id)

        removed = self.state.remove_channel_persona(channel_id)
        if hasattr(self.bot, 'webhook_sender'):
            self.bot.webhook_sender.invalidate_cache(channel_id)

        if removed:
            await ctx.respond(f"Persona removed from #{ctx.channel.name}. Bot will use its default identity.")
        else:
            await ctx.respond(f"No persona was configured for #{ctx.channel.name}.")

    @persona.command(name="toggle", description="Enable or disable persona without removing it")
    @commands.has_permissions(administrator=True)
    async def toggle(self, ctx):
        """Toggle the persona active state."""
        await ctx.defer(ephemeral=True)
        channel_id = str(ctx.channel.id)

        new_state = self.state.toggle_channel_persona(channel_id)
        if new_state is None:
            await ctx.respond(f"No persona configured for #{ctx.channel.name}. Use `/persona set` first.")
            return

        if hasattr(self.bot, 'webhook_sender'):
            self.bot.webhook_sender.invalidate_cache(channel_id)

        status = "enabled" if new_state else "disabled"
        await ctx.respond(f"Persona for #{ctx.channel.name} is now **{status}**.")

    @persona.command(name="templates", description="List all available persona templates")
    async def templates(self, ctx):
        """List all available persona templates."""
        await ctx.defer(ephemeral=True)

        templates = self.state.get_all_persona_templates()
        if not templates:
            await ctx.respond("No persona templates available.")
            return

        embed = discord.Embed(
            title="Persona Templates",
            description=f"{len(templates)} template(s) available",
            color=discord.Color.purple()
        )

        for t in templates:
            builtin_tag = " [Built-in]" if t.get('is_builtin') else ""
            value_parts = [f"Display Name: **{t['display_name']}**"]
            if t.get('description'):
                value_parts.append(t['description'])
            if t.get('model'):
                value_parts.append(f"Model: `{t['model']}`")

            embed.add_field(
                name=f"{t['name']}{builtin_tag}",
                value="\n".join(value_parts),
                inline=False
            )

        embed.set_footer(text="Use /persona template <name> to apply a template to this channel")
        await ctx.respond(embed=embed)

    @persona.command(name="list", description="List all channels with active personas")
    @commands.has_permissions(administrator=True)
    async def list(self, ctx):
        """List all channels with configured personas."""
        await ctx.defer(ephemeral=True)

        personas = self.state.get_all_channel_personas()
        if not personas:
            await ctx.respond("No channels have personas configured.")
            return

        embed = discord.Embed(
            title="Channel Personas",
            description=f"{len(personas)} channel(s) with personas",
            color=discord.Color.purple()
        )

        for p in personas:
            channel = self.bot.get_channel(int(p['channel_id']))
            channel_name = channel.mention if channel else f"ID:{p['channel_id']}"
            status = "Active" if p.get('is_active') else "Inactive"
            template_info = f" (from: {p.get('template_name', 'custom')})" if p.get('template_name') else ""

            embed.add_field(
                name=channel_name,
                value=f"**{p['display_name']}**{template_info}\nStatus: {status}",
                inline=False
            )

        await ctx.respond(embed=embed)

    @persona.command(name="preview", description="Send a test message using the channel persona")
    @commands.has_permissions(administrator=True)
    async def preview(self, ctx):
        """Send a test webhook message with the current persona."""
        await ctx.defer(ephemeral=True)
        channel_id = str(ctx.channel.id)

        persona = self.state.get_effective_persona(channel_id)
        if not persona:
            await ctx.respond("No active persona for this channel. Configure one with `/persona set` or `/persona template` first.")
            return

        if not hasattr(self.bot, 'webhook_sender'):
            await ctx.respond("Webhook sender not initialized.")
            return

        try:
            msg = await self.bot.webhook_sender.send_response(
                ctx.channel,
                f"Hello! I'm **{persona['display_name']}**, the persona for this channel. This is a preview message.",
                channel_id,
            )
            if msg:
                await ctx.respond("Preview message sent! Check the channel.")
            else:
                await ctx.respond("Preview sent via fallback (standard bot account). Check webhook permissions.")
        except Exception as e:
            logger.error(f"Error sending preview: {e}", exc_info=True)
            await ctx.respond(f"Error sending preview: {e}")


def setup(bot):
    bot.add_cog(PersonaCommands(bot))
