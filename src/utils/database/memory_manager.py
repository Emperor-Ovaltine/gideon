import re
import sqlite3
import logging
from datetime import datetime
from typing import Optional, List, Dict, Any

logger = logging.getLogger(__name__)


class MemoryManager:
    """Manages persistent channel memory summaries."""

    def __init__(self, conn):
        self._conn = conn

    def get_memories(self, channel_id: str, limit: int = 10) -> List[Dict[str, Any]]:
        """Returns up to `limit` summaries for a channel, oldest first."""
        sql = """
        SELECT id, channel_id, summary, message_count, conversation_start, created_at
        FROM CHANNEL_MEMORY
        WHERE channel_id = ?
        ORDER BY created_at DESC
        LIMIT ?;
        """
        try:
            cursor = self._conn.cursor()
            cursor.execute(sql, (channel_id, limit))
            rows = cursor.fetchall()
            return [dict(row) for row in reversed(rows)]
        except sqlite3.Error as e:
            logger.error(f"Error getting memories for channel '{channel_id}': {e}", exc_info=True)
            return []

    def add_memory(self, channel_id: str, summary: str, message_count: int,
                   conversation_start: Optional[datetime] = None) -> int:
        """Inserts a new memory summary. Returns the new row id."""
        sql = """
        INSERT INTO CHANNEL_MEMORY (channel_id, summary, message_count, conversation_start, created_at)
        VALUES (?, ?, ?, ?, ?);
        """
        try:
            with self._conn:
                cursor = self._conn.cursor()
                cursor.execute(sql, (channel_id, summary, message_count, conversation_start, datetime.now()))
                return cursor.lastrowid
        except sqlite3.Error as e:
            logger.error(f"Error adding memory for channel '{channel_id}': {e}", exc_info=True)
            raise

    def delete_memories(self, channel_id: str) -> int:
        """Deletes all memory summaries for a channel. Returns number deleted."""
        sql = "DELETE FROM CHANNEL_MEMORY WHERE channel_id = ?;"
        try:
            with self._conn:
                cursor = self._conn.cursor()
                cursor.execute(sql, (channel_id,))
                return cursor.rowcount
        except sqlite3.Error as e:
            logger.error(f"Error deleting memories for channel '{channel_id}': {e}", exc_info=True)
            raise

    def prune_memories(self, channel_id: str, max_count: int) -> int:
        """Keeps only the `max_count` most recent summaries, deletes the rest."""
        sql = """
        DELETE FROM CHANNEL_MEMORY
        WHERE channel_id = ?
          AND id NOT IN (
              SELECT id FROM CHANNEL_MEMORY
              WHERE channel_id = ?
              ORDER BY created_at DESC
              LIMIT ?
          );
        """
        try:
            with self._conn:
                cursor = self._conn.cursor()
                cursor.execute(sql, (channel_id, channel_id, max_count))
                return cursor.rowcount
        except sqlite3.Error as e:
            logger.error(f"Error pruning memories for channel '{channel_id}': {e}", exc_info=True)
            raise

    def search_memories(self, channel_id: str, query: str, limit: int = 3) -> List[Dict[str, Any]]:
        """Full-text search over a channel's memory summaries (FTS5).

        Returns the best-ranked matches, or [] when FTS is unavailable or the
        query has no usable terms.
        """
        # Extract plain word tokens — raw user text is not valid FTS5 query syntax
        terms = re.findall(r"[A-Za-z0-9_]{3,}", query or "")
        if not terms:
            return []
        match_expr = " OR ".join(terms[:12])

        sql = """
        SELECT m.id, m.channel_id, m.summary, m.message_count, m.conversation_start, m.created_at
        FROM memory_fts f
        JOIN CHANNEL_MEMORY m ON m.id = f.rowid
        WHERE memory_fts MATCH ? AND m.channel_id = ?
        ORDER BY rank
        LIMIT ?;
        """
        try:
            cursor = self._conn.cursor()
            cursor.execute(sql, (match_expr, channel_id, limit))
            return [dict(row) for row in cursor.fetchall()]
        except sqlite3.Error as e:
            logger.warning(f"Memory FTS search failed for channel '{channel_id}': {e}")
            return []

    def get_all_memory_stats(self) -> List[Dict[str, Any]]:
        """Returns per-channel memory stats: channel_id, count, latest created_at."""
        sql = """
        SELECT channel_id,
               COUNT(*) AS summary_count,
               MAX(created_at) AS latest_summary_at
        FROM CHANNEL_MEMORY
        GROUP BY channel_id
        ORDER BY latest_summary_at DESC;
        """
        try:
            cursor = self._conn.cursor()
            cursor.execute(sql)
            return [dict(row) for row in cursor.fetchall()]
        except sqlite3.Error as e:
            logger.error(f"Error getting memory stats: {e}", exc_info=True)
            return []
