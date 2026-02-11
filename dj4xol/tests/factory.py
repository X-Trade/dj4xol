from ..factory import GameFactory
from ..starnamer import StarNamer
from django.test import TestCase
from ..models import Game, Account, ServerRaceType, ServerRace
from django.contrib.auth.models import User


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
        self.assertEqual(game.fleets.count(), 6)
        self.assertEqual(game.owner, self.accounts[0])

    def test_join_player_sets_homeworld_population(self):
        self.race_type.starting_population = 500
        self.race_type.save()
        gf = GameFactory()
        gf.set_map_size(100, 100)
        gf.set_owner(self.accounts[0])
        gf.create_stars(5)
        gf.save()
        player = gf.join_player(self.accounts[0], self.races[0])
        self.assertEqual(player.homeworld.colonists, 500)

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
