"""Commands for managing and displaying news feed summaries."""
import discord
from discord.ext import commands, tasks
from discord import Option # Import Option for slash commands
import discord.ui # Import ui components
import aiohttp
import feedparser
import asyncio
import logging
from datetime import datetime, timedelta, timezone
import re # Import regex module
import json # Import json for parsing
from discord.ext import pages # Import pages
from typing import Optional, Dict, Any, List

from ..utils.state_manager import BotStateManager
from ..utils.openrouter_client import OpenRouterClient
from ..config import OPENROUTER_API_KEY, SYSTEM_PROMPT, DEFAULT_MODEL

# Set up logging
logger = logging.getLogger('news_feeds')

# --- Custom Paginator View ---
class DigestPaginatorView(discord.ui.View):
    def __init__(self, embeds, timeout=300): # 5 minute timeout for interaction
        super().__init__(timeout=timeout)
        if not embeds:
            raise ValueError("Embeds list cannot be empty for PaginatorView")
        self.embeds = embeds
        self.current_page = 0
        self.message = None # To store the message object for editing on timeout

        # Initial button state
        self._update_buttons()

    def _update_buttons(self):
        """Disables/enables buttons based on current page."""
        if hasattr(self, 'prev_button'): # Check if buttons exist
            self.prev_button.disabled = self.current_page == 0
        if hasattr(self, 'next_button'):
            self.next_button.disabled = self.current_page >= len(self.embeds) - 1

    async def show_page(self, interaction: discord.Interaction):
        """Edits the message to show the current page."""
        self.current_page = max(0, min(self.current_page, len(self.embeds) - 1))
        self._update_buttons()
        await interaction.response.edit_message(embed=self.embeds[self.current_page], view=self)

    @discord.ui.button(label="⬅️ Previous", style=discord.ButtonStyle.blurple, custom_id="digest_prev_page")
    async def prev_button(self, button: discord.ui.Button, interaction: discord.Interaction): # Swapped parameter order
        if self.current_page > 0:
            self.current_page -= 1
            await self.show_page(interaction) # Pass the interaction object
        else:
            # Defer if already on the first page to acknowledge the interaction
            await interaction.response.defer()

    @discord.ui.button(label="Next ➡️", style=discord.ButtonStyle.blurple, custom_id="digest_next_page")
    async def next_button(self, button: discord.ui.Button, interaction: discord.Interaction): # Swapped parameter order
        if self.current_page < len(self.embeds) - 1:
            self.current_page += 1
            await self.show_page(interaction) # Pass the interaction object
        else:
            # Defer if already on the last page to acknowledge the interaction
            await interaction.response.defer()

    async def on_timeout(self):
        """Disables buttons when the view times out."""
        # Check if message exists before trying to edit
        if self.message:
            try:
                # Disable all buttons
                for item in self.children:
                    item.disabled = True
                # Edit the original message to remove buttons
                await self.message.edit(view=None) # Remove the view entirely
                logger.debug(f"Digest paginator timed out for message {self.message.id}. Buttons removed.")
            except discord.NotFound:
                logger.warning(f"Failed to edit message {self.message.id} on timeout (not found).")
            except discord.Forbidden:
                 logger.warning(f"Failed to edit message {self.message.id} on timeout (forbidden).")
            except Exception as e:
                logger.error(f"Error editing message {self.message.id} on timeout: {e}", exc_info=True)
        self.stop()

class NewsFeedsCommands(commands.Cog):
    """Commands for managing and displaying news feed summaries."""

    def __init__(self, bot):
        self.bot = bot
        self.state = BotStateManager() # Get the singleton instance
        self.openrouter_client = OpenRouterClient(OPENROUTER_API_KEY, SYSTEM_PROMPT, DEFAULT_MODEL)

        # Removed: Old in-memory state initializations - now handled by StateManager/Database
        # Removed: Log of loaded feeds - now fetched from DB when needed

        # Start the background task when the cog is loaded
        # Check if the loop is already running before starting
        if not self.check_news_feeds.is_running():
            # Get frequency from state manager (loaded from DB on state manager init)
            frequency = self.state.get_news_update_frequency()
            self.check_news_feeds.change_interval(hours=frequency)
            self.check_news_feeds.start()
            logger.info(f"News feed check task started with frequency: {frequency} hours")
        else:
            logger.info("News feed check task is already running.")


    def cog_unload(self):
        """Stop tasks when the cog is unloaded."""
        self.check_news_feeds.cancel()
        logger.info("News feed check task cancelled.")

    @tasks.loop(hours=6)  # Define default interval (will be overridden by change_interval)
    async def check_news_feeds(self):
        """Background task to check feeds based on configured frequency."""
        frequency = self.state.get_news_update_frequency()
        logger.info(f"Starting scheduled news feed check (every {frequency} hours)")
        await self.process_all_feeds() # Default force_refresh is False

    @check_news_feeds.before_loop
    async def before_check_news_feeds(self):
        """Wait until the bot is ready before starting the task."""
        await self.bot.wait_until_ready()
        logger.info("News feed check task initialized, waiting for bot to be ready.")


    async def process_all_feeds(self, force_refresh=False): # Add force_refresh parameter
        """Process all feeds, send individual updates, and optionally an AI digest."""
        # Get feeds from the database via state manager
        all_feeds = self.state.get_news_feeds()

        if not all_feeds:
            logger.info("No news feeds configured, skipping check")
            return

        all_new_summaries_data = [] # Collect summaries {title, link, summary, feed_name, category}
        feeds_processed_count = 0
        articles_found_count = 0

        for feed_info in all_feeds: # Iterate over feeds from DB
            feed_id = feed_info.get('feed_id')
            feed_url = feed_info.get('url') # Now retrieved from DB
            feed_name = feed_info.get('name', 'Unknown Feed')
            category = feed_info.get('category', 'General') # Now retrieved from DB

            if not feed_id or not feed_url: # Check both feed_id (key) and url
                 logger.warning(f"Skipping feed with missing feed_id or url: {feed_info}")
                 continue

            try:
                # Fetch new articles, passing force_refresh
                new_articles = await self.fetch_new_articles(feed_id, feed_url, force_refresh=force_refresh)
                feeds_processed_count += 1

                if new_articles:
                    articles_found_count += len(new_articles)
                    logger.info(f"Processing {len(new_articles)} new articles for feed {feed_id} ({feed_name})")

                    # Send individual updates to subscribed channels AND get back the summaries
                    # Pass feed_name and category explicitly
                    generated_summaries = await self.send_feed_updates(feed_id, feed_name, category, new_articles)

                    # Add feed info to the summaries and collect them for the digest
                    for summary_dict in generated_summaries:
                        summary_dict['feed_name'] = feed_name
                        summary_dict['category'] = category
                        all_new_summaries_data.append(summary_dict)
                else:
                     logger.debug(f"No new articles found for feed {feed_id}")

            except Exception as e:
                logger.error(f"Error processing feed {feed_id} ({feed_name}): {str(e)}", exc_info=True)

        logger.info(f"Feed processing cycle complete. Checked {feeds_processed_count} feeds, found {articles_found_count} new articles in total.")

        # After checking all feeds, if broadcast channel is set AND we have summaries, generate and send AI digest
        broadcast_channel_id = self.state.get_news_broadcast_channel_id()
        if broadcast_channel_id and all_new_summaries_data:
            logger.info(f"Generating AI digest for {len(all_new_summaries_data)} summarized articles.")
            # Generate the digest content using the LLM
            digest_content = await self.generate_ai_digest(all_new_summaries_data)

            # Store the generated digest content in the database
            self.state.set_last_digest_content(digest_content)
            logger.debug("Stored last news digest content in DB.")

            # Send the generated digest (pass None for target_channel to use broadcast)
            await self.send_ai_digest(digest_content, target_channel=None)
        elif broadcast_channel_id:
             logger.info("Broadcast channel is set, but no new summaries were generated to create a digest.")
             # Clear last digest in DB if none generated
             self.state.set_last_digest_content(None)
             logger.debug("Cleared last news digest content in DB.")
        else:
            logger.info("Broadcast channel not set, skipping AI digest generation.")
            # Clear last digest in DB if broadcast not set
            self.state.set_last_digest_content(None)
            logger.debug("Cleared last news digest content in DB.")

        # Removed: Explicit state saving - now handled by DB operations


    async def fetch_new_articles(self, feed_id, feed_url, force_refresh=False): # Added feed_url parameter
        """Fetch and return new articles from a feed.

        Args:
            feed_id: The ID of the feed to fetch
            feed_url: The URL of the feed
            force_refresh: If True, ignore history and fetch recent articles
        """
        try:
            # Using synchronous feedparser with run_in_executor for async compatibility
            feed = await asyncio.get_event_loop().run_in_executor(
                None, feedparser.parse, feed_url # Use feed_url parameter
            )

            if not feed or hasattr(feed, 'status') and feed.status >= 400:
                logger.warning(f"Failed to fetch feed {feed_id} from {feed_url}: HTTP {feed.get('status', 'unknown')}")
                return []

            # Find new entries (deduplication happens here)
            new_entries = []
            for entry in feed.entries[:10]:  # Limit to the latest 10 entries
                entry_id = entry.get('id', entry.get('link', ''))
                if not entry_id:
                    continue

                # Skip if we've seen this article before (unless force_refresh is True)
                # Use state manager method to check history
                if not force_refresh and self.state.check_article_history(entry_id, feed_id):
                    logger.debug(f"Skipping already processed article: {entry.get('title', 'Unknown')}")
                    continue

                # Add to new entries and update history in the database
                new_entries.append(entry)
                self.state.add_article_history(entry_id, feed_id) # Timestamp added in state manager/DB

            # Update last checked time in the database
            self.state.update_feed_last_checked(feed_id) # Timestamp added in state manager/DB

            # Removed: Old history cleanup logic - now handled by DB pruning task

            logger.info(f"Found {len(new_entries)} new articles for feed {feed_id}")
            return new_entries

        except Exception as e:
            logger.error(f"Error fetching feed {feed_id} from {feed_url}: {str(e)}", exc_info=True)
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

    async def send_feed_updates(self, feed_id: str, feed_name: str, category: str, articles: List[Any]):
        """Send feed updates (individual summaries) to all configured channels and return summaries."""
        if not articles:
            return [] # Return empty list if no articles

        # Find channels that should receive this feed (all subscribed channels for this feed)
        # Get channel subscriptions from the database via state manager
        channels_to_notify = self.state.get_subscribed_channels(feed_id)

        if not channels_to_notify:
            # Adjusted log message for clarity
            logger.info(f"No channels subscribed to feed {feed_id}, skipping individual updates.")
            return [] # Return empty list

        # Summarize articles
        summaries_data = [] # Store summary dicts {title, summary, link, published}

        # Limit to max 5 articles per feed for individual posts
        # Pass the potentially multi-category string for context in summarization
        for article in articles[:5]:
            summary_dict = await self.summarize_article(article, category)
            if summary_dict and not summary_dict['summary'].startswith("Error") and not summary_dict['summary'].startswith("Unable"): # Check for valid summary
                summaries_data.append(summary_dict)
                # Add slight delay to avoid hitting AI rate limits too hard
                await asyncio.sleep(1)

        if not summaries_data:
            logger.info(f"No successful summaries generated for feed {feed_id}")
            return [] # Return empty list if no summaries

        # Send to each subscribed channel
        for channel_id_str in channels_to_notify: # Iterate over channel IDs from DB
            try:
                channel = self.bot.get_channel(int(channel_id_str))
                if not channel:
                    logger.warning(f"Channel {channel_id_str} not found for feed {feed_id} update.")
                    continue

                # Create embed for feed
                # Use feed_name and category passed as arguments
                embed = discord.Embed(
                    title=f"📰 {feed_name} News Update",
                    description=f"Latest articles from {category} category",
                    color=discord.Color.blue(),
                    timestamp=datetime.now(timezone.utc) # Use timezone aware
                )

                # Add each summary to the embed
                for i, summary in enumerate(summaries_data):
                    # Skip if we already have too many fields (max 25) or summaries (max 5)
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
                logger.debug(f"Sent individual feed update for {feed_id} to channel {channel_id_str}")

            except Exception as e:
                logger.error(f"Error sending individual update to channel {channel_id_str}: {str(e)}", exc_info=True)

        return summaries_data # Return the generated summaries

    # Removed: send_news_to_channel - logic merged into send_feed_updates

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
        feed_id = url # Use URL as the unique ID

        # Add feed to the database via state manager
        try:
            # Pass url explicitly to state manager method
            self.state.add_news_feed(feed_id=feed_id, url=url, name=name, category=category)

            await ctx.followup.send(f"✅ Added/Updated feed: **{name}** ({url}) with category **{category}**")
        except Exception as e:
            logger.error(f"Error adding feed {url}: {e}", exc_info=True)
            await ctx.followup.send(f"⚠️ Failed to add feed: {str(e)}")


    @discord.slash_command(
        name="removefeed",
        description="Remove an RSS news feed"
    )
    @commands.has_permissions(administrator=True)
    async def remove_feed_slash(self, ctx,
                              url: discord.Option(str, "The URL of the RSS feed to remove")):
        """Remove an RSS feed."""
        await ctx.defer()
        feed_id = url # Use URL as the unique ID

        # Delete feed from the database via state manager
        if self.state.delete_news_feed(feed_id):
            await ctx.followup.send(f"✅ Removed feed: **{url}**")
        else:
            await ctx.followup.send(f"⚠️ Feed not found: **{url}**")


    @discord.slash_command(
        name="listfeeds",
        description="List all configured RSS news feeds"
    )
    async def list_feeds_slash(self, ctx):
        """List all configured RSS feeds."""
        await ctx.defer()
        # Get feeds from the database via state manager
        all_feeds = self.state.get_news_feeds()

        if not all_feeds:
            await ctx.followup.send("No news feeds configured. Add one with `/addfeed`")
            return

        feeds_list = []
        for feed in all_feeds:
            feed_id = feed.get('feed_id') # This is the key, often the URL
            url = feed.get('url', feed_id) # Use URL field, fallback to feed_id if missing
            name = feed.get('name', 'Unknown')
            category = feed.get('category', 'General') # Now retrieved from DB
            last_checked = feed.get('last_checked')
            # last_checked should now be a datetime object or None due to detect_types
            last_checked_str = last_checked.strftime("%Y-%m-%d %H:%M") if isinstance(last_checked, datetime) else "Never"
            # Display the URL from the 'url' field
            feeds_list.append(f"• **{name}** ({url})\n  Category: `{category}` | Last Checked: {last_checked_str}")

        embed = discord.Embed(
            title="📰 Configured News Feeds",
            description="\n".join(feeds_list),
            color=discord.Color.blue()
        )
        await ctx.followup.send(embed=embed)


    @discord.slash_command(
        name="subscribechannel",
        description="Subscribe the current channel to all news feeds in a category"
    )
    @commands.has_permissions(administrator=True)
    async def subscribe_channel_slash(self, ctx,
                                    category: discord.Option(str, "The category name to subscribe to")):
        """Subscribe the current channel to all news feeds in a category."""
        await ctx.defer()
        channel_id = str(ctx.channel.id)
        target_category = category.strip().lower() # Normalize category input
        all_feeds = self.state.get_news_feeds()

        feeds_to_subscribe = []
        if target_category == 'all':
            feeds_to_subscribe = all_feeds # Subscribe to all feeds
            category_display_name = "all feeds"
        else:
            feeds_to_subscribe = [
                feed for feed in all_feeds
                # Check if target_category is one of the potentially comma-separated categories, handling spaces
                if target_category in [c.strip() for c in feed.get('category', '').lower().split(',')]
            ]
            category_display_name = f"category **{category}**"

        if not feeds_to_subscribe:
            await ctx.followup.send(f"⚠️ No feeds found for {category_display_name}")
            return

        subscribed_count = 0
        errors = []
        feed_names = []

        for feed in feeds_to_subscribe:
            feed_id = feed.get('feed_id')
            feed_name = feed.get('name', feed_id) # Use name for message
            if not feed_id:
                logger.warning(f"Skipping feed with missing feed_id during subscription: {feed}")
                continue

            try:
                # Add subscription to the database via state manager
                self.state.add_news_subscription(channel_id, feed_id)
                subscribed_count += 1
                feed_names.append(f"'{feed_name}'")
            except Exception as e:
                logger.error(f"Error subscribing channel {channel_id} to feed {feed_id} ({category_display_name}): {e}", exc_info=True)
                errors.append(feed_id)

        if subscribed_count > 0:
            await ctx.followup.send(f"✅ Subscribed this channel to **{subscribed_count}** feed(s) for {category_display_name}.")
        if errors:
            await ctx.followup.send(f"⚠️ Failed to subscribe to some feeds for {category_display_name}: {', '.join(errors)}", ephemeral=True)
        elif subscribed_count == 0 and not errors:
             # This case might happen if all feeds found already had errors or missing IDs
             await ctx.followup.send(f"⚠️ Could not subscribe to any feeds found for {category_display_name}")


    @discord.slash_command(
        name="unsubscribechannel",
        description="Unsubscribe the current channel from all news feeds in a category"
    )
    @commands.has_permissions(administrator=True)
    async def unsubscribe_channel_slash(self, ctx,
                                      category: discord.Option(str, "The category name to unsubscribe from")):
        """Unsubscribe the current channel from all news feeds in a category."""
        await ctx.defer()
        channel_id = str(ctx.channel.id)
        target_category = category.strip().lower() # Normalize category input
        all_feeds = self.state.get_news_feeds()

        feeds_to_unsubscribe = []
        if target_category == 'all':
            feeds_to_unsubscribe = all_feeds # Try unsubscribing from all feeds
            category_display_name = "all feeds"
        else:
            feeds_to_unsubscribe = [
                feed for feed in all_feeds
                # Check if target_category is one of the potentially comma-separated categories, handling spaces
                if target_category in [c.strip() for c in feed.get('category', '').lower().split(',')]
            ]
            category_display_name = f"category **{category}**"

        if not feeds_to_unsubscribe:
            # If category is 'all' but there are no feeds configured at all
            if target_category == 'all' and not all_feeds:
                 await ctx.followup.send("ℹ️ No news feeds are configured.")
                 return
            # If a specific category was given but no feeds match
            elif target_category != 'all':
                await ctx.followup.send(f"⚠️ No feeds found for {category_display_name}")
                return
            # If category is 'all' and feeds exist, but feeds_to_unsubscribe is empty (shouldn't happen)
            else:
                 logger.warning("Unexpected state in unsubscribe: category='all', feeds exist, but feeds_to_unsubscribe is empty.")
                 await ctx.followup.send(f"⚠️ An unexpected error occurred trying to find feeds for {category_display_name}")
                 return


        unsubscribed_count = 0
        not_subscribed_count = 0
        errors = []
        feed_names = []

        for feed in feeds_to_unsubscribe:
            feed_id = feed.get('feed_id')
            feed_name = feed.get('name', feed_id) # Use name for message
            if not feed_id:
                logger.warning(f"Skipping feed with missing feed_id during unsubscription: {feed}")
                continue

            try:
                # Remove subscription from the database via state manager
                # This will return True if removal happened, False if not subscribed
                if self.state.remove_news_subscription(channel_id, feed_id):
                    unsubscribed_count += 1
                    feed_names.append(f"'{feed_name}'")
                else:
                    # Only count as 'not subscribed' if we were specifically targeting a category
                    # If target is 'all', we don't care if it wasn't subscribed to some feeds
                    if target_category != 'all':
                        not_subscribed_count += 1
            except Exception as e:
                logger.error(f"Error unsubscribing channel {channel_id} from feed {feed_id} ({category_display_name}): {e}", exc_info=True)
                errors.append(feed_id)

        # Report results
        if unsubscribed_count > 0:
            await ctx.followup.send(f"✅ Unsubscribed this channel from **{unsubscribed_count}** feed(s) for {category_display_name}.")
        # If targeting a specific category and nothing was unsubscribed (only 'not subscribed' counts)
        elif target_category != 'all' and not_subscribed_count > 0 and unsubscribed_count == 0:
             await ctx.followup.send(f"ℹ️ This channel was not subscribed to any feeds found for {category_display_name}.")
        # If targeting 'all' and nothing was unsubscribed
        elif target_category == 'all' and unsubscribed_count == 0 and not errors:
             await ctx.followup.send(f"ℹ️ This channel was not subscribed to any feeds.")

        # Report errors if any occurred
        if errors:
            await ctx.followup.send(f"⚠️ Failed to process unsubscription for some feeds ({category_display_name}): {', '.join(errors)}", ephemeral=True)


    @discord.slash_command(
        name="updatefeeds",
        description="Manually trigger a news feed update check"
    )
    @commands.has_permissions(administrator=True)
    async def update_feeds_slash(self, ctx,
                                 force_refresh: discord.Option(bool,
                                                               "Force refresh all articles, ignoring history?",
                                                               required=False,
                                                               default=False)):
        """Manually trigger a news feed update check."""
        await ctx.defer()
        await ctx.followup.send("Manually triggering news feed update check...")
        await self.process_all_feeds(force_refresh=force_refresh)
        await ctx.followup.send("News feed update check finished.")


    @discord.slash_command(
        name="getnews",
        description="Get the latest news digest, optionally filtered by category"
    )
    async def get_news_slash(self, ctx,
                             category: discord.Option(str, "Optional: Get a digest for a specific category", required=False) = None):
        """Get the latest news digest, optionally generating one for a specific category."""
        await ctx.defer()

        if category:
            # Generate a digest for a specific category
            target_category = category.strip().lower()
            await ctx.followup.send(f"Generating a news digest for category: **{target_category}**...")

            all_feeds = self.state.get_news_feeds()
            feeds_in_category = [
                feed for feed in all_feeds
                # Check if target_category is one of the potentially comma-separated categories, handling spaces
                if target_category in [c.strip() for c in feed.get('category', '').lower().split(',')]
            ]

            if not feeds_in_category:
                await ctx.followup.send(f"⚠️ No feeds found for category: **{category}**")
                return

            category_articles_data = []
            articles_processed_count = 0
            feeds_checked_count = 0

            for feed_info in feeds_in_category:
                feed_id = feed_info.get('feed_id')
                feed_url = feed_info.get('url')
                feed_name = feed_info.get('name', 'Unknown Feed')
                feed_category = feed_info.get('category', 'General') # Use the feed's specific category for summarization context

                if not feed_id or not feed_url:
                    logger.warning(f"Skipping feed with missing ID or URL during category digest generation: {feed_info}")
                    continue

                feeds_checked_count += 1
                try:
                    # Fetch latest articles (force refresh for on-demand)
                    new_articles = await self.fetch_new_articles(feed_id, feed_url, force_refresh=True)

                    if new_articles:
                        logger.info(f"Processing {len(new_articles)} articles for category digest from feed {feed_id} ({feed_name})")
                        # Summarize articles
                        for article in new_articles: # Summarize all fetched articles for the digest
                            summary_dict = await self.summarize_article(article, feed_category)
                            if summary_dict and not summary_dict['summary'].startswith("Error") and not summary_dict['summary'].startswith("Unable"):
                                summary_dict['feed_name'] = feed_name
                                summary_dict['category'] = feed_category # Store original category
                                category_articles_data.append(summary_dict)
                                articles_processed_count += 1
                                await asyncio.sleep(0.5) # Shorter delay for faster on-demand generation
                    else:
                        logger.debug(f"No new articles found for feed {feed_id} during category digest generation.")

                except Exception as e:
                    logger.error(f"Error processing feed {feed_id} for category digest: {e}", exc_info=True)

            logger.info(f"Category digest generation: Checked {feeds_checked_count} feeds for category '{target_category}', processed {articles_processed_count} articles.")

            if category_articles_data:
                # Generate the category-specific digest
                digest_content = await self.generate_ai_digest(category_articles_data)
                # Send the generated digest
                await self.send_ai_digest(digest_content, target_channel=ctx.channel)
                # Send a confirmation followup
                await ctx.followup.send(f"✅ Generated and displayed news digest for category: **{category}**.", ephemeral=True)
            else:
                await ctx.followup.send(f"ℹ️ No new articles found to generate a digest for category: **{category}**.")

        else:
            # Get the last globally generated AI digest from the database
            last_digest_content = self.state.get_last_digest_content()

            if last_digest_content:
                await ctx.followup.send("Displaying the last generated global news digest:")
                # Send the digest to the requesting channel
                await self.send_ai_digest(last_digest_content, target_channel=ctx.channel)
            else:
                await ctx.followup.send("No global news digest has been generated yet. News feeds are checked periodically.")

    # Removed _send_individual_updates_to_channel helper function

    @discord.slash_command(
        name="setfeedfrequency",
        description="Set how often news feeds are checked (in hours)"
    )
    @commands.has_permissions(administrator=True)
    async def set_feed_frequency_slash(self, ctx,
                                     hours: discord.Option(int, "Frequency in hours (minimum 1)")):
        """Set how often news feeds are checked (in hours)."""
        await ctx.defer()
        if hours < 1:
            await ctx.followup.send("⚠️ Frequency must be at least 1 hour.")
            return

        # Set frequency in the database via state manager
        await self.state.set_news_update_frequency(hours)

        # Update the background task interval
        self.check_news_feeds.change_interval(hours=hours)

        await ctx.followup.send(f"✅ News feed check frequency set to **{hours} hours**.")


    @discord.slash_command(
        name="feedstatus",
        description="Show the current status of news feed processing"
    )
    async def feed_status_slash(self, ctx):
        """Show the current status of feed processing."""
        await ctx.defer()
        # Get stats from the database via state manager
        feed_count = self.state.get_news_feeds_count()
        subscription_count = self.state.get_news_channel_config_count() # This is subscription count
        article_history_count = self.state.get_news_article_history_count() # Get article history count

        # Get last checked time for each feed (requires fetching feeds)
        all_feeds = self.state.get_news_feeds()
        feed_status_list = []
        for feed in all_feeds:
            name = feed.get('name', 'Unknown')
            last_checked = feed.get('last_checked')
            # last_checked should now be a datetime object or None due to detect_types
            last_checked_str = last_checked.strftime("%Y-%m-%d %H:%M:%S") if isinstance(last_checked, datetime) else "Never"
            feed_status_list.append(f"• **{name}**: Last Checked {last_checked_str}")

        embed = discord.Embed(
            title="📰 News Feed Status",
            color=discord.Color.blue()
        )

        embed.add_field(
            name="Configuration",
            value=(f"• Configured Feeds: {feed_count if feed_count >= 0 else 'Error'}\n"
                   f"• Channel Subscriptions: {subscription_count if subscription_count >= 0 else 'Error'}\n"
                   f"• Tracked Article History: {article_history_count if article_history_count >= 0 else 'Error'}\n"
                   f"• Check Frequency: {self.state.get_news_update_frequency()} hours\n"
                   f"• Broadcast Channel ID: {self.state.get_news_broadcast_channel_id() or 'Not Set'}"),
            inline=False
        )

        if feed_status_list:
            embed.add_field(
                name="Last Checked Times",
                value="\n".join(feed_status_list),
                inline=False
            )
        else:
             embed.add_field(
                name="Last Checked Times",
                value="No feeds configured.",
                inline=False
            )

        # Check if the background task is running
        task_status = "Running" if self.check_news_feeds.is_running() else "Not Running"
        embed.add_field(
            name="Task Status",
            value=f"• Background Check Task: {task_status}",
            inline=False
        )


        await ctx.followup.send(embed=embed)


    async def generate_ai_digest(self, all_articles_data):
        """Generate an AI-powered news digest from a list of summarized articles, requesting JSON output."""
        if not all_articles_data:
            # Return a JSON string indicating no articles, matching the expected format
            return json.dumps({"digest_stories": []})

        # Format the summarized articles for the LLM context
        formatted_articles = []
        for article in all_articles_data:
            # Include essential info for the LLM to make selections
            formatted_articles.append(
                f"Title: {article.get('title', 'No Title')}\n"
                f"Summary: {article.get('summary', 'No summary.')}\n"
                f"Link: {article.get('link', 'No link')}\n"
                f"Feed: {article.get('feed_name', 'Unknown')}\n"
                f"Category: {article.get('category', 'General')}\n---"
            )
        articles_text = "\n\n".join(formatted_articles)

        # Define the JSON schema for the expected output
        json_schema = {
            "name": "news_digest",
            "strict": True, # Enforce schema strictly
            "schema": {
                "type": "object",
                "properties": {
                    "digest_stories": {
                        "type": "array",
                        "description": "A list of the top 15-25 most important or impactful news stories.",
                        "items": {
                            "type": "object",
                            "properties": {
                                "title": {"type": "string", "description": "The title of the news article."},
                                "explanation": {"type": "string", "description": "A brief (1-2 sentence) explanation of the story's significance."},
                                "link": {"type": "string", "description": "The URL link to the full article.", "format": "uri"}
                            },
                            "required": ["title", "explanation", "link"]
                        }
                    }
                },
                "required": ["digest_stories"]
            }
        }

        # Define the prompt for the LLM, asking for JSON output
        prompt = (
            f"Below is a list of recent news articles with their summaries. "
            f"Please identify the top 15-25 most important or impactful articles from this list. "
            f"For each selected article, provide its title, a brief (1-2 sentence) explanation of why it's significant, and its link.\n\n"
            f"Format your response *strictly* as a JSON object matching the provided schema. The object should contain a single key 'digest_stories' which is a list of story objects.\n\n"
            f"Here are the articles:\n\n{articles_text}"
        )

        # Define a specific system prompt for digest generation, emphasizing JSON format
        digest_system_prompt = (
            "You are an AI news analyst. Your task is to identify the most important news stories "
            "from a provided list and explain their significance concisely. "
            "Return your response *only* as a valid JSON object matching the requested schema."
        )

        try:
            # Call the client with the response_format parameter
            response = await self.openrouter_client.send_message_with_history(
                messages=[
                    {"role": "system", "content": digest_system_prompt},
                    {"role": "user", "content": prompt}
                ],
                response_format={
                    "type": "json_schema",
                    "json_schema": json_schema
                }
            )
            # The response should already be a JSON string if the API call succeeds with response_format
            logger.debug(f"Received raw JSON digest response: {response}")
            return response
        except Exception as e:
            logger.error(f"Error generating AI digest with JSON format: {e}", exc_info=True)
            # Return a JSON string indicating error, matching the expected format
            error_detail = str(e).replace('"', "'") # Basic sanitization for JSON
            return json.dumps({"error": f"Failed to generate digest: {error_detail}", "digest_stories": []})


    async def send_ai_digest(self, digest_content, target_channel=None): # Add target_channel parameter
        """Parses the AI-generated digest and sends it as paginated embeds using discord.ui.View.

        Args:
            digest_content: The raw string content generated by the AI.
            target_channel: The specific channel to send the digest to. If None, uses the configured broadcast channel.
        """
        # Determine the channel to send to
        channel_to_send = target_channel # Use the provided channel if available

        if channel_to_send is None: # If no target_channel, use the broadcast channel
            broadcast_channel_id = self.state.get_news_broadcast_channel_id() # Use state manager method
            if not broadcast_channel_id:
                logger.warning("Attempted to send AI digest, but no broadcast channel is set and no target_channel provided.")
                return
            try:
                channel_to_send = self.bot.get_channel(int(broadcast_channel_id))
                if not channel_to_send:
                     logger.error(f"Broadcast channel ID {broadcast_channel_id} not found.")
                     return
            except Exception as e:
                logger.error(f"Error getting broadcast channel: {e}")
                return

        # Validate digest content (moved check after channel determination)
        if not digest_content or digest_content.startswith("Error:") or digest_content == "No articles provided for digest.":
            logger.warning(f"Skipping sending AI digest due to invalid content: {digest_content}")
            # Optionally send an error message to the channel if needed and if it's the broadcast channel
            broadcast_channel_id = self.state.get_news_broadcast_channel_id() # Check again for safety
            if channel_to_send and broadcast_channel_id and str(channel_to_send.id) == broadcast_channel_id:
                try:
                    await channel_to_send.send(f"⚠️ Failed to generate AI digest: {digest_content}")
                except Exception as e:
                    logger.error(f"Failed to send digest error message: {e}")
            return

        # Use channel_to_send instead of broadcast_channel throughout the rest of the function
        try:
            # --- Pagination Implementation using discord.ui.View ---

            # 1. Parse the JSON digest_content
            stories = []
            try:
                parsed_data = json.loads(digest_content)
                # Validate basic structure and extract stories
                if isinstance(parsed_data, dict) and 'digest_stories' in parsed_data and isinstance(parsed_data['digest_stories'], list):
                    stories = parsed_data['digest_stories']
                    # Optional: Further validation of each story object's structure/types
                    stories = [s for s in stories if isinstance(s, dict) and all(k in s for k in ['title', 'explanation', 'link'])]
                    logger.info(f"Successfully parsed {len(stories)} stories from JSON digest.")
                    # Check for error message from generation step
                    if 'error' in parsed_data:
                         logger.error(f"Error reported during digest generation: {parsed_data['error']}")
                         # Decide if we should still try to display partial stories or just show error
                         # For now, we'll proceed to display any stories found alongside the error log

                else:
                     logger.error(f"Parsed JSON digest has incorrect structure. Expected {{'digest_stories': [...]}}. Data: {parsed_data}")
                     stories = [] # Ensure stories is empty if structure is wrong

            except json.JSONDecodeError:
                logger.error(f"Failed to decode JSON digest content. Raw content:\n---\n{digest_content}\n---")
                stories = [] # Ensure stories is empty if JSON parsing fails
            except Exception as e:
                logger.error(f"Unexpected error parsing JSON digest: {e}. Raw content:\n---\n{digest_content}\n---", exc_info=True)
                stories = [] # Ensure stories is empty on other errors


            # Fallback / Empty Check: If no stories were parsed (due to error or empty list from LLM)
            if not stories:
                 logger.warning("No valid stories found after JSON parsing or LLM returned empty list.")
                 # Send a simple message indicating failure or empty digest
                 fallback_message = "Could not generate or parse the news digest."
                 # Check if the raw content might be an old markdown digest (basic check)
                 if digest_content.strip().startswith("**1."):
                      fallback_message += " (The stored digest might be in an old format)."
                 elif digest_content:
                      # Try to show the raw content if it's not obviously markdown and not too long
                      truncated_raw = self.truncate_for_embed(digest_content, 500)
                      fallback_message += f"\nRaw response snippet: ```{truncated_raw}```"

                 await channel_to_send.send(f"⚠️ {fallback_message}")
                 return


            # 2. Create Embed Pages from the parsed 'stories' list
            embed_pages = []
            stories_per_page = 5 # Keep this reasonably small for embeds
            num_pages = (len(stories) + stories_per_page - 1) // stories_per_page

            # This check should technically be redundant now due to the check above, but keep for safety
            if num_pages == 0:
                logger.warning("No stories found after parsing (redundant check), cannot create embed pages.")
                return # Nothing to send

            for i in range(num_pages):
                embed = discord.Embed(
                    title=f"🌟 Top News Highlights (Page {i+1}/{num_pages})",
                    color=discord.Color.gold(),
                    timestamp=datetime.now(timezone.utc)
                )

                start_index = i * stories_per_page
                end_index = start_index + stories_per_page
                page_stories = stories[start_index:end_index]

                description = ""
                for j, story in enumerate(page_stories):
                    story_num = start_index + j + 1
                    description += f"**{story_num}. {story['title']}**\n"
                    description += f"{story['explanation']}\n"
                    description += f"<{story['link']}>\n\n" # Use <link> for no embed preview

                embed.description = self.truncate_for_embed(description.strip(), 4000) # Use self.truncate_for_embed
                embed.set_footer(text=f"AI-Curated Digest by Gideon | Page {i+1}/{num_pages}")
                embed_pages.append(embed)

            # 3. Send the first page with the Paginator View
            if not embed_pages:
                 logger.warning("No embed pages created for the digest, skipping send.")
                 return

            view = DigestPaginatorView(embed_pages) # Use the existing DigestPaginatorView class
            # Send the initial message and store it in the view for timeout handling
            message = await channel_to_send.send(embed=embed_pages[0], view=view) # Use channel_to_send
            view.message = message # Assign the sent message to the view instance

            logger.info(f"Sent AI news digest with pagination ({len(embed_pages)} pages) to channel {channel_to_send.id}, message {message.id}")

        except Exception as e:
            logger.error(f"Error sending paginated AI digest to channel {channel_to_send.id if channel_to_send else 'N/A'}: {str(e)}", exc_info=True)
            # Attempt to send a simple error message to the channel
            try:
                if channel_to_send:
                    await channel_to_send.send("⚠️ An error occurred while trying to display the AI news digest.")
            except Exception as send_error:
                 logger.error(f"Failed to send error message to channel {channel_to_send.id if channel_to_send else 'N/A'}: {send_error}")


    @discord.slash_command(
        name="setbroadcastchannel",
        description="Set the channel where the AI news digest will be broadcast"
    )
    @commands.has_permissions(administrator=True)
    async def set_broadcast_channel_slash(self, ctx,
                                        channel: discord.Option(discord.TextChannel, "The channel to set as the broadcast channel")):
        """Set the channel where the AI news digest will be broadcast."""
        await ctx.defer(ephemeral=True) # Respond ephemerally

        # Set broadcast channel ID in the database via state manager
        await self.state.set_news_broadcast_channel_id(str(channel.id))

        await ctx.followup.send(f"✅ News digest broadcast channel set to {channel.mention}")


    @discord.slash_command(
        name="unsetbroadcastchannel",
        description="Unset the AI news digest broadcast channel"
    )
    @commands.has_permissions(administrator=True)
    async def unset_broadcast_channel_slash(self, ctx):
        """Unset the AI news digest broadcast channel."""
        await ctx.defer(ephemeral=True) # Respond ephemerally

        # Unset broadcast channel ID in the database via state manager
        await self.state.set_news_broadcast_channel_id(None)

        await ctx.followup.send("✅ News digest broadcast channel unset.")


    # --- User Feed Commands ---

    myfeeds = discord.SlashCommandGroup("myfeeds", "Manage your personal list of RSS feeds for /mynews")

    @myfeeds.command(name="list", description="Show your saved personal RSS feeds")
    async def myfeeds_list(self, ctx: discord.ApplicationContext):
        """Shows the user's saved personal RSS feeds."""
        await ctx.defer(ephemeral=True)
        user_id = str(ctx.author.id)
        # Corrected: Access db_manager through state
        preferences = self.state.db_manager.get_user_preferences(user_id)
        feed_urls = preferences.get("custom_rss_feeds", []) if preferences else []

        if not feed_urls:
            await ctx.followup.send("You haven't saved any personal feeds yet. Use `/myfeeds add <url>` to add one.", ephemeral=True)
            return

        embed = discord.Embed(
            title=f"📰 {ctx.author.display_name}'s Personal Feeds",
            description="\n".join([f"• {url}" for url in feed_urls]),
            color=discord.Color.green()
        )
        await ctx.followup.send(embed=embed, ephemeral=True)

    @myfeeds.command(name="add", description="Add an RSS feed URL to your personal list")
    async def myfeeds_add(self, ctx: discord.ApplicationContext, url: Option(str, "The URL of the RSS feed to add")):
        """Adds an RSS feed URL to the user's personal list."""
        await ctx.defer(ephemeral=True)
        user_id = str(ctx.author.id)
        feed_url = url.strip()

        # Basic Validation
        try:
            logger.debug(f"Validating feed URL: {feed_url}")
            # Use run_in_executor for the blocking feedparser call
            feed_data = await asyncio.get_event_loop().run_in_executor(
                None, feedparser.parse, feed_url
            )
            # Check for basic feed properties and entries
            if feed_data.bozo: # feedparser sets bozo flag for errors
                 # Check specific exception if available
                 bozo_exception = feed_data.get('bozo_exception', None)
                 logger.warning(f"Feed validation failed for {feed_url}. Bozo flag set. Exception: {bozo_exception}")
                 # Provide more specific error if possible
                 if isinstance(bozo_exception, feedparser.CharacterEncodingOverride):
                     # Often still parsable, maybe allow? For now, reject.
                     await ctx.followup.send(f"⚠️ The feed at `{feed_url}` has character encoding issues. Please try a different URL.", ephemeral=True)
                     return
                 elif isinstance(bozo_exception, Exception): # General exception
                     await ctx.followup.send(f"⚠️ Could not parse the feed at `{feed_url}`. Error: {bozo_exception}. Please check the URL.", ephemeral=True)
                     return
                 else: # Generic bozo error
                    await ctx.followup.send(f"⚠️ The URL `{feed_url}` doesn't seem to be a valid RSS/Atom feed or could not be parsed. Please check the URL.", ephemeral=True)
                    return

            if not feed_data.entries:
                 logger.warning(f"Feed validation failed for {feed_url}: No entries found.")
                 await ctx.followup.send(f"⚠️ The feed at `{feed_url}` was parsed, but no articles/entries were found. It might be empty or not a standard feed.", ephemeral=True)
                 return

            logger.info(f"Feed URL {feed_url} validated successfully.")

        except Exception as e:
            logger.error(f"Error validating feed URL {feed_url}: {e}", exc_info=True)
            await ctx.followup.send(f"⚠️ An unexpected error occurred while trying to validate the URL `{feed_url}`. Please try again later.", ephemeral=True)
            return

        # Add URL to preferences
        # Corrected: Access db_manager through state
        preferences = self.state.db_manager.get_user_preferences(user_id)
        if not preferences:
            preferences = {"custom_rss_feeds": []}

        feed_urls = preferences.get("custom_rss_feeds", [])
        if feed_url in feed_urls:
            await ctx.followup.send(f"ℹ️ You already have `{feed_url}` in your list.", ephemeral=True)
            return

        feed_urls.append(feed_url)
        preferences["custom_rss_feeds"] = feed_urls
        # Corrected: Access db_manager through state
        self.state.db_manager.set_user_preferences(user_id, preferences)

        await ctx.followup.send(f"✅ Added `{feed_url}` to your personal feed list.", ephemeral=True)


    @myfeeds.command(name="remove", description="Remove an RSS feed URL from your personal list")
    async def myfeeds_remove(self, ctx: discord.ApplicationContext, url: Option(str, "The URL of the RSS feed to remove")):
        """Removes an RSS feed URL from the user's personal list."""
        await ctx.defer(ephemeral=True)
        user_id = str(ctx.author.id)
        feed_url_to_remove = url.strip()

        # Corrected: Access db_manager through state
        preferences = self.state.db_manager.get_user_preferences(user_id)
        if not preferences:
            await ctx.followup.send("You don't have any saved feeds to remove.", ephemeral=True)
            return

        feed_urls = preferences.get("custom_rss_feeds", [])
        if feed_url_to_remove not in feed_urls:
            await ctx.followup.send(f"⚠️ The URL `{feed_url_to_remove}` was not found in your list.", ephemeral=True)
            return

        feed_urls.remove(feed_url_to_remove)
        preferences["custom_rss_feeds"] = feed_urls
        # Corrected: Access db_manager through state
        self.state.db_manager.set_user_preferences(user_id, preferences)

        await ctx.followup.send(f"✅ Removed `{feed_url_to_remove}` from your personal feed list.", ephemeral=True)


    @discord.slash_command(
        name="mynews",
        description="Get a personalized news digest from your saved feeds"
    )
    async def mynews_slash(self, ctx: discord.ApplicationContext):
        """Generates and displays a personalized news digest for the user."""
        await ctx.defer()
        user_id = str(ctx.author.id)

        # Corrected: Access db_manager through state
        preferences = self.state.db_manager.get_user_preferences(user_id)
        feed_urls = preferences.get("custom_rss_feeds", []) if preferences else []

        if not feed_urls:
            await ctx.followup.send("You haven't saved any personal feeds yet. Use `/myfeeds add <url>` to add some and then run `/mynews` again.")
            return

        await ctx.followup.send(f"⏳ Generating your personal news digest from {len(feed_urls)} feed(s)...")

        collected_summaries = []
        articles_processed_count = 0
        feeds_checked_count = 0
        max_articles_per_feed = 3 # As decided

        for feed_url in feed_urls:
            feeds_checked_count += 1
            logger.info(f"Processing feed for /mynews: {feed_url}")
            try:
                # Use run_in_executor for the blocking feedparser call
                feed_data = await asyncio.get_event_loop().run_in_executor(
                    None, feedparser.parse, feed_url
                )

                if feed_data.bozo:
                    logger.warning(f"Skipping feed {feed_url} for /mynews due to parsing error (bozo). Exception: {feed_data.get('bozo_exception')}")
                    continue # Skip this feed if it has parsing errors

                if not feed_data.entries:
                    logger.info(f"No entries found in feed {feed_url} for /mynews.")
                    continue

                # Get the latest N articles
                latest_articles = feed_data.entries[:max_articles_per_feed]

                for article in latest_articles:
                    # Summarize article
                    # Use a generic category or none, as it's less relevant for personal feeds
                    summary_dict = await self.summarize_article(article, feed_category="Personal Feed")
                    if summary_dict and not summary_dict['summary'].startswith("Error") and not summary_dict['summary'].startswith("Unable"):
                        # Add feed URL for potential future reference, though not used in digest generation currently
                        summary_dict['feed_url'] = feed_url
                        # Use a generic feed name or the feed title if available
                        summary_dict['feed_name'] = feed_data.feed.get('title', feed_url)
                        summary_dict['category'] = 'Personal' # Assign a category for digest generation context
                        collected_summaries.append(summary_dict)
                        articles_processed_count += 1
                        await asyncio.sleep(0.5) # Rate limiting for AI calls
                    else:
                        logger.warning(f"Failed to summarize article from {feed_url}: {summary_dict.get('title', 'Unknown Title')}")

            except Exception as e:
                logger.error(f"Error processing feed {feed_url} for /mynews: {e}", exc_info=True)
                # Optionally notify user about specific feed errors? For now, just log.

        logger.info(f"/mynews for {user_id}: Checked {feeds_checked_count} feeds, processed {articles_processed_count} articles.")

        if collected_summaries:
            # Generate the digest using the existing function
            digest_content = await self.generate_ai_digest(collected_summaries)
            # Send the digest to the current channel using the existing function
            await self.send_ai_digest(digest_content, target_channel=ctx.channel)
            # Send a new followup message instead of editing
            await ctx.followup.send(content=f"✅ Here is your personal news digest!", ephemeral=True) # Optional: ephemeral confirmation
        else:
            # Send a new followup message instead of editing
            await ctx.followup.send(content="ℹ️ Could not fetch or summarize any new articles from your saved feeds.", ephemeral=True) # Optional: ephemeral confirmation

    # --- End User Feed Commands ---


    @discord.slash_command(
        name="newsdigest",
        description="Get the last generated AI news digest"
    )
    async def news_digest_slash(self, ctx):
        """Get the last generated AI news digest."""
        await ctx.defer()

        # Get the last generated AI digest from the database
        last_digest_content = self.state.get_last_digest_content()

        if last_digest_content:
            await ctx.followup.send("Here is the last generated news digest:")
            # Send the digest to the requesting channel
            await self.send_ai_digest(last_digest_content, target_channel=ctx.channel)
        else:
            await ctx.followup.send("No news digest has been generated yet. News feeds are checked periodically.")


def setup(bot):
    bot.add_cog(NewsFeedsCommands(bot))
