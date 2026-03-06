from pathlib import Path

from django.test import TestCase

from ..star_thumbnail_catalog import ALL_STAR_THUMBNAILS


class StarThumbnailCatalogTest(TestCase):
    def test_star_thumbnail_catalog_matches_filesystem(self):
        root = Path(__file__).resolve().parents[1] / "static"
        star_dir = root / "dj4xol" / "images" / "thumbs" / "star"
        files = sorted(p.relative_to(root).as_posix() for p in star_dir.rglob("*.png"))
        catalog = sorted(ALL_STAR_THUMBNAILS)

        self.assertTrue(files, msg="No star thumbnails found on disk.")
        self.assertEqual(files, catalog)
