from __future__ import unicode_literals

from types import SimpleNamespace

from .colony_rules import (
    COLONISTS_PER_JOB,
    COLONISTS_PER_SHIPYARD,
    KT_PER_MINE,
    calculate_available_buildpoints,
    calculate_growth_factor,
    calculate_productivity_multiplier,
    calculate_staffing_ratio,
    limit_population_growth_by_surface_resources,
    population_growth_uses_surface_resources,
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

BASIC_MANAGED_ORDER_TYPES = (
    'BUILD_MINE',
    'BUILD_FACTORY',
    'BUILD_DEFENSE',
)
SUPPORT_MANAGED_ORDER_TYPES = (
    'BUILD_MINE',
    'BUILD_FACTORY',
    'BUILD_DEFENSE',
    'BUILD_LAB',
    'BUILD_SHIPYARD',
)
LEVEL_ONE_FILLER_ORDER_TYPES = (
    'BUILD_FACTORY',
    'BUILD_DEFENSE',
)
LEVEL_TWO_FILLER_ORDER_TYPES = (
    'BUILD_FACTORY',
    'BUILD_DEFENSE',
    'BUILD_LAB',
)


def empty_queue_requirements():
    """Return a zeroed queue requirement map."""
    requirements = {'bp': 0}
    for key in ALL_RESOURCE_KEYS:
        requirements[key] = 0
    return requirements


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
    growth, _reserve = _projected_population_growth_and_reserve(player, star)
    return population + growth


def _projected_population_growth_and_reserve(player, star, growth_cap=None):
    population = int(getattr(star, 'colonists', 0) or 0)
    if population <= 0 or not player or not getattr(player, 'race_type', None):
        return 0, {'ironium': 0, 'boranium': 0}
    factor = calculate_growth_factor(player, star)
    raw_multiplier = getattr(player.race_type, 'population_growth_multiplier', 1.0)
    if raw_multiplier is None:
        raw_multiplier = 1.0
    factor *= float(
        raw_multiplier
    )
    if factor <= 0:
        return 0, {'ironium': 0, 'boranium': 0}
    growth = int(population * factor)
    if growth_cap is not None:
        growth = min(growth, max(0, int(growth_cap or 0)))
    if growth <= 0:
        return 0, {'ironium': 0, 'boranium': 0}
    if not population_growth_uses_surface_resources(player):
        return growth, {'ironium': 0, 'boranium': 0}
    limited_growth, ironium_cost, boranium_cost = (
        limit_population_growth_by_surface_resources(star, growth)
    )
    return limited_growth, {
        'ironium': int(ironium_cost or 0),
        'boranium': int(boranium_cost or 0),
    }


def _population_growth_resource_reserve(player, star):
    if not population_growth_uses_surface_resources(player):
        return {'ironium': 0, 'boranium': 0}
    population = int(getattr(star, 'colonists', 0) or 0)
    if population <= 0:
        return {'ironium': 0, 'boranium': 0}
    current_jobs = _job_capacity(star)
    target_population = int((float(current_jobs) / JOB_TARGET_RATIO) + 0.999999)
    if target_population <= population:
        return {'ironium': 0, 'boranium': 0}
    growth_needed = target_population - population
    _growth, reserve = _projected_population_growth_and_reserve(
        player,
        star,
        growth_cap=growth_needed,
    )
    return reserve


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


def projected_mining_output(star):
    """Estimate one year of mining output for a real or projected colony."""
    rates = {}
    total_yield = 0
    for key in ALL_RESOURCE_KEYS:
        total_yield += int(getattr(star, '%s_yield' % key, 0) or 0)
    if total_yield <= 0 or int(getattr(star, 'mines', 0) or 0) <= 0:
        for key in ALL_RESOURCE_KEYS:
            rates[key] = 0
        return rates

    staffing_ratio = calculate_staffing_ratio(star)
    if staffing_ratio <= 0:
        for key in ALL_RESOURCE_KEYS:
            rates[key] = 0
        return rates

    productivity = calculate_productivity_multiplier(staffing_ratio)
    total_extraction = int(getattr(star, 'mines', 0) or 0) * KT_PER_MINE * productivity

    for key in ALL_RESOURCE_KEYS:
        yield_val = int(getattr(star, '%s_yield' % key, 0) or 0)
        if yield_val <= 0:
            rates[key] = 0
            continue
        rates[key] = int(total_extraction * yield_val / total_yield)
    return rates


def remaining_queue_requirements(orders, cost_map):
    """Estimate remaining BP and mineral demand for queued production."""
    requirements = empty_queue_requirements()
    for order in list(orders or []):
        remaining_qty = max(
            0,
            int(getattr(order, 'quantity', 0) or 0) -
            int(getattr(order, 'completed', 0) or 0),
        )
        if remaining_qty <= 0:
            continue
        cost = cost_map.get(getattr(order, 'order_type', None), {})
        requirements['bp'] += max(
            0,
            int(cost.get('bp', 0) or 0) * remaining_qty -
            int(getattr(order, 'spent_bp', 0) or 0),
        )
        for key in ALL_RESOURCE_KEYS:
            requirements[key] += max(
                0,
                int(cost.get(key, 0) or 0) * remaining_qty -
                int(getattr(order, 'spent_%s' % key, 0) or 0),
            )
    return requirements


def _add_queue_cost(star_state, cost):
    """Increase projected queue demand for one planned order."""
    setattr(
        star_state,
        'queue_bp',
        int(getattr(star_state, 'queue_bp', 0) or 0) +
        max(0, int(cost.get('bp', 0) or 0)),
    )
    for key in ALL_RESOURCE_KEYS:
        attr = 'queue_%s' % key
        setattr(
            star_state,
            attr,
            int(getattr(star_state, attr, 0) or 0) +
            max(0, int(cost.get(key, 0) or 0)),
        )


def _queue_throughput_pressure(star):
    """Return whether queue demand exceeds one year of projected output."""
    pressure = {'mines': False, 'factories': False}
    if int(getattr(star, 'queue_bp', 0) or 0) > calculate_available_buildpoints(star):
        pressure['factories'] = True

    mining_output = projected_mining_output(star)
    for key in ALL_RESOURCE_KEYS:
        demand = int(getattr(star, 'queue_%s' % key, 0) or 0)
        if demand <= 0:
            continue
        inventory = int(getattr(star, '%s_inventory' % key, 0) or 0)
        if demand <= inventory:
            continue
        if int(getattr(star, '%s_yield' % key, 0) or 0) <= 0:
            continue
        if demand > inventory + int(mining_output.get(key, 0) or 0):
            pressure['mines'] = True
            break
    return pressure


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


def get_micromanager_managed_order_types(tier):
    """Return infrastructure order types managed at the given tier."""
    if int(tier or 0) >= TIER_SUPPORT:
        return SUPPORT_MANAGED_ORDER_TYPES
    if int(tier or 0) >= TIER_BASIC:
        return BASIC_MANAGED_ORDER_TYPES
    return ()


def _has_resource_surplus_for_order(player, star, cost_map, order_type, reserve_factor=2):
    """Return True when the colony can cover queue demand with headroom."""
    if not cost_map:
        return False
    cost = cost_map.get(order_type, {})
    bp_needed = (
        int(getattr(star, 'queue_bp', 0) or 0) +
        max(0, int(cost.get('bp', 0) or 0)) * int(reserve_factor or 0)
    )
    if bp_needed > calculate_available_buildpoints(star):
        return False
    growth_reserve = _population_growth_resource_reserve(player, star)
    for key in ALL_RESOURCE_KEYS:
        demand = (
            int(getattr(star, 'queue_%s' % key, 0) or 0) +
            max(0, int(cost.get(key, 0) or 0)) * int(reserve_factor or 0)
        )
        if key in growth_reserve:
            demand += int(growth_reserve.get(key, 0) or 0)
        if demand > int(getattr(star, '%s_inventory' % key, 0) or 0):
            return False
    return True


def _preserves_population_growth_reserve(player, star, cost_map, order_type):
    """Return True when adding this order won't spend into growth reserves."""
    if not cost_map:
        return True
    growth_reserve = _population_growth_resource_reserve(player, star)
    if not any(int(value or 0) > 0 for value in growth_reserve.values()):
        return True
    cost = cost_map.get(order_type, {})
    for key in ('ironium', 'boranium'):
        reserve = int(growth_reserve.get(key, 0) or 0)
        if reserve <= 0:
            continue
        inventory = int(getattr(star, '%s_inventory' % key, 0) or 0)
        queue_demand = int(getattr(star, 'queue_%s' % key, 0) or 0)
        added_cost = max(0, int(cost.get(key, 0) or 0))
        remaining_after_spend = inventory - min(inventory, queue_demand + added_cost)
        if remaining_after_spend < reserve:
            return False
    return True


def get_micromanager_candidate_orders(
    player,
    star,
    tier,
    fleets_in_orbit=0,
    terraform_available=False,
    terraform_used=False,
    cost_map=None,
):
    """Return candidate automatic production orders in priority order."""
    if int(tier or 0) <= 0:
        return []
    if not bool(getattr(star, 'has_administration', False)):
        return []
    thresholds = _projected_job_thresholds(player, star)
    current_jobs = _job_capacity(star)
    candidates = []

    def append_candidate(order_type):
        if not _preserves_population_growth_reserve(
            player,
            star,
            cost_map,
            order_type,
        ):
            return
        candidates.append(order_type)
    current_mines = int(getattr(star, 'mines', 0) or 0)
    current_factories = int(getattr(star, 'factories', 0) or 0)
    max_mines = safe_mine_count(star)
    mine_room = current_mines < max_mines
    needs_jobs = current_jobs < thresholds['target_jobs']
    queue_pressure = {'mines': False, 'factories': False}
    filler_order_types = LEVEL_ONE_FILLER_ORDER_TYPES
    if int(tier or 0) >= TIER_SUPPORT:
        queue_pressure = _queue_throughput_pressure(star)
        filler_order_types = LEVEL_TWO_FILLER_ORDER_TYPES
    level_one_support_candidates = []
    if (
        int(tier or 0) == TIER_BASIC and
        current_jobs >= thresholds['min_jobs']
    ):
        if (
            int(getattr(star, 'labs', 0) or 0) <= 0 and
            _can_add_jobs_without_breaking_limit(player, star, 'BUILD_LAB') and
            _has_resource_surplus_for_order(player, star, cost_map, 'BUILD_LAB')
        ):
            level_one_support_candidates.append('BUILD_LAB')
        if (
            int(getattr(star, 'shipyards', 0) or 0) <= 0 and
            _can_add_jobs_without_breaking_limit(
                player, star, 'BUILD_SHIPYARD'
            ) and
            _has_resource_surplus_for_order(
                player,
                star,
                cost_map,
                'BUILD_SHIPYARD',
            )
        ):
            level_one_support_candidates.append('BUILD_SHIPYARD')

    if needs_jobs:
        # Bootstrap economic base before considering other priorities.
        if mine_room and current_mines <= 0:
            append_candidate('BUILD_MINE')
        if current_factories <= 0:
            append_candidate('BUILD_FACTORY')
        if queue_pressure.get('mines') and mine_room:
            append_candidate('BUILD_MINE')
        if queue_pressure.get('factories'):
            append_candidate('BUILD_FACTORY')

        if mine_room:
            if current_mines < (current_factories + 1) * 2:
                append_candidate('BUILD_MINE')
                append_candidate('BUILD_FACTORY')
            else:
                append_candidate('BUILD_FACTORY')
                append_candidate('BUILD_MINE')
        else:
            if int(tier or 0) >= TIER_SUPPORT:
                if (
                    int(getattr(star, 'shipyards', 0) or 0) <
                    int(fleets_in_orbit or 0) and
                    _can_add_jobs_without_breaking_limit(
                        player, star, 'BUILD_SHIPYARD'
                    )
                ):
                    append_candidate('BUILD_SHIPYARD')
            for order_type in filler_order_types:
                append_candidate(order_type)
            for order_type in level_one_support_candidates:
                append_candidate(order_type)
    else:
        if queue_pressure.get('mines') and mine_room:
            append_candidate('BUILD_MINE')
        if queue_pressure.get('factories'):
            append_candidate('BUILD_FACTORY')
        if (
            int(tier or 0) >= TIER_SUPPORT and
            int(getattr(star, 'shipyards', 0) or 0) < int(fleets_in_orbit or 0) and
            _can_add_jobs_without_breaking_limit(player, star, 'BUILD_SHIPYARD')
        ):
            append_candidate('BUILD_SHIPYARD')
        for order_type in level_one_support_candidates:
            append_candidate(order_type)

    if (
        int(tier or 0) >= TIER_TERRAFORM and
        terraform_available and
        not terraform_used and
        current_jobs >= thresholds['min_jobs']
    ):
        terraform_order = preferred_terraform_order(player, star)
        if terraform_order:
            append_candidate(terraform_order)

    deduped = []
    seen = set()
    for order_type in candidates:
        if order_type in seen:
            continue
        seen.add(order_type)
        deduped.append(order_type)
    return deduped


def _project_star_state(star, queue_requirements=None):
    queue_requirements = queue_requirements or empty_queue_requirements()
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
            '%s_inventory' % key: int(
                getattr(star, '%s_inventory' % key, 0) or 0
            )
            for key in ALL_RESOURCE_KEYS
        },
        queue_bp=int(queue_requirements.get('bp', 0) or 0),
        **{
            'queue_%s' % key: int(queue_requirements.get(key, 0) or 0)
            for key in ALL_RESOURCE_KEYS
        },
        **{
            '%s_yield' % key: int(getattr(star, '%s_yield' % key, 0) or 0)
            for key in ALL_RESOURCE_KEYS
        }
    )


def apply_projected_order(
    player,
    star_state,
    order_type,
    terraform_rate=0.0,
    cost_map=None,
    add_queue_cost=False,
):
    """Apply one planned order to a projected colony state."""
    if add_queue_cost and cost_map is not None:
        _add_queue_cost(star_state, cost_map.get(order_type, {}))
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
    cost_map=None,
    queue_requirements=None,
    limit=12,
):
    """Plan queued Micromanager orders for one colony."""
    if int(tier or 0) <= 0:
        return []
    projected = _project_star_state(
        star,
        queue_requirements=queue_requirements,
    )
    terraform_used = False
    existing = list(preplanned_orders or [])
    for order_type in existing:
        apply_projected_order(
            player,
            projected,
            order_type,
            terraform_rate=terraform_rate,
            cost_map=cost_map,
            add_queue_cost=False,
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
            cost_map=cost_map,
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
            cost_map=cost_map,
            add_queue_cost=True,
        )
        if str(selected).startswith('TERRAFORM_'):
            terraform_used = True
    return planned


def compress_micromanager_order_runs(order_types):
    """Collapse adjacent identical order types into (type, quantity) runs."""
    runs = []
    for order_type in list(order_types or []):
        if not runs or runs[-1][0] != order_type:
            runs.append([order_type, 1])
            continue
        runs[-1][1] += 1
    return [(order_type, quantity) for order_type, quantity in runs]
