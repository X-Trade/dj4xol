"""Technology thumbnail helpers."""

import json
from .ship_thumbnail_catalog import ALL_SHIP_THUMBNAILS, SHIP_THUMBNAILS_BY_CLASS


TECH_TYPE_PLACEHOLDERS = {
    'PROPULSION': 'dj4xol/images/thumbs/tech/propulsion.svg',
    'HULL': 'dj4xol/images/thumbs/tech/hull.svg',
    'ENERGY_WEAPON': 'dj4xol/images/thumbs/tech/energy_weapon.svg',
    'TORPEDO': 'dj4xol/images/thumbs/tech/torpedo.svg',
    'SHIELD': 'dj4xol/images/thumbs/tech/shield.svg',
    'ARMOUR': 'dj4xol/images/thumbs/tech/armour.svg',
    'SCANNER': 'dj4xol/images/thumbs/tech/scanner.svg',
    'INFRASTRUCTURE': 'dj4xol/images/thumbs/tech/infrastructure.svg',
    'BOMB': 'dj4xol/images/thumbs/tech/bomb.svg',
    'SPECIAL': 'dj4xol/images/thumbs/tech/special.svg',
    'OTHER': 'dj4xol/images/thumbs/tech/other.svg',
}

DEFAULT_TECH_PLACEHOLDER = TECH_TYPE_PLACEHOLDERS['OTHER']


def _safe_params(tech):
    try:
        data = json.loads(getattr(tech, 'params_json', '') or '{}')
    except (TypeError, ValueError):
        return {}
    return data if isinstance(data, dict) else {}


def _infer_hull_class(tech, params):
    hull_class = str(params.get('hull_thumbnail_class') or '').strip().lower()
    if hull_class:
        return hull_class

    name = str(getattr(tech, 'name', '') or '').lower()
    for candidate in (
        'scout', 'fighter', 'frigate', 'freighter', 'tanker', 'capital', 'city'
    ):
        if candidate in name:
            return candidate
    return ''


def _seed_to_index(seed, count):
    if count <= 0:
        return 0
    text = str(seed or '')
    total = 0
    for char in text:
        total = ((total * 131) + ord(char)) & 0xFFFFFFFF
    return total % count


def get_technology_thumbnail_paths(tech):
    """Return static paths for all thumbnails available to this technology."""
    tech_type = str(getattr(tech, 'tech_type', '') or 'OTHER').upper()
    params = _safe_params(tech)

    configured_paths = params.get('thumbnail_paths')
    if isinstance(configured_paths, list):
        paths = [str(path) for path in configured_paths if path]
        if paths:
            return paths

    if tech_type == 'HULL':
        hull_class = _infer_hull_class(tech, params)
        class_pool = SHIP_THUMBNAILS_BY_CLASS.get(hull_class, [])
        if class_pool:
            return list(class_pool)
        if ALL_SHIP_THUMBNAILS:
            return list(ALL_SHIP_THUMBNAILS)
        return [TECH_TYPE_PLACEHOLDERS['HULL']]

    return [TECH_TYPE_PLACEHOLDERS.get(tech_type, DEFAULT_TECH_PLACEHOLDER)]


def get_technology_thumbnail_initial_index(tech, paths=None):
    pool = paths or get_technology_thumbnail_paths(tech)
    return _seed_to_index(getattr(tech, 'id', None), len(pool))


def get_technology_thumbnail_path(tech):
    """Return static path for a technology thumbnail."""
    paths = get_technology_thumbnail_paths(tech)
    if not paths:
        return DEFAULT_TECH_PLACEHOLDER
    idx = get_technology_thumbnail_initial_index(tech, paths=paths)
    if 0 <= idx < len(paths):
        return paths[idx]
    return paths[0]
