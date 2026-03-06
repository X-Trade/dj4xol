from django.test import TestCase
from unittest.mock import patch

from ..messages import DiplomaticMessageFactory, AnomalyTargetLostMessageFactory
from ..models import Game, Player, ServerRaceType
from ._util import default_game


class testDiplomaticMessageFactory(TestCase):
    def setUp(self):
        self.race_type, _ = ServerRaceType.objects.get_or_create(
            code='TEST',
            defaults={'name': 'Test Race', 'description': 'Default test race type'}
        )

    def test_message_is_created(self):
        game = Game(name='Test Game', map_size_x=100, map_size_y=100, description='Test')
        game.save()
        players = []
        for name in ["The Orb of Great Importance", "The Bard Empirium", "Humanity"]:
            player = Player(game=game, name=name, plural_name=name, race_type=self.race_type)
            player.save()
            players.append(player)
        mf = DiplomaticMessageFactory(game=game, player=players[0], encounter_player=players[1])
        message_basic = mf.new_message().message
        self.assertIn("The Bard Empirium", message_basic)
        self.assertTrue(len(message_basic) > 10)
        mf.append_outcome("Colonists", 100)
        message2 = mf.message.message
        self.assertIn("Colonists", message2)
        self.assertIn("100", message2)
        self.assertIn(message_basic, message2)


class TestAnomalyTargetLostMessageFactory(TestCase):
    def test_message_links_fleet_and_space_but_not_deleted_anomaly(self):
        game = default_game(stars=2, fleets=1)
        player = game.players.first()
        fleet = game.fleets.first()
        factory = AnomalyTargetLostMessageFactory(
            game,
            player,
            fleet,
            'Vanished Rift',
            'RIFT',
            42,
            24,
        )
        with patch('dj4xol.messages.random.random', return_value=1.0):
            message = factory.new_message().message
        self.assertIn(fleet.short_id, message)
        self.assertIn('Empty Space (42, 24)', message)
        self.assertIn('Vanished Rift', message)
        self.assertNotIn('>Vanished Rift</a>', message)

    def test_wormhole_message_uses_enter_wording(self):
        game = default_game(stars=2, fleets=1)
        player = game.players.first()
        fleet = game.fleets.first()
        factory = AnomalyTargetLostMessageFactory(
            game,
            player,
            fleet,
            'Wormhole 1',
            'WORMHOLE',
            10,
            12,
        )
        with patch('dj4xol.messages.random.choice', return_value=('collapsed', 'into')):
            message = factory.new_message().message
        self.assertIn('orders to enter Wormhole 1', message)
        self.assertIn('collapsed into', message)
