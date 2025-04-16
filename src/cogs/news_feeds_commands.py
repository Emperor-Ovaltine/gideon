"""Commands for managing and displaying news feed summaries."""
import discord
from discord.ext import commands, tasks
import aiohttp
import feedparser
import asyncio
import logging
from datetime import datetime, timedelta, timezone
from ..utils.state_manager import BotStateManager
from ..utils.openrouter_client import OpenRouterClient
from ..config import OPENROUTER_API_KEY, SYSTEM_PROMPT, DEFAULT_MODEL

# Set up logging
logger = logging.getLogger('news_feeds')

class NewsFeedsCommands(commands.Cog):
    """Commands for managing and displaying news feed summaries."""
    
    def __init__(self, bot):
        self.bot = bot
        self.state = BotStateManager()
        self.openrouter_client = OpenRouterClient(OPENROUTER_API_KEY, SYSTEM_PROMPT, DEFAULT_MODEL)
        
        # Make sure these attributes exist and are properly initialized
        if not hasattr(self.state, 'news_feeds'):
            logger.info("Initializing news_feeds in state manager")
            self.state.news_feeds = {}
        else:
            logger.info(f"Loaded existing news_feeds with {len(self.state.news_feeds)} feeds")
        
        if not hasattr(self.state, 'news_channel_config'):
            logger.info("Initializing news_channel_config in state manager")
            self.state.news_channel_config = {}
        else:
            logger.info(f"Loaded existing news_channel_config with {len(self.state.news_channel_config)} channels")
            
        if not hasattr(self.state, 'news_article_history'):
            logger.info("Initializing news_article_history in state manager")
            self.state.news_article_history = {}
        else:
            logger.info(f"Loaded existing news_article_history with {len(self.state.news_article_history)} feeds")
            
        # Initialize update frequency setting if it doesn't exist (default: 6 hours)
        if not hasattr(self.state, 'news_update_frequency'):
            logger.info("Initializing news_update_frequency in state manager")
            self.state.news_update_frequency = 6  # Default: 6 hours
        else:
            logger.info(f"Loaded existing news_update_frequency: {self.state.news_update_frequency} hours")
            
        # Start the background task when the cog is loaded
        self.check_news_feeds.cancel()  # Cancel any existing task
        self.check_news_feeds.change_interval(hours=self.state.news_update_frequency)
        self.check_news_feeds.start()
        
        # Log the loaded feeds for debugging
        if hasattr(self.state, 'news_feeds') and self.state.news_feeds:
            for feed_id, feed in self.state.news_feeds.items():
                logger.info(f"Loaded feed: {feed.get('name', 'Unknown')} ({feed_id})")
    
    def cog_unload(self):
        """Stop tasks when the cog is unloaded."""
        self.check_news_feeds.cancel()
    
    @tasks.loop(hours=6)  # Define default interval (will be overridden by change_interval)
    async def check_news_feeds(self):
        """Background task to check feeds based on configured frequency."""
        logger.info(f"Starting scheduled news feed check (every {self.state.news_update_frequency} hours)")
        await self.process_all_feeds()
    
    @check_news_feeds.before_loop
    async def before_check_news_feeds(self):
        """Wait until the bot is ready before starting the task."""
        await self.bot.wait_until_ready()
        logger.info("News feed check task initialized")
    
    async def process_all_feeds(self):
        """Process all feeds and send updates to configured channels."""
        if not self.state.news_feeds:
            logger.info("No news feeds configured, skipping check")
            return
            
        for feed_id, feed_info in self.state.news_feeds.items():
            try:
                new_articles = await self.fetch_new_articles(feed_id)
                if not new_articles:
                    continue
                    
                # Send updates to all configured channels
                await self.send_feed_updates(feed_id, feed_info['category'], new_articles)
                
            except Exception as e:
                logger.error(f"Error processing feed {feed_id}: {str(e)}", exc_info=True)
    
    async def fetch_new_articles(self, feed_id, force_refresh=False):
        """Fetch and return new articles from a feed.
        
        Args:
            feed_id: The ID of the feed to fetch
            force_refresh: If True, ignore history and fetch recent articles
        """
        feed_info = self.state.news_feeds.get(feed_id)
        if not feed_info:
            logger.warning(f"Feed ID {feed_id} not found in news_feeds")
            return []
            
        try:
            # Using synchronous feedparser with run_in_executor for async compatibility
            feed = await asyncio.get_event_loop().run_in_executor(
                None, feedparser.parse, feed_info['url']
            )
            
            if not feed or hasattr(feed, 'status') and feed.status >= 400:
                logger.warning(f"Failed to fetch feed {feed_id}: HTTP {feed.get('status', 'unknown')}")
                return []
                
            # Initialize article history for this feed if not exists
            if feed_id not in self.state.news_article_history:
                self.state.news_article_history[feed_id] = {}
                
            # Get current time
            now = datetime.now()
            
            # Find new entries (deduplication happens here)
            new_entries = []
            for entry in feed.entries[:10]:  # Limit to the latest 10 entries
                entry_id = entry.get('id', entry.get('link', ''))
                if not entry_id:
                    continue
                    
                # Skip if we've seen this article before (unless force_refresh is True)
                if not force_refresh and entry_id in self.state.news_article_history[feed_id]:
                    logger.debug(f"Skipping already processed article: {entry.get('title', 'Unknown')}")
                    continue
                    
                # Add to new entries and update history
                new_entries.append(entry)
                self.state.news_article_history[feed_id][entry_id] = now.timestamp()
            
            # Update last checked time
            feed_info['last_checked'] = now.timestamp()
            
            # Clean up old history (keeping last 7 days)
            cutoff = now - timedelta(days=7)
            count_before = len(self.state.news_article_history[feed_id])
            for entry_id in list(self.state.news_article_history[feed_id]):
                timestamp = self.state.news_article_history[feed_id][entry_id]
                if datetime.fromtimestamp(timestamp) < cutoff:
                    del self.state.news_article_history[feed_id][entry_id]
            count_after = len(self.state.news_article_history[feed_id])
            
            if count_before > count_after:
                logger.info(f"Cleaned up {count_before - count_after} old entries from history for feed {feed_id}")
            
            logger.info(f"Found {len(new_entries)} new articles for feed {feed_id}")
            return new_entries
            
        except Exception as e:
            logger.error(f"Error fetching feed {feed_id}: {str(e)}", exc_info=True)
            return []
    
    def truncate_for_embed(self, text, max_length=1000):
        """Truncate text to be safely under Discord's embed field character limit.
        
        Args:
            text: The text to truncate
            max_length: Maximum length (default: 1000 to leave room for additional formatting)
            
        Returns:
            Truncated text with ellipsis if needed
        """
        if len(text) <= max_length:
            return text
            
        # Truncate and add ellipsis
        return text[:max_length] + "..."
    
    async def summarize_article(self, article, feed_category):
        """Summarize a news article using AI."""
        try:
            # Extract article information
            title = article.get('title', 'No title')
            link = article.get('link', '')
            published = article.get('published', datetime.now().strftime('%Y-%m-%d %H:%M:%S'))
            
            # Get content - try different fields that might contain the article text
            content = article.get('content', [{'value': ''}])[0].get('value', '')
            if not content:
                content = article.get('summary', '')
            
            # Prepare summarization prompt - More direct instruction
            prompt = f"Provide a summary of the following news article as 3-4 concise bullet points. Output *only* the bullet points, nothing else:\n\nTitle: {title}\n\nDate: {published}\n\nCategory: {feed_category}\n\nContent: {content}"
            
            # Send to AI for summarization - Updated system prompt
            response = await self.openrouter_client.send_message_with_history([
                {"role": "system", "content": "You are an AI assistant that strictly summarizes news articles into bullet points. Provide *only* the bullet points as your response. Do not add any introductory text, concluding remarks, or conversational filler."},
                {"role": "user", "content": prompt}
            ])
            
            # Handle possible error
            if response.startswith("⚠️"):
                return {
                    "title": title,
                    "summary": "Unable to summarize this article.",
                    "link": link,
                    "published": published
                }
            
            return {
                "title": title,
                "summary": response.strip(), # Added strip() to remove potential leading/trailing whitespace
                "link": link,
                "published": published
            }
            
        except Exception as e:
            logger.error(f"Error summarizing article: {str(e)}", exc_info=True)
            return {
                "title": article.get('title', 'No title'),
                "summary": "Error generating summary.",
                "link": article.get('link', ''),
                "published": article.get('published', 'Unknown date')
            }
    
    async def send_feed_updates(self, feed_id, category, articles):
        """Send feed updates to all configured channels."""
        if not articles:
            return
            
        # Find channels that should receive this category
        channels_to_notify = []
        feed_category_str = category.lower()  # category from feed_info['category']
        # Create a set of the feed's categories for efficient checking
        feed_categories = {c.strip() for c in feed_category_str.split(',') if c.strip()}

        for channel_id, config in self.state.news_channel_config.items():
            # Create a set of the categories the channel is subscribed to
            channel_subscribed_categories = {c.strip() for c in config.get('categories', [])}
            
            # Check if channel subscribes to 'all' OR if any of the feed's categories match the channel's subscriptions
            if 'all' in channel_subscribed_categories or not feed_categories.isdisjoint(channel_subscribed_categories):
                channels_to_notify.append(channel_id)
        
        if not channels_to_notify:
            # Adjusted log message for clarity
            logger.info(f"No channels configured for categories [{', '.join(feed_categories)}], skipping feed {feed_id}")
            return
            
        # Summarize articles
        summaries = []
        
        # Limit to max 5 articles to avoid rate limiting or long processing
        # Pass the potentially multi-category string for context in summarization
        for article in articles[:5]:
            summary = await self.summarize_article(article, category) 
            if summary:
                summaries.append(summary)
                # Add slight delay to avoid hitting AI rate limits too hard
                await asyncio.sleep(1)
        
        # Send to each channel
        for channel_id in channels_to_notify:
            try:
                channel = self.bot.get_channel(int(channel_id))
                if not channel:
                    continue
                    
                # Create embed for feed
                feed_info = self.state.news_feeds.get(feed_id, {})
                feed_name = feed_info.get('name', 'News')
                
                embed = discord.Embed(
                    title=f"📰 {feed_name} News Update",
                    description=f"Latest articles from {category} category",
                    color=discord.Color.blue(),
                    timestamp=datetime.now()
                )
                
                # Add each summary to the embed
                for i, summary in enumerate(summaries):
                    # Skip if we already have too many fields (max 25)
                    if i >= 5:
                        break
                        
                    # Add summary as a field with truncation
                    truncated_summary = self.truncate_for_embed(f"{summary['summary']}\n\n[Read full article]({summary['link']})")
                    embed.add_field(
                        name=f"📄 {summary['title']}",
                        value=truncated_summary,
                        inline=False
                    )
                
                # Set footer
                embed.set_footer(text=f"Feed: {feed_name} | Category: {category}")
                
                # Send to channel
                await channel.send(embed=embed)
                
            except Exception as e:
                logger.error(f"Error sending to channel {channel_id}: {str(e)}", exc_info=True)
    
    async def send_news_to_channel(self, channel, feed_id, category, articles):
        """Send news updates to a specific channel."""
        if not articles:
            return
            
        # Summarize articles
        summaries = []
        
        # Limit to max 5 articles to avoid rate limiting or long processing
        for article in articles[:5]:
            summary = await self.summarize_article(article, category)
            if summary:
                summaries.append(summary)
                # Add slight delay to avoid hitting AI rate limits too hard
                await asyncio.sleep(1)
        
        if not summaries:
            return
            
        try:
            # Create embed for feed
            feed_info = self.state.news_feeds.get(feed_id, {})
            feed_name = feed_info.get('name', 'News')
            
            embed = discord.Embed(
                title=f"📰 {feed_name} News Update",
                description=f"Latest articles from {category} category",
                color=discord.Color.blue(),
                timestamp=datetime.now()
            )
            
            # Add each summary to the embed
            for i, summary in enumerate(summaries):
                # Skip if we already have too many fields (max 25)
                if i >= 5:
                    break
                    
                # Add summary as a field with truncation
                truncated_summary = self.truncate_for_embed(f"{summary['summary']}\n\n[Read full article]({summary['link']})")
                embed.add_field(
                    name=f"📄 {summary['title']}",
                    value=truncated_summary,
                    inline=False
                )
            
            # Set footer
            embed.set_footer(text=f"Feed: {feed_name} | Category: {category}")
            
            # Send to channel
            await channel.send(embed=embed)
                
        except Exception as e:
            logger.error(f"Error sending to requested channel: {str(e)}", exc_info=True)
    
    @discord.slash_command(
        name="addfeed",
        description="Add a new RSS news feed to monitor"
    )
    @commands.has_permissions(administrator=True)
    async def add_feed_slash(self, ctx,
                          url: discord.Option(str, "The URL of the RSS feed"),
                          name: discord.Option(str, "A name for this feed"),
                          category: discord.Option(str, "Category for this feed (tech, world, finance, etc.)")):
        """Add a new RSS feed to monitor."""
        await ctx.defer()
        
        # Validate the URL
        try:
            async with aiohttp.ClientSession() as session:
                async with session.get(url, timeout=10) as response:
                    if response.status != 200:
                        await ctx.respond(f"⚠️ Unable to access feed URL (Status: {response.status})")
                        return
                    
                    # Make sure it's an RSS feed
                    content_type = response.headers.get('Content-Type', '')
                    if not any(ct in content_type.lower() for ct in ['application/rss+xml', 'application/xml', 'text/xml']):
                        # Try parsing anyway just to be sure
                        content = await response.text()
                        
            # Parse feed to validate
            feed = await asyncio.get_event_loop().run_in_executor(
                None, feedparser.parse, url
            )
            
            if not hasattr(feed, 'entries') or len(feed.entries) == 0:
                await ctx.respond("⚠️ This URL doesn't appear to be a valid RSS feed.")
                return
                
            # Generate a unique ID for the feed
            feed_id = str(hash(url) % 10000000)
            
            # Add to feeds list
            self.state.news_feeds[feed_id] = {
                'url': url,
                'name': name,
                'category': category.lower(),
                'added_at': datetime.now().timestamp(),
                'last_checked': None,
                'last_entries': []
            }
            
            # Explicitly save state after adding a new feed
            from ..utils.persistence import StatePersistence
            persistence = StatePersistence()
            saved = persistence.save_state(self.state)
            
            embed = discord.Embed(
                title="✅ RSS Feed Added",
                description=f"Successfully added feed: **{name}**",
                color=discord.Color.green()
            )
            
            embed.add_field(
                name="Details", 
                value=f"**Category:** {category}\n**URL:** {url}\n**Feed ID:** {feed_id}",
                inline=False
            )
            
            embed.add_field(
                name="Next Steps",
                value=(
                    "Use `/subscribechannel` to set which channels receive updates "
                    "from this category.\n\n"
                    "Updates are sent automatically every 6 hours. "
                    "Use `/feedupdate` to fetch updates manually."
                ),
                inline=False
            )
            
            if saved:
                embed.set_footer(text="Feed configuration saved to persistent storage")
            else:
                embed.set_footer(text="⚠️ Warning: State could not be saved")
            
            await ctx.respond(embed=embed)
            
        except Exception as e:
            logger.error(f"Error adding feed: {str(e)}", exc_info=True)
            await ctx.respond(f"⚠️ Error: {str(e)}")
    
    @discord.slash_command(
        name="removefeed",
        description="Remove an RSS feed from monitoring"
    )
    @commands.has_permissions(administrator=True)
    async def remove_feed_slash(self, ctx,
                             feed_id: discord.Option(str, "The ID of the feed to remove")):
        """Remove an RSS feed from monitoring."""
        await ctx.defer()
        
        if feed_id in self.state.news_feeds:
            feed_info = self.state.news_feeds[feed_id]
            del self.state.news_feeds[feed_id]
            
            # Clean up article history
            if feed_id in self.state.news_article_history:
                del self.state.news_article_history[feed_id]
            
            # Explicitly save state after removing a feed
            from ..utils.persistence import StatePersistence
            persistence = StatePersistence()
            saved = persistence.save_state(self.state)
                
            await ctx.respond(f"✅ Removed feed: **{feed_info['name']}** ({feed_info['category']})" + 
                             (". State saved." if saved else "\n⚠️ Warning: State could not be saved."))
        else:
            await ctx.respond("⚠️ Feed not found. Use `/listfeeds` to see available feeds.")
    
    @discord.slash_command(
        name="listfeeds",
        description="List all configured RSS feeds"
    )
    async def list_feeds_slash(self, ctx):
        """List all configured RSS feeds."""
        await ctx.defer()
        
        if not self.state.news_feeds:
            await ctx.respond("No RSS feeds have been configured yet.")
            return
            
        embed = discord.Embed(
            title="📊 Configured RSS Feeds",
            description=f"Total feeds: {len(self.state.news_feeds)}",
            color=discord.Color.blue()
        )
        
        # Group feeds by category
        feeds_by_category = {}
        for feed_id, feed_info in self.state.news_feeds.items():
            category = feed_info['category']
            if category not in feeds_by_category:
                feeds_by_category[category] = []
            feeds_by_category[category].append((feed_id, feed_info))
        
        # Add fields for each category
        for category, feeds in feeds_by_category.items():
            feed_list = []
            for feed_id, feed in feeds:
                last_checked = "Never"
                if feed['last_checked']:
                    last_checked = datetime.fromtimestamp(feed['last_checked']).strftime('%Y-%m-%d %H:%M')
                
                feed_list.append(f"• **{feed['name']}** (ID: {feed_id})\n  Last checked: {last_checked}")
            
            embed.add_field(
                name=f"📰 {category.title()} ({len(feeds)})",
                value="\n".join(feed_list) or "No feeds",
                inline=False
            )
        
        await ctx.respond(embed=embed)
    
    @discord.slash_command(
        name="subscribechannel",
        description="Subscribe this channel to news categories"
    )
    @commands.has_permissions(administrator=True)
    async def subscribe_channel_slash(self, ctx,
                                   categories: discord.Option(str, "Categories to subscribe to (comma-separated, or 'all')")):
        """Subscribe the current channel to specific news categories."""
        await ctx.defer()
        
        channel_id = str(ctx.channel.id)
        
        # Parse categories
        if categories.lower().strip() == 'all':
            category_list = ['all']
        else:
            category_list = [c.lower().strip() for c in categories.split(',') if c.strip()]
            
        if not category_list:
            await ctx.respond("⚠️ Please provide at least one category.")
            return
            
        # Update channel configuration
        if channel_id not in self.state.news_channel_config:
            self.state.news_channel_config[channel_id] = {
                'categories': category_list
            }
        else:
            self.state.news_channel_config[channel_id]['categories'] = category_list
            
        # Explicitly save state after updating channel configuration
        from ..utils.persistence import StatePersistence
        persistence = StatePersistence()
        saved = persistence.save_state(self.state)
            
        # Create description of the categories
        if 'all' in category_list:
            categories_desc = "all categories"
        else:
            categories_desc = ", ".join(category_list)
            
        await ctx.respond(f"✅ This channel will now receive news updates for {categories_desc}." + 
                         (f" Configuration saved." if saved else f"\n⚠️ Warning: State could not be saved."))
    
    @discord.slash_command(
        name="unsubscribechannel",
        description="Unsubscribe this channel from news updates"
    )
    @commands.has_permissions(administrator=True)
    async def unsubscribe_channel_slash(self, ctx):
        """Unsubscribe the current channel from news updates."""
        await ctx.defer()
        
        channel_id = str(ctx.channel.id)
        
        if channel_id in self.state.news_channel_config:
            del self.state.news_channel_config[channel_id]
            await ctx.respond("✅ This channel will no longer receive news updates.")
        else:
            await ctx.respond("ℹ️ This channel is not currently subscribed to news updates.")
    
    @discord.slash_command(
        name="feedupdate",
        description="Manually update and post news from all feeds"
    )
    @commands.has_permissions(administrator=True)
    async def update_feeds_slash(self, ctx, 
                               force_refresh: discord.Option(bool, 
                                                         "Force refresh articles even if already seen", 
                                                         required=False, 
                                                         default=False)):
        """Manually trigger an update of all feeds.
        
        Args:
            force_refresh: If True, fetch recent articles regardless of history
        """
        await ctx.defer()
        
        # Log the current state for debugging
        logger.info(f"Current news_feeds count: {len(self.state.news_feeds)}")
        for feed_id, feed in self.state.news_feeds.items():
            logger.info(f"Feed: {feed.get('name', 'Unknown')} ({feed_id}) - URL: {feed.get('url', 'Unknown')}")
        
        # Start a background task to process feeds
        await ctx.respond(f"🔄 Starting news feed update{'  (Force refresh mode)' if force_refresh else ''}...")
        
        if not self.state.news_feeds:
            await ctx.followup.send("⚠️ No feeds configured. Use `/addfeed` to add feeds first.")
            return
            
        try:
            # Process feeds with force_refresh option
            updates_processed = 0
            for feed_id, feed_info in self.state.news_feeds.items():
                logger.info(f"Processing feed: {feed_info.get('name')} ({feed_id})")
                
                # Pass the force_refresh parameter to fetch_new_articles
                new_articles = await self.fetch_new_articles(feed_id, force_refresh=force_refresh)
                
                if new_articles:
                    updates_processed += 1
                    # Send updates to all configured channels
                    await self.send_feed_updates(feed_id, feed_info['category'], new_articles)
            
            # Make sure state changes get saved
            from ..utils.persistence import StatePersistence
            persistence = StatePersistence()
            saved = persistence.save_state(self.state)
            
            if updates_processed > 0:
                await ctx.followup.send(f"✅ News feed update completed. Processed updates for {updates_processed} feeds. State {'saved' if saved else 'NOT saved'}.")
            else:
                await ctx.followup.send(f"ℹ️ No new articles found for any feeds. Try again with 'force_refresh' option if needed. State {'saved' if saved else 'NOT saved'}.")
                
        except Exception as e:
            logger.error(f"Error in manual feed update: {str(e)}", exc_info=True)
            await ctx.followup.send(f"⚠️ Error during update: {str(e)}")
    
    @discord.slash_command(
        name="getnews",
        description="Get the latest news updates from configured feeds"
    )
    async def get_news_slash(self, ctx,
                           category: discord.Option(str, "Optional: Filter by category", required=False) = None,
                           force_refresh: discord.Option(bool, "Force fetch articles even if already seen", required=False) = False):
        """Fetch and display latest news from configured feeds."""
        await ctx.defer()
        
        if not self.state.news_feeds:
            await ctx.respond("No RSS feeds have been configured yet. Ask an administrator to add some feeds.")
            return
        
        await ctx.respond(f"🔍 Fetching the latest news updates{' (Force refresh mode)' if force_refresh else ''}...")
        
        try:
            # Process all feeds or filter by category
            processed_feeds = 0
            updates_found = False
            
            requested_category_lower = category.lower().strip() if category else None
            
            for feed_id, feed_info in self.state.news_feeds.items():
                # Skip if category filter is provided and doesn't match
                if requested_category_lower and requested_category_lower != 'all':
                    feed_category_str = feed_info.get('category', '').lower()
                    # Split the feed's categories (which might be comma-separated)
                    feed_categories = [c.strip() for c in feed_category_str.split(',')]
                    # Check if the requested category is present in the feed's categories
                    if requested_category_lower not in feed_categories:
                        continue
                
                processed_feeds += 1
                # Pass force_refresh to ensure we can get fresh articles
                new_articles = await self.fetch_new_articles(feed_id, force_refresh=force_refresh)
                
                if new_articles:
                    updates_found = True
                    # Create a method to send to just this channel
                    await self.send_news_to_channel(ctx.channel, feed_id, feed_info['category'], new_articles)
            
            if processed_feeds == 0 and requested_category_lower and requested_category_lower != 'all':
                await ctx.followup.send(f"⚠️ No feeds found with category: '{category}'")
            elif not updates_found:
                await ctx.followup.send("ℹ️ No new updates found in the configured feeds. Try again with 'force_refresh' option to see recent articles.")
            else:
                # Only send this if updates were actually found and sent
                if updates_found:
                    await ctx.followup.send("✅ News updates fetched and displayed.")
                
            # Ensure state is saved after processing
            from ..utils.persistence import StatePersistence
            persistence = StatePersistence()
            persistence.save_state(self.state)
                
        except Exception as e:
            logger.error(f"Error in get_news command: {str(e)}", exc_info=True)
            await ctx.followup.send(f"⚠️ Error fetching news: {str(e)}")
    
    @discord.slash_command(
        name="setfeedfrequency",
        description="Set how often the bot checks for news feed updates (in hours)"
    )
    @commands.has_permissions(administrator=True)
    async def set_feed_frequency_slash(self, ctx,
                                   hours: discord.Option(int, "Hours between feed checks (1-24)", 
                                                     min_value=1, max_value=24, required=True)):
        """Set how often the bot checks for news feed updates."""
        await ctx.defer()
        
        # Update frequency in state
        old_frequency = self.state.news_update_frequency
        self.state.news_update_frequency = hours
        
        # Update the task interval - safely restart it
        try:
            # Check if task is running before trying to cancel
            if self.check_news_feeds.is_running():
                self.check_news_feeds.cancel()
                
            # Reconfigure the task with new interval
            self.check_news_feeds.change_interval(hours=hours)
            
            # Only start if it's not already running
            if not self.check_news_feeds.is_running():
                self.check_news_feeds.start()
            
            task_updated = True
        except Exception as e:
            logger.error(f"Error updating feed check task: {str(e)}", exc_info=True)
            task_updated = False
        
        # Save state
        from ..utils.persistence import StatePersistence
        persistence = StatePersistence()
        saved = persistence.save_state(self.state)
        
        # Send confirmation
        status_message = f"✅ Feed update frequency changed from {old_frequency} to {hours} hours."
        if not task_updated:
            status_message += f"\n⚠️ Warning: Task could not be updated, but will apply on restart."
        status_message += (f" Configuration saved." if saved else f"\n⚠️ Warning: State could not be saved.")
        
        await ctx.respond(status_message)
        
        logger.info(f"Feed update frequency changed to {hours} hours")
    
    @discord.slash_command(
        name="feedstatus",
        description="Show status of news feed processing"
    )
    async def feed_status_slash(self, ctx):
        """Show the current status of feed processing."""
        await ctx.defer()
        
        if not self.state.news_feeds:
            await ctx.respond("No RSS feeds have been configured yet.")
            return
            
        embed = discord.Embed(
            title="📊 News Feed Status",
            description="Current status of news feed processing",
            color=discord.Color.blue(),
            timestamp=datetime.now()
        )
        
        # Add feed information
        feed_status = []
        for feed_id, feed in self.state.news_feeds.items():
            last_checked = "Never"
            if feed['last_checked']:
                # Calculate time since last check
                last_time = datetime.fromtimestamp(feed['last_checked'])
                time_diff = datetime.now() - last_time
                hours = time_diff.total_seconds() / 3600
                
                if hours < 1:
                    last_checked = f"{int(time_diff.total_seconds() / 60)} minutes ago"
                else:
                    last_checked = f"{int(hours)} hours ago"
            
            feed_status.append(f"• **{feed['name']}** ({feed['category']}): Last checked {last_checked}")
        
        embed.add_field(
            name="Feeds",
            value="\n".join(feed_status) or "No feeds configured",
            inline=False
        )
        
        # Add channel subscription information
        channel_info = []
        for channel_id, config in self.state.news_channel_config.items():
            try:
                channel = self.bot.get_channel(int(channel_id))
                channel_name = f"#{channel.name}" if channel else f"Unknown ({channel_id})"
                
                if 'all' in config['categories']:
                    categories = "All categories"
                else:
                    categories = ", ".join(config['categories'])
                    
                channel_info.append(f"• {channel_name}: {categories}")
            except:
                continue
        
        embed.add_field(
            name="Channel Subscriptions",
            value="\n".join(channel_info) or "No channel subscriptions",
            inline=False
        )
        
        # Update global schedule information to include the current frequency
        next_check = self.check_news_feeds.next_iteration
        if next_check:
            # Make sure we're using timezone-aware datetime for comparison
            now = datetime.now(timezone.utc)
            time_until = next_check - now
            minutes = time_until.total_seconds() / 60
            
            if minutes < 0:
                schedule_info = "Check due now"
            elif minutes < 60:
                schedule_info = f"Next check in {int(minutes)} minutes"
            else:
                schedule_info = f"Next check in {int(minutes/60)} hours, {int(minutes%60)} minutes"
        else:
            schedule_info = "Schedule not active"
            
        embed.add_field(
            name="Global Schedule",
            value=f"{schedule_info}\nUpdates occur every {self.state.news_update_frequency} hours",
            inline=False
        )
        
        await ctx.respond(embed=embed)

def setup(bot):
    """Add the NewsFeedsCommands cog to the bot."""
    bot.add_cog(NewsFeedsCommands(bot))
    print("NewsFeedsCommands cog loaded")
