"""Handler for dice rolling and random selection intent."""

import logging
import random
import re
from datetime import datetime
import discord

logger = logging.getLogger('dice_handler')


async def handle_dice_roll(cog, message, channel_id, dice_notation, options, range_min, range_max):
    """
    Handle dice rolling, coin flips, and random selection requests.

    Args:
        cog: The MentionCommands cog instance
        message: Discord message object
        channel_id: Channel ID as string
        dice_notation: Dice notation (e.g., "2d20", "1d6")
        options: List of options to choose from (for "pick one")
        range_min: Minimum value for random number
        range_max: Maximum value for random number
    """
    try:
        # Handle "pick one" from options
        if options and len(options) > 0:
            chosen = random.choice(options)
            response = f"🎯 I choose: **{chosen}**"
            await message.channel.send(response)

            # Add to conversation history
            await cog.state.add_to_channel_history(channel_id, {
                "role": "assistant",
                "content": f"Randomly chose '{chosen}' from {options}",
                "timestamp": datetime.now()
            })

            logger.info(f"[Dice] User {message.author.id} picked one from {len(options)} options: {chosen}")
            return

        # Handle random number in range
        if range_min is not None and range_max is not None:
            try:
                min_val = int(range_min)
                max_val = int(range_max)

                if min_val >= max_val:
                    await message.channel.send("❌ The minimum value must be less than the maximum value.")
                    return

                result = random.randint(min_val, max_val)
                response = f"🎲 Random number between {min_val} and {max_val}: **{result}**"
                await message.channel.send(response)

                # Add to conversation history
                await cog.state.add_to_channel_history(channel_id, {
                    "role": "assistant",
                    "content": f"Generated random number: {result} (between {min_val}-{max_val})",
                    "timestamp": datetime.now()
                })

                logger.info(f"[Dice] User {message.author.id} rolled random {min_val}-{max_val}: {result}")
                return

            except (ValueError, TypeError):
                await message.channel.send("❌ Invalid range values. Please use integers.")
                return

        # Handle dice notation (e.g., "2d20", "1d6+5")
        if dice_notation and dice_notation.strip():
            # Parse dice notation: XdY+Z or XdY-Z
            dice_pattern = r'(\d+)d(\d+)(([+\-])(\d+))?'
            match = re.match(dice_pattern, dice_notation.lower().replace(' ', ''))

            if not match:
                await message.channel.send(
                    "❌ Invalid dice notation. Use format like '2d20', '1d6', or '3d10+5'"
                )
                return

            num_dice = int(match.group(1))
            num_sides = int(match.group(2))
            modifier_sign = match.group(4)  # '+' or '-' or None
            modifier_value = int(match.group(5)) if match.group(5) else 0

            # Validate reasonable values
            if num_dice < 1 or num_dice > 100:
                await message.channel.send("❌ Number of dice must be between 1 and 100.")
                return

            if num_sides < 2 or num_sides > 1000:
                await message.channel.send("❌ Number of sides must be between 2 and 1000.")
                return

            # Roll the dice
            rolls = [random.randint(1, num_sides) for _ in range(num_dice)]
            total = sum(rolls)

            # Apply modifier
            if modifier_sign == '+':
                total += modifier_value
                modifier_str = f"+{modifier_value}"
            elif modifier_sign == '-':
                total -= modifier_value
                modifier_str = f"-{modifier_value}"
            else:
                modifier_str = ""

            # Format response
            if num_dice == 1:
                # Single die: just show result
                if modifier_str:
                    response = f"🎲 Rolled {dice_notation}: **{rolls[0]}** {modifier_str} = **{total}**"
                else:
                    response = f"🎲 Rolled {dice_notation}: **{total}**"
            else:
                # Multiple dice: show individual rolls and total
                rolls_str = ', '.join(map(str, rolls))
                if modifier_str:
                    response = f"🎲 Rolled {dice_notation}: [{rolls_str}] {modifier_str} = **{total}**"
                else:
                    response = f"🎲 Rolled {dice_notation}: [{rolls_str}] = **{total}**"

            await message.channel.send(response)

            # Add to conversation history
            await cog.state.add_to_channel_history(channel_id, {
                "role": "assistant",
                "content": f"Rolled {dice_notation}: {total}",
                "timestamp": datetime.now()
            })

            logger.info(f"[Dice] User {message.author.id} rolled {dice_notation}: {total}")
            return

        # No valid input provided
        await message.channel.send(
            "❌ I need dice notation (like '2d20'), options to pick from, or a number range.\n"
            "Examples:\n"
            "- '@Gideon roll 2d20'\n"
            "- '@Gideon flip a coin'\n"
            "- '@Gideon pick one: pizza, tacos, burgers'\n"
            "- '@Gideon random number between 1 and 100'"
        )
        logger.warning(f"[Dice] Missing valid input for user {message.author.id}")

    except Exception as e:
        logger.exception(f"[Dice] Error for user {message.author.id}: {e}")
        await message.channel.send(f"❌ Dice roll failed: {str(e)}")
