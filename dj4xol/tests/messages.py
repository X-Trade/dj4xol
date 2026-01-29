from django.test import TestCase
from ..messages import DiplomaticMessageFactory
from ..models import Game, PlayerRace


class testDiplomaticMessageFactory(TestCase):
    def test_message_is_created(self):
        game = Game()
        races = []
        for name in ["The Orb of Great Importance", "The Bard Empirium", "Humanity"]:
            race = PlayerRace(game=game, name=name, formal_name=name, plural_name=name)
            races.append(race)
        mf = DiplomaticMessageFactory(game=game, player_race=races[0], encounter_race=races[1])
        message_basic = mf.new_message().message
        self.assertIn("The Bard Empirium", message_basic)
        self.assertTrue(len(message_basic) > 10)
        mf.append_outcome("Colonists", 100)
        message2 = mf.message.message
        self.assertIn("Colonists", message2)
        self.assertIn("100", message2)
        self.assertIn(message_basic, message2)
