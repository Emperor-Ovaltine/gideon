import sqlite3
import logging
from datetime import datetime
from typing import Optional, List, Dict, Any

logger = logging.getLogger(__name__)


class APIKeyManager:
    """Manages API key storage and audit logging in the database."""

    def __init__(self, conn):
        self._conn = conn

    def add_key(self, key_id: str, provider: str, encrypted_key: str,
                key_alias: Optional[str] = None) -> bool:
        sql = """
        INSERT INTO API_KEYS (key_id, provider, encrypted_key, key_alias, created_at, validation_status)
        VALUES (?, ?, ?, ?, ?, 'untested');
        """
        try:
            with self._conn:
                cursor = self._conn.cursor()
                cursor.execute(sql, (key_id, provider, encrypted_key, key_alias,
                                     datetime.utcnow().isoformat()))
            logger.info(f"Added API key '{key_id}' for provider '{provider}'")
            return True
        except sqlite3.Error as e:
            logger.error(f"Error adding API key '{key_id}': {e}", exc_info=True)
            raise

    def update_key(self, key_id: str, encrypted_key: Optional[str] = None,
                   key_alias: Optional[str] = None) -> bool:
        parts = []
        params = []
        if encrypted_key is not None:
            parts.append("encrypted_key = ?")
            params.append(encrypted_key)
            parts.append("validation_status = 'untested'")
            parts.append("last_validated = NULL")
        if key_alias is not None:
            parts.append("key_alias = ?")
            params.append(key_alias)
        if not parts:
            return False
        params.append(key_id)
        sql = f"UPDATE API_KEYS SET {', '.join(parts)} WHERE key_id = ?;"
        try:
            with self._conn:
                cursor = self._conn.cursor()
                cursor.execute(sql, params)
                updated = cursor.rowcount > 0
            if updated:
                logger.info(f"Updated API key '{key_id}'")
            return updated
        except sqlite3.Error as e:
            logger.error(f"Error updating API key '{key_id}': {e}", exc_info=True)
            raise

    def delete_key(self, key_id: str) -> bool:
        sql = "DELETE FROM API_KEYS WHERE key_id = ?;"
        try:
            with self._conn:
                cursor = self._conn.cursor()
                cursor.execute(sql, (key_id,))
                deleted = cursor.rowcount > 0
            if deleted:
                logger.info(f"Deleted API key '{key_id}'")
            return deleted
        except sqlite3.Error as e:
            logger.error(f"Error deleting API key '{key_id}': {e}", exc_info=True)
            raise

    def get_key(self, key_id: str) -> Optional[Dict[str, Any]]:
        sql = "SELECT * FROM API_KEYS WHERE key_id = ?;"
        try:
            cursor = self._conn.cursor()
            cursor.execute(sql, (key_id,))
            row = cursor.fetchone()
            return dict(row) if row else None
        except sqlite3.Error as e:
            logger.error(f"Error getting API key '{key_id}': {e}", exc_info=True)
            return None

    def get_keys_by_provider(self, provider: str) -> List[Dict[str, Any]]:
        sql = "SELECT * FROM API_KEYS WHERE provider = ? ORDER BY created_at DESC;"
        try:
            cursor = self._conn.cursor()
            cursor.execute(sql, (provider,))
            return [dict(row) for row in cursor.fetchall()]
        except sqlite3.Error as e:
            logger.error(f"Error getting keys for provider '{provider}': {e}", exc_info=True)
            return []

    def get_active_key_for_provider(self, provider: str) -> Optional[Dict[str, Any]]:
        sql = """
        SELECT * FROM API_KEYS
        WHERE provider = ? AND is_active = 1
        ORDER BY created_at DESC
        LIMIT 1;
        """
        try:
            cursor = self._conn.cursor()
            cursor.execute(sql, (provider,))
            row = cursor.fetchone()
            return dict(row) if row else None
        except sqlite3.Error as e:
            logger.error(f"Error getting active key for '{provider}': {e}", exc_info=True)
            return None

    def get_all_keys(self) -> List[Dict[str, Any]]:
        sql = "SELECT * FROM API_KEYS ORDER BY provider, created_at DESC;"
        try:
            cursor = self._conn.cursor()
            cursor.execute(sql)
            return [dict(row) for row in cursor.fetchall()]
        except sqlite3.Error as e:
            logger.error(f"Error getting all API keys: {e}", exc_info=True)
            return []

    def set_key_active(self, key_id: str, is_active: bool) -> bool:
        sql = "UPDATE API_KEYS SET is_active = ? WHERE key_id = ?;"
        try:
            with self._conn:
                cursor = self._conn.cursor()
                cursor.execute(sql, (1 if is_active else 0, key_id))
                return cursor.rowcount > 0
        except sqlite3.Error as e:
            logger.error(f"Error setting active state for key '{key_id}': {e}", exc_info=True)
            raise

    def update_last_used(self, key_id: str) -> bool:
        sql = "UPDATE API_KEYS SET last_used = ? WHERE key_id = ?;"
        try:
            with self._conn:
                cursor = self._conn.cursor()
                cursor.execute(sql, (datetime.utcnow().isoformat(), key_id))
                return cursor.rowcount > 0
        except sqlite3.Error as e:
            logger.error(f"Error updating last_used for key '{key_id}': {e}", exc_info=True)
            return False

    def update_validation_status(self, key_id: str, status: str,
                                 timestamp: Optional[str] = None) -> bool:
        ts = timestamp or datetime.utcnow().isoformat()
        sql = "UPDATE API_KEYS SET validation_status = ?, last_validated = ? WHERE key_id = ?;"
        try:
            with self._conn:
                cursor = self._conn.cursor()
                cursor.execute(sql, (status, ts, key_id))
                return cursor.rowcount > 0
        except sqlite3.Error as e:
            logger.error(f"Error updating validation status for key '{key_id}': {e}", exc_info=True)
            raise

    # --- Audit Log ---

    def add_audit_entry(self, key_id: str, action: str,
                        user_identifier: Optional[str] = None,
                        details: Optional[str] = None) -> int:
        sql = """
        INSERT INTO API_KEY_AUDIT (key_id, action, timestamp, user_identifier, details)
        VALUES (?, ?, ?, ?, ?);
        """
        try:
            with self._conn:
                cursor = self._conn.cursor()
                cursor.execute(sql, (key_id, action, datetime.utcnow().isoformat(),
                                     user_identifier, details))
                return cursor.lastrowid
        except sqlite3.Error as e:
            logger.error(f"Error adding audit entry for key '{key_id}': {e}", exc_info=True)
            return -1

    def get_audit_log(self, key_id: Optional[str] = None,
                      limit: int = 50) -> List[Dict[str, Any]]:
        if key_id:
            sql = """
            SELECT * FROM API_KEY_AUDIT
            WHERE key_id = ?
            ORDER BY timestamp DESC
            LIMIT ?;
            """
            params = (key_id, limit)
        else:
            sql = """
            SELECT * FROM API_KEY_AUDIT
            ORDER BY timestamp DESC
            LIMIT ?;
            """
            params = (limit,)
        try:
            cursor = self._conn.cursor()
            cursor.execute(sql, params)
            return [dict(row) for row in cursor.fetchall()]
        except sqlite3.Error as e:
            logger.error(f"Error getting audit log: {e}", exc_info=True)
            return []

    def prune_old_audit_entries(self, cutoff_timestamp: datetime) -> int:
        sql = "DELETE FROM API_KEY_AUDIT WHERE timestamp < ?;"
        try:
            with self._conn:
                cursor = self._conn.cursor()
                cursor.execute(sql, (cutoff_timestamp.isoformat(),))
                count = cursor.rowcount
            if count > 0:
                logger.info(f"Pruned {count} old API key audit entries")
            return count
        except sqlite3.Error as e:
            logger.error(f"Error pruning audit entries: {e}", exc_info=True)
            return 0
