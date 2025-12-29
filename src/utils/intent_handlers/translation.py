"""Handler for translation intent."""

import logging
from datetime import datetime

logger = logging.getLogger('translation_handler')


async def handle_translation(cog, message, channel_id, text, source_language, target_language):
    """
    Handle translation requests using AI.

    Args:
        cog: The MentionCommands cog instance
        message: Discord message object
        channel_id: Channel ID as string
        text: Text to translate
        source_language: Source language (can be empty for auto-detection)
        target_language: Target language
    """
    # Validate inputs
    if not text or not text.strip():
        await message.channel.send(
            "❌ I need text to translate. "
            "Try something like: '@Gideon translate hello to Spanish'"
        )
        logger.warning(f"[Translation] Missing text for user {message.author.id}")
        return

    if not target_language or not target_language.strip():
        await message.channel.send(
            "❌ I need to know what language to translate to. "
            "Try something like: '@Gideon translate hello to Spanish'"
        )
        logger.warning(f"[Translation] Missing target language for user {message.author.id}")
        return

    # Get model and client for translation
    model_id_full = cog.get_model_for_channel(channel_id)
    try:
        provider, model_name = model_id_full.split('/', 1)
    except ValueError:
        provider = cog.state.global_provider if cog.state else "openrouter"
        model_name = model_id_full

    client_to_use = cog.clients.get(provider)

    if not client_to_use or not hasattr(client_to_use, 'send_message_with_history'):
        await message.channel.send("⚠️ Translation system not available.")
        logger.error(f"[Translation] Client for provider '{provider}' not available")
        return

    # Build translation-specific system prompt
    if source_language and source_language.strip():
        system_prompt = f"You are a professional translator. Translate the following text from {source_language} to {target_language}. Provide ONLY the translation, no explanations or additional text."
    else:
        system_prompt = f"You are a professional translator. Translate the following text to {target_language}. Provide ONLY the translation, no explanations or additional text."

    # Prepare message for AI
    messages = [
        {"role": "user", "content": text}
    ]

    try:
        # Send translation request
        async with message.channel.typing():
            translation = await client_to_use.send_message_with_history(
                messages=messages,
                model=model_name,
                system_prompt=system_prompt
            )

        # Format response
        if source_language and source_language.strip():
            response_message = f"**Translation** ({source_language} → {target_language}):\n{translation}"
        else:
            response_message = f"**Translation** (→ {target_language}):\n{translation}"

        await message.channel.send(response_message)

        # Add to conversation history
        await cog.state.add_to_channel_history(channel_id, {
            "role": "assistant",
            "content": f"Translated '{text}' to {target_language}: {translation}",
            "timestamp": datetime.now()
        })

        logger.info(f"[Translation] User {message.author.id} translated: {text} → {target_language}")

    except Exception as e:
        logger.exception(f"[Translation] Error for user {message.author.id}: {e}")
        await message.channel.send(f"❌ Translation failed: {str(e)}")
