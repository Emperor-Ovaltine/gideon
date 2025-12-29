"""Handler for definition/explanation intent."""

import logging
from datetime import datetime

logger = logging.getLogger('definition_handler')


async def handle_definition(cog, message, channel_id, term, depth="brief"):
    """
    Handle definition/explanation requests using AI.

    Args:
        cog: The MentionCommands cog instance
        message: Discord message object
        channel_id: Channel ID as string
        term: The term/concept to define
        depth: "brief" or "detailed" (default: "brief")
    """
    # Validate term
    if not term or not term.strip():
        await message.channel.send(
            "❌ I need a term to define. "
            "Try something like: '@Gideon what is quantum computing?'"
        )
        logger.warning(f"[Definition] Missing term for user {message.author.id}")
        return

    # Get model and client
    model_id_full = cog.get_model_for_channel(channel_id)
    try:
        provider, model_name = model_id_full.split('/', 1)
    except ValueError:
        provider = cog.state.global_provider if cog.state else "openrouter"
        model_name = model_id_full

    client_to_use = cog.clients.get(provider)

    if not client_to_use or not hasattr(client_to_use, 'send_message_with_history'):
        await message.channel.send("⚠️ Definition system not available.")
        logger.error(f"[Definition] Client for provider '{provider}' not available")
        return

    # Build definition-specific system prompt based on depth
    if depth and depth.lower() == "detailed":
        system_prompt = f"You are an encyclopedia. Provide a clear, comprehensive definition of '{term}'. Include key details, examples if relevant, and important context. Be thorough but well-organized."
    else:
        system_prompt = f"You are an encyclopedia. Provide a clear, concise definition of '{term}'. Keep it factual and educational. Be brief (2-4 sentences) unless the topic requires more context."

    # Prepare message for AI
    messages = [
        {"role": "user", "content": f"Define: {term}"}
    ]

    try:
        # Send definition request
        async with message.channel.typing():
            definition = await client_to_use.send_message_with_history(
                messages=messages,
                model=model_name,
                system_prompt=system_prompt
            )

        # Send response
        await message.channel.send(definition)

        # Add to conversation history
        await cog.state.add_to_channel_history(channel_id, {
            "role": "assistant",
            "content": definition,
            "timestamp": datetime.now()
        })

        logger.info(f"[Definition] User {message.author.id} requested definition of: {term}")

    except Exception as e:
        logger.exception(f"[Definition] Error for user {message.author.id}: {e}")
        await message.channel.send(f"❌ Definition lookup failed: {str(e)}")
