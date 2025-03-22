"""Commands for generating images using Cloudflare Worker API."""
import discord
from discord.ext import commands
import asyncio
import random
import json
from typing import Optional
import logging
import os
from ..utils.state_manager import BotStateManager
from ..utils.cloudflare_client import CloudflareWorkerClient

# Configure logging
logger = logging.getLogger('cloudflare_images')

# Load from environment
CLOUDFLARE_WORKER_URL = os.environ.get("CLOUDFLARE_WORKER_URL", "https://image-generator.example.workers.dev")
CLOUDFLARE_API_KEY = os.environ.get("CLOUDFLARE_API_KEY")  # Optional, if your worker requires authentication

class CloudflareImageCommands(commands.Cog):
    """Commands for AI image generation using Cloudflare Workers."""
    
    def __init__(self, bot):
        self.bot = bot
        self.state = BotStateManager()
        self.cf_client = CloudflareWorkerClient(CLOUDFLARE_WORKER_URL, CLOUDFLARE_API_KEY)
    
    @discord.slash_command(
        name="dream",
        description="Generate an image with flux1 schnell model via Cloudflare"
    )
    async def dream_slash(self, ctx, 
                        prompt: discord.Option(str, "Describe the image you want to create"),
                        negative_prompt: discord.Option(str, "What to exclude from the image", required=False) = "",
                        size: discord.Option(
                            str,
                            "Select image size",
                            choices=["768x768", "512x512", "768x512", "512x768"]
                        ) = "768x768",
                        steps: discord.Option(
                            int,
                            "Generation steps (higher = more detail but slower)",
                            min_value=15,
                            max_value=50,
                            required=False
                        ) = 25,
                        seed: discord.Option(
                            int,
                            "Random seed for reproducibility (leave empty for random)",
                            required=False
                        ) = None):
        
        # Parse the size string into width and height
        width, height = map(int, size.split('x'))
        
        # Generate random seed if not provided
        if seed is None:
            seed = random.randint(0, 2147483647)
            
        await ctx.defer()
        
        # Show a thinking message
        thinking_msg = await ctx.respond(
            f"✨ Dreaming: `{prompt}`\n\n*Generating image with flux1 schnell model...*"
        )
        
        # Update the message periodically to show it's still working
        progress_task = asyncio.create_task(self._update_progress(thinking_msg, prompt))
        
        try:
            # Call the Cloudflare Worker client
            result = await self.cf_client.generate_image(
                prompt=prompt,
                negative_prompt=negative_prompt,
                width=width,
                height=height,
                steps=steps,
                seed=seed
            )
            
            # Cancel the progress updates
            progress_task.cancel()
            
            if "error" in result:
                error_msg = result["error"]
                await thinking_msg.edit(content=f"⚠️ Failed to generate image: {error_msg}")
                return
                
            if ("image_url" in result and result.get("success", False)) or ("image_data" in result and result.get("success", False)):
                # Create embed with the image
                embed = discord.Embed(
                    title="Generated Image",
                    description=f"**Prompt:** {prompt}\n**Model:** flux1 schnell\n**Seed:** {result.get('seed', seed)}",
                    color=discord.Color.purple()
                )
                
                if "image_url" in result:
                    embed.set_image(url=result["image_url"])
                elif "local_path" in result:
                    # For binary image responses, we can inform but can't display directly
                    file = discord.File(result["local_path"], filename="generated_image.jpg")
                    embed.set_image(url=f"attachment://generated_image.jpg")
                    await thinking_msg.edit(content=None, embed=embed, file=file)
                    return
                
                # Add negative prompt if it was provided
                if negative_prompt:
                    embed.add_field(name="Negative Prompt", value=negative_prompt)
                    
                embed.set_footer(text=f"Size: {width}x{height} | Steps: {steps}")
                
                await thinking_msg.edit(content=None, embed=embed)
            else:
                await thinking_msg.edit(content=f"⚠️ Unexpected response format from Cloudflare Worker")
                
        except Exception as e:
            progress_task.cancel()
            logger.error(f"Error in dream command: {str(e)}")
            await thinking_msg.edit(content=f"⚠️ Error generating image: {str(e)}")
    
    @discord.slash_command(
        name="cftest",
        description="Test connection to Cloudflare Worker"
    )
    async def cf_test_slash(self, ctx):
        await ctx.defer()
        await ctx.respond("Testing connection to Cloudflare Worker...")
        result = await self.cf_client.test_connection("a blue sky")
        if result.get("success", False):
            embed = discord.Embed(
                title="✅ Cloudflare Worker Connection Successful",
                description=f"Connected to: `{self.cf_client.api_url}`",
                color=discord.Color.green()
            )
            if result.get("result_type") == "json":
                embed.add_field(
                    name="Response Type", 
                    value="JSON data", 
                    inline=False
                )
                embed.add_field(
                    name="Response Data", 
                    value=f"```json\n{json.dumps(result.get('data', {}), indent=2)[:1000]}\n```", 
                    inline=False
                )
            elif result.get("result_type") == "binary_image":
                embed.add_field(
                    name="Response Type", 
                    value=f"Direct image data ({result.get('size', 0)} bytes)", 
                    inline=False
                )
                embed.add_field(
                    name="Worker Status", 
                    value="✅ Worker is returning images directly as binary data", 
                    inline=False
                )
            else:
                embed.add_field(
                    name="Response Type", 
                    value=f"{result.get('result_type', 'unknown')}", 
                    inline=False
                )
                embed.add_field(
                    name="Content Type", 
                    value=f"`{result.get('content_type', 'unspecified')}`", 
                    inline=False
                )
            await ctx.followup.send(embed=embed)
        else:
            embed = discord.Embed(
                title="❌ Cloudflare Worker Connection Failed",
                description=f"Error connecting to: `{self.cf_client.api_url}`",
                color=discord.Color.red()
            )
            embed.add_field(
                name="Error Details", 
                value=result.get("error", "Unknown error"), 
                inline=False
            )
            embed.add_field(
                name="Recommended Actions",
                value="• Verify the worker URL in your .env file\n• Check that your worker is deployed\n• Try the curl command again to verify it's still working",
                inline=False
            )
            await ctx.followup.send(embed=embed)

    async def _update_progress(self, message, prompt):
        """Updates the progress message periodically so the user knows we're still waiting."""
        dots = 1
        wait_time = 0
        try:
            while True:
                dot_str = "." * dots
                await message.edit(content=f"✨ Dreaming: `{prompt}`\n\n*Generating image with flux1 schnell{dot_str} ({wait_time}s)*")
                dots = (dots % 3) + 1
                wait_time += 4
                await asyncio.sleep(4)
        except asyncio.CancelledError:
            # Task was cancelled, just exit
            pass
        except Exception as e:
            logger.error(f"Error in progress updates: {str(e)}")

def setup(bot):
    bot.add_cog(CloudflareImageCommands(bot))
