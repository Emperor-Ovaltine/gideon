"""Unit conversion via the channel's LLM (convert_units tool)."""

import logging

logger = logging.getLogger('unit_conversion_handler')

_SYSTEM_PROMPT = """You are a precise unit conversion assistant. Convert the value from one unit to another.

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


async def convert_units(client, model_name, value, source_unit, target_unit, category="") -> str:
    """Converts a value between units using the given LLM client.

    Returns a human-readable result string. Raises ValueError on bad input
    or provider failure.
    """
    if value is None or value == "":
        raise ValueError("No value provided to convert.")
    if not source_unit or not source_unit.strip():
        raise ValueError("No source unit provided.")
    if not target_unit or not target_unit.strip():
        raise ValueError("No target unit provided.")

    result = await client.send_message_with_history(
        messages=[{"role": "user", "content": f"Convert {value} {source_unit} to {target_unit}"}],
        model=model_name,
        system_prompt=_SYSTEM_PROMPT
    )

    if not isinstance(result, str) or result.startswith("⚠️"):
        raise ValueError(f"Unit conversion provider error: {result}")

    return f"{value} {source_unit} = {result}"
