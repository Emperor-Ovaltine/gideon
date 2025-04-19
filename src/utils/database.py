import sqlite3
import os
import logging
from datetime import datetime
from typing import Optional, List, Dict, Any, Tuple

# Import DATA_DIRECTORY from config
from ..config import DATA_DIRECTORY

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
            # Use check_same_thread=False for potential async usage, though direct async isn't standard in sqlite3
            # Register adapter for datetime objects (should be default, but explicit is safer)
            # sqlite3.register_adapter(datetime, lambda val: val.isoformat()) # Not strictly needed for storing datetime objects

            # Register converter for DATETIME column type
            # Removed: Register converter for DATETIME column type
            # sqlite3.register_converter("DATETIME", datetime.fromisoformat)

            # Use check_same_thread=False for potential async usage, though direct async isn't standard in sqlite3
            # Consider using a library like aiosqlite if heavy async DB operations are needed later.
            # Use check_same_thread=False for potential async usage.
            # Enable detect_types to automatically convert declared types (like DATETIME).
            self._conn = sqlite3.connect(self.db_path, detect_types=sqlite3.PARSE_DECLTYPES, check_same_thread=False)
            # Use Row factory for dictionary-like access to rows
            self._conn.row_factory = sqlite3.Row
            logger.info(f"Connected to database: {self.db_path}")
            self._initialize_schema()
        except sqlite3.Error as e:
            logger.error(f"Database connection error to {self.db_path}: {e}", exc_info=True)
            raise  # Re-raise the exception to signal failure

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

    def _initialize_schema(self):
        """Creates database tables if they don't already exist."""
        schema_statements = [
            """
            CREATE TABLE IF NOT EXISTS GLOBAL_CONFIG (
                key TEXT PRIMARY KEY,
                value TEXT,
                type TEXT NOT NULL CHECK(type IN ('string', 'int', 'float', 'bool', 'json'))
            );
            """,
            """
            CREATE TABLE IF NOT EXISTS CHANNELS (
                channel_id TEXT PRIMARY KEY,
                name TEXT
            );
            """,
            # Added foreign key constraint to CHANNELS
            """
            CREATE TABLE IF NOT EXISTS CHANNEL_CONFIG (
                channel_id TEXT PRIMARY KEY,
                model TEXT,
                system_prompt TEXT,
                FOREIGN KEY (channel_id) REFERENCES CHANNELS(channel_id) ON DELETE CASCADE
            );
            """,
            # Added foreign key constraint to CHANNELS
            """
            CREATE TABLE IF NOT EXISTS THREADS (
                thread_id TEXT PRIMARY KEY,
                channel_id TEXT,
                name TEXT,
                created_at DATETIME NOT NULL,
                model TEXT, -- Added model column
                system_prompt TEXT, -- Added system_prompt column
                FOREIGN KEY (channel_id) REFERENCES CHANNELS(channel_id) ON DELETE SET NULL
            );
            """,
            # Added foreign key constraints and indexes
            """
            CREATE TABLE IF NOT EXISTS MESSAGES (
                message_pk INTEGER PRIMARY KEY AUTOINCREMENT,
                channel_id TEXT,
                thread_id TEXT,
                user_id TEXT,
                role TEXT NOT NULL CHECK(role IN ('user', 'assistant', 'system', 'tool')),
                content TEXT NOT NULL,
                timestamp DATETIME NOT NULL,
                FOREIGN KEY (channel_id) REFERENCES CHANNELS(channel_id) ON DELETE CASCADE,
                FOREIGN KEY (thread_id) REFERENCES THREADS(thread_id) ON DELETE CASCADE
            );
            """,
            """CREATE INDEX IF NOT EXISTS idx_messages_channel_timestamp ON MESSAGES (channel_id, timestamp);""",
            """CREATE INDEX IF NOT EXISTS idx_messages_thread_timestamp ON MESSAGES (thread_id, timestamp);""",
            """CREATE INDEX IF NOT EXISTS idx_messages_timestamp ON MESSAGES (timestamp);""",
            """
            CREATE TABLE IF NOT EXISTS NEWS_FEEDS (
                feed_id TEXT PRIMARY KEY, -- Typically the URL
                url TEXT UNIQUE,          -- Explicit URL column (can enforce uniqueness)
                name TEXT,
                category TEXT,            -- Category for the feed
                last_checked DATETIME
            );
            """,
            # Added foreign key constraints
            """
            CREATE TABLE IF NOT EXISTS NEWS_CHANNEL_SUBSCRIPTIONS (
                channel_id TEXT NOT NULL,
                feed_id TEXT NOT NULL,
                PRIMARY KEY (channel_id, feed_id),
                FOREIGN KEY (channel_id) REFERENCES CHANNELS(channel_id) ON DELETE CASCADE,
                FOREIGN KEY (feed_id) REFERENCES NEWS_FEEDS(feed_id) ON DELETE CASCADE
            );
            """,
            # Added foreign key constraint and index
            """
            CREATE TABLE IF NOT EXISTS NEWS_ARTICLES_HISTORY (
                article_identifier TEXT NOT NULL,
                feed_id TEXT NOT NULL,
                processed_at DATETIME NOT NULL,
                PRIMARY KEY (article_identifier, feed_id),
                FOREIGN KEY (feed_id) REFERENCES NEWS_FEEDS(feed_id) ON DELETE CASCADE
            );
            """,
            """CREATE INDEX IF NOT EXISTS idx_news_articles_processed_at ON NEWS_ARTICLES_HISTORY (processed_at);""",
            """
            CREATE TABLE IF NOT EXISTS USERS (
                user_id TEXT PRIMARY KEY,
                preferences_json TEXT
            );
            """
            # Add more indexes as needed based on query patterns
        ]

        try:
            with self._conn: # Use connection as context manager for transaction
                cursor = self._get_cursor()
                for statement in schema_statements:
                    cursor.execute(statement)
                logger.info("Database schema creation/verification complete.")

                # --- Schema Migrations ---
                # Add url and category columns to NEWS_FEEDS if they don't exist
                self._add_column_if_not_exists(cursor, "NEWS_FEEDS", "url", "TEXT") # Removed UNIQUE constraint for compatibility
                self._add_column_if_not_exists(cursor, "NEWS_FEEDS", "category", "TEXT")

                logger.info("Database schema migration checks complete.")
        except sqlite3.Error as e:
            logger.error(f"Error initializing/migrating database schema: {e}", exc_info=True)
            raise

    def _add_column_if_not_exists(self, cursor: sqlite3.Cursor, table_name: str, column_name: str, column_type: str):
        """Helper to add a column to a table if it doesn't already exist."""
        try:
            # Check if column exists using PRAGMA table_info
            cursor.execute(f"PRAGMA table_info({table_name})")
            columns = [column[1] for column in cursor.fetchall()]
            if column_name not in columns:
                cursor.execute(f"ALTER TABLE {table_name} ADD COLUMN {column_name} {column_type}")
                logger.info(f"Added column '{column_name}' to table '{table_name}'.")
            else:
                 logger.debug(f"Column '{column_name}' already exists in table '{table_name}'.")
        except sqlite3.Error as e:
            # Specifically ignore "duplicate column name" error if ALTER TABLE fails concurrently,
            # though the PRAGMA check should prevent this in most cases.
            if "duplicate column name" in str(e).lower():
                 logger.warning(f"Attempted to add duplicate column '{column_name}' to '{table_name}', ignoring. Error: {e}")
            else:
                logger.error(f"Error adding column '{column_name}' to table '{table_name}': {e}", exc_info=True)
                raise # Re-raise other errors

    # --- Global Config Methods ---

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
                cursor = self._get_cursor()
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
            cursor = self._get_cursor()
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
            # In case of error, maybe return default to avoid crashing? Or re-raise?
            # Let's return default for now to be safer during operation.
            return default
        except (ValueError, TypeError) as e:
             logger.error(f"Error converting value for global config key '{key}': {e}", exc_info=True)
             return default # Return default if conversion fails

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
                cursor = self._get_cursor()
                cursor.execute(sql, (key,))
                deleted = cursor.rowcount > 0
            if deleted:
                logger.debug(f"Deleted global config key: {key}")
            return deleted
        except sqlite3.Error as e:
            logger.error(f"Error deleting global config key '{key}': {e}", exc_info=True)
            raise

    # --- Channel Methods ---

    def _ensure_channel_exists(self, channel_id: str, name: Optional[str] = None):
        """Ensures a channel record exists in the CHANNELS table."""
        sql_channel = "INSERT OR IGNORE INTO CHANNELS (channel_id, name) VALUES (?, ?);"
        # Ensure config row exists too, even if empty, to simplify updates
        sql_config = """
        INSERT OR IGNORE INTO CHANNEL_CONFIG (channel_id, model, system_prompt)
        VALUES (?, NULL, NULL);
        """
        try:
            with self._conn:
                cursor = self._get_cursor()
                cursor.execute(sql_channel, (channel_id, name))
                cursor.execute(sql_config, (channel_id,))
            logger.debug(f"Ensured channel exists: {channel_id}")
        except sqlite3.Error as e:
            logger.error(f"Error ensuring channel '{channel_id}' exists: {e}", exc_info=True)
            raise

    def set_channel_model(self, channel_id: str, model: Optional[str]):
        """Sets the specific model override for a channel."""
        self._ensure_channel_exists(channel_id) # Make sure channel record exists
        sql = """
        UPDATE CHANNEL_CONFIG SET model = ? WHERE channel_id = ?;
        """
        try:
            with self._conn:
                cursor = self._get_cursor()
                cursor.execute(sql, (model, channel_id))
            logger.debug(f"Set model for channel {channel_id} to {model}")
        except sqlite3.Error as e:
            logger.error(f"Error setting model for channel '{channel_id}': {e}", exc_info=True)
            raise

    def get_channel_model(self, channel_id: str) -> Optional[str]:
        """Gets the specific model override for a channel."""
        sql = "SELECT model FROM CHANNEL_CONFIG WHERE channel_id = ?;"
        try:
            cursor = self._get_cursor()
            cursor.execute(sql, (channel_id,))
            row = cursor.fetchone()
            return row['model'] if row else None
        except sqlite3.Error as e:
            logger.error(f"Error getting model for channel '{channel_id}': {e}", exc_info=True)
            return None # Return None on error

    def set_channel_system_prompt(self, channel_id: str, prompt: Optional[str]):
        """Sets the specific system prompt override for a channel."""
        self._ensure_channel_exists(channel_id) # Make sure channel record exists
        sql = """
        UPDATE CHANNEL_CONFIG SET system_prompt = ? WHERE channel_id = ?;
        """
        try:
            with self._conn:
                cursor = self._get_cursor()
                cursor.execute(sql, (prompt, channel_id))
            logger.debug(f"Set system prompt for channel {channel_id}")
        except sqlite3.Error as e:
            logger.error(f"Error setting system prompt for channel '{channel_id}': {e}", exc_info=True)
            raise

    def get_channel_system_prompt(self, channel_id: str) -> Optional[str]:
        """Gets the specific system prompt override for a channel."""
        sql = "SELECT system_prompt FROM CHANNEL_CONFIG WHERE channel_id = ?;"
        try:
            cursor = self._get_cursor()
            cursor.execute(sql, (channel_id,))
            row = cursor.fetchone()
            return row['system_prompt'] if row else None
        except sqlite3.Error as e:
            logger.error(f"Error getting system prompt for channel '{channel_id}': {e}", exc_info=True)
            return None # Return None on error

    def get_channel_config(self, channel_id: str) -> Optional[Dict[str, Optional[str]]]:
        """Gets both model and system prompt for a channel."""
        sql = "SELECT model, system_prompt FROM CHANNEL_CONFIG WHERE channel_id = ?;"
        try:
            cursor = self._get_cursor()
            cursor.execute(sql, (channel_id,))
            row = cursor.fetchone()
            if row:
                return {"model": row["model"], "system_prompt": row["system_prompt"]}
            else:
                # If no config row exists (shouldn't happen with _ensure_channel), return None
                return None
        except sqlite3.Error as e:
            logger.error(f"Error getting config for channel '{channel_id}': {e}", exc_info=True)
            return None

    def reset_channel_config(self, channel_id: str) -> bool:
        """Resets a channel's model and system prompt to NULL (effectively using global defaults)."""
        # We update to NULL instead of deleting the row, as the row might be needed
        # by foreign key constraints (e.g., if messages reference it, though CASCADE should handle).
        # Keeping the row simplifies logic.
        sql = "UPDATE CHANNEL_CONFIG SET model = NULL, system_prompt = NULL WHERE channel_id = ?;"
        try:
            with self._conn:
                cursor = self._get_cursor()
                cursor.execute(sql, (channel_id,))
                updated = cursor.rowcount > 0
            if updated:
                logger.debug(f"Reset config for channel: {channel_id}")
            return updated
        except sqlite3.Error as e:
            logger.error(f"Error resetting config for channel '{channel_id}': {e}", exc_info=True)
            raise

    # --- Thread Methods ---

    def add_thread(self, thread_id: str, channel_id: str, name: str, created_at: datetime):
        """Adds a new thread record."""
        # Ensure the parent channel exists first
        self._ensure_channel_exists(channel_id)
        sql = """
        INSERT OR IGNORE INTO THREADS (thread_id, channel_id, name, created_at)
        VALUES (?, ?, ?, ?);
        """
        try:
            with self._conn:
                cursor = self._get_cursor()
                cursor.execute(sql, (thread_id, channel_id, name, created_at))
            logger.debug(f"Added or ignored thread: {thread_id} in channel {channel_id}")
        except sqlite3.Error as e:
            logger.error(f"Error adding thread '{thread_id}': {e}", exc_info=True)
            raise

    def get_thread_info(self, thread_id: str) -> Optional[Dict[str, Any]]:
        """Gets information about a specific thread."""
        sql = "SELECT thread_id, channel_id, name, created_at FROM THREADS WHERE thread_id = ?;"
        try:
            cursor = self._get_cursor()
            cursor.execute(sql, (thread_id,))
            row = cursor.fetchone()
            return dict(row) if row else None
        except sqlite3.Error as e:
            logger.error(f"Error getting info for thread '{thread_id}': {e}", exc_info=True)
            return None

    def prune_old_threads(self, cutoff_timestamp: datetime) -> int:
        """
        Deletes threads older than the cutoff timestamp based on creation time.
        Associated messages will be deleted due to CASCADE constraint.

        Args:
            cutoff_timestamp (datetime): Threads created before this time will be deleted.

        Returns:
            int: The number of threads deleted.
        """
        sql = "DELETE FROM THREADS WHERE created_at < ?;"
        try:
            with self._conn:
                cursor = self._get_cursor()
                cursor.execute(sql, (cutoff_timestamp,))
                deleted_count = cursor.rowcount
            if deleted_count > 0:
                logger.info(f"Pruned {deleted_count} old threads created before {cutoff_timestamp}.")
            return deleted_count
        except sqlite3.Error as e:
            logger.error(f"Error pruning old threads: {e}", exc_info=True)
            raise

    def set_thread_model(self, thread_id: str, model: Optional[str]):
        """Sets the specific model override for a thread."""
        # We assume the thread record exists when setting config
        sql = """
        UPDATE THREADS SET model = ? WHERE thread_id = ?;
        """
        try:
            with self._conn:
                cursor = self._get_cursor()
                cursor.execute(sql, (model, thread_id))
                updated = cursor.rowcount > 0
            if updated:
                logger.debug(f"Set model for thread {thread_id} to {model}")
            # Return True if updated, False if thread_id not found
            return updated
        except sqlite3.Error as e:
            logger.error(f"Error setting model for thread '{thread_id}': {e}", exc_info=True)
            raise

    def set_thread_system_prompt(self, thread_id: str, prompt: Optional[str]):
        """Sets the specific system prompt override for a thread."""
        # We assume the thread record exists when setting config
        sql = """
        UPDATE THREADS SET system_prompt = ? WHERE thread_id = ?;
        """
        try:
            with self._conn:
                cursor = self._get_cursor()
                cursor.execute(sql, (prompt, thread_id))
                updated = cursor.rowcount > 0
            if updated:
                logger.debug(f"Set system prompt for thread {thread_id}")
            # Return True if updated, False if thread_id not found
            return updated
        except sqlite3.Error as e:
            logger.error(f"Error setting system prompt for thread '{thread_id}': {e}", exc_info=True)
            raise

    def get_thread_config(self, thread_id: str) -> Optional[Dict[str, Optional[str]]]:
        """Gets both model and system prompt for a thread."""
        sql = "SELECT model, system_prompt FROM THREADS WHERE thread_id = ?;"
        try:
            cursor = self._get_cursor()
            cursor.execute(sql, (thread_id,))
            row = cursor.fetchone()
            if row:
                return {"model": row["model"], "system_prompt": row["system_prompt"]}
            else:
                return None # Return None if thread not found
        except sqlite3.Error as e:
            logger.error(f"Error getting config for thread '{thread_id}': {e}", exc_info=True)
            return None

    def list_threads_for_channel(self, channel_id: str) -> List[Dict[str, Any]]:
        """Lists all threads associated with a channel."""
        sql = "SELECT thread_id, channel_id, name, created_at, model, system_prompt FROM THREADS WHERE channel_id = ? ORDER BY created_at DESC;"
        try:
            cursor = self._get_cursor()
            cursor.execute(sql, (channel_id,))
            rows = cursor.fetchall()
            return [dict(row) for row in rows]
        except sqlite3.Error as e:
            logger.error(f"Error listing threads for channel '{channel_id}': {e}", exc_info=True)
            return []

    def delete_thread(self, thread_id: str) -> bool:
        """Deletes a thread by its ID. Associated messages are deleted via CASCADE."""
        sql = "DELETE FROM THREADS WHERE thread_id = ?;"
        try:
            with self._conn:
                cursor = self._get_cursor()
                cursor.execute(sql, (thread_id,))
                deleted = cursor.rowcount > 0
            if deleted:
                logger.info(f"Deleted thread: {thread_id} and associated messages.")
            return deleted
        except sqlite3.Error as e:
            logger.error(f"Error deleting thread '{thread_id}': {e}", exc_info=True)
            raise

    def rename_thread(self, thread_id: str, new_name: str) -> bool:
        """Renames a thread."""
        sql = "UPDATE THREADS SET name = ? WHERE thread_id = ?;"
        try:
            with self._conn:
                cursor = self._get_cursor()
                cursor.execute(sql, (new_name, thread_id))
                updated = cursor.rowcount > 0
            if updated:
                logger.debug(f"Renamed thread {thread_id} to '{new_name}'")
            return updated
        except sqlite3.Error as e:
            logger.error(f"Error renaming thread '{thread_id}': {e}", exc_info=True)
            raise

    def get_thread_message_count(self, thread_id: str) -> int:
        """Gets the number of messages in a specific thread."""
        sql = "SELECT COUNT(*) FROM MESSAGES WHERE thread_id = ?;"
        try:
            cursor = self._get_cursor()
            cursor.execute(sql, (thread_id,))
            row = cursor.fetchone()
            return row[0] if row else 0
        except sqlite3.Error as e:
            logger.error(f"Error getting message count for thread '{thread_id}': {e}", exc_info=True)
            return -1 # Indicate error

    # --- Message Methods ---

    def add_message(self, role: str, content: str, timestamp: datetime,
                    channel_id: Optional[str] = None,
                    thread_id: Optional[str] = None,
                    user_id: Optional[str] = None) -> int:
        """
        Adds a message to the database, associated with either a channel or a thread.

        Args:
            role (str): 'user', 'assistant', 'system', or 'tool'.
            content (str): The message content.
            timestamp (datetime): The time the message was created/received.
            channel_id (Optional[str]): The ID of the channel if it's a channel message.
            thread_id (Optional[str]): The ID of the thread if it's a thread message.
            user_id (Optional[str]): The ID of the user who sent the message.

        Returns:
            int: The primary key (message_pk) of the inserted message.

        Raises:
            ValueError: If neither channel_id nor thread_id is provided.
        """
        if not channel_id and not thread_id:
            raise ValueError("Either channel_id or thread_id must be provided for a message.")
        if channel_id and thread_id:
             logger.warning(f"Message provided with both channel_id ({channel_id}) and thread_id ({thread_id}). Associating with thread.")
             channel_id = None # Prioritize thread_id if both given

        # Ensure parent channel/thread exists if provided
        if channel_id:
            self._ensure_channel_exists(channel_id)
        # We assume add_thread was called before adding messages to it.

        sql = """
        INSERT INTO MESSAGES (channel_id, thread_id, user_id, role, content, timestamp)
        VALUES (?, ?, ?, ?, ?, ?);
        """
        try:
            with self._conn:
                cursor = self._get_cursor()
                cursor.execute(sql, (channel_id, thread_id, user_id, role, content, timestamp))
                last_id = cursor.lastrowid
            logger.debug(f"Added message (PK: {last_id}) for {'channel ' + channel_id if channel_id else 'thread ' + thread_id}")
            return last_id
        except sqlite3.Error as e:
            logger.error(f"Error adding message for {'channel ' + str(channel_id) if channel_id else 'thread ' + str(thread_id)}: {e}", exc_info=True)
            raise

    def _get_history(self, entity_id: str, id_column: str, limit: Optional[int] = None, hours_limit: Optional[int] = None) -> List[Dict[str, Any]]:
        """Internal helper to get message history for a channel or thread."""
        base_sql = f"SELECT role, content, timestamp, user_id FROM MESSAGES WHERE {id_column} = ?"
        params: List[Any] = [entity_id]

        if hours_limit is not None:
            cutoff_time = datetime.now() - timedelta(hours=hours_limit)
            base_sql += " AND timestamp >= ?"
            params.append(cutoff_time)

        base_sql += " ORDER BY timestamp DESC" # Get latest first

        if limit is not None:
            base_sql += " LIMIT ?"
            params.append(limit)

        try:
            cursor = self._get_cursor()
            cursor.execute(base_sql, tuple(params))
            # Fetch all and reverse to get chronological order (oldest first)
            # Fetch all and reverse to get chronological order (oldest first)
            rows = cursor.fetchall()

            # --- Debugging: Inspect raw timestamp data ---
            debug_rows = []
            for row in rows:
                debug_row = dict(row) # Convert Row to dict for easier inspection
                timestamp_value = debug_row.get("timestamp")
                timestamp_type = type(timestamp_value).__name__
                logger.debug(f"Raw timestamp value: {timestamp_value}, Type: {timestamp_type}")
                debug_rows.append(debug_row)
            rows = debug_rows # Use the debugged rows

            # Rely on sqlite3's registered converter for DATETIME (if detect_types is enabled)
            # Since detect_types is temporarily disabled, timestamps will be strings or None
            # We will return the raw data for inspection.
            return [dict(row) for row in reversed(rows)]
        except sqlite3.Error as e:
            logger.error(f"Error getting history for {id_column} '{entity_id}': {e}", exc_info=True)
            return [] # Return empty list on error

    def get_channel_history(self, channel_id: str, limit: Optional[int] = None, hours_limit: Optional[int] = None) -> List[Dict[str, Any]]:
        """Gets message history for a specific channel."""
        return self._get_history(channel_id, "channel_id", limit, hours_limit)

    def get_thread_history(self, thread_id: str, limit: Optional[int] = None, hours_limit: Optional[int] = None) -> List[Dict[str, Any]]:
        """Gets message history for a specific thread."""
        return self._get_history(thread_id, "thread_id", limit, hours_limit)

    def prune_old_messages(self, cutoff_timestamp: datetime) -> int:
        """
        Deletes messages older than the specified cutoff timestamp.

        Args:
            cutoff_timestamp (datetime): Messages older than this will be deleted.

        Returns:
            int: The number of messages deleted.
        """
        sql = "DELETE FROM MESSAGES WHERE timestamp < ?;"
        try:
            with self._conn:
                cursor = self._get_cursor()
                cursor.execute(sql, (cutoff_timestamp,))
                deleted_count = cursor.rowcount
            if deleted_count > 0:
                logger.info(f"Pruned {deleted_count} old messages before {cutoff_timestamp}.")
            return deleted_count
        except sqlite3.Error as e:
            logger.error(f"Error pruning old messages: {e}", exc_info=True)
            raise

    # --- News Feed Methods ---

    def add_news_feed(self, feed_id: str, url: str, name: Optional[str] = None, category: Optional[str] = None):
        """Adds or updates a news feed, including its URL and category."""
        # Use ON CONFLICT to update existing feeds based on feed_id (primary key)
        sql = """
        INSERT INTO NEWS_FEEDS (feed_id, url, name, category, last_checked)
        VALUES (?, ?, ?, ?, NULL)
        ON CONFLICT(feed_id) DO UPDATE SET
            url = excluded.url,
            name = excluded.name,
            category = excluded.category;
        """
        try:
            with self._conn:
                cursor = self._get_cursor()
                cursor.execute(sql, (feed_id, url, name, category))
            logger.debug(f"Added or updated news feed: {feed_id} (Name: {name}, Category: {category})")
        except sqlite3.Error as e:
            logger.error(f"Error adding/updating news feed '{feed_id}': {e}", exc_info=True)
            raise

    def get_news_feeds(self) -> List[Dict[str, Any]]:
        """Gets all configured news feeds, including URL and category."""
        sql = "SELECT feed_id, url, name, category, last_checked FROM NEWS_FEEDS ORDER BY name;"
        try:
            cursor = self._get_cursor()
            cursor.execute(sql)
            rows = cursor.fetchall()
            feeds = []
            for row in rows:
                feed_dict = dict(row)
                last_checked_raw = feed_dict.get('last_checked')
                if isinstance(last_checked_raw, str):
                    try:
                        # Attempt to parse ISO format string (common SQLite storage)
                        feed_dict['last_checked'] = datetime.fromisoformat(last_checked_raw)
                    except ValueError:
                        try:
                            # Fallback for other potential formats if needed, e.g., with microseconds
                            feed_dict['last_checked'] = datetime.strptime(last_checked_raw, '%Y-%m-%d %H:%M:%S.%f')
                        except ValueError:
                             logger.warning(f"Could not parse last_checked timestamp string '{last_checked_raw}' for feed {feed_dict.get('feed_id')}. Setting to None.")
                             feed_dict['last_checked'] = None # Set to None if parsing fails
                elif not isinstance(last_checked_raw, datetime) and last_checked_raw is not None:
                     logger.warning(f"Unexpected type for last_checked ({type(last_checked_raw)}) for feed {feed_dict.get('feed_id')}. Setting to None.")
                     feed_dict['last_checked'] = None # Ensure it's None if not datetime or string

                feeds.append(feed_dict)
            return feeds
        except sqlite3.Error as e:
            logger.error(f"Error getting news feeds: {e}", exc_info=True)
            return []

    def update_feed_last_checked(self, feed_id: str, timestamp: datetime):
        """Updates the last checked timestamp for a feed."""
        sql = "UPDATE NEWS_FEEDS SET last_checked = ? WHERE feed_id = ?;"
        try:
            with self._conn:
                cursor = self._get_cursor()
                cursor.execute(sql, (timestamp, feed_id))
            logger.debug(f"Updated last checked time for feed: {feed_id}")
        except sqlite3.Error as e:
            logger.error(f"Error updating last checked time for feed '{feed_id}': {e}", exc_info=True)
            raise

    def delete_news_feed(self, feed_id: str) -> bool:
        """Deletes a news feed and its associated subscriptions and history (via CASCADE)."""
        sql = "DELETE FROM NEWS_FEEDS WHERE feed_id = ?;"
        try:
            with self._conn:
                cursor = self._get_cursor()
                cursor.execute(sql, (feed_id,))
                deleted = cursor.rowcount > 0
            if deleted:
                logger.info(f"Deleted news feed: {feed_id} and associated data.")
            return deleted
        except sqlite3.Error as e:
            logger.error(f"Error deleting news feed '{feed_id}': {e}", exc_info=True)
            raise

    def add_news_subscription(self, channel_id: str, feed_id: str):
        """Subscribes a channel to a news feed."""
        # Ensure channel and feed exist
        self._ensure_channel_exists(channel_id)
        # Feed should already exist before subscribing. Removed call: self.add_news_feed(feed_id)
        sql = "INSERT OR IGNORE INTO NEWS_CHANNEL_SUBSCRIPTIONS (channel_id, feed_id) VALUES (?, ?);"
        try:
            with self._conn:
                cursor = self._get_cursor()
                cursor.execute(sql, (channel_id, feed_id))
            logger.debug(f"Subscribed channel {channel_id} to feed {feed_id}")
        except sqlite3.Error as e:
            logger.error(f"Error subscribing channel '{channel_id}' to feed '{feed_id}': {e}", exc_info=True)
            raise

    def remove_news_subscription(self, channel_id: str, feed_id: str) -> bool:
        """Unsubscribes a channel from a news feed."""
        sql = "DELETE FROM NEWS_CHANNEL_SUBSCRIPTIONS WHERE channel_id = ? AND feed_id = ?;"
        try:
            with self._conn:
                cursor = self._get_cursor()
                cursor.execute(sql, (channel_id, feed_id))
                deleted = cursor.rowcount > 0
            if deleted:
                logger.debug(f"Unsubscribed channel {channel_id} from feed {feed_id}")
            return deleted
        except sqlite3.Error as e:
            logger.error(f"Error unsubscribing channel '{channel_id}' from feed '{feed_id}': {e}", exc_info=True)
            raise

    def get_subscribed_channels(self, feed_id: str) -> List[str]:
        """Gets a list of channel IDs subscribed to a specific feed."""
        sql = "SELECT channel_id FROM NEWS_CHANNEL_SUBSCRIPTIONS WHERE feed_id = ?;"
        try:
            cursor = self._get_cursor()
            cursor.execute(sql, (feed_id,))
            rows = cursor.fetchall()
            return [row['channel_id'] for row in rows]
        except sqlite3.Error as e:
            logger.error(f"Error getting subscribers for feed '{feed_id}': {e}", exc_info=True)
            return []

    def get_channel_subscriptions(self, channel_id: str) -> List[str]:
        """Gets a list of feed IDs a specific channel is subscribed to."""
        sql = "SELECT feed_id FROM NEWS_CHANNEL_SUBSCRIPTIONS WHERE channel_id = ?;"
        try:
            cursor = self._get_cursor()
            cursor.execute(sql, (channel_id,))
            rows = cursor.fetchall()
            return [row['feed_id'] for row in rows]
        except sqlite3.Error as e:
            logger.error(f"Error getting subscriptions for channel '{channel_id}': {e}", exc_info=True)
            return []

    def add_article_history(self, article_identifier: str, feed_id: str, processed_at: datetime):
        """Adds a record indicating an article has been processed for a feed."""
        sql = "INSERT OR IGNORE INTO NEWS_ARTICLES_HISTORY (article_identifier, feed_id, processed_at) VALUES (?, ?, ?);"
        try:
            with self._conn:
                cursor = self._get_cursor()
                cursor.execute(sql, (article_identifier, feed_id, processed_at))
            # No need to log every article, can be very verbose
        except sqlite3.Error as e:
            # Log only errors
            logger.error(f"Error adding article history for feed '{feed_id}', article '{article_identifier}': {e}", exc_info=True)
            raise

    def check_article_history(self, article_identifier: str, feed_id: str) -> bool:
        """Checks if an article has already been processed for a feed."""
        sql = "SELECT 1 FROM NEWS_ARTICLES_HISTORY WHERE article_identifier = ? AND feed_id = ? LIMIT 1;"
        try:
            cursor = self._get_cursor()
            cursor.execute(sql, (article_identifier, feed_id))
            return cursor.fetchone() is not None
        except sqlite3.Error as e:
            logger.error(f"Error checking article history for feed '{feed_id}', article '{article_identifier}': {e}", exc_info=True)
            # Fail safe: assume not processed if error occurs? Or re-raise?
            # Let's re-raise for now, as failing safe might lead to duplicate posts.
            raise

    def prune_old_articles(self, cutoff_timestamp: datetime) -> int:
        """
        Deletes article history records older than the specified cutoff timestamp.

        Args:
            cutoff_timestamp (datetime): Records older than this will be deleted.

        Returns:
            int: The number of article history records deleted.
        """
        sql = "DELETE FROM NEWS_ARTICLES_HISTORY WHERE processed_at < ?;"
        try:
            with self._conn:
                cursor = self._get_cursor()
                cursor.execute(sql, (cutoff_timestamp,))
                deleted_count = cursor.rowcount
            if deleted_count > 0:
                logger.info(f"Pruned {deleted_count} old article history records before {cutoff_timestamp}.")
            return deleted_count
        except sqlite3.Error as e:
            logger.error(f"Error pruning old article history: {e}", exc_info=True)
            raise

    def get_news_article_history_count(self) -> int:
        """Gets the total number of news article history records stored."""
        sql = "SELECT COUNT(*) FROM NEWS_ARTICLES_HISTORY;"
        try:
            cursor = self._get_cursor()
            cursor.execute(sql)
            row = cursor.fetchone()
            return row[0] if row else 0
        except sqlite3.Error as e:
            logger.error(f"Error getting news article history count: {e}", exc_info=True)
            return -1 # Indicate error

    # --- Last Digest Content Methods (Using Global Config) ---

    def set_last_digest_content(self, content: Optional[str]):
        """Stores the last generated news digest content."""
        # Store as a string in GLOBAL_CONFIG
        self.set_global_config("last_news_digest_content", content, 'string')
        logger.debug("Stored last news digest content.")

    def get_last_digest_content(self) -> Optional[str]:
        """Retrieves the last generated news digest content."""
        # Retrieve as a string from GLOBAL_CONFIG
        return self.get_global_config("last_news_digest_content")

    # --- User Methods (Basic Structure) ---

    def _ensure_user_exists(self, user_id: str):
         """Ensures a user record exists."""
         sql = "INSERT OR IGNORE INTO USERS (user_id, preferences_json) VALUES (?, NULL);"
         try:
             with self._conn:
                 cursor = self._get_cursor()
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
                cursor = self._get_cursor()
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
            cursor = self._get_cursor()
            cursor.execute(sql, (user_id,))
            row = cursor.fetchone()
            if row and row['preferences_json']:
                return json.loads(row['preferences_json'])
            else:
                return None # Return None if no user or no preferences set
        except sqlite3.Error as e:
            logger.error(f"Error getting preferences for user '{user_id}': {e}", exc_info=True)
            return None
        except json.JSONDecodeError as e:
            logger.error(f"Error decoding preferences JSON for user '{user_id}': {e}", exc_info=True)
            return None


# Example usage (optional, for testing)
if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
    logger.info("Running database manager test...")
    try:
        db_manager = DatabaseManager(db_name="test_gideon_state.db")

        # Test config
        db_manager.set_global_config("test_string", "hello world", "string")
        db_manager.set_global_config("test_int", 123, "int")
        db_manager.set_global_config("test_float", 45.67, "float")
        db_manager.set_global_config("test_bool_true", True, "bool")
        db_manager.set_global_config("test_bool_false", False, "bool")
        db_manager.set_global_config("test_json", {"a": 1, "b": [2, 3]}, "json")

        print(f"String: {db_manager.get_global_config('test_string')}")
        print(f"Int: {db_manager.get_global_config('test_int')}")
        print(f"Float: {db_manager.get_global_config('test_float')}")
        print(f"Bool True: {db_manager.get_global_config('test_bool_true')}")
        print(f"Bool False: {db_manager.get_global_config('test_bool_false')}")
        print(f"JSON: {db_manager.get_global_config('test_json')}")
        print(f"Non-existent: {db_manager.get_global_config('non_existent', 'default_val')}")

        # Test update
        db_manager.set_global_config("test_string", "updated hello", "string")
        print(f"Updated String: {db_manager.get_global_config('test_string')}")

        # Test delete
        print(f"Deleting test_int: {db_manager.delete_global_config('test_int')}")
        print(f"Getting deleted test_int: {db_manager.get_global_config('test_int', 'was deleted')}")
        print(f"Deleting non-existent: {db_manager.delete_global_config('non_existent')}")

        db_manager.close()
        # Clean up test db
        test_db_path = os.path.join(DATA_DIRECTORY, "test_gideon_state.db")
        if os.path.exists(test_db_path):
            os.remove(test_db_path)
            logger.info(f"Removed test database: {test_db_path}")

    except Exception as e:
        logger.error(f"Database manager test failed: {e}", exc_info=True)

    logger.info("Database manager test finished.")