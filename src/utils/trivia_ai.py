"""AI-powered trivia question generation and answer validation."""

import json
import logging
from typing import Dict, Any, Optional, Tuple
from difflib import SequenceMatcher

from .trivia_config import (
    QUESTION_GENERATION_PROMPT,
    ANSWER_VALIDATION_PROMPT,
    MAX_EDIT_DISTANCE_FOR_AI,
    normalize_answer,
    DEFAULT_QUESTION_MODEL,
    DEFAULT_ANSWER_MODEL
)

logger = logging.getLogger(__name__)


def calculate_edit_distance(s1: str, s2: str) -> int:
    """Calculate Levenshtein edit distance between two strings."""
    if len(s1) < len(s2):
        return calculate_edit_distance(s2, s1)

    if len(s2) == 0:
        return len(s1)

    previous_row = range(len(s2) + 1)
    for i, c1 in enumerate(s1):
        current_row = [i + 1]
        for j, c2 in enumerate(s2):
            # j+1 instead of j since previous_row and current_row are one character longer than s2
            insertions = previous_row[j + 1] + 1
            deletions = current_row[j] + 1
            substitutions = previous_row[j] + (c1 != c2)
            current_row.append(min(insertions, deletions, substitutions))
        previous_row = current_row

    return previous_row[-1]


async def generate_question(
    category: str,
    difficulty: str,
    ai_client,
    channel_id: str = None,
    state_manager=None,
    asked_questions: list = None
) -> Optional[Dict[str, Any]]:
    """
    Generate a trivia question using AI.

    Args:
        category: Free-form category text (e.g., "science", "80s movies")
        difficulty: 'easy', 'medium', or 'hard'
        ai_client: AI client instance (OpenRouterClient or OpenAIClient)
        channel_id: Discord channel ID (to get effective model)
        state_manager: Optional state manager for model configuration
        asked_questions: List of previously asked questions to avoid duplicates

    Returns:
        Dict with keys: question, correct_answer, options, explanation
        Returns None if generation fails
    """
    # Get the effective model for the channel
    model_to_use = None
    if state_manager and channel_id:
        model_to_use = state_manager.get_effective_model(channel_id)
        logger.debug(f"Using channel effective model: {model_to_use}")

    # Fallback to configured model or default
    if not model_to_use:
        model_to_use = DEFAULT_QUESTION_MODEL
        if state_manager:
            from .trivia_config import CONFIG_QUESTION_MODEL
            configured_model = state_manager.get_global_config(CONFIG_QUESTION_MODEL)
            if configured_model:
                model_to_use = configured_model
                logger.debug(f"Using configured question model: {model_to_use}")

    # Build duplicate avoidance instruction
    avoid_duplicates = ""
    if asked_questions and len(asked_questions) > 0:
        questions_list = "\n".join([f"  - {q}" for q in asked_questions[-10:]])  # Only show last 10
        avoid_duplicates = f"\n- IMPORTANT: Do NOT generate questions about the same topic as these previously asked questions:\n{questions_list}"

    # Format the prompt
    prompt = QUESTION_GENERATION_PROMPT.format(
        difficulty=difficulty,
        category=category or "general knowledge",
        avoid_duplicates=avoid_duplicates
    )

    try:
        # Generate question using message history format
        messages = [{"role": "user", "content": prompt}]

        # Use send_message_with_history with JSON response format
        response = await ai_client.send_message_with_history(
            messages=messages,
            model=model_to_use,
            system_prompt="You are a trivia question generator. Only respond with valid JSON.",
            response_format={"type": "json_object"}
        )

        # Parse JSON response
        # Try to extract JSON from response (in case there's extra text)
        response_text = response.strip()

        # Try to find JSON object in response
        start_idx = response_text.find('{')
        end_idx = response_text.rfind('}') + 1

        if start_idx == -1 or end_idx == 0:
            logger.error(f"No JSON object found in AI response: {response_text[:200]}")
            return None

        json_str = response_text[start_idx:end_idx]
        question_data = json.loads(json_str)

        # Validate required fields
        required_fields = ['question', 'correct_answer', 'options']
        if not all(field in question_data for field in required_fields):
            logger.error(f"Missing required fields in question data: {question_data}")
            return None

        # Validate options
        if not isinstance(question_data['options'], list) or len(question_data['options']) < 2:
            logger.error(f"Invalid options in question data: {question_data.get('options')}")
            return None

        # Ensure correct answer is in options
        if question_data['correct_answer'] not in question_data['options']:
            logger.warning(f"Correct answer not in options, adding it: {question_data['correct_answer']}")
            # Replace first option with correct answer
            question_data['options'][0] = question_data['correct_answer']

        logger.debug(f"Generated trivia question: {question_data['question'][:50]}...")
        return question_data

    except json.JSONDecodeError as e:
        logger.error(f"Failed to parse AI response as JSON: {e}\nResponse: {response[:200] if 'response' in locals() else 'N/A'}")
        return None
    except Exception as e:
        logger.error(f"Error generating trivia question: {e}", exc_info=True)
        return None


async def validate_answer_with_ai(
    question: str,
    correct_answer: str,
    user_answer: str,
    ai_client,
    channel_id: str = None,
    state_manager=None
) -> Tuple[bool, float, str]:
    """
    Validate a user's answer using AI for fuzzy matching.

    Args:
        question: The trivia question text
        correct_answer: The correct answer
        user_answer: User's submitted answer
        ai_client: AI client instance
        channel_id: Discord channel ID (to get effective model)
        state_manager: Optional state manager for model configuration

    Returns:
        Tuple of (is_correct, confidence, reason)
    """
    # Get the effective model for the channel
    model_to_use = None
    if state_manager and channel_id:
        model_to_use = state_manager.get_effective_model(channel_id)
        logger.debug(f"Using channel effective model for validation: {model_to_use}")

    # Fallback to configured model or default
    if not model_to_use:
        model_to_use = DEFAULT_ANSWER_MODEL
        if state_manager:
            from .trivia_config import CONFIG_ANSWER_MODEL
            configured_model = state_manager.get_global_config(CONFIG_ANSWER_MODEL)
            if configured_model:
                model_to_use = configured_model
                logger.debug(f"Using configured answer model: {model_to_use}")

    # Format the prompt
    prompt = ANSWER_VALIDATION_PROMPT.format(
        question=question,
        correct_answer=correct_answer,
        user_answer=user_answer
    )

    try:
        # Validate answer using message history format
        messages = [{"role": "user", "content": prompt}]

        # Use send_message_with_history with JSON response format
        response = await ai_client.send_message_with_history(
            messages=messages,
            model=model_to_use,
            system_prompt="You are a trivia answer validator. Only respond with valid JSON.",
            response_format={"type": "json_object"}
        )

        # Parse JSON response
        response_text = response.strip()
        start_idx = response_text.find('{')
        end_idx = response_text.rfind('}') + 1

        if start_idx == -1 or end_idx == 0:
            logger.error(f"No JSON object found in validation response: {response_text[:200]}")
            return (False, 0.0, "Failed to parse AI response")

        json_str = response_text[start_idx:end_idx]
        validation_data = json.loads(json_str)

        is_correct = validation_data.get('is_correct', False)
        confidence = validation_data.get('confidence', 0.0)
        reason = validation_data.get('reason', 'No reason provided')

        logger.debug(f"AI validation: {is_correct} (confidence: {confidence})")
        return (is_correct, confidence, reason)

    except json.JSONDecodeError as e:
        logger.error(f"Failed to parse AI validation response as JSON: {e}")
        return (False, 0.0, "Failed to parse AI response")
    except Exception as e:
        logger.error(f"Error validating answer with AI: {e}", exc_info=True)
        return (False, 0.0, f"Error: {str(e)}")


def validate_answer(
    user_answer: str,
    correct_answer: str,
    options: list
) -> Tuple[bool, str]:
    """
    Validate a user's answer using exact matching.
    This is the fast, free validation that happens first.

    Args:
        user_answer: User's submitted answer
        correct_answer: The correct answer
        options: List of all answer options (for letter matching)

    Returns:
        Tuple of (is_correct, match_type) where match_type is:
        - 'exact': Exact match with correct answer
        - 'letter': Matched via option letter (A/B/C/D)
        - 'none': No match
    """
    normalized_user = normalize_answer(user_answer)
    normalized_correct = normalize_answer(correct_answer)

    # Check for exact match with correct answer
    if normalized_user == normalized_correct:
        return (True, 'exact')

    # Check if user answered with option letter (A, B, C, D)
    option_letters = ['A', 'B', 'C', 'D']
    if normalized_user in option_letters:
        try:
            # Get the index of the letter
            index = option_letters.index(normalized_user)
            if index < len(options):
                # Check if this option is the correct answer
                if options[index] == correct_answer:
                    return (True, 'letter')
        except (ValueError, IndexError):
            pass

    # Check for match with any normalized option text
    for i, option in enumerate(options):
        normalized_option = normalize_answer(option)
        if normalized_user == normalized_option:
            # Check if this option is correct
            if option == correct_answer:
                return (True, 'exact')
            else:
                return (False, 'wrong_option')

    return (False, 'none')


def should_use_ai_validation(user_answer: str, correct_answer: str) -> bool:
    """
    Determine if AI validation should be used based on answer similarity.

    Args:
        user_answer: User's submitted answer
        correct_answer: The correct answer

    Returns:
        bool: True if AI validation should be attempted
    """
    normalized_user = normalize_answer(user_answer)
    normalized_correct = normalize_answer(correct_answer)

    # Calculate edit distance
    edit_dist = calculate_edit_distance(normalized_user, normalized_correct)

    # If edit distance is small, might be a typo - use AI
    if edit_dist <= MAX_EDIT_DISTANCE_FOR_AI:
        # Also check similarity ratio
        similarity = SequenceMatcher(None, normalized_user, normalized_correct).ratio()
        # If >50% similar, worth checking with AI
        if similarity > 0.5:
            logger.debug(f"Edit distance: {edit_dist}, Similarity: {similarity:.2f} - Using AI validation")
            return True

    return False


async def validate_answer_complete(
    user_answer: str,
    correct_answer: str,
    options: list,
    question: str,
    ai_client,
    channel_id: str = None,
    state_manager=None
) -> Tuple[bool, str, Optional[str]]:
    """
    Complete answer validation with exact matching first, then AI if needed.

    Args:
        user_answer: User's submitted answer
        correct_answer: The correct answer
        options: List of all answer options
        question: The full question text (for AI context)
        ai_client: AI client for fuzzy matching
        channel_id: Discord channel ID (to get effective model)
        state_manager: Optional state manager for configuration

    Returns:
        Tuple of (is_correct, match_type, ai_reason)
    """
    # First try exact matching (fast, free)
    is_correct, match_type = validate_answer(user_answer, correct_answer, options)

    if match_type in ['exact', 'letter', 'wrong_option']:
        # Definitive match found
        return (is_correct, match_type, None)

    # No exact match - check if AI validation is worth it
    if not should_use_ai_validation(user_answer, correct_answer):
        return (False, 'no_match', None)

    # Use AI for fuzzy matching
    logger.info(f"Using AI validation for '{user_answer}' vs '{correct_answer}'")
    is_correct_ai, confidence, reason = await validate_answer_with_ai(
        question, correct_answer, user_answer, ai_client, channel_id, state_manager
    )

    if is_correct_ai and confidence > 0.7:
        # High confidence AI match
        return (True, 'ai_fuzzy', reason)
    else:
        return (False, 'ai_rejected', reason)
