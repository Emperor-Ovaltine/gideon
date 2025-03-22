import discord
from discord.ext import commands
import asyncio
from ..utils.state_manager import BotStateManager
from ..utils.ai_horde_client import AIHordeClient
from ..config import AI_HORDE_API_KEY
import io
import aiohttp
import logging

logger = logging.getLogger('image_commands')

class ImageCommands(commands.Cog):
    """Commands for AI image generation."""
    
    def __init__(self, bot):
        self.bot = bot
        self.state = BotStateManager()
        self.horde_client = AIHordeClient(AI_HORDE_API_KEY)
        self._cached_models = None
        # Initialize with default models in case API is unavailable during startup
        self.available_models = ["stable_diffusion_2.1", "stable_diffusion_xl", "midjourney_diffusion", 
                               "deliberate_v2", "flux_1", "dream_shaper", "realistic_vision"]
        # Schedule the model fetch to run in the background
        bot.loop.create_task(self.initialize_model_choices())
    
    async def initialize_model_choices(self):
        """Fetch available models when the bot starts"""
        await self.bot.wait_until_ready()
        try:
            logger.info("Fetching available AI Horde models...")
            models = await self.get_model_choices()
            if models and len(models) > 0:
                self.available_models = models
                logger.info(f"Successfully loaded {len(models)} models from AI Horde")
            else:
                logger.warning("Failed to get models from AI Horde, using defaults")
        except Exception as e:
            logger.error(f"Error initializing model choices: {str(e)}")
    
    # Note: We can't directly use dynamic choices with slash command,
    # but we can use autocomplete instead - which is even better
    @discord.slash_command(
        name="imagine",
        description="Generate an image with AI using AI Horde"
    )
    async def imagine_slash(self, ctx, 
                           prompt: discord.Option(str, "Describe the image you want to create"),
                           negative_prompt: discord.Option(str, "What to exclude from the image", required=False) = "",
                           size: discord.Option(
                               str,
                               "Select image size",
                               choices=["512x512", "768x768", "512x768", "768x512"]
                           ) = "512x512",
                           steps: discord.Option(
                               int,
                               "Generation steps (higher needs more kudos)",
                               min_value=20,
                               max_value=50,
                               required=False
                           ) = 30,
                           model: discord.Option(
                               str, 
                               "Select AI model to use",
                               # Instead of fixed choices, use autocomplete
                               autocomplete=discord.utils.basic_autocomplete(lambda ctx: ImageCommands.model_autocomplete(ctx))
                           ) = "stable_diffusion_2.1"):
        # Parse the size string into width and height
        width, height = map(int, size.split('x'))
        
        # Ensure dimensions are multiples of 64 (AI Horde requirement)
        width = round(width / 64) * 64
        height = round(height / 64) * 64
        
        await ctx.defer()
        
        # Show a thinking message with estimated time warning
        thinking_msg = await ctx.respond(
            f"🎨 Generating: `{prompt}`\n\n*This may take 1-5 minutes with AI Horde. Please be patient...*"
        )
        
        # Update the message periodically to show it's still working
        progress_task = asyncio.create_task(self._update_progress(thinking_msg, prompt))
        
        try:
            # Call the AI Horde client
            result = await self.horde_client.generate_image(
                prompt=prompt,
                negative_prompt=negative_prompt,
                width=width,
                height=height,
                steps=steps,
                model=model
            )
            
            # Cancel the progress updates
            progress_task.cancel()
            
            if "error" in result:
                error_msg = result["error"]
                
                # Check if it's a kudos-related error
                if "kudos" in error_msg.lower() or "KudosUpfront" in error_msg:
                    await thinking_msg.edit(content=(
                        f"⚠️ AI Horde Kudos Error: {error_msg}\n\n"
                        "**Try these solutions:**\n"
                        "• Use a smaller image size (512×512)\n"
                        "• Reduce steps (try 20-30)\n"
                        "• Choose a different model\n"
                        "• Wait for available workers\n\n"
                        f"Original request: {width}x{height}, {steps} steps, model: {model}"
                    ))
                else:
                    await thinking_msg.edit(content=f"⚠️ Failed to generate image: {error_msg}")
                return
                
            if "image_url" in result:
                # Create embed with the image
                embed = discord.Embed(
                    title="Generated Image",
                    description=f"**Prompt:** {prompt}\n**Model:** {result.get('model', model)}\n**Seed:** {result.get('seed', 'unknown')}",
                    color=discord.Color.blue()
                )
                embed.set_image(url=result["image_url"])
                
                # Add negative prompt if it was provided
                if negative_prompt:
                    embed.add_field(name="Negative Prompt", value=negative_prompt)
                
                await thinking_msg.edit(content=None, embed=embed)
            else:
                await thinking_msg.edit(content=f"⚠️ Unexpected response format from AI Horde")
                
        except Exception as e:
            progress_task.cancel()
            await thinking_msg.edit(content=f"⚠️ Error generating image: {str(e)}")
    
    # Static method for autocomplete - can be called without instance
    @staticmethod
    async def model_autocomplete(ctx):
        # Get the cog instance
        cog = ctx.bot.get_cog("ImageCommands")
        if not cog:
            return ["stable_diffusion_2.1", "stable_diffusion_xl", "midjourney_diffusion"]
        
        # Get what the user has typed so far
        current_input = ctx.options.get("model", "").lower()
        
        if not current_input:
            # If user hasn't typed anything, return the top models
            return cog.available_models[:25]
        
        # Filter available models by what the user has typed
        matching_models = [
            model for model in cog.available_models 
            if current_input in model.lower()
        ]
        
        # Sort matching models to prioritize those that start with the input
        # This puts more relevant matches at the top
        priority_matches = []
        secondary_matches = []
        
        for model in matching_models:
            if model.lower().startswith(current_input):
                priority_matches.append(model)
            else:
                secondary_matches.append(model)
        
        # Combine and limit to 25 results
        filtered_models = (priority_matches + secondary_matches)[:25]
        
        # If no matches found, return the first 25 models anyway
        return filtered_models if filtered_models else cog.available_models[:25]
    
    async def _update_progress(self, message, prompt):
        """Updates the progress message periodically so the user knows we're still waiting."""
        dots = 1
        wait_time = 0
        try:
            while True:
                dot_str = "." * dots
                await message.edit(content=f"🎨 Generating: `{prompt}`\n\n*Waiting in AI Horde queue{dot_str} ({wait_time}s)*")
                dots = (dots % 3) + 1
                wait_time += 10
                await asyncio.sleep(10)
        except asyncio.CancelledError:
            # Task was cancelled, just exit
            pass
        except Exception as e:
            # Silently handle any errors with progress updates
            print(f"Error in progress updates: {str(e)}")
    
    @discord.slash_command(
        name="hordemodels",
        description="Show available models on AI Horde"
    )
    async def horde_models_slash(self, ctx, 
                                page: discord.Option(int, "Page number", required=False, default=1),
                                filter: discord.Option(str, "Filter models by name", required=False) = ""):
        await ctx.defer()
        
        try:
            result = await self.horde_client.get_available_models()
            
            if "error" in result:
                await ctx.respond(f"⚠️ Failed to get models: {result['error']}")
                return
            
            # Extract models from the response structure
            if "success" in result and result["success"]:
                models = result["models"]
                
                # Update our cached models list for the imagine command
                self.available_models = [m["name"] for m in models if m["count"] > 0]
            else:
                # Fallback for compatibility with old format (if API returns a list directly)
                models = result if isinstance(result, list) else []
            
            # Apply filter if provided
            if filter:
                filter = filter.lower()
                models = [m for m in models if filter in m["name"].lower()]
                
            # Sort by worker count (availability)
            models.sort(key=lambda x: x["count"], reverse=True)
            
            # Paginate results
            models_per_page = 10
            total_pages = max(1, (len(models) + models_per_page - 1) // models_per_page)
            page = min(max(1, page), total_pages)
            
            start_idx = (page - 1) * models_per_page
            end_idx = min(start_idx + models_per_page, len(models))
            page_models = models[start_idx:end_idx]
            
            # Create embed
            embed = discord.Embed(
                title="AI Horde Models",
                description=f"Showing {len(page_models)} of {len(models)} available models (page {page}/{total_pages})",
                color=discord.Color.blue()
            )
            
            if not page_models:
                embed.add_field(
                    name="No Results",
                    value="No models found matching your criteria",
                    inline=False
                )
            else:
                model_list = "\n".join([f"• **{m['name']}** - {m['count']} workers, {m['queued']} queued" 
                                    for m in page_models])
                
                embed.add_field(
                    name="Available Models",
                    value=model_list,
                    inline=False
                )
                
            # Add navigation instructions
            embed.set_footer(text=f"Use /hordemodels page:{page+1} to see more models" if page < total_pages else "End of list")
            
            await ctx.respond(embed=embed)
                
        except Exception as e:
            await ctx.respond(f"⚠️ Error: {str(e)}")
    
    async def get_model_choices(self):
        """Get available models for the choices dropdown"""
        try:
            result = await self.horde_client.get_available_models()
            if "error" not in result:
                # Get models with at least 1 worker available
                if "success" in result and result["success"]:
                    models = [m["name"] for m in result["models"] if m.get("count", 0) > 0]
                else:
                    # Old format
                    models = [m["name"] for m in result if m.get("count", 0) > 0]
                
                # Add popular models at the top if they exist
                popular_models = ["stable_diffusion_2.1", "stable_diffusion_xl", "midjourney_diffusion", "deliberate_v2"]
                sorted_models = [m for m in popular_models if m in models] + [m for m in models if m not in popular_models]
                
                # Store the full list - we'll filter it during autocomplete based on user input
                self._cached_models = sorted_models
                return sorted_models
            
            # Fallback to defaults if API fails
            return ["stable_diffusion_2.1", "stable_diffusion_xl", "midjourney_diffusion", "deliberate_v2", "flux_1"]
        except Exception as e:
            logger.error(f"Error fetching model choices: {str(e)}")
            # Return defaults in case of any error
            return ["stable_diffusion_2.1", "stable_diffusion_xl", "midjourney_diffusion", "deliberate_v2"]

def setup(bot):
    bot.add_cog(ImageCommands(bot))