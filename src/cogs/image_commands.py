import discord
from discord.ext import commands
import asyncio
from ..utils.state_manager import BotStateManager
from ..utils.ai_horde_client import AIHordeClient
from ..config import AI_HORDE_API_KEY
import io
import aiohttp

class ImageCommands(commands.Cog):
    """Commands for AI image generation."""
    
    def __init__(self, bot):
        self.bot = bot
        self.state = BotStateManager()
        self.horde_client = AIHordeClient(AI_HORDE_API_KEY)
    
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
                           model: discord.Option(
                               str, 
                               "Select AI model to use",
                               choices=["stable_diffusion_2.1", "stable_diffusion_xl", "midjourney_diffusion", "deliberate_v2", "flux_1"]
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
                model=model
            )
            
            # Cancel the progress updates
            progress_task.cancel()
            
            if "error" in result:
                await thinking_msg.edit(content=f"⚠️ Failed to generate image: {result['error']}")
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
    async def horde_models_slash(self, ctx):
        await ctx.defer()
        
        try:
            result = await self.horde_client.get_available_models()
            
            if "error" in result:
                await ctx.respond(f"⚠️ Failed to get models: {result['error']}")
                return
            
            # Process the models list
            stable_diffusion_models = []
            for model in result:
                if model.get("type") == "image" and not model.get("unavailable", False):
                    stable_diffusion_models.append({
                        "name": model.get("name"),
                        "count": model.get("count", 0),
                        "performance": model.get("performance", "unknown"),
                        "queued": model.get("queued", 0)
                    })
            
            # Sort by worker count (availability)
            stable_diffusion_models.sort(key=lambda x: x["count"], reverse=True)
            
            # Create embed with the top models
            embed = discord.Embed(
                title="Available AI Horde Models",
                description="These models are currently available for image generation:",
                color=discord.Color.blue()
            )
            
            # Show top 15 models by availability
            top_models = stable_diffusion_models[:15]
            model_list = "\n".join([f"• **{m['name']}** - {m['count']} workers, {m['queued']} queued" 
                                   for m in top_models])
            
            embed.add_field(
                name="Top Models by Availability",
                value=model_list if model_list else "No models available",
                inline=False
            )
            
            await ctx.respond(embed=embed)
                
        except Exception as e:
            await ctx.respond(f"⚠️ Error: {str(e)}")

def setup(bot):
    bot.add_cog(ImageCommands(bot))