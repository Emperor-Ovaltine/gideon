"""Configuration constants and achievements for the trivia system."""

# ===== AI Model Configuration =====

# Default models (can be overridden via global config)
DEFAULT_QUESTION_MODEL = "openrouter/openai/gpt-4o-mini"  # Cheap, fast, good quality
DEFAULT_ANSWER_MODEL = "openrouter/openai/gpt-4o-mini"    # Good at fuzzy matching

# Model configuration keys in GLOBAL_CONFIG
CONFIG_QUESTION_MODEL = "trivia_question_model"
CONFIG_ANSWER_MODEL = "trivia_answer_model"

# ===== Scoring Constants =====

# Base points by difficulty
DIFFICULTY_BASE_POINTS = {
    'easy': 100,
    'medium': 200,
    'hard': 300
}

# Speed bonus multipliers (applied to base points)
def get_speed_bonus_multiplier(response_time_seconds: float) -> float:
    """Calculate speed bonus multiplier based on response time."""
    if response_time_seconds < 5:
        return 1.5  # +50% bonus
    elif response_time_seconds < 10:
        return 1.3  # +30% bonus
    elif response_time_seconds < 20:
        return 1.1  # +10% bonus
    else:
        return 1.0  # No bonus

# Streak multipliers
def get_streak_multiplier(streak: int) -> float:
    """Calculate streak multiplier based on consecutive correct answers."""
    if streak < 3:
        return 1.0
    elif streak < 5:
        return 1.1   # 3-4 correct
    elif streak < 10:
        return 1.25  # 5-9 correct
    elif streak < 20:
        return 1.5   # 10-19 correct
    else:
        return 2.0   # 20+ correct

def calculate_points(difficulty: str, response_time: float, streak: int) -> int:
    """
    Calculate total points for a correct answer.

    Args:
        difficulty: 'easy', 'medium', or 'hard'
        response_time: Time taken to answer in seconds
        streak: Current consecutive correct answers

    Returns:
        int: Total points earned
    """
    base_points = DIFFICULTY_BASE_POINTS.get(difficulty, 100)
    speed_bonus = get_speed_bonus_multiplier(response_time)
    streak_bonus = get_streak_multiplier(streak)

    # Apply speed bonus to base, then apply streak multiplier
    points_with_speed = int(base_points * speed_bonus)
    total_points = int(points_with_speed * streak_bonus)

    return total_points

# ===== Game Configuration =====

DEFAULT_QUESTIONS_PER_GAME = 10
MAX_QUESTIONS_PER_GAME = 50
DEFAULT_DIFFICULTY = 'medium'

# Timeouts
QUESTION_TIMEOUT_SECONDS = 60  # How long to wait for an answer
NEXT_QUESTION_DELAY_SECONDS = 3  # Delay before posting next question
COMPETITIVE_ANSWER_WINDOW_SECONDS = 10  # Window after first correct answer for others to respond

# Competitive mode scoring
LATE_ANSWER_POINT_MULTIPLIER = 0.5  # Late answers in competitive earn 50% points

# Rate limiting
MAX_GAMES_PER_HOUR_PER_USER = 10
MAX_ANSWERS_PER_MINUTE_PER_USER = 20

# ===== Achievement Definitions =====

ACHIEVEMENTS = {
    # Milestone achievements
    'first_win': {
        'name': '🎯 First Blood',
        'description': 'Answer your first question correctly',
        'check': lambda stats: stats.get('total_correct', 0) >= 1
    },
    'streak_5': {
        'name': '🔥 On Fire',
        'description': 'Get 5 correct answers in a row',
        'check': lambda stats: stats.get('best_streak', 0) >= 5
    },
    'streak_10': {
        'name': '⚡ Unstoppable',
        'description': 'Get 10 correct answers in a row',
        'check': lambda stats: stats.get('best_streak', 0) >= 10
    },
    'streak_20': {
        'name': '🌟 Legendary',
        'description': 'Get 20 correct answers in a row',
        'check': lambda stats: stats.get('best_streak', 0) >= 20
    },
    'perfect_game': {
        'name': '💯 Perfectionist',
        'description': 'Complete a game with 100% accuracy',
        'check': lambda stats: stats.get('game_accuracy', 0) == 100
    },

    # Speed achievements
    'speed_demon': {
        'name': '💨 Speed Demon',
        'description': 'Answer 10 questions in under 3 seconds each',
        'check': lambda stats: stats.get('fast_answers_count', 0) >= 10
    },
    'lightning_fast': {
        'name': '🚀 Lightning Fast',
        'description': 'Answer a question in under 1 second',
        'check': lambda stats: stats.get('fastest_answer', 999) < 1.0
    },

    # Participation achievements
    'trivia_enthusiast': {
        'name': '🎲 Trivia Enthusiast',
        'description': 'Play 10 trivia games',
        'check': lambda stats: stats.get('total_games', 0) >= 10
    },
    'trivia_addict': {
        'name': '🎯 Trivia Addict',
        'description': 'Play 50 trivia games',
        'check': lambda stats: stats.get('total_games', 0) >= 50
    },
    'trivia_master': {
        'name': '👑 Trivia Master',
        'description': 'Play 100 trivia games',
        'check': lambda stats: stats.get('total_games', 0) >= 100
    },

    # Competitive achievements
    'competitive_winner': {
        'name': '🏆 Champion',
        'description': 'Win 25 competitive rounds',
        'check': lambda stats: stats.get('competitive_wins', 0) >= 25
    },
    'leaderboard_king': {
        'name': '👑 Trivia King/Queen',
        'description': 'Reach #1 on the leaderboard',
        'check': lambda stats: stats.get('leaderboard_position', 999) == 1
    },

    # Accuracy achievements
    'sharp_shooter': {
        'name': '🎯 Sharp Shooter',
        'description': 'Maintain 80% accuracy over 50 questions',
        'check': lambda stats: (
            stats.get('total_questions', 0) >= 50 and
            (stats.get('total_correct', 0) / stats.get('total_questions', 1)) >= 0.8
        )
    },
    'genius': {
        'name': '🧠 Genius',
        'description': 'Maintain 90% accuracy over 100 questions',
        'check': lambda stats: (
            stats.get('total_questions', 0) >= 100 and
            (stats.get('total_correct', 0) / stats.get('total_questions', 1)) >= 0.9
        )
    },

    # Points achievements
    'point_collector': {
        'name': '💰 Point Collector',
        'description': 'Earn 10,000 total points',
        'check': lambda stats: stats.get('total_points', 0) >= 10000
    },
    'point_millionaire': {
        'name': '💎 Point Millionaire',
        'description': 'Earn 100,000 total points',
        'check': lambda stats: stats.get('total_points', 0) >= 100000
    }
}

def check_achievements(user_stats: dict, game_stats: dict = None) -> list:
    """
    Check which achievements a user has earned.

    Args:
        user_stats: User's overall stats from leaderboard
        game_stats: Optional game-specific stats (for game-specific achievements)

    Returns:
        list: List of achievement IDs that are newly earned
    """
    newly_earned = []

    # Combine user stats with game stats
    combined_stats = {**user_stats}
    if game_stats:
        combined_stats.update(game_stats)

    for achievement_id, achievement in ACHIEVEMENTS.items():
        try:
            if achievement['check'](combined_stats):
                newly_earned.append(achievement_id)
        except Exception:
            # Skip achievements that can't be checked yet
            continue

    return newly_earned

# ===== AI Prompt Templates =====

QUESTION_GENERATION_PROMPT = """You are a trivia question generator. Generate a {difficulty} difficulty trivia question about: {category}

Requirements:
- Question type: multiple_choice
- Difficulty: {difficulty} (easy=common knowledge, medium=specific knowledge, hard=expert/obscure)
- The question should be factual and have a single correct answer
- Ensure the correct answer is randomly positioned among the options (not always first)
- Format: JSON only, no other text
{avoid_duplicates}

Response format:
{{
  "question": "What is the capital of France?",
  "correct_answer": "Paris",
  "options": ["Paris", "London", "Berlin", "Madrid"],
  "explanation": "Brief 1-sentence explanation"
}}

Generate the trivia question now:"""

ANSWER_VALIDATION_PROMPT = """You are a trivia answer validator.

Question: {question}
Correct Answer: {correct_answer}
User's Answer: {user_answer}

Determine if the user's answer is correct, accounting for:
- Spelling variations and typos
- Capitalization differences
- Extra whitespace
- Partial matches that demonstrate knowledge (e.g., "Paris" for "Paris, France")
- Common abbreviations
- Synonyms or alternative names

Respond with ONLY a JSON object:
{{
  "is_correct": true or false,
  "confidence": 0.0 to 1.0,
  "reason": "Brief explanation of your decision"
}}"""

# ===== Answer Matching Configuration =====

# Edit distance threshold for fuzzy AI validation
# If edit distance is greater than this, don't bother with AI validation
MAX_EDIT_DISTANCE_FOR_AI = 5

# Option letter mappings
OPTION_LETTERS = ['A', 'B', 'C', 'D']

def normalize_answer(answer: str) -> str:
    """Normalize an answer for comparison."""
    return answer.strip().upper()

def get_option_letter(options: list, correct_answer: str) -> str:
    """Get the letter (A/B/C/D) for the correct answer."""
    try:
        index = options.index(correct_answer)
        return OPTION_LETTERS[index]
    except (ValueError, IndexError):
        return ""

# ===== Difficulty Descriptions =====

DIFFICULTY_DESCRIPTIONS = {
    'easy': '⭐ Easy - Common knowledge questions',
    'medium': '⭐⭐ Medium - Requires specific knowledge',
    'hard': '⭐⭐⭐ Hard - Expert level questions'
}

GAME_MODE_DESCRIPTIONS = {
    'solo': '🎯 Solo - Personal trivia session',
    'competitive': '⚔️ Competitive - First correct answer wins each round'
}

# ===== Leaderboard Configuration =====

LEADERBOARD_PAGE_SIZE = 10

# Emoji rankings for leaderboard display
RANK_EMOJIS = {
    1: '🥇',
    2: '🥈',
    3: '🥉'
}

def get_rank_emoji(rank: int) -> str:
    """Get emoji for a leaderboard rank."""
    return RANK_EMOJIS.get(rank, f'{rank}.')
