from functools import lru_cache
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
STATIC_ROOT = PROJECT_ROOT / "dj4xol" / "static"
SALVAGE_ROOT = STATIC_ROOT / "dj4xol" / "images" / "thumbs" / "salvage"


@lru_cache(maxsize=None)
def _list_pngs(relative_dir):
    target = SALVAGE_ROOT / relative_dir
    if not target.exists():
        return []
    items = sorted(
        str(path.relative_to(STATIC_ROOT))
        for path in target.glob("*.png")
        if path.is_file()
    )
    return items


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


def choose_salvage_thumbnail(seed, category):
    pool = _list_pngs(category)
    if not pool:
        return None
    idx = _seed_to_index(seed, len(pool))
    return pool[idx]


def get_salvage_thumbnail(salvage):
    if not salvage:
        return None
    salvage_type = getattr(salvage, 'salvage_type', None)
    if salvage_type == 'ASTEROID_FIELD':
        category = "asteroids"
    elif salvage_type == 'ANCIENT_DEBRIS':
        category = "ancientdebris"
    else:
        category = "debris"
    return choose_salvage_thumbnail(
        salvage.id or salvage.short_id or salvage.name,
        category,
    )
