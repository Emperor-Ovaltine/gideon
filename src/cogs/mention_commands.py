"""Functionality for responding to @mentions in messages."""
import discord
from discord.ext import commands
from ..utils.state_manager import BotStateManager
from ..utils.conversation import get_channel_context
from ..utils.openrouter_client import OpenRouterClient
from ..config import OPENROUTER_API_KEY, SYSTEM_PROMPT, DEFAULT_MODEL
from datetime import datetime

class MentionCommands(commands.Cog):
    """Handles responses when the bot is @mentioned in messages."""
    
    def __init__(self, bot):
        self.bot = bot
        self.state = BotStateManager()
        self.openrouter_client = OpenRouterClient(OPENROUTER_API_KEY, SYSTEM_PROMPT, DEFAULT_MODEL)
    
    def get_model_for_channel(self, channel_id):
        """Get the appropriate model for this channel"""
        return self.state.get_effective_model(channel_id)
    
    @commands.Cog.listener()
    async def on_message(self, message):
        """Listen for messages in channels and build context memory."""
        # Ignore messages from the bot itself
        if message.author == self.bot.user:
            return
            
        # Ignore messages in threads as they're handled by ThreadCommands
        if isinstance(message.channel, discord.Thread):
            return
        
        # Store all regular messages to build context
        channel_id = str(message.channel.id)
        if channel_id not in self.state.channel_history:
            self.state.channel_history[channel_id] = []
        
        # Add all regular user messages to history
        if not message.content.startswith('/'):  # Ignore slash commands
            self.state.add_to_channel_history(channel_id, {
                "role": "user",
                "name": message.author.display_name,
                "content": message.content,
                "timestamp": datetime.now()
            })
                
        # Process mentions - improved detection method for Py-Cord
        is_mentioned = False
        # Check if the bot is mentioned in the message
        if message.mentions:
            for mention in message.mentions:
                if mention.id == self.bot.user.id:
                    is_mentioned = True
                    break
        
        # Alternative check for raw mention text in content (more robust)
        if not is_mentioned and f'<@{self.bot.user.id}>' in message.content or f'<@!{self.bot.user.id}>' in message.content:
            is_mentioned = True
                
        if is_mentioned and not message.mention_everyone:
            # Determine which model to use for this channel
            current_model = self.openrouter_client.model  # Store original model
            model_to_use = self.get_model_for_channel(channel_id)  # Get effective model for this channel
            
            # Set the model to use for this request
            self.openrouter_client.model = model_to_use
            
            try:
                # Get the message content without the mention
                content = message.content
                # Remove any mentions of the bot from the content
                content = content.replace(f'<@{self.bot.user.id}>', '').replace(f'<@!{self.bot.user.id}>', '')
                
                # Trim whitespace and handle empty messages
                content = content.strip()
                if not content:
                    content = "Hello!"  # Default message if they just mentioned the bot
                
                # Process images if any are attached
                images = []
                if self.openrouter_client.model_supports_vision() and message.attachments:
                    for attachment in message.attachments:
                        if any(attachment.filename.lower().endswith(ext) for ext in ['.jpg', '.jpeg', '.png', '.gif', '.webp']):
                            try:
                                image_data = await attachment.read()
                                images.append({
                                    'data': image_data,
                                    'type': attachment.content_type or 'image/jpeg'
                                })
                            except Exception as e:
                                await message.channel.send(f"⚠️ Failed to process image {attachment.filename}: {str(e)}")
                
                # Get channel-specific system prompt if it exists
                channel_system_prompt = self.state.get_channel_system_prompt(channel_id)
                
                # Get recent channel context
                conversation_context = await get_channel_context(channel_id)
                
                # Format the final query with the current user's message
                conversation_context.append({
                    "role": "user", 
                    "content": f"{message.author.display_name}: {content}"
                })
                
                # Send "thinking" message with typing indicator
                async with message.channel.typing():
                    # Send to API with images if applicable and channel-specific system prompt
                    response = await self.openrouter_client.send_message_with_history(
                        conversation_context,
                        images=images if self.openrouter_client.model_supports_vision() else [],
                        system_prompt=channel_system_prompt
                    )
                
                # Check if response is an error
                if response.startswith("⚠️"):
                    # If it's an error, don't split chunks and don't add to history
                    await message.channel.send(response)
                else:
                    # Add assistant's response to history
                    self.state.add_to_channel_history(channel_id, {
                        "role": "assistant",
                        "content": response,
                        "timestamp": datetime.now()
                    })
                    
                    # Split response into chunks of 2000 characters or fewer
                    max_length = 2000
                    chunks = [response[i:i+max_length] for i in range(0, len(response), max_length)]
                    
                    # Send each chunk as a separate message
                    for chunk in chunks:
                        await message.channel.send(chunk)
            
            finally:
                # Always restore the original model
                self.openrouter_client.model = current_model

def setup(bot):
    bot.add_cog(MentionCommands(bot))
