import sqlite3
import logging
from typing import Any

logger = logging.getLogger(__name__)

class ConfigManager:
    """Manages global configuration key-value storage."""

    def __init__(self, conn):
        self._conn = conn

    def set_global_config(self, key: str, value: Any, value_type: str):
        """
        Sets or updates a global configuration value.

        Args:
            key (str): The configuration key.
            value (Any): The configuration value.
            value_type (str): The type of the value ('string', 'int', 'float', 'bool', 'json').
        """
        if value_type not in ('string', 'int', 'float', 'bool', 'json'):
            raise ValueError(f"Invalid value_type: {value_type}")

        # Convert value to string for storage (except JSON which is already string)
        if value_type == 'json':
            import json
            value_str = json.dumps(value)
        elif value_type == 'bool':
            value_str = "1" if value else "0"
        else:
            value_str = str(value)

        sql = """
        INSERT INTO GLOBAL_CONFIG (key, value, type)
        VALUES (?, ?, ?)
        ON CONFLICT(key) DO UPDATE SET
            value = excluded.value,
            type = excluded.type;
        """
        try:
            with self._conn:
                cursor = self._conn.cursor()
                cursor.execute(sql, (key, value_str, value_type))
            logger.debug(f"Set global config: {key} = {value_str} (type: {value_type})")
        except sqlite3.Error as e:
            logger.error(f"Error setting global config key '{key}': {e}", exc_info=True)
            raise

    def get_global_config(self, key: str, default: Any = None) -> Any:
        """
        Retrieves a global configuration value.

        Args:
            key (str): The configuration key.
            default (Any): The value to return if the key is not found.

        Returns:
            Any: The configuration value, converted to its original type, or the default.
        """
        sql = "SELECT value, type FROM GLOBAL_CONFIG WHERE key = ?;"
        try:
            cursor = self._conn.cursor()
            cursor.execute(sql, (key,))
            row = cursor.fetchone()

            if row:
                value_str = row['value']
                value_type = row['type']

                if value_type == 'string':
                    return value_str
                elif value_type == 'int':
                    return int(value_str)
                elif value_type == 'float':
                    return float(value_str)
                elif value_type == 'bool':
                    return value_str == "1"
                elif value_type == 'json':
                    import json
                    return json.loads(value_str)
                else:
                    logger.warning(f"Unknown config type '{value_type}' for key '{key}'. Returning raw string.")
                    return value_str
            else:
                return default
        except sqlite3.Error as e:
            logger.error(f"Error getting global config key '{key}': {e}", exc_info=True)
            return default
        except (ValueError, TypeError) as e:
            logger.error(f"Error converting value for global config key '{key}': {e}", exc_info=True)
            return default

    def delete_global_config(self, key: str) -> bool:
        """
        Deletes a global configuration key.

        Args:
            key (str): The configuration key to delete.

        Returns:
            bool: True if a key was deleted, False otherwise.
        """
        sql = "DELETE FROM GLOBAL_CONFIG WHERE key = ?;"
        try:
            with self._conn:
                cursor = self._conn.cursor()
                cursor.execute(sql, (key,))
                deleted = cursor.rowcount > 0
            if deleted:
                logger.debug(f"Deleted global config key: {key}")
            return deleted
        except sqlite3.Error as e:
            logger.error(f"Error deleting global config key '{key}': {e}", exc_info=True)
            raise
