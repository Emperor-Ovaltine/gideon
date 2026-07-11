"""
Shared pieces of the web-search flows, used by both the /search command
(chat_commands.py) and the web_search tool path (mention_commands.py) so
the two don't drift.
"""

from typing import Optional

# Status message shown while a search is in flight; use .format(query=...)
SEARCHING_STATUS = "🔍 Searching for information about: **{query}**..."


def build_search_system_prompt(channel_system_prompt: Optional[str]) -> str:
    """Wraps the channel's effective system prompt with search instructions."""
    if channel_system_prompt:
        return channel_system_prompt + "\n\nYou have access to web search. When answering, use the most current information available from searching the web."
    return "You are a helpful AI assistant with access to web search. When answering questions, use the most current information available from searching the web. Always cite your sources."
