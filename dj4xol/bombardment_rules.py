import math
import random

from .chance_rules import scaled_luck_roll
from .combat_rules import normalize_ship_count
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
NOVA_BOMB_GRAVITY_DELTA = -0.20
NOVA_BOMB_RADIATION_DELTA = 0.02
SUPERNOVA_BOMB_GRAVITY_DELTA = -0.55
SUPERNOVA_BOMB_RADIATION_DELTA = NOVA_BOMB_RADIATION_DELTA * 2.0
NOVA_COLLAPSE_GRAVITY_THRESHOLD = 0.09
SUPERNOVA_COLLAPSE_GRAVITY_THRESHOLD = 0.15


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


def _clamped_environment_scale(scale):
    try:
        return max(0.0, min(1.0, float(scale)))
    except (TypeError, ValueError):
        return 1.0


def apply_neutron_bomb_environment_shift(temperature, radiation, scale=1.0):
    """Apply neutron bombardment environmental side-effects with clamping."""
    scale = _clamped_environment_scale(scale)
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
        min(2.0, current_temperature + (NEUTRON_BOMB_TEMPERATURE_DELTA * scale)),
    )
    new_radiation = max(
        0.0,
        min(2.0, current_radiation + (NEUTRON_BOMB_RADIATION_DELTA * scale)),
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


def bombardment_point_budget(damage_k, minimum_points=0, points_per_damage=2):
    """Convert coarse bombardment damage into spendable bombardment points."""
    try:
        damage = max(0, int(damage_k or 0))
    except (TypeError, ValueError):
        damage = 0
    try:
        minimum = max(0, int(minimum_points or 0))
    except (TypeError, ValueError):
        minimum = 0
    try:
        multiplier = max(0, int(points_per_damage or 0))
    except (TypeError, ValueError):
        multiplier = 0
    return max(minimum, damage * multiplier)


def allocate_weighted_hits(
    total_hits,
    capacities,
    weight_scales=None,
    rng=None,
    scale_by_capacity=True,
):
    """Allocate hits across capped targets, using stable random remainder spreading."""
    results = {
        key: 0
        for key in (capacities or {})
    }
    try:
        hits = max(0, int(total_hits or 0))
    except (TypeError, ValueError):
        hits = 0
    if hits <= 0 or not capacities:
        return results

    if rng is None:
        rng = random
    scales = weight_scales or {}

    remaining = {}
    for key, raw_capacity in capacities.items():
        try:
            capacity = max(0, int(raw_capacity or 0))
        except (TypeError, ValueError):
            capacity = 0
        if capacity > 0:
            remaining[key] = capacity
    if not remaining:
        return results

    hits = min(hits, sum(remaining.values()))

    weighted = []
    total_weight = 0.0
    for key, capacity in remaining.items():
        try:
            scale = float(scales.get(key, 1.0) or 0.0)
        except (TypeError, ValueError):
            scale = 1.0
        weight = max(0.0, scale)
        if scale_by_capacity:
            weight *= float(capacity)
        if weight <= 0.0:
            continue
        weighted.append((key, weight))
        total_weight += weight
    if total_weight <= 0.0:
        return results

    assigned = 0
    for key, weight in weighted:
        share = float(hits) * (weight / total_weight)
        base_hits = min(remaining[key], int(math.floor(share)))
        results[key] += base_hits
        remaining[key] -= base_hits
        assigned += base_hits

    remaining_hits = max(0, hits - assigned)
    while remaining_hits > 0:
        choices = []
        total_choice_weight = 0.0
        for key, capacity in remaining.items():
            if capacity <= 0:
                continue
            try:
                scale = float(scales.get(key, 1.0) or 0.0)
            except (TypeError, ValueError):
                scale = 1.0
            weight = max(0.0, scale)
            if scale_by_capacity:
                weight *= float(capacity)
            if weight <= 0.0:
                continue
            choices.append((key, weight))
            total_choice_weight += weight
        if total_choice_weight <= 0.0:
            break
        roll = float(rng.random()) * total_choice_weight
        chosen_key = choices[-1][0]
        cumulative = 0.0
        for key, weight in choices:
            cumulative += weight
            if roll < cumulative:
                chosen_key = key
                break
        results[chosen_key] += 1
        remaining[chosen_key] -= 1
        remaining_hits -= 1
    return results


def distribute_infrastructure_hits(structure_counts, total_hits):
    """Distribute shared infrastructure damage proportionally across categories."""
    results = {
        key: 0
        for key in (structure_counts or {})
    }
    try:
        hits = max(0, int(total_hits or 0))
    except (TypeError, ValueError):
        hits = 0
    if hits <= 0 or not structure_counts:
        return results

    active = []
    total_available = 0
    for index, (key, raw_count) in enumerate(structure_counts.items()):
        try:
            count = max(0, int(raw_count or 0))
        except (TypeError, ValueError):
            count = 0
        if count <= 0:
            continue
        active.append((index, key, count))
        total_available += count
    if total_available <= 0:
        return results

    hits = min(hits, total_available)
    assigned = 0
    ranked = []
    for index, key, count in active:
        raw_share = (float(hits) * float(count)) / float(total_available)
        base_loss = min(count, int(math.floor(raw_share)))
        results[key] = base_loss
        assigned += base_loss
        ranked.append((key, raw_share - float(base_loss), count, index))

    remaining = max(0, hits - assigned)
    for key, _, _, _ in sorted(
        ranked,
        key=lambda item: (-item[1], -item[2], item[3]),
    )[:remaining]:
        results[key] += 1
    return results


def graviton_bombs_apply_gravity_shift(bomb_type):
    return normalize_bomb_type(bomb_type) == BOMB_TYPE_GRAVITON


def apply_graviton_bomb_environment_shift(gravity, scale=1.0):
    """Apply graviton bombardment gravity side-effect with clamping."""
    scale = _clamped_environment_scale(scale)
    try:
        current_gravity = float(gravity)
    except (TypeError, ValueError):
        current_gravity = 0.0

    return max(
        0.0,
        min(2.0, current_gravity + (GRAVITON_BOMB_GRAVITY_DELTA * scale)),
    )


def apply_nova_family_environment_shift(gravity, radiation, bomb_type, scale=1.0):
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
    scale = _clamped_environment_scale(scale)

    gravity_delta = NOVA_BOMB_GRAVITY_DELTA
    radiation_delta = NOVA_BOMB_RADIATION_DELTA
    if normalized == BOMB_TYPE_SUPERNOVA:
        gravity_delta = SUPERNOVA_BOMB_GRAVITY_DELTA
        radiation_delta = SUPERNOVA_BOMB_RADIATION_DELTA

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
        min(2.0, current_gravity + (gravity_delta * scale)),
    )
    new_radiation = max(
        0.0,
        min(2.0, current_radiation + (radiation_delta * scale)),
    )
    return new_gravity, new_radiation


def bombardment_damage_k(
    ship_count,
    defense_level,
    defenses,
    luck_multiplier,
    bomb_type,
    bombardment_multiplier=1.0,
):
    """Return bombardment damage in thousands of units."""
    mult = bomb_damage_multiplier(bomb_type)
    if mult <= 0.0:
        return 0

    count = max(0, int(ship_count or 0))
    if count <= 0:
        return 0

    try:
        defense_tech = float(defense_level)
    except (TypeError, ValueError):
        defense_tech = 0.0
    bombardment_tech_factor = max(0.5, 1.0 + (defense_tech * 0.5))
    try:
        bombardment_mult = float(bombardment_multiplier)
    except (TypeError, ValueError):
        bombardment_mult = 1.0
    offense_roll = scaled_luck_roll(
        luck_multiplier,
        min_scale=0.5,
        max_scale=1.0,
        bend=0.65,
    )
    attack_pressure = normalize_ship_count(
        float(count) *
        bombardment_tech_factor *
        max(0.0, bombardment_mult) *
        offense_roll *
        mult
    )
    defense_pressure = normalize_ship_count(max(0.0, float(defenses or 0.0)))
    if attack_pressure <= 0.0:
        return 0
    if defense_pressure <= 0.0:
        raw = attack_pressure
    else:
        raw = attack_pressure * (attack_pressure / (attack_pressure + defense_pressure))
    return max(0, int(math.floor(raw)))
