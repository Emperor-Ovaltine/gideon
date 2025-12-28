import sqlite3
import logging
from typing import Dict, Any, Optional

logger = logging.getLogger(__name__)

class UserManager:
    """Manages user records and preferences."""

    def __init__(self, conn):
        self._conn = conn

    def _ensure_user_exists(self, user_id: str):
        """Ensures a user record exists."""
        sql = "INSERT OR IGNORE INTO USERS (user_id, preferences_json) VALUES (?, NULL);"
        try:
            with self._conn:
                cursor = self._conn.cursor()
                cursor.execute(sql, (user_id,))
            logger.debug(f"Ensured user exists: {user_id}")
        except sqlite3.Error as e:
            logger.error(f"Error ensuring user '{user_id}' exists: {e}", exc_info=True)
            raise

    def set_user_preferences(self, user_id: str, preferences: Dict[str, Any]):
        """Sets the preferences JSON for a user."""
        import json
        self._ensure_user_exists(user_id)
        prefs_json = json.dumps(preferences)
        sql = "UPDATE USERS SET preferences_json = ? WHERE user_id = ?;"
        try:
            with self._conn:
                cursor = self._conn.cursor()
                cursor.execute(sql, (prefs_json, user_id))
            logger.debug(f"Set preferences for user {user_id}")
        except sqlite3.Error as e:
            logger.error(f"Error setting preferences for user '{user_id}': {e}", exc_info=True)
            raise

    def get_user_preferences(self, user_id: str) -> Optional[Dict[str, Any]]:
        """Gets the preferences JSON for a user."""
        import json
        sql = "SELECT preferences_json FROM USERS WHERE user_id = ?;"
        try:
            cursor = self._conn.cursor()
            cursor.execute(sql, (user_id,))
            row = cursor.fetchone()
            if row and row['preferences_json']:
                return json.loads(row['preferences_json'])
            else:
                return None
        except sqlite3.Error as e:
            logger.error(f"Error getting preferences for user '{user_id}': {e}", exc_info=True)
            return None
        except json.JSONDecodeError as e:
            logger.error(f"Error decoding preferences JSON for user '{user_id}': {e}", exc_info=True)
            return None
