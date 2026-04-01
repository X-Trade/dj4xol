import math

from .chance_rules import scaled_luck_roll
from .models import (
    BOMB_TYPE_CONVENTIONAL,
    BOMB_TYPE_NEUTRON,
    BOMB_TYPE_SMART,
    BOMB_TYPE_GRAVITON,
    BOMB_TYPE_NOVA,
    BOMB_TYPE_SUPERNOVA,
)


_BOMB_DAMAGE_MULTIPLIER = {
    BOMB_TYPE_CONVENTIONAL: 1.0,
    BOMB_TYPE_NEUTRON: 2.0,
    BOMB_TYPE_SMART: 4.0,
    BOMB_TYPE_GRAVITON: 7.0,
    BOMB_TYPE_NOVA: 10.0,
    BOMB_TYPE_SUPERNOVA: 10.0,
}

NEUTRON_BOMB_TEMPERATURE_DELTA = 0.01
NEUTRON_BOMB_RADIATION_DELTA = 0.02
GRAVITON_BOMB_GRAVITY_DELTA = 0.05
NEUTRON_BOMB_COLLATERAL_INFRA_SCALE = 0.25
DYSON_BOMBARDMENT_DAMPING_MULTIPLIER = 0.50
NOVA_BOMB_GRAVITY_DELTA = -0.10
NOVA_BOMB_RADIATION_DELTA = 0.02
SUPERNOVA_BOMB_ENV_MULTIPLIER = 2.0


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


def neutron_bombs_target_population_shipyards_and_cities(bomb_type):
    return normalize_bomb_type(bomb_type) == BOMB_TYPE_NEUTRON


def apply_neutron_bomb_environment_shift(temperature, radiation):
    """Apply neutron bombardment environmental side-effects with clamping."""
    try:
        current_temperature = float(temperature)
    except (TypeError, ValueError):
        current_temperature = 0.0
    try:
        current_radiation = float(radiation)
    except (TypeError, ValueError):
        current_radiation = 0.0

    new_temperature = max(
        0.0,
        min(2.0, current_temperature + NEUTRON_BOMB_TEMPERATURE_DELTA),
    )
    new_radiation = max(
        0.0,
        min(2.0, current_radiation + NEUTRON_BOMB_RADIATION_DELTA),
    )
    return new_temperature, new_radiation


def neutron_bomb_collateral_damage_k(damage_k):
    """Reduced collateral damage neutron bombs apply to non-primary infrastructure."""
    try:
        base = int(damage_k or 0)
    except (TypeError, ValueError):
        base = 0
    if base <= 0:
        return 0
    return max(0, int(round(base * NEUTRON_BOMB_COLLATERAL_INFRA_SCALE)))


def apply_dyson_bombardment_damping(damage_k, has_dyson_sphere):
    """Apply Dyson Sphere bombardment damping to all destruction deductions."""
    try:
        base = int(damage_k or 0)
    except (TypeError, ValueError):
        base = 0
    if base <= 0 or not bool(has_dyson_sphere):
        return max(0, base)
    return max(
        0,
        int(round(base * DYSON_BOMBARDMENT_DAMPING_MULTIPLIER)),
    )


def graviton_bombs_apply_gravity_shift(bomb_type):
    return normalize_bomb_type(bomb_type) == BOMB_TYPE_GRAVITON


def apply_graviton_bomb_environment_shift(gravity):
    """Apply graviton bombardment gravity side-effect with clamping."""
    try:
        current_gravity = float(gravity)
    except (TypeError, ValueError):
        current_gravity = 0.0

    return max(
        0.0,
        min(2.0, current_gravity + GRAVITON_BOMB_GRAVITY_DELTA),
    )


def apply_nova_family_environment_shift(gravity, radiation, bomb_type):
    """Apply nova/supernova environmental side-effects (if a star survives)."""
    normalized = normalize_bomb_type(bomb_type)
    if normalized not in (BOMB_TYPE_NOVA, BOMB_TYPE_SUPERNOVA):
        try:
            current_gravity = float(gravity)
        except (TypeError, ValueError):
            current_gravity = 0.0
        try:
            current_radiation = float(radiation)
        except (TypeError, ValueError):
            current_radiation = 0.0
        return (
            max(0.0, min(2.0, current_gravity)),
            max(0.0, min(2.0, current_radiation)),
        )

    multiplier = 1.0
    if normalized == BOMB_TYPE_SUPERNOVA:
        multiplier = SUPERNOVA_BOMB_ENV_MULTIPLIER

    try:
        current_gravity = float(gravity)
    except (TypeError, ValueError):
        current_gravity = 0.0
    try:
        current_radiation = float(radiation)
    except (TypeError, ValueError):
        current_radiation = 0.0

    new_gravity = max(
        0.0,
        min(2.0, current_gravity + (NOVA_BOMB_GRAVITY_DELTA * multiplier)),
    )
    new_radiation = max(
        0.0,
        min(2.0, current_radiation + (NOVA_BOMB_RADIATION_DELTA * multiplier)),
    )
    return new_gravity, new_radiation


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
