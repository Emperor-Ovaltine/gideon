"""Core chat commands for the AI assistant."""
import discord
import asyncio
import socket
import re  # Add this import here
from discord.ext import commands
from ..utils.state_manager import BotStateManager
from ..utils.conversation import get_channel_context
from ..utils.openrouter_client import OpenRouterClient
from ..config import OPENROUTER_API_KEY, SYSTEM_PROMPT, ALLOWED_MODELS, DEFAULT_MODEL
from datetime import datetime

class ChatCommands(commands.Cog):
    """Commands for basic AI chat functionality."""
    
    def __init__(self, bot):
        self.bot = bot
        self.state = BotStateManager()
        self.openrouter_client = OpenRouterClient(OPENROUTER_API_KEY, SYSTEM_PROMPT, DEFAULT_MODEL)
    
    async def check_internet_connection(self):
        """Check if the bot has an internet connection."""
        try:
            # Try to resolve a well-known domain
            await asyncio.get_event_loop().getaddrinfo('google.com', 443)
            return True
        except socket.gaierror:
            return False

    def get_model_for_channel(self, channel_id):
        """Get the appropriate model for this channel"""
        return self.state.get_effective_model(channel_id)
        
    def format_perplexity_response(self, response_text):
        """
        Formats model responses into embeds with pagination.
        Returns a list of embed objects ready to be displayed.
        """
        # Create embeds with pagination
        embeds = []
        
        # Split main content into chunks of ~4000 characters (embed description limit is 4096)
        # Try to split on paragraph boundaries
        paragraphs = response_text.split('\n\n')
        current_embed = discord.Embed(
            title="AI Response",
            color=discord.Color.blue()
        )
        current_content = ""
        
        for paragraph in paragraphs:
            # If adding this paragraph would exceed the limit, create a new embed
            if len(current_content) + len(paragraph) + 2 > 4000:  # +2 for the \n\n
                current_embed.description = current_content
                embeds.append(current_embed)
                current_embed = discord.Embed(
                    title="AI Response (continued)",
                    color=discord.Color.blue()
                )
                current_content = paragraph
            else:
                if current_content:
                    current_content += "\n\n" + paragraph
                else:
                    current_content = paragraph
        
        # Don't forget the last embed
        if current_content:
            current_embed.description = current_content
            embeds.append(current_embed)
        
        # If no embeds were created (unlikely), create a default one
        if not embeds:
            embeds.append(discord.Embed(
                title="AI Response",
                description=response_text[:4000] if len(response_text) > 4000 else response_text,
                color=discord.Color.blue()
            ))
        
        # Add page numbers
        for i, embed in enumerate(embeds):
            embed.set_footer(text=f"Page {i+1}/{len(embeds)}")
        
        return embeds

    def is_citation_based_model(self, model_name):
        """
        Determines if a model uses citations/footnotes in its responses.
        
        Args:
            model_name (str): The model identifier
            
        Returns:
            bool: True if the model typically uses citations
        """
        if not model_name:
            return False
            
        # Common identifiers for citation-based models, using more standardized patterns
        citation_identifiers = [
            "sonar",
            "perplexity", 
            "pplx",
            "claude-3",  # Covers all Claude 3 models
            "fireworks/mixtral",
            "anthropic/claude"
        ]
        
        model_lower = str(model_name).lower()
        
        # More detailed logging about the model name
        print(f"Checking citation model: '{model_name}' (lower: '{model_lower}')")
        
        # Check if model contains any of the citation identifiers
        for identifier in citation_identifiers:
            if identifier in model_lower:
                print(f"✅ Model '{model_name}' identified as citation-based (matches '{identifier}')")
                return True
                
        print(f"❌ Model '{model_name}' is NOT identified as citation-based")
        return False
        
    def should_format_citations(self, model_name, response_text):
        """
        Determines if a response should be formatted for citations.
        Checks both the model name and if the response appears to contain citations.
        
        Args:
            model_name (str): The model identifier
            response_text (str): The model's response
            
        Returns:
            bool: True if the response should be formatted for citations
        """
        import re
        
        # Explicitly check for Sonar first
        if "sonar" in str(model_name).lower() or "perplexity" in str(model_name).lower():
            print(f"✅ Direct match for Sonar/Perplexity model: {model_name}")
            return True
            
        # More robust pattern to detect footnote-style citations
        # Looks for [number] patterns that likely indicate footnotes
        footnote_pattern = r'\[\d+\](?:\s+|\n|$)'
        has_citation_format = bool(re.search(footnote_pattern, response_text))
        
        # Check for citation section markers
        has_reference_section = any(marker in response_text.lower() for marker in 
                                 ["sources:", "references:", "citations:", "footnotes:"])
        
        # Is this a known citation model?
        is_citation_model = self.is_citation_based_model(model_name)
        
        # Log detailed detection info
        print(f"Citation detection for '{model_name}':")
        print(f"- Is known citation model: {is_citation_model}")
        print(f"- Has citation format: {has_citation_format}")
        print(f"- Has reference section: {has_reference_section}")
        
        # More permissive logic:
        # 1. It's a known citation model OR
        # 2. It has citation format OR
        # 3. It has a reference section
        should_format = is_citation_model or has_citation_format or has_reference_section
        print(f"Citation formatting decision: {should_format}")
        
        return should_format

    @discord.slash_command(
        name="chat",
        description="Send a message to the AI assistant"
    )
    async def chat_slash(self, ctx, 
                         message: str,
                         image: discord.Attachment = None):
        await ctx.defer()
        
        # Check internet connection first
        if not await self.check_internet_connection():
            await ctx.respond("⚠️ Network issue: Unable to connect to the internet. Please check your connection and try again.")
            return
        
        # Get channel ID to track conversation per channel
        channel_id = str(ctx.channel.id)
        
        # Initialize this channel's history if it doesn't exist
        if channel_id not in self.state.channel_history:
            self.state.channel_history[channel_id] = []
        
        # Determine which model to use for this channel
        current_model = self.openrouter_client.model  # Store original model
        model_to_use = self.get_model_for_channel(channel_id)  # Get effective model for this channel
        
        # Set the model to use for this request
        self.openrouter_client.model = model_to_use
        
        # Log which model is being used for debugging
        print(f"Using model for channel {channel_id}: {model_to_use}")

        # Check if the model supports images
        model_supports_images = self.openrouter_client.model_supports_vision()
        
        # Process image if provided and model supports it
        images = []
        image_embed = None
        
        if image:
            # Check if it's an image file
            if any(image.filename.lower().endswith(ext) for ext in ['.jpg', '.jpeg', '.png', '.gif', '.webp']):
                # Create an embed to display the image
                image_embed = discord.Embed(title="Analyzing Image", color=discord.Color.blue())
                image_embed.set_image(url=image.url)
                image_embed.add_field(name="File", value=image.filename)
                
                if model_supports_images:
                    try:
                        # Download the image data
                        image_data = await image.read()
                        images.append({
                            'data': image_data,
                            'type': image.content_type or 'image/jpeg'  # Default to jpeg if not specified
                        })
                    except Exception as e:
                        await ctx.respond(f"⚠️ Failed to process image {image.filename}: {str(e)}")
                        return
                else:
                    image_embed.description = "⚠️ Current model doesn't support image analysis. Consider switching to a vision-capable model."
        
        # Get channel-specific system prompt if it exists
        channel_system_prompt = self.state.get_channel_system_prompt(channel_id)
        
        try:
            # Get recent channel context
            conversation_context = await get_channel_context(channel_id)
            
            # Add this new message
            self.state.add_to_channel_history(channel_id, {
                "role": "user",
                "name": ctx.author.display_name,
                "content": message,
                "timestamp": datetime.now()
            })
            
            # Format the final query with the current user's question
            conversation_context.append({
                "role": "user", 
                "content": f"{ctx.author.display_name}: {message}"
            })
            
            # First response - show the user's message
            if image_embed:
                await ctx.respond(f"**{ctx.author.display_name}**: {message}", embed=image_embed)
            else:
                # Show user's message (without processing note)
                await ctx.respond(f"**{ctx.author.display_name}**: {message}")
            
            # Always send a separate processing message that we'll edit
            processing_msg = await ctx.followup.send("Processing response...")
                
            # Send to API with images if applicable and channel-specific system prompt
            response = await self.openrouter_client.send_message_with_history(
                conversation_context,
                images=images if model_supports_images else [],
                system_prompt=channel_system_prompt
            )
            
            # Check if response is an error
            if response.startswith("⚠️"):
                # If it's an error, don't split chunks and don't add to history
                await processing_msg.edit(content=response)
            else:
                # Add assistant's response to history
                self.state.add_to_channel_history(channel_id, {
                    "role": "assistant",
                    "content": response,
                    "timestamp": datetime.now()
                })
                
                # Debug logs for better troubleshooting
                is_citation_model = self.is_citation_based_model(model_to_use)
                has_citation_format = bool(re.search(r'\[\d+\]', response))
                print(f"Model: {model_to_use}, Is citation model: {is_citation_model}, Has citation format: {has_citation_format}")
                
                # Format responses from models that use citations as paginated embeds
                if self.should_format_citations(model_to_use, response):
                    print(f"Formatting response from {model_to_use} with citations")
                    embeds = self.format_perplexity_response(response)
                    
                    # Send the first embed by editing the processing message
                    if embeds:
                        await processing_msg.edit(content=None, embed=embeds[0])
                        
                        # Send additional embeds if there are more than one
                        for embed in embeds[1:]:
                            await ctx.channel.send(embed=embed)
                else:
                    print(f"Using standard formatting for model {model_to_use}")
                    # For non-Sonar models, use the original text response approach
                    # Split response into chunks of 2000 characters or fewer
                    max_length = 2000
                    chunks = [response[i:i+max_length] for i in range(0, len(response), max_length)]
                    
                    # Send each chunk as a separate message
                    for i, chunk in enumerate(chunks):
                        if i == 0:
                            # Always edit the processing message with first chunk
                            await processing_msg.edit(content=chunk)
                        else:
                            await ctx.channel.send(chunk)
        finally:
            # Always restore the original model
            self.openrouter_client.model = current_model

    @discord.slash_command(
        name="reset",
        description="Reset the conversation history for this channel"
    )
    async def reset_slash(self, ctx):
        channel_id = str(ctx.channel.id)
        if self.state.clear_channel_history(channel_id):
            await ctx.respond("The conversation history for this channel has been reset.")
        else:
            await ctx.respond("No conversation history found for this channel.")

    @discord.slash_command(
        name="memory",
        description="Show how many messages are stored for this channel"
    )
    async def channel_memory_slash(self, ctx):
        channel_id = str(ctx.channel.id)
        history = self.state.get_channel_history(channel_id)
        if history:
            history_length = len(history)
            await ctx.respond(f"Currently storing {history_length} messages for this channel, spanning up to {self.state.time_window_hours} hours.")
        else:
            await ctx.respond("No conversation history found for this channel.")
            
    @discord.slash_command(
        name="summarize",
        description="Summarize the current conversation history"
    )
    async def summarize_slash(self, ctx):
        await ctx.defer()
        channel_id = str(ctx.channel.id)
        history = self.state.get_channel_history(channel_id)
        if not history:
            await ctx.respond("No conversation history to summarize.")
            return
            
        await ctx.respond("Generating conversation summary...")
        
        conversation_context = await get_channel_context(channel_id)
        summary_request = [
            {"role": "system", "content": "Summarize the following conversation in 3-5 bullet points:"},
            {"role": "user", "content": "\n".join([msg["content"] for msg in conversation_context])}
        ]
        
        summary = await self.openrouter_client.send_message_with_history(summary_request)
        await ctx.respond(f"**Conversation Summary:**\n{summary}")

def setup(bot):
    bot.add_cog(ChatCommands(bot))
