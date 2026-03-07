from pathlib import Path

from django.test import TestCase

from ..star_thumbnail_catalog import ALL_STAR_THUMBNAILS
from ..thumbnail_variants import blur_variant_path, get_blur_variant_path


class StarThumbnailCatalogTest(TestCase):
    def test_star_thumbnail_catalog_matches_filesystem(self):
        root = Path(__file__).resolve().parents[1] / "static"
        star_dir = root / "dj4xol" / "images" / "thumbs" / "star"
        files = sorted(
            p.relative_to(root).as_posix()
            for p in star_dir.rglob("*.png")
            if not p.name.endswith("__blur.png")
        )
        catalog = sorted(ALL_STAR_THUMBNAILS)

        self.assertTrue(files, msg="No star thumbnails found on disk.")
        self.assertEqual(files, catalog)

    def test_blur_variant_path_uses_generated_suffix(self):
        source = ALL_STAR_THUMBNAILS[0]
        blurred = blur_variant_path(source)
        self.assertTrue(blurred.endswith("__blur.png"))
        self.assertNotEqual(source, blurred)

    def test_blur_variant_path_falls_back_only_when_missing(self):
        source = ALL_STAR_THUMBNAILS[0]
        blurred = get_blur_variant_path(source)
        self.assertTrue(blurred.endswith("__blur.png"))
