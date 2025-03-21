"""Utilities for conversation management."""
from datetime import datetime, timedelta
from typing import List, Dict, Any
from .state_manager import BotStateManager

async def get_channel_context(channel_id: str) -> List[Dict[str, str]]:
    """Get the conversation context for a channel"""
    state = BotStateManager()
    channel_history = state.get_channel_history(channel_id)
    
    if not channel_history:
        return []
        
    # Get messages from the past X hours
    cutoff_time = datetime.now() - timedelta(hours=state.time_window_hours)
    recent_messages = [
        {
            "role": msg["role"],
            "content": f"{msg['name']}: {msg['content']}" if "name" in msg else msg["content"]
        }
        for msg in channel_history
        if msg["timestamp"] > cutoff_time
    ]
    
    # Limit to max_channel_history most recent messages
    return recent_messages[-state.max_channel_history:]

# More utility functions...
