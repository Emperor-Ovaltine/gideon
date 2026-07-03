"""Factual definition lookup via the channel's LLM (define tool)."""

import logging

logger = logging.getLogger('definition_handler')


async def define_term(client, model_name, term, depth="brief") -> str:
    """Looks up a definition using the given LLM client. Returns the definition.

    Raises ValueError on bad input or provider failure.
    """
    if not term or not term.strip():
        raise ValueError("No term provided to define.")

    if depth and depth.lower() == "detailed":
        system_prompt = (
            f"You are an encyclopedia. Provide a clear, comprehensive definition of '{term}'. "
            f"Include key details, examples if relevant, and important context. "
            f"Be thorough but well-organized."
        )
    else:
        system_prompt = (
            f"You are an encyclopedia. Provide a clear, concise definition of '{term}'. "
            f"Keep it factual and educational. Be brief (2-4 sentences) unless the topic "
            f"requires more context."
        )

    definition = await client.send_message_with_history(
        messages=[{"role": "user", "content": f"Define: {term}"}],
        model=model_name,
        system_prompt=system_prompt
    )

    if not isinstance(definition, str) or definition.startswith("⚠️"):
        raise ValueError(f"Definition provider error: {definition}")

    return definition
