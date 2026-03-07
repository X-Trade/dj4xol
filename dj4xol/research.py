import json
import math

from django.db import models, transaction

from .colony_rules import (
    calculate_available_buildpoints,
    calculate_available_researchpoints,
    calculate_staffing_ratio,
)
from .bombardment_rules import normalize_bomb_type, normalize_miner_type
from .micromanager_rules import (
    ADMINISTRATION_ORDER_TYPE,
    administration_level_from_params,
)
from .models import (
    DefaultResearchLevelRequirement,
    PlayerResearch,
    ResearchCategory,
    ResearchLevelRequirement,
    ResearchLevelPrerequisite,
    Technology,
)
from .research_rules import (
    allocate_rp_integer,
    clamp_percent,
    rp_cost_for_level,
    normalise_percentages,
)
from .technology_thumbnails import (
    get_technology_thumbnail_initial_index,
    get_technology_thumbnail_path,
    get_technology_thumbnail_paths,
)
from .secret_resources import SECRET_RESOURCE_KEYS, get_secret_resource_label

TECH_PARAM_LABELS = {
    'max_warp_speed': 'Maximum Warp',
    'max_cargo_capacity': 'Cargo Capacity',
    'max_fuel': 'Fuel Capacity',
    'fuel_efficiency': 'Fuel Efficiency',
    'overmax_fuel_penalty': 'Overmax Fuel Penalty',
    'wormhole_fuel_per_ly': 'Wormhole Fuel (mg/ly)',
    'wormhole_destruction_chance': 'Wormhole Destruction Chance',
    'hull_thumbnail_class': 'Hull Class',
    'offense_level': 'Offense Level',
    'defense_level': 'Defense Level',
    'colony_defense_level': 'Colony Defense Level',
    'basic_scanner_range': 'Basic Scanner Range',
    'advanced_scanner_range': 'Advanced Scanner Range',
    'terraforming_rate': 'Terraforming Rate',
    'administration_level': 'Administration Level',
}

TERRAFORM_ORDER_LABELS = {
    'TERRAFORM_GRAVITY': 'Terraform Gravity',
    'TERRAFORM_TEMPERATURE': 'Terraform Temperature',
    'TERRAFORM_RADIATION': 'Terraform Radiation',
}

RESEARCH_RESOURCE_KEYS = (
    'ironium', 'boranium', 'germanium',
    'resource_x', 'resource_y', 'resource_z',
)

RESEARCH_RESOURCE_LABELS = {
    'ironium': 'Ironium',
    'boranium': 'Boranium',
    'germanium': 'Germanium',
}


def _safe_params(tech):
    try:
        data = json.loads(tech.params_json or '{}')
        if isinstance(data, dict):
            return data
    except (TypeError, ValueError):
        pass
    return {}


def _format_param_key(key):
    """Return a player-facing label for a technology parameter key."""
    if key in TECH_PARAM_LABELS:
        return TECH_PARAM_LABELS[key]
    return key.replace('_', ' ').title()


def _format_param_value(key, value):
    """Return player-facing display value for technology parameter values."""
    if key in ('offense_level', 'defense_level', 'colony_defense_level'):
        try:
            scaled = int(round(float(value) * 10))
            return '{:+d}'.format(scaled)
        except (TypeError, ValueError):
            return value
    if key in ('fuel_efficiency', 'overmax_fuel_penalty'):
        try:
            return '{}%'.format(int(round(float(value) * 100)))
        except (TypeError, ValueError):
            return value
    if key == 'wormhole_destruction_chance':
        try:
            return '{}%'.format(int(round(float(value) * 100)))
        except (TypeError, ValueError):
            return value
    if key == 'wormhole_fuel_per_ly':
        try:
            return '{:.2f}'.format(float(value))
        except (TypeError, ValueError):
            return value
    if key == 'hull_thumbnail_class':
        text = str(value or '').strip()
        if not text:
            return value
        return text.replace('_', ' ').title()
    if key == 'terraforming_rate':
        try:
            return '{}%'.format(int(round(float(value) * 100.0)))
        except (TypeError, ValueError):
            return value
    if key == 'administration_level':
        try:
            return '{}'.format(int(value))
        except (TypeError, ValueError):
            return value
    return value


def _should_show_param(key, value):
    if key == 'advanced_scanner_range':
        try:
            return float(value) > 0
        except (TypeError, ValueError):
            return True
    if key == 'production_cost_overrides':
        return False
    return True


def format_terraform_order_label(order_type, rate_percent=None):
    label = TERRAFORM_ORDER_LABELS.get(order_type, order_type)
    if rate_percent is None:
        return label
    return '%s (%s%%)' % (label, int(rate_percent))


def _normalise_cost_dict(cost):
    base = {
        'bp': 0,
        'ironium': 0,
        'boranium': 0,
        'germanium': 0,
        'resource_x': 0,
        'resource_y': 0,
        'resource_z': 0,
        'colonists': 0,
    }
    if not isinstance(cost, dict):
        return base
    for key in base:
        try:
            base[key] = int(cost.get(key, base[key]) or 0)
        except (TypeError, ValueError):
            base[key] = base[key]
    return base


def _parse_terraforming_rate(value):
    try:
        rate = float(value)
    except (TypeError, ValueError):
        return 0.0
    if rate > 1.0:
        return max(0.0, rate / 100.0)
    return max(0.0, rate)


def _select_terraforming_tech(unlocked):
    selected = None
    selected_sort_key = None
    for tech in unlocked:
        if str(tech.tech_type or '') != 'INFRASTRUCTURE':
            continue
        params = _safe_params(tech)
        if 'terraforming_rate' not in params and 'production_cost_overrides' not in params:
            continue
        sort_key = (int(tech.level), int(tech.display_order or 0), str(tech.name or ''))
        if selected is None or sort_key > selected_sort_key:
            selected = tech
            selected_sort_key = sort_key
    return selected


def _select_administration_tech(unlocked):
    selected = None
    selected_sort_key = None
    for tech in unlocked:
        if str(tech.tech_type or '') != 'INFRASTRUCTURE':
            continue
        params = _safe_params(tech)
        level = administration_level_from_params(params)
        if level <= 0:
            continue
        sort_key = (
            int(level),
            int(tech.level),
            int(tech.display_order or 0),
            str(tech.name or ''),
        )
        if selected is None or sort_key > selected_sort_key:
            selected = tech
            selected_sort_key = sort_key
    return selected


def get_player_terraforming_profile(player):
    """Return terraforming rate/costs for a player based on INFRASTRUCTURE tech."""
    if not player or not getattr(player, 'race_type', None):
        return {'rate': 0.0, 'costs': {}, 'tech': None}
    if not bool(getattr(player.race_type, 'has_terraforming', True)):
        return {'rate': 0.0, 'costs': {}, 'tech': None}
    unlocked = list(get_player_unlocked_technologies(player))
    if not unlocked:
        return {'rate': 0.0, 'costs': {}, 'tech': None}
    selected = _select_terraforming_tech(unlocked)
    if selected is None:
        return {'rate': 0.0, 'costs': {}, 'tech': None}
    params = _safe_params(selected)
    rate = _parse_terraforming_rate(params.get('terraforming_rate', 0.0))
    overrides = params.get('production_cost_overrides') if isinstance(params, dict) else None
    if not isinstance(overrides, dict):
        overrides = {}
    costs = {}
    for order_type, cost in overrides.items():
        if order_type not in TERRAFORM_ORDER_LABELS:
            continue
        costs[order_type] = _normalise_cost_dict(cost)
    return {'rate': rate, 'costs': costs, 'tech': selected}


def get_player_administration_profile(player):
    """Return Administration automation tier from unlocked tech."""
    if not player or not getattr(player, 'race_type', None):
        return {'level': 0, 'tech': None}
    unlocked = list(get_player_unlocked_technologies(player))
    if not unlocked:
        return {'level': 0, 'tech': None}
    selected = _select_administration_tech(unlocked)
    if selected is None:
        return {'level': 0, 'tech': None}
    params = _safe_params(selected)
    return {
        'level': administration_level_from_params(params),
        'tech': selected,
    }


def get_player_production_costs(player):
    """Return production costs for the player, including tech overrides."""
    from .models import PRODUCTION_COSTS
    costs = {}
    for key, value in PRODUCTION_COSTS.items():
        costs[key] = _normalise_cost_dict(value)
    profile = get_player_terraforming_profile(player)
    for order_type, override in profile.get('costs', {}).items():
        if order_type not in costs:
            continue
        merged = costs[order_type].copy()
        merged.update(override)
        costs[order_type] = _normalise_cost_dict(merged)
    return costs


def get_player_available_production_orders(player, star):
    """Return available production order choices for a player at a star."""
    if not player or not star or getattr(star, 'player_id', None) != player.id:
        return []
    orders = []
    administration_profile = get_player_administration_profile(player)
    profile = get_player_terraforming_profile(player)
    rate = profile.get('rate', 0.0)
    if rate > 0:
        rate_percent = int(round(rate * 100.0))
        for order_type in ('TERRAFORM_GRAVITY', 'TERRAFORM_TEMPERATURE', 'TERRAFORM_RADIATION'):
            orders.append({
                'value': order_type,
                'label': format_terraform_order_label(order_type, rate_percent),
                'repeat_allowed': True,
            })
    if int(getattr(star, 'shipyards', 0) or 0) > 0:
        orders.append({
            'value': 'BUILD_FLEET',
            'label': 'Build Fleet',
            'repeat_allowed': True,
        })
    orders.extend([
        {
            'value': 'BUILD_MINE',
            'label': 'Build Mine',
            'repeat_allowed': True,
        },
        {
            'value': 'BUILD_FACTORY',
            'label': 'Build Factory',
            'repeat_allowed': True,
        },
        {
            'value': 'BUILD_LAB',
            'label': 'Build Lab',
            'repeat_allowed': True,
        },
        {
            'value': 'BUILD_DEFENSE',
            'label': 'Build Defense',
            'repeat_allowed': True,
        },
        {
            'value': 'BUILD_SHIPYARD',
            'label': 'Build Shipyard',
            'repeat_allowed': True,
        },
    ])
    has_admin_order = star.production_orders.filter(
        order_type=ADMINISTRATION_ORDER_TYPE
    ).exists()
    if (
        int(administration_profile.get('level', 0) or 0) > 0 and
        not bool(getattr(star, 'has_administration', False)) and
        not has_admin_order
    ):
        orders.append({
            'value': ADMINISTRATION_ORDER_TYPE,
            'label': 'Build Administration',
            'repeat_allowed': False,
        })
    return orders


def build_production_cost_entries(params, resource_labels=None):
    """Return display entries for production cost overrides."""
    overrides = params.get('production_cost_overrides') if isinstance(params, dict) else None
    if not isinstance(overrides, dict):
        return []
    entries = []
    label_map = dict(RESEARCH_RESOURCE_LABELS)
    if resource_labels:
        label_map.update(resource_labels)
    else:
        for key in SECRET_RESOURCE_KEYS:
            label_map[key] = get_secret_resource_label(key, True)
    for order_type, cost in overrides.items():
        if order_type not in TERRAFORM_ORDER_LABELS:
            continue
        normalised = _normalise_cost_dict(cost)
        label = '%s Cost' % format_terraform_order_label(order_type, None)
        parts = []
        bp_val = normalised.get('bp', 0)
        if bp_val:
            parts.append('BP %s' % bp_val)
        for key in RESEARCH_RESOURCE_KEYS:
            amount = int(normalised.get(key, 0) or 0)
            if amount > 0:
                parts.append('%s %skt' % (label_map.get(key, str(key).title()), amount))
        colonists = int(normalised.get('colonists', 0) or 0)
        if colonists:
            parts.append('Colonists %s' % colonists)
        value = ', '.join(parts) if parts else 'No cost'
        entries.append({'label': label, 'value': value})
    return entries


def _tech_type_label(tech_type):
    choice_map = dict(Technology.TECH_TYPE_CHOICES)
    return choice_map.get(str(tech_type or ''), str(tech_type or 'Other').title())


def _whole_percentages(values):
    """Normalise to whole-number percentages summing to 100."""
    norm = normalise_percentages(values)
    base = [int(v) for v in norm]
    remainder = 100 - sum(base)
    ranked = sorted(
        range(len(norm)),
        key=lambda idx: (norm[idx] - int(norm[idx])),
        reverse=True
    )
    for idx in ranked:
        if remainder <= 0:
            break
        base[idx] += 1
        remainder -= 1
    return [float(v) for v in base]


def ensure_default_level_requirements(max_level=26):
    """Ensure default level requirement rows exist up to max_level."""
    target = int(max(1, max_level))
    existing = set(
        DefaultResearchLevelRequirement.objects.filter(
            level__lte=target
        ).values_list('level', flat=True)
    )
    missing = []
    for level in range(1, target + 1):
        if level in existing:
            continue
        missing.append(DefaultResearchLevelRequirement(
            level=level,
            rp_cost=rp_cost_for_level(level),
            ironium_cost=0,
            boranium_cost=0,
            germanium_cost=0,
            resource_x_cost=0,
            resource_y_cost=0,
            resource_z_cost=0,
        ))
    if missing:
        DefaultResearchLevelRequirement.objects.bulk_create(missing)


def copy_default_requirements_to_category(
        category, ensure_defaults=True, overwrite_existing=False):
    """Copy or sync per-level requirements from defaults into a category."""
    if ensure_defaults:
        ensure_default_level_requirements()
    defaults = list(DefaultResearchLevelRequirement.objects.all().order_by('level'))
    existing_by_level = {
        row.level: row
        for row in ResearchLevelRequirement.objects.filter(category=category)
    }
    missing = []
    dirty = []
    for default in defaults:
        existing = existing_by_level.get(default.level)
        if existing is None:
            missing.append(ResearchLevelRequirement(
                category=category,
                level=default.level,
                rp_cost=default.rp_cost,
                ironium_cost=default.ironium_cost,
                boranium_cost=default.boranium_cost,
                germanium_cost=default.germanium_cost,
                resource_x_cost=default.resource_x_cost,
                resource_y_cost=default.resource_y_cost,
                resource_z_cost=default.resource_z_cost,
            ))
            continue
        if not overwrite_existing:
            continue
        changed = False
        if existing.rp_cost != default.rp_cost:
            existing.rp_cost = default.rp_cost
            changed = True
        if existing.ironium_cost != default.ironium_cost:
            existing.ironium_cost = default.ironium_cost
            changed = True
        if existing.boranium_cost != default.boranium_cost:
            existing.boranium_cost = default.boranium_cost
            changed = True
        if existing.germanium_cost != default.germanium_cost:
            existing.germanium_cost = default.germanium_cost
            changed = True
        if existing.resource_x_cost != default.resource_x_cost:
            existing.resource_x_cost = default.resource_x_cost
            changed = True
        if existing.resource_y_cost != default.resource_y_cost:
            existing.resource_y_cost = default.resource_y_cost
            changed = True
        if existing.resource_z_cost != default.resource_z_cost:
            existing.resource_z_cost = default.resource_z_cost
            changed = True
        if changed:
            dirty.append(existing)
    if missing:
        ResearchLevelRequirement.objects.bulk_create(missing)
    for row in dirty:
        row.save(update_fields=[
            'rp_cost', 'ironium_cost', 'boranium_cost', 'germanium_cost',
            'resource_x_cost', 'resource_y_cost', 'resource_z_cost',
        ])


def _apply_research_cost_multiplier(requirement, multiplier):
    try:
        mult = float(multiplier)
    except (TypeError, ValueError):
        return requirement
    if mult <= 0:
        return requirement
    if abs(mult - 1.0) < 1e-6:
        return requirement
    scaled = {}
    for key in [
        'rp_cost',
        'ironium_cost',
        'boranium_cost',
        'germanium_cost',
        'resource_x_cost',
        'resource_y_cost',
        'resource_z_cost',
    ]:
        value = int(requirement.get(key, 0) or 0)
        scaled[key] = max(0, int(round(value * mult)))
    return scaled


def get_level_requirement(category_id, level, player=None, game=None):
    """Resolve RP/mineral requirements for a category level."""
    if player is not None and game is None:
        game = getattr(player, 'game', None)
    try:
        req = ResearchLevelRequirement.objects.get(
            category_id=category_id, level=level
        )
        base = {
            'rp_cost': int(req.rp_cost),
            'ironium_cost': int(req.ironium_cost),
            'boranium_cost': int(req.boranium_cost),
            'germanium_cost': int(req.germanium_cost),
            'resource_x_cost': int(req.resource_x_cost),
            'resource_y_cost': int(req.resource_y_cost),
            'resource_z_cost': int(req.resource_z_cost),
        }
        if game is not None:
            return _apply_research_cost_multiplier(
                base, getattr(game, 'research_cost_multiplier', 1.0)
            )
        return base
    except ResearchLevelRequirement.DoesNotExist:
        pass

    default = DefaultResearchLevelRequirement.objects.filter(level=level).first()
    if default:
        base = {
            'rp_cost': int(default.rp_cost),
            'ironium_cost': int(default.ironium_cost),
            'boranium_cost': int(default.boranium_cost),
            'germanium_cost': int(default.germanium_cost),
            'resource_x_cost': int(default.resource_x_cost),
            'resource_y_cost': int(default.resource_y_cost),
            'resource_z_cost': int(default.resource_z_cost),
        }
        if game is not None:
            return _apply_research_cost_multiplier(
                base, getattr(game, 'research_cost_multiplier', 1.0)
            )
        return base
    base = {
        'rp_cost': int(rp_cost_for_level(level)),
        'ironium_cost': 0,
        'boranium_cost': 0,
        'germanium_cost': 0,
        'resource_x_cost': 0,
        'resource_y_cost': 0,
        'resource_z_cost': 0,
    }
    if game is not None:
        return _apply_research_cost_multiplier(
            base, getattr(game, 'research_cost_multiplier', 1.0)
        )
    return base


def get_level_prerequisites(category_id, level):
    """Return prerequisite rows for a category level."""
    if category_id is None:
        return []
    return list(
        ResearchLevelPrerequisite.objects.select_related('requires_category').filter(
            category_id=category_id,
            level=int(level),
        )
    )


def _prerequisites_met(category_id, level, level_map):
    if not level_map:
        return True
    prereqs = get_level_prerequisites(category_id, level)
    if not prereqs:
        return True
    for prereq in prereqs:
        current = int(level_map.get(prereq.requires_category_id, 0) or 0)
        if current < int(prereq.min_level or 0):
            return False
    return True


def _eligible_research_stars(player):
    """Return owned colonies with labs that can pay research requirements."""
    return list(
        player.stars.filter(labs__gt=0).order_by('-labs', '-ironium_inventory', 'id')
    )


def _allocate_weighted_integer(total_amount, weights):
    """Allocate integer amounts by weights, preserving total."""
    if not weights:
        return []
    cleaned = [max(0.0, float(weight or 0.0)) for weight in weights]
    total_weight = sum(cleaned)
    if total_weight <= 0 or total_amount <= 0:
        return [0 for _ in cleaned]
    raw = [(float(total_amount) * weight) / total_weight for weight in cleaned]
    floors = [int(value) for value in raw]
    remainder = int(total_amount) - sum(floors)
    ranked = sorted(
        range(len(raw)),
        key=lambda idx: (raw[idx] - floors[idx]),
        reverse=True,
    )
    for idx in ranked:
        if remainder <= 0:
            break
        floors[idx] += 1
        remainder -= 1
    return floors


def _consume_resource_partial(stars, inventory_field, amount):
    """Consume up to amount of a mineral, weighted by staffed labs with reallocation."""
    remaining = int(amount or 0)
    if remaining <= 0:
        return 0

    candidates = []
    for star in stars:
        if int(getattr(star, inventory_field, 0) or 0) <= 0:
            continue
        if int(star.labs or 0) <= 0:
            continue
        staffing_ratio = calculate_staffing_ratio(star)
        if staffing_ratio <= 0:
            continue
        effectiveness = 1.0 if staffing_ratio <= 1.0 else (1.0 / staffing_ratio)
        effective_labs = float(star.labs) * effectiveness
        if effective_labs <= 0.0:
            continue
        candidates.append((star, effective_labs))
    consumed = 0

    while remaining > 0 and candidates:
        weights = [math.log1p(effective_labs) for _, effective_labs in candidates]
        total_weight = sum(weights)
        if total_weight <= 0:
            break
        allocations = _allocate_weighted_integer(remaining, weights)
        next_candidates = []
        progress = False
        for (star, effective_labs), allocation in zip(candidates, allocations):
            if allocation <= 0:
                if int(getattr(star, inventory_field, 0) or 0) > 0:
                    next_candidates.append((star, effective_labs))
                continue
            available = int(getattr(star, inventory_field, 0) or 0)
            take = min(available, allocation)
            if take > 0:
                setattr(star, inventory_field, available - take)
                star.save(update_fields=[inventory_field])
                consumed += take
                remaining -= take
                available -= take
                progress = True
            if available > 0:
                next_candidates.append((star, effective_labs))
        if not progress:
            break
        candidates = next_candidates

    return consumed


def _clamp_paid_to_requirement(paid, requirement):
    """Clamp paid minerals to the current requirement."""
    clamped = {}
    for key in RESEARCH_RESOURCE_KEYS:
        paid_key = f'{key}_paid'
        cost_key = f'{key}_cost'
        current_paid = int(paid.get(paid_key, 0) or 0)
        clamped[paid_key] = min(current_paid, int(requirement.get(cost_key, 0) or 0))
    return clamped


def _allocate_mineral_progress(rows, eligible_stars, max_level_by_category):
    """Allocate available minerals across categories by allocation percentage."""
    if not rows or not eligible_stars:
        return

    requirements = {}
    for row in rows:
        max_level = max_level_by_category.get(row.category_id, int(row.current_level))
        if int(row.current_level) >= int(max_level):
            continue
        next_level = int(row.current_level) + 1
        requirement = get_level_requirement(row.category_id, next_level, player=row.player)
        paid = _clamp_paid_to_requirement({
            f'{key}_paid': getattr(row, f'{key}_paid', 0) for key in RESEARCH_RESOURCE_KEYS
        }, requirement)
        for key in RESEARCH_RESOURCE_KEYS:
            setattr(row, f'{key}_paid', paid.get(f'{key}_paid', 0))
        requirements[row.id] = requirement

    resource_specs = [
        (f'{key}_cost', f'{key}_paid', f'{key}_inventory')
        for key in RESEARCH_RESOURCE_KEYS
    ]

    for cost_key, paid_attr, inventory_field in resource_specs:
        available = sum(int(getattr(star, inventory_field, 0) or 0) for star in eligible_stars)
        if available <= 0:
            continue
        candidates = []
        total_needed = 0
        for row in rows:
            requirement = requirements.get(row.id)
            if not requirement:
                continue
            cost = int(requirement.get(cost_key, 0))
            if cost <= 0:
                continue
            paid = int(getattr(row, paid_attr, 0) or 0)
            remaining = max(0, cost - paid)
            if remaining <= 0:
                continue
            candidates.append((row, remaining))
            total_needed += remaining

        if not candidates or total_needed <= 0:
            continue

        if available >= total_needed:
            for row, remaining in candidates:
                consumed = _consume_resource_partial(eligible_stars, inventory_field, remaining)
                if consumed > 0:
                    setattr(row, paid_attr, int(getattr(row, paid_attr, 0) or 0) + consumed)
            continue

        remaining_available = int(available)
        pending = list(candidates)
        while remaining_available > 0 and pending:
            weights = [row.allocation_percent for row, _ in pending]
            total_weight = sum(max(0.0, float(w or 0.0)) for w in weights)
            if total_weight <= 0:
                break
            allocations = _allocate_weighted_integer(remaining_available, weights)
            next_pending = []
            progress = False
            for (row, remaining_need), allocation in zip(pending, allocations):
                if allocation <= 0:
                    if remaining_need > 0:
                        next_pending.append((row, remaining_need))
                    continue
                take = min(allocation, remaining_need)
                consumed = _consume_resource_partial(eligible_stars, inventory_field, take)
                if consumed > 0:
                    setattr(row, paid_attr, int(getattr(row, paid_attr, 0) or 0) + consumed)
                    remaining_available -= consumed
                    remaining_need -= consumed
                    progress = True
                if remaining_need > 0:
                    next_pending.append((row, remaining_need))
            if not progress:
                break
            pending = next_pending

def _can_pay_requirement(stars, requirement):
    """Check if eligible stars have enough minerals for this requirement."""
    for key in RESEARCH_RESOURCE_KEYS:
        needed = int(requirement.get(f'{key}_cost', 0) or 0)
        if needed <= 0:
            continue
        total = sum(int(getattr(star, f'{key}_inventory', 0) or 0) for star in stars)
        if total < needed:
            return False
    return True


def _consume_requirement(stars, requirement):
    """Consume required minerals from eligible stars, largest labs first."""
    fields = [
        (f'{key}_inventory', int(requirement.get(f'{key}_cost', 0) or 0))
        for key in RESEARCH_RESOURCE_KEYS
    ]
    dirty_stars = {}
    for field, amount in fields:
        remaining = amount
        if remaining <= 0:
            continue
        for star in stars:
            if remaining <= 0:
                break
            available = getattr(star, field)
            if available <= 0:
                continue
            spend = min(available, remaining)
            setattr(star, field, available - spend)
            dirty_stars[star.id] = star
            remaining -= spend
        if remaining > 0:
            return False
    for star in dirty_stars.values():
        update_fields = [
            f'{key}_inventory' for key in RESEARCH_RESOURCE_KEYS
        ]
        star.save(update_fields=update_fields)
    return True


def _max_level_by_category(category_ids):
    """Return the configured maximum research level per category."""
    if not category_ids:
        return {}
    rows = ResearchLevelRequirement.objects.filter(
        category_id__in=category_ids
    ).values('category_id').order_by().annotate(
        max_level=models.Max('level')
    )
    result = {row['category_id']: int(row['max_level']) for row in rows}
    default_max = DefaultResearchLevelRequirement.objects.aggregate(
        models.Max('level')
    ).get('level__max') or 0
    for category_id in category_ids:
        result.setdefault(category_id, int(default_max))
    return result


def get_global_research_max_level():
    """Return the highest configured research level."""
    ensure_default_level_requirements()
    max_level = (
        DefaultResearchLevelRequirement.objects.aggregate(
            models.Max('level')
        ).get('level__max') or 0
    )
    return int(max_level)


def get_starting_tech_balance_costs(max_level=None, rp_per_point=10.0):
    """Return cumulative starting-tech costs in Balance Points by level."""
    ensure_default_level_requirements()
    if max_level is None:
        max_level = get_global_research_max_level()
    max_level = max(0, int(max_level))
    rp_per_point = max(0.0001, float(rp_per_point))

    level_rp = {
        int(row.level): int(row.rp_cost)
        for row in DefaultResearchLevelRequirement.objects.filter(
            level__lte=max_level
        ).order_by('level')
    }
    costs = {0: 0.0}
    cumulative_rp = 0
    for level in range(1, max_level + 1):
        cumulative_rp += int(level_rp.get(level, rp_cost_for_level(level)))
        costs[level] = cumulative_rp / rp_per_point
    return costs


def get_starting_tech_balance_cost(level, rp_per_point=10.0):
    """Return cumulative Balance Point cost for a chosen starting tech level."""
    level = max(0, int(level or 0))
    return float(
        get_starting_tech_balance_costs(
            max_level=level,
            rp_per_point=rp_per_point,
        ).get(level, 0.0)
    )


def _advance_research_row_with_requirements(
    row,
    added_rp,
    max_level,
    eligible_stars,
    allow_mineral_payment=True,
    level_map=None,
):
    """Apply RP and advance one research row, consuming required minerals."""
    old_level = float(row.current_level or 0.0)
    level = old_level
    stored_rp = int(row.stored_rp) + int(added_rp or 0)
    paid_by_key = {
        key: int(getattr(row, f'{key}_paid', 0) or 0) for key in RESEARCH_RESOURCE_KEYS
    }
    while int(level) < int(max_level):
        next_level = int(level) + 1
        requirement = get_level_requirement(row.category_id, next_level, player=row.player)
        if not _prerequisites_met(row.category_id, next_level, level_map):
            break
        rp_cost = int(requirement['rp_cost'])
        paid = _clamp_paid_to_requirement({
            f'{key}_paid': paid_by_key.get(key, 0) for key in RESEARCH_RESOURCE_KEYS
        }, requirement)
        for key in RESEARCH_RESOURCE_KEYS:
            paid_by_key[key] = paid.get(f'{key}_paid', 0)

        if allow_mineral_payment:
            for key in RESEARCH_RESOURCE_KEYS:
                needed = max(
                    0,
                    int(requirement.get(f'{key}_cost', 0) or 0) - int(paid_by_key.get(key, 0) or 0)
                )
                if needed > 0:
                    paid_by_key[key] += _consume_resource_partial(
                        eligible_stars, f'{key}_inventory', needed
                    )

        if any(
            int(paid_by_key.get(key, 0) or 0) < int(requirement.get(f'{key}_cost', 0) or 0)
            for key in RESEARCH_RESOURCE_KEYS
        ):
            break
        if stored_rp < rp_cost:
            break
        stored_rp -= rp_cost
        level += 1.0
        for key in RESEARCH_RESOURCE_KEYS:
            paid_by_key[key] = 0
    row.current_level = level
    row.stored_rp = stored_rp
    for key in RESEARCH_RESOURCE_KEYS:
        setattr(row, f'{key}_paid', int(paid_by_key.get(key, 0) or 0))
    return old_level, level


def ensure_player_research_rows(player):
    """Ensure a player has per-category research rows."""
    categories = list(ResearchCategory.objects.filter(enabled=True))
    ensure_default_level_requirements()
    for category in categories:
        copy_default_requirements_to_category(category, ensure_defaults=False)
    existing = {
        pr.category_id: pr for pr in PlayerResearch.objects.filter(player=player)
    }

    missing = []
    for category in categories:
        if category.id not in existing:
            missing.append(PlayerResearch(
                player=player,
                category=category,
                current_level=0.0,
                stored_rp=0.0,
                allocation_percent=0.0,
            ))
    if missing:
        PlayerResearch.objects.bulk_create(missing)

    rows = list(
        PlayerResearch.objects.select_related('category')
        .filter(player=player, category__enabled=True)
        .order_by('category__display_order', 'category__name')
    )

    changed = False
    if player.singular_research:
        changed = _apply_singular_allocations(rows)
    else:
        allocations = [row.allocation_percent for row in rows]
        norm = _whole_percentages(allocations)
        for idx, row in enumerate(rows):
            if abs(row.allocation_percent - norm[idx]) > 0.001:
                row.allocation_percent = norm[idx]
                changed = True
    if changed:
        for row in rows:
            row.save(update_fields=['allocation_percent'])
    return rows


def update_player_allocations(player, requested_percentages):
    """Apply and normalise submitted allocation percentages."""
    rows = ensure_player_research_rows(player)
    if player.singular_research:
        return rows
    row_by_cat = {str(row.category_id): row for row in rows}

    for cat_id, raw in requested_percentages.items():
        row = row_by_cat.get(str(cat_id))
        if not row:
            continue
        try:
            value = float(raw)
        except (TypeError, ValueError):
            value = row.allocation_percent
        row.allocation_percent = clamp_percent(value)

    norm = _whole_percentages([row.allocation_percent for row in rows])
    for idx, row in enumerate(rows):
        row.allocation_percent = norm[idx]
        row.save(update_fields=['allocation_percent'])
    return rows


def set_even_allocations(player):
    """Set all enabled category allocations to an even split."""
    rows = ensure_player_research_rows(player)
    if not rows:
        return rows
    if player.singular_research:
        _apply_singular_allocations(rows)
        for row in rows:
            row.save(update_fields=['allocation_percent'])
        return rows
    norm = _whole_percentages([1.0 for _ in rows])
    for idx, row in enumerate(rows):
        row.allocation_percent = norm[idx]
        row.save(update_fields=['allocation_percent'])
    return rows


def _apply_singular_allocations(rows, focus_category_id=None):
    """Ensure one research row has 100% and all others 0%."""
    if not rows:
        return False
    selected = None
    if focus_category_id is not None:
        for row in rows:
            if str(row.category_id) == str(focus_category_id):
                selected = row
                break
    if selected is None:
        selected = max(rows, key=lambda r: (float(r.allocation_percent or 0.0), -int(r.category_id)))
        if float(selected.allocation_percent or 0.0) <= 0:
            selected = rows[0]

    changed = False
    for row in rows:
        target = 100.0 if row == selected else 0.0
        if abs(float(row.allocation_percent or 0.0) - target) > 0.001:
            row.allocation_percent = target
            changed = True
    return changed


def set_singular_allocation(player, category_id):
    """Set focused research category for singular-research races."""
    rows = ensure_player_research_rows(player)
    if not rows:
        return rows
    if _apply_singular_allocations(rows, focus_category_id=category_id):
        for row in rows:
            row.save(update_fields=['allocation_percent'])
    return rows


def get_player_unlocked_technologies(player):
    """Return all enabled technologies unlocked by player state."""
    rows = ensure_player_research_rows(player)
    level_by_cat = {
        row.category_id: row.current_level for row in rows
    }
    unlocked = []
    for tech in Technology.objects.select_related('category').filter(enabled=True):
        if level_by_cat.get(tech.category_id, 0.0) >= tech.level:
            unlocked.append(tech)
    return unlocked


def _select_scanner_ranges(unlocked, tech_type):
    selected = None
    selected_sort_key = None
    for tech in unlocked:
        if str(tech.tech_type or '') != tech_type:
            continue
        params = _safe_params(tech)
        if 'basic_scanner_range' not in params and 'advanced_scanner_range' not in params:
            continue
        sort_key = (int(tech.level), int(tech.display_order or 0), str(tech.name or ''))
        if selected is None or sort_key > selected_sort_key:
            selected = tech
            selected_sort_key = sort_key
    if selected is None:
        return 0, 0
    params = _safe_params(selected)
    try:
        basic = int(params.get('basic_scanner_range') or 0)
    except (TypeError, ValueError):
        basic = 0
    try:
        advanced = int(params.get('advanced_scanner_range') or 0)
    except (TypeError, ValueError):
        advanced = 0
    if advanced > basic:
        basic = advanced
    return max(0, basic), max(0, advanced)


def get_player_colony_scanner_ranges(player):
    """Return scanner ranges sourced from INFRASTRUCTURE tech."""
    unlocked = list(get_player_unlocked_technologies(player))
    if not unlocked:
        return 0, 0
    return _select_scanner_ranges(unlocked, 'INFRASTRUCTURE')


def get_player_tech_effects(player):
    """Return current research effects for fleet commissioning/combat.

    Effects come from one selected technology per type:
    - Highest unlocked level in each tech type (deterministic tie-break)
    - INFRASTRUCTURE is excluded from fleet offense/defense effects
    - Highest unlocked HULL controls max cargo/fuel + thumbnail class
    """
    effects = {
        'max_warp_speed': 2,
        'max_cargo_capacity': 100,
        'max_fuel': 50.0,
        'fuel_efficiency': 1.0,
        'overmax_fuel_penalty': 1.0,
        'wormhole_fuel_per_ly': 5.0,
        'wormhole_destruction_chance': None,
        'hull_thumbnail_class': 'scout',
        'offense_level': 0.0,
        'defense_level': 0.0,
        'has_bombs': None,
        'has_miners': None,
        'has_fuel_factory': False,
        'has_wormhole_drive': False,
        'basic_scanner_range': 0,
        'advanced_scanner_range': 0,
    }
    unlocked = list(get_player_unlocked_technologies(player))
    if not unlocked:
        return effects

    selected_by_type = {}
    for tech in unlocked:
        key = str(tech.tech_type or '')
        sort_key = (int(tech.level), int(tech.display_order or 0), str(tech.name or ''))
        current = selected_by_type.get(key)
        if current is None:
            selected_by_type[key] = (sort_key, tech)
            continue
        if sort_key > current[0]:
            selected_by_type[key] = (sort_key, tech)

    selected_hull = None
    if 'HULL' in selected_by_type:
        selected_hull = selected_by_type['HULL'][1]
    selected_propulsion = None
    if 'PROPULSION' in selected_by_type:
        selected_propulsion = selected_by_type['PROPULSION'][1]

    for tech_type, selected in selected_by_type.items():
        if tech_type == 'INFRASTRUCTURE':
            continue
        tech = selected[1]
        params = _safe_params(tech)
        if tech_type == 'SCANNER':
            try:
                effects['basic_scanner_range'] = max(
                    0, int(params.get('basic_scanner_range') or 0)
                )
            except (TypeError, ValueError):
                effects['basic_scanner_range'] = 0
            try:
                effects['advanced_scanner_range'] = max(
                    0, int(params.get('advanced_scanner_range') or 0)
                )
            except (TypeError, ValueError):
                effects['advanced_scanner_range'] = 0
            if effects['advanced_scanner_range'] > effects['basic_scanner_range']:
                effects['basic_scanner_range'] = effects['advanced_scanner_range']
            continue
        max_warp = params.get('max_warp_speed')
        if max_warp is not None:
            try:
                effects['max_warp_speed'] = max(
                    effects['max_warp_speed'], int(max_warp)
                )
            except (TypeError, ValueError):
                pass
        offense_level = params.get('offense_level')
        if offense_level is not None:
            try:
                effects['offense_level'] += float(offense_level)
            except (TypeError, ValueError):
                pass
        defense_level = params.get('defense_level')
        if defense_level is not None:
            try:
                effects['defense_level'] += float(defense_level)
            except (TypeError, ValueError):
                pass
        bomb_type = normalize_bomb_type(params.get('has_bombs'))
        if bomb_type is not None:
            effects['has_bombs'] = bomb_type
        miner_type = normalize_miner_type(params.get('has_miners'))
        if miner_type is not None:
            effects['has_miners'] = miner_type
        if bool(params.get('has_fuel_factory')):
            effects['has_fuel_factory'] = True
        if bool(params.get('has_wormhole_drive')):
            effects['has_wormhole_drive'] = True

    if selected_hull is not None:
        params = _safe_params(selected_hull)
        max_cargo = params.get('max_cargo_capacity')
        if max_cargo is not None:
            try:
                effects['max_cargo_capacity'] = max(0, int(max_cargo))
            except (TypeError, ValueError):
                pass
        max_fuel = params.get('max_fuel')
        if max_fuel is not None:
            try:
                effects['max_fuel'] = max(0.0, float(max_fuel))
            except (TypeError, ValueError):
                pass
        hull_class = params.get('hull_thumbnail_class')
        if hull_class:
            effects['hull_thumbnail_class'] = str(hull_class).strip().lower()

    if selected_propulsion is not None:
        params = _safe_params(selected_propulsion)
        fuel_efficiency = params.get('fuel_efficiency')
        if fuel_efficiency is not None:
            try:
                effects['fuel_efficiency'] = max(0.05, float(fuel_efficiency))
            except (TypeError, ValueError):
                pass
        overmax_penalty = params.get('overmax_fuel_penalty')
        if overmax_penalty is not None:
            try:
                effects['overmax_fuel_penalty'] = max(0.1, float(overmax_penalty))
            except (TypeError, ValueError):
                pass
        wormhole_fuel_per_ly = params.get('wormhole_fuel_per_ly')
        if wormhole_fuel_per_ly is not None:
            try:
                effects['wormhole_fuel_per_ly'] = max(0.1, float(wormhole_fuel_per_ly))
            except (TypeError, ValueError):
                pass
        wormhole_destruction_chance = params.get('wormhole_destruction_chance')
        if wormhole_destruction_chance is not None:
            try:
                effects['wormhole_destruction_chance'] = max(
                    0.0, min(1.0, float(wormhole_destruction_chance))
                )
            except (TypeError, ValueError):
                pass
    if effects.get('has_wormhole_drive'):
        if effects.get('wormhole_destruction_chance') is None:
            try:
                fallback = 1.0 - float(effects.get('fuel_efficiency') or 1.0)
            except (TypeError, ValueError):
                fallback = 0.0
            effects['wormhole_destruction_chance'] = max(0.0, min(1.0, fallback))
    elif effects.get('wormhole_destruction_chance') is None:
        effects['wormhole_destruction_chance'] = 0.0
    return effects


def get_player_colony_defense_level(player):
    """Return latest unlocked colony defense bonus for invasion defense.

    Colony defense does not stack. It uses the single latest unlocked
    technology that defines colony_defense_level.
    """
    unlocked = list(get_player_unlocked_technologies(player))
    if not unlocked:
        return 0.0

    selected = None
    selected_level = 0.0
    selected_sort_key = None
    selected_bonus = None

    for tech in unlocked:
        params = _safe_params(tech)
        raw_level = params.get('colony_defense_level')
        if raw_level is None:
            raw_level = params.get('colony_defence_level')
        if raw_level is None:
            continue
        try:
            level = float(raw_level)
        except (TypeError, ValueError):
            continue

        sort_key = (int(tech.level), int(tech.display_order), str(tech.name))
        bonus = level
        if (
            selected is None
            or int(tech.level) > selected_sort_key[0]
            or (int(tech.level) == selected_sort_key[0] and bonus > float(selected_bonus or 0.0))
            or (int(tech.level) == selected_sort_key[0] and bonus == float(selected_bonus or 0.0) and sort_key > selected_sort_key)
        ):
            selected = tech
            selected_level = level
            selected_sort_key = sort_key
            selected_bonus = bonus

    if selected is None:
        return 0.0
    return selected_level


def build_research_budget(player):
    """Build a per-turn RP budget summary."""
    stars = player.stars.all()
    total_labs = 0
    lab_generated = 0
    converted_rp = 0
    leftover_bonus_rp = 0
    for star in stars:
        total_labs += star.labs
        lab_generated += int(calculate_available_researchpoints(star))
        if player.convert_unused_buildpoints_to_research:
            available_bp = int(calculate_available_buildpoints(star))
            used_bp = int(star.buildpoints_consumed or 0)
            converted_rp += max(0, (available_bp - used_bp) // 2)
    if player.spend_leftover_points_on_research and (player.leftover_points or 0) > 0:
        leftover_bonus_rp = int(round(float(player.leftover_points) * 10.0))
    lab_generated = int(round(lab_generated * player.race_type.research_multiplier))
    generated = int(lab_generated + converted_rp + leftover_bonus_rp)
    return {
        'total_labs': total_labs,
        'lab_generated_rp': lab_generated,
        'converted_rp': converted_rp,
        'leftover_bonus_rp': leftover_bonus_rp,
        'generated_rp': generated,
    }


@transaction.atomic
def process_player_research_for_year(player):
    """Apply one year of RP generation/allocation/level progression."""
    rows = ensure_player_research_rows(player)
    if not rows:
        if player.spend_leftover_points_on_research and (player.leftover_points or 0) > 0:
            player.leftover_points = 0.0
            player.save(update_fields=['leftover_points'])
        return []

    budget = build_research_budget(player)
    total_rp = budget['generated_rp']
    eligible_stars = _eligible_research_stars(player)

    allocations = allocate_rp_integer(total_rp, [row.allocation_percent for row in rows])
    max_level_by_category = _max_level_by_category(
        [row.category_id for row in rows]
    )
    level_map = {row.category_id: int(row.current_level or 0) for row in rows}

    _allocate_mineral_progress(rows, eligible_stars, max_level_by_category)

    unlocks = []
    for idx, row in enumerate(rows):
        max_level = max_level_by_category.get(row.category_id, int(row.current_level))
        old_level, new_level = _advance_research_row_with_requirements(
            row=row,
            added_rp=allocations[idx],
            max_level=max_level,
            eligible_stars=eligible_stars,
            allow_mineral_payment=False,
            level_map=level_map,
        )
        if int(new_level) > int(old_level):
            unlocks.append({
                'category': row.category,
                'old_level': int(old_level),
                'new_level': int(new_level),
            })
            level_map[row.category_id] = int(new_level)

    for row in rows:
        row.save(update_fields=[
            'stored_rp',
            'current_level',
            'ironium_paid',
            'boranium_paid',
            'germanium_paid',
            'resource_x_paid',
            'resource_y_paid',
            'resource_z_paid',
        ])
    if budget.get('leftover_bonus_rp', 0) > 0 and player.spend_leftover_points_on_research:
        player.leftover_points = 0.0
        player.save(update_fields=['leftover_points'])
    return unlocks


@transaction.atomic
def apply_research_bonus_rp(player, category_id, bonus_rp):
    """Apply bonus RP to one category and resolve immediate progression."""
    rows = ensure_player_research_rows(player)
    if not rows:
        return None
    row = None
    for candidate in rows:
        if candidate.category_id == category_id:
            row = candidate
            break
    if row is None:
        return None

    eligible_stars = _eligible_research_stars(player)
    max_level = _max_level_by_category([row.category_id]).get(
        row.category_id, int(row.current_level)
    )
    level_map = {item.category_id: int(item.current_level or 0) for item in rows}
    old_level, new_level = _advance_research_row_with_requirements(
        row=row,
        added_rp=bonus_rp,
        max_level=max_level,
        eligible_stars=eligible_stars,
        level_map=level_map,
    )
    row.save(update_fields=[
        'stored_rp',
        'current_level',
        'ironium_paid',
        'boranium_paid',
        'germanium_paid',
        'resource_x_paid',
        'resource_y_paid',
        'resource_z_paid',
    ])
    return {
        'category': row.category,
        'old_level': int(old_level),
        'new_level': int(new_level),
        'bonus_rp': int(bonus_rp),
    }


def build_research_screen_data(player, selected_category_id=None):
    """Build data for the research screen."""
    rows = ensure_player_research_rows(player)
    budget = build_research_budget(player)
    selected = None
    if selected_category_id:
        for row in rows:
            if str(row.category_id) == str(selected_category_id):
                selected = row.category
                break
    if not selected and rows:
        selected = rows[0].category

    next_level_items = []
    selected_research = None
    level_cost = None
    rp_per_year = None
    eta_years = None
    progress_percent = None
    next_level_req = None
    next_level_number = None
    next_level_rp_current = None
    next_level_rp_met = None
    next_level_resource_rows = []
    next_level_prerequisites = []
    next_level_blocked = False
    selected_is_maxed = False
    selected_max_level = None
    resource_labels = {
        key: get_secret_resource_label(
            key,
            bool(getattr(player, f'discovered_{key}', False)),
        )
        for key in SECRET_RESOURCE_KEYS
    }
    level_map = {row.category_id: int(row.current_level or 0) for row in rows}
    max_level_by_category = _max_level_by_category(
        [row.category_id for row in rows]
    )
    if selected is not None:
        for row in rows:
            if row.category_id == selected.id:
                selected_research = row
                break
        selected_level = int(selected_research.current_level) if selected_research else 0
        selected_max_level = max_level_by_category.get(selected.id, selected_level)
        selected_is_maxed = bool(
            selected_research and selected_max_level > 0 and selected_level >= selected_max_level
        )
        next_level = selected_level + 1 if selected_research else 1
        if selected_is_maxed:
            progress_percent = 100
        else:
            next_level_number = next_level
            next_level_req = get_level_requirement(selected.id, next_level, player=player)
            level_cost = int(next_level_req['rp_cost'])
            prereqs = get_level_prerequisites(selected.id, next_level)
            for prereq in prereqs:
                current = int(level_map.get(prereq.requires_category_id, 0) or 0)
                required = int(prereq.min_level or 0)
                met = current >= required
                if not met:
                    next_level_blocked = True
                next_level_prerequisites.append({
                    'name': prereq.requires_category.name,
                    'current': current,
                    'required': required,
                    'met': met,
                })
        if selected_research and not selected_is_maxed:
            allocations = allocate_rp_integer(
                budget['generated_rp'],
                [row.allocation_percent for row in rows]
            )
            rp_per_year = 0
            for idx, row in enumerate(rows):
                if row.category_id == selected_research.category_id:
                    rp_per_year = int(allocations[idx])
                    break
            remaining = max(0.0, level_cost - selected_research.stored_rp)
            next_level_rp_current = int(max(0, selected_research.stored_rp))
            if level_cost > 0:
                next_level_rp_met = next_level_rp_current >= level_cost
            else:
                next_level_rp_met = True
            if level_cost > 0:
                progress_percent = int(
                    max(0, min(100, (selected_research.stored_rp / float(level_cost)) * 100.0))
                )
            if rp_per_year and rp_per_year > 0:
                eta_years = int(math.ceil(remaining / rp_per_year))
        elif selected_research:
            next_level_rp_current = 0
            next_level_rp_met = False

        if not selected_is_maxed and next_level_req:
            paid_by_resource = {
                f'{key}_cost': int(getattr(selected_research, f'{key}_paid', 0) or 0)
                for key in RESEARCH_RESOURCE_KEYS
            }
            for key in RESEARCH_RESOURCE_KEYS:
                cost = int(next_level_req.get(f'{key}_cost', 0) or 0)
                if cost <= 0:
                    continue
                current = int(min(max(0, paid_by_resource.get(f'{key}_cost', 0)), cost))
                if key in SECRET_RESOURCE_KEYS:
                    label = get_secret_resource_label(
                        key,
                        bool(getattr(player, f'discovered_{key}', False)),
                    )
                else:
                    label = RESEARCH_RESOURCE_LABELS.get(key, str(key).title())
                next_level_resource_rows.append({
                    'label': label,
                    'current': current,
                    'cost': cost,
                    'met': current >= cost,
                    'unit': 'kt',
                })

        if not selected_is_maxed:
            items = Technology.objects.filter(
                enabled=True,
                category=selected,
                level=next_level
            ).order_by('display_order', 'name')
            for item in items:
                params = _safe_params(item)
                next_level_items.append({
                    'name': item.name,
                    'description': item.description,
                    'tech_type': item.tech_type,
                    'tech_type_label': _tech_type_label(item.tech_type),
                    'thumbnail_path': get_technology_thumbnail_path(item),
                    'thumbnail_paths': get_technology_thumbnail_paths(item),
                    'thumbnail_initial_index': get_technology_thumbnail_initial_index(item),
                    'params': params,
                    'params_display': [
                        {'label': _format_param_key(key), 'value': _format_param_value(key, value)}
                        for key, value in params.items()
                        if _should_show_param(key, value)
                    ] + build_production_cost_entries(params, resource_labels=resource_labels),
                })

    for row in rows:
        row_max_level = max_level_by_category.get(row.category_id, int(row.current_level))
        row_next_level = int(row.current_level) + 1
        if row_max_level > 0 and int(row.current_level) >= row_max_level:
            row.next_level_cost = 0
            row.progress_percent = 100
        else:
            row_next_cost = int(get_level_requirement(
                row.category_id, row_next_level, player=player
            )['rp_cost'])
            row.next_level_cost = row_next_cost
            if row_next_cost > 0:
                pct = int((float(row.stored_rp) / float(row_next_cost)) * 100.0)
                row.progress_percent = max(0, min(100, pct))
            else:
                row.progress_percent = 0

    return {
        'budget': budget,
        'rows': rows,
        'selected_category': selected,
        'selected_research': selected_research,
        'selected_is_maxed': selected_is_maxed,
        'selected_max_level': selected_max_level,
        'next_level_number': next_level_number,
        'next_level_cost': level_cost,
        'next_level_rp_current': next_level_rp_current,
        'next_level_rp_met': next_level_rp_met,
        'next_level_progress_percent': progress_percent,
        'next_level_rp_per_year': rp_per_year,
        'next_level_eta_years': eta_years,
        'next_level_requirements': next_level_req if selected else None,
        'next_level_resource_rows': next_level_resource_rows,
        'next_level_prerequisites': next_level_prerequisites,
        'next_level_blocked': next_level_blocked,
        'next_level_items': next_level_items,
    }
