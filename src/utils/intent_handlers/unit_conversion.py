"""Handler for unit conversion intent using AI."""

import logging
from datetime import datetime

logger = logging.getLogger('unit_conversion_handler')


async def handle_unit_conversion(cog, message, channel_id, value, source_unit, target_unit, category=""):
    """
    Handle unit conversion requests using AI.

    Args:
        cog: The MentionCommands cog instance
        message: Discord message object
        channel_id: Channel ID as string
        value: Numeric value to convert
        source_unit: Source unit
        target_unit: Target unit
        category: Unit category hint (optional)
    """
    # Validate inputs
    if not value:
        await message.channel.send(
            "❌ I need a value to convert. "
            "Try something like: '@Gideon convert 5 miles to km'"
        )
        logger.warning(f"[UnitConversion] Missing value for user {message.author.id}")
        return

    if not source_unit or not source_unit.strip():
        await message.channel.send(
            "❌ I need to know the source unit. "
            "Try something like: '@Gideon convert 5 miles to km'"
        )
        logger.warning(f"[UnitConversion] Missing source unit for user {message.author.id}")
        return

    if not target_unit or not target_unit.strip():
        await message.channel.send(
            "❌ I need to know the target unit. "
            "Try something like: '@Gideon convert 5 miles to km'"
        )
        logger.warning(f"[UnitConversion] Missing target unit for user {message.author.id}")
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
        await message.channel.send("⚠️ Unit conversion system not available.")
        logger.error(f"[UnitConversion] Client for provider '{provider}' not available")
        return

    # Build unit conversion system prompt
    system_prompt = f"""You are a precise unit conversion assistant. Convert the value from one unit to another.

Instructions:
1. Perform the accurate unit conversion calculation
2. Provide ONLY the converted value followed by the target unit
3. Be concise - just the number and unit, nothing else
4. Round to reasonable precision (avoid unnecessary decimals)
5. For currency conversions, note that exchange rates may not be current/live

Example responses:
- "8.05 km"
- "0°C"
- "Approximately 85 EUR (Note: Exchange rates vary)"
- "10 meters"
"""

    # Prepare message for AI
    conversion_query = f"Convert {value} {source_unit} to {target_unit}"
    messages = [
        {"role": "user", "content": conversion_query}
    ]

    try:
        # Send conversion request
        async with message.channel.typing():
            conversion_result = await client_to_use.send_message_with_history(
                messages=messages,
                model=model_name,
                system_prompt=system_prompt
            )

        # Format response
        response_message = f"**Unit Conversion:**\n{value} {source_unit} = **{conversion_result}**"

        await message.channel.send(response_message)

        # Add to conversation history
        await cog.state.add_to_channel_history(channel_id, {
            "role": "assistant",
            "content": f"Converted {value} {source_unit} to {target_unit}: {conversion_result}",
            "timestamp": datetime.now()
        })

        logger.info(f"[UnitConversion] User {message.author.id} converted {value} {source_unit} to {target_unit}")

    except Exception as e:
        logger.exception(f"[UnitConversion] Error for user {message.author.id}: {e}")
        await message.channel.send(f"❌ Unit conversion failed: {str(e)}")
