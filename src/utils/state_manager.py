"""Centralized state management for the bot."""
from datetime import datetime, timedelta
from typing import Dict, List, Any
import logging
import asyncio

logger = logging.getLogger('state_manager')

class BotStateManager:
    """Singleton class to manage shared state across cogs"""
    _instance = None
    
    def __new__(cls):
        if cls._instance is None:
            cls._instance = super(BotStateManager, cls).__new__(cls)
            cls._instance._initialize()
            logger.info(f"Created new BotStateManager instance with id: {id(cls._instance)}")
        else:
            logger.info(f"Reusing existing BotStateManager instance with id: {id(cls._instance)}")
        return cls._instance
        
    def _initialize(self):
        self._lock = asyncio.Lock()
        # Chat related state
        self.channel_history = {}
        self.channel_models = {}
        self.channel_system_prompts = {}  # NEW: Store channel-specific system prompts
        
        # Thread related state
        self.discord_threads = {}  # Only keeping discord_threads
        
        # Configuration
        self.max_channel_history = 35
        self.max_threads_per_channel = 10
        self.time_window_hours = 48
        
        # Import allowed models from config
        from ..config import ALLOWED_MODELS, DEFAULT_MODEL
        self.allowed_models = ALLOWED_MODELS
        self.global_model = DEFAULT_MODEL  # NEW: Store the global model
        
        # News feed related state - explicitly initialize these attributes
        self.news_feeds = {}
        self.news_channel_config = {}
        self.news_article_history = {}
    
    # Getters and setters for all state properties
    # This allows controlled access to the state from different cogs
    
    # Channel history methods
    def get_channel_history(self, channel_id: str) -> List[Dict[str, Any]]:
        return self.channel_history.get(channel_id, [])
    
    async def add_to_channel_history(self, channel_id: str, message: Dict[str, Any]):
        async with self._lock:
            msg = message.copy()
            msg["timestamp"] = datetime.now()  # CRITICAL: Add timestamp
            
            if channel_id not in self.channel_history:
                self.channel_history[channel_id] = []
                
            self.channel_history[channel_id].append(msg)
            
            # Enforce maximum history size
            if len(self.channel_history[channel_id]) > self.max_channel_history:
                self.channel_history[channel_id] = self.channel_history[channel_id][-self.max_channel_history:]
    
    def clear_channel_history(self, channel_id: str) -> bool:
        """Clear history for a channel. Returns True if any history was cleared."""
        if channel_id in self.channel_history:
            self.channel_history[channel_id] = []
            return True
        return False
    
    # Discord thread methods
    def get_discord_thread(self, thread_id: str) -> Dict[str, Any]:
        """Get thread data by Discord thread ID"""
        return self.discord_threads.get(thread_id)
    
    async def add_discord_thread_message(self, thread_id: str, message: Dict[str, Any]):
        async with self._lock:
            msg = message.copy()
            msg["timestamp"] = datetime.now()  # CRITICAL: Add timestamp
            if thread_id not in self.discord_threads:
                self.discord_threads[thread_id] = {
                    "name": "Unnamed Thread",
                    "channel_id": "unknown",
                    "created_at": datetime.now(),
                    "messages": []
                }
            self.discord_threads[thread_id]["messages"].append(msg)
    
    def get_discord_thread_history(self, thread_id: str, hours_limit: int = None) -> List[Dict[str, Any]]:
        """Get message history for a Discord thread with optional time window"""
        if thread_id not in self.discord_threads:
            return []
        messages = self.discord_threads[thread_id].get("messages", [])
        cutoff_time = datetime.now() - timedelta(hours=hours_limit or self.time_window_hours)
        return [msg for msg in messages if "timestamp" not in msg or msg["timestamp"] > cutoff_time]
    
    def prune_old_data(self):
        """Remove outdated conversations and inactive threads."""
        # Set cutoff times
        channel_cutoff = datetime.now() - timedelta(hours=self.time_window_hours * 2)
        thread_cutoff = datetime.now() - timedelta(days=14)  # 2 weeks for threads
        
        # Prune channel history
        channels_pruned = 0
        messages_pruned = 0
        
        for channel_id in list(self.channel_history.keys()):
            history = self.channel_history[channel_id]
            if not history:
                del self.channel_history[channel_id]
                channels_pruned += 1
                continue
                
            # Check if the most recent message is older than cutoff
            if history and isinstance(history, list) and len(history) > 0:
                last_message_time = history[-1].get("timestamp") if isinstance(history[-1], dict) else None
                if last_message_time and isinstance(last_message_time, datetime) and last_message_time < channel_cutoff:
                    del self.channel_history[channel_id]
                    channels_pruned += 1
                    messages_pruned += len(history)
                    
                    # Also clean up channel model if no longer used
                    if channel_id in self.channel_models:
                        del self.channel_models[channel_id]
                    if channel_id in self.channel_system_prompts:
                        del self.channel_system_prompts[channel_id]
        
        # Prune Discord threads
        threads_pruned = 0
        for thread_id in list(self.discord_threads.keys()):
            thread_data = self.discord_threads[thread_id]
            last_time = thread_data.get("created_at")
            if "messages" in thread_data and thread_data["messages"]:
                last_time = thread_data["messages"][-1].get("timestamp", last_time)
            if last_time and last_time < thread_cutoff:
                del self.discord_threads[thread_id]
                threads_pruned += 1
        
        # Also prune old news article history
        news_entries_pruned = 0
        if hasattr(self, 'news_article_history'):
            news_cutoff = datetime.now() - timedelta(days=7)  # 1 week for news articles
            for feed_id in list(self.news_article_history.keys()):
                if feed_id in self.news_article_history:
                    before_count = len(self.news_article_history[feed_id])
                    for entry_id in list(self.news_article_history[feed_id]):
                        timestamp = self.news_article_history[feed_id][entry_id]
                        if datetime.fromtimestamp(timestamp) < news_cutoff:
                            del self.news_article_history[feed_id][entry_id]
                            news_entries_pruned += 1
                    # If empty after pruning, remove the feed entry entirely
                    if not self.news_article_history[feed_id]:
                        del self.news_article_history[feed_id]
        
        return {
            "channels_pruned": channels_pruned,
            "messages_pruned": messages_pruned,
            "threads_pruned": threads_pruned,
            "news_entries_pruned": news_entries_pruned
        }
    
    # NEW: System prompt methods
    def get_channel_system_prompt(self, channel_id: str) -> str:
        """Get the system prompt for a specific channel, or return None if not set."""
        return self.channel_system_prompts.get(channel_id)
    
    def set_channel_system_prompt(self, channel_id: str, prompt: str) -> None:
        """Set a custom system prompt for a channel."""
        self.channel_system_prompts[channel_id] = prompt
    
    def reset_channel_system_prompt(self, channel_id: str) -> bool:
        """Reset a channel to use the default system prompt. Returns True if a custom prompt was removed."""
        if channel_id in self.channel_system_prompts:
            del self.channel_system_prompts[channel_id]
            return True
        return False
    
    # NEW: Methods for global model management
    def get_global_model(self) -> str:
        """Get the current global model."""
        return self.global_model
    
    def set_global_model(self, model: str) -> None:
        """Set the global model with validation."""
        if model not in self.allowed_models:
            raise ValueError(f"Model '{model}' not in allowed models: {self.allowed_models}")
        self.global_model = model
    
    async def set_channel_model(self, channel_id: str, model: str) -> None:
        """Set a channel-specific model with validation."""
        async with self._lock:
            if model not in self.allowed_models:
                raise ValueError(f"Model '{model}' not in allowed models: {self.allowed_models}")
            self.channel_models[str(channel_id)] = model
    
    def get_effective_model(self, channel_id: str) -> str:
        """Get the effective model for a channel, considering channel-specific overrides."""
        channel_id = str(channel_id)
        # First check channel-specific model
        if channel_id in self.channel_models:
            return self.channel_models[channel_id]
        # Fall back to global model
        return self.global_model
    
    # NEWS FEED METHODS
    def get_news_feeds_count(self) -> int:
        """Get the count of configured news feeds."""
        return len(getattr(self, 'news_feeds', {}))
    
    def get_news_channel_config_count(self) -> int:
        """Get the count of channels configured for news."""
        return len(getattr(self, 'news_channel_config', {}))
