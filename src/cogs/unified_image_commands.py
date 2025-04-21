import discord
from discord.ext import commands
from discord import option # Use discord.option for type hinting
import asyncio
import json
import logging
from typing import Optional, Literal, Dict, Any

# Import clients and config
from ..utils.ai_horde_client import AIHordeClient
from ..utils.cloudflare_client import CloudflareWorkerClient
from ..utils.openai_client import OpenAIClient
from ..utils.database import DatabaseManager
from ..config import (
    AI_HORDE_API_KEY,
    CLOUDFLARE_WORKER_URL,
    CLOUDFLARE_API_KEY,
    OPENAI_API_KEY,
    DATA_DIRECTORY # Needed for DatabaseManager default path
)

# Configure logging
logger = logging.getLogger('unified_image_commands')

# Define provider types for clarity
ProviderType = Literal['ai_horde', 'cloudflare', 'openai']

# Database keys
DB_KEY_ACTIVE_PROVIDER = "image_active_provider"
DB_KEY_CONFIG_PREFIX = "image_config_" # e.g., image_config_openai

# Default configurations (used if nothing is set in DB)
DEFAULT_PROVIDER: ProviderType = 'ai_horde'
DEFAULT_CONFIGS: Dict[ProviderType, Dict[str, Any]] = {
    'ai_horde': {
        "model": "stable_diffusion_xl",
        "size": "1024x1024",
        "steps": 30
    },
    'cloudflare': {
        "size": "768x768",
        "steps": 25,
        "seed": None # Let CF client handle random seed if None
    },
    'openai': {
        "model": "dall-e-3",
        "size": "1024x1024", # Fixed for OpenAI in this implementation
        "quality": "standard",
        "style": "vivid"
    }
}

class UnifiedImageCommands(commands.Cog):
    """Unified command for AI image generation with backend management."""

    def __init__(self, bot):
        self.bot = bot
        self.db = DatabaseManager() # Assumes default DB path is okay

        # Initialize clients (only if API keys/URLs are provided)
        self.horde_client = AIHordeClient(AI_HORDE_API_KEY) if AI_HORDE_API_KEY else None
        self.cf_client = CloudflareWorkerClient(CLOUDFLARE_WORKER_URL, CLOUDFLARE_API_KEY) if CLOUDFLARE_WORKER_URL else None
        self.openai_client = OpenAIClient(OPENAI_API_KEY) if OPENAI_API_KEY else None

        # Log which clients are available
        if not self.horde_client: logger.warning("AI Horde client not initialized (API key missing).")
        if not self.cf_client: logger.warning("Cloudflare client not initialized (Worker URL missing).")
        if not self.openai_client: logger.warning("OpenAI client not initialized (API key missing).")

    # --- User Command ---

    @discord.slash_command(
        name="dream",
        description="Generate an image using the configured AI backend."
    )
    @option("prompt", str, description="Describe the image you want to create.", required=True)
    @option("negative_prompt", str, description="What to exclude from the image (if supported).", required=False, default=None)
    async def dream(self, ctx: discord.ApplicationContext, prompt: str, negative_prompt: Optional[str]):
        await ctx.defer()

        # 1. Get active provider from DB
        active_provider: ProviderType = self.db.get_global_config(DB_KEY_ACTIVE_PROVIDER, DEFAULT_PROVIDER)

        # 2. Get provider config from DB
        config_key = f"{DB_KEY_CONFIG_PREFIX}{active_provider}"
        config_json = self.db.get_global_config(config_key)
        provider_config = {}
        if config_json:
            try:
                provider_config = json.loads(config_json)
            except json.JSONDecodeError:
                logger.error(f"Failed to parse config JSON for {active_provider} from DB. Using defaults.")
                provider_config = DEFAULT_CONFIGS.get(active_provider, {})
        else:
            # Use hardcoded defaults if nothing in DB
            provider_config = DEFAULT_CONFIGS.get(active_provider, {})

        # Ensure all expected keys from defaults are present
        default_provider_config = DEFAULT_CONFIGS.get(active_provider, {})
        for key, value in default_provider_config.items():
            provider_config.setdefault(key, value)


        # 3. Select client and prepare parameters
        client = None
        params = {"prompt": prompt}
        provider_display_name = "Unknown"

        if active_provider == 'ai_horde':
            client = self.horde_client
            provider_display_name = "AI Horde"
            if client:
                width, height = map(int, provider_config.get("size", "512x512").split('x'))
                params.update({
                    "negative_prompt": negative_prompt,
                    "width": round(width / 64) * 64, # Ensure multiple of 64
                    "height": round(height / 64) * 64,
                    "steps": provider_config.get("steps", 30),
                    "model": provider_config.get("model", "stable_diffusion_xl")
                })
            else:
                await ctx.respond("⚠️ AI Horde client is not configured (missing API key). Please contact an admin.", ephemeral=True)
                return

        elif active_provider == 'cloudflare':
            client = self.cf_client
            provider_display_name = "Cloudflare"
            if client:
                width, height = map(int, provider_config.get("size", "768x768").split('x'))
                params.update({
                    "negative_prompt": negative_prompt,
                    "width": width,
                    "height": height,
                    "steps": provider_config.get("steps", 25),
                    "seed": provider_config.get("seed") # Can be None
                })
            else:
                await ctx.respond("⚠️ Cloudflare client is not configured (missing Worker URL). Please contact an admin.", ephemeral=True)
                return

        elif active_provider == 'openai':
            client = self.openai_client
            provider_display_name = "OpenAI"
            if client:
                # OpenAI size is fixed in this plan, but we read model/quality/style
                params.update({
                    "model": provider_config.get("model", "dall-e-3"),
                    "size": "1024x1024", # Enforce size
                    "quality": provider_config.get("quality") if provider_config.get("model") == "dall-e-3" else None,
                    "style": provider_config.get("style") if provider_config.get("model") == "dall-e-3" else None
                })
                # OpenAI doesn't support negative_prompt directly
                if negative_prompt:
                    # Optionally append to prompt or just log a warning
                    logger.info(f"Negative prompt '{negative_prompt}' provided for OpenAI, which doesn't support it directly. Ignoring.")
                    # params["prompt"] += f". Avoid: {negative_prompt}" # Basic workaround - uncomment if desired
            else:
                await ctx.respond("⚠️ OpenAI client is not configured (missing API key). Please contact an admin.", ephemeral=True)
                return

        else:
            await ctx.respond(f"⚠️ Unknown or unsupported image provider configured: '{active_provider}'. Please contact an admin.", ephemeral=True)
            return

        # 4. Call the client's generate_image method
        thinking_msg = await ctx.followup.send(f"🎨 Generating image with **{provider_display_name}**: `{prompt}`\n*Please wait...*")

        try:
            result = await client.generate_image(**params)

            # 5. Format and send response
            if result.get("success"):
                embed = discord.Embed(
                    title="Generated Image",
                    description=f"**Prompt:** {prompt}",
                    color=discord.Color.blue() # Or provider-specific color
                )
                if negative_prompt and active_provider != 'openai': # Show negative if provided and supported
                     embed.add_field(name="Negative Prompt", value=negative_prompt, inline=False)

                footer_parts = [f"Provider: {provider_display_name}"]
                if result.get("model_used"): footer_parts.append(f"Model: {result.get('model_used')}")
                if result.get("seed"): footer_parts.append(f"Seed: {result.get('seed')}")
                if params.get("steps"): footer_parts.append(f"Steps: {params.get('steps')}")
                if params.get("size"): footer_parts.append(f"Size: {params.get('size')}")
                elif params.get("width"): footer_parts.append(f"Size: {params.get('width')}x{params.get('height')}")

                embed.set_footer(text=" | ".join(footer_parts))

                if result.get("revised_prompt"):
                    embed.add_field(name="Revised Prompt (DALL-E 3)", value=result["revised_prompt"], inline=False)

                if "image_url" in result:
                    embed.set_image(url=result["image_url"])
                    await thinking_msg.edit(content=None, embed=embed)
                elif "local_path" in result: # Handle direct image data from Cloudflare if needed
                    file = discord.File(result["local_path"], filename="generated_image.png")
                    embed.set_image(url=f"attachment://generated_image.png")
                    await thinking_msg.edit(content=None, embed=embed, file=file)
                else:
                     await thinking_msg.edit(content="⚠️ Generation succeeded but no image URL or data found in response.")

            else:
                error_msg = result.get("error", "Unknown error")
                # Specific error handling (e.g., AI Horde Kudos) can be added here if needed
                await thinking_msg.edit(content=f"⚠️ Failed to generate image via {provider_display_name}: {error_msg}")

        except Exception as e:
            logger.exception(f"Error during image generation with {active_provider}: {e}")
            await thinking_msg.edit(content=f"⚠️ An unexpected error occurred while generating the image: {str(e)}")


    # --- Admin Commands (Group Definition) ---

    manage = discord.SlashCommandGroup(
        "dream_manage",
        "Manage image generation backend settings (Admin Only)"
        # Permissions will be applied to each subcommand individually
    )

    # Define subcommands attached to the group
    @manage.command(name="set_provider", description="Set the active image generation provider.")
    @commands.has_permissions(administrator=True) # Re-enabled permission check
    @option("provider", description="Choose the backend provider.", choices=[
        discord.OptionChoice(name="AI Horde", value="ai_horde"),
        discord.OptionChoice(name="Cloudflare", value="cloudflare"),
        discord.OptionChoice(name="OpenAI", value="openai")
    ], required=True)
    async def manage_set_provider(self, ctx: discord.ApplicationContext, provider: str): # Changed ProviderType to str
        """Sets the active image generation provider."""
        # Check if the selected provider's client is initialized
        valid_provider = False
        if provider == 'ai_horde' and self.horde_client: valid_provider = True
        elif provider == 'cloudflare' and self.cf_client: valid_provider = True
        elif provider == 'openai' and self.openai_client: valid_provider = True

        if not valid_provider:
             await ctx.respond(f"⚠️ Cannot set provider to '{provider}'. Its client is not configured/initialized (missing API key/URL?).", ephemeral=True)
             return

        try:
            self.db.set_global_config(DB_KEY_ACTIVE_PROVIDER, provider, 'string') # Added back with correct type string
            await ctx.respond(f"✅ Image generation provider set to: **{provider}**", ephemeral=True)
            logger.info(f"Admin {ctx.author} set image provider to {provider}")
        except Exception as e:
            logger.error(f"Failed to set image provider in DB: {e}")
            await ctx.respond(f"❌ Failed to save provider setting to database: {e}", ephemeral=True)

    @manage.command(name="view_config", description="View the current image generation configuration.")
    @commands.has_permissions(administrator=True) # Re-enabled permission check
    async def manage_view_config(self, ctx: discord.ApplicationContext):
        """Displays the current image generation configuration."""
        active_provider = self.db.get_global_config(DB_KEY_ACTIVE_PROVIDER, DEFAULT_PROVIDER)

        embed = discord.Embed(title="Image Generation Configuration", color=discord.Color.orange())
        embed.add_field(name="Active Provider", value=f"**{active_provider}**", inline=False)

        for provider_name in ProviderType.__args__: # Use provider_name to avoid conflict
            config_key = f"{DB_KEY_CONFIG_PREFIX}{provider_name}"
            config_json = self.db.get_global_config(config_key)
            config_display = "Not Set (Using Defaults)"
            if config_json:
                try:
                    config_data = json.loads(config_json)
                    config_display = f"```json\n{json.dumps(config_data, indent=2)}\n```"
                except json.JSONDecodeError:
                    config_display = f"Error parsing stored JSON: `{config_json}`"
            else:
                 default_conf = DEFAULT_CONFIGS.get(provider_name, {})
                 config_display = f"*Using Defaults:*\n```json\n{json.dumps(default_conf, indent=2)}\n```"

            embed.add_field(name=f"⚙️ {provider_name.capitalize()} Config", value=config_display, inline=False)

        await ctx.respond(embed=embed, ephemeral=True)

    # Define the subgroup directly from the main group
    configure = manage.create_subgroup("configure", "Configure default settings for a provider.")
    # Group permissions apply to commands within the subgroup

    # Define commands attached to the subgroup
    @configure.command(name="ai_horde", description="Configure AI Horde default settings.")
    @commands.has_permissions(administrator=True) # Re-enabled permission check
    @option("model", str, description="Default model name (e.g., stable_diffusion_xl).", required=True)
    @option("size", str, description="Default image size.", choices=[
        discord.OptionChoice(name="512x512", value="512x512"),
        discord.OptionChoice(name="768x768", value="768x768"),
        discord.OptionChoice(name="1024x1024", value="1024x1024"),
        discord.OptionChoice(name="512x768", value="512x768"),
        discord.OptionChoice(name="768x512", value="768x512"),
        discord.OptionChoice(name="1024x768", value="1024x768"),
        discord.OptionChoice(name="768x1024", value="768x1024")
    ], required=True)
    @option("steps", int, description="Default generation steps (e.g., 30).", min_value=10, max_value=100, required=True)
    async def configure_ai_horde(self, ctx: discord.ApplicationContext, model: str, size: str, steps: int):
        """Configures default settings for the AI Horde provider."""
        config = {"model": model, "size": size, "steps": steps}
        await self._save_provider_config(ctx, 'ai_horde', config)

    @configure.command(name="cloudflare", description="Configure Cloudflare default settings.")
    @commands.has_permissions(administrator=True) # Re-enabled permission check
    @option("size", str, description="Default image size.", choices=[
        discord.OptionChoice(name="256x256", value="256x256"),
        discord.OptionChoice(name="512x512", value="512x512"),
        discord.OptionChoice(name="768x768", value="768x768"),
        discord.OptionChoice(name="1024x1024", value="1024x1024"),
        discord.OptionChoice(name="512x768", value="512x768"),
        discord.OptionChoice(name="768x512", value="768x512"),
        discord.OptionChoice(name="1024x768", value="1024x768"),
        discord.OptionChoice(name="768x1024", value="768x1024")
    ], required=True)
    @option("steps", int, description="Default generation steps (e.g., 25).", min_value=10, max_value=50, required=True)
    @option("seed", int, description="Default seed (optional, leave blank for random).", required=False, default=None)
    async def configure_cloudflare(self, ctx: discord.ApplicationContext, size: str, steps: int, seed: Optional[int]):
        """Configures default settings for the Cloudflare provider."""
        config = {"size": size, "steps": steps, "seed": seed}
        # Remove seed if None for cleaner storage, although None is valid JSON
        config = {k: v for k, v in config.items() if v is not None}
        await self._save_provider_config(ctx, 'cloudflare', config)

    @configure.command(name="openai", description="Configure OpenAI default settings.")
    @commands.has_permissions(administrator=True) # Re-enabled permission check
    @option("model", description="Default OpenAI model.", choices=[
        discord.OptionChoice(name="DALL-E 3", value="dall-e-3"),
        discord.OptionChoice(name="DALL-E 2", value="dall-e-2")
    ], required=True)
    @option("quality", description="Default quality (DALL-E 3 only).", type=str, choices=[ # Added type=str
        discord.OptionChoice(name="Standard", value="standard"),
        discord.OptionChoice(name="HD", value="hd")
    ], required=False, default=None) # Default None, let user choose standard/hd explicitly
    @option("style", description="Default style (DALL-E 3 only).", type=str, choices=[ # Added type=str
        discord.OptionChoice(name="Vivid", value="vivid"),
        discord.OptionChoice(name="Natural", value="natural")
    ], required=False, default=None) # Default None
    async def configure_openai(self, ctx: discord.ApplicationContext, model: str, quality: Optional[str], style: Optional[str]): # Changed Literals to str/Optional[str]
        """Configures default settings for the OpenAI provider."""
        config = {
            "model": model,
            "size": "1024x1024", # Size is fixed for OpenAI in this plan
            "quality": quality if model == 'dall-e-3' else None,
            "style": style if model == 'dall-e-3' else None
        }
        # Remove None values for cleaner storage
        config = {k: v for k, v in config.items() if v is not None}
        await self._save_provider_config(ctx, 'openai', config)


    async def _save_provider_config(self, ctx: discord.ApplicationContext, provider: ProviderType, config: Dict[str, Any]):
        """Helper function to save provider config JSON to the database."""
        config_key = f"{DB_KEY_CONFIG_PREFIX}{provider}"
        try:
            config_json = json.dumps(config)
            self.db.set_global_config(config_key, config_json, 'json') # Store as JSON string
            await ctx.respond(f"✅ Default configuration saved for **{provider}**:\n```json\n{json.dumps(config, indent=2)}\n```", ephemeral=True)
            logger.info(f"Admin {ctx.author} updated config for {provider}: {config_json}")
        except json.JSONDecodeError:
             await ctx.respond(f"❌ Internal error: Failed to serialize configuration to JSON.", ephemeral=True)
        except Exception as e:
            logger.error(f"Failed to save config for {provider} to DB: {e}")
            await ctx.respond(f"❌ Failed to save configuration to database: {e}", ephemeral=True)


def setup(bot):
    # Ensure DatabaseManager is initialized before adding cog if it relies on it heavily at init
    # (In this case, DB is initialized within the cog's __init__)
    bot.add_cog(UnifiedImageCommands(bot))
    logger.info("UnifiedImageCommands cog loaded.")