import sqlite3
import logging
from datetime import datetime
from typing import Optional, List, Dict, Any

logger = logging.getLogger(__name__)

class TriviaManager:
    """Manages trivia game storage and retrieval."""

    def __init__(self, conn):
        self._conn = conn

    # ===== Game Session Management =====

    def create_session(self, thread_id: str, channel_id: str, user_id: Optional[str],
                      game_mode: str, category: Optional[str], difficulty: str,
                      questions_total: int = 10) -> int:
        """
        Creates a new trivia game session.

        Args:
            thread_id: Discord thread ID where game takes place
            channel_id: Parent channel ID
            user_id: User ID for solo mode, None for competitive
            game_mode: 'solo' or 'competitive'
            category: Free-form category text
            difficulty: 'easy', 'medium', or 'hard'
            questions_total: Total questions in the game (default 10)

        Returns:
            int: The session_id of the created session

        Raises:
            sqlite3.Error: If database operation fails
        """
        sql = """
        INSERT INTO TRIVIA_GAME_SESSIONS
        (thread_id, channel_id, user_id, game_mode, category, difficulty,
         questions_total, questions_answered, started_at, is_active)
        VALUES (?, ?, ?, ?, ?, ?, ?, 0, ?, 1);
        """
        try:
            with self._conn:
                cursor = self._conn.cursor()
                cursor.execute(sql, (thread_id, channel_id, user_id, game_mode,
                                   category, difficulty, questions_total, datetime.now()))
                last_id = cursor.lastrowid
            logger.debug(f"Created trivia session (ID: {last_id}) in thread {thread_id}")
            return last_id
        except sqlite3.Error as e:
            logger.error(f"Error creating trivia session: {e}", exc_info=True)
            raise

    def get_active_session_by_thread(self, thread_id: str) -> Optional[Dict[str, Any]]:
        """
        Gets the active trivia session for a thread.

        Args:
            thread_id: Discord thread ID

        Returns:
            Dict with session data or None if no active session
        """
        sql = """
        SELECT session_id, thread_id, channel_id, user_id, game_mode, category,
               difficulty, questions_total, questions_answered, started_at, is_active
        FROM TRIVIA_GAME_SESSIONS
        WHERE thread_id = ? AND is_active = 1;
        """
        try:
            cursor = self._conn.cursor()
            cursor.execute(sql, (thread_id,))
            row = cursor.fetchone()
            return dict(row) if row else None
        except sqlite3.Error as e:
            logger.error(f"Error getting active session for thread {thread_id}: {e}", exc_info=True)
            return None

    def update_questions_answered(self, thread_id: str) -> bool:
        """
        Increments the questions_answered counter for a session.

        Args:
            thread_id: Discord thread ID

        Returns:
            bool: True if updated successfully
        """
        sql = """
        UPDATE TRIVIA_GAME_SESSIONS
        SET questions_answered = questions_answered + 1
        WHERE thread_id = ? AND is_active = 1;
        """
        try:
            with self._conn:
                cursor = self._conn.cursor()
                cursor.execute(sql, (thread_id,))
                updated = cursor.rowcount > 0
            return updated
        except sqlite3.Error as e:
            logger.error(f"Error updating questions_answered for thread {thread_id}: {e}", exc_info=True)
            return False

    def end_session(self, thread_id: str) -> bool:
        """
        Ends a trivia session by setting is_active = 0 and ended_at timestamp.

        Args:
            thread_id: Discord thread ID

        Returns:
            bool: True if session was ended
        """
        sql = """
        UPDATE TRIVIA_GAME_SESSIONS
        SET is_active = 0, ended_at = ?
        WHERE thread_id = ? AND is_active = 1;
        """
        try:
            with self._conn:
                cursor = self._conn.cursor()
                cursor.execute(sql, (datetime.now(), thread_id))
                updated = cursor.rowcount > 0
            if updated:
                logger.debug(f"Ended trivia session for thread {thread_id}")
            return updated
        except sqlite3.Error as e:
            logger.error(f"Error ending session for thread {thread_id}: {e}", exc_info=True)
            return False

    # ===== Leaderboard Management =====

    def update_leaderboard(self, user_id: str, server_id: str,
                          questions_answered: int, correct_answers: int,
                          points_earned: int, current_streak: int,
                          response_time: float) -> bool:
        """
        Updates leaderboard stats for a user after a game.

        Args:
            user_id: Discord user ID
            server_id: Discord server/guild ID
            questions_answered: Number of questions answered in the game
            correct_answers: Number of correct answers
            points_earned: Points earned in the game
            current_streak: Current streak at end of game
            response_time: Average response time

        Returns:
            bool: True if updated successfully
        """
        sql = """
        INSERT INTO TRIVIA_LEADERBOARD
        (user_id, server_id, total_games, total_questions, total_correct,
         total_points, current_streak, best_streak, average_response_time, last_played)
        VALUES (?, ?, 1, ?, ?, ?, ?, ?, ?, ?)
        ON CONFLICT(user_id, server_id) DO UPDATE SET
            total_games = total_games + 1,
            total_questions = total_questions + ?,
            total_correct = total_correct + ?,
            total_points = total_points + ?,
            current_streak = ?,
            best_streak = MAX(best_streak, ?),
            average_response_time = ((average_response_time * total_questions) + (? * ?)) / (total_questions + ?),
            last_played = ?;
        """
        try:
            with self._conn:
                cursor = self._conn.cursor()
                cursor.execute(sql, (
                    user_id, server_id, questions_answered, correct_answers,
                    points_earned, current_streak, current_streak, response_time, datetime.now(),
                    questions_answered, correct_answers, points_earned, current_streak,
                    current_streak, response_time, questions_answered, questions_answered, datetime.now()
                ))
            logger.debug(f"Updated leaderboard for user {user_id} in server {server_id}")
            return True
        except sqlite3.Error as e:
            logger.error(f"Error updating leaderboard: {e}", exc_info=True)
            return False

    def get_leaderboard(self, server_id: str, timeframe: str = 'all_time',
                       limit: int = 10) -> List[Dict[str, Any]]:
        """
        Gets the leaderboard rankings for a server.

        Args:
            server_id: Discord server/guild ID
            timeframe: 'daily', 'weekly', 'monthly', or 'all_time'
            limit: Maximum number of entries to return

        Returns:
            List of user stats dictionaries
        """
        # For now, implement all_time. Time-based filtering would require tracking
        # individual game timestamps in a separate table.
        sql = """
        SELECT user_id, total_games, total_questions, total_correct,
               total_points, best_streak, average_response_time, last_played
        FROM TRIVIA_LEADERBOARD
        WHERE server_id = ?
        ORDER BY total_points DESC, average_response_time ASC
        LIMIT ?;
        """
        try:
            cursor = self._conn.cursor()
            cursor.execute(sql, (server_id, limit))
            rows = cursor.fetchall()
            return [dict(row) for row in rows]
        except sqlite3.Error as e:
            logger.error(f"Error getting leaderboard for server {server_id}: {e}", exc_info=True)
            return []

    def get_user_stats(self, user_id: str, server_id: str) -> Optional[Dict[str, Any]]:
        """
        Gets trivia stats for a specific user in a server.

        Args:
            user_id: Discord user ID
            server_id: Discord server/guild ID

        Returns:
            Dict with user stats or None if no stats found
        """
        sql = """
        SELECT user_id, server_id, total_games, total_questions, total_correct,
               total_points, current_streak, best_streak, average_response_time, last_played
        FROM TRIVIA_LEADERBOARD
        WHERE user_id = ? AND server_id = ?;
        """
        try:
            cursor = self._conn.cursor()
            cursor.execute(sql, (user_id, server_id))
            row = cursor.fetchone()
            return dict(row) if row else None
        except sqlite3.Error as e:
            logger.error(f"Error getting stats for user {user_id}: {e}", exc_info=True)
            return None

    # ===== Achievement Management =====

    def add_achievement(self, user_id: str, server_id: str,
                       achievement_type: str, achievement_name: str,
                       metadata_json: Optional[str] = None) -> int:
        """
        Adds an achievement for a user.

        Args:
            user_id: Discord user ID
            server_id: Discord server/guild ID
            achievement_type: Type identifier (e.g., 'first_win', 'streak_10')
            achievement_name: Display name (e.g., '🎯 First Blood')
            metadata_json: Optional JSON string with additional data

        Returns:
            int: The achievement_id of the inserted achievement

        Raises:
            sqlite3.Error: If database operation fails
        """
        sql = """
        INSERT INTO TRIVIA_ACHIEVEMENTS
        (user_id, server_id, achievement_type, achievement_name, earned_at, metadata_json)
        VALUES (?, ?, ?, ?, ?, ?);
        """
        try:
            with self._conn:
                cursor = self._conn.cursor()
                cursor.execute(sql, (user_id, server_id, achievement_type,
                                   achievement_name, datetime.now(), metadata_json))
                last_id = cursor.lastrowid
            logger.debug(f"Added achievement '{achievement_name}' for user {user_id}")
            return last_id
        except sqlite3.Error as e:
            logger.error(f"Error adding achievement: {e}", exc_info=True)
            raise

    def get_user_achievements(self, user_id: str, server_id: str) -> List[Dict[str, Any]]:
        """
        Gets all achievements for a user in a server.

        Args:
            user_id: Discord user ID
            server_id: Discord server/guild ID

        Returns:
            List of achievement dictionaries
        """
        sql = """
        SELECT achievement_id, achievement_type, achievement_name, earned_at, metadata_json
        FROM TRIVIA_ACHIEVEMENTS
        WHERE user_id = ? AND server_id = ?
        ORDER BY earned_at DESC;
        """
        try:
            cursor = self._conn.cursor()
            cursor.execute(sql, (user_id, server_id))
            rows = cursor.fetchall()
            return [dict(row) for row in rows]
        except sqlite3.Error as e:
            logger.error(f"Error getting achievements for user {user_id}: {e}", exc_info=True)
            return []

    def has_achievement(self, user_id: str, server_id: str,
                       achievement_type: str) -> bool:
        """
        Checks if a user has already earned a specific achievement.

        Args:
            user_id: Discord user ID
            server_id: Discord server/guild ID
            achievement_type: Type identifier to check

        Returns:
            bool: True if user has this achievement
        """
        sql = """
        SELECT COUNT(*) as count
        FROM TRIVIA_ACHIEVEMENTS
        WHERE user_id = ? AND server_id = ? AND achievement_type = ?;
        """
        try:
            cursor = self._conn.cursor()
            cursor.execute(sql, (user_id, server_id, achievement_type))
            row = cursor.fetchone()
            return row['count'] > 0 if row else False
        except sqlite3.Error as e:
            logger.error(f"Error checking achievement for user {user_id}: {e}", exc_info=True)
            return False

    # ===== Cleanup & Maintenance =====

    def prune_old_sessions(self, days_old: int = 30) -> int:
        """
        Deletes inactive sessions older than specified days.

        Args:
            days_old: Number of days to keep (default 30)

        Returns:
            int: Number of sessions deleted
        """
        sql = """
        DELETE FROM TRIVIA_GAME_SESSIONS
        WHERE is_active = 0 AND ended_at < datetime('now', ? || ' days');
        """
        try:
            with self._conn:
                cursor = self._conn.cursor()
                cursor.execute(sql, (f'-{days_old}',))
                deleted = cursor.rowcount
            if deleted > 0:
                logger.info(f"Pruned {deleted} old trivia sessions")
            return deleted
        except sqlite3.Error as e:
            logger.error(f"Error pruning old sessions: {e}", exc_info=True)
            return 0
