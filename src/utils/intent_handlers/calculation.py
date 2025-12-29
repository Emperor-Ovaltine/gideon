"""Handler for mathematical calculation intent."""

import logging
from datetime import datetime
from sympy import sympify, N
from sympy.parsing.sympy_parser import (
    parse_expr,
    standard_transformations,
    implicit_multiplication_application,
    convert_xor
)

logger = logging.getLogger('calculation_handler')


async def handle_calculation(cog, message, channel_id, expression):
    """
    Handle mathematical calculation requests.

    Args:
        cog: The MentionCommands cog instance
        message: Discord message object
        channel_id: Channel ID as string
        expression: Mathematical expression to evaluate
    """
    # Validate expression
    if not expression or not expression.strip():
        await message.channel.send(
            "❌ I need a mathematical expression to calculate. "
            "Try something like: '@Gideon what's 15% of 250?'"
        )
        logger.warning(f"[Calculation] Missing expression for user {message.author.id}")
        return

    try:
        # Preprocess the expression to handle common patterns
        expr_str = expression.strip()

        # Handle percentage calculations
        if '%' in expr_str and 'of' in expr_str.lower():
            # "15% of 250" → "(15/100) * 250"
            parts = expr_str.lower().split('of')
            if len(parts) == 2:
                percent_part = parts[0].replace('%', '').strip()
                number_part = parts[1].strip()
                expr_str = f"({percent_part}/100) * {number_part}"
        elif '%' in expr_str:
            # "15%" → "15/100"
            expr_str = expr_str.replace('%', '/100')

        # Handle "X squared" → "X**2"
        if 'squared' in expr_str.lower():
            expr_str = expr_str.lower().replace('squared', '**2')

        # Handle "square root of X" → "sqrt(X)"
        if 'square root of' in expr_str.lower():
            expr_str = expr_str.lower().replace('square root of', 'sqrt')
        elif 'sqrt of' in expr_str.lower():
            expr_str = expr_str.lower().replace('sqrt of', 'sqrt')

        # Handle "X cubed" → "X**3"
        if 'cubed' in expr_str.lower():
            expr_str = expr_str.lower().replace('cubed', '**3')

        # Parse and evaluate using sympy (safe)
        transformations = (
            standard_transformations +
            (implicit_multiplication_application, convert_xor)
        )

        # Parse the expression
        parsed_expr = parse_expr(expr_str, transformations=transformations)

        # Evaluate numerically
        result = N(parsed_expr, 15)  # 15 significant figures

        # Format result nicely
        result_float = float(result)

        # Round to reasonable precision (avoid floating point noise)
        if abs(result_float) < 1e-10:
            formatted_result = "0"
        elif result_float == int(result_float):
            formatted_result = str(int(result_float))
        else:
            # Remove trailing zeros
            formatted_result = f"{result_float:.10f}".rstrip('0').rstrip('.')

        # Send response
        response_message = f"**Calculation:** `{expression}`\n**Result:** `{formatted_result}`"
        await message.channel.send(response_message)

        # Add to conversation history
        await cog.state.add_to_channel_history(channel_id, {
            "role": "assistant",
            "content": f"Calculated {expression} = {formatted_result}",
            "timestamp": datetime.now()
        })

        logger.info(f"[Calculation] User {message.author.id} calculated: {expression} = {formatted_result}")

    except Exception as e:
        # Handle calculation errors
        error_message = f"❌ I couldn't calculate that expression. "

        if "unexpected" in str(e).lower() or "syntax" in str(e).lower():
            error_message += "The mathematical expression seems malformed. Please check the syntax."
        elif "undefined" in str(e).lower() or "division" in str(e).lower():
            error_message += "The calculation resulted in an undefined value (division by zero?)."
        else:
            error_message += f"Error: {str(e)}"

        await message.channel.send(error_message)
        logger.error(f"[Calculation] Error for user {message.author.id}: {e}", exc_info=True)
