from ..factory import GameFactory
from ..starnamer import StarNamer
from django.test import TestCase
from ..models import Game, Player
from django.contrib.auth import models as auth_models

class testGameFactory(TestCase):
    def setUp(self):
        self.players = []
        for n in range(2):
            django_user = auth_models.User.objects.create_user(
                username="test_userX"+str(n), email="X"+str(n)+"@example.com", password="1234")
            player = Player.objects.create(
                django_user=django_user)
            self.players.append(player)
        gf = GameFactory()
        return super().setUp()
    
    def cleanUp(self):
        Game.objects.all().delete()
        for player in self.players:
            player.user.delete()
            player.delete()
        return super().cleanUp()

    def test_create_game(self):
        gf = GameFactory()
        self.assertIsInstance(gf.game, Game)
        self.assertEqual(gf.stars, [])
        self.assertEqual(gf.ships, [])
    
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
    
    def test_saved_game(self):
        gf = GameFactory()
        gf.set_map_size(150, 150)
        gf.create_stars(5)
        gf.set_owner(self.players[0])
        gf.add_player(self.players[1])
        gf._create_random_ships(3)
        game = gf.save()
        game.refresh_from_db()
        self.assertIsInstance(game, Game)
        self.assertEqual(game.map_size_x, 150)
        self.assertEqual(game.map_size_y, 150)
        self.assertEqual(game.stars.count(), 5)
        self.assertEqual(game.players.count(), 2)
        self.assertEqual(game.ships.count(), 6)  # 3 ships per player
        self.assertEqual(game.owner, self.players[0])


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