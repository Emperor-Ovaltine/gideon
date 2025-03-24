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
    """Commands for AI-powered Fantasy TTRPG game sessions."""
    
    def __init__(self, bot):
        self.bot = bot
        self.state = BotStateManager()
        self.openrouter_client = OpenRouterClient(OPENROUTER_API_KEY, SYSTEM_PROMPT, DEFAULT_MODEL)
        
        # Initialize DND state if it doesn't exist
        if not hasattr(self.state, 'dnd_adventures'):
            self.state.dnd_adventures = {}
        
        # Initialize adventures dictionary
        self.adventures = {}
        self.turn_counters = {}  # Track turn counters per adventure
        self.image_generation_available = True  # Flag to enable/disable image generation
        self.pending_image_tasks = {}  # Track ongoing image generation tasks
        self.processed_messages = set()  # Track which messages we've already processed
        
        # Centralized DM system prompt
        self.dm_system_prompt = (
            "You are an experienced and creative Dungeon Master for a tabletop RPG game. "
            "Your responses should be descriptive, engaging, and help move the story forward. "
            "Include sensory details, NPC dialogue, and opportunities for player choices. "
            "Keep your responses concise (300 words or less). "
            "When players roll dice, acknowledge the result and incorporate it into the narrative. "
            "If players want to add new characters, help them do so."
        )
        
        # Important: Restore any existing thread adventures from state
        for channel_id, adventure in self.state.dnd_adventures.items():
            if "thread_id" in adventure and adventure.get("active", False):
                thread_id = str(adventure["thread_id"])
                self.adventures[thread_id] = {
                    'name': adventure.get("name", "Adventure"),
                    'setting': adventure.get("setting", "Fantasy"),
                    'description': "Restored adventure",
                    'started_at': adventure.get("started_at", datetime.now()),
                    'started_by': adventure.get("started_by", "Unknown"),
                    'active': True,
                    'player_actions': adventure.get("player_actions", []),
                    'dm_responses': adventure.get("dm_responses", [])
                }
                logger.info(f"Restored adventure in thread {thread_id}")
        
        # For scene image generation
        self.image_frequency = 5  # Generate an image every 5 turns
        self.cf_client = CloudflareWorkerClient(
            os.environ.get("CLOUDFLARE_WORKER_URL", "https://image-generator.example.workers.dev"),
            os.environ.get("CLOUDFLARE_API_KEY")
        )
        
        print(f"DungeonMasterCommands cog initialized with {len(self.adventures)} adventures")
        logger.info(f"Adventures dictionary initialized with keys: {list(self.adventures.keys())}")
    
    def _verify_thread_id(self, thread_id):
        """Verify and normalize thread ID to ensure consistent format."""
        # Always convert to string for consistency
        thread_id = str(thread_id)
        
        # Direct match check
        if thread_id in self.adventures:
            return thread_id
            
        # No adventures exist yet
        if not self.adventures:
            logger.debug(f"No adventures exist yet, returning thread ID {thread_id}")
            return thread_id
            
        # Try to find the thread ID with different representations
        for key in list(self.adventures.keys()):
            try:
                # Try string/int conversion comparison
                if str(key) == thread_id or (key.isdigit() and thread_id.isdigit() and int(key) == int(thread_id)):
                    logger.info(f"Found thread ID {thread_id} as {key} after conversion check")
                    return key
            except:
                pass
                
        # Log that we didn't find this thread ID
        logger.warning(f"Thread ID {thread_id} not found in adventures dict with keys: {list(self.adventures.keys())}")
        return thread_id
    
    # Helper methods for common operations
    async def _get_model_for_context(self, channel_id=None):
        """Get the appropriate model for the current context."""
        # Store original model
        current_model = self.openrouter_client.model
        
        if channel_id:
            # Set model to channel-specific or global model
            model_to_use = self.state.get_effective_model(channel_id)
            self.openrouter_client.model = model_to_use
            
        return current_model
    
    async def _restore_model(self, original_model):
        """Restore the original model after API calls."""
        self.openrouter_client.model = original_model
    
    async def _generate_dm_response(self, context, channel_id=None):
        """Generate a DM response based on the conversation context."""
        # Set appropriate model
        original_model = await self._get_model_for_context(channel_id)
        
        try:
            # Send to API
            response = await self.openrouter_client.send_message_with_history(
                context,
                system_prompt=self.dm_system_prompt
            )
            return response
        finally:
            # Restore original model
            await self._restore_model(original_model)
    
    def _build_conversation_context(self, adventure, limit=5):
        """Build conversation context for the AI based on adventure history."""
        context = []
        
        # Add the last few interactions to maintain context
        history_limit = min(limit, len(adventure["player_actions"]))
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
        
        return context
    
    def _initialize_adventure(self, thread_id, name, setting, description, started_by):
        """Initialize a new adventure in the adventures dictionary."""
        self.adventures[thread_id] = {
            'name': name,
            'setting': setting,
            'description': description,
            'started_at': datetime.now(),
            'started_by': started_by,
            'active': True,
            'player_actions': [],
            'dm_responses': []
        }
        logger.info(f"Created new adventure in thread {thread_id}")
        return self.adventures[thread_id]
    
    def _update_adventure_state(self, thread_id, channel_id, adventure_data):
        """Update adventure state in both thread dictionary and channel state."""
        # Update thread-specific state
        self.adventures[thread_id] = adventure_data
        
        # Update channel-based state for backward compatibility
        self.state.dnd_adventures[channel_id] = {
            "active": adventure_data["active"],
            "thread_id": thread_id,
            "setting": adventure_data["setting"],
            "name": adventure_data["name"],
            "description": adventure_data.get("description", ""),
            "started_at": adventure_data["started_at"],
            "started_by": adventure_data["started_by"],
            "player_actions": adventure_data["player_actions"],
            "dm_responses": adventure_data["dm_responses"],
            "characters": adventure_data.get("characters", {})
        }
    
    async def _handle_image_generation(self, channel, thread_id, response):
        """Handle image generation for the adventure."""
        if self.image_generation_available:
            # Initialize counter if needed
            if thread_id not in self.turn_counters:
                self.turn_counters[thread_id] = 0
                
            # Increment adventure-specific counter
            self.turn_counters[thread_id] += 1
            
            # Check if we should generate an image
            if self.image_frequency > 0 and self.turn_counters[thread_id] % self.image_frequency == 0:
                logger.info(f"Generating image for adventure {thread_id} (turn {self.turn_counters[thread_id]})")
                
                # Create and store the task with a reference
                task = asyncio.create_task(self.generate_scene_image(channel, response))
                self.pending_image_tasks[thread_id] = task
                
                # Add a callback to clean up when task completes
                def task_done_callback(completed_task):
                    if thread_id in self.pending_image_tasks and self.pending_image_tasks[thread_id] == completed_task:
                        del self.pending_image_tasks[thread_id]
                        logger.info(f"Image generation for thread {thread_id} completed")
                
                task.add_done_callback(task_done_callback)
    
    adventure_group = discord.SlashCommandGroup(
        "adventure", 
        "AI Dungeon Master commands"
    )

    @commands.Cog.listener()
    async def on_ready(self):
        print(f"DungeonMasterCommands cog ready, adventure commands registered")

    @adventure_group.command(
        name="new",
        description="Start a new adventure in a thread"
    )
    async def new_adventure_slash(self, ctx, 
                               name: discord.Option(
                                   str,
                                   "Name for your adventure thread",
                                   required=True
                               ),
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
        
        # Check if the channel supports threads
        if not isinstance(ctx.channel, discord.TextChannel):
            await ctx.respond("⚠️ This command can only be used in text channels that support threads.")
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
        
        # Create an initial message that will anchor the thread
        initial_message = await ctx.channel.send(f"**AI Adventure: {name}**\n*Starting a new {setting} adventure...*")
        
        try:
            # Create actual Discord thread from the message
            thread = await initial_message.create_thread(
                name=name,
                auto_archive_duration=1440  # Auto-archive after 24 hours of inactivity
            )
            
            # Initialize this adventure in the thread-specific state
            thread_id = str(thread.id)
            channel_id = str(ctx.channel.id)
            
            # Initialize adventure
            adventure = self._initialize_adventure(
                thread_id=thread_id,
                name=name,
                setting=setting,
                description=adventure_prompt,
                started_by=ctx.author.display_name
            )
            
            # Update state in both places
            self._update_adventure_state(thread_id, channel_id, adventure)
            
            # Get the initial scene from the AI
            setup_message = f"Start a new adventure in {adventure_prompt}. Describe the opening scene, introduce the setting, and give the players a situation to respond to."
            
            # Send initial thinking message to thread
            thinking_msg = await thread.send("🎲 *The Dungeon Master is creating your adventure...*")
            
            # Generate DM response
            context = [{"role": "user", "content": setup_message}]
            response = await self._generate_dm_response(context, channel_id)
            
            # Store the DM's response
            adventure["dm_responses"].append({
                "content": response,
                "timestamp": datetime.now()
            })
            
            # Update state
            self._update_adventure_state(thread_id, channel_id, adventure)
            
            # Create an embed for the adventure start
            embed = discord.Embed(
                title=f"🎲 Adventure: {name}",
                description=response,
                color=discord.Color.dark_gold()
            )
            embed.set_footer(text=f"Adventure started by {ctx.author.display_name} | Just type in this thread to continue")
            
            # Update the thinking message
            await thinking_msg.edit(content=None, embed=embed)
            
            # Add welcome message in the thread
            welcome_msg = (
                "✅ Adventure thread created! You can interact with the AI Dungeon Master by just sending "
                "regular messages in this thread. I'll respond to everything automatically.\n\n"
                "Special commands:\n"
                "• To roll dice, type `/adventure roll` (e.g., `/adventure roll 1d20`)\n"
                "• To check adventure status, type `/adventure status`\n"
                "• To end the adventure, type `/adventure end`"
            )
            await thread.send(welcome_msg)
            
            # Reply to the slash command
            await ctx.respond(f"✅ Created new adventure thread: **{name}**\nJoin the thread to begin your adventure!")
                
        except discord.Forbidden:
            await ctx.respond("⚠️ I don't have permission to create threads in this channel.")
        except discord.HTTPException as e:
            await ctx.respond(f"⚠️ Failed to create thread: {str(e)}")

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
        
        # Check if we're in a thread and it's an active adventure
        if isinstance(ctx.channel, discord.Thread):
            thread_id = self._verify_thread_id(str(ctx.channel.id))
            
            if thread_id in self.adventures and self.adventures[thread_id].get("active", False):
                adventure = self.adventures[thread_id]
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
        # Check if we're in a thread
        if isinstance(ctx.channel, discord.Thread):
            thread_id = self._verify_thread_id(str(ctx.channel.id))
            
            if thread_id in self.adventures and self.adventures[thread_id].get("active", False):
                adventure = self.adventures[thread_id]
                
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
                    name="Name", 
                    value=adventure["name"],  
                    inline=True
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
                return
                
        await ctx.respond("⚠️ There's no active adventure in this thread.")
    
    @adventure_group.command(
        name="end", 
        description="End the current adventure"           
    )
    async def end_adventure_slash(self, ctx):
        # Check if we're in a thread
        if isinstance(ctx.channel, discord.Thread):
            thread_id = self._verify_thread_id(str(ctx.channel.id))
            
            if thread_id in self.adventures and self.adventures[thread_id].get("active", False):
                adventure = self.adventures[thread_id]
                
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
                return
                
        await ctx.respond("⚠️ There's no active adventure in this thread.")
    
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
            logger.info(f"Generated image prompt for {channel.id}: {image_prompt[:100]}...")
            
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
            
            # Detailed logging for image generation result
            logger.info(f"Image generation result: success={result.get('success', False)}, keys={list(result.keys())}")
            
            if result.get("success", False):
                embed = discord.Embed(
                    title="📜 Scene Visualization",
                    description=f"*{image_prompt[:200]}{'...' if len(image_prompt) > 200 else ''}*",
                    color=discord.Color.dark_gold()
                )
                try:
                    if "image_url" in result:
                        embed.set_image(url=result["image_url"])
                        await thinking_msg.edit(content=None, embed=embed)
                    elif "local_path" in result:
                        file = discord.File(result["local_path"], filename="scene.jpg")
                        embed.set_image(url=f"attachment://scene.jpg")
                        await thinking_msg.edit(content=None, embed=embed, file=file)
                    logger.info(f"Successfully edited message with image embed for channel {channel.id}")
                    return True
                except Exception as edit_error:
                    logger.error(f"Error editing image message: {str(edit_error)}")
                    # If editing fails, delete the old message and send a new one
                    try:
                        await thinking_msg.delete()
                    except:
                        pass
                    
                    # Send a new message with the embed
                    if "image_url" in result:
                        await channel.send(embed=embed)
                    elif "local_path" in result:
                        file = discord.File(result["local_path"], filename="scene.jpg")
                        await channel.send(embed=embed, file=file)
                    logger.info(f"Sent new message with image embed after edit failure for channel {channel.id}")
                    return True
            else:
                try:
                    await thinking_msg.delete()
                except:
                    pass
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
    
    @commands.Cog.listener()
    async def on_message(self, message):
        """Listen for messages in adventure threads to process player actions"""
        # Ignore messages from the bot itself
        if message.author.bot:
            return
            
        # Check if this is in a thread
        if isinstance(message.channel, discord.Thread):
            original_thread_id = str(message.channel.id)
            thread_id = self._verify_thread_id(original_thread_id)
            message_id = str(message.id)
            
            # Check if we've already processed this message
            if message_id in self.processed_messages:
                logger.debug(f"Already processed message {message_id} - skipping")
                return
                
            # Mark message as being processed immediately to prevent duplicates
            self.processed_messages.add(message_id)
            
            logger.debug(f"Message received in thread {original_thread_id}, available adventures: {list(self.adventures.keys())}")
            
            # First check if this is one of our adventure threads
            is_adventure_thread = thread_id in self.adventures
            
            # If not, check if parent channel has an adventure we can associate with
            if not is_adventure_thread:
                parent_thread_adopted = False
                
                # Check if we should adopt this thread based on parent channel
                if message.channel.parent and isinstance(message.channel.parent, discord.TextChannel):
                    parent_id = str(message.channel.parent.id)
                    if parent_id in self.state.dnd_adventures and self.state.dnd_adventures[parent_id].get("active", False):
                        logger.info(f"Found parent channel with active adventure - adopting thread {thread_id}")
                        
                        # Create a new adventure entry for this thread
                        parent_adventure = self.state.dnd_adventures[parent_id]
                        thread_name = getattr(message.channel, 'name', 'Adventure Thread')
                        
                        # Initialize new adventure in thread
                        self._initialize_adventure(
                            thread_id=thread_id,
                            name=thread_name,
                            setting=parent_adventure.get("setting", "Fantasy"),
                            description="Adopted from parent channel adventure",
                            started_by=parent_adventure.get("started_by", "Unknown")
                        )
                        logger.info(f"Adopted thread {thread_id} as adventure thread, keys now: {list(self.adventures.keys())}")
                        is_adventure_thread = True
                
                # Thread hasn't been adopted from parent - not an adventure thread
                if not is_adventure_thread:
                    logger.debug(f"Thread {thread_id} not recognized as adventure thread")
                    # Remove from processed_messages since we're not actually processing it
                    self.processed_messages.discard(message_id)
                    return
            
            # Only process if this is one of our adventure threads
            if is_adventure_thread:
                adventure = self.adventures[thread_id]
                logger.info(f"Processing message in adventure thread {thread_id}")
                
                # Make sure we have the 'active' key and it's set to True
                if not adventure.get('active', False):
                    logger.debug(f"Thread {thread_id} exists but is not active")
                    # Remove from processed_messages since we're not actually processing it
                    self.processed_messages.discard(message_id)
                    return
                
                # Initialize player_actions if it doesn't exist
                if "player_actions" not in adventure:
                    adventure["player_actions"] = []
                if "dm_responses" not in adventure:
                    adventure["dm_responses"] = []
                    
                # Store the player's action
                adventure["player_actions"].append({
                    "player": message.author.display_name,
                    "content": message.content,
                    "timestamp": datetime.now()
                })
                
                # Build conversation context for the AI
                context = self._build_conversation_context(adventure)
                
                # First send a "thinking" message - force disable embed for thinking status
                thinking_msg = await message.channel.send("🎲 *The Dungeon Master is thinking...*")
                
                try:
                    # Get channel ID for model selection
                    channel_id = None
                    if message.channel.parent:
                        channel_id = str(message.channel.parent.id)
                    
                    # Generate DM response
                    response = await self._generate_dm_response(context, channel_id)
                    
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
                    
                    # Add debug logging
                    logger.info(f"Attempting to edit message with DM response embed in thread {thread_id}")
                    
                    # Send the response
                    try:
                        await thinking_msg.edit(content=None, embed=embed)
                        logger.info(f"Successfully edited thinking message with embed in thread {thread_id}")
                    except Exception as edit_error:
                        logger.error(f"Error editing thinking message: {str(edit_error)}")
                        # If editing fails, delete and send a new message
                        try:
                            await thinking_msg.delete()
                        except:
                            pass
                        
                        await message.channel.send(embed=embed)
                        logger.info(f"Sent new message with embed after edit failure in thread {thread_id}")
                    
                    # Handle image generation
                    await self._handle_image_generation(message.channel, thread_id, response)
                    
                    # Mark that we've handled this message to prevent the regular thread cog from also processing it
                    return True
                    
                except Exception as e:
                    logger.error(f"Error processing thread message: {str(e)}")
                    logger.error(traceback.format_exc())
                    try:
                        await thinking_msg.edit(content=f"⚠️ Error: {str(e)[:100]}...")
                    except:
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