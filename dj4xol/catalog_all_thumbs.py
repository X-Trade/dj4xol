"""Generate blurred thumbnail variants and refresh thumbnail catalogs.

Usage:
    pyenv exec python -m dj4xol.catalog_all_thumbs
"""

from __future__ import annotations

from .catalog_anomaly_thumbs import main as catalog_anomalies
from .catalog_ship_thumbs import main as catalog_ships
from .catalog_star_thumbs import main as catalog_stars
from .thumbnail_variants import ensure_all_blur_variants


def main():
    results = ensure_all_blur_variants(force=True)
    catalog_stars()
    catalog_ships()
    catalog_anomalies()
    for name in ("star", "ship", "anomaly", "salvage"):
        result = results.get(name, {})
        generated = int(result.get("generated", 0) or 0)
        refreshed = int(result.get("refreshed", 0) or 0)
        print(
            "Blur variants for %s: generated=%s refreshed=%s"
            % (name, generated, refreshed)
        )


if __name__ == "__main__":
    main()
