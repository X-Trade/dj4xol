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


class PlayerAdminFormTest(TestCase):
    def setUp(self):
        self.game = default_game(stars=8)
        self.player = self.game.players.get()
        self.player.is_ai = True
        self.player.ai_module = 'idle'
        self.player.save(update_fields=['is_ai', 'ai_module'])
        self.client = Client()
        self.admin_user = User.objects.create_superuser(
            username='player_admin_user',
            email='player-admin@example.com',
            password='testpass123',
        )
        self.client.force_login(self.admin_user)

    def test_player_admin_game_is_readonly_on_change_form(self):
        response = self.client.get(
            reverse('admin:dj4xol_player_change', args=[self.player.pk])
        )

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, str(self.game))
        self.assertNotContains(response, 'name="game"', html=False)

    def test_player_admin_homeworld_queryset_is_limited_to_player_colonies(self):
        extra_colony = self.game.stars.filter(player=None).order_by('name', 'id').first()
        extra_colony.player = self.player
        extra_colony.colonists = 1000
        extra_colony.save(update_fields=['player', 'colonists'])
        unowned_star = self.game.stars.filter(player=None).order_by('name', 'id').first()

        response = self.client.get(
            reverse('admin:dj4xol_player_change', args=[self.player.pk])
        )

        self.assertEqual(response.status_code, 200)
        homeworld_queryset = response.context['adminform'].form.fields['homeworld'].queryset
        homeworld_ids = list(homeworld_queryset.values_list('id', flat=True))
        self.assertEqual(
            homeworld_ids,
            list(self.player.stars.order_by('name', 'id').values_list('id', flat=True)),
        )
        self.assertNotIn(unowned_star.id, homeworld_ids)

    def test_player_admin_ai_module_uses_select_widget(self):
        response = self.client.get(
            reverse('admin:dj4xol_player_change', args=[self.player.pk])
        )

        self.assertEqual(response.status_code, 200)
        ai_module_field = response.context['adminform'].form.fields['ai_module']
        self.assertEqual(ai_module_field.widget.__class__.__name__, 'Select')
        self.assertIn(('idle', 'Idle'), list(ai_module_field.choices))
