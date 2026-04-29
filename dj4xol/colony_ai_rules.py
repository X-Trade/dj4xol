from __future__ import unicode_literals

from .colony_rules import (
    BILLION,
    MILLION,
    effective_capacity,
    habitability_value_for_environment,
)
from .mineral_rules import ALL_RESOURCE_KEYS
from .mineral_rules import SECRET_RESOURCE_KEYS


ROLE_MINING = 'mining'
ROLE_EDEN = 'eden'
ROLE_PRODUCTION = 'production'
ROLE_RESEARCH = 'research'
ROLE_FRONTIER = 'frontier'
ROLE_SECRET_RESOURCE = 'secret_resource'
ROLE_TERRAFORM_CANDIDATE = 'terraform_candidate'
ROLE_MARGINAL = 'marginal'

MINING_RESOURCE_FACTOR = 56
EDEN_HABITABILITY = 0.78
RESEARCH_HABITABILITY = 0.62
PRODUCTION_HABITABILITY = 0.40
SURVIVABLE_HABITABILITY = 0.02
TERRAFORM_TARGET_HABITABILITY = 0.72
POTENTIAL_EDEN_HABITABILITY = 0.50
POTENTIAL_EDEN_NEAR_IDEAL_ENVIRONMENT = 0.85
POTENTIAL_EDEN_BASE_CAPACITY = 1500 * MILLION
POTENTIAL_EDEN_STRONG_BASE_CAPACITY = 3000 * MILLION
POTENTIAL_EDEN_MODERATE_RESOURCE_FACTOR = 25
POTENTIAL_EDEN_MINING_HABITABILITY = 0.62
POTENTIAL_EDEN_MINING_MATURE_MINES = 50
POTENTIAL_EDEN_MINING_MATURE_FACTORIES = 60

STANCE_THREAT_WEIGHTS = {
    'HOSTILE': 1.0,
    'COLD': 0.65,
    'NEUTRAL': 0.25,
    'WARM': 0.05,
    'ALLIED': 0.0,
    'UNKNOWN': 0.35,
}


def _clamp(value, minimum=0.0, maximum=1.0):
    return max(float(minimum), min(float(maximum), float(value or 0.0)))


def _safe_float(value, default=0.0):
    try:
        return float(value)
    except (TypeError, ValueError):
        return float(default)


def _safe_int(value, default=0):
    try:
        return int(value)
    except (TypeError, ValueError):
        return int(default)


def environment_habitability_factors(player, star):
    """Return per-factor environment habitability, without economy bonuses."""
    if not player or not star:
        return {}
    factors = {}
    for env in ('gravity', 'temperature', 'radiation'):
        try:
            factors[env] = float(
                habitability_value_for_environment(
                    player,
                    env,
                    getattr(star, env),
                )
            )
        except (AttributeError, TypeError, ValueError, ZeroDivisionError):
            factors[env] = 0.0
    return factors


def environment_habitability(player, star):
    """Return environment-only habitability, without economy bonuses."""
    factors = environment_habitability_factors(player, star)
    if not factors:
        return 0.0
    total = 0.0
    for env in ('gravity', 'temperature', 'radiation'):
        total += float(factors.get(env, 0.0) or 0.0)
    return total / float(len(factors))


def resource_quality(star):
    """Return a normalized resource quality profile for colony role scoring."""
    yields = {}
    for key in ALL_RESOURCE_KEYS:
        yields[key] = max(0, _safe_int(getattr(star, '%s_yield' % key, 0)))
    values = list(yields.values())
    secret_values = [yields.get(key, 0) for key in SECRET_RESOURCE_KEYS]
    if not yields:
        return {
            'max_resource_factor': 0,
            'average_resource_factor': 0.0,
            'resource_score': 0.0,
            'max_secret_resource_factor': 0,
            'has_secret_resource_yield': False,
        }
    max_factor = max(values)
    max_secret = max(secret_values) if secret_values else 0
    average = float(sum(values)) / float(len(values))
    return {
        'max_resource_factor': max_factor,
        'average_resource_factor': average,
        'resource_score': _clamp(float(max_factor) / 100.0),
        'max_secret_resource_factor': max_secret,
        'has_secret_resource_yield': max_secret > 0,
    }


def colony_capacity(player, star):
    try:
        return int(effective_capacity(player, star) or 0)
    except (AttributeError, TypeError, ValueError, ZeroDivisionError):
        base = max(0, _safe_int(getattr(star, 'base_capacity', 0)))
        return base * 1000000


def colony_base_capacity(player, star):
    """Return raw capacity before habitability scaling."""
    base = max(0, _safe_int(getattr(star, 'base_capacity', 0)))
    multiplier = 1.0
    race_type = getattr(player, 'race_type', None)
    if race_type is not None:
        multiplier = max(
            0.0,
            _safe_float(getattr(race_type, 'population_cap_multiplier', 1.0), 1.0),
        )
    return int(float(base * 1000000) * multiplier)


def potential_eden_terraform_score(
    habitability,
    resources,
    base_capacity,
    environment_factors,
    mines=0,
    factories=0,
    shipyards=0,
):
    """Score worlds that could become eden after targeted terraforming."""
    habitability = _safe_float(habitability)
    if habitability < POTENTIAL_EDEN_HABITABILITY or habitability >= EDEN_HABITABILITY:
        return 0.0

    env_values = [
        _safe_float(environment_factors.get(env, 0.0))
        for env in ('gravity', 'temperature', 'radiation')
        if isinstance(environment_factors, dict)
    ]
    if not env_values:
        return 0.0
    best_environment = max(env_values)
    if best_environment < POTENTIAL_EDEN_NEAR_IDEAL_ENVIRONMENT:
        return 0.0

    base_capacity = max(0, _safe_int(base_capacity))
    if base_capacity < POTENTIAL_EDEN_BASE_CAPACITY:
        return 0.0

    capacity_score = _clamp(
        (
            float(base_capacity - POTENTIAL_EDEN_BASE_CAPACITY) /
            float(POTENTIAL_EDEN_STRONG_BASE_CAPACITY - POTENTIAL_EDEN_BASE_CAPACITY)
        )
    )
    max_resource = max(0, _safe_int((resources or {}).get('max_resource_factor', 0)))
    has_secret_resource = bool((resources or {}).get('has_secret_resource_yield'))
    resource_rich = max_resource >= MINING_RESOURCE_FACTOR or has_secret_resource
    if resource_rich:
        mature_mining_mines = max(
            POTENTIAL_EDEN_MINING_MATURE_MINES,
            max_resource,
        )
        mature_mining = (
            _safe_int(mines) >= mature_mining_mines or
            (
                _safe_int(mines) >= POTENTIAL_EDEN_MINING_MATURE_MINES and
                (
                    _safe_int(factories) >= POTENTIAL_EDEN_MINING_MATURE_FACTORIES or
                    _safe_int(shipyards) > 0
                )
            )
        )
        if habitability < POTENTIAL_EDEN_MINING_HABITABILITY or not mature_mining:
            return 0.0

    average_resource = max(
        0.0,
        _safe_float((resources or {}).get('average_resource_factor', 0.0)),
    )
    resource_support = _clamp(
        (
            max(max_resource, average_resource) -
            POTENTIAL_EDEN_MODERATE_RESOURCE_FACTOR
        ) / 35.0
    )
    habitability_score = _clamp(
        (habitability - POTENTIAL_EDEN_HABITABILITY) /
        (EDEN_HABITABILITY - POTENTIAL_EDEN_HABITABILITY)
    )
    near_ideal_score = _clamp(
        (
            best_environment - POTENTIAL_EDEN_NEAR_IDEAL_ENVIRONMENT
        ) / (
            1.0 - POTENTIAL_EDEN_NEAR_IDEAL_ENVIRONMENT
        )
    )
    score = _clamp(
        0.30 +
        (habitability_score * 0.28) +
        (capacity_score * 0.28) +
        (near_ideal_score * 0.08) +
        (resource_support * 0.06)
    )
    if resource_rich:
        score *= 0.85
    return _clamp(score)


def threat_score_from_report_context(report_context):
    """Return a threat score from already-known report-derived context."""
    if not isinstance(report_context, dict):
        return 0.0
    direct_score = report_context.get('threat_score')
    if direct_score is not None:
        return _clamp(_safe_float(direct_score))
    hostile = max(0, _safe_int(report_context.get('nearby_hostile_colonies', 0)))
    cold = max(0, _safe_int(report_context.get('nearby_cold_colonies', 0)))
    foreign = max(0, _safe_int(report_context.get('nearby_foreign_colonies', 0)))
    nearest = report_context.get('nearest_foreign_distance')
    distance_factor = 1.0
    if nearest is not None:
        distance_factor = 1.0 - _clamp(_safe_float(nearest) / 120.0)
    score = (
        min(1.0, hostile * 0.45) +
        min(0.6, cold * 0.25) +
        min(0.35, foreign * 0.10)
    ) * max(0.25, distance_factor)
    return _clamp(score)


def stance_threat_weight(stance):
    key = str(stance or 'UNKNOWN').strip().upper()
    return STANCE_THREAT_WEIGHTS.get(key, STANCE_THREAT_WEIGHTS['UNKNOWN'])


def classify_colony_role(player, star, report_context=None):
    """Classify a colony into strategic roles for Administration AI.

    The returned profile is deliberately data-only so production, logistics,
    and tests can share the same vocabulary without depending on the ORM.
    """
    environment_factors = environment_habitability_factors(player, star)
    if environment_factors:
        habitability = sum(
            float(environment_factors.get(env, 0.0) or 0.0)
            for env in ('gravity', 'temperature', 'radiation')
        ) / 3.0
    else:
        habitability = 0.0
    resources = resource_quality(star)
    max_resource = int(resources['max_resource_factor'])
    max_secret_resource = int(resources['max_secret_resource_factor'])
    has_secret_resource = bool(resources['has_secret_resource_yield'])
    resource_score = float(resources['resource_score'])
    capacity = colony_capacity(player, star)
    base_capacity = colony_base_capacity(player, star)
    capacity_score = _clamp(float(capacity) / float(3 * BILLION))
    threat_score = threat_score_from_report_context(report_context)
    mines = max(0, _safe_int(getattr(star, 'mines', 0)))
    factories = max(0, _safe_int(getattr(star, 'factories', 0)))
    labs = max(0, _safe_int(getattr(star, 'labs', 0)))
    shipyards = max(0, _safe_int(getattr(star, 'shipyards', 0)))
    defenses = max(0, _safe_int(getattr(star, 'defenses', 0)))
    potential_eden_score = potential_eden_terraform_score(
        habitability,
        resources,
        base_capacity,
        environment_factors,
        mines=mines,
        factories=factories,
        shipyards=shipyards,
    )
    is_homeworld = bool(
        getattr(player, 'homeworld_id', None) and
        getattr(player, 'homeworld_id', None) == getattr(star, 'id', None)
    )
    survivable = habitability > SURVIVABLE_HABITABILITY

    scores = {
        ROLE_MINING: 0.0,
        ROLE_EDEN: 0.0,
        ROLE_PRODUCTION: 0.0,
        ROLE_RESEARCH: 0.0,
        ROLE_FRONTIER: 0.0,
        ROLE_SECRET_RESOURCE: 0.0,
        ROLE_TERRAFORM_CANDIDATE: 0.0,
        ROLE_MARGINAL: 0.0,
    }

    if survivable and (max_resource >= MINING_RESOURCE_FACTOR or has_secret_resource):
        scores[ROLE_MINING] = _clamp(
            0.35 + ((max_resource - MINING_RESOURCE_FACTOR) / 70.0)
        )
        if has_secret_resource:
            scores[ROLE_MINING] = max(
                scores[ROLE_MINING],
                _clamp(0.42 + (float(max_secret_resource) / 160.0)),
            )

    if survivable and has_secret_resource:
        scores[ROLE_SECRET_RESOURCE] = _clamp(
            0.50 +
            (float(max_secret_resource) / 140.0) +
            (resource_score * 0.10)
        )

    if habitability >= EDEN_HABITABILITY:
        scores[ROLE_EDEN] = _clamp(
            0.55 +
            ((habitability - EDEN_HABITABILITY) * 1.7) +
            (capacity_score * 0.25)
        )
        if is_homeworld:
            scores[ROLE_EDEN] = min(1.0, scores[ROLE_EDEN] + 0.10)

    if survivable and (
        factories >= 60 or
        shipyards > 0 or
        (habitability >= PRODUCTION_HABITABILITY and resource_score >= 0.45)
    ):
        scores[ROLE_PRODUCTION] = _clamp(
            0.25 +
            min(0.35, factories / 300.0) +
            min(0.20, shipyards / 10.0) +
            (resource_score * 0.25) +
            (_clamp(habitability) * 0.15)
        )

    if habitability >= RESEARCH_HABITABILITY and max_resource < MINING_RESOURCE_FACTOR:
        scores[ROLE_RESEARCH] = _clamp(
            0.30 +
            ((habitability - RESEARCH_HABITABILITY) * 0.9) +
            min(0.25, labs / 250.0)
        )

    if threat_score > 0.0:
        scores[ROLE_FRONTIER] = _clamp(
            threat_score +
            min(0.15, defenses / 500.0)
        )

    terraform_value = max(
        scores[ROLE_MINING],
        scores[ROLE_EDEN] * 0.85,
        scores[ROLE_PRODUCTION],
        scores[ROLE_SECRET_RESOURCE],
        potential_eden_score,
        capacity_score * 0.60,
        scores[ROLE_FRONTIER] * 0.75,
    )
    if survivable and habitability < TERRAFORM_TARGET_HABITABILITY and terraform_value > 0.20:
        scores[ROLE_TERRAFORM_CANDIDATE] = _clamp(
            terraform_value * (TERRAFORM_TARGET_HABITABILITY - habitability + 0.15)
        )

    if max(scores.values()) <= 0.0 and survivable:
        scores[ROLE_MARGINAL] = 0.35

    roles = tuple(
        role for role, score in sorted(
            scores.items(),
            key=lambda item: (-item[1], item[0]),
        )
        if score > 0.0
    )
    primary_role = roles[0] if roles else ROLE_MARGINAL
    return {
        'primary_role': primary_role,
        'roles': roles,
        'scores': scores,
        'habitability': habitability,
        'environment_factors': environment_factors,
        'capacity': capacity,
        'base_capacity': base_capacity,
        'potential_eden_score': potential_eden_score,
        'max_resource_factor': max_resource,
        'max_secret_resource_factor': max_secret_resource,
        'has_secret_resource_yield': has_secret_resource,
        'average_resource_factor': resources['average_resource_factor'],
        'threat_score': threat_score,
        'is_homeworld': is_homeworld,
        'report_context': dict(report_context or {}),
    }


def role_score(profile, role):
    if not isinstance(profile, dict):
        return 0.0
    scores = profile.get('scores')
    if not isinstance(scores, dict):
        return 0.0
    return _clamp(_safe_float(scores.get(role, 0.0)))


def score_terraform_roi(profile, tier=3):
    """Return an additive production score for terraforming valuable colonies."""
    if not isinstance(profile, dict):
        return 0.0
    habitability = _safe_float(profile.get('habitability', 0.0))
    if habitability >= TERRAFORM_TARGET_HABITABILITY:
        return 0.0
    try:
        level = int(tier or 0)
    except (TypeError, ValueError):
        level = 0
    mining_value = role_score(profile, ROLE_MINING)
    eden_value = role_score(profile, ROLE_EDEN)
    production_value = role_score(profile, ROLE_PRODUCTION)
    secret_value = role_score(profile, ROLE_SECRET_RESOURCE)
    frontier_value = role_score(profile, ROLE_FRONTIER)
    potential_eden = _safe_float(profile.get('potential_eden_score', 0.0))
    value = max(
        mining_value,
        eden_value * 0.85,
        production_value,
        secret_value,
        frontier_value * 0.70,
        potential_eden,
    )
    if level <= 3:
        value = max(
            mining_value,
            production_value * 0.85,
            secret_value,
            frontier_value * 0.55,
            potential_eden * 0.60,
        )
    elif level >= 4:
        value = max(
            value,
            potential_eden * 1.12,
            production_value * 1.05,
            secret_value * 1.08,
        )
        if bool(profile.get('is_homeworld')):
            value = max(value, 0.65)
    if value <= 0.0:
        return 0.0
    gap = _clamp(TERRAFORM_TARGET_HABITABILITY - habitability)
    tier_factor = 0.55 if level <= 3 else 1.0
    if level >= 5:
        tier_factor = 1.25
    gap_factor = 0.35 + gap
    if level >= 4 and potential_eden > 0.0:
        gap_factor += min(0.08, potential_eden * 0.08)
    return 260.0 * value * gap_factor * tier_factor
