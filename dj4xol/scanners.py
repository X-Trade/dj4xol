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


def get_scanner_sources_for_player(game, player):
    """Return scanner source dicts for a player (fleets + colonies)."""
    if not player:
        return []
    if getattr(game, 'no_scanners', False):
        return []
    from .research import get_player_colony_scanner_ranges

    sources = []
    for fleet in game.fleets.filter(player=player):
        basic, advanced = _coerce_ranges(
            getattr(fleet, 'basic_scanner_range', 0),
            getattr(fleet, 'advanced_scanner_range', 0),
        )
        if basic <= 0 and advanced <= 0:
            continue
        sources.append({
            'x': int(fleet.x),
            'y': int(fleet.y),
            'basic': basic,
            'advanced': advanced,
            'source_type': 'fleet',
        })

    colony_basic, colony_advanced = get_player_colony_scanner_ranges(player)
    colony_basic, colony_advanced = _coerce_ranges(colony_basic, colony_advanced)
    if colony_basic > 0 or colony_advanced > 0:
        for star in game.stars.filter(player=player):
            sources.append({
                'x': int(star.x),
                'y': int(star.y),
                'basic': colony_basic,
                'advanced': colony_advanced,
                'source_type': 'colony',
            })
    return sources


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


def fleet_visible_to_player(fleet, player, sources=None):
    if not player:
        return False
    if getattr(fleet.game, 'no_scanners', False):
        return True
    if fleet.player_id == player.id:
        return True
    sources = sources if sources is not None else get_scanner_sources_for_player(fleet.game, player)
    return position_in_scanner_range(fleet.x, fleet.y, sources, range_key='basic')
