"""Rename nebula thumbnails with a color prefix based on dominant hue.

Usage:
    pyenv exec python -m dj4xol.rename_nebula_thumbs
"""

from __future__ import annotations

from pathlib import Path
from PIL import Image


PROJECT_ROOT = Path(__file__).resolve().parents[1]
NEBULA_ROOT = PROJECT_ROOT / "dj4xol" / "static" / "dj4xol" / "images" / "thumbs" / "anomaly" / "nebula"

PALETTE_TARGETS = {
    "orange": (244, 148, 74),
    "yellow": (240, 218, 106),
    "red": (236, 108, 126),
    "blue": (108, 156, 228),
    "white": (224, 232, 244),
}


def _average_color(path: Path):
    with Image.open(path) as img:
        img = img.convert("RGBA")
        img = img.resize((32, 32))
        pixels = img.getdata()
    total_r = total_g = total_b = count = 0
    for r, g, b, a in pixels:
        if a < 20:
            continue
        total_r += r
        total_g += g
        total_b += b
        count += 1
    if count == 0:
        return (0, 0, 0)
    return (total_r // count, total_g // count, total_b // count)


def _closest_palette(rgb):
    best = None
    best_dist = None
    for name, target in PALETTE_TARGETS.items():
        dr = rgb[0] - target[0]
        dg = rgb[1] - target[1]
        db = rgb[2] - target[2]
        dist = dr * dr + dg * dg + db * db
        if best_dist is None or dist < best_dist:
            best_dist = dist
            best = name
    return best or "blue"


def _prefixed_name(color, stem):
    if stem.startswith(color + "_"):
        return stem + ".png"
    return f"{color}_{stem}.png"


def rename_nebula_thumbnails():
    if not NEBULA_ROOT.exists():
        raise SystemExit(f"Nebula thumbnail folder not found: {NEBULA_ROOT}")

    renamed = 0
    for png in sorted(NEBULA_ROOT.glob("*.png")):
        stem = png.stem
        avg = _average_color(png)
        color = _closest_palette(avg)
        new_name = _prefixed_name(color, stem)
        if new_name == png.name:
            continue
        target = png.with_name(new_name)
        if target.exists():
            # Avoid clobbering; keep original name if collision.
            continue
        png.rename(target)
        renamed += 1

    print(f"Renamed {renamed} nebula thumbnails under {NEBULA_ROOT}.")


if __name__ == "__main__":
    rename_nebula_thumbnails()
