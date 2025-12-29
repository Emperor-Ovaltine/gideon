"""In-memory game state management for trivia sessions."""

import time
import logging
from typing import Dict, List, Optional, Tuple, Any
from datetime import datetime

from .trivia_config import calculate_points, check_achievements

logger = logging.getLogger(__name__)


class PlayerState:
    """Tracks individual player state within a game."""

    def __init__(self, user_id: str, username: str):
        self.user_id = user_id
        self.username = username
        self.score = 0
        self.correct_answers = 0
        self.total_answers = 0
        self.current_streak = 0
        self.best_streak = 0
        self.response_times: List[float] = []
        self.last_answer_time: Optional[float] = None

    def record_answer(self, is_correct: bool, response_time: float, points_earned: int):
        """Record an answer attempt and update stats."""
        self.total_answers += 1
        self.response_times.append(response_time)

        if is_correct:
            self.correct_answers += 1
            self.current_streak += 1
            self.best_streak = max(self.best_streak, self.current_streak)
            self.score += points_earned
        else:
            self.current_streak = 0

    def get_average_response_time(self) -> float:
        """Calculate average response time."""
        if not self.response_times:
            return 0.0
        return sum(self.response_times) / len(self.response_times)

    def get_accuracy(self) -> float:
        """Calculate accuracy percentage."""
        if self.total_answers == 0:
            return 0.0
        return (self.correct_answers / self.total_answers) * 100


class GameSession:
    """Manages the state of an active trivia game."""

    def __init__(
        self,
        session_id: int,
        thread_id: str,
        channel_id: str,
        game_mode: str,
        category: Optional[str],
        difficulty: str,
        questions_total: int,
        host_user_id: Optional[str] = None
    ):
        """
        Initialize a new game session.

        Args:
            session_id: Database session ID
            thread_id: Discord thread ID where game takes place
            channel_id: Parent channel ID
            game_mode: 'solo' or 'competitive'
            category: Free-form category text
            difficulty: 'easy', 'medium', or 'hard'
            questions_total: Total questions in the game
            host_user_id: User ID for solo mode (None for competitive)
        """
        self.session_id = session_id
        self.thread_id = thread_id
        self.channel_id = channel_id
        self.game_mode = game_mode
        self.category = category
        self.difficulty = difficulty
        self.questions_total = questions_total
        self.host_user_id = host_user_id

        # Game state
        self.questions_answered = 0
        self.current_question: Optional[Dict[str, Any]] = None
        self.current_correct_answer: Optional[str] = None
        self.current_options: Optional[List[str]] = None
        self.question_start_time: Optional[float] = None
        self.is_waiting_for_answer = False
        self.is_active = True

        # Track asked questions to avoid duplicates
        self.asked_questions: List[str] = []

        # Player tracking
        self.players: Dict[str, PlayerState] = {}  # user_id -> PlayerState
        self.answered_current_question: set = set()  # Track who answered current question

        # Competitive mode tracking
        self.round_winner: Optional[str] = None  # user_id of round winner

        logger.debug(f"Created GameSession {session_id} in thread {thread_id} ({game_mode} mode)")

    def add_player(self, user_id: str, username: str):
        """Add a player to the game (competitive mode only)."""
        if user_id not in self.players:
            self.players[user_id] = PlayerState(user_id, username)
            logger.debug(f"Added player {username} ({user_id}) to game {self.session_id}")

    def get_or_create_player(self, user_id: str, username: str) -> PlayerState:
        """Get existing player or create new one."""
        if user_id not in self.players:
            self.add_player(user_id, username)
        return self.players[user_id]

    def post_question(self, question_data: Dict[str, Any]):
        """
        Post a new question to the game.

        Args:
            question_data: Dict with keys: question, correct_answer, options, explanation
        """
        self.current_question = question_data['question']
        self.current_correct_answer = question_data['correct_answer']
        self.current_options = question_data['options']
        self.question_start_time = time.time()
        self.is_waiting_for_answer = True
        self.answered_current_question.clear()
        self.round_winner = None

        # Track question to avoid duplicates
        self.asked_questions.append(question_data['question'])

        logger.debug(f"Posted question {self.questions_answered + 1}/{self.questions_total} to game {self.session_id}")

    def process_answer(
        self,
        user_id: str,
        username: str,
        is_correct: bool
    ) -> Tuple[bool, Optional[int], Optional[str]]:
        """
        Process a user's answer to the current question.

        Args:
            user_id: Discord user ID
            username: Discord username
            is_correct: Whether the answer is correct

        Returns:
            Tuple of:
            - bool: Whether this answer should be counted (not duplicate)
            - Optional[int]: Points earned (None if incorrect or duplicate)
            - Optional[str]: Winner status ('first_correct', 'also_correct', 'incorrect', 'duplicate')
        """
        if not self.is_waiting_for_answer:
            return (False, None, 'not_waiting')

        # Check if user already answered this question
        if user_id in self.answered_current_question:
            return (False, None, 'duplicate')

        # Mark as answered
        self.answered_current_question.add(user_id)

        # Calculate response time
        response_time = time.time() - self.question_start_time

        # Get or create player
        player = self.get_or_create_player(user_id, username)

        if not is_correct:
            # Wrong answer - no points
            player.record_answer(False, response_time, 0)
            return (True, 0, 'incorrect')

        # Correct answer - calculate points
        points = calculate_points(self.difficulty, response_time, player.current_streak)

        # Record the answer
        player.record_answer(True, response_time, points)

        # Determine winner status
        if self.game_mode == 'competitive':
            if self.round_winner is None:
                # First correct answer in competitive mode
                self.round_winner = user_id
                return (True, points, 'first_correct')
            else:
                # Subsequent correct answer in competitive mode
                return (True, points, 'also_correct')
        else:
            # Solo mode - always first correct
            return (True, points, 'first_correct')

    def complete_question(self):
        """Mark current question as complete and increment counter."""
        self.questions_answered += 1
        self.is_waiting_for_answer = False
        logger.debug(f"Completed question {self.questions_answered}/{self.questions_total} in game {self.session_id}")

    def is_game_complete(self) -> bool:
        """Check if all questions have been answered."""
        return self.questions_answered >= self.questions_total

    def get_current_standings(self) -> List[Dict[str, Any]]:
        """
        Get current game standings sorted by score.

        Returns:
            List of player stats dictionaries sorted by score (descending)
        """
        standings = []
        for player in self.players.values():
            standings.append({
                'user_id': player.user_id,
                'username': player.username,
                'score': player.score,
                'correct': player.correct_answers,
                'total': player.total_answers,
                'accuracy': player.get_accuracy(),
                'streak': player.current_streak,
                'best_streak': player.best_streak,
                'avg_time': player.get_average_response_time()
            })

        # Sort by score descending, then by average time ascending
        standings.sort(key=lambda x: (-x['score'], x['avg_time']))
        return standings

    def get_game_summary(self) -> Dict[str, Any]:
        """
        Get complete game summary for final results.

        Returns:
            Dict with game statistics and player results
        """
        standings = self.get_current_standings()

        summary = {
            'session_id': self.session_id,
            'thread_id': self.thread_id,
            'game_mode': self.game_mode,
            'category': self.category,
            'difficulty': self.difficulty,
            'questions_total': self.questions_total,
            'questions_answered': self.questions_answered,
            'standings': standings
        }

        # Add winner for competitive mode
        if self.game_mode == 'competitive' and standings:
            summary['winner'] = standings[0]

        return summary

    def check_achievements_for_player(
        self,
        user_id: str,
        leaderboard_stats: Optional[Dict[str, Any]] = None
    ) -> List[str]:
        """
        Check for newly earned achievements for a player.

        Args:
            user_id: Discord user ID
            leaderboard_stats: Current leaderboard stats from database

        Returns:
            List of achievement IDs that are newly earned
        """
        if user_id not in self.players:
            return []

        player = self.players[user_id]

        # Combine game stats with leaderboard stats
        game_stats = {
            'best_streak': player.best_streak,
            'game_accuracy': player.get_accuracy(),
            'fast_answers_count': sum(1 for t in player.response_times if t < 3.0),
            'fastest_answer': min(player.response_times) if player.response_times else 999,
        }

        # Add leaderboard stats if provided
        if leaderboard_stats:
            game_stats.update(leaderboard_stats)

        # Check achievements
        newly_earned = check_achievements(game_stats, game_stats)
        return newly_earned


class GameSessionManager:
    """Manages all active trivia game sessions in memory."""

    def __init__(self):
        self._sessions: Dict[str, GameSession] = {}  # thread_id -> GameSession
        logger.debug("Initialized GameSessionManager")

    def create_session(
        self,
        session_id: int,
        thread_id: str,
        channel_id: str,
        game_mode: str,
        category: Optional[str],
        difficulty: str,
        questions_total: int,
        host_user_id: Optional[str] = None
    ) -> GameSession:
        """
        Create and register a new game session.

        Args:
            session_id: Database session ID
            thread_id: Discord thread ID
            channel_id: Parent channel ID
            game_mode: 'solo' or 'competitive'
            category: Free-form category text
            difficulty: 'easy', 'medium', or 'hard'
            questions_total: Total questions in the game
            host_user_id: User ID for solo mode

        Returns:
            GameSession: The created session
        """
        session = GameSession(
            session_id=session_id,
            thread_id=thread_id,
            channel_id=channel_id,
            game_mode=game_mode,
            category=category,
            difficulty=difficulty,
            questions_total=questions_total,
            host_user_id=host_user_id
        )

        self._sessions[thread_id] = session
        logger.info(f"Created game session {session_id} in thread {thread_id}")
        return session

    def get_session(self, thread_id: str) -> Optional[GameSession]:
        """Get an active game session by thread ID."""
        return self._sessions.get(thread_id)

    def end_session(self, thread_id: str) -> Optional[GameSession]:
        """
        End and remove a game session.

        Args:
            thread_id: Discord thread ID

        Returns:
            The ended session, or None if not found
        """
        session = self._sessions.pop(thread_id, None)
        if session:
            session.is_active = False
            logger.info(f"Ended game session {session.session_id} in thread {thread_id}")
        return session

    def is_active_game(self, thread_id: str) -> bool:
        """Check if there's an active game in a thread."""
        return thread_id in self._sessions

    def get_all_active_sessions(self) -> List[GameSession]:
        """Get all active game sessions."""
        return list(self._sessions.values())

    def cleanup_inactive_sessions(self, max_age_hours: int = 24) -> int:
        """
        Remove stale game sessions that haven't been updated recently.

        Args:
            max_age_hours: Maximum age in hours before cleanup

        Returns:
            Number of sessions cleaned up
        """
        # This is a simple cleanup - in production you'd check timestamps
        # For now, we'll just remove sessions marked as inactive
        to_remove = [
            thread_id for thread_id, session in self._sessions.items()
            if not session.is_active
        ]

        for thread_id in to_remove:
            del self._sessions[thread_id]

        if to_remove:
            logger.info(f"Cleaned up {len(to_remove)} inactive game sessions")

        return len(to_remove)
