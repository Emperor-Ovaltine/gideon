"""
Tool registry for native LLM tool calling.

Defines all available tools in OpenAI function schema format and provides
a dispatch mechanism to execute tool calls from the LLM.

This replaces the old intent classification system with native tool calling,
where the primary LLM model decides which tools to call as part of its inference.
"""

import json
import logging
from typing import Dict, Any, List, Optional, Callable

logger = logging.getLogger('tool_registry')


# ─── Tool Definitions (OpenAI function schema format) ───────────────────────

TOOL_DEFINITIONS: List[Dict[str, Any]] = [
    {
        "type": "function",
        "function": {
            "name": "set_reminder",
            "description": "Set a reminder for the user. Use when the user asks to be reminded about something at a future time.",
            "parameters": {
                "type": "object",
                "properties": {
                    "reminder_message": {
                        "type": "string",
                        "description": "What to remind the user about"
                    },
                    "time_expression": {
                        "type": "string",
                        "description": "When to send the reminder, as a natural language time expression (e.g., 'in 2 hours', 'tomorrow at 3pm', 'at 5pm')"
                    }
                },
                "required": ["reminder_message", "time_expression"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "generate_image",
            "description": "Generate an AI image. Use when the user asks to draw, create, or generate a picture or image.",
            "parameters": {
                "type": "object",
                "properties": {
                    "prompt": {
                        "type": "string",
                        "description": "The main description of what to generate"
                    },
                    "negative_prompt": {
                        "type": "string",
                        "description": "What to exclude from the image (optional)"
                    },
                    "size": {
                        "type": "string",
                        "description": "Dimensions if specified (e.g., '512x512', '1024x1024', 'landscape', 'portrait'). Empty string if not specified."
                    },
                    "quality": {
                        "type": "string",
                        "description": "Quality setting: 'hd', 'high quality', or 'standard'. Empty string if not specified."
                    },
                    "style": {
                        "type": "string",
                        "description": "Style preference: 'vivid', 'natural', 'realistic', 'artistic'. Empty string if not specified."
                    }
                },
                "required": ["prompt"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "web_search",
            "description": "Search the web for current/real-time information. Use for time-sensitive queries, current events, news, weather, stock prices, etc.",
            "parameters": {
                "type": "object",
                "properties": {
                    "query": {
                        "type": "string",
                        "description": "The search query"
                    }
                },
                "required": ["query"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "calculate",
            "description": "Evaluate a mathematical expression. Use for arithmetic, percentages, square roots, powers, etc.",
            "parameters": {
                "type": "object",
                "properties": {
                    "expression": {
                        "type": "string",
                        "description": "The mathematical expression to evaluate (e.g., '15% of 250', '45 * 89', 'sqrt(144)', '2^8')"
                    }
                },
                "required": ["expression"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "translate",
            "description": "Translate text between languages. Use when the user wants to translate specific text.",
            "parameters": {
                "type": "object",
                "properties": {
                    "text": {
                        "type": "string",
                        "description": "The text to translate"
                    },
                    "source_language": {
                        "type": "string",
                        "description": "Source language (empty string if unknown, for auto-detection)"
                    },
                    "target_language": {
                        "type": "string",
                        "description": "Target language to translate to"
                    }
                },
                "required": ["text", "target_language"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "define",
            "description": "Look up a factual definition or explanation of a term. Use for timeless knowledge, general concepts, people, etc.",
            "parameters": {
                "type": "object",
                "properties": {
                    "term": {
                        "type": "string",
                        "description": "The term or concept to define"
                    },
                    "depth": {
                        "type": "string",
                        "enum": ["brief", "detailed"],
                        "description": "How detailed the definition should be"
                    }
                },
                "required": ["term"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "create_poll",
            "description": "Create a poll or vote in Discord. Use when the user wants to create a poll with a question and options.",
            "parameters": {
                "type": "object",
                "properties": {
                    "question": {
                        "type": "string",
                        "description": "The poll question"
                    },
                    "options": {
                        "type": "array",
                        "items": {"type": "string"},
                        "description": "List of poll options (2-10 options)"
                    },
                    "duration": {
                        "type": "integer",
                        "description": "Poll duration in hours (default: 24)"
                    }
                },
                "required": ["question", "options"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "convert_timezone",
            "description": "Convert a time from one timezone to another. Use when the user wants to know what time something is in a different timezone.",
            "parameters": {
                "type": "object",
                "properties": {
                    "time": {
                        "type": "string",
                        "description": "The time to convert (e.g., '3pm', '14:00')"
                    },
                    "source_timezone": {
                        "type": "string",
                        "description": "Source timezone (e.g., 'EST', 'UTC', 'Tokyo')"
                    },
                    "target_timezone": {
                        "type": "string",
                        "description": "Target timezone (e.g., 'PST', 'London', 'Tokyo')"
                    }
                },
                "required": ["time", "source_timezone", "target_timezone"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "convert_units",
            "description": "Convert between units (distance, temperature, currency, etc.). Use when the user wants to convert a value from one unit to another.",
            "parameters": {
                "type": "object",
                "properties": {
                    "value": {
                        "type": "number",
                        "description": "The numeric value to convert"
                    },
                    "source_unit": {
                        "type": "string",
                        "description": "Source unit (e.g., 'miles', 'F', 'USD')"
                    },
                    "target_unit": {
                        "type": "string",
                        "description": "Target unit (e.g., 'km', 'celsius', 'EUR')"
                    },
                    "category": {
                        "type": "string",
                        "description": "Unit category hint: 'distance', 'temperature', 'currency', etc."
                    }
                },
                "required": ["value", "source_unit", "target_unit"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "roll_dice",
            "description": "Roll dice, flip coins, pick random options, or generate random numbers. Use for any random selection or dice rolling request.",
            "parameters": {
                "type": "object",
                "properties": {
                    "dice_notation": {
                        "type": "string",
                        "description": "Standard dice notation (e.g., '2d20', '1d6'). Empty string if not applicable."
                    },
                    "options": {
                        "type": "array",
                        "items": {"type": "string"},
                        "description": "List of options to choose from (for 'pick one' scenarios). Empty array if not applicable."
                    },
                    "range_min": {
                        "type": "integer",
                        "description": "Minimum value for random number generation (null if not applicable)"
                    },
                    "range_max": {
                        "type": "integer",
                        "description": "Maximum value for random number generation (null if not applicable)"
                    }
                },
                "required": []
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "schedule_event",
            "description": "Create a scheduled Discord event. Use when the user wants to schedule or create an event with a specific time.",
            "parameters": {
                "type": "object",
                "properties": {
                    "event_name": {
                        "type": "string",
                        "description": "Name of the event (e.g., 'movie night', 'gaming', 'team meeting')"
                    },
                    "date_time": {
                        "type": "string",
                        "description": "When the event occurs, as a natural language expression (e.g., 'Friday 8pm', 'tomorrow at 2pm')"
                    },
                    "duration": {
                        "type": "integer",
                        "description": "Event duration in minutes (default: 60)"
                    },
                    "description": {
                        "type": "string",
                        "description": "Event details or description (optional)"
                    }
                },
                "required": ["event_name", "date_time"]
            }
        }
    }
]


# ─── Tool Execution ─────────────────────────────────────────────────────────

async def execute_tool(
    tool_name: str,
    arguments: Dict[str, Any],
    context: Dict[str, Any]
) -> str:
    """
    Execute a tool by name with the given arguments.

    Args:
        tool_name: Name of the tool to execute
        arguments: Parsed JSON arguments from the LLM
        context: Dictionary containing:
            - bot: Discord bot instance
            - state: BotStateManager instance
            - message: Discord message object
            - channel_id: Channel ID as string
            - clients: Dict of provider clients

    Returns:
        String result to feed back to the LLM as the tool response
    """
    logger.info(f"[Tool] Executing tool '{tool_name}' with args: {arguments}")

    try:
        if tool_name == "set_reminder":
            return await _execute_set_reminder(arguments, context)
        elif tool_name == "generate_image":
            return await _execute_generate_image(arguments, context)
        elif tool_name == "web_search":
            return await _execute_web_search(arguments, context)
        elif tool_name == "calculate":
            return await _execute_calculate(arguments, context)
        elif tool_name == "translate":
            return await _execute_translate(arguments, context)
        elif tool_name == "define":
            return await _execute_define(arguments, context)
        elif tool_name == "create_poll":
            return await _execute_create_poll(arguments, context)
        elif tool_name == "convert_timezone":
            return await _execute_convert_timezone(arguments, context)
        elif tool_name == "convert_units":
            return await _execute_convert_units(arguments, context)
        elif tool_name == "roll_dice":
            return await _execute_roll_dice(arguments, context)
        elif tool_name == "schedule_event":
            return await _execute_schedule_event(arguments, context)
        else:
            return f"Error: Unknown tool '{tool_name}'"

    except Exception as e:
        logger.exception(f"[Tool] Error executing tool '{tool_name}': {e}")
        return f"Error executing tool '{tool_name}': {str(e)}"


def get_tool_definitions() -> List[Dict[str, Any]]:
    """Return the list of tool definitions for the LLM API."""
    return TOOL_DEFINITIONS


def get_tool_names() -> List[str]:
    """Return a list of all registered tool names."""
    return [t["function"]["name"] for t in TOOL_DEFINITIONS]


# ─── Tool Implementations ───────────────────────────────────────────────────
# These wrap the existing handler modules, adapting them to the tool-calling
# interface. Each returns a string result for the LLM.

async def _execute_set_reminder(args: Dict[str, Any], ctx: Dict[str, Any]) -> str:
    """Execute the set_reminder tool using the inline reminder handler."""
    from ..cogs.mention_commands import MentionCommands
    
    # Create a lightweight adapter that mimics the cog interface
    adapter = _CogAdapter(ctx)
    
    # Import the handler inline to avoid circular imports
    # The reminder handler is an inline method on MentionCommands, so we
    # call it through a wrapper
    message = ctx["message"]
    channel_id = ctx["channel_id"]
    
    reminder_message = args.get("reminder_message", "")
    time_expression = args.get("time_expression", "")
    
    # Use the existing handle_reminder_request logic via the cog
    cog = ctx.get("cog")
    if cog and hasattr(cog, "handle_reminder_request"):
        await cog.handle_reminder_request(
            message, channel_id,
            reminder_message, time_expression
        )
        return f"Reminder set successfully: '{reminder_message}' at '{time_expression}'"
    else:
        return "Error: Reminder handler not available"


async def _execute_generate_image(args: Dict[str, Any], ctx: Dict[str, Any]) -> str:
    """Execute the generate_image tool using the inline image handler."""
    message = ctx["message"]
    channel_id = ctx["channel_id"]
    
    prompt = args.get("prompt", "")
    negative_prompt = args.get("negative_prompt", "")
    size = args.get("size", "")
    quality = args.get("quality", "")
    style = args.get("style", "")
    
    cog = ctx.get("cog")
    if cog and hasattr(cog, "handle_image_generation_request"):
        await cog.handle_image_generation_request(
            message, channel_id,
            prompt, negative_prompt, size, quality, style
        )
        return f"Image generation completed for prompt: '{prompt}'"
    else:
        return "Error: Image generation handler not available"


async def _execute_web_search(args: Dict[str, Any], ctx: Dict[str, Any]) -> str:
    """Execute the web_search tool using the inline search handler."""
    message = ctx["message"]
    channel_id = ctx["channel_id"]
    query = args.get("query", "")
    
    cog = ctx.get("cog")
    if cog and hasattr(cog, "handle_search_request"):
        await cog.handle_search_request(message, channel_id, query)
        return f"Web search completed for query: '{query}'"
    else:
        return "Error: Search handler not available"


async def _execute_calculate(args: Dict[str, Any], ctx: Dict[str, Any]) -> str:
    """Execute the calculate tool using the calculation handler module."""
    from .intent_handlers.calculation import handle_calculation
    
    adapter = _CogAdapter(ctx)
    message = ctx["message"]
    channel_id = ctx["channel_id"]
    expression = args.get("expression", "")
    
    await handle_calculation(adapter, message, channel_id, expression)
    return f"Calculation completed for expression: '{expression}'"


async def _execute_translate(args: Dict[str, Any], ctx: Dict[str, Any]) -> str:
    """Execute the translate tool using the translation handler module."""
    from .intent_handlers.translation import handle_translation
    
    adapter = _CogAdapter(ctx)
    message = ctx["message"]
    channel_id = ctx["channel_id"]
    text = args.get("text", "")
    source_language = args.get("source_language", "")
    target_language = args.get("target_language", "")
    
    await handle_translation(adapter, message, channel_id, text, source_language, target_language)
    return f"Translation completed: '{text}' to {target_language}"


async def _execute_define(args: Dict[str, Any], ctx: Dict[str, Any]) -> str:
    """Execute the define tool using the definition handler module."""
    from .intent_handlers.definition import handle_definition
    
    adapter = _CogAdapter(ctx)
    message = ctx["message"]
    channel_id = ctx["channel_id"]
    term = args.get("term", "")
    depth = args.get("depth", "brief")
    
    await handle_definition(adapter, message, channel_id, term, depth)
    return f"Definition completed for term: '{term}'"


async def _execute_create_poll(args: Dict[str, Any], ctx: Dict[str, Any]) -> str:
    """Execute the create_poll tool using the poll handler module."""
    from .intent_handlers.poll import handle_poll_creation
    
    adapter = _CogAdapter(ctx)
    message = ctx["message"]
    channel_id = ctx["channel_id"]
    question = args.get("question", "")
    options = args.get("options", [])
    duration = args.get("duration", 24)
    
    await handle_poll_creation(adapter, message, channel_id, question, options, duration)
    return f"Poll created: '{question}' with {len(options)} options"


async def _execute_convert_timezone(args: Dict[str, Any], ctx: Dict[str, Any]) -> str:
    """Execute the convert_timezone tool using the timezone handler module."""
    from .intent_handlers.timezone import handle_timezone_conversion
    
    adapter = _CogAdapter(ctx)
    message = ctx["message"]
    channel_id = ctx["channel_id"]
    time = args.get("time", "")
    source_timezone = args.get("source_timezone", "")
    target_timezone = args.get("target_timezone", "")
    
    await handle_timezone_conversion(adapter, message, channel_id, time, source_timezone, target_timezone)
    return f"Timezone conversion completed: {time} {source_timezone} → {target_timezone}"


async def _execute_convert_units(args: Dict[str, Any], ctx: Dict[str, Any]) -> str:
    """Execute the convert_units tool using the unit conversion handler module."""
    from .intent_handlers.unit_conversion import handle_unit_conversion
    
    adapter = _CogAdapter(ctx)
    message = ctx["message"]
    channel_id = ctx["channel_id"]
    value = args.get("value", "")
    source_unit = args.get("source_unit", "")
    target_unit = args.get("target_unit", "")
    category = args.get("category", "")
    
    await handle_unit_conversion(adapter, message, channel_id, value, source_unit, target_unit, category)
    return f"Unit conversion completed: {value} {source_unit} → {target_unit}"


async def _execute_roll_dice(args: Dict[str, Any], ctx: Dict[str, Any]) -> str:
    """Execute the roll_dice tool using the dice handler module."""
    from .intent_handlers.dice import handle_dice_roll
    
    adapter = _CogAdapter(ctx)
    message = ctx["message"]
    channel_id = ctx["channel_id"]
    dice_notation = args.get("dice_notation", "")
    options = args.get("options", [])
    range_min = args.get("range_min")
    range_max = args.get("range_max")
    
    await handle_dice_roll(adapter, message, channel_id, dice_notation, options, range_min, range_max)
    return f"Dice roll completed: {dice_notation or 'random selection'}"


async def _execute_schedule_event(args: Dict[str, Any], ctx: Dict[str, Any]) -> str:
    """Execute the schedule_event tool using the event handler module."""
    from .intent_handlers.event import handle_event_scheduling
    
    adapter = _CogAdapter(ctx)
    message = ctx["message"]
    channel_id = ctx["channel_id"]
    event_name = args.get("event_name", "")
    date_time = args.get("date_time", "")
    duration = args.get("duration", 60)
    description = args.get("description", "")
    
    await handle_event_scheduling(adapter, message, channel_id, event_name, date_time, duration, description)
    return f"Event scheduled: '{event_name}' at {date_time}"


# ─── Compatibility Adapter ──────────────────────────────────────────────────

class _CogAdapter:
    """
    Lightweight adapter that mimics the MentionCommands cog interface.
    
    The existing intent handler modules expect a `cog` object with:
    - cog.get_model_for_channel(channel_id)
    - cog.state (BotStateManager)
    - cog.bot (Discord bot)
    - cog.clients (dict of provider clients)
    
    This adapter provides those attributes from the tool context dict.
    """

    def __init__(self, ctx: Dict[str, Any]):
        self.bot = ctx.get("bot")
        self.state = ctx.get("state")
        self.clients = ctx.get("clients", {})
        self._cog = ctx.get("cog")

    def get_model_for_channel(self, channel_id):
        """Get the appropriate model for this channel."""
        if self._cog and hasattr(self._cog, "get_model_for_channel"):
            return self._cog.get_model_for_channel(channel_id)
        if self.state:
            return self.state.get_effective_model(channel_id)
        from ..config import DEFAULT_MODEL
        return DEFAULT_MODEL