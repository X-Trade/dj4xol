from __future__ import unicode_literals

from types import SimpleNamespace

from .colony_rules import (
    COLONISTS_PER_JOB,
    COLONISTS_PER_SHIPYARD,
    DYSON_SPHERE_JOBS,
    KT_PER_MINE,
    calculate_available_buildpoints,
    calculate_growth_factor,
    calculate_productivity_multiplier,
    calculate_staffing_ratio,
    calculate_total_jobs,
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
TIER_MECHANICAL_GROWTH = 4

MECHANICAL_GROWTH_EMPLOYMENT_MIN = 45.0
MECHANICAL_GROWTH_EMPLOYMENT_TOP = 90.0

ADMINISTRATION_ORDER_TYPE = 'BUILD_ADMINISTRATION'
REMOVE_ADMINISTRATION_ORDER_TYPE = 'REMOVE_ADMINISTRATION'
DYSON_SPHERE_ORDER_TYPE = 'BUILD_DYSON_SPHERE'
ADMINISTRATION_ONE_OFF_ORDER_TYPES = (
    ADMINISTRATION_ORDER_TYPE,
    REMOVE_ADMINISTRATION_ORDER_TYPE,
    DYSON_SPHERE_ORDER_TYPE,
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
LEVEL_TWO_DEFENSE_FLOOR = 12
LEVEL_TWO_LAB_FLOOR = 8
SHIPYARD_COMPLETION_MAX_YEARS = 5
DYSON_COMPLETION_MAX_YEARS = 9


def empty_queue_requirements():
    """Return a zeroed queue requirement map."""
    requirements = {'bp': 0}
    for key in ALL_RESOURCE_KEYS:
        requirements[key] = 0
    return requirements


def _job_capacity(star):
    return int(calculate_total_jobs(star))


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
    if bool(getattr(player.race_type, 'is_mechanical', False)):
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


def _jobs_added_by_order(order_type):
    if order_type in (
        'BUILD_MINE',
        'BUILD_FACTORY',
        'BUILD_LAB',
        'BUILD_DEFENSE',
    ):
        return COLONISTS_PER_JOB
    if order_type == 'BUILD_SHIPYARD':
        return COLONISTS_PER_SHIPYARD
    if order_type == DYSON_SPHERE_ORDER_TYPE:
        return DYSON_SPHERE_JOBS
    return 0


def _can_add_order_without_exceeding_max_jobs(player, star, order_type):
    """Return True when this order keeps projected jobs <= 75% target cap."""
    extra_jobs = int(_jobs_added_by_order(order_type) or 0)
    if extra_jobs <= 0:
        return True
    thresholds = _projected_job_thresholds(player, star)
    next_jobs = int(_job_capacity(star) or 0) + extra_jobs
    return next_jobs <= int(thresholds.get('max_jobs', 0) or 0)


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


def _planning_limit_for_star(player, star, limit):
    """Return a deeper queue target when jobs are critically low."""
    plan_limit = max(0, int(limit or 0))
    thresholds = _projected_job_thresholds(player, star)
    current_jobs = _job_capacity(star)
    if current_jobs < thresholds['min_jobs']:
        missing_jobs = thresholds['min_jobs'] - current_jobs
        catchup_limit = (
            missing_jobs + COLONISTS_PER_JOB - 1
        ) // COLONISTS_PER_JOB
        return max(plan_limit, min(1000, int(catchup_limit)))
    if current_jobs < thresholds['target_jobs']:
        missing_jobs = thresholds['target_jobs'] - current_jobs
        catchup_limit = (
            missing_jobs + COLONISTS_PER_JOB - 1
        ) // COLONISTS_PER_JOB
        return max(plan_limit, min(120, int(catchup_limit)))
    return plan_limit


def _one_year_planning_budget(player, star, queue_requirements=None):
    """Return remaining one-year BP/mineral budget after queued work."""
    queue_requirements = queue_requirements or empty_queue_requirements()
    mining_output = projected_mining_output(star)
    budget = {
        'bp': max(
            0,
            calculate_available_buildpoints(star) -
            int(queue_requirements.get('bp', 0) or 0),
        ),
    }
    for key in ALL_RESOURCE_KEYS:
        available = (
            int(getattr(star, '%s_inventory' % key, 0) or 0) +
            int(mining_output.get(key, 0) or 0) -
            int(queue_requirements.get(key, 0) or 0)
        )
        budget[key] = max(0, available)
    return budget


def _can_afford_from_budget(cost_map, budget, order_type):
    """Return True when the order fits within the one-year budget."""
    if not cost_map:
        return True
    cost = cost_map.get(order_type, {})
    if max(0, int(cost.get('bp', 0) or 0)) > int(budget.get('bp', 0) or 0):
        return False
    for key in ALL_RESOURCE_KEYS:
        if (
            max(0, int(cost.get(key, 0) or 0)) >
            int(budget.get(key, 0) or 0)
        ):
            return False
    return True


def _ignores_planning_budget_caps(order_type):
    """Return True when this order should bypass one-year budget gating."""
    return str(order_type or '').strip().upper() == 'BUILD_COLONISTS_1K'


def _spend_budget(cost_map, budget, order_type):
    """Reduce the one-year budget by the positive costs of one order."""
    if not cost_map:
        return
    cost = cost_map.get(order_type, {})
    budget['bp'] = max(
        0,
        int(budget.get('bp', 0) or 0) -
        max(0, int(cost.get('bp', 0) or 0)),
    )
    for key in ALL_RESOURCE_KEYS:
        budget[key] = max(
            0,
            int(budget.get(key, 0) or 0) -
            max(0, int(cost.get(key, 0) or 0)),
        )


def _one_year_income(star):
    """Return estimated one-year BP/mineral income for planning horizons."""
    income = {'bp': max(0, int(calculate_available_buildpoints(star) or 0))}
    mining_output = projected_mining_output(star)
    for key in ALL_RESOURCE_KEYS:
        income[key] = max(0, int(mining_output.get(key, 0) or 0))
    return income


def _can_complete_within_years(cost_map, budget, income, order_type, years):
    """Return True when an order can complete within a multi-year horizon."""
    if not cost_map:
        return False
    max_years = max(1, int(years or 1))
    cost = cost_map.get(order_type, {})
    horizon_extra_years = max(0, max_years - 1)

    bp_need = max(0, int(cost.get('bp', 0) or 0))
    bp_available = (
        max(0, int(budget.get('bp', 0) or 0)) +
        (max(0, int(income.get('bp', 0) or 0)) * horizon_extra_years)
    )
    if bp_need > bp_available:
        return False

    for key in ALL_RESOURCE_KEYS:
        need = max(0, int(cost.get(key, 0) or 0))
        available = (
            max(0, int(budget.get(key, 0) or 0)) +
            (max(0, int(income.get(key, 0) or 0)) * horizon_extra_years)
        )
        if need > available:
            return False
    return True


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
    for key in ALL_RESOURCE_KEYS:
        demand = (
            int(getattr(star, 'queue_%s' % key, 0) or 0) +
            max(0, int(cost.get(key, 0) or 0)) * int(reserve_factor or 0)
        )
        if demand > int(getattr(star, '%s_inventory' % key, 0) or 0):
            return False
    return True


def _ordered_support_balance_candidates(star):
    """Return support orders that bring labs/defenses back toward factory parity."""
    current_factories = int(getattr(star, 'factories', 0) or 0)
    if current_factories <= 0:
        return []
    support_gaps = [
        (
            'BUILD_LAB',
            max(
                0,
                current_factories - (int(getattr(star, 'labs', 0) or 0) * 2),
            ),
        ),
        (
            'BUILD_DEFENSE',
            max(
                0,
                current_factories - (int(getattr(star, 'defenses', 0) or 0) * 2),
            ),
        ),
    ]
    support_gaps.sort(key=lambda item: (-item[1], item[0]))
    return [
        order_type for order_type, gap in support_gaps
        if gap > 0
    ]


def _mechanical_growth_candidate_orders(player, star, tier):
    if int(tier or 0) < TIER_MECHANICAL_GROWTH:
        return 'none', []
    race_type = getattr(player, 'race_type', None)
    if race_type is None or not bool(getattr(race_type, 'is_mechanical', False)):
        return 'none', []
    if int(getattr(star, 'planned_colonist_growth_orders', 0) or 0) > 0:
        return 'none', []
    employment_pct = float(calculate_staffing_ratio(star) * 100.0)
    if employment_pct >= MECHANICAL_GROWTH_EMPLOYMENT_TOP:
        return 'top', ['BUILD_COLONISTS_1M', 'BUILD_COLONISTS_1K']
    if employment_pct >= MECHANICAL_GROWTH_EMPLOYMENT_MIN:
        return 'normal', ['BUILD_COLONISTS_1K', 'BUILD_COLONISTS_1M']
    return 'none', []


def get_micromanager_candidate_orders(
    player,
    star,
    tier,
    fleets_in_orbit=0,
    terraform_available=False,
    terraform_used=False,
    dyson_available=False,
    cost_map=None,
    administration_active=None,
):
    """Return candidate automatic production orders in priority order."""
    if int(tier or 0) <= 0:
        return []
    if administration_active is None:
        administration_active = bool(getattr(star, 'has_administration', False))
    if not bool(administration_active):
        return []
    thresholds = _projected_job_thresholds(player, star)
    current_jobs = _job_capacity(star)
    candidates = []

    def append_candidate(order_type):
        candidates.append(order_type)
    current_mines = int(getattr(star, 'mines', 0) or 0)
    current_factories = int(getattr(star, 'factories', 0) or 0)
    current_shipyards = int(getattr(star, 'shipyards', 0) or 0)
    shipyard_target = max(1, int(fleets_in_orbit or 0))
    max_mines = safe_mine_count(star)
    if int(tier or 0) == TIER_BASIC:
        mine_room = max_mines > 0
    else:
        mine_room = current_mines < max_mines
    needs_jobs = current_jobs < thresholds['target_jobs']
    queue_pressure = {'mines': False, 'factories': False}
    filler_order_types = LEVEL_ONE_FILLER_ORDER_TYPES
    support_balance_candidates = []
    if int(tier or 0) >= TIER_SUPPORT:
        queue_pressure = _queue_throughput_pressure(star)
        support_balance_candidates = _ordered_support_balance_candidates(star)
    level_one_support_candidates = []
    growth_priority, growth_candidates = _mechanical_growth_candidate_orders(
        player,
        star,
        tier,
    )
    if growth_priority == 'top':
        for order_type in growth_candidates:
            append_candidate(order_type)
    if (
        needs_jobs and
        int(tier or 0) >= TIER_TERRAFORM and
        dyson_available and
        _can_add_order_without_exceeding_max_jobs(
            player, star, DYSON_SPHERE_ORDER_TYPE
        ) and
        not bool(getattr(star, 'has_dyson_sphere', False))
    ):
        append_candidate(DYSON_SPHERE_ORDER_TYPE)
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
        if growth_priority == 'normal':
            for order_type in growth_candidates:
                append_candidate(order_type)

        if int(tier or 0) >= TIER_SUPPORT:
            if queue_pressure.get('factories'):
                append_candidate('BUILD_FACTORY')
            if _can_add_jobs_without_breaking_limit(
                player, star, 'BUILD_SHIPYARD'
            ) and _can_add_order_without_exceeding_max_jobs(
                player, star, 'BUILD_SHIPYARD'
            ) and current_shipyards < shipyard_target:
                append_candidate('BUILD_SHIPYARD')
            if support_balance_candidates:
                for order_type in support_balance_candidates:
                    if _can_add_jobs_without_breaking_limit(
                        player, star, order_type
                    ):
                        append_candidate(order_type)
            else:
                append_candidate('BUILD_FACTORY')
            if queue_pressure.get('mines') and mine_room:
                append_candidate('BUILD_MINE')
            if mine_room and current_mines < (current_factories + 1) * 2:
                append_candidate('BUILD_MINE')
        elif mine_room:
            if queue_pressure.get('factories'):
                append_candidate('BUILD_FACTORY')
            if current_mines < (current_factories + 1) * 2:
                append_candidate('BUILD_MINE')
                append_candidate('BUILD_FACTORY')
            else:
                append_candidate('BUILD_FACTORY')
                append_candidate('BUILD_MINE')
        else:
            if int(tier or 0) >= TIER_SUPPORT:
                if _can_add_jobs_without_breaking_limit(
                    player, star, 'BUILD_SHIPYARD'
                ) and _can_add_order_without_exceeding_max_jobs(
                    player, star, 'BUILD_SHIPYARD'
                ) and current_shipyards < shipyard_target:
                    append_candidate('BUILD_SHIPYARD')
                if (
                    int(getattr(star, 'defenses', 0) or 0) <
                    LEVEL_TWO_DEFENSE_FLOOR and
                    _can_add_jobs_without_breaking_limit(
                        player, star, 'BUILD_DEFENSE'
                    )
                ):
                    append_candidate('BUILD_DEFENSE')
                if (
                    int(getattr(star, 'labs', 0) or 0) <
                    LEVEL_TWO_LAB_FLOOR and
                    _can_add_jobs_without_breaking_limit(
                        player, star, 'BUILD_LAB'
                    )
                ):
                    append_candidate('BUILD_LAB')
            if queue_pressure.get('factories'):
                append_candidate('BUILD_FACTORY')
            for order_type in filler_order_types:
                append_candidate(order_type)
            for order_type in level_one_support_candidates:
                append_candidate(order_type)
    else:
        if growth_priority == 'normal':
            for order_type in growth_candidates:
                append_candidate(order_type)
        if queue_pressure.get('mines') and mine_room:
            append_candidate('BUILD_MINE')
        if queue_pressure.get('factories'):
            append_candidate('BUILD_FACTORY')
        if int(tier or 0) >= TIER_SUPPORT:
            if (
                int(getattr(star, 'shipyards', 0) or 0) < int(fleets_in_orbit or 0) and
                _can_add_jobs_without_breaking_limit(player, star, 'BUILD_SHIPYARD') and
                _can_add_order_without_exceeding_max_jobs(
                    player, star, 'BUILD_SHIPYARD'
                )
            ):
                append_candidate('BUILD_SHIPYARD')
            if support_balance_candidates:
                for order_type in support_balance_candidates:
                    if _can_add_jobs_without_breaking_limit(
                        player, star, order_type
                    ):
                        append_candidate(order_type)
            elif not queue_pressure.get('factories'):
                append_candidate('BUILD_FACTORY')
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
        player_id=getattr(star, 'player_id', None),
        colonists=int(getattr(star, 'colonists', 0) or 0),
        base_capacity=int(getattr(star, 'base_capacity', 0) or 0),
        mines=int(getattr(star, 'mines', 0) or 0),
        factories=int(getattr(star, 'factories', 0) or 0),
        labs=int(getattr(star, 'labs', 0) or 0),
        defenses=int(getattr(star, 'defenses', 0) or 0),
        shipyards=int(getattr(star, 'shipyards', 0) or 0),
        has_dyson_sphere=bool(getattr(star, 'has_dyson_sphere', False)),
        planned_colonist_growth_orders=0,
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
    try:
        terraforming_multiplier = float(
            getattr(
                getattr(player, 'race_type', None),
                'terraforming_multiplier',
                1.0,
            ) or 1.0
        )
    except (TypeError, ValueError):
        terraforming_multiplier = 1.0
    effective_terraform_rate = max(
        0.0,
        float(terraform_rate or 0.0) * terraforming_multiplier,
    )
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
    elif order_type == DYSON_SPHERE_ORDER_TYPE:
        star_state.has_dyson_sphere = True
    elif order_type == 'BUILD_COLONISTS_1K':
        star_state.colonists += 1000
        star_state.planned_colonist_growth_orders = int(
            getattr(star_state, 'planned_colonist_growth_orders', 0) or 0
        ) + 1
    elif order_type == 'BUILD_COLONISTS_1M':
        star_state.colonists += 1000000
        star_state.planned_colonist_growth_orders = int(
            getattr(star_state, 'planned_colonist_growth_orders', 0) or 0
        ) + 1
    elif order_type == 'TERRAFORM_GRAVITY':
        distance = float(getattr(player, 'gravity_center', 0.0) or 0.0) - star_state.gravity
        star_state.gravity += distance * effective_terraform_rate
    elif order_type == 'TERRAFORM_TEMPERATURE':
        distance = (
            float(getattr(player, 'temperature_center', 0.0) or 0.0) -
            star_state.temperature
        )
        star_state.temperature += distance * effective_terraform_rate
    elif order_type == 'TERRAFORM_RADIATION':
        distance = (
            float(getattr(player, 'radiation_center', 0.0) or 0.0) -
            star_state.radiation
        )
        star_state.radiation += distance * effective_terraform_rate


def plan_micromanager_orders(
    player,
    star,
    tier,
    fleets_in_orbit=0,
    terraform_available=False,
    terraform_rate=0.0,
    dyson_available=False,
    preplanned_orders=None,
    cost_map=None,
    queue_requirements=None,
    limit=12,
    administration_active=None,
):
    """Plan queued Micromanager orders for one colony."""
    if int(tier or 0) <= 0:
        return []
    if administration_active is None:
        administration_active = bool(getattr(star, 'has_administration', False))
    if not bool(administration_active):
        return []
    projected = _project_star_state(
        star,
        queue_requirements=queue_requirements,
    )
    planning_budget = _one_year_planning_budget(
        player,
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
    plan_limit = _planning_limit_for_star(player, projected, limit)
    for _ in range(plan_limit):
        candidates = get_micromanager_candidate_orders(
            player,
            projected,
            tier,
            fleets_in_orbit=fleets_in_orbit,
            terraform_available=terraform_available,
            terraform_used=terraform_used,
            dyson_available=dyson_available,
            cost_map=cost_map,
            administration_active=administration_active,
        )
        if not candidates:
            break
        selected = None
        one_year_income = _one_year_income(projected)
        for candidate in candidates:
            if candidate in ('BUILD_SHIPYARD', DYSON_SPHERE_ORDER_TYPE):
                if not _can_add_order_without_exceeding_max_jobs(
                    player, projected, candidate
                ):
                    continue
            if (
                not _ignores_planning_budget_caps(candidate) and
                not _can_afford_from_budget(cost_map, planning_budget, candidate)
            ):
                if (
                    candidate == 'BUILD_SHIPYARD' and
                    _can_complete_within_years(
                        cost_map,
                        planning_budget,
                        one_year_income,
                        candidate,
                        SHIPYARD_COMPLETION_MAX_YEARS,
                    )
                ):
                    selected = candidate
                    break
                if (
                    candidate == DYSON_SPHERE_ORDER_TYPE and
                    _can_complete_within_years(
                        cost_map,
                        planning_budget,
                        one_year_income,
                        candidate,
                        DYSON_COMPLETION_MAX_YEARS,
                    )
                ):
                    selected = candidate
                    break
                continue
            selected = candidate
            break
        if selected is None:
            # Tier-2/3 may surface support-only candidate sets. If none of
            # those are affordable, allow an initial factory bootstrap so the
            # queue does not go empty while still preserving support priority.
            if (
                not planned and
                not existing and
                'BUILD_FACTORY' not in candidates and
                _can_add_jobs_without_breaking_limit(
                    player, projected, 'BUILD_FACTORY'
                ) and
                _can_afford_from_budget(
                    cost_map, planning_budget, 'BUILD_FACTORY'
                )
            ):
                selected = 'BUILD_FACTORY'
            else:
                break
        planned.append(selected)
        _spend_budget(cost_map, planning_budget, selected)
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


def collapse_micromanager_order_totals(order_types):
    """Collapse all identical order types into one row, keeping first order."""
    totals = []
    positions = {}
    for order_type in list(order_types or []):
        if order_type not in positions:
            positions[order_type] = len(totals)
            totals.append([order_type, 1])
            continue
        totals[positions[order_type]][1] += 1
    return [(order_type, quantity) for order_type, quantity in totals]
