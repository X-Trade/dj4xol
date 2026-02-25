"""Fleet thumbnail selection helpers."""

from .ship_thumbnail_catalog import ALL_SHIP_THUMBNAILS
from .ship_thumbnail_catalog import SHIP_THUMBNAILS_BY_CLASS


DEFAULT_FLEET_THUMBNAIL = "dj4xol/images/thumbs/ship/scout/1__r01_c01.png"


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


def choose_fleet_thumbnail(seed, ship_class=None):
    """Return a deterministic thumbnail path for a given seed/class."""
    pool = None
    if ship_class:
        pool = SHIP_THUMBNAILS_BY_CLASS.get(str(ship_class).lower())
    if not pool:
        pool = ALL_SHIP_THUMBNAILS
    if not pool:
        return DEFAULT_FLEET_THUMBNAIL
    idx = _seed_to_index(seed, len(pool))
    return pool[idx]
