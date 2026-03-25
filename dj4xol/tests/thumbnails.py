import tempfile
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from django.test import TestCase

from ..retro_mapfleet_sprites import (
    available_retro_mapfleet_variants,
    choose_retro_mapfleet_sprite,
    clear_retro_mapfleet_sprite_cache,
)
from ..star_thumbnail_catalog import ALL_STAR_THUMBNAILS
from ..technology_thumbnails import (
    TECH_TYPE_PLACEHOLDERS,
    get_technology_thumbnail_path,
    get_technology_thumbnail_paths,
)
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


class TechnologyThumbnailHelperTest(TestCase):
    def test_dyson_infrastructure_uses_dyson_thumbnail_cycler(self):
        tech = SimpleNamespace(
            id=195,
            tech_type='INFRASTRUCTURE',
            name='Dyson Sphere',
            thumbnail_class='star/dyson',
            thumbnail_path='',
            params_json='{}',
        )
        paths = get_technology_thumbnail_paths(tech)
        self.assertTrue(paths)
        self.assertTrue(all('/star/dyson/' in path for path in paths))
        self.assertIn(get_technology_thumbnail_path(tech), paths)

    def test_configured_single_thumbnail_path_is_used(self):
        tech = SimpleNamespace(
            id=196,
            tech_type='INFRASTRUCTURE',
            name='Custom Infrastructure Card',
            thumbnail_class='',
            thumbnail_path='star/dyson/ds1_1.png',
            params_json='{}',
        )
        paths = get_technology_thumbnail_paths(tech)
        self.assertEqual(paths, ['dj4xol/images/thumbs/star/dyson/ds1_1.png'])

    def test_thumbnail_class_overrides_thumbnail_path(self):
        tech = SimpleNamespace(
            id=197,
            tech_type='INFRASTRUCTURE',
            name='Conflicting Tech',
            thumbnail_class='star/dyson',
            thumbnail_path='star/all/1__r01_c01.png',
            params_json='{}',
        )
        paths = get_technology_thumbnail_paths(tech)
        self.assertTrue(paths)
        self.assertTrue(all('/star/dyson/' in path for path in paths))

    def test_hull_thumbnail_class_supports_bare_class_alias(self):
        tech = SimpleNamespace(
            id=199,
            tech_type='HULL',
            name='Alias Hull Tech',
            thumbnail_class='fighter',
            thumbnail_path='',
            params_json='{}',
        )
        paths = get_technology_thumbnail_paths(tech)
        self.assertTrue(paths)
        self.assertTrue(all('/ship/fighter/' in path for path in paths))

    def test_legacy_params_thumbnail_cycle_still_supported(self):
        tech = SimpleNamespace(
            id=198,
            tech_type='INFRASTRUCTURE',
            name='Legacy Config Tech',
            thumbnail_class='',
            thumbnail_path='',
            params_json='{"thumbnail_cycle": "star/dyson"}',
        )
        paths = get_technology_thumbnail_paths(tech)
        self.assertTrue(paths)
        self.assertTrue(all('/star/dyson/' in path for path in paths))

    def test_regular_infrastructure_uses_placeholder_thumbnail(self):
        tech = SimpleNamespace(
            id=100,
            tech_type='INFRASTRUCTURE',
            name='Orbital Foundry',
            thumbnail_class='',
            thumbnail_path='',
            params_json='{}',
        )
        paths = get_technology_thumbnail_paths(tech)
        self.assertEqual(paths, [TECH_TYPE_PLACEHOLDERS['INFRASTRUCTURE']])


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
