import sqlite3
import logging

logger = logging.getLogger(__name__)

class SchemaManager:
    """Handles database schema initialization and migrations."""

    # Core table definitions (excluding news feed tables)
    CORE_TABLES = [
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
        """
        CREATE TABLE IF NOT EXISTS CHANNEL_CONFIG (
            channel_id TEXT PRIMARY KEY,
            model TEXT,
            provider TEXT,
            system_prompt TEXT,
            FOREIGN KEY (channel_id) REFERENCES CHANNELS(channel_id) ON DELETE CASCADE
        );
        """,
        """
        CREATE TABLE IF NOT EXISTS THREADS (
            thread_id TEXT PRIMARY KEY,
            channel_id TEXT,
            name TEXT,
            created_at DATETIME NOT NULL,
            model TEXT,
            system_prompt TEXT,
            FOREIGN KEY (channel_id) REFERENCES CHANNELS(channel_id) ON DELETE SET NULL
        );
        """,
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
        """
        CREATE TABLE IF NOT EXISTS USERS (
            user_id TEXT PRIMARY KEY,
            preferences_json TEXT
        );
        """
    ]

    # Index definitions
    INDEXES = [
        """CREATE INDEX IF NOT EXISTS idx_messages_channel_timestamp ON MESSAGES (channel_id, timestamp);""",
        """CREATE INDEX IF NOT EXISTS idx_messages_thread_timestamp ON MESSAGES (thread_id, timestamp);""",
        """CREATE INDEX IF NOT EXISTS idx_messages_timestamp ON MESSAGES (timestamp);"""
    ]

    @staticmethod
    def initialize(conn):
        """Creates all tables and indexes, runs migrations."""
        try:
            with conn:
                cursor = conn.cursor()

                # Create core tables
                for statement in SchemaManager.CORE_TABLES:
                    cursor.execute(statement)

                # Create indexes
                for statement in SchemaManager.INDEXES:
                    cursor.execute(statement)

                logger.info("Database schema creation/verification complete.")

                # Run migrations
                SchemaManager._migrate_remove_news_feeds(cursor)
                SchemaManager._add_column_if_not_exists(cursor, "CHANNEL_CONFIG", "provider", "TEXT")

                logger.info("Database schema migration checks complete.")
        except sqlite3.Error as e:
            logger.error(f"Error initializing/migrating database schema: {e}", exc_info=True)
            raise

    @staticmethod
    def _migrate_remove_news_feeds(cursor):
        """Migration: Remove all news feed related tables."""
        tables_to_drop = [
            'NEWS_FEEDS',
            'NEWS_CHANNEL_SUBSCRIPTIONS',
            'NEWS_ARTICLES_HISTORY',
            'article_summaries',
            'user_article_summaries'
        ]

        for table in tables_to_drop:
            try:
                cursor.execute(f"DROP TABLE IF EXISTS {table}")
                logger.info(f"Migration: Dropped news feed table '{table}'")
            except sqlite3.Error as e:
                logger.warning(f"Could not drop table '{table}': {e}")

    @staticmethod
    def _add_column_if_not_exists(cursor: sqlite3.Cursor, table_name: str, column_name: str, column_type: str):
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
            # Specifically ignore "duplicate column name" error if ALTER TABLE fails concurrently
            if "duplicate column name" in str(e).lower():
                logger.warning(f"Attempted to add duplicate column '{column_name}' to '{table_name}', ignoring. Error: {e}")
            else:
                logger.error(f"Error adding column '{column_name}' to table '{table_name}': {e}", exc_info=True)
                raise
