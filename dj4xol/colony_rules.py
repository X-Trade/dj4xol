import math
from .employment_rules import (
    calculate_total_jobs_count,
    calculate_employment_percent as _employment_percent_from_jobs,
    calculate_staffing_ratio as _staffing_ratio_from_jobs,
    calculate_overemployment_effectiveness,
    calculate_productivity_multiplier as _productivity_multiplier_from_employment,
)

BILLION = 1_000_000_000
MILLION = 1_000_000
DEFAULT_SOFT_CAP = 10 * BILLION   # Fallback if no star capacity
CAPACITY_SCALE_RATIO = 0.5        # Scale is this fraction of soft cap
CAPACITY_HAB_EXPONENT = 8.0       # Nonlinear hab curve: mid-hab worlds stay small

# Economic constants
COLONISTS_PER_JOB = 1000  # Each mine/factory employs this many colonists
COLONISTS_PER_SHIPYARD = 10000  # Shipyards employ 10x more colonists
BUILDPOINTS_PER_FACTORY = 10  # Each factory produces this many buildpoints per turn
RESEARCHPOINTS_PER_LAB = 20  # Each lab produces this many research points per turn
KT_PER_MINE = 10  # Each mine extracts this many kt of minerals per turn
# Baseline depletion per kt extracted. Additional depletion is applied when a
# resource is over-mined (annual extraction exceeds that resource's yield %).
YIELD_DEPLETION_RATE = 0.0001  # 0.01% per kt
OVERMINING_DEPLETION_MULTIPLIER = 1.0
HOMEWORLD_MIN_YIELD = 30  # Homeworld yields never drop below this percentage
DYSON_PRODUCTIVITY_MULTIPLIER = 3.0  # 200% bonus (base + 200%)
DYSON_HABITABILITY_MULTIPLIER = 1.5  # +50% habitability factor
DYSON_SPHERE_JOBS = BILLION  # Active Dyson Sphere provides 1bn jobs
ENVIRONMENT_IGNORE_FIELDS = {
    'gravity': 'ignores_gravity',
    'temperature': 'ignores_temperature',
    'radiation': 'ignores_radiation',
}
DEFAULT_POPULATION_CAP_MULTIPLIER = 1
RESOURCE_LIMIT_GROWTH_STAGE_ONE_MAX = 2000


def has_active_dyson_sphere(star, player=None):
    """Return True when the star's Dyson Sphere should apply for this context."""
    if not star or not bool(getattr(star, 'has_dyson_sphere', False)):
        return False
    owner_id = getattr(star, 'player_id', None)
    if not owner_id:
        return False
    if player is None:
        return True
    return int(owner_id) == int(getattr(player, 'id', 0) or 0)


def calculate_total_jobs(star):
    """Return total colony jobs, including Dyson Sphere staffing demand."""
    if star is None:
        return 0
    return calculate_total_jobs_count(
        getattr(star, 'mines', 0),
        getattr(star, 'factories', 0),
        getattr(star, 'labs', 0),
        getattr(star, 'defenses', 0),
        getattr(star, 'shipyards', 0),
        COLONISTS_PER_JOB,
        COLONISTS_PER_SHIPYARD,
        include_special_jobs=has_active_dyson_sphere(star),
        special_jobs=DYSON_SPHERE_JOBS,
    )


def capacity_modifier(population, soft_cap):
    """Returns a modifier that reduces growth at high populations.

    Uses tanh curve centered at soft_cap:
    - At 10% of cap: ~95% of normal growth
    - At 50% of cap: ~76% of normal growth
    - At soft_cap: 0% growth
    - Above soft_cap: negative growth (population decline)
    - At 200% of cap: ~-96% (rapid decline)
    """
    if soft_cap <= 0:
        return 1.0
    scale = soft_cap * CAPACITY_SCALE_RATIO
    return -math.tanh((population - soft_cap) / scale)


def player_ignores_environment(player, env):
    race_type = getattr(player, 'race_type', None)
    if race_type is None:
        return False
    return bool(getattr(race_type, ENVIRONMENT_IGNORE_FIELDS.get(env, ''), False))


def player_population_cap_multiplier(player):
    race_type = getattr(player, 'race_type', None)
    if race_type is None:
        return float(DEFAULT_POPULATION_CAP_MULTIPLIER)
    raw_value = getattr(
        race_type,
        'population_cap_multiplier',
        DEFAULT_POPULATION_CAP_MULTIPLIER,
    )
    try:
        value = float(raw_value)
    except (TypeError, ValueError):
        value = float(DEFAULT_POPULATION_CAP_MULTIPLIER)
    return max(0.0, value)


def habitability_value_for_environment(player, env, value):
    if player_ignores_environment(player, env):
        return 1.0
    return habitability_proportion(
        player.hab_min(env),
        player.hab_max(env),
        getattr(player, f'{env}_center'),
        value,
    )


def environment_matches_player_preference(player, env, value):
    if player_ignores_environment(player, env):
        return True
    return abs(float(value) - float(getattr(player, f'{env}_center'))) < 1e-9


def population_growth_uses_surface_resources(player):
    race_type = getattr(player, 'race_type', None)
    if race_type is None:
        return False
    return bool(getattr(race_type, 'population_growth_uses_resources', False))


def limit_population_growth_by_surface_resources(star, proposed_growth):
    """Limit positive population growth by surface ironium/boranium availability.

    Rules:
    - The first 2000 added colonists require 1kt ironium per 1000 colonists.
    - Additional colonists require 1kt ironium and 1kt boranium per 2000 colonists.
    """
    growth = max(0, int(proposed_growth or 0))
    if growth <= 0:
        return 0, 0, 0

    available_ironium = max(0, int(getattr(star, 'ironium_inventory', 0) or 0))
    available_boranium = max(0, int(getattr(star, 'boranium_inventory', 0) or 0))

    stage_one_requested = min(growth, RESOURCE_LIMIT_GROWTH_STAGE_ONE_MAX)
    stage_one_growth = min(stage_one_requested, available_ironium * 1000)
    ironium_cost = 0
    if stage_one_growth > 0:
        ironium_cost = min(
            available_ironium,
            int(math.ceil(float(stage_one_growth) / 1000.0)),
        )
    boranium_cost = 0

    remaining_growth = growth - stage_one_requested
    if remaining_growth <= 0 or stage_one_growth < stage_one_requested:
        return stage_one_growth, ironium_cost, boranium_cost

    available_ironium -= ironium_cost
    mixed_growth = min(remaining_growth, available_ironium * 2000, available_boranium * 2000)
    if mixed_growth <= 0:
        return stage_one_growth, ironium_cost, boranium_cost

    mixed_cost = min(
        available_ironium,
        available_boranium,
        int(math.ceil(float(mixed_growth) / 2000.0)),
    )
    return (
        stage_one_growth + mixed_growth,
        ironium_cost + mixed_cost,
        mixed_cost,
    )


def effective_capacity(player, star):
    """Calculate effective carrying capacity for a star based on habitability.

    Uses base_capacity (in millions) scaled by a nonlinear habitability factor.
    The exponent keeps poor/mid-habitability worlds in the low millions while
    preserving large capacities only for excellent worlds.
    """
    hab_factor = 0
    for env in ['gravity', 'temperature', 'radiation']:
        proportion = habitability_value_for_environment(player, env, getattr(star, env))
        hab_factor += max(0, proportion)
    hab_factor = hab_factor / 3.0

    # base_capacity is in millions, convert to actual colonists
    base = star.base_capacity * MILLION * player_population_cap_multiplier(player)
    if hab_factor <= 0:
        return MILLION  # Minimum 1m capacity
    scaled = hab_factor ** CAPACITY_HAB_EXPONENT
    return max(MILLION, int(base * scaled))


def habitability_proportion(hab_min, hab_max, centre, value):
    """Returns 1 at centre, 0 at min/max edges, negative outside range."""
    if value == centre:
        return 1.0
    elif value > centre:
        return 1.0 - (value - centre) / (hab_max - centre)
    else:
        return 1.0 - (centre - value) / (centre - hab_min)


def calculate_employment_percent(star):
    """Calculate employment percentage based on infrastructure.

    Each mine, factory, and defense employs COLONISTS_PER_JOB colonists.
    Each shipyard employs COLONISTS_PER_SHIPYARD colonists (10x more).
    Active Dyson Spheres add a fixed 1bn jobs.
    Returns 0-100, capped at 100%.
    """
    jobs = calculate_total_jobs(star)
    return _employment_percent_from_jobs(getattr(star, 'colonists', 0), jobs)


def calculate_effective_defenses(star):
    """Calculate effective defenses based on staffing levels.

    Employment ratio uses all jobs. If employment exceeds 100%,
    defenses are reduced by the reciprocal of employment.
    """
    if star.defenses <= 0:
        return 0.0
    if star.colonists <= 0:
        return 0.0
    jobs = calculate_total_jobs(star)
    if jobs <= 0:
        return 0.0
    employment_ratio = _staffing_ratio_from_jobs(star.colonists, jobs)
    effectiveness = calculate_overemployment_effectiveness(employment_ratio)
    defense_multiplier = 1.0
    player = getattr(star, 'player', None)
    if player and getattr(player, 'race_type', None):
        try:
            raw_multiplier = getattr(player.race_type, 'defence_multiplier', 1.0)
            if raw_multiplier is None:
                raw_multiplier = 1.0
            defense_multiplier = float(
                raw_multiplier
            )
        except (TypeError, ValueError):
            defense_multiplier = 1.0
    return star.defenses * effectiveness * defense_multiplier


def calculate_available_buildpoints(star):
    """Calculate buildpoints available this turn from factories.

    Buildpoints represent factory labour capacity and do not accumulate.
    Only fully staffed factories produce buildpoints - if there aren't
    enough colonists to staff all infrastructure, output is proportionally reduced.
    """
    if star.factories == 0:
        return 0
    employment_ratio = calculate_staffing_ratio(star)
    if employment_ratio <= 0:
        return 0
    productivity = calculate_productivity_multiplier(employment_ratio)
    manufacturing_multiplier = 1.0
    player = getattr(star, 'player', None)
    if player and getattr(player, 'race_type', None):
        try:
            raw_multiplier = getattr(player.race_type, 'manufacturing_multiplier', 1.0)
            if raw_multiplier is None:
                raw_multiplier = 1.0
            manufacturing_multiplier = float(
                raw_multiplier
            )
        except (TypeError, ValueError):
            manufacturing_multiplier = 1.0
    total = (
        float(star.factories) * BUILDPOINTS_PER_FACTORY * productivity * manufacturing_multiplier
    )
    if has_active_dyson_sphere(star):
        total *= DYSON_PRODUCTIVITY_MULTIPLIER
    return int(total)


def calculate_available_researchpoints(star):
    """Calculate research points available this turn from labs."""
    if star.labs == 0:
        return 0
    employment_ratio = calculate_staffing_ratio(star)
    if employment_ratio <= 0:
        return 0
    productivity = calculate_productivity_multiplier(employment_ratio)
    total = float(star.labs) * RESEARCHPOINTS_PER_LAB * productivity
    if has_active_dyson_sphere(star):
        total *= DYSON_PRODUCTIVITY_MULTIPLIER
    return int(total)


def calculate_staffing_ratio(star):
    """Calculate employment ratio (jobs/colonists)."""
    jobs = calculate_total_jobs(star)
    return _staffing_ratio_from_jobs(getattr(star, 'colonists', 0), jobs)


def calculate_available_construction_colonists(star, colonists_busy=0, employed_jobs=None):
    """Return unemployed colonists available for mine/factory construction this turn."""
    if employed_jobs is None:
        employed_jobs = calculate_total_jobs(star)
    available = int(star.colonists or 0) - int(employed_jobs or 0) - int(colonists_busy or 0)
    return max(0, available)


def calculate_productivity_multiplier(employment_ratio):
    return _productivity_multiplier_from_employment(employment_ratio)


def calculate_productivity_percent(star):
    """Calculate productivity percentage based on buildpoints consumed.

    Productivity is the percentage of available buildpoints that were
    consumed this turn. Capped at 100%.
    """
    available = calculate_available_buildpoints(star)
    if available == 0:
        return 0
    consumed = calculate_consumed_buildpoints(star)
    return min(100, consumed / available * 100)


def calculate_consumed_buildpoints(star):
    """Calculate buildpoints consumed by production this turn."""
    return star.buildpoints_consumed


def calculate_economy_percent(star):
    """Calculate economy percentage from employment and productivity.

    economy% = employment%/2 + productivity%/2
    Returns 0-100, minimum 0%.
    """
    employment = calculate_employment_percent(star)
    productivity = calculate_productivity_percent(star)
    return (employment - 50) + (productivity - 25) / 2


def calculate_economy_factor(star):
    """Calculate economy factor as a coefficient (0-1 range).

    Converts economy percentage to the same scale as environmental factors.
    """
    return calculate_economy_percent(star) / 100


def calculate_habitability_factor(player, star):
    """Calculate raw habitability factor without capacity modifier.

    Returns a factor where:
    - Perfect habitability (all envs at center): 1.0
    - Edge habitability (all envs at min/max): 0.0
    - Outside range: negative

    Economy factor is added to environmental factors before averaging,
    but the /3 divisor is kept. This allows economic activity to
    temporarily boost growth beyond what environment alone would allow.
    """
    factor = 0
    for env in ['gravity', 'temperature', 'radiation']:
        factor += habitability_value_for_environment(player, env, getattr(star, env))
    # Add economy factor before averaging
    factor += calculate_economy_factor(star)
    # Average using the original /3 divisor (economy is a bonus)
    value = factor / 6.0  # changed to nerf growth
    if value > 0 and has_active_dyson_sphere(star, player=player):
        value *= DYSON_HABITABILITY_MULTIPLIER
    return value


def calculate_growth_factor(player, star):
    """Calculate population growth factor based on habitability and carrying capacity.

    Returns a factor where:
    - Perfect habitability (all envs at center): ~0.25 (25% growth) at low pop
    - Edge habitability (all envs at min/max): 0 (no growth)
    - Outside range: negative (linear decline)
    - High population: reduced by carrying capacity (tanh curve)

    The returned factor should be multiplied by race_type.population_growth_multiplier
    before being passed to apply_population_change().
    """
    hab_factor = calculate_habitability_factor(player, star)

    if hab_factor >= 0:
        # Dampen growth: max ~0.5 at perfect habitability
        factor = (hab_factor ** 2) / 2
        # Apply carrying capacity modifier (reduces growth at high populations)
        cap = effective_capacity(player, star)
        factor *= capacity_modifier(star.colonists, cap)
        return factor
    else:
        # Negative factor for environmental deaths
        return hab_factor
