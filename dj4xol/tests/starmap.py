from ..starmap import StarMap
from ..models import Star, Fleet
from ._util import default_game
from django.test import TestCase


class TestStarMap(TestCase):
    def test_render_map(self):
        game = default_game(fleets=1)
        player = game.players.first()
        starmap = StarMap(game, player)
        html = starmap.render_map()
        self.assertIn('class="mapstar', html)
        self.assertIn('class="mapfleet', html)