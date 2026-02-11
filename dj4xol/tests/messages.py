from django.test import TestCase
from ..messages import DiplomaticMessageFactory
from ..models import Game, Player, ServerRaceType


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
