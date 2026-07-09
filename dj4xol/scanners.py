from __future__ import annotations

from typing import Dict, Iterable, List, Tuple


def _coerce_ranges(basic, advanced):
    try:
        basic = int(basic or 0)
    except (TypeError, ValueError):
        basic = 0
    try:
        advanced = int(advanced or 0)
    except (TypeError, ValueError):
        advanced = 0
    if advanced > basic:
        basic = advanced
    return max(0, basic), max(0, advanced)


def _append_sources_for_owner(game, owner, output, get_player_colony_scanner_ranges):
    for fleet in game.fleets.filter(player=owner):
        basic, advanced = _coerce_ranges(
            getattr(fleet, 'basic_scanner_range', 0),
            getattr(fleet, 'advanced_scanner_range', 0),
        )
        if basic <= 0 and advanced <= 0:
            continue
        output.append({
            'x': int(fleet.x),
            'y': int(fleet.y),
            'basic': basic,
            'advanced': advanced,
            'source_type': 'fleet',
            'owner_id': getattr(owner, 'id', None),
        })

    colony_basic, colony_advanced = get_player_colony_scanner_ranges(owner)
    colony_basic, colony_advanced = _coerce_ranges(colony_basic, colony_advanced)
    if colony_basic > 0 or colony_advanced > 0:
        for star in game.stars.filter(player=owner):
            output.append({
                'x': int(star.x),
                'y': int(star.y),
                'basic': colony_basic,
                'advanced': colony_advanced,
                'source_type': 'colony',
                'owner_id': getattr(owner, 'id', None),
            })


def get_owned_scanner_sources_for_player(game, player):
    """Return scanner source dicts for the player's own fleets and colonies."""
    if not player:
        return []
    if getattr(game, 'no_scanners', False):
        return []
    from .research import get_player_colony_scanner_ranges

    sources = []
    _append_sources_for_owner(game, player, sources, get_player_colony_scanner_ranges)
    return sources


def get_scanner_sources_for_player(game, player):
    """Return scanner source dicts for a player (fleets + colonies)."""
    if not player:
        return []
    if getattr(game, 'no_scanners', False):
        return []
    from .diplomacy import (
        PERMISSION_SHARE_SCANNERS,
        player_grants_permission,
    )
    from .models import Player
    from .research import get_player_colony_scanner_ranges

    sources = []
    _append_sources_for_owner(game, player, sources, get_player_colony_scanner_ranges)

    scanner_grantors = Player.objects.filter(game=game).exclude(id=player.id).exclude(defeated=True)
    for grantor in scanner_grantors:
        if player_grants_permission(grantor, player, PERMISSION_SHARE_SCANNERS):
            _append_sources_for_owner(game, grantor, sources, get_player_colony_scanner_ranges)
    return sources


def strongest_scanner_circles_by_position(sources, range_key):
    """Return one max-radius scanner circle per map position."""
    strongest = {}
    for src in sources:
        try:
            x = int(src.get('x'))
            y = int(src.get('y'))
            radius = int(src.get(range_key) or 0)
        except (TypeError, ValueError):
            continue
        if radius <= 0:
            continue
        key = (x, y)
        if radius > strongest.get(key, 0):
            strongest[key] = radius
    return [
        {
            'center_x': x,
            'center_y': y,
            'radius': radius,
        }
        for (x, y), radius in strongest.items()
    ]


def _in_range(x, y, sx, sy, radius):
    if radius <= 0:
        return False
    dx = float(x) - float(sx)
    dy = float(y) - float(sy)
    return (dx * dx) + (dy * dy) <= float(radius) * float(radius)


def position_in_scanner_range(x, y, sources, range_key='basic'):
    for src in sources:
        radius = int(src.get(range_key) or 0)
        if radius <= 0:
            continue
        if _in_range(x, y, src.get('x'), src.get('y'), radius):
            return True
    return False


def fleet_is_cloaked(fleet):
    if not fleet:
        return False
    if not getattr(fleet, 'player_id', None):
        return False
    try:
        max_cloaked_warp = int(getattr(fleet, 'max_cloaked_warp', -1) or 0)
    except (TypeError, ValueError):
        max_cloaked_warp = -1
    if max_cloaked_warp < 0:
        return False
    try:
        travel_warp = int(getattr(fleet, 'travel_warp', 0) or 0)
    except (TypeError, ValueError):
        travel_warp = 0
    return travel_warp <= max_cloaked_warp


def fleet_revealed_by_advanced_scanners(fleet, sources):
    if not fleet:
        return False
    if bool(getattr(fleet, 'advanced_cloak', False)):
        return False
    return position_in_scanner_range(fleet.x, fleet.y, sources, range_key='advanced')


def fleet_targetable_by_patrol(fleet, player, sources=None):
    if not fleet or not player:
        return False
    if fleet.player_id == player.id:
        return False
    sources = sources if sources is not None else get_scanner_sources_for_player(fleet.game, player)
    if fleet_is_cloaked(fleet):
        return fleet_revealed_by_advanced_scanners(fleet, sources)
    return fleet_visible_to_player(fleet, player, sources=sources)


def fleet_visible_to_player(fleet, player, sources=None):
    if not player:
        return False
    if fleet.player_id == player.id:
        return True
    from .diplomacy import (
        PERMISSION_SHARE_INTEL,
        player_grants_permission,
        player_reveals_cloaked_fleets,
    )
    cloaked = fleet_is_cloaked(fleet)
    if player_grants_permission(
        getattr(fleet, 'player', None),
        player,
        PERMISSION_SHARE_INTEL,
    ):
        if not cloaked or player_reveals_cloaked_fleets(getattr(fleet, 'player', None), player):
            return True
    sources = sources if sources is not None else get_scanner_sources_for_player(fleet.game, player)
    if cloaked:
        return fleet_revealed_by_advanced_scanners(fleet, sources)
    if getattr(fleet.game, 'no_scanners', False):
        return True
    return position_in_scanner_range(fleet.x, fleet.y, sources, range_key='basic')
