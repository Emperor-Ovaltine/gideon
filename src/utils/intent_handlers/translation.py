"""Text translation via the channel's LLM (translate tool)."""

import logging

logger = logging.getLogger('translation_handler')


async def translate_text(client, model_name, text, source_language, target_language) -> str:
    """Translates text using the given LLM client. Returns the translation.

    Raises ValueError on bad input or provider failure.
    """
    if not text or not text.strip():
        raise ValueError("No text provided to translate.")
    if not target_language or not target_language.strip():
        raise ValueError("No target language provided.")

    if source_language and source_language.strip():
        system_prompt = (
            f"You are a professional translator. Translate the following text from "
            f"{source_language} to {target_language}. Provide ONLY the translation, "
            f"no explanations or additional text."
        )
    else:
        system_prompt = (
            f"You are a professional translator. Translate the following text to "
            f"{target_language}. Provide ONLY the translation, no explanations or additional text."
        )

    translation = await client.send_message_with_history(
        messages=[{"role": "user", "content": text}],
        model=model_name,
        system_prompt=system_prompt
    )

    if not isinstance(translation, str) or translation.startswith("⚠️"):
        raise ValueError(f"Translation provider error: {translation}")

    return f"Translation to {target_language}: {translation}"
