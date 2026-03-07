from __future__ import unicode_literals

from types import SimpleNamespace

from .colony_rules import (
    COLONISTS_PER_JOB,
    COLONISTS_PER_SHIPYARD,
    KT_PER_MINE,
    calculate_growth_factor,
    calculate_productivity_multiplier,
    calculate_staffing_ratio,
)
from .mineral_rules import ALL_RESOURCE_KEYS


JOB_MIN_RATIO = 0.25
JOB_TARGET_RATIO = 0.50
JOB_MAX_RATIO = 0.75

TIER_BASIC = 1
TIER_SUPPORT = 2
TIER_TERRAFORM = 3

ADMINISTRATION_ORDER_TYPE = 'BUILD_ADMINISTRATION'
REMOVE_ADMINISTRATION_ORDER_TYPE = 'REMOVE_ADMINISTRATION'
ADMINISTRATION_ONE_OFF_ORDER_TYPES = (
    ADMINISTRATION_ORDER_TYPE,
    REMOVE_ADMINISTRATION_ORDER_TYPE,
)
ADMINISTRATION_LEVEL_PARAM_KEYS = (
    'administration_level',
    'micromanager_tier',
    'colony_micromanager_tier',
)

FILLER_ORDER_TYPES = (
    'BUILD_FACTORY',
    'BUILD_LAB',
    'BUILD_DEFENSE',
)


def _job_capacity(star):
    return int(
        (
            (int(star.mines or 0) + int(star.factories or 0) +
             int(star.labs or 0) + int(star.defenses or 0)) *
            COLONISTS_PER_JOB
        ) + (int(star.shipyards or 0) * COLONISTS_PER_SHIPYARD)
    )


def _projected_population(player, star):
    population = int(getattr(star, 'colonists', 0) or 0)
    if population <= 0 or not player or not getattr(player, 'race_type', None):
        return population
    factor = calculate_growth_factor(player, star)
    factor *= float(
        getattr(player.race_type, 'population_growth_multiplier', 1.0) or 1.0
    )
    if factor <= 0:
        return population
    return population + int(population * factor)


def _projected_job_thresholds(player, star):
    projected_population = _projected_population(player, star)
    min_jobs = int(projected_population * JOB_MIN_RATIO)
    target_jobs = int(projected_population * JOB_TARGET_RATIO)
    max_jobs = int(projected_population * JOB_MAX_RATIO)
    return {
        'min_jobs': max(0, min_jobs),
        'target_jobs': max(0, target_jobs),
        'max_jobs': max(0, max_jobs),
    }


def _job_capacity_after(star, order_type):
    extra = 0
    if order_type in (
        'BUILD_MINE',
        'BUILD_FACTORY',
        'BUILD_LAB',
        'BUILD_DEFENSE',
    ):
        extra = COLONISTS_PER_JOB
    elif order_type == 'BUILD_SHIPYARD':
        extra = COLONISTS_PER_SHIPYARD
    return _job_capacity(star) + extra


def _can_add_jobs_without_breaking_limit(player, star, order_type):
    thresholds = _projected_job_thresholds(player, star)
    current_jobs = _job_capacity(star)
    next_jobs = _job_capacity_after(star, order_type)
    if current_jobs < thresholds['min_jobs']:
        return True
    return next_jobs <= thresholds['max_jobs']


def safe_mine_count(star):
    total_yield = 0
    for key in ALL_RESOURCE_KEYS:
        total_yield += int(getattr(star, '%s_yield' % key, 0) or 0)
    if total_yield <= 0:
        return 0
    staffing_ratio = calculate_staffing_ratio(star)
    productivity = calculate_productivity_multiplier(staffing_ratio)
    if productivity <= 0:
        productivity = 1.0
    sustainable = float(total_yield) / float(KT_PER_MINE * productivity)
    if sustainable <= 0:
        return 0
    return int(sustainable)


def preferred_terraform_order(player, star):
    if not player or not star:
        return None
    candidates = [
        (
            abs(float(getattr(star, 'gravity', 0.0) or 0.0) -
                float(getattr(player, 'gravity_center', 0.0) or 0.0)),
            'TERRAFORM_GRAVITY',
        ),
        (
            abs(float(getattr(star, 'temperature', 0.0) or 0.0) -
                float(getattr(player, 'temperature_center', 0.0) or 0.0)),
            'TERRAFORM_TEMPERATURE',
        ),
        (
            abs(float(getattr(star, 'radiation', 0.0) or 0.0) -
                float(getattr(player, 'radiation_center', 0.0) or 0.0)),
            'TERRAFORM_RADIATION',
        ),
    ]
    candidates.sort(reverse=True)
    distance, order_type = candidates[0]
    if distance <= 0.0001:
        return None
    return order_type


def administration_level_from_params(params):
    if not isinstance(params, dict):
        return 0
    for key in ADMINISTRATION_LEVEL_PARAM_KEYS:
        try:
            level = int(params.get(key) or 0)
        except (TypeError, ValueError):
            level = 0
        if level > 0:
            return level
    return 0


def get_micromanager_candidate_orders(
    player,
    star,
    tier,
    fleets_in_orbit=0,
    terraform_available=False,
    terraform_used=False,
):
    """Return candidate automatic production orders in priority order."""
    if int(tier or 0) <= 0:
        return []
    if not bool(getattr(star, 'has_administration', False)):
        return []
    thresholds = _projected_job_thresholds(player, star)
    current_jobs = _job_capacity(star)
    candidates = []
    max_mines = safe_mine_count(star)
    mine_room = int(getattr(star, 'mines', 0) or 0) < max_mines
    needs_jobs = current_jobs < thresholds['target_jobs']

    if needs_jobs:
        if mine_room:
            if int(getattr(star, 'mines', 0) or 0) < (
                int(getattr(star, 'factories', 0) or 0) + 1
            ) * 2:
                candidates.extend(['BUILD_MINE', 'BUILD_FACTORY'])
            else:
                candidates.extend(['BUILD_FACTORY', 'BUILD_MINE'])
        else:
            if int(tier or 0) >= TIER_SUPPORT:
                if (
                    int(getattr(star, 'shipyards', 0) or 0) <
                    int(fleets_in_orbit or 0) and
                    _can_add_jobs_without_breaking_limit(
                        player, star, 'BUILD_SHIPYARD'
                    )
                ):
                    candidates.append('BUILD_SHIPYARD')
                candidates.extend(FILLER_ORDER_TYPES)
            else:
                candidates.append('BUILD_FACTORY')
    elif (
        int(tier or 0) >= TIER_SUPPORT and
        int(getattr(star, 'shipyards', 0) or 0) < int(fleets_in_orbit or 0) and
        _can_add_jobs_without_breaking_limit(player, star, 'BUILD_SHIPYARD')
    ):
        candidates.append('BUILD_SHIPYARD')

    if (
        int(tier or 0) >= TIER_TERRAFORM and
        terraform_available and
        not terraform_used and
        current_jobs >= thresholds['min_jobs']
    ):
        terraform_order = preferred_terraform_order(player, star)
        if terraform_order:
            candidates.append(terraform_order)

    deduped = []
    seen = set()
    for order_type in candidates:
        if order_type in seen:
            continue
        seen.add(order_type)
        deduped.append(order_type)
    return deduped


def _project_star_state(star):
    return SimpleNamespace(
        colonists=int(getattr(star, 'colonists', 0) or 0),
        base_capacity=int(getattr(star, 'base_capacity', 0) or 0),
        mines=int(getattr(star, 'mines', 0) or 0),
        factories=int(getattr(star, 'factories', 0) or 0),
        labs=int(getattr(star, 'labs', 0) or 0),
        defenses=int(getattr(star, 'defenses', 0) or 0),
        shipyards=int(getattr(star, 'shipyards', 0) or 0),
        buildpoints_consumed=int(
            getattr(star, 'buildpoints_consumed', 0) or 0
        ),
        has_administration=bool(getattr(star, 'has_administration', False)),
        gravity=float(getattr(star, 'gravity', 0.0) or 0.0),
        temperature=float(getattr(star, 'temperature', 0.0) or 0.0),
        radiation=float(getattr(star, 'radiation', 0.0) or 0.0),
        **{
            '%s_yield' % key: int(getattr(star, '%s_yield' % key, 0) or 0)
            for key in ALL_RESOURCE_KEYS
        }
    )


def apply_projected_order(player, star_state, order_type, terraform_rate=0.0):
    """Apply one planned order to a projected colony state."""
    if order_type == 'BUILD_MINE':
        star_state.mines += 1
    elif order_type == 'BUILD_FACTORY':
        star_state.factories += 1
    elif order_type == 'BUILD_LAB':
        star_state.labs += 1
    elif order_type == 'BUILD_DEFENSE':
        star_state.defenses += 1
    elif order_type == 'BUILD_SHIPYARD':
        star_state.shipyards += 1
    elif order_type == ADMINISTRATION_ORDER_TYPE:
        star_state.has_administration = True
    elif order_type == 'TERRAFORM_GRAVITY':
        distance = float(getattr(player, 'gravity_center', 0.0) or 0.0) - star_state.gravity
        star_state.gravity += distance * float(terraform_rate or 0.0)
    elif order_type == 'TERRAFORM_TEMPERATURE':
        distance = (
            float(getattr(player, 'temperature_center', 0.0) or 0.0) -
            star_state.temperature
        )
        star_state.temperature += distance * float(terraform_rate or 0.0)
    elif order_type == 'TERRAFORM_RADIATION':
        distance = (
            float(getattr(player, 'radiation_center', 0.0) or 0.0) -
            star_state.radiation
        )
        star_state.radiation += distance * float(terraform_rate or 0.0)


def plan_micromanager_orders(
    player,
    star,
    tier,
    fleets_in_orbit=0,
    terraform_available=False,
    terraform_rate=0.0,
    preplanned_orders=None,
    limit=12,
):
    """Plan queued Micromanager orders for one colony."""
    if int(tier or 0) <= 0:
        return []
    projected = _project_star_state(star)
    terraform_used = False
    existing = list(preplanned_orders or [])
    for order_type in existing:
        apply_projected_order(
            player,
            projected,
            order_type,
            terraform_rate=terraform_rate,
        )
        if str(order_type).startswith('TERRAFORM_'):
            terraform_used = True

    planned = []
    for _ in range(max(0, int(limit or 0))):
        candidates = get_micromanager_candidate_orders(
            player,
            projected,
            tier,
            fleets_in_orbit=fleets_in_orbit,
            terraform_available=terraform_available,
            terraform_used=terraform_used,
        )
        if not candidates:
            break
        selected = candidates[0]
        planned.append(selected)
        apply_projected_order(
            player,
            projected,
            selected,
            terraform_rate=terraform_rate,
        )
        if str(selected).startswith('TERRAFORM_'):
            terraform_used = True
    return planned
