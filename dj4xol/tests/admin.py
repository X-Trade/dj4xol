from unittest.mock import patch

from django.contrib.auth.models import User
from django.test import Client, TestCase
from django.urls import reverse

from ..models import Player
from ._util import default_game, get_default_race


class GameAdminAiPlayerViewTest(TestCase):
    def setUp(self):
        self.game = default_game(stars=8)
        self.race = get_default_race()
        self.client = Client()
        self.admin_user = User.objects.create_superuser(
            username='admin_user',
            email='admin@example.com',
            password='testpass123',
        )
        self.client.force_login(self.admin_user)

    def test_add_ai_player_view_renders(self):
        response = self.client.get(
            reverse('admin:add-ai-player', args=[self.game.pk])
        )

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'Add AI player')
        self.assertContains(response, 'AI Player Type')
        self.assertContains(response, 'Homeworld Star')

    def test_add_ai_player_view_adds_ai_to_selected_homeworld(self):
        target_star = self.game.stars.filter(player=None).order_by('name', 'id').first()

        response = self.client.post(
            reverse('admin:add-ai-player', args=[self.game.pk]),
            {
                'ai_module': 'idle',
                'default_diplomatic_stance': 'WARM',
                'starting_tech_level': '4',
                'race': str(self.race.pk),
                'homeworld_star': str(target_star.pk),
            },
        )

        self.assertEqual(response.status_code, 302)
        ai_player = self.game.players.get(is_ai=True)
        self.assertEqual(ai_player.ai_module, 'idle')
        self.assertEqual(ai_player.default_diplomatic_stance, 'WARM')
        self.assertEqual(ai_player.starting_tech_level, 4)
        self.assertEqual(ai_player.homeworld_id, target_star.id)

    def test_add_ai_player_view_uses_random_race_path(self):
        with patch('dj4xol.admin.build_random_ai_race_template', return_value=self.race) as race_mock, \
             patch('dj4xol.admin.resolve_ai_slot_stance', return_value='COLD') as stance_mock:
            response = self.client.post(
                reverse('admin:add-ai-player', args=[self.game.pk]),
                {
                    'ai_module': 'idle',
                    'default_diplomatic_stance': 'RANDOM',
                    'starting_tech_level': '',
                    'race': '__RANDOM__',
                    'homeworld_star': '',
                },
            )

        self.assertEqual(response.status_code, 302)
        ai_player = self.game.players.get(is_ai=True)
        self.assertEqual(ai_player.ai_module, 'idle')
        self.assertEqual(ai_player.default_diplomatic_stance, 'COLD')
        self.assertIsInstance(ai_player, Player)
        race_mock.assert_called_once_with(
            max_starting_tech_level=self.game.max_starting_tech_level
        )
        stance_mock.assert_called_once_with('RANDOM')
