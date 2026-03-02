import math

from .chance_rules import scaled_luck_roll
from .models import (
    BOMB_TYPE_CONVENTIONAL,
    BOMB_TYPE_SMART,
    BOMB_TYPE_NOVA,
)


_BOMB_DAMAGE_MULTIPLIER = {
    BOMB_TYPE_CONVENTIONAL: 1.0,
    BOMB_TYPE_SMART: 4.0,
    BOMB_TYPE_NOVA: 10.0,
}


def normalize_bomb_type(value):
    """Return a canonical bomb type string or None."""
    if value in (None, False, '', 'False', 'false', 'NONE', 'none'):
        return None
    normalised = str(value).strip().upper()
    if normalised in _BOMB_DAMAGE_MULTIPLIER:
        return normalised
    return None


def normalize_miner_type(value):
    """Return a canonical miner type string or None."""
    if value in (None, False, '', 'False', 'false', 'NONE', 'none'):
        return None
    normalised = str(value).strip().upper()
    if normalised in ('SMALL', 'MEDIUM', 'LARGE'):
        return normalised
    return None


def bomb_damage_multiplier(bomb_type):
    """Return the per-type bombardment damage multiplier."""
    canonical = normalize_bomb_type(bomb_type)
    if canonical is None:
        return 0.0
    return _BOMB_DAMAGE_MULTIPLIER[canonical]


def smart_bombs_only_target_defenses_and_population(bomb_type):
    return normalize_bomb_type(bomb_type) == BOMB_TYPE_SMART


def bombardment_damage_k(ship_count, offense_level, defenses, luck_multiplier, bomb_type):
    """Return bombardment damage in thousands of units."""
    mult = bomb_damage_multiplier(bomb_type)
    if mult <= 0.0:
        return 0

    count = max(0, int(ship_count or 0))
    if count <= 0:
        return 0

    try:
        offense = float(offense_level)
    except (TypeError, ValueError):
        offense = 0.0
    attack_strength = 2.0 ** max(0.0, offense)

    # Defenses temper bombardment output: 0 defenses => full damage,
    # higher defenses progressively reduce damage.
    defense_factor = 1.0 + max(0.0, float(defenses or 0.0))
    offense_roll = scaled_luck_roll(
        luck_multiplier,
        min_scale=0.5,
        max_scale=1.0,
        bend=0.65,
    )
    raw = float(count) * attack_strength * offense_roll * mult
    raw /= defense_factor
    return max(0, int(math.floor(raw)))
