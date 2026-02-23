def rp_cost_for_level(level):
    """Return RP cost required to unlock the given level (1-indexed)."""
    if level <= 0:
        return 0
    if level == 1:
        return 50
    if level == 2:
        return 80
    prev = 80
    prev_prev = 50
    idx = 3
    while idx <= level:
        current = prev + prev_prev
        prev_prev = prev
        prev = current
        idx += 1
    return prev


def clamp_percent(value):
    """Clamp an allocation percentage to [0, 100]."""
    if value < 0:
        return 0.0
    if value > 100:
        return 100.0
    return float(value)


def normalise_percentages(values):
    """Normalise percentages safely to sum to 100."""
    if not values:
        return []
    cleaned = [clamp_percent(v) for v in values]
    total = sum(cleaned)
    if total <= 0:
        equal = 100.0 / float(len(cleaned))
        return [equal for _ in cleaned]
    return [(v * 100.0) / total for v in cleaned]
