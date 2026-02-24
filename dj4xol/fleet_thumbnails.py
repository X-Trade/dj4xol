"""Fleet thumbnail selection helpers."""

from .ship_thumbnail_catalog import ALL_SHIP_THUMBNAILS


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


def choose_fleet_thumbnail(seed):
    """Return a deterministic thumbnail path for a given seed."""
    if not ALL_SHIP_THUMBNAILS:
        return DEFAULT_FLEET_THUMBNAIL
    idx = _seed_to_index(seed, len(ALL_SHIP_THUMBNAILS))
    return ALL_SHIP_THUMBNAILS[idx]
