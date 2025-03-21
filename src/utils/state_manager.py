"""Centralized state management for the bot."""
from datetime import datetime, timedelta
from typing import Dict, List, Any
import logging

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
        # Chat related state
        self.channel_history = {}
        self.channel_models = {}
        self.channel_system_prompts = {}  # NEW: Store channel-specific system prompts
        
        # Thread related state
        self.threads = {}
        self.simple_id_mapping = {}
        self.discord_threads = {}
        
        # Configuration
        self.max_channel_history = 35
        self.max_threads_per_channel = 10
        self.time_window_hours = 48
        
        # Import allowed models from config
        from ..config import ALLOWED_MODELS, DEFAULT_MODEL
        self.allowed_models = ALLOWED_MODELS
        self.global_model = DEFAULT_MODEL  # NEW: Store the global model
        
    # Getters and setters for all state properties
    # This allows controlled access to the state from different cogs
    
    # Channel history methods
    def get_channel_history(self, channel_id: str) -> List[Dict[str, Any]]:
        return self.channel_history.get(channel_id, [])
    
    def add_to_channel_history(self, channel_id: str, message: Dict[str, Any]):
        if channel_id not in self.channel_history:
            self.channel_history[channel_id] = []
            
        self.channel_history[channel_id].append(message)
        
        # Enforce maximum history size
        if len(self.channel_history[channel_id]) > self.max_channel_history:
            self.channel_history[channel_id] = self.channel_history[channel_id][-self.max_channel_history:]
    
    def clear_channel_history(self, channel_id: str) -> bool:
        """Clear history for a channel. Returns True if any history was cleared."""
        if channel_id in self.channel_history:
            self.channel_history[channel_id] = []
            return True
        return False
    
    # Thread management methods
    def get_thread(self, channel_id: str, thread_id: str) -> Dict[str, Any]:
        """Get thread data by channel and thread ID"""
        return self.threads.get(channel_id, {}).get(thread_id)
    
    def add_thread_message(self, channel_id: str, thread_id: str, message: Dict[str, Any]):
        """Add a message to a thread's history"""
        if channel_id not in self.threads:
            self.threads[channel_id] = {}
            
        if thread_id not in self.threads[channel_id]:
            # Initialize new thread if it doesn't exist
            self.threads[channel_id][thread_id] = {
                "name": "Unnamed Thread",
                "messages": [],
                "created_at": datetime.now()
            }
            
        # Add message to thread history
        self.threads[channel_id][thread_id]["messages"].append(message)
    
    def get_thread_history(self, channel_id: str, thread_id: str, hours_limit: int = None) -> List[Dict[str, Any]]:
        """Get message history for a thread with optional time window"""
        if channel_id not in self.threads or thread_id not in self.threads[channel_id]:
            return []
            
        messages = self.threads[channel_id][thread_id]["messages"]
        
        if not hours_limit:
            hours_limit = self.time_window_hours
            
        # Filter by time window if specified
        cutoff_time = datetime.now() - timedelta(hours=hours_limit)
        return [msg for msg in messages if "timestamp" not in msg or msg["timestamp"] > cutoff_time]
    
    def prune_inactive_data(self):
        """Remove history and model settings for inactive channels and threads"""
        # Prune channel history
        cutoff = datetime.now() - timedelta(days=7)
        inactive_channels = []
        
        for channel_id, history in self.channel_history.items():
            if not history:
                continue
            last_message = history[-1]["timestamp"]
            if last_message < cutoff:
                inactive_channels.append(channel_id)
        
        for channel_id in inactive_channels:
            del self.channel_history[channel_id]
            # Also remove channel model settings if they exist
            if channel_id in self.channel_models:
                del self.channel_models[channel_id]
        
        # Prune inactive threads
        for channel_id in list(self.threads.keys()):
            inactive_threads = []
            for thread_id, thread_data in self.threads[channel_id].items():
                if not thread_data["messages"]:
                    continue
                last_message_time = thread_data["messages"][-1].get("timestamp")
                if last_message_time and last_message_time < datetime.now() - timedelta(days=14):
                    inactive_threads.append(thread_id)
                    # Also clean up simple ID mapping
                    if "simple_id" in thread_data:
                        simple_id = thread_data["simple_id"]
                        if simple_id in self.simple_id_mapping:
                            del self.simple_id_mapping[simple_id]
            
            # Remove inactive threads
            for thread_id in inactive_threads:
                del self.threads[channel_id][thread_id]
                
            # Clean up empty channel entries
            if not self.threads[channel_id]:
                del self.threads[channel_id]
                
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
        """Set the global model."""
        self.global_model = model
    
    def get_effective_model(self, channel_id: str) -> str:
        """Get the effective model for a channel, considering channel-specific overrides."""
        channel_id = str(channel_id)
        # First check channel-specific model
        if channel_id in self.channel_models:
            return self.channel_models[channel_id]
        # Fall back to global model
        return self.global_model

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
        
        # Prune thread data
        threads_pruned = 0
        
        for channel_id in list(self.threads.keys()):
            # Skip if not a dict or empty
            if not isinstance(self.threads[channel_id], dict):
                continue
                
            for thread_id in list(self.threads[channel_id].keys()):
                thread_data = self.threads[channel_id][thread_id]
                if not isinstance(thread_data, dict):
                    continue
                    
                # Check last activity in thread
                messages = thread_data.get("messages", [])
                if messages and isinstance(messages, list) and len(messages) > 0:
                    last_message = messages[-1]
                    if not isinstance(last_message, dict):
                        continue
                        
                    last_time = last_message.get("timestamp")
                    if not last_time:
                        last_time = thread_data.get("created_at")
                    
                    if last_time and isinstance(last_time, datetime) and last_time < thread_cutoff:
                        # Clean up mapping if present
                        if "simple_id" in thread_data:
                            simple_id = thread_data["simple_id"]
                            if simple_id in self.simple_id_mapping:
                                del self.simple_id_mapping[simple_id]
                        
                        # Remove thread
                        del self.threads[channel_id][thread_id]
                        threads_pruned += 1
            
            # Remove empty channels
            if not self.threads[channel_id]:
                del self.threads[channel_id]
        
        return {
            "channels_pruned": channels_pruned,
            "messages_pruned": messages_pruned,
            "threads_pruned": threads_pruned
        }
