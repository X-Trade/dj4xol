from ..factory import GameFactory
from ..starnamer import StarNamer
from django.test import TestCase
from ..models import (
    Game, Account, ServerRaceType, ServerRace, ResearchCategory, Technology, Anomaly,
    Star, Fleet, random_anomaly_stability_init, random_wormhole_stability_init,
)
from math import atanh, tanh

from ..research import ensure_player_research_rows, get_player_tech_effects
from ..mineral_rules import random_asteroid_field_minerals
from ._util import default_game
from django.contrib.auth.models import User
from unittest.mock import patch


class testGameFactory(TestCase):
    def setUp(self):
        self.race_type, _ = ServerRaceType.objects.get_or_create(
            code='TEST', defaults={'name': 'Test', 'description': 'Test', 'enabled': False}
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

    def test_natural_asteroid_fields_use_reduced_default_total_cap(self):
        with patch('dj4xol.mineral_rules.random.randint', return_value=50000) as randint_mock:
            iron, bor, germ = random_asteroid_field_minerals()

        randint_mock.assert_called_once_with(1000, 50000)
        self.assertEqual(iron + bor + germ, 50000)

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

    def test_stars_do_not_stack_without_systems(self):
        modes = [
            {'clusters': False, 'spiral_arms': False},
            {'clusters': True, 'spiral_arms': False},
            {'clusters': False, 'spiral_arms': True},
        ]
        for mode in modes:
            gf = GameFactory()
            gf.set_map_size(120, 120)
            gf.game.anomalies_enabled = False
            gf.create_stars(250, systems=False, **mode)
            coords = [(s.x, s.y) for s in gf.stars]
            self.assertTrue(len(coords) > 0)
            self.assertEqual(len(coords), len(set(coords)))

    def test_systems_allow_stacked_stars(self):
        gf = GameFactory()
        gf.set_map_size(120, 120)
        gf.game.anomalies_enabled = False
        gf.create_stars(200, systems=True)
        coords = [(s.x, s.y) for s in gf.stars]
        self.assertTrue(len(coords) > 0)
        self.assertLess(len(set(coords)), len(coords))

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

    def test_join_player_allows_multiple_ai_players_without_account(self):
        gf = GameFactory()
        gf.set_map_size(150, 150)
        gf.set_owner(self.accounts[0])
        gf.create_stars(8)
        game = gf.save()

        ai_one = gf.join_player(None, self.races[0], invited=True, is_ai=True, ai_module='micromanager')
        ai_two = gf.join_player(None, self.races[1], invited=True, is_ai=True, ai_module='idle')

        self.assertIsNotNone(ai_one)
        self.assertIsNotNone(ai_two)
        self.assertTrue(ai_one.is_ai)
        self.assertTrue(ai_two.is_ai)
        self.assertEqual(ai_one.ai_module, 'micromanager')
        self.assertEqual(ai_two.ai_module, 'idle')
        self.assertIsNone(ai_one.account_id)
        self.assertIsNone(ai_two.account_id)
        self.assertEqual(game.players.filter(is_ai=True).count(), 2)
        self.assertNotEqual(ai_one.name, self.races[0].name)
        self.assertNotEqual(ai_two.name, self.races[1].name)
        self.assertTrue(ai_one.plural_name.endswith('s'))
        self.assertTrue(ai_two.plural_name.endswith('s'))

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

    def test_join_player_splits_starting_population_across_starting_colonies(self):
        self.race_type.starting_colonies = 2
        self.race_type.save(update_fields=['starting_colonies'])
        self.races[0].starting_colonists = 5
        self.races[0].save(update_fields=['starting_colonists'])
        gf = GameFactory()
        gf.set_map_size(100, 100)
        gf.set_owner(self.accounts[0])
        gf.create_stars(10)
        gf.save()

        player = gf.join_player(self.accounts[0], self.races[0])
        owned_stars = list(player.stars.order_by('id'))
        self.assertEqual(len(owned_stars), 2)
        self.assertEqual(sum(star.colonists for star in owned_stars), 5000)
        self.assertEqual(sorted(star.colonists for star in owned_stars), [2500, 2500])
        secondary = [star for star in owned_stars if star.id != player.homeworld_id][0]
        self.assertLessEqual(gf._distance(player.homeworld, secondary), 30.0)

    def test_join_player_splits_mines_and_factories_with_homeworld_remainder(self):
        self.race_type.starting_colonies = 2
        self.race_type.save(update_fields=['starting_colonies'])
        self.races[0].starting_mines = 5
        self.races[0].starting_factories = 3
        self.races[0].save(update_fields=['starting_mines', 'starting_factories'])
        gf = GameFactory()
        gf.set_map_size(100, 100)
        gf.set_owner(self.accounts[0])
        gf.create_stars(10)
        gf.save()

        player = gf.join_player(self.accounts[0], self.races[0])
        owned_stars = list(player.stars.order_by('id'))
        self.assertEqual(len(owned_stars), 2)
        homeworld = player.homeworld
        secondary = [star for star in owned_stars if star.id != homeworld.id][0]
        self.assertEqual(homeworld.mines, 3)
        self.assertEqual(secondary.mines, 2)
        self.assertEqual(homeworld.factories, 2)
        self.assertEqual(secondary.factories, 1)
        self.assertEqual(homeworld.labs, self.races[0].starting_labs)
        self.assertEqual(homeworld.shipyards, self.races[0].starting_shipyards)
        self.assertEqual(secondary.labs, 0)
        self.assertEqual(secondary.shipyards, 0)

    def test_join_player_creates_secondary_starting_colony_when_needed(self):
        self.race_type.starting_colonies = 2
        self.race_type.save(update_fields=['starting_colonies'])
        gf = GameFactory()
        gf.set_map_size(100, 100)
        gf.set_owner(self.accounts[0])
        gf.create_stars(1)
        gf.save()

        player = gf.join_player(self.accounts[0], self.races[0])
        owned_stars = list(player.stars.order_by('id'))
        self.assertEqual(len(owned_stars), 2)
        self.assertEqual(gf.game.stars.count(), 2)
        secondary = [star for star in owned_stars if star.id != player.homeworld_id][0]
        self.assertLessEqual(gf._distance(player.homeworld, secondary), 30.0)
        self.assertNotEqual(
            (secondary.gravity, secondary.temperature, secondary.radiation),
            (
                player.gravity_center,
                player.temperature_center,
                player.radiation_center,
            ),
        )

    def test_join_player_uses_stacked_secondary_colony_only_as_fallback(self):
        self.race_type.starting_colonies = 2
        self.race_type.save(update_fields=['starting_colonies'])
        gf = GameFactory()
        gf.set_map_size(200, 200)
        gf.set_owner(self.accounts[0])
        gf.create_stars(30, systems=True)
        gf.save()

        stars_by_coord = {}
        for star in gf.game.stars.all():
            stars_by_coord.setdefault((star.x, star.y), []).append(star)
        stacked_group = next(group for group in stars_by_coord.values() if len(group) > 1)
        chosen_homeworld = stacked_group[0]
        for idx, star in enumerate(
            gf.game.stars.exclude(id__in=[s.id for s in stacked_group]).order_by('id')
        ):
            # Move all non-stacked stars to the far edge opposite the chosen homeworld
            # so no non-stacked candidate can remain within STARTING_COLONY_RADIUS.
            if chosen_homeworld.x >= (gf.game.map_size_x // 2):
                star.x = max(0, min(20, idx))
            else:
                star.x = min(int(gf.game.map_size_x), int(gf.game.map_size_x) - idx)
            if chosen_homeworld.y >= (gf.game.map_size_y // 2):
                star.y = max(0, min(20, idx))
            else:
                star.y = min(int(gf.game.map_size_y), int(gf.game.map_size_y) - idx)
            star.save(update_fields=['x', 'y'])

        with patch.object(gf, '_find_homeworld_star', return_value=chosen_homeworld):
            player = gf.join_player(self.accounts[0], self.races[0])

        owned_stars = list(player.stars.order_by('id'))
        self.assertEqual(len(owned_stars), 2)
        secondary = [star for star in owned_stars if star.id != player.homeworld_id][0]
        self.assertEqual((secondary.x, secondary.y), (player.homeworld.x, player.homeworld.y))

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

    def test_homeworld_name_duplicate_uses_generated_name_for_later_player(self):
        shared_name = 'Shared Home'
        self.races[0].homeworld_name = shared_name
        self.races[1].homeworld_name = shared_name
        self.races[0].save(update_fields=['homeworld_name'])
        self.races[1].save(update_fields=['homeworld_name'])

        gf = GameFactory()
        gf.set_map_size(100, 100)
        gf.set_owner(self.accounts[0])
        gf.game.joinable = True
        gf.create_stars(8)
        gf.save()
        original_names = [s.name for s in gf.stars]

        first = gf.join_player(self.accounts[0], self.races[0])
        second = gf.join_player(self.accounts[1], self.races[1])

        self.assertEqual(first.homeworld.name, shared_name)
        self.assertNotEqual(second.homeworld.name, shared_name)
        self.assertIn(second.homeworld.name, original_names)

    def test_ai_homeworld_name_override_is_not_applied(self):
        self.races[0].homeworld_name = 'AI Prime'
        self.races[0].save(update_fields=['homeworld_name'])

        gf = GameFactory()
        gf.set_map_size(100, 100)
        gf.set_owner(self.accounts[0])
        gf.create_stars(8)
        gf.save()
        original_names = [s.name for s in gf.stars]

        ai_player = gf.join_player(
            None,
            self.races[0],
            invited=True,
            is_ai=True,
            ai_module='idle',
        )
        self.assertIsNotNone(ai_player)
        self.assertNotEqual(ai_player.homeworld.name, 'AI Prime')
        self.assertIn(ai_player.homeworld.name, original_names)

    def test_ai_name_generation_drops_terminal_a_for_ans_style(self):
        singular, plural = GameFactory._build_ai_demonym('Alpha', 'ans')
        self.assertEqual(singular, 'Alphan')
        self.assertEqual(plural, 'Alphans')

    def test_ai_name_generation_drops_terminal_i_for_oids_style(self):
        singular, plural = GameFactory._build_ai_demonym('Centuri', 'oids')
        self.assertEqual(singular, 'Centuroid')
        self.assertEqual(plural, 'Centuroids')

    def test_ai_name_generation_handles_alphanumeric_homeworld_fragments(self):
        singular, plural = GameFactory._build_unique_ai_identity(
            'X-131',
            existing_names=set(),
        )
        self.assertEqual(singular, 'Xan')
        self.assertEqual(plural, 'Xans')

    def test_ai_name_generation_uses_last_homeworld_word(self):
        singular, plural = GameFactory._build_unique_ai_identity(
            'Delta Centuri',
            existing_names=set(),
        )
        self.assertEqual(singular, 'Centuroid')
        self.assertEqual(plural, 'Centuroids')

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

    def test_improved_star_names_number_stacked_system_members(self):
        gf = GameFactory()
        gf.set_map_size(200, 200)
        gf.stars = [
            Star(name='Centauri', x=10, y=10),
            Star(name='Old B', x=10, y=10),
            Star(name='Old C', x=10, y=10),
        ]
        with patch('dj4xol.factory.random.random', return_value=0.9):
            gf._apply_improved_star_names(clusters=False)

        self.assertEqual(
            [star.name for star in gf.stars],
            ['Centauri I', 'Centauri II', 'Centauri III'],
        )

    def test_improved_star_names_use_related_cluster_names(self):
        gf = GameFactory()
        gf.set_map_size(200, 200)
        gf.stars = [
            Star(name='Centauri', x=10, y=10),
            Star(name='Old B', x=10, y=10),
            Star(name='Bellatrix', x=18, y=12),
            Star(name='Rigel', x=26, y=15),
        ]
        with patch('dj4xol.factory.random.random', return_value=0.9):
            gf._apply_improved_star_names(clusters=True)

        self.assertEqual(gf.stars[0].name, 'Alpha Centauri I')
        self.assertEqual(gf.stars[1].name, 'Alpha Centauri II')
        self.assertEqual(gf.stars[2].name, 'Beta Centauri')
        self.assertEqual(gf.stars[3].name, 'Gamma Centauri')

    def test_improved_star_names_can_leave_traditional_system_unique(self):
        gf = GameFactory()
        gf.set_map_size(200, 200)
        gf.stars = [
            Star(name='Centauri', x=10, y=10),
            Star(name='Bellatrix', x=10, y=10),
        ]
        with patch('dj4xol.factory.random.random', return_value=0.1):
            gf._apply_improved_star_names(clusters=False)

        self.assertEqual([star.name for star in gf.stars], ['Centauri', 'Bellatrix'])

    def test_improved_star_names_leave_catalogue_system_names_alone(self):
        gf = GameFactory()
        gf.set_map_size(200, 200)
        gf.stars = [
            Star(name='NGC-127', x=10, y=10),
            Star(name='LV-426', x=10, y=10),
            Star(name='Centauri', x=20, y=20),
        ]
        with patch('dj4xol.factory.random.random', return_value=0.9):
            gf._apply_improved_star_names(clusters=True)

        self.assertEqual(gf.stars[0].name, 'NGC-127')
        self.assertEqual(gf.stars[1].name, 'LV-426')
        self.assertEqual(gf.stars[2].name, 'Centauri')

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

    def test_join_player_defaults_non_singular_research_to_even_split(self):
        self.races[0].singular_research = False
        self.races[0].save(update_fields=['singular_research'])
        gf = GameFactory()
        gf.set_map_size(100, 100)
        gf.set_owner(self.accounts[0])
        gf.create_stars(5)
        gf.save()

        player = gf.join_player(self.accounts[0], self.races[0])
        rows = ensure_player_research_rows(player)
        allocations = [int(row.allocation_percent or 0) for row in rows]
        self.assertEqual(sum(allocations), 100)
        self.assertLessEqual(max(allocations) - min(allocations), 1)

    def test_game_scoped_short_ids_resolve_map_object_collision(self):
        game = default_game(stars=1, fleets=0)
        player = game.players.first()
        base_id = f"{game.short_id[:4]}dup00000"
        with patch(
            'dj4xol.models.AbstractGameObject._generate_short_id_from_uuid',
            return_value=base_id,
        ):
            star = Star.objects.create(game=game, name='Dup Star', x=2, y=2)
            fleet = Fleet.objects.create(game=game, player=player, name='Dup Fleet', x=2, y=2)
        self.assertEqual(star.short_id, base_id)
        self.assertNotEqual(fleet.short_id, base_id)
        self.assertTrue(fleet.short_id.startswith(base_id[:11]))

    def test_game_scoped_short_ids_allow_cross_game_duplicates(self):
        game_a = default_game(stars=1, fleets=0)
        game_b = default_game(stars=1, fleets=0)
        short_id = "dup000000000"
        star_a = Star.objects.create(game=game_a, name='Dup A', x=3, y=3, short_id=short_id)
        star_b = Star.objects.create(game=game_b, name='Dup B', x=4, y=4, short_id=short_id)
        self.assertEqual(star_a.short_id, short_id)
        self.assertEqual(star_b.short_id, short_id)

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
        self.race_type.warp_advantage = 0.6
        self.race_type.save(update_fields=['warp_advantage'])
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
        self.assertAlmostEqual(fleet.warp_advantage, 0.6, places=4)
        self.assertAlmostEqual(fleet.offense_level, effects['offense_level'], places=4)
        self.assertAlmostEqual(fleet.defense_level, effects['defense_level'], places=4)
        self.assertEqual(fleet.basic_scanner_range, effects['basic_scanner_range'])
        self.assertEqual(fleet.advanced_scanner_range, effects['advanced_scanner_range'])
        self.assertEqual(
            fleet.fuel_factory_mg_per_year,
            effects['fuel_factory_mg_per_year'],
        )
        self.assertEqual(
            fleet.fuel_factory_max_warp,
            effects['fuel_factory_max_warp'],
        )

    def test_starting_fleets_combine_race_and_hull_speed_advantage_with_cap(self):
        self.race_type.warp_advantage = 0.6
        self.race_type.save(update_fields=['warp_advantage'])
        category, _ = ResearchCategory.objects.get_or_create(
            code='TEST_HULL_SPEED',
            defaults={'name': 'Test Hull Speed', 'description': 'Test hull speed tech'}
        )
        Technology.objects.create(
            category=category,
            level=4,
            name='Test L4 Swift Hull',
            tech_type='HULL',
            params_json='{"max_cargo_capacity": 200, "max_fuel": 100, "hull_thumbnail_class": "scout", "warp_advantage": 0.5}',
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

        expected = tanh(atanh(0.6) + atanh(0.5))
        self.assertAlmostEqual(effects['warp_advantage'], 0.5, places=4)
        self.assertAlmostEqual(fleet.warp_advantage, expected, places=4)
        self.assertIn('/scout/', fleet.thumbnail_path)

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

    def test_random_anomaly_stability_init_is_fixed_baseline(self):
        self.assertEqual(random_anomaly_stability_init(), 50)

    def test_random_wormhole_stability_init_is_fixed_baseline(self):
        self.assertEqual(random_wormhole_stability_init(), 50)


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

    def test_primary_primary_name_can_fall_back_to_single_name(self):
        namer = StarNamer()
        with patch('dj4xol.starnamer.random.randint', side_effect=[0]):
            self.assertEqual(
                namer._random_name(index=0, chance=7),
                namer._data[0],
            )

    def test_primary_primary_name_still_exists_when_gate_passes(self):
        namer = StarNamer()
        with patch('dj4xol.starnamer.random.randint', side_effect=[1, 2]):
            self.assertEqual(
                namer._random_name(index=0, chance=7),
                '%s %s' % (namer._data[2], namer._data[0]),
            )
