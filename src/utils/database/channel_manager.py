import sqlite3
import logging
from typing import Optional, Dict, Any, List

logger = logging.getLogger(__name__)

class ChannelManager:
    """Manages channel records and per-channel configuration."""

    def __init__(self, conn):
        self._conn = conn

    def _ensure_channel_exists(self, channel_id: str, name: Optional[str] = None):
        """Ensures a channel record exists in the CHANNELS table."""
        sql_channel = "INSERT OR IGNORE INTO CHANNELS (channel_id, name) VALUES (?, ?);"
        # Ensure config row exists too, even if empty, to simplify updates
        sql_config = """
        INSERT OR IGNORE INTO CHANNEL_CONFIG (channel_id, model, provider, system_prompt)
        VALUES (?, NULL, NULL, NULL);
        """
        try:
            with self._conn:
                cursor = self._conn.cursor()
                cursor.execute(sql_channel, (channel_id, name))
                cursor.execute(sql_config, (channel_id,))
            logger.debug(f"Ensured channel exists: {channel_id}")
        except sqlite3.Error as e:
            logger.error(f"Error ensuring channel '{channel_id}' exists: {e}", exc_info=True)
            raise

    def set_channel_model(self, channel_id: str, model: Optional[str]):
        """Sets the specific model override for a channel."""
        self._ensure_channel_exists(channel_id)
        sql = """
        UPDATE CHANNEL_CONFIG SET model = ? WHERE channel_id = ?;
        """
        try:
            with self._conn:
                cursor = self._conn.cursor()
                cursor.execute(sql, (model, channel_id))
            logger.debug(f"Set model for channel {channel_id} to {model}")
        except sqlite3.Error as e:
            logger.error(f"Error setting model for channel '{channel_id}': {e}", exc_info=True)
            raise

    def get_channel_model(self, channel_id: str) -> Optional[str]:
        """Gets the specific model override for a channel."""
        sql = "SELECT model FROM CHANNEL_CONFIG WHERE channel_id = ?;"
        try:
            cursor = self._conn.cursor()
            cursor.execute(sql, (channel_id,))
            row = cursor.fetchone()
            return row['model'] if row else None
        except sqlite3.Error as e:
            logger.error(f"Error getting model for channel '{channel_id}': {e}", exc_info=True)
            return None

    def set_channel_system_prompt(self, channel_id: str, prompt: Optional[str]):
        """Sets the specific system prompt override for a channel."""
        self._ensure_channel_exists(channel_id)
        sql = """
        UPDATE CHANNEL_CONFIG SET system_prompt = ? WHERE channel_id = ?;
        """
        try:
            with self._conn:
                cursor = self._conn.cursor()
                cursor.execute(sql, (prompt, channel_id))
            logger.debug(f"Set system prompt for channel {channel_id}")
        except sqlite3.Error as e:
            logger.error(f"Error setting system prompt for channel '{channel_id}': {e}", exc_info=True)
            raise

    def get_channel_system_prompt(self, channel_id: str) -> Optional[str]:
        """Gets the specific system prompt override for a channel."""
        sql = "SELECT system_prompt FROM CHANNEL_CONFIG WHERE channel_id = ?;"
        try:
            cursor = self._conn.cursor()
            cursor.execute(sql, (channel_id,))
            row = cursor.fetchone()
            return row['system_prompt'] if row else None
        except sqlite3.Error as e:
            logger.error(f"Error getting system prompt for channel '{channel_id}': {e}", exc_info=True)
            return None

    def set_channel_provider(self, channel_id: str, provider: Optional[str]):
        """Sets the AI provider for a channel."""
        self._ensure_channel_exists(channel_id)
        sql = """
        UPDATE CHANNEL_CONFIG SET provider = ? WHERE channel_id = ?;
        """
        try:
            with self._conn:
                cursor = self._conn.cursor()
                cursor.execute(sql, (provider, channel_id))
            logger.debug(f"Set provider for channel {channel_id} to {provider}")
        except sqlite3.Error as e:
            logger.error(f"Error setting provider for channel '{channel_id}': {e}", exc_info=True)
            raise

    def get_channel_provider(self, channel_id: str) -> Optional[str]:
        """Gets the AI provider for a channel."""
        sql = "SELECT provider FROM CHANNEL_CONFIG WHERE channel_id = ?;"
        try:
            cursor = self._conn.cursor()
            cursor.execute(sql, (channel_id,))
            row = cursor.fetchone()
            return row['provider'] if row else None
        except sqlite3.Error as e:
            logger.error(f"Error getting provider for channel '{channel_id}': {e}", exc_info=True)
            return None

    def get_channel_config(self, channel_id: str) -> Optional[Dict[str, Optional[str]]]:
        """Gets model, provider and system prompt for a channel."""
        sql = "SELECT model, provider, system_prompt FROM CHANNEL_CONFIG WHERE channel_id = ?;"
        try:
            cursor = self._conn.cursor()
            cursor.execute(sql, (channel_id,))
            row = cursor.fetchone()
            if row:
                return {"model": row["model"], "system_prompt": row["system_prompt"]}
            else:
                return None
        except sqlite3.Error as e:
            logger.error(f"Error getting config for channel '{channel_id}': {e}", exc_info=True)
            return None

    def reset_channel_config(self, channel_id: str) -> bool:
        """Resets a channel's model and system prompt to NULL (effectively using global defaults)."""
        sql = "UPDATE CHANNEL_CONFIG SET model = NULL, provider = NULL, system_prompt = NULL WHERE channel_id = ?;"
        try:
            with self._conn:
                cursor = self._conn.cursor()
                cursor.execute(sql, (channel_id,))
                updated = cursor.rowcount > 0
            if updated:
                logger.debug(f"Reset config for channel: {channel_id}")
            return updated
        except sqlite3.Error as e:
            logger.error(f"Error resetting config for channel '{channel_id}': {e}", exc_info=True)
            raise

    def get_all_configured_channel_ids(self) -> List[str]:
        """Gets IDs of channels with non-NULL model, provider, or system_prompt."""
        sql = """
        SELECT DISTINCT channel_id FROM CHANNEL_CONFIG
        WHERE model IS NOT NULL OR provider IS NOT NULL OR system_prompt IS NOT NULL;
        """
        try:
            cursor = self._conn.cursor()
            cursor.execute(sql)
            rows = cursor.fetchall()
            return [row['channel_id'] for row in rows]
        except sqlite3.Error as e:
            logger.error(f"Error getting configured channel IDs: {e}", exc_info=True)
            return []

    def get_all_channel_configs(self) -> List[Dict[str, Any]]:
        """Gets detailed configuration for all channels with overrides."""
        sql = """
        SELECT channel_id, model, provider, system_prompt
        FROM CHANNEL_CONFIG
        WHERE model IS NOT NULL OR provider IS NOT NULL OR system_prompt IS NOT NULL;
        """
        try:
            cursor = self._conn.cursor()
            cursor.execute(sql)
            rows = cursor.fetchall()
            return [dict(row) for row in rows]
        except sqlite3.Error as e:
            logger.error(f"Error getting all channel configs: {e}", exc_info=True)
            return []
