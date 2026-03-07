from django.test import TestCase, Client
from django.urls import reverse
from django.contrib.auth.models import User

from ..models import Account, Fleet, ServerSettings, Spectator
from ..factory import GameFactory
from ._util import get_default_race


class SpectatorViewTest(TestCase):
    def setUp(self):
        self.user = User.objects.create_user('spectator_user', 'spec@test.com', 'pass')
        self.account = Account.objects.create(django_user=self.user)
        self.client = Client()
        self.client.force_login(self.user)

        owner_user = User.objects.create_user('owner_user', 'owner@test.com', 'pass')
        owner_account = Account.objects.create(django_user=owner_user)
        factory = GameFactory()
        factory.set_map_size(60, 60)
        factory.set_owner(owner_account)
        factory.create_stars(5)
        self.game = factory.save()
        self.game.public = True
        self.game.joinable = True
        self.game.save(update_fields=['public', 'joinable'])

        race = get_default_race()
        self.player = factory.join_player(owner_account, race)

    def test_spectator_consent_blocks_join(self):
        response = self.client.post(
            reverse('dj4xol:spectate_game_confirm', args=[self.game.short_id])
        )
        self.assertEqual(response.status_code, 302)
        self.assertTrue(Spectator.objects.filter(game=self.game, account=self.account).exists())

        join_response = self.client.get(
            reverse('dj4xol:join_game', args=[self.game.short_id])
        )
        self.assertEqual(join_response.status_code, 403)

    def test_disabled_spectator_mode_hides_view_action(self):
        ServerSettings.objects.update_or_create(
            key='enable_spectator_mode',
            defaults={'value': 'False', 'description': 'Enable spectator mode'},
        )

        response = self.client.get(reverse('dj4xol:index'))
        self.assertEqual(response.status_code, 200)
        self.assertNotContains(
            response,
            reverse('dj4xol:spectate_game_confirm', args=[self.game.short_id]),
        )

    def test_spectate_confirm_uses_form_navigation_menu(self):
        response = self.client.get(
            reverse('dj4xol:spectate_game_confirm', args=[self.game.short_id])
        )
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'id="hamburger-btn"')
        self.assertContains(response, 'id="nav-dropdown"')
        self.assertNotContains(response, 'class="nav-link-game"')
        self.assertNotContains(response, '>Research<', html=True)

    def test_disabled_spectator_mode_blocks_confirm(self):
        ServerSettings.objects.update_or_create(
            key='enable_spectator_mode',
            defaults={'value': 'False', 'description': 'Enable spectator mode'},
        )

        response = self.client.get(
            reverse('dj4xol:spectate_game_confirm', args=[self.game.short_id])
        )
        self.assertEqual(response.status_code, 403)
        self.assertContains(
            response,
            'Spectator mode is disabled on this server',
            status_code=403,
        )

    def test_disabled_spectator_mode_blocks_starmap(self):
        ServerSettings.objects.update_or_create(
            key='enable_spectator_mode',
            defaults={'value': 'False', 'description': 'Enable spectator mode'},
        )
        Spectator.objects.create(game=self.game, account=self.account)

        response = self.client.get(
            reverse('dj4xol:spectate_game', args=[self.game.short_id])
        )
        self.assertEqual(response.status_code, 403)
        self.assertContains(
            response,
            'Spectator mode is disabled on this server',
            status_code=403,
        )

    def test_spectator_basic_detail_includes_star_resources_and_population(self):
        star = self.game.stars.first()
        star.player = self.player
        star.colonists = 5000
        star.ironium_yield = 40
        star.ironium_inventory = 120
        star.save(update_fields=[
            'player', 'colonists', 'ironium_yield', 'ironium_inventory'
        ])

        Spectator.objects.create(game=self.game, account=self.account)
        response = self.client.get(
            reverse('dj4xol:spectate_game', args=[self.game.short_id]) + f'?sel={star.short_id}'
        )
        self.assertEqual(response.status_code, 200)
        detail = response.context['detail']
        self.assertEqual(detail.get('report_tier'), 'basic')
        self.assertTrue(detail.get('owner_known'))
        self.assertEqual(detail.get('population'), 5000)
        self.assertIn('ironium', detail.get('resources', {}))

    def test_spectator_basic_detail_includes_fleet_inventory(self):
        star = self.game.stars.first()
        fleet = Fleet.objects.create(
            game=self.game,
            player=self.player,
            name='Enemy Cargo',
            x=star.x,
            y=star.y,
            cargo_capacity=200,
            ironium_inventory=35,
            max_fuel=100,
            fuel=40,
        )
        Spectator.objects.create(game=self.game, account=self.account)
        response = self.client.get(
            reverse('dj4xol:spectate_game', args=[self.game.short_id]) + f'?sel={fleet.short_id}'
        )
        detail = response.context['detail']
        self.assertEqual(detail.get('report_tier'), 'basic')
        self.assertFalse(detail.get('show_composition'))
        self.assertIn('ironium', detail.get('fleet_inventory', {}))
        self.assertEqual(detail.get('fleet_cargo', {}).get('capacity'), 200)

    def test_spectator_admin_view_shows_composition(self):
        self.user.is_staff = True
        self.user.save(update_fields=['is_staff'])

        star = self.game.stars.first()
        fleet = Fleet.objects.create(
            game=self.game,
            player=self.player,
            name='Enemy Combat',
            x=star.x,
            y=star.y,
            ship_count=4,
            integrity=80,
            cargo_capacity=120,
            ironium_inventory=20,
        )
        Spectator.objects.create(game=self.game, account=self.account)
        response = self.client.get(
            reverse('dj4xol:spectate_game', args=[self.game.short_id]) + f'?sel={fleet.short_id}'
        )
        detail = response.context['detail']
        self.assertTrue(detail.get('show_composition'))
        self.assertEqual(detail.get('fleet_cargo', {}).get('ship_count'), 4)
        self.assertEqual(detail.get('fleet_cargo', {}).get('ironium'), 20)
