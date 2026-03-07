"""Fleet thumbnail selection helpers."""

from functools import lru_cache
from pathlib import Path

from .ship_thumbnail_catalog import ALL_SHIP_THUMBNAILS
from .ship_thumbnail_catalog import SHIP_THUMBNAILS_BY_CLASS
from .thumbnail_variants import get_blur_variant_path


DEFAULT_FLEET_THUMBNAIL = "dj4xol/images/thumbs/ship/scout/1__r01_c01.png"
PROJECT_ROOT = Path(__file__).resolve().parents[1]
STATIC_ROOT = PROJECT_ROOT / "dj4xol" / "static"


def _seed_to_index(seed, count):
    if count <= 0:
        return 0
    if seed is None:
        return 0
    text = str(seed)
    if not text:
        return 0
    total = 0
    for char in text:
        total = ((total * 131) + ord(char)) & 0xFFFFFFFF
    return total % count


@lru_cache(maxsize=None)
def _existing_paths(paths_tuple):
    paths = [p for p in paths_tuple if (STATIC_ROOT / p).exists()]
    return tuple(paths)


def _filter_existing(paths):
    if not paths:
        return []
    existing = _existing_paths(tuple(paths))
    return list(existing) if existing else list(paths)


def get_ship_class_from_path(path):
    if not path:
        return None
    parts = str(path).split("/")
    try:
        idx = parts.index("ship")
    except ValueError:
        return None
    if idx + 1 >= len(parts):
        return None
    return parts[idx + 1]


def is_valid_fleet_thumbnail(path):
    if not path:
        return False
    if path not in ALL_SHIP_THUMBNAILS:
        return False
    return (STATIC_ROOT / path).exists()


def choose_fleet_thumbnail(seed, ship_class=None):
    """Return a deterministic thumbnail path for a given seed/class."""
    pool = None
    if ship_class:
        pool = SHIP_THUMBNAILS_BY_CLASS.get(str(ship_class).lower())
    if not pool:
        pool = ALL_SHIP_THUMBNAILS
    pool = _filter_existing(pool)
    if not pool:
        return DEFAULT_FLEET_THUMBNAIL
    idx = _seed_to_index(seed, len(pool))
    return pool[idx]


def get_blurred_fleet_thumbnail(path):
    return get_blur_variant_path(path)
