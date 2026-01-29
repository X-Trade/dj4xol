from ..starmap import StarMap
from ..models import Star, Ship
from ._util import default_game
from django.test import TestCase


class TestStarMap(TestCase):
    def test_render_map(self):
        game = default_game()
        player = game.players.first()
        starmap = StarMap(game, player)
        html = starmap.render_map()
        self.assertIn('<div class="mapstar"', html)
        self.assertIn('<div class="mapship"', html)