"""Safe mathematical expression evaluation (calculate tool)."""

import logging
from sympy import N
from sympy.parsing.sympy_parser import (
    parse_expr,
    standard_transformations,
    implicit_multiplication_application,
    convert_xor
)

logger = logging.getLogger('calculation_handler')

_TRANSFORMATIONS = (
    standard_transformations +
    (implicit_multiplication_application, convert_xor)
)


def evaluate_expression(expression: str) -> str:
    """Evaluates a natural-language math expression and returns the result.

    Raises ValueError with a user-facing explanation on failure.
    """
    if not expression or not expression.strip():
        raise ValueError("No mathematical expression provided.")

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

    # Handle "X squared" / "X cubed"
    if 'squared' in expr_str.lower():
        expr_str = expr_str.lower().replace('squared', '**2')
    if 'cubed' in expr_str.lower():
        expr_str = expr_str.lower().replace('cubed', '**3')

    # Handle "square root of X" → "sqrt(X)"
    if 'square root of' in expr_str.lower():
        expr_str = expr_str.lower().replace('square root of', 'sqrt')
    elif 'sqrt of' in expr_str.lower():
        expr_str = expr_str.lower().replace('sqrt of', 'sqrt')

    try:
        parsed_expr = parse_expr(expr_str, transformations=_TRANSFORMATIONS)
        result = N(parsed_expr, 15)  # 15 significant figures
        result_float = float(result)
    except Exception as e:
        logger.warning(f"[Calculation] Failed to evaluate '{expression}': {e}")
        if "unexpected" in str(e).lower() or "syntax" in str(e).lower():
            raise ValueError("The mathematical expression seems malformed.") from e
        raise ValueError(f"Could not evaluate the expression: {e}") from e

    # Round to reasonable precision (avoid floating point noise)
    if abs(result_float) < 1e-10:
        formatted_result = "0"
    elif result_float == int(result_float):
        formatted_result = str(int(result_float))
    else:
        formatted_result = f"{result_float:.10f}".rstrip('0').rstrip('.')

    return f"{expression} = {formatted_result}"
