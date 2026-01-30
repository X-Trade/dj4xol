from django import template

register = template.Library()


def human_number(value, show_sign=False):
    """Convert a number to human-friendly format.

    Examples:
        100000 -> "100k"
        127000 -> "127k"
        127900 -> "~128k"
        1234567890 -> "~1bn"
        2501000000 -> "~3bn"

    Args:
        value: The number to format
        show_sign: If True, prefix positive numbers with +
    """
    if value is None:
        return ""

    try:
        value = int(value)
    except (ValueError, TypeError):
        return str(value)

    sign = ""
    if show_sign and value > 0:
        sign = "+"
    elif value < 0:
        sign = "-"
        value = abs(value)

    if value == 0:
        return "0"

    # Define thresholds and suffixes
    thresholds = [
        (1_000_000_000_000, "tn"),  # trillion
        (1_000_000_000, "bn"),       # billion
        (1_000_000, "m"),            # million
        (1_000, "k"),                # thousand
    ]

    for threshold, suffix in thresholds:
        if value >= threshold:
            divided = value / threshold
            rounded = round(divided)
            # Check if we need approximation indicator
            if abs(divided - rounded) > 0.05:
                return f"~{sign}{rounded}{suffix}"
            else:
                # Format without decimals if it's exact-ish
                if divided == int(divided):
                    return f"{sign}{int(divided)}{suffix}"
                else:
                    return f"~{sign}{rounded}{suffix}"

    # Less than 1000, just return with commas
    return f"{sign}{value:,}"


def exact_number(value):
    """Format a number with commas for tooltip display."""
    if value is None:
        return ""
    try:
        return f"{int(value):,}"
    except (ValueError, TypeError):
        return str(value)


@register.filter
def humanize_pop(value):
    """Template filter for population display."""
    return human_number(value)


@register.filter
def humanize_pop_change(value):
    """Template filter for population change with +/- sign."""
    return human_number(value, show_sign=True)


@register.filter
def exact_pop(value):
    """Template filter for exact population (for tooltips)."""
    return exact_number(value)
