"""Technology thumbnail helpers."""

import json
from functools import lru_cache
from pathlib import Path, PurePosixPath

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
THUMB_ROOT_PREFIX = "dj4xol/images/thumbs/"
PROJECT_ROOT = Path(__file__).resolve().parents[1]
STATIC_ROOT = PROJECT_ROOT / "dj4xol" / "static"
THUMBS_ROOT = STATIC_ROOT / "dj4xol" / "images" / "thumbs"


def _safe_params(tech):
    try:
        data = json.loads(getattr(tech, 'params_json', '') or '{}')
    except (TypeError, ValueError):
        return {}
    return data if isinstance(data, dict) else {}


def _normalise_thumb_relative_path(value):
    text = str(value or '').strip().replace('\\', '/')
    if not text:
        return ''
    if text.startswith(THUMB_ROOT_PREFIX):
        text = text[len(THUMB_ROOT_PREFIX):]
    text = text.lstrip('/')
    if not text:
        return ''
    try:
        rel = PurePosixPath(text)
    except Exception:
        return ''
    if '..' in rel.parts:
        return ''
    return rel.as_posix()


def _resolve_single_thumbnail_path(value):
    rel = _normalise_thumb_relative_path(value)
    if not rel:
        return ''
    path = f"{THUMB_ROOT_PREFIX}{rel}"
    absolute_path = STATIC_ROOT / path
    if absolute_path.exists() and absolute_path.is_file():
        return path
    return ''


@lru_cache(maxsize=None)
def _resolve_thumbnail_cycle_paths(value):
    rel = _normalise_thumb_relative_path(value)
    if not rel:
        return tuple()
    folder = THUMBS_ROOT / rel
    if not folder.exists() or not folder.is_dir():
        return tuple()
    paths = []
    for path in sorted(folder.glob('*.png')):
        if path.name.endswith('__blur.png'):
            continue
        paths.append(path.relative_to(STATIC_ROOT).as_posix())
    return tuple(paths)


def _infer_hull_class(tech, params):
    try:
        linked_hull = getattr(tech, 'hull_design', None)
    except Exception:
        linked_hull = None
    hull_class = str(
        getattr(linked_hull, 'thumbnail_class', '') or ''
    ).strip().lower()
    if hull_class:
        return hull_class

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

    configured_class = (
        str(getattr(tech, 'thumbnail_class', '') or '').strip()
        or str(params.get('thumbnail_class') or '').strip()
        or str(params.get('thumbnail_cycle') or '').strip()
    )
    if configured_class:
        cycle_paths = list(_resolve_thumbnail_cycle_paths(configured_class))
        if (
            not cycle_paths and tech_type == 'HULL'
            and '/' not in configured_class
        ):
            cycle_paths = list(
                _resolve_thumbnail_cycle_paths(
                    'ship/%s' % configured_class.strip().lower()
                )
            )
        if cycle_paths:
            return cycle_paths

    configured_single = (
        str(getattr(tech, 'thumbnail_path', '') or '').strip()
        or str(params.get('thumbnail_path') or '').strip()
    )
    if configured_single:
        resolved_single = _resolve_single_thumbnail_path(configured_single)
        if resolved_single:
            return [resolved_single]

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
