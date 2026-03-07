"""Anomaly thumbnail selection helpers."""

import random
from functools import lru_cache
from pathlib import Path

from .anomaly_thumbnail_catalog import (
    ALL_ANOMALY_THUMBNAILS,
    ANOMALY_THUMBNAILS_BY_TYPE,
)
from .thumbnail_variants import get_blur_variant_path


ANOMALY_TYPE_TO_FOLDER = {
    "NEBULA": "nebula",
    "COMET": "comet",
    "RIFT": "rift",
    "BLACK_HOLE": "blackhole",
    "WORMHOLE": "wormhole",
    "ANOMALY": "nebula",
}

DEFAULT_ANOMALY_THUMBNAIL = (
    ALL_ANOMALY_THUMBNAILS[0] if ALL_ANOMALY_THUMBNAILS else ""
)

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


def choose_anomaly_thumbnail(seed, anomaly_type=None):
    """Return a deterministic anomaly thumbnail path for a given seed/type."""
    if not ALL_ANOMALY_THUMBNAILS:
        return DEFAULT_ANOMALY_THUMBNAIL
    paths = _paths_for_type(anomaly_type)
    idx = _seed_to_index(seed, len(paths))
    return paths[idx]


@lru_cache(maxsize=None)
def _existing_paths(paths_tuple):
    paths = [p for p in paths_tuple if (STATIC_ROOT / p).exists()]
    return tuple(paths)


def _filter_existing(paths):
    if not paths:
        return []
    existing = _existing_paths(tuple(paths))
    return list(existing) if existing else list(paths)


def _paths_for_type(anomaly_type=None):
    key = str(anomaly_type or "").strip().upper()
    folder = ANOMALY_TYPE_TO_FOLDER.get(key)
    paths = ANOMALY_THUMBNAILS_BY_TYPE.get(folder) if folder else None
    if not paths:
        paths = ALL_ANOMALY_THUMBNAILS
    return _filter_existing(paths)


def choose_random_anomaly_thumbnail(anomaly_type=None):
    """Return a random anomaly thumbnail path for a given type."""
    paths = _paths_for_type(anomaly_type)
    if not paths:
        return DEFAULT_ANOMALY_THUMBNAIL
    return random.choice(paths)


def is_valid_anomaly_thumbnail(path):
    if not path:
        return False
    if path not in ALL_ANOMALY_THUMBNAILS:
        return False
    return (STATIC_ROOT / path).exists()


def nebula_palette_from_thumbnail(path):
    if not path:
        return None
    name = Path(path).name.lower()
    for palette in ("blue", "orange", "yellow", "red", "white"):
        if name.startswith(palette + "_"):
            return palette
    return None


def get_blurred_anomaly_thumbnail(path):
    return get_blur_variant_path(path)
