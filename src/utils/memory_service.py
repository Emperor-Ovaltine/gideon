"""Session rotation and channel memory summarization."""
import logging
from datetime import datetime, timedelta
from typing import List, Dict, Any, Optional

logger = logging.getLogger(__name__)

_SUMMARIZE_PROMPT = (
    "Summarize the following Discord conversation in 2-3 sentences. "
    "Focus on the main topics discussed, any decisions made, and the general tone. "
    "Be concise and factual.\n\n"
    "{conversation}"
)

_MIN_MESSAGES_TO_SUMMARIZE = 3


async def check_and_rotate_session(channel_id: str, state, client) -> bool:
    """
    Checks whether the channel's session has expired. If so, optionally
    summarizes the history, stores a memory entry, and clears the history.

    Must be called *before* adding the new incoming message to history.

    Returns True if a session rotation occurred, False otherwise.
    """
    timeout_hours = state.get_effective_session_timeout(channel_id)
    history = state.get_channel_history(channel_id)

    if not history:
        return False

    last_msg = history[-1]
    last_ts = _parse_timestamp(last_msg.get("timestamp"))
    if last_ts is None:
        return False

    age = datetime.now() - last_ts
    if age <= timedelta(hours=timeout_hours):
        return False

    logger.info(
        f"[Memory] Session expired for channel {channel_id} "
        f"(last activity {age} ago, timeout {timeout_hours}h). Rotating."
    )

    summary_enabled = state.get_effective_memory_summary_enabled(channel_id)
    if summary_enabled and len(history) >= _MIN_MESSAGES_TO_SUMMARIZE:
        summary = await _summarize_history(history, channel_id, state, client)
        if summary:
            state.add_channel_memory(channel_id, summary, len(history))
            max_summaries = state.get_effective_max_memory_summaries(channel_id)
            state.prune_channel_memories(channel_id, max_summaries)
            logger.info(f"[Memory] Stored summary for channel {channel_id} ({len(history)} messages).")

    state.clear_channel_history(channel_id)
    return True


async def _summarize_history(
    history: List[Dict[str, Any]],
    channel_id: str,
    state,
    client,
) -> Optional[str]:
    """Calls the LLM to generate a compact summary of the conversation history."""
    model_id = state.get_effective_model(channel_id)
    try:
        provider, model_name = model_id.split("/", 1)
    except ValueError:
        provider = "openrouter"
        model_name = model_id

    # Use the client passed in (already the correct provider client from the caller)
    # Fall back to openrouter client if needed
    llm_client = client
    if llm_client is None or not hasattr(llm_client, "send_message_with_history"):
        logger.warning(
            f"[Memory] No suitable client for summarization in channel {channel_id}. Skipping."
        )
        return None

    conversation_text = _format_history_for_summary(history)
    prompt = _SUMMARIZE_PROMPT.format(conversation=conversation_text)

    try:
        response = await llm_client.send_message_with_history(
            messages=[{"role": "user", "content": prompt}],
            model=model_name,
            system_prompt="You are a helpful assistant that summarizes conversations.",
            images=[],
        )
        if response and not response.startswith("⚠️"):
            return response.strip()
        logger.warning(f"[Memory] Summarization returned error for channel {channel_id}: {response}")
        return None
    except Exception as e:
        logger.error(f"[Memory] Summarization failed for channel {channel_id}: {e}", exc_info=True)
        return None


def _format_history_for_summary(history: List[Dict[str, Any]]) -> str:
    lines = []
    for msg in history:
        role = msg.get("role", "unknown").capitalize()
        content = msg.get("content", "")
        if content:
            lines.append(f"{role}: {content}")
    return "\n".join(lines)


def _parse_timestamp(ts) -> Optional[datetime]:
    if ts is None:
        return None
    if isinstance(ts, datetime):
        return ts
    if isinstance(ts, str):
        for fmt in ("%Y-%m-%d %H:%M:%S.%f", "%Y-%m-%d %H:%M:%S", "%Y-%m-%dT%H:%M:%S.%f", "%Y-%m-%dT%H:%M:%S"):
            try:
                return datetime.strptime(ts, fmt)
            except ValueError:
                continue
    return None
