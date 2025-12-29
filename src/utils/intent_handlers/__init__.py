"""Intent handler modules for natural interaction via @mentions."""

from .calculation import handle_calculation
from .translation import handle_translation
from .definition import handle_definition
from .poll import handle_poll_creation
from .timezone import handle_timezone_conversion
from .unit_conversion import handle_unit_conversion
from .dice import handle_dice_roll
from .event import handle_event_scheduling

__all__ = [
    'handle_calculation',
    'handle_translation',
    'handle_definition',
    'handle_poll_creation',
    'handle_timezone_conversion',
    'handle_unit_conversion',
    'handle_dice_roll',
    'handle_event_scheduling',
]
