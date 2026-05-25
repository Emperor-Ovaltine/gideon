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

_SUMMARIZE_SYSTEM_BASE = "You are a helpful assistant that summarizes Discord conversations."

_SUMMARIZE_SYSTEM_WITH_CONTEXT = (
    "You are a helpful assistant that summarizes Discord conversations. "
    "For context, here is what has been previously noted about this channel:\n"
    "{prior_memories}\n\n"
    "Use this context to write a coherent summary that builds on prior history where relevant."
)

_MIN_MESSAGES_TO_SUMMARIZE = 3


async def check_and_rotate_session(channel_id: str, state, clients: dict) -> bool:
    """
    Checks whether the channel's session has expired. If so, optionally
    summarizes the history, stores a memory entry, and clears the history.

    Must be called *before* adding the new incoming message to history.
    `clients` must be a dict mapping provider name → client object.

    Returns True if a rotation occurred, False otherwise.
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
        conversation_start = _parse_timestamp(history[0].get("timestamp"))
        summary = await _summarize_history(history, channel_id, state, clients)
        if summary:
            state.add_channel_memory(channel_id, summary, len(history),
                                     conversation_start=conversation_start)
            max_summaries = state.get_effective_max_memory_summaries(channel_id)
            state.prune_channel_memories(channel_id, max_summaries)
            logger.info(f"[Memory] Stored summary for channel {channel_id} ({len(history)} messages).")

    state.clear_channel_history(channel_id)
    return True


async def _summarize_history(
    history: List[Dict[str, Any]],
    channel_id: str,
    state,
    clients: dict,
) -> Optional[str]:
    """Calls the LLM to generate a summary of the conversation history.

    Fetches existing channel memories and passes them as context so the
    new summary can build on prior sessions rather than summarising in isolation.
    """
    # Resolve the correct client from the channel's effective model
    model_id = state.get_effective_model(channel_id)
    try:
        provider, model_name = model_id.split("/", 1)
    except ValueError:
        provider = "openrouter"
        model_name = model_id

    llm_client = clients.get(provider) or clients.get("openrouter")
    if llm_client is None or not hasattr(llm_client, "send_message_with_history"):
        logger.warning(
            f"[Memory] No suitable client for summarization in channel {channel_id} "
            f"(provider='{provider}'). Skipping."
        )
        return None

    # Build a context-aware system prompt from existing memories (Issue 1 fix)
    existing_memories = state.get_channel_memories(channel_id, limit=5)
    if existing_memories:
        prior_lines = [f"- {m['summary']}" for m in existing_memories]
        system_prompt = _SUMMARIZE_SYSTEM_WITH_CONTEXT.format(
            prior_memories="\n".join(prior_lines)
        )
    else:
        system_prompt = _SUMMARIZE_SYSTEM_BASE

    conversation_text = _format_history_for_summary(history)
    prompt = _SUMMARIZE_PROMPT.format(conversation=conversation_text)

    try:
        response = await llm_client.send_message_with_history(
            messages=[{"role": "user", "content": prompt}],
            model=model_name,
            system_prompt=system_prompt,
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
        for fmt in ("%Y-%m-%d %H:%M:%S.%f", "%Y-%m-%d %H:%M:%S",
                    "%Y-%m-%dT%H:%M:%S.%f", "%Y-%m-%dT%H:%M:%S"):
            try:
                return datetime.strptime(ts, fmt)
            except ValueError:
                continue
    return None
