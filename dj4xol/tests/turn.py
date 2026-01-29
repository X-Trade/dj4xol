from ..turn import GameTurn
from ..factory import GameFactory
from django.test import TestCase
from ._util import default_game, default_game_factory

class TestGameTurn(TestCase):
    def test_generate_turn(self):
        game = default_game_factory().set_year(1000).save()
        turn = GameTurn(game)
        turn.generate_turn()
        self.assertEquals(game.year, 1001)

    def test_multiple_turns(self):
        game = default_game_factory().set_year(1000).save()
        turn = GameTurn(game)
        turn.generate_turns(5)
        self.assertEquals(game.year, 1005)