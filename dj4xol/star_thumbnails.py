"""Star thumbnail selection helpers."""

from .star_thumbnail_catalog import ALL_STAR_THUMBNAILS


DEFAULT_STAR_THUMBNAIL = "dj4xol/images/thumbs/star/all/1__r01_c01.png"


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


def choose_star_thumbnail(seed):
    """Return a deterministic star thumbnail path for a given seed."""
    if not ALL_STAR_THUMBNAILS:
        return DEFAULT_STAR_THUMBNAIL
    idx = _seed_to_index(seed, len(ALL_STAR_THUMBNAILS))
    return ALL_STAR_THUMBNAILS[idx]
