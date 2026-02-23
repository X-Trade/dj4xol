from unittest.mock import patch

from django.test import TestCase

from ..models import GameMessage, ResearchCategory, Technology
from ..research import ensure_player_research_rows
from ..turn import GameTurn
from ._util import default_game


class ResearchEventsTest(TestCase):
    def setUp(self):
        self.game = default_game(stars=5)
        self.player = self.game.players.first()
        self.star = self.player.homeworld
        self.category = ResearchCategory.objects.create(
            code='ENERGY', name='Energy', enabled=True
        )
        Technology.objects.create(
            category=self.category,
            level=1,
            name='Warp 3',
            tech_type='PROPULSION',
            params_json='{"max_warp_speed": 3}',
            enabled=True,
        )

    def test_research_unlock_creates_message(self):
        self.star.mines = 0
        self.star.factories = 0
        self.star.defenses = 0
        self.star.shipyards = 0
        self.star.labs = 10
        self.star.colonists = 10000
        self.star.save()

        row = ensure_player_research_rows(self.player)[0]
        row.allocation_percent = 100
        row.save(update_fields=['allocation_percent'])

        GameTurn(self.game).research()

        msg = GameMessage.objects.filter(
            game=self.game, player=self.player, category='GENERAL'
        ).order_by('-id').first()
        self.assertIsNotNone(msg)
        self.assertIn('Energy', msg.message)
        self.assertIn('level', msg.message.lower())

    def test_research_breakthrough_event_adds_rp_and_message(self):
        self.game.random_events = True
        self.game.save(update_fields=['random_events'])
        self.star.labs = 5
        self.star.colonists = 5000
        self.star.save()

        row = ensure_player_research_rows(self.player)[0]
        row.allocation_percent = 100
        row.stored_rp = 0
        row.current_level = 0
        row.save(update_fields=['allocation_percent', 'stored_rp', 'current_level'])

        turn = GameTurn(self.game)
        with patch('dj4xol.turn.random.random', side_effect=[0.0, 0.0, 0.5]):
            turn._trigger_research_breakthrough_event(self.player)

        row.refresh_from_db()
        self.assertGreaterEqual(int(row.stored_rp), 0)
        msg = GameMessage.objects.filter(
            game=self.game, player=self.player, category='RANDOM'
        ).order_by('-id').first()
        self.assertIsNotNone(msg)
        self.assertIn('RP', msg.message)
        self.assertIn('Energy', msg.message)
