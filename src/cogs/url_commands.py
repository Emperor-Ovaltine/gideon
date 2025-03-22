"""Commands for URL processing and summarization."""
import discord
from discord.ext import commands
import aiohttp
from bs4 import BeautifulSoup
import logging
from ..utils.state_manager import BotStateManager
from ..utils.openrouter_client import OpenRouterClient
from ..config import OPENROUTER_API_KEY, SYSTEM_PROMPT, DEFAULT_MODEL

# Set up logging
logger = logging.getLogger('url_commands')

class URLCommands(commands.Cog):
    """Commands for analyzing and summarizing web content."""
    
    def __init__(self, bot):
        self.bot = bot
        self.state = BotStateManager()
        self.openrouter_client = OpenRouterClient(OPENROUTER_API_KEY, SYSTEM_PROMPT, DEFAULT_MODEL)
    
    @discord.slash_command(
        name="summarize_url",
        description="Summarize content from a web page"
    )
    async def summarize_url_slash(self, ctx, 
                                url: str, 
                                detailed: bool = False):
        """Fetch and summarize content from a URL."""
        await ctx.defer()
        
        # Set the right model
        channel_id = str(ctx.channel.id)
        current_model = self.openrouter_client.model
        model_to_use = self.state.get_effective_model(channel_id)
        self.openrouter_client.model = model_to_use
        
        try:
            # Notify user that processing has started
            processing_msg = await ctx.respond(f"📄 Fetching content from: {url}")
            
            # Fetch the webpage content
            async with aiohttp.ClientSession() as session:
                async with session.get(url, timeout=30) as response:
                    if response.status != 200:
                        await ctx.followup.send(f"⚠️ Error: Could not access URL (Status code: {response.status})")
                        return
                    
                    html = await response.text()
            
            # Parse the HTML to extract text
            soup = BeautifulSoup(html, 'html.parser')
            
            # Remove script and style elements
            for script in soup(["script", "style", "header", "footer", "nav"]):
                script.extract()
            
            # Get page title
            title = soup.title.string if soup.title else "No title found"
            
            # Get main text content
            text = soup.get_text(separator='\n')
            
            # Clean up text - remove extra whitespace
            lines = (line.strip() for line in text.splitlines())
            chunks = (line for line in lines if line)
            text = '\n'.join(chunks)
            
            # Truncate if too long
            if len(text) > 12000:
                text = text[:12000] + "... [content truncated due to length]"
            
            # Update status message
            await ctx.edit(content=f"📝 Analyzing content from: {url}")
            
            # Create the summary prompt based on detail level
            if detailed:
                summary_prompt = f"Please provide a detailed summary of this web page content in bullet point format, organized by sections. Include key information, main arguments, and important data points:\n\nTitle: {title}\n\nContent: {text}"
            else:
                summary_prompt = f"Please provide a concise summary (5-7 bullet points) of this web page content:\n\nTitle: {title}\n\nContent: {text}"
            
            # Send to AI
            response = await self.openrouter_client.send_message_with_history([
                {"role": "system", "content": "You are a helpful AI that summarizes web content clearly and accurately."},
                {"role": "user", "content": summary_prompt}
            ])
            
            # Create embed
            embed = discord.Embed(
                title=f"Summary of: {title}",
                description=response,
                color=discord.Color.blue(),
                url=url
            )
            embed.set_footer(text=f"Requested by {ctx.author.display_name} • {model_to_use}")
            
            # Send response
            await ctx.edit(embed=embed)
            
        except Exception as e:
            logger.error(f"Error processing URL: {str(e)}", exc_info=True)
            await ctx.respond(f"⚠️ Error processing URL: {str(e)}")
        finally:
            # Restore original model
            self.openrouter_client.model = current_model

def setup(bot):
    bot.add_cog(URLCommands(bot))
