"""Star thumbnail selection helpers."""

from functools import lru_cache
from pathlib import Path

from .star_thumbnail_catalog import ALL_STAR_THUMBNAILS
from .thumbnail_variants import get_blur_variant_path


DEFAULT_STAR_THUMBNAIL = "dj4xol/images/thumbs/star/all/1__r01_c01.png"
PROJECT_ROOT = Path(__file__).resolve().parents[1]
STATIC_ROOT = PROJECT_ROOT / "dj4xol" / "static"


@lru_cache(maxsize=None)
def _existing_paths(paths_tuple):
    paths = [p for p in paths_tuple if (STATIC_ROOT / p).exists()]
    return tuple(paths)


def _filter_existing(paths):
    if not paths:
        return []
    existing = _existing_paths(tuple(paths))
    return list(existing) if existing else list(paths)


def is_valid_star_thumbnail(path):
    if not path:
        return False
    if path not in ALL_STAR_THUMBNAILS:
        return False
    return (STATIC_ROOT / path).exists()


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
    pool = _filter_existing(ALL_STAR_THUMBNAILS)
    if not pool:
        return DEFAULT_STAR_THUMBNAIL
    idx = _seed_to_index(seed, len(pool))
    return pool[idx]


def get_blurred_star_thumbnail(path):
    return get_blur_variant_path(path)
