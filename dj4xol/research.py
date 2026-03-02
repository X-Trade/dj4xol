import json
import math

from django.db import models, transaction

from .colony_rules import calculate_available_buildpoints, calculate_available_researchpoints
from .bombardment_rules import normalize_bomb_type, normalize_miner_type
from .models import (
    DefaultResearchLevelRequirement,
    PlayerResearch,
    ResearchCategory,
    ResearchLevelRequirement,
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

TECH_PARAM_LABELS = {
    'max_warp_speed': 'Maximum Warp',
    'max_cargo_capacity': 'Cargo Capacity',
    'max_fuel': 'Fuel Capacity',
    'fuel_efficiency': 'Fuel Efficiency',
    'overmax_fuel_penalty': 'Overmax Fuel Penalty',
    'wormhole_fuel_per_ly': 'Wormhole Fuel (mg/ly)',
    'hull_thumbnail_class': 'Hull Class',
    'offense_level': 'Offense Level',
    'defense_level': 'Defense Level',
    'colony_defense_level': 'Colony Defense Level',
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
    return value


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
        if changed:
            dirty.append(existing)
    if missing:
        ResearchLevelRequirement.objects.bulk_create(missing)
    for row in dirty:
        row.save(update_fields=[
            'rp_cost', 'ironium_cost', 'boranium_cost', 'germanium_cost'
        ])


def get_level_requirement(category_id, level):
    """Resolve RP/mineral requirements for a category level."""
    try:
        req = ResearchLevelRequirement.objects.get(
            category_id=category_id, level=level
        )
        return {
            'rp_cost': int(req.rp_cost),
            'ironium_cost': int(req.ironium_cost),
            'boranium_cost': int(req.boranium_cost),
            'germanium_cost': int(req.germanium_cost),
        }
    except ResearchLevelRequirement.DoesNotExist:
        pass

    default = DefaultResearchLevelRequirement.objects.filter(level=level).first()
    if default:
        return {
            'rp_cost': int(default.rp_cost),
            'ironium_cost': int(default.ironium_cost),
            'boranium_cost': int(default.boranium_cost),
            'germanium_cost': int(default.germanium_cost),
        }
    return {
        'rp_cost': int(rp_cost_for_level(level)),
        'ironium_cost': 0,
        'boranium_cost': 0,
        'germanium_cost': 0,
    }


def _eligible_research_stars(player):
    """Return owned colonies with labs that can pay research requirements."""
    return list(
        player.stars.filter(labs__gt=0).order_by('-labs', '-ironium_inventory', 'id')
    )


def _can_pay_requirement(stars, requirement):
    """Check if eligible stars have enough minerals for this requirement."""
    needed_iron = int(requirement.get('ironium_cost', 0))
    needed_bor = int(requirement.get('boranium_cost', 0))
    needed_germ = int(requirement.get('germanium_cost', 0))
    total_iron = sum(star.ironium_inventory for star in stars)
    total_bor = sum(star.boranium_inventory for star in stars)
    total_germ = sum(star.germanium_inventory for star in stars)
    return (
        total_iron >= needed_iron and
        total_bor >= needed_bor and
        total_germ >= needed_germ
    )


def _consume_requirement(stars, requirement):
    """Consume required minerals from eligible stars, largest labs first."""
    fields = (
        ('ironium_inventory', int(requirement.get('ironium_cost', 0))),
        ('boranium_inventory', int(requirement.get('boranium_cost', 0))),
        ('germanium_inventory', int(requirement.get('germanium_cost', 0))),
    )
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
        star.save(update_fields=[
            'ironium_inventory', 'boranium_inventory', 'germanium_inventory'
        ])
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


def _advance_research_row_with_requirements(row, added_rp, max_level, eligible_stars):
    """Apply RP and advance one research row, consuming required minerals."""
    old_level = float(row.current_level or 0.0)
    level = old_level
    stored_rp = int(row.stored_rp) + int(added_rp or 0)
    while int(level) < int(max_level):
        next_level = int(level) + 1
        requirement = get_level_requirement(row.category_id, next_level)
        rp_cost = int(requirement['rp_cost'])
        if stored_rp < rp_cost:
            break
        if not _can_pay_requirement(eligible_stars, requirement):
            break
        if not _consume_requirement(eligible_stars, requirement):
            break
        stored_rp -= rp_cost
        level += 1.0
    row.current_level = level
    row.stored_rp = stored_rp
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
        'hull_thumbnail_class': 'scout',
        'offense_level': 0.0,
        'defense_level': 0.0,
        'has_bombs': None,
        'has_miners': None,
        'has_fuel_factory': False,
        'has_wormhole_drive': False,
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
        if selected is None or sort_key > selected_sort_key:
            selected = tech
            selected_level = level
            selected_sort_key = sort_key

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

    unlocks = []
    for idx, row in enumerate(rows):
        max_level = max_level_by_category.get(row.category_id, int(row.current_level))
        old_level, new_level = _advance_research_row_with_requirements(
            row=row,
            added_rp=allocations[idx],
            max_level=max_level,
            eligible_stars=eligible_stars,
        )
        if int(new_level) > int(old_level):
            unlocks.append({
                'category': row.category,
                'old_level': int(old_level),
                'new_level': int(new_level),
            })

    for row in rows:
        row.save(update_fields=['stored_rp', 'current_level'])
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
    old_level, new_level = _advance_research_row_with_requirements(
        row=row,
        added_rp=bonus_rp,
        max_level=max_level,
        eligible_stars=eligible_stars,
    )
    row.save(update_fields=['stored_rp', 'current_level'])
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
    next_level_resource_rows = []
    selected_is_maxed = False
    selected_max_level = None
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
            next_level_req = get_level_requirement(selected.id, next_level)
            level_cost = int(next_level_req['rp_cost'])
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
            next_level_rp_current = int(min(max(0, selected_research.stored_rp), level_cost))
            if level_cost > 0:
                progress_percent = int(
                    max(0, min(100, (selected_research.stored_rp / float(level_cost)) * 100.0))
                )
            if rp_per_year and rp_per_year > 0:
                eta_years = int(math.ceil(remaining / rp_per_year))
        elif selected_research:
            next_level_rp_current = 0

        if not selected_is_maxed and next_level_req:
            eligible_stars = _eligible_research_stars(player)
            available_by_resource = {
                'ironium_cost': sum(star.ironium_inventory for star in eligible_stars),
                'boranium_cost': sum(star.boranium_inventory for star in eligible_stars),
                'germanium_cost': sum(star.germanium_inventory for star in eligible_stars),
            }
            for key, label in (
                ('ironium_cost', 'Ironium'),
                ('boranium_cost', 'Boranium'),
                ('germanium_cost', 'Germanium'),
            ):
                cost = int(next_level_req.get(key, 0))
                if cost <= 0:
                    continue
                current = int(min(max(0, available_by_resource.get(key, 0)), cost))
                next_level_resource_rows.append({
                    'label': label,
                    'current': current,
                    'cost': cost,
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
                    ],
                })

    for row in rows:
        row_max_level = max_level_by_category.get(row.category_id, int(row.current_level))
        row_next_level = int(row.current_level) + 1
        if row_max_level > 0 and int(row.current_level) >= row_max_level:
            row.next_level_cost = 0
            row.progress_percent = 100
        else:
            row_next_cost = int(get_level_requirement(
                row.category_id, row_next_level
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
        'next_level_progress_percent': progress_percent,
        'next_level_rp_per_year': rp_per_year,
        'next_level_eta_years': eta_years,
        'next_level_requirements': next_level_req if selected else None,
        'next_level_resource_rows': next_level_resource_rows,
        'next_level_items': next_level_items,
    }
