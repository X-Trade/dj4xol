from __future__ import unicode_literals

from math import ceil
from types import SimpleNamespace

from .colony_rules import (
    CITY_JOBS,
    COLONISTS_PER_JOB,
    COLONISTS_PER_SHIPYARD,
    DYSON_SPHERE_JOBS,
    KT_PER_MINE,
    MEGACITY_JOBS,
    calculate_available_buildpoints,
    calculate_growth_factor,
    calculate_productivity_multiplier,
    calculate_staffing_ratio,
    calculate_total_jobs,
    limit_population_growth_by_surface_resources,
    population_growth_uses_surface_resources,
)
from .mineral_rules import ALL_RESOURCE_KEYS
from .production_rules import (
    MINE_BUILD_CAP,
    production_infrastructure_cap,
    production_infrastructure_count,
)


JOB_MIN_RATIO = 0.25
JOB_TARGET_RATIO = 0.50
JOB_MAX_RATIO = 0.75

MICROMANAGER_MODE_STANDARD = 'standard'
MICROMANAGER_MODE_EXPANSIONIST = 'expansionist'
EXPANSIONIST_MINE_TARGET_MULTIPLIER = 1.75

TIER_BASIC = 1
TIER_SUPPORT = 2
TIER_TERRAFORM = 3
TIER_MECHANICAL_GROWTH = 4

MECHANICAL_GROWTH_EMPLOYMENT_MIN = 45.0
MECHANICAL_GROWTH_EMPLOYMENT_TOP = 90.0

ADMINISTRATION_ORDER_TYPE = 'BUILD_ADMINISTRATION'
REMOVE_ADMINISTRATION_ORDER_TYPE = 'REMOVE_ADMINISTRATION'
DYSON_SPHERE_ORDER_TYPE = 'BUILD_DYSON_SPHERE'
CITY_ORDER_TYPE = 'BUILD_CITY'
MEGACITY_ORDER_TYPE = 'BUILD_MEGACITY'
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


def _normalize_micromanager_mode(micromanager_mode):
    if str(micromanager_mode or '').strip().lower() == MICROMANAGER_MODE_EXPANSIONIST:
        return MICROMANAGER_MODE_EXPANSIONIST
    return MICROMANAGER_MODE_STANDARD


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


def _total_mineral_yield(star):
    total_yield = 0
    for key in ALL_RESOURCE_KEYS:
        total_yield += int(getattr(star, '%s_yield' % key, 0) or 0)
    return int(total_yield)


def _safe_ratio(numerator, denominator, default=0.0):
    denominator = float(denominator or 0.0)
    if denominator <= 0.0:
        return float(default)
    return float(numerator or 0.0) / denominator


def _clamp(value, minimum=0.0, maximum=1.0):
    return max(float(minimum), min(float(maximum), float(value or 0.0)))


def _job_fill_ratio(player, star):
    projected_population = int(_projected_population(player, star) or 0)
    if projected_population <= 0:
        return 1.0
    return _safe_ratio(_job_capacity(star), projected_population, default=1.0)


def _mine_fill_ratio(star):
    max_mines = int(safe_mine_count(star) or 0)
    if max_mines <= 0:
        return 1.0
    return _safe_ratio(int(getattr(star, 'mines', 0) or 0), max_mines, default=1.0)


def _target_mine_count(star, micromanager_mode=MICROMANAGER_MODE_STANDARD):
    micromanager_mode = _normalize_micromanager_mode(micromanager_mode)
    safe_count = int(safe_mine_count(star) or 0)
    if safe_count <= 0:
        return 0
    if micromanager_mode != MICROMANAGER_MODE_EXPANSIONIST:
        return min(MINE_BUILD_CAP, safe_count)
    target = max(
        safe_count,
        int(ceil(float(safe_count) * EXPANSIONIST_MINE_TARGET_MULTIPLIER)),
    )
    return min(MINE_BUILD_CAP, target)


def _target_mine_fill_ratio(star, micromanager_mode=MICROMANAGER_MODE_STANDARD):
    target_mines = int(_target_mine_count(star, micromanager_mode=micromanager_mode) or 0)
    if target_mines <= 0:
        return 1.0
    return _safe_ratio(int(getattr(star, 'mines', 0) or 0), target_mines, default=1.0)


def _support_gap_scores(star):
    current_factories = int(getattr(star, 'factories', 0) or 0)
    if current_factories <= 0:
        return {}
    return {
        'BUILD_LAB': max(
            0,
            current_factories - (int(getattr(star, 'labs', 0) or 0) * 2),
        ),
        'BUILD_DEFENSE': max(
            0,
            current_factories - (int(getattr(star, 'defenses', 0) or 0) * 2),
        ),
    }


def _mature_support_balance_factor(star, tier):
    if int(tier or 0) < TIER_TERRAFORM:
        return 0.5
    if int(getattr(star, 'factories', 0) or 0) < 20:
        return 0.5
    if _mine_fill_ratio(star) < 0.50:
        return 0.5
    if int(tier or 0) >= TIER_MECHANICAL_GROWTH:
        return 1.0
    return 0.75


def _balanced_lab_target(star, tier):
    balance_factor = _mature_support_balance_factor(star, tier)
    return int(ceil(
        float(int(getattr(star, 'factories', 0) or 0)) * float(balance_factor)
    ))


def _factory_balance_penalty(star, tier):
    balance_factor = _mature_support_balance_factor(star, tier)
    if balance_factor <= 0.5:
        return 1.0
    factory_jobs = int(getattr(star, 'factories', 0) or 0) * COLONISTS_PER_JOB
    if factory_jobs <= 0:
        return 1.0
    target_jobs = max(1, int(ceil(float(factory_jobs) * float(balance_factor))))
    lab_jobs = int(getattr(star, 'labs', 0) or 0) * COLONISTS_PER_JOB
    shipyard_jobs = (
        int(getattr(star, 'shipyards', 0) or 0) * COLONISTS_PER_SHIPYARD
    )
    support_ratio = min(
        _safe_ratio(lab_jobs, target_jobs, default=1.0),
        _safe_ratio(shipyard_jobs, target_jobs, default=1.0),
    )
    return 0.35 + (0.65 * _clamp(support_ratio))


def _support_gap_scores_for_tier(star, tier):
    current_factories = int(getattr(star, 'factories', 0) or 0)
    if current_factories <= 0:
        return {}
    return {
        'BUILD_LAB': max(
            0,
            _balanced_lab_target(star, tier) -
            int(getattr(star, 'labs', 0) or 0),
        ),
        'BUILD_DEFENSE': max(
            0,
            current_factories - (int(getattr(star, 'defenses', 0) or 0) * 2),
        ),
    }


def _mine_bootstrap_pressure(star, micromanager_mode=MICROMANAGER_MODE_STANDARD):
    mine_ratio = _target_mine_fill_ratio(
        star,
        micromanager_mode=micromanager_mode,
    )
    if mine_ratio < 0.50:
        return 1.0
    if mine_ratio >= 1.0:
        return 0.0
    return _clamp((1.0 - mine_ratio) / 0.50)


def _employment_job_build_tailoff(job_ratio):
    ratio = float(job_ratio or 0.0)
    if ratio <= JOB_TARGET_RATIO:
        return 1.0
    if ratio >= JOB_MAX_RATIO:
        return 0.0
    return _clamp(
        (JOB_MAX_RATIO - ratio) / (JOB_MAX_RATIO - JOB_TARGET_RATIO)
    )


def _job_capacity_after(star, order_type):
    extra = int(_jobs_added_by_order(order_type) or 0)
    return _job_capacity(star) + max(0, extra)


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
    if order_type == CITY_ORDER_TYPE:
        return CITY_JOBS
    if order_type == MEGACITY_ORDER_TYPE:
        return MEGACITY_JOBS
    return 0


def _can_queue_job_expansion(player, star, order_type):
    if int(_jobs_added_by_order(order_type) or 0) <= 0:
        return True
    return _can_add_jobs_without_breaking_limit(player, star, order_type)


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


def _order_has_infrastructure_room(star, order_type):
    cap = production_infrastructure_cap(order_type)
    if cap is None:
        return True
    count = production_infrastructure_count(star, order_type)
    if count is None:
        return True
    return int(count) < int(cap)


def safe_mine_count(star):
    total_yield = _total_mineral_yield(star)
    if total_yield <= 0:
        return 0
    staffing_ratio = calculate_staffing_ratio(star)
    productivity = calculate_productivity_multiplier(staffing_ratio)
    if productivity <= 0:
        productivity = 1.0
    sustainable = float(total_yield) / float(KT_PER_MINE * productivity)
    if sustainable <= 0:
        return 0
    return min(MINE_BUILD_CAP, int(sustainable))


def projected_mining_output(star):
    """Estimate one year of mining output for a real or projected colony."""
    rates = {}
    total_yield = _total_mineral_yield(star)
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


def _planning_limit_for_star(
    player,
    star,
    limit,
    tier=1,
    micromanager_mode=MICROMANAGER_MODE_STANDARD,
):
    """Return a deeper queue target when jobs or extraction are underbuilt."""
    micromanager_mode = _normalize_micromanager_mode(micromanager_mode)
    expansionist_mode = micromanager_mode == MICROMANAGER_MODE_EXPANSIONIST
    plan_limit = max(0, int(limit or 0))
    thresholds = _projected_job_thresholds(player, star)
    current_jobs = _job_capacity(star)
    target_mines = int(_target_mine_count(star, micromanager_mode=micromanager_mode) or 0)
    if int(tier or 0) <= TIER_BASIC:
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

    job_ratio = _job_fill_ratio(player, star)
    if job_ratio < JOB_MIN_RATIO:
        missing_jobs = thresholds['min_jobs'] - current_jobs
        catchup_limit = (
            missing_jobs + COLONISTS_PER_JOB - 1
        ) // COLONISTS_PER_JOB
        return max(plan_limit, min(1000, int(catchup_limit)))
    if job_ratio < 0.40:
        missing_jobs = thresholds['target_jobs'] - current_jobs
        catchup_limit = (
            missing_jobs + COLONISTS_PER_JOB - 1
        ) // COLONISTS_PER_JOB
        cap = 60 if int(tier or 0) >= TIER_MECHANICAL_GROWTH else 36
        if expansionist_mode:
            cap = int(ceil(float(cap) * 1.5))
        return max(plan_limit, min(cap, int(catchup_limit)))
    if job_ratio < JOB_TARGET_RATIO:
        missing_jobs = thresholds['target_jobs'] - current_jobs
        catchup_limit = (
            missing_jobs + COLONISTS_PER_JOB - 1
        ) // COLONISTS_PER_JOB
        cap = 24 if int(tier or 0) >= TIER_MECHANICAL_GROWTH else 12
        if expansionist_mode:
            cap = int(ceil(float(cap) * 1.5))
        return max(plan_limit, min(cap, int(catchup_limit)))

    mine_ratio = _target_mine_fill_ratio(star, micromanager_mode=micromanager_mode)
    max_mines = target_mines
    if max_mines > 0 and mine_ratio < 0.50:
        missing_mines = max(0, int((max_mines * 0.50) - int(getattr(star, 'mines', 0) or 0)))
        cap = 18 if int(tier or 0) >= TIER_MECHANICAL_GROWTH else 10
        if expansionist_mode:
            cap = int(ceil(float(cap) * 1.5))
        return max(plan_limit, min(cap, max(1, missing_mines)))
    if expansionist_mode and max_mines > 0 and mine_ratio < 0.90:
        missing_mines = max(
            0,
            int((max_mines * 0.90) - int(getattr(star, 'mines', 0) or 0)),
        )
        return max(plan_limit, min(32, max(1, missing_mines)))
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


def _ordered_support_balance_candidates(star, tier):
    """Return support orders that bring labs/defenses back toward factory parity."""
    support_gaps = list(_support_gap_scores_for_tier(star, tier).items())
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


def _scored_micromanager_candidate_orders(
    player,
    star,
    tier,
    fleets_in_orbit=0,
    terraform_available=False,
    terraform_used=False,
    dyson_available=False,
    city_available=False,
    megacity_available=False,
    cost_map=None,
    micromanager_mode=MICROMANAGER_MODE_STANDARD,
):
    micromanager_mode = _normalize_micromanager_mode(micromanager_mode)
    expansionist_mode = micromanager_mode == MICROMANAGER_MODE_EXPANSIONIST
    thresholds = _projected_job_thresholds(player, star)
    current_jobs = _job_capacity(star)
    current_mines = int(getattr(star, 'mines', 0) or 0)
    current_factories = int(getattr(star, 'factories', 0) or 0)
    current_shipyards = int(getattr(star, 'shipyards', 0) or 0)
    shipyard_target = max(
        1,
        int(fleets_in_orbit or 0),
    )
    max_mines = int(_target_mine_count(star, micromanager_mode=micromanager_mode) or 0)
    has_yield = _total_mineral_yield(star) > 0
    mine_room = (
        has_yield and
        current_mines < max_mines and
        current_mines < MINE_BUILD_CAP
    )
    queue_pressure = _queue_throughput_pressure(star)
    support_gap_scores = _support_gap_scores_for_tier(star, tier)
    job_ratio = _job_fill_ratio(player, star)
    mine_ratio = _target_mine_fill_ratio(star, micromanager_mode=micromanager_mode)
    bootstrap_pressure = _mine_bootstrap_pressure(
        star,
        micromanager_mode=micromanager_mode,
    )
    extraction_ready = 1.0 - bootstrap_pressure
    job_build_tailoff = _employment_job_build_tailoff(job_ratio)
    high_employment = job_ratio >= JOB_MAX_RATIO
    factory_balance_penalty = _factory_balance_penalty(star, tier)
    candidates = {}
    first_seen = {}

    def append_candidate(order_type, score):
        score = float(score or 0.0)
        if score <= 0.0:
            return
        if not _order_has_infrastructure_room(star, order_type):
            return
        if order_type not in first_seen:
            first_seen[order_type] = len(first_seen)
            candidates[order_type] = 0.0
        candidates[order_type] += score

    growth_priority, growth_candidates = _mechanical_growth_candidate_orders(
        player,
        star,
        tier,
    )
    if growth_priority == 'top':
        for idx, order_type in enumerate(growth_candidates):
            score = 1200.0 - (idx * 20.0)
            if expansionist_mode:
                score += 120.0
            append_candidate(
                order_type,
                score,
            )
    elif growth_priority == 'normal':
        growth_score = 120.0 + ((1.0 - job_build_tailoff) * 280.0)
        if high_employment:
            growth_score = 1000.0
        if expansionist_mode:
            growth_score = (growth_score * 1.35) + 60.0
        for idx, order_type in enumerate(growth_candidates):
            append_candidate(
                order_type,
                growth_score - (idx * 20.0),
            )

    if (
        job_ratio < JOB_TARGET_RATIO and
        int(tier or 0) >= TIER_TERRAFORM and
        dyson_available and
        _can_add_order_without_exceeding_max_jobs(
            player, star, DYSON_SPHERE_ORDER_TYPE
        ) and
        not bool(getattr(star, 'has_dyson_sphere', False))
    ):
        append_candidate(DYSON_SPHERE_ORDER_TYPE, 180.0)

    if (
        int(tier or 0) >= TIER_SUPPORT and
        job_ratio < JOB_TARGET_RATIO
    ):
        jobs_shortfall = max(0, int(thresholds['target_jobs'] - current_jobs))
        shortfall_ratio = _clamp(
            _safe_ratio(
                jobs_shortfall,
                max(1, int(thresholds['target_jobs'] or 0)),
                default=0.0,
            )
        )
        if (
            city_available and
            _can_add_jobs_without_breaking_limit(player, star, CITY_ORDER_TYPE) and
            _can_add_order_without_exceeding_max_jobs(player, star, CITY_ORDER_TYPE)
        ):
            city_score = 70.0 + (shortfall_ratio * 120.0)
            if current_jobs < thresholds['min_jobs']:
                city_score += 30.0
            if bootstrap_pressure >= 1.0:
                city_score *= 0.85
            elif bootstrap_pressure > 0.0:
                city_score *= 0.92
            append_candidate(CITY_ORDER_TYPE, city_score)
        if (
            megacity_available and
            _can_add_jobs_without_breaking_limit(player, star, MEGACITY_ORDER_TYPE) and
            _can_add_order_without_exceeding_max_jobs(player, star, MEGACITY_ORDER_TYPE)
        ):
            megacity_score = 52.0 + (shortfall_ratio * 105.0)
            if jobs_shortfall >= MEGACITY_JOBS:
                megacity_score += 35.0
            elif jobs_shortfall <= CITY_JOBS:
                megacity_score *= 0.55
            if current_jobs < thresholds['min_jobs']:
                megacity_score += 20.0
            if bootstrap_pressure >= 1.0:
                megacity_score *= 0.80
            elif bootstrap_pressure > 0.0:
                megacity_score *= 0.90
            append_candidate(MEGACITY_ORDER_TYPE, megacity_score)

    if (
        current_mines <= 0 and
        max_mines > 0 and
        _can_queue_job_expansion(player, star, 'BUILD_MINE')
    ):
        append_candidate(
            'BUILD_MINE',
            max(25.0, 300.0 * job_build_tailoff),
        )
    if (
        current_factories <= 0 and
        _can_queue_job_expansion(player, star, 'BUILD_FACTORY')
    ):
        append_candidate(
            'BUILD_FACTORY',
            max(25.0, 280.0 * job_build_tailoff),
        )

    if mine_room and _can_queue_job_expansion(player, star, 'BUILD_MINE'):
        mine_score = 0.0
        if mine_ratio < 0.50:
            mine_score += 260.0 + ((0.50 - mine_ratio) * 220.0)
        elif mine_ratio < 0.75:
            mine_score += 145.0 + ((0.75 - mine_ratio) * 120.0)
        elif mine_ratio < 1.00:
            mine_score += 40.0 + ((1.00 - mine_ratio) * 55.0)
        if queue_pressure.get('mines'):
            mine_score += 90.0
        if mine_score > 0.0:
            if expansionist_mode:
                if mine_ratio < 0.50:
                    mine_score *= 1.75
                elif mine_ratio < 0.90:
                    mine_score *= 1.45
                else:
                    mine_score *= 1.20
            append_candidate('BUILD_MINE', mine_score * job_build_tailoff)

    if (
        _can_queue_job_expansion(player, star, 'BUILD_FACTORY') and
        job_ratio < JOB_MIN_RATIO
    ):
        append_candidate(
            'BUILD_FACTORY',
            (
                220.0 + ((JOB_MIN_RATIO - job_ratio) * 260.0) +
                (extraction_ready * 40.0)
            ) * job_build_tailoff * factory_balance_penalty * (
                1.20 if expansionist_mode else 1.0
            ),
        )
    elif (
        _can_queue_job_expansion(player, star, 'BUILD_FACTORY') and
        job_ratio < 0.40
    ):
        append_candidate(
            'BUILD_FACTORY',
            (
                135.0 + ((0.40 - job_ratio) * 150.0) +
                (extraction_ready * 25.0)
            ) * job_build_tailoff * factory_balance_penalty * (
                1.15 if expansionist_mode else 1.0
            ),
        )
    elif (
        _can_queue_job_expansion(player, star, 'BUILD_FACTORY') and
        job_ratio < JOB_TARGET_RATIO
    ):
        append_candidate(
            'BUILD_FACTORY',
            (
                80.0 + ((JOB_TARGET_RATIO - job_ratio) * 90.0) +
                (extraction_ready * 20.0)
            ) * job_build_tailoff * factory_balance_penalty * (
                1.10 if expansionist_mode else 1.0
            ),
        )
    elif (
        _can_queue_job_expansion(player, star, 'BUILD_FACTORY') and
        queue_pressure.get('factories')
    ):
        append_candidate(
            'BUILD_FACTORY',
            90.0 * job_build_tailoff * factory_balance_penalty,
        )
    elif (
        _can_queue_job_expansion(player, star, 'BUILD_FACTORY') and
        job_ratio < JOB_MAX_RATIO
    ):
        append_candidate(
            'BUILD_FACTORY',
            (
                12.0 + (extraction_ready * 10.0)
            ) * job_build_tailoff * factory_balance_penalty,
        )

    if int(tier or 0) >= TIER_SUPPORT:
        for idx, order_type in enumerate(_ordered_support_balance_candidates(star, tier)):
            gap_score = float(support_gap_scores.get(order_type, 0) or 0)
            if gap_score <= 0:
                continue
            if not _can_queue_job_expansion(player, star, order_type):
                continue
            support_pressure = _clamp(
                _safe_ratio(gap_score, max(1, current_factories), default=0.0)
            )
            base_score = (
                80.0 +
                min(80.0, gap_score * 4.0) +
                (support_pressure * 140.0)
            )
            if current_factories >= 100 and support_pressure >= 0.50:
                base_score += 90.0
            if job_ratio < JOB_MIN_RATIO:
                base_score *= 0.75
            elif job_ratio < JOB_TARGET_RATIO:
                base_score *= 0.80
            if bootstrap_pressure >= 1.0:
                base_score *= 0.55
            elif bootstrap_pressure > 0.0:
                base_score *= 0.75
            if expansionist_mode and (
                bootstrap_pressure > 0.0 or job_ratio >= JOB_TARGET_RATIO
            ):
                base_score *= 0.75
            append_candidate(order_type, base_score - (idx * 5.0))

        shipyard_deficit = max(0, shipyard_target - current_shipyards)
        if (
            shipyard_deficit > 0 and
            _can_add_jobs_without_breaking_limit(player, star, 'BUILD_SHIPYARD') and
            _can_add_order_without_exceeding_max_jobs(
                player, star, 'BUILD_SHIPYARD'
            )
        ):
            shipyard_score = 15.0 + (shipyard_deficit * 16.0)
            if job_ratio < JOB_MIN_RATIO:
                shipyard_score += 40.0
            elif job_ratio < 0.40:
                shipyard_score += 25.0
            elif job_ratio < JOB_TARGET_RATIO:
                shipyard_score += 12.0
            elif job_ratio < JOB_MAX_RATIO:
                shipyard_score += 5.0
            if bootstrap_pressure >= 1.0:
                shipyard_score *= 0.35
            elif bootstrap_pressure > 0.0:
                shipyard_score *= 0.60
            if expansionist_mode and current_shipyards > 0:
                shipyard_score *= 0.70
            append_candidate('BUILD_SHIPYARD', shipyard_score)

        if (
            not support_gap_scores and
            not queue_pressure.get('factories') and
            _can_queue_job_expansion(player, star, 'BUILD_FACTORY')
        ):
            append_candidate('BUILD_FACTORY', 12.0)

    if (
        int(tier or 0) >= TIER_TERRAFORM and
        terraform_available and
        not terraform_used and
        current_jobs >= thresholds['min_jobs']
    ):
        terraform_order = preferred_terraform_order(player, star)
        if terraform_order:
            append_candidate(terraform_order, 85.0)

    ranked = sorted(
        candidates.items(),
        key=lambda item: (-item[1], first_seen[item[0]], item[0]),
    )
    return [order_type for order_type, _score in ranked]


def get_micromanager_candidate_orders(
    player,
    star,
    tier,
    fleets_in_orbit=0,
    terraform_available=False,
    terraform_used=False,
    dyson_available=False,
    city_available=False,
    megacity_available=False,
    cost_map=None,
    administration_active=None,
    micromanager_mode=MICROMANAGER_MODE_STANDARD,
):
    """Return candidate automatic production orders in priority order."""
    micromanager_mode = _normalize_micromanager_mode(micromanager_mode)
    if int(tier or 0) <= 0:
        return []
    if administration_active is None:
        administration_active = bool(getattr(star, 'has_administration', False))
    if not bool(administration_active):
        return []
    if int(tier or 0) > TIER_BASIC:
        return _scored_micromanager_candidate_orders(
            player,
            star,
            tier,
            fleets_in_orbit=fleets_in_orbit,
            terraform_available=terraform_available,
            terraform_used=terraform_used,
            dyson_available=dyson_available,
            city_available=city_available,
            megacity_available=megacity_available,
            cost_map=cost_map,
            micromanager_mode=micromanager_mode,
        )
    thresholds = _projected_job_thresholds(player, star)
    current_jobs = _job_capacity(star)
    candidates = []

    def append_candidate(order_type):
        if not _order_has_infrastructure_room(star, order_type):
            return
        candidates.append(order_type)
    current_mines = int(getattr(star, 'mines', 0) or 0)
    current_factories = int(getattr(star, 'factories', 0) or 0)
    current_shipyards = int(getattr(star, 'shipyards', 0) or 0)
    shipyard_target = max(1, int(fleets_in_orbit or 0))
    max_mines = _target_mine_count(star, micromanager_mode=micromanager_mode)
    has_yield = _total_mineral_yield(star) > 0
    if int(tier or 0) == TIER_BASIC:
        mine_room = (
            has_yield and
            max_mines > 0 and
            current_mines < MINE_BUILD_CAP
        )
    else:
        mine_room = (
            has_yield and
            current_mines < max_mines and
            current_mines < MINE_BUILD_CAP
        )
    needs_jobs = current_jobs < thresholds['target_jobs']
    queue_pressure = {'mines': False, 'factories': False}
    filler_order_types = LEVEL_ONE_FILLER_ORDER_TYPES
    support_balance_candidates = []
    if int(tier or 0) >= TIER_SUPPORT:
        queue_pressure = _queue_throughput_pressure(star)
        support_balance_candidates = _ordered_support_balance_candidates(star, tier)
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
            if support_balance_candidates:
                for order_type in support_balance_candidates:
                    if _can_add_jobs_without_breaking_limit(
                        player, star, order_type
                    ):
                        append_candidate(order_type)
            else:
                append_candidate('BUILD_FACTORY')
            if _can_add_jobs_without_breaking_limit(
                player, star, 'BUILD_SHIPYARD'
            ) and _can_add_order_without_exceeding_max_jobs(
                player, star, 'BUILD_SHIPYARD'
            ) and current_shipyards < shipyard_target:
                append_candidate('BUILD_SHIPYARD')
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
                if _can_add_jobs_without_breaking_limit(
                    player, star, 'BUILD_SHIPYARD'
                ) and _can_add_order_without_exceeding_max_jobs(
                    player, star, 'BUILD_SHIPYARD'
                ) and current_shipyards < shipyard_target:
                    append_candidate('BUILD_SHIPYARD')
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
            if support_balance_candidates:
                for order_type in support_balance_candidates:
                    if _can_add_jobs_without_breaking_limit(
                        player, star, order_type
                    ):
                        append_candidate(order_type)
            elif not queue_pressure.get('factories'):
                append_candidate('BUILD_FACTORY')
            if (
                int(getattr(star, 'shipyards', 0) or 0) < int(fleets_in_orbit or 0) and
                _can_add_jobs_without_breaking_limit(player, star, 'BUILD_SHIPYARD') and
                _can_add_order_without_exceeding_max_jobs(
                    player, star, 'BUILD_SHIPYARD'
                )
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
        player_id=getattr(star, 'player_id', None),
        colonists=int(getattr(star, 'colonists', 0) or 0),
        base_capacity=int(getattr(star, 'base_capacity', 0) or 0),
        mines=int(getattr(star, 'mines', 0) or 0),
        factories=int(getattr(star, 'factories', 0) or 0),
        labs=int(getattr(star, 'labs', 0) or 0),
        defenses=int(getattr(star, 'defenses', 0) or 0),
        shipyards=int(getattr(star, 'shipyards', 0) or 0),
        cities=int(getattr(star, 'cities', 0) or 0),
        megacities=int(getattr(star, 'megacities', 0) or 0),
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
        if _order_has_infrastructure_room(star_state, order_type):
            star_state.mines += 1
    elif order_type == 'BUILD_FACTORY':
        if _order_has_infrastructure_room(star_state, order_type):
            star_state.factories += 1
    elif order_type == 'BUILD_LAB':
        if _order_has_infrastructure_room(star_state, order_type):
            star_state.labs += 1
    elif order_type == 'BUILD_DEFENSE':
        if _order_has_infrastructure_room(star_state, order_type):
            star_state.defenses += 1
    elif order_type == 'BUILD_SHIPYARD':
        if _order_has_infrastructure_room(star_state, order_type):
            star_state.shipyards += 1
    elif order_type == CITY_ORDER_TYPE:
        if _order_has_infrastructure_room(star_state, order_type):
            star_state.cities += 1
    elif order_type == MEGACITY_ORDER_TYPE:
        if _order_has_infrastructure_room(star_state, order_type):
            star_state.megacities += 1
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
    city_available=False,
    megacity_available=False,
    preplanned_orders=None,
    cost_map=None,
    queue_requirements=None,
    limit=12,
    administration_active=None,
    micromanager_mode=MICROMANAGER_MODE_STANDARD,
):
    """Plan queued Micromanager orders for one colony."""
    micromanager_mode = _normalize_micromanager_mode(micromanager_mode)
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
    plan_limit = _planning_limit_for_star(
        player,
        projected,
        limit,
        tier=tier,
        micromanager_mode=micromanager_mode,
    )

    def pick_candidate(candidates, excluded_order_type=None):
        one_year_income = _one_year_income(projected)
        for candidate in candidates:
            if candidate == excluded_order_type:
                continue
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
                    return candidate
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
                    return candidate
                continue
            return candidate
        return None

    for _ in range(plan_limit):
        candidates = get_micromanager_candidate_orders(
            player,
            projected,
            tier,
            fleets_in_orbit=fleets_in_orbit,
            terraform_available=terraform_available,
            terraform_used=terraform_used,
            dyson_available=dyson_available,
            city_available=city_available,
            megacity_available=megacity_available,
            cost_map=cost_map,
            administration_active=administration_active,
            micromanager_mode=micromanager_mode,
        )
        if not candidates:
            break
        selected = pick_candidate(candidates)
        if (
            selected is not None and
            int(tier or 0) >= TIER_SUPPORT and
            len(planned) >= 2 and
            planned[-1] == planned[-2] == selected
        ):
            alternate = pick_candidate(candidates, excluded_order_type=selected)
            if alternate is not None:
                selected = alternate
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
