from __future__ import unicode_literals

from math import sqrt

from django.db.models import Q

from .models import Player, PlayerDiplomaticStance, Report


STANCE_HOSTILE = 'HOSTILE'
STANCE_COLD = 'COLD'
STANCE_NEUTRAL = 'NEUTRAL'
STANCE_WARM = 'WARM'
STANCE_ALLIED = 'ALLIED'

STANCE_CHOICES = [
    (STANCE_HOSTILE, 'Hostile'),
    (STANCE_COLD, 'Cold'),
    (STANCE_NEUTRAL, 'Neutral'),
    (STANCE_WARM, 'Warm'),
    (STANCE_ALLIED, 'Allied'),
]

STANCE_LABELS = dict(STANCE_CHOICES)
STANCE_SCORES = {
    STANCE_HOSTILE: 0,
    STANCE_COLD: 1,
    STANCE_NEUTRAL: 2,
    STANCE_WARM: 3,
    STANCE_ALLIED: 4,
}
COMBINED_SCORE_COMBAT_CHANCES = {
    2: 70,
    3: 50,
    4: 30,
    5: 8,
    6: 1,
    7: 0,
    8: 0,
}
DEFAULT_STANCE = STANCE_NEUTRAL

PERMISSION_ORBITAL_DEFENSE_CHANCE_SCALE = 'orbital_defense_chance_scale'
PERMISSION_SHIPYARD_REPAIR_RATE = 'shipyard_repair_rate'
PERMISSION_ALLOW_TRANSFER_RAID_DEFENSE = 'allow_transfer_raid_defense'
PERMISSION_ALLOW_TRANSFER_RAID_ROLL = 'allow_transfer_raid_roll'
PERMISSION_SHARE_INTEL = 'share_intel'
PERMISSION_SHARE_SCANNERS = 'share_scanners'
PERMISSION_SHARE_FLEET_REPORT_LEVEL = 'share_fleet_report_level'
PERMISSION_SHARE_COLONY_REPORT_LEVEL = 'share_colony_report_level'
PERMISSION_REVEAL_CLOAKED_FLEETS = 'reveal_cloaked_fleets'

FLEET_REPORT_LEVEL_ADVANCED = 'advanced'
FLEET_REPORT_LEVEL_CARGO = 'cargo'
FLEET_REPORT_LEVEL_FULL = 'full'

COLONY_REPORT_LEVEL_ADVANCED = 'advanced'
COLONY_REPORT_LEVEL_FULL = 'full'

def _self_combat_percent(stance):
    stance = (stance or DEFAULT_STANCE).upper()
    if stance not in STANCE_SCORES:
        stance = DEFAULT_STANCE
    if stance == STANCE_HOSTILE:
        return 100
    score = STANCE_SCORES[stance] + STANCE_SCORES[stance]
    return COMBINED_SCORE_COMBAT_CHANCES.get(score, 0)


_STANCE_SELF_COMBAT_PERCENT = {
    STANCE_HOSTILE: _self_combat_percent(STANCE_HOSTILE),
    STANCE_COLD: _self_combat_percent(STANCE_COLD),
    STANCE_NEUTRAL: _self_combat_percent(STANCE_NEUTRAL),
    STANCE_WARM: _self_combat_percent(STANCE_WARM),
    STANCE_ALLIED: _self_combat_percent(STANCE_ALLIED),
}

STANCE_PERMISSION_PROFILES = {
    STANCE_HOSTILE: {
        PERMISSION_ORBITAL_DEFENSE_CHANCE_SCALE: 1.0,
        PERMISSION_SHIPYARD_REPAIR_RATE: 0.0,
        PERMISSION_ALLOW_TRANSFER_RAID_DEFENSE: True,
        PERMISSION_ALLOW_TRANSFER_RAID_ROLL: True,
        PERMISSION_SHARE_INTEL: False,
        PERMISSION_SHARE_SCANNERS: False,
        PERMISSION_SHARE_FLEET_REPORT_LEVEL: FLEET_REPORT_LEVEL_ADVANCED,
        PERMISSION_SHARE_COLONY_REPORT_LEVEL: COLONY_REPORT_LEVEL_ADVANCED,
        PERMISSION_REVEAL_CLOAKED_FLEETS: False,
    },
    STANCE_COLD: {
        PERMISSION_ORBITAL_DEFENSE_CHANCE_SCALE: _STANCE_SELF_COMBAT_PERCENT[STANCE_COLD] / 100.0,
        PERMISSION_SHIPYARD_REPAIR_RATE: 0.0,
        PERMISSION_ALLOW_TRANSFER_RAID_DEFENSE: True,
        PERMISSION_ALLOW_TRANSFER_RAID_ROLL: True,
        PERMISSION_SHARE_INTEL: False,
        PERMISSION_SHARE_SCANNERS: False,
        PERMISSION_SHARE_FLEET_REPORT_LEVEL: FLEET_REPORT_LEVEL_ADVANCED,
        PERMISSION_SHARE_COLONY_REPORT_LEVEL: COLONY_REPORT_LEVEL_ADVANCED,
        PERMISSION_REVEAL_CLOAKED_FLEETS: False,
    },
    STANCE_NEUTRAL: {
        PERMISSION_ORBITAL_DEFENSE_CHANCE_SCALE: _STANCE_SELF_COMBAT_PERCENT[STANCE_NEUTRAL] / 100.0,
        PERMISSION_SHIPYARD_REPAIR_RATE: 0.25,
        PERMISSION_ALLOW_TRANSFER_RAID_DEFENSE: True,
        PERMISSION_ALLOW_TRANSFER_RAID_ROLL: True,
        PERMISSION_SHARE_INTEL: False,
        PERMISSION_SHARE_SCANNERS: False,
        PERMISSION_SHARE_FLEET_REPORT_LEVEL: FLEET_REPORT_LEVEL_ADVANCED,
        PERMISSION_SHARE_COLONY_REPORT_LEVEL: COLONY_REPORT_LEVEL_ADVANCED,
        PERMISSION_REVEAL_CLOAKED_FLEETS: False,
    },
    STANCE_WARM: {
        PERMISSION_ORBITAL_DEFENSE_CHANCE_SCALE: _STANCE_SELF_COMBAT_PERCENT[STANCE_WARM] / 100.0,
        PERMISSION_SHIPYARD_REPAIR_RATE: 0.5,
        PERMISSION_ALLOW_TRANSFER_RAID_DEFENSE: True,
        PERMISSION_ALLOW_TRANSFER_RAID_ROLL: True,
        PERMISSION_SHARE_INTEL: False,
        PERMISSION_SHARE_SCANNERS: False,
        PERMISSION_SHARE_FLEET_REPORT_LEVEL: FLEET_REPORT_LEVEL_ADVANCED,
        PERMISSION_SHARE_COLONY_REPORT_LEVEL: COLONY_REPORT_LEVEL_ADVANCED,
        PERMISSION_REVEAL_CLOAKED_FLEETS: False,
    },
    STANCE_ALLIED: {
        PERMISSION_ORBITAL_DEFENSE_CHANCE_SCALE: 0.0,
        PERMISSION_SHIPYARD_REPAIR_RATE: 1.0,
        PERMISSION_ALLOW_TRANSFER_RAID_DEFENSE: False,
        PERMISSION_ALLOW_TRANSFER_RAID_ROLL: False,
        PERMISSION_SHARE_INTEL: True,
        PERMISSION_SHARE_SCANNERS: True,
        PERMISSION_SHARE_FLEET_REPORT_LEVEL: FLEET_REPORT_LEVEL_FULL,
        PERMISSION_SHARE_COLONY_REPORT_LEVEL: COLONY_REPORT_LEVEL_FULL,
        PERMISSION_REVEAL_CLOAKED_FLEETS: False,
    },
}

STANCE_EFFECT_ITEMS = {
    STANCE_HOSTILE: [
        {
            'name': 'Defences',
            'summary': 'On Alert',
            'description': 'Colony defenses respond at maximum readiness.',
        },
    ],
    STANCE_COLD: [
        {
            'name': 'Defences',
            'summary': 'Vigilant',
            'description': 'Colony defenses stay on a high-alert footing.',
        },
    ],
    STANCE_NEUTRAL: [
        {
            'name': 'Defences',
            'summary': 'On Guard',
            'description': 'Colony defenses remain active and cautious.',
        },
        {
            'name': 'Shipyards',
            'summary': '25% Repair',
            'description': 'Visiting fleets repair at 25% of normal rate.',
        },
    ],
    STANCE_WARM: [
        {
            'name': 'Defences',
            'summary': 'Lowered',
            'description': 'Colony defenses are reduced for friendly traffic.',
        },
        {
            'name': 'Shipyards',
            'summary': '50% Repair',
            'description': 'Visiting fleets repair at 50% of normal rate.',
        },
    ],
    STANCE_ALLIED: [
        {
            'name': 'Defences',
            'summary': 'At Ease',
            'description': 'Colony defenses stand down for allied fleets.',
        },
        {
            'name': 'Shipyards',
            'summary': 'Full Repair',
            'description': 'Visiting fleets repair at full rate after your fleets.',
        },
        {
            'name': 'Resource Access',
            'summary': 'Full Access',
            'description': 'Resource transfers proceed without defensive resistance.',
        },
        {
            'name': 'Intel',
            'summary': 'Full',
            'description': 'Shares full allied fleet and colony reports.',
        },
        {
            'name': 'Scanners',
            'summary': 'Shared',
            'description': 'Scanner coverage contributes to allied sensor range.',
        },
    ],
}


def normalise_stance(value):
    value = (value or DEFAULT_STANCE).upper()
    return value if value in STANCE_LABELS else DEFAULT_STANCE


def stance_meets_minimum(value, minimum_stance):
    value = normalise_stance(value)
    minimum_stance = normalise_stance(minimum_stance)
    return STANCE_SCORES.get(value, 0) >= STANCE_SCORES.get(minimum_stance, 0)


def stance_label(value):
    return STANCE_LABELS.get(normalise_stance(value), STANCE_LABELS[DEFAULT_STANCE])


def combat_chance_percent(stance_a, stance_b):
    stance_a = normalise_stance(stance_a)
    stance_b = normalise_stance(stance_b)
    if stance_a == STANCE_HOSTILE and stance_b == STANCE_NEUTRAL:
        return 98
    if stance_b == STANCE_HOSTILE and stance_a == STANCE_NEUTRAL:
        return 98
    if stance_a == STANCE_HOSTILE and stance_b == STANCE_WARM:
        return 95
    if stance_b == STANCE_HOSTILE and stance_a == STANCE_WARM:
        return 95
    if stance_a == STANCE_HOSTILE and stance_b == STANCE_ALLIED:
        return 90
    if stance_b == STANCE_HOSTILE and stance_a == STANCE_ALLIED:
        return 90
    if stance_a == STANCE_HOSTILE or stance_b == STANCE_HOSTILE:
        return 100
    score = STANCE_SCORES[stance_a] + STANCE_SCORES[stance_b]
    return COMBINED_SCORE_COMBAT_CHANCES.get(score, 0)


def player_diplomacy_multiplier(player):
    if not player:
        return 1.0
    race_type = getattr(player, 'race_type', None)
    try:
        value = float(getattr(race_type, 'diplomacy_multiplier', 1.0))
    except (TypeError, ValueError):
        value = 1.0
    return max(0.01, value)


def combined_diplomacy_chance_scale(player_a, player_b):
    diplomacy_a = player_diplomacy_multiplier(player_a)
    diplomacy_b = player_diplomacy_multiplier(player_b)
    return 1.0 / sqrt(diplomacy_a * diplomacy_b)


def combat_chance_with_diplomacy_percent(stance_a, stance_b, player_a, player_b):
    base_chance = float(combat_chance_percent(stance_a, stance_b))
    scaled = base_chance * combined_diplomacy_chance_scale(player_a, player_b)
    return max(0, min(100, int(round(scaled))))


def combat_chance_modifier_percent(player_a, player_b):
    modifier = combined_diplomacy_chance_scale(player_a, player_b) - 1.0
    return int(round(modifier * 100.0))


def combat_readiness_multiplier(stance_self, stance_other):
    own_score = STANCE_SCORES[normalise_stance(stance_self)]
    other_score = STANCE_SCORES[normalise_stance(stance_other)]
    delta = other_score - own_score
    modifier = 1.0 + (0.10 * float(delta))
    return max(0.6, min(1.4, modifier))


def player_default_stance(player):
    return normalise_stance(getattr(player, 'default_diplomatic_stance', DEFAULT_STANCE))


def player_pending_default_stance(player):
    # Default stance only seeds future first-contact rows, so it does not need
    # turn-boundary pending treatment.
    return player_default_stance(player) if player else DEFAULT_STANCE


def stance_permission_profile(stance):
    return STANCE_PERMISSION_PROFILES[normalise_stance(stance)]


def stance_permission_value(stance, permission_key, default=None):
    profile = stance_permission_profile(stance)
    if permission_key in profile:
        return profile[permission_key]
    return default


def stance_effect_items(stance):
    return STANCE_EFFECT_ITEMS.get(normalise_stance(stance), [])


def build_stance_map(player):
    if not player:
        return {}
    return {
        row.target_player_id: normalise_stance(row.stance)
        for row in PlayerDiplomaticStance.objects.filter(player=player)
    }


def build_pending_stance_map(player):
    if not player:
        return {}
    return {
        row.target_player_id: normalise_stance(getattr(row, 'pending_stance', row.stance))
        for row in PlayerDiplomaticStance.objects.filter(player=player)
    }


def stance_towards(player, other_player, stance_map=None):
    if not player or not other_player or player.id == other_player.id:
        return player_default_stance(player) if player else DEFAULT_STANCE
    stance_map = stance_map if stance_map is not None else build_stance_map(player)
    return normalise_stance(stance_map.get(other_player.id, player_default_stance(player)))


def player_permission_value(player, other_player, permission_key, default=None, stance_map=None):
    stance = stance_towards(player, other_player, stance_map=stance_map)
    return stance_permission_value(stance, permission_key, default=default)


def player_can_refuel_fleet(player, other_player, stance_map=None):
    if not player or not other_player:
        return False
    if player.id == other_player.id:
        return True
    return stance_meets_minimum(
        stance_towards(player, other_player, stance_map=stance_map),
        STANCE_NEUTRAL,
    )


def player_can_transfer_with_fleet(
    player,
    other_player,
    stance_map=None,
    other_stance_map=None,
):
    """Fleet-to-fleet material/colonist transfers require mutual alliance."""
    if not player or not other_player:
        return False
    if player.id == other_player.id:
        return True
    return (
        stance_towards(player, other_player, stance_map=stance_map) == STANCE_ALLIED and
        stance_towards(other_player, player, stance_map=other_stance_map) == STANCE_ALLIED
    )


def player_grants_permission(player, other_player, permission_key, stance_map=None):
    return bool(
        player_permission_value(
            player,
            other_player,
            permission_key,
            default=False,
            stance_map=stance_map,
        )
    )


def player_shared_fleet_report_level(player, other_player, stance_map=None):
    return str(
        player_permission_value(
            player,
            other_player,
            PERMISSION_SHARE_FLEET_REPORT_LEVEL,
            default=FLEET_REPORT_LEVEL_ADVANCED,
            stance_map=stance_map,
        ) or FLEET_REPORT_LEVEL_ADVANCED
    ).lower()


def player_shared_colony_report_level(player, other_player, stance_map=None):
    return str(
        player_permission_value(
            player,
            other_player,
            PERMISSION_SHARE_COLONY_REPORT_LEVEL,
            default=COLONY_REPORT_LEVEL_ADVANCED,
            stance_map=stance_map,
        ) or COLONY_REPORT_LEVEL_ADVANCED
    ).lower()


def shared_fleet_report_policy(player, other_player, stance_map=None):
    level = player_shared_fleet_report_level(player, other_player, stance_map=stance_map)
    policies = {
        FLEET_REPORT_LEVEL_ADVANCED: ('advanced', False),
        FLEET_REPORT_LEVEL_CARGO: ('advanced', True),
        FLEET_REPORT_LEVEL_FULL: ('ownership', True),
    }
    return policies.get(level, policies[FLEET_REPORT_LEVEL_ADVANCED])


def shared_colony_report_policy(player, other_player, stance_map=None):
    level = player_shared_colony_report_level(player, other_player, stance_map=stance_map)
    policies = {
        COLONY_REPORT_LEVEL_ADVANCED: 'advanced',
        COLONY_REPORT_LEVEL_FULL: 'ownership',
    }
    return policies.get(level, policies[COLONY_REPORT_LEVEL_ADVANCED])


def player_reveals_cloaked_fleets(player, other_player):
    if not player or not other_player:
        return False
    if not player_grants_permission(player, other_player, PERMISSION_SHARE_INTEL):
        return False
    default_reveal = bool(
        player_permission_value(
            player,
            other_player,
            PERMISSION_REVEAL_CLOAKED_FLEETS,
            default=False,
        )
    )
    row = PlayerDiplomaticStance.objects.filter(
        player=player,
        target_player=other_player,
    ).first()
    if row is None:
        return default_reveal
    return bool(getattr(row, 'reveal_cloaked_fleets', default_reveal))


def encountered_players(player):
    if not player:
        return []

    player_ids = set(
        PlayerDiplomaticStance.objects.filter(player=player)
        .values_list('target_player_id', flat=True)
    )

    reports = Report.objects.filter(
        player=player,
        target_type__in=['star', 'fleet'],
    ).order_by('id')

    player_names = set()
    for report in reports:
        try:
            data = report.get_report_data()
        except Exception:
            continue
        player_name = data.get('player_name')
        if player_name and player_name != player.name:
            player_names.add(player_name)

    if not player_names and not player_ids:
        return []

    others = list(
        Player.objects.filter(game=player.game)
        .filter(Q(id__in=player_ids) | Q(name__in=player_names))
        .exclude(id=player.id)
        .order_by('name', 'id')
    )
    return others


def has_encountered_player(player, other_player):
    """Return True when player has discovered other_player via diplomacy/report state."""
    if not player or not other_player:
        return False
    if player.id == other_player.id:
        return True
    if player.game_id != other_player.game_id:
        return False
    if PlayerDiplomaticStance.objects.filter(
        player=player,
        target_player=other_player,
    ).exists():
        return True
    reports = Report.objects.filter(
        player=player,
        target_type__in=['star', 'fleet'],
    ).order_by('id')
    for report in reports:
        try:
            data = report.get_report_data()
        except Exception:
            continue
        if data.get('player_name') == other_player.name:
            return True
    return False


def update_player_stances(player, default_stance, stance_by_target_short_id):
    if not player:
        return

    player.default_diplomatic_stance = normalise_stance(default_stance)
    player.save(update_fields=['default_diplomatic_stance'])

    targets = {
        p.short_id: p for p in Player.objects.filter(game=player.game).exclude(id=player.id)
    }
    for target_short_id, stance_value in stance_by_target_short_id.items():
        target = targets.get(target_short_id)
        if not target:
            continue
        stance_value = normalise_stance(stance_value)
        row, _created = PlayerDiplomaticStance.objects.get_or_create(
            player=player,
            target_player=target,
            defaults={
                'stance': player_default_stance(player),
                'pending_stance': stance_value,
            },
        )
        if row.pending_stance != stance_value:
            row.pending_stance = stance_value
            row.save(update_fields=['pending_stance'])


def ensure_contact_stance_entry(player, other_player):
    if not player or not other_player or player.id == other_player.id:
        return None
    if player.game_id != other_player.game_id:
        return None
    row, _created = PlayerDiplomaticStance.objects.get_or_create(
        player=player,
        target_player=other_player,
        defaults={
            'stance': player_default_stance(player),
            'pending_stance': player_default_stance(player),
        },
    )
    return row


def apply_pending_diplomacy_snapshot(game):
    """Apply pending diplomacy changes to effective stance values for this turn."""
    if not game:
        return []

    changed_rows = []

    for player in Player.objects.filter(game=game):
        pending_default = player_pending_default_stance(player)
        if normalise_stance(player.default_diplomatic_stance) != pending_default:
            player.default_diplomatic_stance = pending_default
            player.save(update_fields=['default_diplomatic_stance'])

    rows = PlayerDiplomaticStance.objects.filter(
        player__game=game
    ).select_related('player', 'target_player')
    for row in rows:
        old_stance = normalise_stance(row.stance)
        new_stance = normalise_stance(getattr(row, 'pending_stance', row.stance))
        if old_stance == new_stance:
            continue
        row.stance = new_stance
        row.save(update_fields=['stance'])
        changed_rows.append({
            'source_player': row.player,
            'target_player': row.target_player,
            'old_stance': old_stance,
            'new_stance': new_stance,
        })

    return changed_rows
