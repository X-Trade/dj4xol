"""Retro map fleet sprite lookup helpers."""

import re
from functools import lru_cache
from pathlib import Path

from .fleet_thumbnails import PROJECT_ROOT


STATIC_ROOT = PROJECT_ROOT / "dj4xol" / "static"
SPRITE_ROOT = STATIC_ROOT / "dj4xol" / "images" / "mapfleet" / "retro" / "source"
RETRO_MAPFLEET_PALETTES = ("friendly", "allied", "enemy")
VARIANT_RE = re.compile(r"^(?P<ship_class>[a-z0-9]+?)(?:_(?P<variant>\d+))?\.png$", re.IGNORECASE)


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


def _variant_sort_key(variant):
    filename = variant["filename"]
    match = VARIANT_RE.match(filename)
    variant_num = match.group("variant") if match else None
    if not variant_num:
        return (0, 0, filename)
    return (1, int(variant_num), filename)


@lru_cache(maxsize=None)
def _sprite_catalog():
    catalog = {}
    for palette in RETRO_MAPFLEET_PALETTES:
        palette_dir = SPRITE_ROOT / palette
        palette_entries = {}
        if palette_dir.exists():
            for path in sorted(palette_dir.glob("*.png")):
                match = VARIANT_RE.match(path.name)
                if not match:
                    continue
                ship_class = str(match.group("ship_class") or "").strip().lower()
                if not ship_class:
                    continue
                palette_entries.setdefault(ship_class, []).append({
                    "filename": path.name,
                    "path": path.relative_to(STATIC_ROOT).as_posix(),
                })
        for ship_class in palette_entries:
            palette_entries[ship_class] = sorted(
                palette_entries[ship_class],
                key=_variant_sort_key,
            )
        catalog[palette] = palette_entries
    return catalog


def available_retro_mapfleet_variants(ship_class, palette="friendly"):
    """Return available sprite variants for a retro map fleet class/palette."""
    palette = str(palette or "friendly").strip().lower()
    ship_class = str(ship_class or "").strip().lower()
    if palette not in RETRO_MAPFLEET_PALETTES or not ship_class:
        return []
    return list(_sprite_catalog().get(palette, {}).get(ship_class, ()))


def choose_retro_mapfleet_sprite(seed, ship_class, palette="friendly"):
    """Return one deterministic retro map fleet sprite path for a class/palette."""
    candidate_classes = []
    requested = str(ship_class or "").strip().lower()
    for candidate in (requested, "fighter", "probe"):
        if candidate and candidate not in candidate_classes:
            candidate_classes.append(candidate)

    for candidate in candidate_classes:
        variants = available_retro_mapfleet_variants(candidate, palette=palette)
        if variants:
            return variants[_seed_to_index(seed, len(variants))]["path"]
    return ""


def clear_retro_mapfleet_sprite_cache():
    _sprite_catalog.cache_clear()
