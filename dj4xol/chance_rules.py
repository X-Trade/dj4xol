import random


def clamp_probability(value):
    """Clamp a probability to the inclusive range 0..1."""
    try:
        chance = float(value)
    except (TypeError, ValueError):
        chance = 0.0
    return max(0.0, min(1.0, chance))


def normalize_luck(value, minimum=0.1):
    """Normalize luck values used for weighted chance calculations."""
    try:
        luck = float(value)
    except (TypeError, ValueError):
        luck = 1.0
    return max(float(minimum), luck)


def roll_chance(probability, rng=None):
    """Return True when a random roll falls under the given probability."""
    if rng is None:
        rng = random.random
    return rng() < clamp_probability(probability)


def apply_roll_bend(unit_value, bend=0.0):
    """Apply a curve transform to a 0..1 roll.

    bend = 0: linear (x)
    bend > 0: biases higher values using 1 - (1 - x)^(1 + bend)
    bend < 0: biases lower values using x^(1 + |bend|)

    Examples:
      bend=1  -> 1 - (1 - x)^2
      bend=-1 -> x^2
    """
    x = clamp_probability(unit_value)
    try:
        b = float(bend)
    except (TypeError, ValueError):
        b = 0.0
    if b == 0.0:
        return x
    exponent = 1.0 + abs(b)
    if b > 0:
        return 1.0 - ((1.0 - x) ** exponent)
    return x ** exponent


def luck_biased_unit_roll(luck_multiplier, bend=0.0, rng=None):
    """Return a 0..1 roll skewed by luck.

    luck > 1 biases toward higher values, luck < 1 biases lower values.
    """
    if rng is None:
        rng = random.random
    luck = normalize_luck(luck_multiplier)
    base = rng()
    luck_biased = 1.0 - ((1.0 - base) ** luck)
    return apply_roll_bend(luck_biased, bend=bend)


def scaled_luck_roll(luck_multiplier, min_scale=0.0, max_scale=1.0, bend=0.0, rng=None):
    """Return a luck-biased roll scaled to [min_scale, max_scale]."""
    low = float(min_scale)
    high = float(max_scale)
    if high < low:
        low, high = high, low
    if high == low:
        return low
    biased = luck_biased_unit_roll(luck_multiplier, bend=bend, rng=rng)
    return low + ((high - low) * biased)


def luck_ratio_chance(base_chance, source_luck, target_luck,
                      min_chance=0.0, max_chance=1.0):
    """Scale base chance by source/target luck ratio and clamp to bounds."""
    source = normalize_luck(source_luck)
    target = normalize_luck(target_luck)
    chance = float(base_chance) * (source / target)
    low = clamp_probability(min_chance)
    high = clamp_probability(max_chance)
    if high < low:
        low, high = high, low
    return max(low, min(high, chance))
