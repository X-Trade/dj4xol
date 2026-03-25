"""Star thumbnail selection helpers."""

from functools import lru_cache
from pathlib import Path

from .star_thumbnail_catalog import ALL_STAR_THUMBNAILS
from .thumbnail_variants import get_blur_variant_path


DEFAULT_STAR_THUMBNAIL = "dj4xol/images/thumbs/star/all/1__r01_c01.png"
STAR_THUMB_CATEGORY_ALL = "all"
STAR_THUMB_CATEGORY_CITY = "city"
STAR_THUMB_CATEGORY_DYSON = "dyson"
# Star.colonists is stored in thousands; 10bn = 10,000,000k.
CITY_THUMB_POPULATION_THRESHOLD_K = 10_000_000
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
    absolute_path = STATIC_ROOT / path
    if not absolute_path.exists():
        return False
    if path in ALL_STAR_THUMBNAILS:
        return True
    # Allow newly-added star thumbnails even before catalog regeneration.
    return path.startswith("dj4xol/images/thumbs/star/")


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


def _category_paths(category):
    category_name = str(category or STAR_THUMB_CATEGORY_ALL).strip().lower()
    if category_name not in {
        STAR_THUMB_CATEGORY_ALL,
        STAR_THUMB_CATEGORY_CITY,
        STAR_THUMB_CATEGORY_DYSON,
    }:
        category_name = STAR_THUMB_CATEGORY_ALL

    category_marker = f"/star/{category_name}/"
    return [path for path in ALL_STAR_THUMBNAILS if category_marker in path]


def choose_star_thumbnail(seed, category=STAR_THUMB_CATEGORY_ALL):
    """Return a deterministic star thumbnail path for a given seed/category."""
    if not ALL_STAR_THUMBNAILS:
        return DEFAULT_STAR_THUMBNAIL
    pool = _filter_existing(_category_paths(category))
    if not pool and category != STAR_THUMB_CATEGORY_ALL:
        pool = _filter_existing(_category_paths(STAR_THUMB_CATEGORY_ALL))
    if not pool:
        pool = _filter_existing(ALL_STAR_THUMBNAILS)
    if not pool:
        return DEFAULT_STAR_THUMBNAIL
    idx = _seed_to_index(seed, len(pool))
    return pool[idx]


def choose_special_star_thumbnail(star):
    """Return special-case city/dyson thumbnail for a star, or None."""
    if not star:
        return None
    seed = getattr(star, "id", None) or getattr(star, "short_id", None) or getattr(star, "name", None)
    if bool(getattr(star, "has_dyson_sphere", False)):
        return choose_star_thumbnail(seed, category=STAR_THUMB_CATEGORY_DYSON)

    try:
        colonists = int(getattr(star, "colonists", 0) or 0)
    except (TypeError, ValueError):
        colonists = 0
    if colonists > CITY_THUMB_POPULATION_THRESHOLD_K:
        return choose_star_thumbnail(seed, category=STAR_THUMB_CATEGORY_CITY)
    return None


def get_blurred_star_thumbnail(path):
    return get_blur_variant_path(path)
