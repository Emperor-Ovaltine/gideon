import sqlite3
import os
import logging
from datetime import datetime
from typing import Optional, List, Dict, Any

from ...config import DATA_DIRECTORY
from .schema import SchemaManager
from .config_manager import ConfigManager
from .channel_manager import ChannelManager
from .thread_manager import ThreadManager
from .message_manager import MessageManager
from .user_manager import UserManager
from .reminder_manager import ReminderManager
from .trivia_manager import TriviaManager

logger = logging.getLogger(__name__)

class DatabaseManager:
    """Handles all interactions with the SQLite database."""

    def __init__(self, db_name="gideon_state.db"):
        """
        Initializes the database connection and ensures the schema exists.

        Args:
            db_name (str): The name of the database file within the data directory.
        """
        self.db_path = os.path.join(DATA_DIRECTORY, db_name)
        # Ensure the data directory exists
        os.makedirs(DATA_DIRECTORY, exist_ok=True)
        self._conn = None
        try:
            # Use check_same_thread=False for potential async usage
            self._conn = sqlite3.connect(self.db_path, detect_types=sqlite3.PARSE_DECLTYPES, check_same_thread=False)
            # Use Row factory for dictionary-like access to rows
            self._conn.row_factory = sqlite3.Row
            logger.info(f"Connected to database: {self.db_path}")

            # Initialize schema
            SchemaManager.initialize(self._conn)

            # Initialize managers with shared connection
            self._config = ConfigManager(self._conn)
            self._channels = ChannelManager(self._conn)
            self._threads = ThreadManager(self._conn)
            self._messages = MessageManager(self._conn)
            self._users = UserManager(self._conn)
            self._reminders = ReminderManager(self._conn)
            self._trivia = TriviaManager(self._conn)

        except sqlite3.Error as e:
            logger.error(f"Database connection error to {self.db_path}: {e}", exc_info=True)
            raise

    def _get_cursor(self):
        """Returns a cursor for database operations."""
        if not self._conn:
            raise sqlite3.Error("Database connection is not established.")
        return self._conn.cursor()

    def _commit(self):
        """Commits the current transaction."""
        if self._conn:
            self._conn.commit()

    def close(self):
        """Closes the database connection."""
        if self._conn:
            self._conn.close()
            logger.info("Database connection closed.")
            self._conn = None

    # --- Global Config Methods (delegate to ConfigManager) ---

    def set_global_config(self, key: str, value: Any, value_type: str):
        """Sets or updates a global configuration value."""
        return self._config.set_global_config(key, value, value_type)

    def get_global_config(self, key: str, default: Any = None) -> Any:
        """Retrieves a global configuration value."""
        return self._config.get_global_config(key, default)

    def delete_global_config(self, key: str) -> bool:
        """Deletes a global configuration key."""
        return self._config.delete_global_config(key)

    # --- Channel Methods (delegate to ChannelManager) ---

    def _ensure_channel_exists(self, channel_id: str, name: Optional[str] = None):
        """Ensures a channel record exists in the CHANNELS table."""
        return self._channels._ensure_channel_exists(channel_id, name)

    def set_channel_model(self, channel_id: str, model: Optional[str]):
        """Sets the specific model override for a channel."""
        return self._channels.set_channel_model(channel_id, model)

    def get_channel_model(self, channel_id: str) -> Optional[str]:
        """Gets the specific model override for a channel."""
        return self._channels.get_channel_model(channel_id)

    def set_channel_system_prompt(self, channel_id: str, prompt: Optional[str]):
        """Sets the specific system prompt override for a channel."""
        return self._channels.set_channel_system_prompt(channel_id, prompt)

    def get_channel_system_prompt(self, channel_id: str) -> Optional[str]:
        """Gets the specific system prompt override for a channel."""
        return self._channels.get_channel_system_prompt(channel_id)

    def set_channel_provider(self, channel_id: str, provider: Optional[str]):
        """Sets the AI provider for a channel."""
        return self._channels.set_channel_provider(channel_id, provider)

    def get_channel_provider(self, channel_id: str) -> Optional[str]:
        """Gets the AI provider for a channel."""
        return self._channels.get_channel_provider(channel_id)

    def get_channel_config(self, channel_id: str) -> Optional[Dict[str, Optional[str]]]:
        """Gets model, provider and system prompt for a channel."""
        return self._channels.get_channel_config(channel_id)

    def reset_channel_config(self, channel_id: str) -> bool:
        """Resets a channel's model and system prompt to NULL."""
        return self._channels.reset_channel_config(channel_id)

    def get_all_configured_channel_ids(self) -> List[str]:
        """Gets IDs of channels with non-NULL model, provider, or system_prompt."""
        return self._channels.get_all_configured_channel_ids()

    def get_all_channel_configs(self) -> List[Dict[str, Any]]:
        """Gets detailed configuration for all channels with overrides."""
        return self._channels.get_all_channel_configs()

    # --- Thread Methods (delegate to ThreadManager) ---

    def add_thread(self, thread_id: str, channel_id: str, name: str, created_at: datetime):
        """Adds a new thread record."""
        # Ensure the parent channel exists first
        self._ensure_channel_exists(channel_id)
        return self._threads.add_thread(thread_id, channel_id, name, created_at)

    def get_thread_info(self, thread_id: str) -> Optional[Dict[str, Any]]:
        """Gets information about a specific thread."""
        return self._threads.get_thread_info(thread_id)

    def prune_old_threads(self, cutoff_timestamp: datetime) -> int:
        """Deletes threads older than the cutoff timestamp."""
        return self._threads.prune_old_threads(cutoff_timestamp)

    def set_thread_model(self, thread_id: str, model: Optional[str]):
        """Sets the specific model override for a thread."""
        return self._threads.set_thread_model(thread_id, model)

    def set_thread_system_prompt(self, thread_id: str, prompt: Optional[str]):
        """Sets the specific system prompt override for a thread."""
        return self._threads.set_thread_system_prompt(thread_id, prompt)

    def get_thread_config(self, thread_id: str) -> Optional[Dict[str, Optional[str]]]:
        """Gets both model and system prompt for a thread."""
        return self._threads.get_thread_config(thread_id)

    def list_threads_for_channel(self, channel_id: str) -> List[Dict[str, Any]]:
        """Lists all threads associated with a channel."""
        return self._threads.list_threads_for_channel(channel_id)

    def delete_thread(self, thread_id: str) -> bool:
        """Deletes a thread by its ID."""
        return self._threads.delete_thread(thread_id)

    def rename_thread(self, thread_id: str, new_name: str) -> bool:
        """Renames a thread."""
        return self._threads.rename_thread(thread_id, new_name)

    def get_thread_message_count(self, thread_id: str) -> int:
        """Gets the number of messages in a specific thread."""
        return self._threads.get_thread_message_count(thread_id)

    def get_all_configured_thread_ids(self) -> List[str]:
        """Gets IDs of threads with non-NULL model or system_prompt."""
        return self._threads.get_all_configured_thread_ids()

    def get_all_thread_configs(self) -> List[Dict[str, Any]]:
        """Gets detailed configuration for all threads with overrides."""
        return self._threads.get_all_thread_configs()

    # --- Message Methods (delegate to MessageManager) ---

    def add_message(self, role: str, content: str, timestamp: datetime,
                    channel_id: Optional[str] = None,
                    thread_id: Optional[str] = None,
                    user_id: Optional[str] = None) -> int:
        """Adds a message to the database."""
        # Ensure parent channel/thread exists if provided
        if channel_id:
            self._ensure_channel_exists(channel_id)
        return self._messages.add_message(role, content, timestamp, channel_id, thread_id, user_id)

    def get_channel_history(self, channel_id: str, limit: Optional[int] = None, hours_limit: Optional[int] = None) -> List[Dict[str, Any]]:
        """Gets message history for a specific channel."""
        return self._messages.get_channel_history(channel_id, limit, hours_limit)

    def get_thread_history(self, thread_id: str, limit: Optional[int] = None, hours_limit: Optional[int] = None) -> List[Dict[str, Any]]:
        """Gets message history for a specific thread."""
        return self._messages.get_thread_history(thread_id, limit, hours_limit)

    def prune_old_messages(self, cutoff_timestamp: datetime) -> int:
        """Deletes messages older than the specified cutoff timestamp."""
        return self._messages.prune_old_messages(cutoff_timestamp)

    # --- User Methods (delegate to UserManager) ---

    def _ensure_user_exists(self, user_id: str):
        """Ensures a user record exists."""
        return self._users._ensure_user_exists(user_id)

    def set_user_preferences(self, user_id: str, preferences: Dict[str, Any]):
        """Sets the preferences JSON for a user."""
        return self._users.set_user_preferences(user_id, preferences)

    def get_user_preferences(self, user_id: str) -> Optional[Dict[str, Any]]:
        """Gets the preferences JSON for a user."""
        return self._users.get_user_preferences(user_id)

    # --- Reminder Methods (delegate to ReminderManager) ---

    def add_reminder(self, user_id: str, channel_id: str, message: str,
                     due_timestamp: datetime) -> int:
        """Adds a new reminder to the database."""
        # Ensure parent channel exists
        self._ensure_channel_exists(channel_id)
        return self._reminders.add_reminder(user_id, channel_id, message, due_timestamp)

    def get_due_reminders(self, current_time: datetime) -> List[Dict[str, Any]]:
        """Gets reminders that are due."""
        return self._reminders.get_due_reminders(current_time)

    def mark_reminder_sent(self, reminder_id: int) -> bool:
        """Marks a reminder as sent."""
        return self._reminders.mark_reminder_sent(reminder_id)

    def get_user_reminders(self, user_id: str, include_sent: bool = False) -> List[Dict[str, Any]]:
        """Gets reminders for a specific user."""
        return self._reminders.get_user_reminders(user_id, include_sent)

    def delete_reminder(self, reminder_id: int, user_id: str) -> bool:
        """Deletes a reminder by ID."""
        return self._reminders.delete_reminder(reminder_id, user_id)

    def prune_old_reminders(self, cutoff_timestamp: datetime) -> int:
        """Deletes sent reminders older than cutoff."""
        return self._reminders.prune_old_reminders(cutoff_timestamp)

    # --- Trivia Methods (delegate to TriviaManager) ---

    def create_trivia_session(self, thread_id: str, channel_id: str, user_id: Optional[str],
                             game_mode: str, category: Optional[str], difficulty: str,
                             questions_total: int = 10) -> int:
        """Creates a new trivia game session."""
        self._ensure_channel_exists(channel_id)
        return self._trivia.create_session(thread_id, channel_id, user_id, game_mode,
                                          category, difficulty, questions_total)

    def get_active_trivia_session(self, thread_id: str) -> Optional[Dict[str, Any]]:
        """Gets the active trivia session for a thread."""
        return self._trivia.get_active_session_by_thread(thread_id)

    def update_trivia_questions_answered(self, thread_id: str) -> bool:
        """Increments the questions_answered counter."""
        return self._trivia.update_questions_answered(thread_id)

    def end_trivia_session(self, thread_id: str) -> bool:
        """Ends a trivia session."""
        return self._trivia.end_session(thread_id)

    def update_trivia_leaderboard(self, user_id: str, server_id: str,
                                  questions_answered: int, correct_answers: int,
                                  points_earned: int, current_streak: int,
                                  response_time: float) -> bool:
        """Updates leaderboard stats for a user."""
        return self._trivia.update_leaderboard(user_id, server_id, questions_answered,
                                              correct_answers, points_earned,
                                              current_streak, response_time)

    def get_trivia_leaderboard(self, server_id: str, timeframe: str = 'all_time',
                              limit: int = 10) -> List[Dict[str, Any]]:
        """Gets the leaderboard rankings for a server."""
        return self._trivia.get_leaderboard(server_id, timeframe, limit)

    def get_trivia_user_stats(self, user_id: str, server_id: str) -> Optional[Dict[str, Any]]:
        """Gets trivia stats for a specific user."""
        return self._trivia.get_user_stats(user_id, server_id)

    def add_trivia_achievement(self, user_id: str, server_id: str,
                              achievement_type: str, achievement_name: str,
                              metadata_json: Optional[str] = None) -> int:
        """Adds an achievement for a user."""
        return self._trivia.add_achievement(user_id, server_id, achievement_type,
                                           achievement_name, metadata_json)

    def get_trivia_user_achievements(self, user_id: str, server_id: str) -> List[Dict[str, Any]]:
        """Gets all achievements for a user."""
        return self._trivia.get_user_achievements(user_id, server_id)

    def has_trivia_achievement(self, user_id: str, server_id: str, achievement_type: str) -> bool:
        """Checks if user has a specific achievement."""
        return self._trivia.has_achievement(user_id, server_id, achievement_type)

    def prune_old_trivia_sessions(self, days_old: int = 30) -> int:
        """Deletes inactive trivia sessions older than specified days."""
        return self._trivia.prune_old_sessions(days_old)

    # Note: The following methods were removed as they were part of the news feed system:
    # - All news feed management methods
    # - All news subscription methods
    # - All article history methods
    # - All article summary methods (both channel and user-specific)
    # - prune_old_articles, prune_old_summaries, prune_old_user_summaries
    # - get_news_article_history_count
    # - set_last_digest_content, get_last_digest_content
    # - get_users_with_personal_feeds
