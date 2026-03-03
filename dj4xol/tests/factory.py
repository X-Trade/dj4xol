from ..factory import GameFactory
from ..starnamer import StarNamer
from django.test import TestCase
from ..models import (
    Game, Account, ServerRaceType, ServerRace, ResearchCategory, Technology, Anomaly,
    random_anomaly_stability_init,
)
from ..research import get_player_tech_effects
from django.contrib.auth.models import User
from unittest.mock import patch


class testGameFactory(TestCase):
    def setUp(self):
        self.race_type, _ = ServerRaceType.objects.get_or_create(
            code='TEST', defaults={'name': 'Test', 'description': 'Test'}
        )
        self.races = [
            ServerRace.objects.create(
                name=n, plural_name=n+'s', race_type=self.race_type
            ) for n in ['Humanoid', 'Roboticon']
        ]
        self.accounts = [
            Account.objects.create(
                django_user=User.objects.create_user(f'user{i}', f'{i}@test.com', 'pass')
            ) for i in range(2)
        ]

    def test_create_game(self):
        gf = GameFactory()
        self.assertIsInstance(gf.game, Game)
        self.assertEqual(gf.stars, [])

    def test_map_size(self):
        gf = GameFactory()
        gf.set_map_size(100, 100)
        self.assertEqual(gf.game.map_size_x, 100)
        self.assertEqual(gf.game.map_size_y, 100)

    def test_create_stars(self):
        gf = GameFactory()
        gf.set_map_size(200, 200)
        gf.create_stars(10)
        self.assertEqual(len(gf.stars), 10)
        for star in gf.stars:
            self.assertTrue(0 <= star.x <= 200)
            self.assertTrue(0 <= star.y <= 200)

    def test_saved_game_with_players(self):
        gf = GameFactory()
        gf.set_map_size(150, 150)
        gf.set_owner(self.accounts[0])
        gf.game.joinable = True  # Allow others to join
        gf.create_stars(5)
        game = gf.save()
        gf.join_player(self.accounts[0], self.races[0])
        gf.join_player(self.accounts[1], self.races[1])
        gf._create_random_fleets(3)

        game.refresh_from_db()
        self.assertEqual(game.map_size_x, 150)
        self.assertEqual(game.stars.count(), 5)
        self.assertEqual(game.players.count(), 2)
        self.assertEqual(game.fleets.count(), 10)
        self.assertEqual(game.owner, self.accounts[0])

    def test_join_player_sets_homeworld_population(self):
        self.races[0].starting_colonists = 5
        self.races[0].save()
        gf = GameFactory()
        gf.set_map_size(100, 100)
        gf.set_owner(self.accounts[0])
        gf.create_stars(5)
        gf.save()
        player = gf.join_player(self.accounts[0], self.races[0])
        self.assertEqual(player.homeworld.colonists, 5000)

    def test_leftover_points_for_research_do_not_increase_homeworld_minerals(self):
        self.races[0].leftover_points = 20.0
        self.races[0].spend_leftover_points_on_research = True
        self.races[0].save(update_fields=['leftover_points', 'spend_leftover_points_on_research'])
        gf = GameFactory()
        gf.set_map_size(100, 100)
        gf.set_owner(self.accounts[0])
        gf.create_stars(5)
        gf.save()
        for star in gf.game.stars.all():
            star.ironium_inventory = 1000
            star.boranium_inventory = 1000
            star.germanium_inventory = 1000
            star.save(update_fields=['ironium_inventory', 'boranium_inventory', 'germanium_inventory'])
        player = gf.join_player(self.accounts[0], self.races[0])
        homeworld = player.homeworld
        self.assertTrue(player.spend_leftover_points_on_research)
        self.assertEqual(homeworld.ironium_inventory, 1000)
        self.assertEqual(homeworld.boranium_inventory, 1000)
        self.assertEqual(homeworld.germanium_inventory, 1000)

    def test_homeworlds_are_spaced_apart(self):
        gf = GameFactory()
        gf.set_map_size(200, 200)  # min distance = min(250, 50) = 50
        gf.set_owner(self.accounts[0])
        gf.game.joinable = True
        gf.create_stars(100)
        gf.save()
        p1 = gf.join_player(self.accounts[0], self.races[0])
        p2 = gf.join_player(self.accounts[1], self.races[1])
        dist = gf._distance(p1.homeworld, p2.homeworld)
        # Should be at least 50ly apart (25% of 200)
        self.assertGreaterEqual(dist, 50)

    def test_homeworld_environmentals_match_player_centers(self):
        """Homeworld should have environmentals set to player's habitable centers."""
        self.races[0].gravity_center = 0.8
        self.races[0].temperature_center = 1.2
        self.races[0].radiation_center = 0.5
        self.races[0].save()
        gf = GameFactory()
        gf.set_map_size(100, 100)
        gf.set_owner(self.accounts[0])
        gf.create_stars(5)
        gf.save()
        player = gf.join_player(self.accounts[0], self.races[0])
        self.assertAlmostEqual(player.homeworld.gravity, 0.8)
        self.assertAlmostEqual(player.homeworld.temperature, 1.2)
        self.assertAlmostEqual(player.homeworld.radiation, 0.5)

    def test_homeworld_name_override(self):
        """Homeworld name should be overridden if race has homeworld_name set."""
        self.races[0].homeworld_name = 'Terra Prime'
        self.races[0].save()
        gf = GameFactory()
        gf.set_map_size(100, 100)
        gf.set_owner(self.accounts[0])
        gf.create_stars(5)
        gf.save()
        player = gf.join_player(self.accounts[0], self.races[0])
        self.assertEqual(player.homeworld.name, 'Terra Prime')

    def test_homeworld_name_not_overridden_if_blank(self):
        """Homeworld name should not be overridden if race has no homeworld_name."""
        self.races[0].homeworld_name = ''
        self.races[0].save()
        gf = GameFactory()
        gf.set_map_size(100, 100)
        gf.set_owner(self.accounts[0])
        gf.create_stars(5)
        gf.save()
        original_names = [s.name for s in gf.stars]
        player = gf.join_player(self.accounts[0], self.races[0])
        # Name should be one of the original generated names
        self.assertIn(player.homeworld.name, original_names)

    def test_systems_adds_companion_stars(self):
        """Systems option should add companion stars at same coordinates."""
        gf = GameFactory()
        gf.set_map_size(200, 200)
        gf.set_owner(self.accounts[0])
        gf.create_stars(40, systems=True)  # 25% of 40 = 10 stars get companions
        # Should have more than 40 stars due to companions
        self.assertGreater(len(gf.stars), 40)
        # Check that some stars share coordinates (indicating systems)
        coords = [(s.x, s.y) for s in gf.stars]
        unique_coords = set(coords)
        self.assertLess(len(unique_coords), len(coords))

    def test_join_player_applies_starting_tech_level_to_research_rows(self):
        self.races[0].starting_tech_level = 3
        self.races[0].save(update_fields=['starting_tech_level'])
        gf = GameFactory()
        gf.set_map_size(100, 100)
        gf.set_owner(self.accounts[0])
        gf.create_stars(5)
        gf.save()

        player = gf.join_player(self.accounts[0], self.races[0])
        levels = set(
            player.research_progress.values_list('current_level', flat=True)
        )
        self.assertEqual(levels, {3.0})

    def test_join_player_caps_starting_tech_level_and_refunds_leftover_points(self):
        self.races[0].starting_tech_level = 3
        self.races[0].leftover_points = 1.0
        self.races[0].spend_leftover_points_on_research = True
        self.races[0].save(update_fields=[
            'starting_tech_level',
            'leftover_points',
            'spend_leftover_points_on_research',
        ])
        gf = GameFactory()
        gf.set_map_size(100, 100)
        gf.set_owner(self.accounts[0])
        gf.create_stars(5)
        gf.save()
        gf.game.max_starting_tech_level = 2
        gf.game.save(update_fields=['max_starting_tech_level'])

        player = gf.join_player(self.accounts[0], self.races[0])
        self.assertEqual(player.starting_tech_level, 2)
        # L3 costs 26 BP and L2 costs 13 BP, so 13 BP refunded + 1 existing.
        self.assertEqual(player.leftover_points, 14.0)
        levels = set(
            player.research_progress.values_list('current_level', flat=True)
        )
        self.assertEqual(levels, {2.0})

    def test_starting_fleets_follow_player_starting_tech_effects(self):
        category, _ = ResearchCategory.objects.get_or_create(
            code='TEST_HULL',
            defaults={'name': 'Test Hull', 'description': 'Test hull tech'}
        )
        Technology.objects.create(
            category=category,
            level=4,
            name='Test L4 Hull',
            tech_type='HULL',
            params_json='{"max_cargo_capacity": 777, "max_fuel": 333, "hull_thumbnail_class": "capital"}',
            enabled=True,
            display_order=9999,
        )
        Technology.objects.create(
            category=category,
            level=4,
            name='Test L4 Warp',
            tech_type='PROPULSION',
            params_json='{"max_warp_speed": 9, "fuel_efficiency": 0.8, "overmax_fuel_penalty": 1.3}',
            enabled=True,
            display_order=9999,
        )
        Technology.objects.create(
            category=category,
            level=4,
            name='Test L4 Offense',
            tech_type='ENERGY_WEAPON',
            params_json='{"offense_level": 0.7}',
            enabled=True,
            display_order=9999,
        )
        Technology.objects.create(
            category=category,
            level=4,
            name='Test L4 Defense',
            tech_type='SHIELD',
            params_json='{"defense_level": 0.6}',
            enabled=True,
            display_order=9999,
        )

        self.races[0].starting_tech_level = 4
        self.races[0].starting_fleets = 1
        self.races[0].save(update_fields=['starting_tech_level', 'starting_fleets'])

        gf = GameFactory()
        gf.set_map_size(100, 100)
        gf.set_owner(self.accounts[0])
        gf.create_stars(5)
        gf.save()
        player = gf.join_player(self.accounts[0], self.races[0])
        fleet = player.fleets.first()
        effects = get_player_tech_effects(player)

        self.assertEqual(fleet.cargo_capacity, effects['max_cargo_capacity'])
        self.assertEqual(fleet.max_fuel, effects['max_fuel'])
        self.assertEqual(fleet.fuel, effects['max_fuel'])
        self.assertEqual(fleet.max_safe_warp, effects['max_warp_speed'])
        self.assertAlmostEqual(fleet.fuel_efficiency, effects['fuel_efficiency'], places=4)
        self.assertAlmostEqual(fleet.overmax_fuel_penalty, effects['overmax_fuel_penalty'], places=4)
        self.assertAlmostEqual(fleet.offense_level, effects['offense_level'], places=4)
        self.assertAlmostEqual(fleet.defense_level, effects['defense_level'], places=4)
        self.assertIn('/capital/', fleet.thumbnail_path)

    def test_initial_anomalies_have_unique_short_ids(self):
        gf = GameFactory()
        gf.set_map_size(180, 180)
        gf.set_owner(self.accounts[0])
        gf.game.anomalies_enabled = True
        gf.create_stars(80)
        game = gf.save()
        anomalies = list(Anomaly.objects.filter(game=game))
        self.assertTrue(len(anomalies) > 0)
        short_ids = [a.short_id for a in anomalies]
        self.assertEqual(len(short_ids), len(set(short_ids)))
        self.assertTrue(all(bool(sid) and len(sid) == 12 for sid in short_ids))
        self.assertTrue(all(0.0 <= float(a.heading) < 360.0 for a in anomalies))
        self.assertTrue(all(0 <= int(a.stability) <= 100 for a in anomalies))

    def test_random_anomaly_stability_init_distribution_bands(self):
        with patch('dj4xol.models.random.random', return_value=0.10):
            with patch('dj4xol.models.random.randint', return_value=95):
                self.assertEqual(random_anomaly_stability_init(), 95)
        with patch('dj4xol.models.random.random', return_value=0.80):
            with patch('dj4xol.models.random.randint', return_value=65):
                self.assertEqual(random_anomaly_stability_init(), 65)


class testStarNamer(TestCase):
    def test_data_contains_no_duplicates(self):
        namer = StarNamer()
        for template in namer._data:
            self.assertEqual(1, namer._data.count(template), msg=template)

        for template in namer._additional:
            self.assertEqual(1, namer._additional.count(template), msg=template)

    def test_namer_returns_unique_names(self):
        namer = StarNamer()
        names = [namer.get_unique() for _ in range(1000)]
        self.assertEqual(len(names), len(set(names)))
