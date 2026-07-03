"""Tool implementation modules for native LLM tool calling.

Pure tools expose compute functions that return data for the model;
side-effect tools (polls, events) expose handlers that post to Discord.
"""

from .calculation import evaluate_expression
from .translation import translate_text
from .definition import define_term
from .poll import handle_poll_creation
from .timezone import convert_time
from .unit_conversion import convert_units
from .dice import roll
from .event import handle_event_scheduling

__all__ = [
    'evaluate_expression',
    'translate_text',
    'define_term',
    'handle_poll_creation',
    'convert_time',
    'convert_units',
    'roll',
    'handle_event_scheduling',
]
