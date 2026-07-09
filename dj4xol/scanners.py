from __future__ import annotations

from functools import lru_cache
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
    """Return max-radius scanner circles, dropping fully contained circles."""
    return reduced_scanner_range_circles(sources, range_key)


def reduced_scanner_range_circles(sources, range_key='basic'):
    """Return scanner circles suitable for owner-agnostic range checks."""
    signature = _scanner_range_signature(sources, range_key)
    return [
        {
            'center_x': x,
            'center_y': y,
            'radius': radius,
        }
        for x, y, radius in _reduced_scanner_range_circle_tuples(signature)
    ]


def _scanner_range_signature(sources, range_key):
    circles = []
    for src in sources:
        circle = _scanner_circle_tuple_from_source(src, range_key)
        if circle is not None:
            circles.append(circle)
    return tuple(sorted(circles))


def _scanner_circle_tuple_from_source(src, range_key):
    try:
        x = int(src.get('x'))
        y = int(src.get('y'))
        radius = int(src.get(range_key) or 0)
    except (TypeError, ValueError):
        return None
    if radius <= 0:
        return None
    return x, y, radius


@lru_cache(maxsize=256)
def _reduced_scanner_range_circle_tuples(signature):
    strongest = {}
    for x, y, radius in signature:
        key = (x, y)
        current = strongest.get(key)
        if current is None or radius > current['radius']:
            strongest[key] = {
                'center_x': x,
                'center_y': y,
                'radius': radius,
            }
    circles = [
        strongest[key]
        for key in sorted(strongest)
    ]
    return tuple(
        (circle['center_x'], circle['center_y'], circle['radius'])
        for circle in _prune_contained_scanner_circles(circles)
    )


def _circle_contains(outer, inner):
    outer_radius = int(outer.get('radius') or 0)
    inner_radius = int(inner.get('radius') or 0)
    if outer_radius < inner_radius:
        return False
    dx = int(inner.get('center_x') or 0) - int(outer.get('center_x') or 0)
    dy = int(inner.get('center_y') or 0) - int(outer.get('center_y') or 0)
    radius_diff = outer_radius - inner_radius
    return (dx * dx) + (dy * dy) <= radius_diff * radius_diff


def _prune_contained_scanner_circles(circles):
    indexed = list(enumerate(circles))
    by_desc_radius = sorted(
        indexed,
        key=lambda item: (-int(item[1].get('radius') or 0), item[0]),
    )
    kept = []
    for index, circle in by_desc_radius:
        if any(_circle_contains(kept_circle, circle) for _kept_index, kept_circle in kept):
            continue
        kept.append((index, circle))
    return [circle for _index, circle in sorted(kept, key=lambda item: item[0])]


def _in_range(x, y, sx, sy, radius):
    if radius <= 0:
        return False
    dx = float(x) - float(sx)
    dy = float(y) - float(sy)
    return (dx * dx) + (dy * dy) <= float(radius) * float(radius)


def _scanner_circle_target_sort_key(circle, x, y):
    dx = float(x) - float(circle['center_x'])
    dy = float(y) - float(circle['center_y'])
    distance_sq = (dx * dx) + (dy * dy)
    radius = int(circle.get('radius') or 0)
    return (
        distance_sq,
        -radius,
    )


def _order_scanner_circles_for_target(circles, x, y):
    return sorted(
        circles,
        key=lambda circle: _scanner_circle_target_sort_key(circle, x, y),
    )


def position_in_scanner_range(x, y, sources, range_key='basic'):
    circles = reduced_scanner_range_circles(sources, range_key)
    for circle in _order_scanner_circles_for_target(circles, x, y):
        if _in_range(x, y, circle['center_x'], circle['center_y'], circle['radius']):
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
