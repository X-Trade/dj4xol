import tempfile
from pathlib import Path
from unittest.mock import patch

from django.test import TestCase

from ..retro_mapfleet_sprites import (
    available_retro_mapfleet_variants,
    choose_retro_mapfleet_sprite,
    clear_retro_mapfleet_sprite_cache,
)
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


class RetroMapFleetSpriteTest(TestCase):
    def tearDown(self):
        clear_retro_mapfleet_sprite_cache()

    def test_available_variants_include_base_and_numbered_names(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            friendly = root / "friendly"
            friendly.mkdir(parents=True)
            for name in ("fighter.png", "fighter_1.png", "fighter_2.png", "frigate_1.png"):
                (friendly / name).write_bytes(b"png")
            for palette in ("allied", "enemy"):
                (root / palette).mkdir(parents=True)

            with patch("dj4xol.retro_mapfleet_sprites.SPRITE_ROOT", root), \
                    patch("dj4xol.retro_mapfleet_sprites.STATIC_ROOT", root):
                clear_retro_mapfleet_sprite_cache()
                variants = available_retro_mapfleet_variants("fighter", palette="friendly")

            self.assertEqual(
                [entry["filename"] for entry in variants],
                ["fighter.png", "fighter_1.png", "fighter_2.png"],
            )

    def test_choose_sprite_can_select_numbered_variant(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            friendly = root / "friendly"
            friendly.mkdir(parents=True)
            for name in ("fighter.png", "fighter_1.png", "fighter_2.png"):
                (friendly / name).write_bytes(b"png")
            for palette in ("allied", "enemy"):
                (root / palette).mkdir(parents=True)

            with patch("dj4xol.retro_mapfleet_sprites.SPRITE_ROOT", root), \
                    patch("dj4xol.retro_mapfleet_sprites.STATIC_ROOT", root):
                clear_retro_mapfleet_sprite_cache()
                selected = choose_retro_mapfleet_sprite("retro-seed", "fighter", palette="friendly")

            self.assertIn(
                selected,
                (
                    "friendly/fighter.png",
                    "friendly/fighter_1.png",
                    "friendly/fighter_2.png",
                ),
            )

    def test_choose_sprite_falls_back_to_fighter_then_probe(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            friendly = root / "friendly"
            friendly.mkdir(parents=True)
            (friendly / "fighter.png").write_bytes(b"png")
            (friendly / "probe.png").write_bytes(b"png")
            for palette in ("allied", "enemy"):
                (root / palette).mkdir(parents=True)

            with patch("dj4xol.retro_mapfleet_sprites.SPRITE_ROOT", root), \
                    patch("dj4xol.retro_mapfleet_sprites.STATIC_ROOT", root):
                clear_retro_mapfleet_sprite_cache()
                selected = choose_retro_mapfleet_sprite("retro-seed", "destroyer", palette="friendly")

            self.assertEqual(selected, "friendly/fighter.png")
