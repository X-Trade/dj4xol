import json
from unittest.mock import patch

from django.contrib.auth.models import User
from django.test import TestCase

from .. import scanners
from ..factory import GameFactory
from ..fleet_thumbnails import choose_fleet_thumbnail
from ..models import (
    Account,
    Report,
    Anomaly,
    Fleet,
    Salvage,
    PlayerDiplomaticStance,
    PlayerStarMarker,
)
from ..starmap import StarMap
from ..views import _build_scanner_circles
from ._util import default_game, get_default_race


class TestStarMap(TestCase):
    def test_render_map(self):
        game = default_game(fleets=1)
        player = game.players.first()
        starmap = StarMap(game, player)
        html = starmap.render_map()
        self.assertIn('class="mapstar', html)
        self.assertIn('class="mapfleet', html)

    def test_stars_are_dimmed_without_report_and_bright_with_report(self):
        game = default_game(stars=8, fleets=0)
        player = game.players.first()
        unknown_star = game.stars.filter(player__isnull=True).first()
        self.assertIsNotNone(unknown_star)

        starmap = StarMap(game, player)
        html = starmap.render_map()
        self.assertIn(
            f'data-object-id="{unknown_star.short_id}"',
            html,
        )
        self.assertIn('mapstar-unexplored', html)

        Report.objects.create(
            game=game,
            player=player,
            year=game.year,
            target_type='star',
            target_id=unknown_star.id,
            cached_report='{}',
        )
        starmap = StarMap(game, player)
        html = starmap.render_map()
        self.assertIn('mapstar-explored', html)

    def test_map_objects_include_selection_data_attributes(self):
        game = default_game(stars=5, fleets=1)
        player = game.players.first()
        starmap = StarMap(game, player, dest_mode=True)
        html = starmap.render_map()
        self.assertIn('data-map-object="1"', html)
        self.assertIn('data-object-type="star"', html)
        self.assertIn('data-object-type="fleet"', html)

    def test_rift_map_object_includes_anomaly_type_data_attribute(self):
        game = default_game(stars=5, fleets=0)
        player = game.players.first()
        rift = Anomaly.objects.create(
            game=game,
            x=20,
            y=20,
            name='Tall Rift',
            anomaly_type=Anomaly.TYPE_RIFT,
        )

        starmap = StarMap(game, player, dest_mode=True)
        html = starmap.render_anomaly(rift)

        self.assertIn('data-object-type="anomaly"', html)
        self.assertIn('data-anomaly-type="RIFT"', html)

    def test_star_marker_renders_circle_class_on_map(self):
        game = default_game(stars=5, fleets=0)
        player = game.players.first()
        star = player.homeworld
        PlayerStarMarker.objects.create(
            player=player,
            star=star,
            marker_type=PlayerStarMarker.TYPE_CIRCLE,
            marker_color=PlayerStarMarker.COLOR_BLUE,
        )

        starmap = StarMap(game, player)
        html = starmap.render_star(star)

        self.assertIn('mapstar-marker-circle', html)
        self.assertIn('mapstar-marker-color-blue', html)

    def test_legacy_white_marker_renders_with_blue_style(self):
        game = default_game(stars=5, fleets=0)
        player = game.players.first()
        star = player.homeworld
        PlayerStarMarker.objects.create(
            player=player,
            star=star,
            marker_type=PlayerStarMarker.TYPE_CIRCLE,
            marker_color=PlayerStarMarker.COLOR_WHITE,
        )

        starmap = StarMap(game, player)
        html = starmap.render_star(star)

        self.assertIn('mapstar-marker-circle', html)
        self.assertIn('mapstar-marker-color-blue', html)
        self.assertNotIn('mapstar-marker-color-white', html)

    def test_primary_star_marker_does_not_render_on_satellite_star(self):
        game = default_game(stars=2, fleets=0)
        player = game.players.first()
        primary = player.homeworld
        satellite = game.stars.exclude(pk=primary.pk).first()
        satellite.x = primary.x
        satellite.y = primary.y
        satellite.save(update_fields=['x', 'y'])
        PlayerStarMarker.objects.create(
            player=player,
            star=primary,
            marker_type=PlayerStarMarker.TYPE_CIRCLE,
        )

        starmap = StarMap(game, player)
        satellite_html = starmap.render_star(
            satellite,
            satellite=True,
            selection_star=satellite,
            primary_star=primary,
        )

        self.assertNotIn('mapstar-marker-circle', satellite_html)

    def test_multi_star_stack_renders_satellite_with_own_selection_and_primary_metadata(self):
        game = default_game(stars=2, fleets=0)
        player = game.players.first()
        home = player.homeworld
        other_star = game.stars.exclude(pk=home.pk).first()
        other_star.x = home.x
        other_star.y = home.y
        other_star.save(update_fields=['x', 'y'])

        starmap = StarMap(game, player)
        html = starmap.render_map()

        self.assertIn(f'title="{home.name}"', html)
        self.assertIn(f'sel={home.short_id}', html)
        self.assertIn(f'data-object-id="{home.short_id}"', html)
        self.assertIn(f'data-object-id="{other_star.short_id}"', html)
        self.assertIn(f'data-primary-object-id="{home.short_id}"', html)

    def test_multi_star_stack_promotes_single_colonized_secondary_to_main_dot(self):
        game = default_game(stars=2, fleets=0)
        player = game.players.first()
        primary = player.homeworld
        primary.player = None
        primary.colonists = 0
        primary.save(update_fields=['player', 'colonists'])

        secondary = game.stars.exclude(pk=primary.pk).first()
        secondary.x = primary.x
        secondary.y = primary.y
        secondary.player = player
        secondary.colonists = 1000
        secondary.save(update_fields=['x', 'y', 'player', 'colonists'])

        starmap = StarMap(game, player)
        html = starmap.render_map()

        self.assertIn(f'?x={secondary.x}&y={secondary.y}&sel={secondary.short_id}', html)
        self.assertIn(f'data-object-id="{secondary.short_id}"', html)
        self.assertEqual(html.count('mapstar-owned'), 1)
        self.assertEqual(html.count('mapstar-satellite-owned'), 0)

    def test_marker_follows_promoted_primary_star_at_same_coordinate(self):
        game = default_game(stars=2, fleets=0)
        player = game.players.first()
        primary = player.homeworld
        secondary = game.stars.exclude(pk=primary.pk).first()
        secondary.x = primary.x
        secondary.y = primary.y
        secondary.save(update_fields=['x', 'y'])
        PlayerStarMarker.objects.create(
            player=player,
            star=primary,
            marker_type=PlayerStarMarker.TYPE_CIRCLE,
            marker_color=PlayerStarMarker.COLOR_BLUE,
        )

        primary.player = None
        primary.colonists = 0
        primary.save(update_fields=['player', 'colonists'])
        secondary.player = player
        secondary.colonists = 1000
        secondary.save(update_fields=['player', 'colonists'])

        starmap = StarMap(game, player)
        html = starmap.render_map()

        self.assertIn(f'?x={secondary.x}&y={secondary.y}&sel={secondary.short_id}', html)
        self.assertIn('mapstar-marker-circle', html)

    def test_fleet_at_star_selects_primary_star_instead_of_fleet(self):
        game = default_game(stars=5, fleets=0)
        player = game.players.first()
        home = player.homeworld
        fleet = Fleet.objects.create(
            game=game,
            player=player,
            name='Orbital Fleet',
            x=home.x,
            y=home.y,
        )

        starmap = StarMap(game, player)
        html = starmap.render_fleet(fleet)

        self.assertIn(f'sel={home.short_id}', html)
        self.assertIn('data-object-type="star"', html)
        self.assertIn(f'data-object-id="{home.short_id}"', html)

    def test_fleet_map_includes_thumbnail_class_hook_and_rotation_variable(self):
        game = default_game(stars=5, fleets=1)
        player = game.players.first()
        fleet = player.fleets.first()
        fleet.thumbnail_path = choose_fleet_thumbnail('retro-hook', 'fighter')
        fleet.heading = 45
        fleet.save(update_fields=['thumbnail_path', 'heading'])

        starmap = StarMap(game, player)
        html = starmap.render_fleet(fleet)

        self.assertIn('mapfleet-thumb', html)
        self.assertIn('mapfleet-thumb-fighter', html)
        self.assertIn('mapfleet-thumb-has-sprite', html)
        self.assertIn('data-fleet-class="fighter"', html)
        self.assertIn('var(--mapfleet-rotation-offset, 0deg)', html)
        self.assertIn(
            "--retro-mapfleet-sprite: url('/static/dj4xol/images/mapfleet/retro/source/friendly/fighter",
            html,
        )

    def test_wormhole_anomaly_uses_wormhole_css_class(self):
        game = default_game(stars=5, fleets=0)
        player = game.players.first()
        Anomaly.objects.create(
            game=game,
            x=20,
            y=20,
            name='Pair A',
            anomaly_type=Anomaly.TYPE_WORMHOLE,
        )
        starmap = StarMap(game, player)
        html = starmap.render_map()
        self.assertIn('mapanomaly-wormhole', html)

    def test_salvage_requires_report_to_render_on_player_map(self):
        game = default_game(stars=5, fleets=0)
        player = game.players.first()
        salvage = Salvage.objects.create(
            game=game,
            x=24,
            y=24,
            ironium_inventory=40,
            boranium_inventory=10,
            germanium_inventory=5,
        )

        starmap = StarMap(game, player)
        html = starmap.render_map()
        self.assertNotIn(f'data-object-id="{salvage.short_id}"', html)

        Report.objects.create(
            game=game,
            player=player,
            year=game.year,
            target_type='salvage',
            target_id=salvage.id,
            cached_report=json.dumps({
                'name': salvage.name,
                'x': salvage.x,
                'y': salvage.y,
                'salvage_type': salvage.salvage_type,
                'total_minerals': salvage.total_minerals,
                'report_tier': 'basic',
            }),
        )

        starmap = StarMap(game, player)
        html = starmap.render_map()
        self.assertIn(f'data-object-id="{salvage.short_id}"', html)

    def test_basic_scanner_fleet_map_title_is_obfuscated(self):
        game = default_game(stars=5, fleets=0)
        player1 = game.players.first()
        user2 = User.objects.create_user('fleet_map_enemy', 'fme@test.com', 'pass')
        account2 = Account.objects.create(django_user=user2)
        factory = GameFactory(game=game)
        player2 = factory.join_player(account2, get_default_race())

        scanner = Fleet.objects.create(
            game=game,
            player=player1,
            name='Our Scanner',
            x=20,
            y=20,
            basic_scanner_range=6,
            advanced_scanner_range=0,
        )
        enemy_fleet = Fleet.objects.create(
            game=game,
            player=player2,
            name='Leaky Fleet Name',
            x=scanner.x + 3,
            y=scanner.y,
        )

        starmap = StarMap(game, player1)
        html = starmap.render_map()
        self.assertIn('title="Unknown Fleet"', html)
        self.assertNotIn('title="Leaky Fleet Name"', html)
        self.assertIn(f'data-object-id="{enemy_fleet.short_id}"', html)

    def test_scanner_overlay_keeps_only_largest_circle_per_position(self):
        game = default_game(stars=8, fleets=0)
        player1 = game.players.first()
        game.joinable = True
        game.save(update_fields=['joinable'])
        user2 = User.objects.create_user(
            'scanner_overlay_friend',
            'sof@test.com',
            'pass',
        )
        account2 = Account.objects.create(django_user=user2)
        player2 = GameFactory(game=game).join_player(account2, get_default_race())
        home = player1.homeworld

        Fleet.objects.create(
            game=game,
            player=player1,
            name='Small Orbital Scanner',
            x=home.x,
            y=home.y,
            basic_scanner_range=6,
            advanced_scanner_range=2,
        )
        Fleet.objects.create(
            game=game,
            player=player1,
            name='Large Orbital Scanner',
            x=home.x,
            y=home.y,
            basic_scanner_range=12,
            advanced_scanner_range=4,
        )
        Fleet.objects.create(
            game=game,
            player=player2,
            name='Shared Orbital Scanner',
            x=home.x,
            y=home.y,
            basic_scanner_range=10,
            advanced_scanner_range=7,
        )
        Fleet.objects.create(
            game=game,
            player=player1,
            name='Remote Scanner',
            x=home.x + 15,
            y=home.y,
            basic_scanner_range=5,
            advanced_scanner_range=3,
        )
        PlayerDiplomaticStance.objects.create(
            player=player2,
            target_player=player1,
            stance='ALLIED',
        )

        basic, advanced = _build_scanner_circles(game, player1)
        home_basic = [
            circle for circle in basic
            if (circle['center_x'], circle['center_y']) == (home.x, home.y)
        ]
        home_advanced = [
            circle for circle in advanced
            if (circle['center_x'], circle['center_y']) == (home.x, home.y)
        ]

        self.assertEqual(home_basic, [{
            'center_x': home.x,
            'center_y': home.y,
            'radius': 12,
        }])
        self.assertEqual(home_advanced, [{
            'center_x': home.x,
            'center_y': home.y,
            'radius': 7,
        }])

    def test_scanner_overlay_prunes_only_fully_contained_circles(self):
        game = default_game(stars=8, fleets=0)
        player = game.players.first()
        Fleet.objects.create(
            game=game,
            player=player,
            name='Large Scanner',
            x=50,
            y=50,
            basic_scanner_range=20,
        )
        Fleet.objects.create(
            game=game,
            player=player,
            name='Engulfed Scanner',
            x=55,
            y=50,
            basic_scanner_range=5,
        )
        Fleet.objects.create(
            game=game,
            player=player,
            name='Partial Scanner',
            x=65,
            y=50,
            basic_scanner_range=10,
        )

        basic, _advanced = _build_scanner_circles(game, player)
        circles = {
            (circle['center_x'], circle['center_y'], circle['radius'])
            for circle in basic
        }

        self.assertIn((50, 50, 20), circles)
        self.assertNotIn((55, 50, 5), circles)
        self.assertIn((65, 50, 10), circles)

    def test_scanner_range_check_reduces_and_orders_sources_before_matching(self):
        sources = [
            {'x': 100, 'y': 100, 'basic': 3, 'owner_id': 1},
            {'x': 10, 'y': 0, 'basic': 1, 'owner_id': 2},
            {'x': 10, 'y': 0, 'basic': 8, 'owner_id': 3},
        ]
        calls = []
        real_in_range = scanners._in_range

        def wrapped_in_range(x, y, sx, sy, radius):
            calls.append((sx, sy, radius))
            return real_in_range(x, y, sx, sy, radius)

        with patch('dj4xol.scanners._in_range', side_effect=wrapped_in_range):
            self.assertTrue(
                scanners.position_in_scanner_range(12, 0, sources, range_key='basic')
            )

        self.assertEqual(calls, [(10, 0, 8)])

    def test_scanner_range_check_prunes_contained_sources(self):
        sources = [
            {'x': 50, 'y': 50, 'basic': 20},
            {'x': 55, 'y': 50, 'basic': 5},
        ]
        calls = []
        real_in_range = scanners._in_range

        def wrapped_in_range(x, y, sx, sy, radius):
            calls.append((sx, sy, radius))
            return real_in_range(x, y, sx, sy, radius)

        with patch('dj4xol.scanners._in_range', side_effect=wrapped_in_range):
            self.assertTrue(
                scanners.position_in_scanner_range(55, 50, sources, range_key='basic')
            )

        self.assertEqual(calls, [(50, 50, 20)])

    def test_scanner_range_check_keeps_partially_overlapping_sources(self):
        sources = [
            {'x': 50, 'y': 50, 'basic': 20},
            {'x': 65, 'y': 50, 'basic': 10},
        ]

        self.assertTrue(
            scanners.position_in_scanner_range(73, 50, sources, range_key='basic')
        )

    def test_starmap_renders_one_fleet_icon_per_player_at_star(self):
        game = default_game(stars=5, fleets=0)
        player = game.players.first()
        player.fleets.all().delete()
        home = player.homeworld
        for idx in range(3):
            Fleet.objects.create(
                game=game,
                player=player,
                name='Orbital Fleet %s' % idx,
                x=home.x,
                y=home.y,
            )

        starmap = StarMap(game, player)
        html = starmap.render_map()

        self.assertEqual(html.count('class="mapfleet'), 1)

    def test_starmap_keeps_selected_fleet_when_aggregating_star_fleets(self):
        game = default_game(stars=5, fleets=0)
        player = game.players.first()
        player.fleets.all().delete()
        home = player.homeworld
        Fleet.objects.create(
            game=game,
            player=player,
            name='Rendered Orbital Fleet',
            x=home.x,
            y=home.y,
        )
        selected = Fleet.objects.create(
            game=game,
            player=player,
            name='Selected Orbital Fleet',
            x=home.x,
            y=home.y,
        )

        starmap = StarMap(game, player, selected_short_id=selected.short_id)
        html = starmap.render_map()

        self.assertEqual(html.count('class="mapfleet'), 2)
        self.assertIn('title="Selected Orbital Fleet"', html)

    def test_starmap_renders_at_most_four_unselected_fleets_away_from_stars(self):
        game = default_game(stars=5, fleets=0)
        player = game.players.first()
        player.fleets.all().delete()
        for idx in range(6):
            Fleet.objects.create(
                game=game,
                player=player,
                name='Deep Space Fleet %s' % idx,
                x=12,
                y=13,
            )

        starmap = StarMap(game, player)
        html = starmap.render_map()

        self.assertEqual(html.count('class="mapfleet'), 4)
        self.assertNotIn('Deep Space Fleet 5', html)

    def test_starmap_keeps_selected_fleet_when_aggregating_deep_space_fleets(self):
        game = default_game(stars=5, fleets=0)
        player = game.players.first()
        player.fleets.all().delete()
        selected = None
        for idx in range(6):
            fleet = Fleet.objects.create(
                game=game,
                player=player,
                name='Deep Space Fleet %s' % idx,
                x=12,
                y=13,
            )
            if idx == 5:
                selected = fleet

        starmap = StarMap(game, player, selected_short_id=selected.short_id)
        html = starmap.render_map()

        self.assertEqual(html.count('class="mapfleet'), 5)
        self.assertIn(f'data-object-id="{selected.short_id}"', html)

    def test_basic_ancient_debris_map_title_is_hidden(self):
        game = default_game(stars=5, fleets=0)
        player = game.players.first()
        salvage = Salvage.objects.create(
            game=game,
            x=24,
            y=24,
            salvage_type=Salvage.TYPE_ANCIENT_DEBRIS,
            ironium_inventory=40,
            boranium_inventory=10,
            germanium_inventory=5,
        )
        Report.objects.create(
            game=game,
            player=player,
            year=game.year,
            target_type='salvage',
            target_id=salvage.id,
            cached_report=json.dumps({
                'name': salvage.name,
                'x': salvage.x,
                'y': salvage.y,
                'salvage_type': salvage.salvage_type,
                'total_minerals': salvage.total_minerals,
                'report_tier': 'basic',
            }),
        )

        starmap = StarMap(game, player)
        html = starmap.render_map()
        self.assertIn('title="???"', html)
        self.assertNotIn(salvage.name, html)

    def test_rift_anomaly_has_deterministic_variable_height_style(self):
        game = default_game(stars=5, fleets=0)
        player = game.players.first()
        rift = Anomaly.objects.create(
            game=game,
            x=22,
            y=22,
            name='Rift Height Check',
            anomaly_type=Anomaly.TYPE_RIFT,
        )
        starmap = StarMap(game, player)
        html = starmap.render_map()
        self.assertIn(f'data-object-id="{rift.short_id}"', html)
        self.assertIn('--rift-height:', html)

    def test_basic_star_reports_hide_enemy_ownership_on_map(self):
        factory = GameFactory()
        factory.set_map_size(100, 100)
        user1 = User.objects.create_user('scanner_map_1', 's1@test.com', 'pass')
        account1 = Account.objects.create(django_user=user1)
        factory.set_owner(account1)
        factory.create_stars(12)
        game = factory.save()
        game.joinable = True
        game.save(update_fields=['joinable'])

        player1 = factory.join_player(account1, get_default_race())
        user2 = User.objects.create_user('scanner_map_2', 's2@test.com', 'pass')
        account2 = Account.objects.create(django_user=user2)
        player2 = factory.join_player(account2, get_default_race())
        enemy_star = player2.homeworld

        occupied = set(
            game.stars.exclude(id=enemy_star.id).values_list('x', 'y')
        )
        target = None
        for x in range(1, int(game.map_size_x)):
            for y in range(1, int(game.map_size_y)):
                if (x, y) not in occupied:
                    target = (x, y)
                    break
            if target:
                break
        self.assertIsNotNone(target)
        enemy_star.x, enemy_star.y = target
        enemy_star.save(update_fields=['x', 'y'])

        Report.objects.create(
            game=game,
            player=player1,
            year=game.year,
            target_type='star',
            target_id=enemy_star.id,
            cached_report=json.dumps({
                'name': enemy_star.name,
                'x': enemy_star.x,
                'y': enemy_star.y,
                'report_tier': 'basic',
            }),
        )
        starmap = StarMap(game, player1)
        html = starmap.render_map()
        needle = f'data-object-id="{enemy_star.short_id}"'
        idx = html.find(needle)
        self.assertNotEqual(idx, -1)
        start = html.rfind('<', 0, idx)
        end = html.find('>', idx)
        tag = html[start:end]
        self.assertIn('mapstar', tag)
        self.assertNotIn('mapstar-enemy', tag)

        Report.objects.filter(
            game=game,
            player=player1,
            target_type='star',
            target_id=enemy_star.id,
        ).update(cached_report=json.dumps({
            'name': enemy_star.name,
            'x': enemy_star.x,
            'y': enemy_star.y,
            'report_tier': 'advanced',
        }))
        starmap = StarMap(game, player1)
        html = starmap.render_map()
        idx = html.find(needle)
        self.assertNotEqual(idx, -1)
        start = html.rfind('<', 0, idx)
        end = html.find('>', idx)
        tag = html[start:end]
        self.assertIn('mapstar-enemy', tag)

    def test_no_scanners_shows_enemy_fleets_and_star_ownership(self):
        user1 = User.objects.create_user('noscan_map_1', 'ns1@test.com', 'pass')
        account1 = Account.objects.create(django_user=user1)
        user2 = User.objects.create_user('noscan_map_2', 'ns2@test.com', 'pass')
        account2 = Account.objects.create(django_user=user2)

        factory = GameFactory()
        factory.set_map_size(100, 100)
        factory.set_owner(account1)
        factory.create_stars(12)
        game = factory.save()
        game.joinable = True
        game.no_scanners = True
        game.save(update_fields=['joinable', 'no_scanners'])

        player1 = factory.join_player(account1, get_default_race())
        player2 = factory.join_player(account2, get_default_race())
        enemy_star = player2.homeworld
        enemy_star.x = 42
        enemy_star.y = 42
        enemy_star.save(update_fields=['x', 'y'])

        enemy_fleet = Fleet.objects.create(
            game=game,
            player=player2,
            name='Visible Raider',
            x=45,
            y=45,
        )

        starmap = StarMap(game, player1)
        html = starmap.render_map()
        self.assertIn('mapfleet-enemy', html)
        self.assertIn(f'data-object-id="{enemy_fleet.short_id}"', html)

        needle = f'data-object-id="{enemy_star.short_id}"'
        idx = html.find(needle)
        self.assertNotEqual(idx, -1)
        start = html.rfind('<', 0, idx)
        end = html.find('>', idx)
        tag = html[start:end]
        self.assertIn('mapstar-enemy', tag)

    def test_no_scanners_shows_salvage_without_report(self):
        game = default_game(stars=5, fleets=0)
        player = game.players.first()
        game.no_scanners = True
        game.save(update_fields=['no_scanners'])
        salvage = Salvage.objects.create(
            game=game,
            x=26,
            y=26,
            ironium_inventory=30,
            boranium_inventory=5,
            germanium_inventory=0,
        )

        starmap = StarMap(game, player)
        html = starmap.render_map()
        self.assertIn(f'data-object-id="{salvage.short_id}"', html)

    def test_allied_intel_sharing_makes_enemy_fleet_visible(self):
        user1 = User.objects.create_user('share_map_1', 'sm1@test.com', 'pass')
        account1 = Account.objects.create(django_user=user1)
        user2 = User.objects.create_user('share_map_2', 'sm2@test.com', 'pass')
        account2 = Account.objects.create(django_user=user2)

        factory = GameFactory()
        factory.set_map_size(100, 100)
        factory.set_owner(account1)
        factory.create_stars(12)
        game = factory.save()
        game.joinable = True
        game.save(update_fields=['joinable'])

        player1 = factory.join_player(account1, get_default_race())
        player2 = factory.join_player(account2, get_default_race())
        enemy_fleet = Fleet.objects.create(
            game=game,
            player=player2,
            name='Hidden Scout',
            x=88,
            y=88,
            basic_scanner_range=0,
            advanced_scanner_range=0,
        )

        starmap = StarMap(game, player1)
        html = starmap.render_map()
        self.assertNotIn(f'data-object-id="{enemy_fleet.short_id}"', html)

        PlayerDiplomaticStance.objects.create(
            player=player2,
            target_player=player1,
            stance='ALLIED',
        )

        starmap = StarMap(game, player1)
        html = starmap.render_map()
        self.assertIn(f'data-object-id="{enemy_fleet.short_id}"', html)
        self.assertIn('mapfleet-allied', html)

        allied_star = player2.homeworld
        html_with_star = starmap.render_star(allied_star)
        self.assertIn('mapstar-allied', html_with_star)

    def test_unowned_fleet_uses_unexplored_grey_style(self):
        game = default_game(stars=5, fleets=0)
        player = game.players.first()
        derelict = Fleet.objects.create(
            game=game,
            player=None,
            name='Derelict',
            x=45,
            y=45,
        )

        starmap = StarMap(game, player)
        html = starmap.render_fleet(derelict)
        self.assertIn('mapfleet-unowned', html)
