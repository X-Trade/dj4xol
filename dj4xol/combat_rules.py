from math import ceil, log2, sqrt


COUNT_LINEAR_LIMIT = 3.0
COUNT_SQRT_OFFSET = 1.0
COUNT_SQRT_SCALE = 4.0


def normalize_ship_count(ship_count):
    """Return softened effective ship count.

    Small engagements stay intuitive: counts up to 3 remain linear.
    Beyond that, growth transitions into a square-root curve so large
    stacks stay stronger without exploding linearly forever.
    """
    try:
        n = float(ship_count or 0.0)
    except (TypeError, ValueError):
        n = 0.0
    if n <= 0.0:
        return 0.0
    if n <= COUNT_LINEAR_LIMIT:
        return n
    return COUNT_LINEAR_LIMIT + (
        COUNT_SQRT_SCALE * (sqrt(n + COUNT_SQRT_OFFSET) - sqrt(COUNT_LINEAR_LIMIT + COUNT_SQRT_OFFSET))
    )


def denormalize_ship_count(effective_count):
    """Invert ``normalize_ship_count`` for values produced by that curve."""
    try:
        value = float(effective_count or 0.0)
    except (TypeError, ValueError):
        value = 0.0
    if value <= 0.0:
        return 0.0
    if value <= COUNT_LINEAR_LIMIT:
        return value
    root_term = (
        (value - COUNT_LINEAR_LIMIT) / COUNT_SQRT_SCALE
    ) + sqrt(COUNT_LINEAR_LIMIT + COUNT_SQRT_OFFSET)
    return max(0.0, (root_term ** 2) - COUNT_SQRT_OFFSET)


def tech_level_to_multiplier(level):
    """Convert log2 tech level to linear multiplier."""
    try:
        value = float(level)
    except (TypeError, ValueError):
        value = 0.0
    return 2.0 ** max(0.0, value)


def multiplier_to_tech_level(multiplier):
    """Convert linear multiplier back to log2 tech level."""
    try:
        value = float(multiplier)
    except (TypeError, ValueError):
        value = 1.0
    return max(0.0, log2(max(1.0, value)))


def integrity_factor(integrity):
    """Convert 0-100 integrity into a smooth combat effectiveness factor."""
    try:
        integrity_norm = max(0.0, min(1.0, float(integrity) / 100.0))
    except (TypeError, ValueError):
        integrity_norm = 0.0
    return (2.0 * integrity_norm) - (integrity_norm ** 2)


def clamp_integrity(integrity):
    """Clamp displayed integrity into the 0-100 range."""
    try:
        value = float(integrity)
    except (TypeError, ValueError):
        value = 0.0
    return max(0.0, min(100.0, value))


def calculate_display_integrity_total(ship_count, integrity):
    """Return total displayed integrity across all ships in a fleet."""
    try:
        ships = max(0, int(ship_count or 0))
    except (TypeError, ValueError):
        ships = 0
    return float(ships) * clamp_integrity(integrity)


def calculate_fleet_durability_pool(ship_count, defense_multiplier=1.0, integrity=100.0):
    """Return the current defended integrity pool for a fleet."""
    try:
        defense = max(0.001, float(defense_multiplier or 0.0))
    except (TypeError, ValueError):
        defense = 1.0
    return calculate_display_integrity_total(ship_count, integrity) * defense


def calculate_fleet_durability_capacity(ship_count, defense_multiplier=1.0):
    """Return the full defended hull capacity for a fleet at 100% integrity."""
    return calculate_fleet_durability_pool(
        ship_count,
        defense_multiplier=defense_multiplier,
        integrity=100.0,
    )


def resolve_damage_to_fleet(
    ship_count,
    integrity,
    defense_multiplier=1.0,
    damage_percent=0.0,
):
    """Apply pooled combat damage to a fleet and convert it back to ships + integrity."""
    try:
        ships = max(0, int(ship_count or 0))
    except (TypeError, ValueError):
        ships = 0
    start_integrity = clamp_integrity(integrity)
    if ships <= 0 or start_integrity <= 0.0:
        return {
            'destroyed': ships > 0,
            'ship_count': 0,
            'integrity': 0,
            'ships_lost': ships,
            'integrity_lost': int(round(calculate_display_integrity_total(ships, start_integrity))),
            'damage_fraction': 1.0 if ships > 0 else 0.0,
        }

    try:
        defense = max(0.001, float(defense_multiplier or 0.0))
    except (TypeError, ValueError):
        defense = 1.0
    try:
        damage_ratio = max(0.0, float(damage_percent or 0.0)) / 100.0
    except (TypeError, ValueError):
        damage_ratio = 0.0

    current_pool = calculate_fleet_durability_pool(
        ships,
        defense_multiplier=defense,
        integrity=start_integrity,
    )
    max_pool = calculate_fleet_durability_capacity(
        ships,
        defense_multiplier=defense,
    )
    if current_pool <= 0.0 or damage_ratio <= 0.0:
        return {
            'destroyed': False,
            'ship_count': ships,
            'integrity': int(round(start_integrity)),
            'ships_lost': 0,
            'integrity_lost': 0,
            'damage_fraction': 0.0,
        }

    applied_damage = min(current_pool, max_pool * damage_ratio)
    remaining_pool = current_pool - applied_damage
    if remaining_pool <= 0.000001:
        return {
            'destroyed': True,
            'ship_count': 0,
            'integrity': 0,
            'ships_lost': ships,
            'integrity_lost': int(round(calculate_display_integrity_total(ships, start_integrity))),
            'damage_fraction': 1.0,
        }

    per_ship_pool = 100.0 * defense
    remaining_ships = max(1, int(ceil((remaining_pool - 1e-9) / per_ship_pool)))
    new_integrity = int((remaining_pool + 1e-9) / (remaining_ships * defense))
    new_integrity = max(1, min(100, new_integrity))
    total_before = calculate_display_integrity_total(ships, start_integrity)
    total_after = calculate_display_integrity_total(remaining_ships, new_integrity)

    return {
        'destroyed': False,
        'ship_count': remaining_ships,
        'integrity': new_integrity,
        'ships_lost': max(0, ships - remaining_ships),
        'integrity_lost': max(0, int(round(total_before - total_after))),
        'damage_fraction': max(0.0, min(1.0, applied_damage / max_pool)),
    }


def calculate_scaled_count_strength(
    ship_count,
    multiplier=1.0,
    integrity=100.0,
    roll_scale=1.0,
    bonus_multiplier=1.0,
):
    """Return softened strength for a count scaled by offense/defense factors."""
    try:
        scaled_multiplier = max(0.0, float(multiplier))
    except (TypeError, ValueError):
        scaled_multiplier = 0.0
    try:
        scale = max(0.0, float(roll_scale))
    except (TypeError, ValueError):
        scale = 1.0
    try:
        bonus = max(0.0, float(bonus_multiplier))
    except (TypeError, ValueError):
        bonus = 1.0
    scaled_count = max(0.0, float(ship_count or 0.0)) * scaled_multiplier * scale * bonus
    return normalize_ship_count(scaled_count) * integrity_factor(integrity)


def calculate_damage_pressure(opponent_attack_strength, own_defense_strength, damage_scale=30.0):
    """Convert attack-vs-defense pressure into integrity damage."""
    try:
        attack = max(0.0, float(opponent_attack_strength or 0.0))
    except (TypeError, ValueError):
        attack = 0.0
    try:
        defense = max(0.001, float(own_defense_strength or 0.0))
    except (TypeError, ValueError):
        defense = 0.001
    try:
        scale = max(0.0, float(damage_scale or 0.0))
    except (TypeError, ValueError):
        scale = 0.0
    if attack <= 0.0 or scale <= 0.0:
        return 0.0
    pressure = attack / defense
    return scale * log2(1.0 + pressure)
