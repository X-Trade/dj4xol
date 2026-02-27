import math

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


def effective_capacity(player, star):
    """Calculate effective carrying capacity for a star based on habitability.

    Uses base_capacity (in millions) scaled by a nonlinear habitability factor.
    The exponent keeps poor/mid-habitability worlds in the low millions while
    preserving large capacities only for excellent worlds.
    """
    hab_factor = 0
    for env in ['gravity', 'temperature', 'radiation']:
        proportion = habitability_proportion(
            player.hab_min(env),
            player.hab_max(env),
            getattr(player, f'{env}_center'),
            getattr(star, env)
        )
        hab_factor += max(0, proportion)
    hab_factor = hab_factor / 3.0

    # base_capacity is in millions, convert to actual colonists
    base = star.base_capacity * MILLION
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
    Returns 0-100, capped at 100%.
    """
    if star.colonists == 0:
        return 0
    jobs = ((star.mines + star.factories + star.labs + star.defenses) *
            COLONISTS_PER_JOB
            + star.shipyards * COLONISTS_PER_SHIPYARD)
    return min(100, jobs / star.colonists * 100)


def calculate_effective_defenses(star):
    """Calculate effective defenses based on staffing levels.

    Employment ratio uses all jobs. If employment exceeds 100%,
    defenses are reduced by the reciprocal of employment.
    """
    if star.defenses <= 0:
        return 0.0
    if star.colonists <= 0:
        return 0.0
    jobs = ((star.mines + star.factories + star.labs + star.defenses) *
            COLONISTS_PER_JOB
            + star.shipyards * COLONISTS_PER_SHIPYARD)
    if jobs <= 0:
        return 0.0
    employment_ratio = jobs / star.colonists
    effectiveness = 1.0 if employment_ratio <= 1.0 else (1.0 / employment_ratio)
    return star.defenses * effectiveness


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
    return int(star.factories * BUILDPOINTS_PER_FACTORY * productivity)


def calculate_available_researchpoints(star):
    """Calculate research points available this turn from labs."""
    if star.labs == 0:
        return 0
    employment_ratio = calculate_staffing_ratio(star)
    if employment_ratio <= 0:
        return 0
    productivity = calculate_productivity_multiplier(employment_ratio)
    return int(star.labs * RESEARCHPOINTS_PER_LAB * productivity)


def calculate_staffing_ratio(star):
    """Calculate employment ratio (jobs/colonists)."""
    jobs = ((star.mines + star.factories + star.labs + star.defenses) *
            COLONISTS_PER_JOB
            + star.shipyards * COLONISTS_PER_SHIPYARD)
    if jobs <= 0 or star.colonists <= 0:
        return 0
    return jobs / star.colonists


def calculate_productivity_multiplier(employment_ratio):
    """Bell-curve productivity based on employment ratio.

    Targets: 0.25x at 1%, 0.5x at 10%, 1.5x at 50%, 1.0x at 100%.
    Productivity never drops below 0.2x once any staffing exists.
    Above 100% employment, productivity declines as 1/employment.
    """
    if employment_ratio <= 0:
        return 0.0
    if employment_ratio >= 1.0:
        return 1.0 / employment_ratio

    ratio = max(0.0, min(1.0, employment_ratio))
    if ratio < 0.01:
        return 0.2 + (ratio / 0.01) * 0.05
    if ratio <= 0.1:
        return 0.25 + ((ratio - 0.01) / 0.09) * 0.25

    # Quadratic fit through (0.1, 0.5), (0.5, 1.5), (1.0, 1.0)
    a = -3.8888888889
    b = 4.8333333333
    c = 0.0555555556
    return a * ratio * ratio + b * ratio + c


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
        factor += habitability_proportion(
            player.hab_min(env),
            player.hab_max(env),
            getattr(player, f'{env}_center'),
            getattr(star, env)
        )
    # Add economy factor before averaging
    factor += calculate_economy_factor(star)
    # Average using the original /3 divisor (economy is a bonus)
    return factor / 6.0  # changed to nerf growth


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
