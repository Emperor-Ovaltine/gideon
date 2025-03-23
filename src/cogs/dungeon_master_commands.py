"""Commands for the AI Dungeon Master functionality."""
import discord
import random
import re
import traceback
from discord.ext import commands
from ..utils.state_manager import BotStateManager
from ..utils.openrouter_client import OpenRouterClient
from ..config import OPENROUTER_API_KEY, SYSTEM_PROMPT, DEFAULT_MODEL
from datetime import datetime
from ..utils.cloudflare_client import CloudflareWorkerClient
import os
import asyncio
import logging

# Set up logger
logger = logging.getLogger(__name__)

class DungeonMasterCommands(commands.Cog):
    """Commands for AI-powered D&D game sessions."""
    
    def __init__(self, bot):
        self.bot = bot
        self.state = BotStateManager()
        self.openrouter_client = OpenRouterClient(OPENROUTER_API_KEY, SYSTEM_PROMPT, DEFAULT_MODEL)
        
        # Initialize DND state if it doesn't exist
        if not hasattr(self.state, 'dnd_adventures'):
            self.state.dnd_adventures = {}
        
        print(f"DungeonMasterCommands cog initialized")
        
        # For scene image generation
        self.turn_counter = 0
        self.image_frequency = 5  # Generate an image every 5 turns
        self.cf_client = CloudflareWorkerClient(
            os.environ.get("CLOUDFLARE_WORKER_URL", "https://image-generator.example.workers.dev"),
            os.environ.get("CLOUDFLARE_API_KEY")
        )
    
    adventure_group = discord.SlashCommandGroup(
        "adventure", 
        "AI Dungeon Master commands"
    )
    
    @commands.Cog.listener()
    async def on_ready(self):
        print(f"DungeonMasterCommands cog ready, adventure commands registered")
    
    @adventure_group.command(
        name="start",
        description="Start a new D&D adventure"
    )
    async def start_adventure_slash(self, ctx, 
                                  setting: discord.Option(
                                      str, 
                                      "The setting for your adventure",
                                      choices=["Fantasy", "Sci-Fi", "Horror", "Modern", "Custom"]
                                  ) = "Fantasy",
                                  description: discord.Option(
                                      str, 
                                      "Adventure description (required for Custom setting, optional for others)",
                                      required=False
                                  ) = None):
        await ctx.defer()
        
        channel_id = str(ctx.channel.id)
        
        # Check if there's already an adventure in this channel
        if channel_id in self.state.dnd_adventures and self.state.dnd_adventures[channel_id]["active"]:
            await ctx.respond("⚠️ There's already an active adventure in this channel. End it with `/adventure end` before starting a new one.")
            return
        
        # Check if Custom is selected but no prompt provided
        if setting == "Custom" and not description:
            await ctx.respond("⚠️ You must provide a description when selecting the Custom setting.")
            return
        
        # Build the prompt based on the setting
        if description:
            # If a description is provided, use it regardless of the setting
            adventure_prompt = description
        else:
            # Default prompts based on setting
            prompts = {
                "Fantasy": "a medieval fantasy world with magic, dragons, and brave heroes",
                "Sci-Fi": "a futuristic space adventure with advanced technology and alien species",
                "Horror": "a suspenseful horror story in an abandoned mansion",
                "Modern": "a modern-day adventure in a city with mysterious events"
            }
            adventure_prompt = prompts.get(setting, prompts["Fantasy"])
        
        # Initialize this adventure in state
        self.state.dnd_adventures[channel_id] = {
            "active": True,
            "setting": setting,
            "started_at": datetime.now(),
            "started_by": ctx.author.display_name,
            "player_actions": [],
            "dm_responses": [],
            "characters": {}
        }
        
        # Create the DM system prompt
        dm_system_prompt = (
            "You are an experienced and creative Dungeon Master for a tabletop RPG game. "
            "Your responses should be descriptive, engaging, and help move the story forward. "
            "Include sensory details, NPC dialogue, and opportunities for player choices. "
            "Keep your responses concise (300 words or less). "
            "When players roll dice, acknowledge the result and incorporate it into the narrative. "
            "If players want to add new characters, help them do so."
        )
        
        # Get the initial scene from the AI
        setup_message = f"Start a new adventure in {adventure_prompt}. Describe the opening scene, introduce the setting, and give the players a situation to respond to."
        
        # Store the original model to restore later
        current_model = self.openrouter_client.model
        
        try:
            # Set model to channel-specific or global model
            model_to_use = self.state.get_effective_model(channel_id)
            self.openrouter_client.model = model_to_use
            
            # Send to API
            response = await self.openrouter_client.send_message_with_history(
                [{"role": "user", "content": setup_message}],
                system_prompt=dm_system_prompt
            )
            
            # Store the DM's response
            self.state.dnd_adventures[channel_id]["dm_responses"].append({
                "content": response,
                "timestamp": datetime.now()
            })
            
            # Create an embed for the adventure start
            embed = discord.Embed(
                title=f"🎲 New Adventure: {setting} Realm",
                description=response,
                color=discord.Color.dark_gold()
            )
            embed.set_footer(text=f"Adventure started by {ctx.author.display_name} | Use /adventure action to continue")
            
            await ctx.respond(embed=embed)
            
        finally:
            # Restore original model
            self.openrouter_client.model = current_model
    
    @adventure_group.command(
        name="action",
        description="Take an action in the current adventure"
    )
    async def take_action_slash(self, ctx, 
                              action: discord.Option(
                                  str, 
                                  "Describe what you want to do"
                              )):
        await ctx.defer()
        
        channel_id = str(ctx.channel.id)
        
        # Check if there's an active adventure
        if channel_id not in self.state.dnd_adventures or not self.state.dnd_adventures[channel_id]["active"]:
            await ctx.respond("⚠️ There's no active adventure in this channel. Start one with `/adventure start`.")
            return
        
        # Add the player's action to history
        adventure = self.state.dnd_adventures[channel_id]
        adventure["player_actions"].append({
            "player": ctx.author.display_name,
            "content": action,
            "timestamp": datetime.now()
        })
        
        # Build conversation context for the AI
        dm_system_prompt = (
            "You are an experienced and creative Dungeon Master for a tabletop RPG game. "
            "Your responses should be descriptive, engaging, and help move the story forward. "
            "Include sensory details, NPC dialogue, and opportunities for player choices. "
            "Keep your responses concise (300 words or less). "
            "When players roll dice, acknowledge the result and incorporate it into the narrative. "
            "If players want to add new characters, help them do so."
        )
        
        context = []
        
        # Add the last few interactions to maintain context (up to 10 total)
        history_limit = min(5, len(adventure["player_actions"]))
        for i in range(max(0, len(adventure["player_actions"]) - history_limit), len(adventure["player_actions"])):
            player_action = adventure["player_actions"][i]
            context.append({
                "role": "user", 
                "content": f"{player_action['player']}: {player_action['content']}"
            })
            
            # Add corresponding DM response if available
            if i < len(adventure["dm_responses"]):
                context.append({
                    "role": "assistant", 
                    "content": adventure["dm_responses"][i]["content"]
                })
        
        # Store original model
        current_model = self.openrouter_client.model
        processing_msg = None
        
        try:
            # First show the player's action
            processing_msg = await ctx.respond(f"🎭 **{ctx.author.display_name}**: {action}\n\n*The Dungeon Master is thinking...*")
            
            # Set model to channel-specific or global model
            model_to_use = self.state.get_effective_model(channel_id)
            self.openrouter_client.model = model_to_use
            
            # Send to API
            response = await self.openrouter_client.send_message_with_history(
                context,
                system_prompt=dm_system_prompt
            )
            
            # Store the DM's response
            adventure["dm_responses"].append({
                "content": response,
                "timestamp": datetime.now()
            })
            
            # Create an embed for the DM's response
            embed = discord.Embed(
                title="🎲 Dungeon Master",
                description=response,
                color=discord.Color.dark_purple()
            )
            
            # Send the response
            await processing_msg.edit(content=f"🎭 **{ctx.author.display_name}**: {action}", embed=embed)
            
            # Image generation logic
            # Increment turn counter and check if we should generate an image
            self.turn_counter += 1
            if self.image_frequency > 0 and self.turn_counter % self.image_frequency == 0:
                # Generate image in the background so it doesn't block the game flow
                asyncio.create_task(self.generate_scene_image(ctx.channel, response))
            
        finally:
            # Restore original model
            self.openrouter_client.model = current_model
    
    @adventure_group.command(
        name="roll",
        description="Roll dice for your adventure"
    )
    async def roll_dice_slash(self, ctx, 
                            dice: discord.Option(
                                str, 
                                "Dice to roll (e.g., 1d20, 2d6, 3d8+2)",
                                required=True
                            )):
        channel_id = str(ctx.channel.id)
        
        # Parse the dice string
        dice_pattern = re.compile(r'(\d+)d(\d+)(?:([+-])(\d+))?')
        match = dice_pattern.match(dice)
        
        if not match:
            await ctx.respond("⚠️ Invalid dice format. Use formats like `1d20`, `2d6`, or `3d8+2`.")
            return
        
        num_dice = int(match.group(1))
        dice_type = int(match.group(2))
        modifier_sign = match.group(3) or ""
        modifier_value = int(match.group(4) or 0)
        
        # Cap at reasonable limits
        if num_dice > 20 or dice_type > 100:
            await ctx.respond("⚠️ Maximum limits: 20 dice and d100")
            return
        
        # Roll the dice
        rolls = [random.randint(1, dice_type) for _ in range(num_dice)]
        
        # Calculate total
        total = sum(rolls)
        if modifier_sign == "+":
            total += modifier_value
        elif modifier_sign == "-":
            total -= modifier_value
        
        # Format the roll result
        roll_details = ", ".join(str(r) for r in rolls)
        
        if len(roll_details) > 1024:  # Discord embed field value limit
            roll_details = "Too many dice to show individual results"
            
        # Create an embed for the roll
        embed = discord.Embed(
            title=f"🎲 Dice Roll: {dice}",
            color=discord.Color.blue()
        )
        
        embed.add_field(name="Rolls", value=roll_details, inline=False)
        
        if modifier_sign:
            embed.add_field(name="Modifier", value=f"{modifier_sign}{modifier_value}", inline=True)
            
        embed.add_field(name="Total", value=str(total), inline=True)
        embed.set_footer(text=f"Rolled by {ctx.author.display_name}")
        
        # Check if there's an active adventure to add this as an action
        if channel_id in self.state.dnd_adventures and self.state.dnd_adventures[channel_id]["active"]:
            adventure = self.state.dnd_adventures[channel_id]
            adventure["player_actions"].append({
                "player": ctx.author.display_name,
                "content": f"rolled {dice} and got {total}",
                "timestamp": datetime.now()
            })
        
        await ctx.respond(embed=embed)
    
    @adventure_group.command(
        name="status",
        description="Check the status of the current adventure"
    )
    async def check_status_slash(self, ctx):
        channel_id = str(ctx.channel.id)
        
        # Check if there's an active adventure
        if channel_id not in self.state.dnd_adventures or not self.state.dnd_adventures[channel_id]["active"]:
            await ctx.respond("⚠️ There's no active adventure in this channel. Start one with `/adventure start`.")
            return
        
        adventure = self.state.dnd_adventures[channel_id]
        
        # Calculate duration
        started_at = adventure["started_at"]
        duration = datetime.now() - started_at
        
        # Create an embed for the status
        embed = discord.Embed(
            title="🎲 Adventure Status",
            description=f"Setting: {adventure['setting']}",
            color=discord.Color.green()
        )
        
        embed.add_field(
            name="Started By", 
            value=adventure["started_by"], 
            inline=True
        )
        
        embed.add_field(
            name="Duration", 
            value=f"{duration.days}d {duration.seconds // 3600}h {(duration.seconds // 60) % 60}m", 
            inline=True
        )
        
        embed.add_field(
            name="Actions", 
            value=str(len(adventure["player_actions"])), 
            inline=True
        )
        
        # List the last 5 actions
        if adventure["player_actions"]:
            recent_actions = adventure["player_actions"][-5:]
            action_list = "\n".join([f"• **{action['player']}**: {action['content'][:50]}..." if len(action['content']) > 50 else f"• **{action['player']}**: {action['content']}" for action in recent_actions])
            
            embed.add_field(
                name="Recent Actions", 
                value=action_list, 
                inline=False
            )
        
        await ctx.respond(embed=embed)
    
    @adventure_group.command(
        name="end",
        description="End the current adventure"
    )
    async def end_adventure_slash(self, ctx):
        channel_id = str(ctx.channel.id)
        
        # Check if there's an active adventure
        if channel_id not in self.state.dnd_adventures or not self.state.dnd_adventures[channel_id]["active"]:
            await ctx.respond("⚠️ There's no active adventure in this channel.")
            return
        
        adventure = self.state.dnd_adventures[channel_id]
        
        # Mark the adventure as inactive
        adventure["active"] = False
        adventure["ended_at"] = datetime.now()
        adventure["ended_by"] = ctx.author.display_name
        
        # Calculate stats
        duration = adventure["ended_at"] - adventure["started_at"]
        
        # Create an embed for the end
        embed = discord.Embed(
            title="🎲 Adventure Concluded",
            description=f"Your {adventure['setting']} adventure has ended.",
            color=discord.Color.dark_red()
        )
        
        embed.add_field(
            name="Started By", 
            value=adventure["started_by"], 
            inline=True
        )
        
        embed.add_field(
            name="Ended By", 
            value=adventure["ended_by"], 
            inline=True
        )
        
        embed.add_field(
            name="Duration", 
            value=f"{duration.days}d {duration.seconds // 3600}h {(duration.seconds // 60) % 60}m", 
            inline=True
        )
        
        embed.add_field(
            name="Actions", 
            value=str(len(adventure["player_actions"])), 
            inline=True
        )
        
        await ctx.respond(embed=embed)
    
    async def _create_image_prompt(self, narration):
        """Use the LLM to create a better image prompt from the narration text."""
        try:
            # Store original model
            current_model = self.openrouter_client.model
            
            try:
                # Set model to global model
                model_to_use = self.state.get_global_model()
                self.openrouter_client.model = model_to_use
                
                system_prompt = (
                    "You are an expert at creating vivid image generation prompts. "
                    "Convert the following D&D game narration into a detailed, visual prompt "
                    "suitable for fantasy image generation. Focus on describing the visual scene, "
                    "characters, lighting, mood, and environment. Keep it under 100 words, "
                    "and make it highly descriptive for an AI image generator."
                )
                
                response = await self.openrouter_client.send_message_with_history(
                    [{"role": "user", "content": f"Create an image prompt based on this game narration:\n\n{narration}"}],
                    system_prompt=system_prompt
                )
                
                enhanced_prompt = f"{response.strip()}, fantasy art style, detailed, vibrant colors, dramatic lighting"
                return enhanced_prompt
                
            finally:
                # Restore original model
                self.openrouter_client.model = current_model
                
            return f"Fantasy RPG scene: {narration[:150]}..."
        except Exception as e:
            logger.error(f"Error creating image prompt: {str(e)}")
            return f"Fantasy RPG scene with characters in a dynamic pose: {narration[:100]}..."
    
    async def generate_scene_image(self, channel, narration):
        """Generate an image based on the current scene and display it to players."""
        try:
            thinking_msg = await channel.send("🎨 *Creating a visual of the current scene...*")
            image_prompt = await self._create_image_prompt(narration)
            logger.info(f"Generated image prompt: {image_prompt}")
            progress_task = asyncio.create_task(self._update_progress(thinking_msg))
            result = await self.cf_client.generate_image(
                prompt=image_prompt,
                negative_prompt="blurry, distorted, text, watermark, signature, low quality, disfigured, cartoon",
                width=768,
                height=512,
                steps=30,
                seed=random.randint(0, 2147483647)
            )
            progress_task.cancel()
            if result.get("success", False):
                embed = discord.Embed(
                    title="📜 Scene Visualization",
                    description=f"*{image_prompt[:200]}{'...' if len(image_prompt) > 200 else ''}*",
                    color=discord.Color.dark_gold()
                )
                if "image_url" in result:
                    embed.set_image(url=result["image_url"])
                    await thinking_msg.edit(content=None, embed=embed)
                elif "local_path" in result:
                    file = discord.File(result["local_path"], filename="scene.jpg")
                    embed.set_image(url=f"attachment://scene.jpg")
                    await thinking_msg.edit(content=None, embed=embed, file=file)
                return True
            else:
                await thinking_msg.delete()
                return False
        except Exception as e:
            logger.error(f"Error generating scene image: {str(e)}")
            try:
                await thinking_msg.delete()
            except:
                pass
            return False
    
    async def _update_progress(self, message):
        """Updates the progress message periodically."""
        dots = 1
        wait_time = 0
        try:
            while True:
                dot_str = "." * dots
                await message.edit(content=f"🎨 *Creating a visual of the current scene{dot_str} ({wait_time}s)*")
                dots = (dots % 3) + 1
                wait_time += 2
                await asyncio.sleep(2)
        except asyncio.CancelledError:
            pass
        except Exception as e:
            logger.error(f"Error in progress updates: {str(e)}")
    
    @adventure_group.command(name="config_images", description="Configure image generation frequency")
    async def config_images(
        self, 
        ctx, 
        frequency: discord.Option(
            int, 
            "Number of turns between image generation (0 to disable)", 
            min_value=0, 
            max_value=20,
            required=True
        )
    ):
        """Configure how often scene images are generated during gameplay."""
        await ctx.defer()
        if frequency == 0:
            self.image_frequency = 0
            await ctx.respond("📷 Scene image generation has been disabled.")
        else:
            self.image_frequency = frequency
            await ctx.respond(f"📷 Scene images will be generated every {frequency} turns.")
    
    async def process_turn(self, ctx, action, *args, **kwargs):
        """Process a player's turn in the adventure."""
        # Placeholder for future implementation
        pass

def setup(bot):
    try:
        print("Registering DungeonMasterCommands cog...")
        bot.add_cog(DungeonMasterCommands(bot))
        print("DungeonMasterCommands cog setup complete")
    except Exception as e:
        print(f"Error during DungeonMasterCommands cog setup: {e}")
        print(traceback.format_exc())
        raise
