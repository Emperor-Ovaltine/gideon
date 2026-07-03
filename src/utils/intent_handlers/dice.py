"""Dice rolling and random selection (roll_dice tool)."""

import logging
import random
import re

logger = logging.getLogger('dice_handler')

_DICE_PATTERN = re.compile(r'(\d+)d(\d+)(([+\-])(\d+))?')


def roll(dice_notation="", options=None, range_min=None, range_max=None) -> str:
    """Rolls dice, picks from options, or generates a random number.

    Returns a human-readable result string. Raises ValueError on bad input.
    """
    # "Pick one" from options
    if options:
        chosen = random.choice(options)
        return f"Randomly chose '{chosen}' from {len(options)} options: {', '.join(options)}"

    # Random number in range
    if range_min is not None and range_max is not None:
        try:
            min_val = int(range_min)
            max_val = int(range_max)
        except (ValueError, TypeError):
            raise ValueError("Range values must be integers.")
        if min_val >= max_val:
            raise ValueError("The minimum value must be less than the maximum value.")
        result = random.randint(min_val, max_val)
        return f"Random number between {min_val} and {max_val}: {result}"

    # Dice notation (e.g. "2d20", "3d10+5")
    if dice_notation and dice_notation.strip():
        match = _DICE_PATTERN.match(dice_notation.lower().replace(' ', ''))
        if not match:
            raise ValueError("Invalid dice notation. Use a format like '2d20', '1d6', or '3d10+5'.")

        num_dice = int(match.group(1))
        num_sides = int(match.group(2))
        modifier_sign = match.group(4)
        modifier_value = int(match.group(5)) if match.group(5) else 0

        if num_dice < 1 or num_dice > 100:
            raise ValueError("Number of dice must be between 1 and 100.")
        if num_sides < 2 or num_sides > 1000:
            raise ValueError("Number of sides must be between 2 and 1000.")

        rolls = [random.randint(1, num_sides) for _ in range(num_dice)]
        total = sum(rolls)
        if modifier_sign == '+':
            total += modifier_value
        elif modifier_sign == '-':
            total -= modifier_value

        rolls_str = ', '.join(map(str, rolls))
        modifier_str = f" {modifier_sign}{modifier_value}" if modifier_sign else ""
        return f"Rolled {dice_notation}: [{rolls_str}]{modifier_str} = {total}"

    raise ValueError(
        "Need dice notation (like '2d20'), options to pick from, or a number range."
    )
