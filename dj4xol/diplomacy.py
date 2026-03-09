from __future__ import unicode_literals

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


def normalise_stance(value):
    value = (value or DEFAULT_STANCE).upper()
    return value if value in STANCE_LABELS else DEFAULT_STANCE


def stance_label(value):
    return STANCE_LABELS.get(normalise_stance(value), STANCE_LABELS[DEFAULT_STANCE])


def combat_chance_percent(stance_a, stance_b):
    stance_a = normalise_stance(stance_a)
    stance_b = normalise_stance(stance_b)
    if stance_a == STANCE_HOSTILE or stance_b == STANCE_HOSTILE:
        return 100
    score = STANCE_SCORES[stance_a] + STANCE_SCORES[stance_b]
    return COMBINED_SCORE_COMBAT_CHANCES.get(score, 0)


def combat_readiness_multiplier(stance_self, stance_other):
    own_score = STANCE_SCORES[normalise_stance(stance_self)]
    other_score = STANCE_SCORES[normalise_stance(stance_other)]
    delta = other_score - own_score
    modifier = 1.0 + (0.10 * float(delta))
    return max(0.6, min(1.4, modifier))


def player_default_stance(player):
    return normalise_stance(getattr(player, 'default_diplomatic_stance', DEFAULT_STANCE))


def build_stance_map(player):
    if not player:
        return {}
    return {
        row.target_player_id: normalise_stance(row.stance)
        for row in PlayerDiplomaticStance.objects.filter(player=player)
    }


def stance_towards(player, other_player, stance_map=None):
    if not player or not other_player or player.id == other_player.id:
        return player_default_stance(player) if player else DEFAULT_STANCE
    stance_map = stance_map if stance_map is not None else build_stance_map(player)
    return normalise_stance(stance_map.get(other_player.id, player_default_stance(player)))


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
            defaults={'stance': stance_value},
        )
        if row.stance != stance_value:
            row.stance = stance_value
            row.save(update_fields=['stance'])


def ensure_contact_stance_entry(player, other_player):
    if not player or not other_player or player.id == other_player.id:
        return None
    if player.game_id != other_player.game_id:
        return None
    row, _created = PlayerDiplomaticStance.objects.get_or_create(
        player=player,
        target_player=other_player,
        defaults={'stance': player_default_stance(player)},
    )
    return row
