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
    """Normalise percentages safely to sum to 100.

    Invalid, negative, and overflow values are clamped before scaling.
    If all values are zero, equal distribution is used.
    """
    if not values:
        return []
    cleaned = [clamp_percent(v) for v in values]
    total = sum(cleaned)
    if total <= 0:
        equal = 100.0 / float(len(cleaned))
        return [equal for _ in cleaned]
    return [(v * 100.0) / total for v in cleaned]


def allocate_rp(total_rp, percentages):
    """Allocate RP by normalised percentages."""
    if not percentages:
        return []
    norm = normalise_percentages(percentages)
    allocations = []
    for pct in norm:
        allocations.append(total_rp * pct / 100.0)
    return allocations


def allocate_rp_integer(total_rp, percentages):
    """Allocate integer RP by percentages, preserving total."""
    if not percentages:
        return []
    norm = normalise_percentages(percentages)
    raw = []
    floors = []
    for pct in norm:
        value = (float(total_rp) * pct) / 100.0
        raw.append(value)
        floors.append(int(value))
    remainder = int(total_rp) - sum(floors)
    ranked = sorted(
        range(len(raw)),
        key=lambda idx: (raw[idx] - floors[idx]),
        reverse=True
    )
    for idx in ranked:
        if remainder <= 0:
            break
        floors[idx] += 1
        remainder -= 1
    return floors


def resolve_level_progress(current_level, stored_rp, max_available_level):
    """Advance levels while stored RP covers next level costs."""
    level = float(current_level or 0.0)
    rp = float(stored_rp or 0.0)
    max_level = int(max_available_level or 0)
    while int(level) < max_level:
        next_level = int(level) + 1
        cost = float(rp_cost_for_level(next_level))
        if rp < cost:
            break
        rp -= cost
        level += 1.0
    return level, rp
