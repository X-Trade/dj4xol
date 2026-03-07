import json

from django.test import TestCase, Client
from django.urls import reverse
from django.contrib.auth.models import User
from ..models import (
    Account,
    Fleet,
    FleetOrders,
    GameMessage,
    ProductionOrder,
    Report,
    ResearchCategory,
    Salvage,
    ServerSettings,
    Technology,
)
from ..research import ensure_player_research_rows
from ..turn import (
    GameTurn,
    format_basic_hidden_salvage_name,
    format_basic_unknown_fleet_name,
)
from ..factory import GameFactory
from ._util import default_game, get_default_user, get_default_race


class TestLandingPage(TestCase):
    def test_anonymous_index_renders_dynamic_landing_lists(self):
        response = self.client.get(reverse('dj4xol:index'))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'data-panel="roadmap"')
        self.assertTrue(response.context['feature_highlights'])
        self.assertTrue(response.context['roadmap_priorities'])
        self.assertTrue(response.context['roadmap_future'])
        self.assertContains(response, response.context['feature_highlights'][0])
        self.assertContains(response, response.context['roadmap_priorities'][0])
        self.assertContains(response, response.context['roadmap_future'][0])

    def test_staff_home_shows_server_settings_action(self):
        user, _ = get_default_user()
        user.is_staff = True
        user.save(update_fields=['is_staff'])
        client = Client()
        client.force_login(user)

        response = client.get(reverse('dj4xol:index'))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'Server Settings')

    def test_home_shows_turned_in_status_for_my_quorum_game(self):
        game = default_game(stars=5)
        player = game.players.first()
        player.turned_in = True
        player.save(update_fields=['turned_in'])

        user, _ = get_default_user()
        client = Client()
        client.force_login(user)

        response = client.get(reverse('dj4xol:index'))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'Turned in')


class TestMessageFiltering(TestCase):
    def test_messages_filtered_by_messages_seen_year(self):
        """Messages should be filtered to year >= messages_seen_year."""
        game = default_game(stars=5)
        player = game.players.first()
        # Create messages for different years
        GameMessage.objects.create(game=game, player=player, year=2400, message="Old message")
        GameMessage.objects.create(game=game, player=player, year=2401, message="Middle message")
        GameMessage.objects.create(game=game, player=player, year=2402, message="Recent message")
        # Set messages_seen_year to 2401
        player.messages_seen_year = 2401
        player.save()
        # Filter as the view does
        messages = player.messages.filter(year__gte=player.messages_seen_year)
        self.assertEqual(messages.count(), 2)
        years = set(m.year for m in messages)
        self.assertIn(2401, years)
        self.assertIn(2402, years)
        self.assertNotIn(2400, years)

    def test_all_messages_shown_when_messages_seen_year_null(self):
        """All messages should be shown when messages_seen_year is None."""
        game = default_game(stars=5)
        player = game.players.first()
        GameMessage.objects.create(game=game, player=player, year=2400, message="Old message")
        GameMessage.objects.create(game=game, player=player, year=2401, message="Recent message")
        self.assertIsNone(player.messages_seen_year)
        # Without filter, all messages shown
        messages = player.messages.all()
        self.assertEqual(messages.count(), 2)

    def test_messages_limited_to_1000(self):
        """Messages should be limited to 1000."""
        game = default_game(stars=5)
        player = game.players.first()
        # Create 1100 messages
        for i in range(1100):
            GameMessage.objects.create(game=game, player=player, year=2400, message=f"Message {i}")
        # Apply limit as view does
        messages = player.messages.order_by('-year', '-id')[:1000]
        self.assertEqual(len(messages), 1000)

    def test_last_seen_year_updated_on_view(self):
        """last_seen_year should be updated when viewing the game."""
        game = default_game(stars=5)
        game.year = 2405
        game.save()
        player = game.players.first()
        player.last_seen_year = 2400
        player.save()
        user, account = get_default_user()
        client = Client()
        client.force_login(user)
        # Visit the game view
        response = client.get(reverse('dj4xol:game', args=[game.short_id]))
        self.assertEqual(response.status_code, 200)
        # Check last_seen_year was updated
        player.refresh_from_db()
        self.assertEqual(player.last_seen_year, 2405)

    def test_messages_seen_year_updated_on_turn_generation(self):
        """messages_seen_year should be updated from last_seen_year when turn generates."""
        game = default_game(stars=5)
        player = game.players.first()
        player.last_seen_year = 2400
        player.messages_seen_year = None
        player.save()
        GameTurn(game).generate_turn()
        player.refresh_from_db()
        # messages_seen_year should now equal last_seen_year
        self.assertEqual(player.messages_seen_year, 2400)

    def test_messages_persist_on_reload(self):
        """Messages should not disappear when page is reloaded."""
        game = default_game(stars=5)
        game.year = 2405
        game.save()
        player = game.players.first()
        # Simulate: player viewed at 2404, turn generated, now at 2405
        player.last_seen_year = 2404
        player.messages_seen_year = 2404
        player.save()
        # Create a message from the turn
        GameMessage.objects.create(game=game, player=player, year=2404, message="Turn message")
        user, account = get_default_user()
        client = Client()
        client.force_login(user)
        # First view - should see message
        response = client.get(reverse('dj4xol:game', args=[game.short_id]))
        self.assertContains(response, "Turn message")
        # Reload - should still see message (messages_seen_year unchanged)
        response = client.get(reverse('dj4xol:game', args=[game.short_id]))
        self.assertContains(response, "Turn message")
        player.refresh_from_db()
        # last_seen_year updated but messages_seen_year unchanged
        self.assertEqual(player.last_seen_year, 2405)
        self.assertEqual(player.messages_seen_year, 2404)


class TestProductionOrders(TestCase):
    def _unlock_administration(self, player, tech_level=1, administration_level=1):
        build_cost = {
            1: {'bp': 120, 'ironium': 300, 'boranium': 0, 'germanium': 450},
            2: {'bp': 90, 'ironium': 225, 'boranium': 0, 'germanium': 325},
            3: {'bp': 70, 'ironium': 175, 'boranium': 0, 'germanium': 250},
        }[administration_level]
        category = ResearchCategory.objects.create(
            code='VIEWAUTO%s' % tech_level,
            name='View Auto %s' % tech_level,
            enabled=True,
        )
        Technology.objects.create(
            category=category,
            level=tech_level,
            name='Administration %s' % administration_level,
            tech_type='INFRASTRUCTURE',
            params_json=(
                '{"administration_level": %s, "production_cost_overrides": '
                '{"BUILD_ADMINISTRATION": {"bp": %s, "ironium": %s, '
                '"boranium": %s, "germanium": %s, "colonists": 0}}}'
            ) % (
                administration_level,
                build_cost['bp'],
                build_cost['ironium'],
                build_cost['boranium'],
                build_cost['germanium'],
            ),
        )
        rows = ensure_player_research_rows(player)
        for row in rows:
            if row.category_id == category.id:
                row.current_level = float(tech_level)
                row.save(update_fields=['current_level'])
                break

    def test_blank_production_order_not_created(self):
        """Submitting blank order_type should not create a production order."""
        game = default_game(stars=5)
        player = game.players.first()
        homeworld = player.homeworld
        user, account = get_default_user()
        client = Client()
        client.force_login(user)
        initial_count = ProductionOrder.objects.filter(star=homeworld).count()
        # Submit with blank order_type
        response = client.post(
            reverse('dj4xol:add_production', args=[game.short_id]),
            {'star': homeworld.short_id, 'order_type': ''}
        )
        self.assertEqual(response.status_code, 302)  # Redirects
        # No new order should be created
        self.assertEqual(
            ProductionOrder.objects.filter(star=homeworld).count(),
            initial_count
        )

    def test_valid_production_order_created(self):
        """Submitting valid order_type should create a production order."""
        game = default_game(stars=5)
        player = game.players.first()
        homeworld = player.homeworld
        user, account = get_default_user()
        client = Client()
        client.force_login(user)
        initial_count = ProductionOrder.objects.filter(star=homeworld).count()
        # Submit with valid order_type
        response = client.post(
            reverse('dj4xol:add_production', args=[game.short_id]),
            {'star': homeworld.short_id, 'order_type': 'BUILD_MINE'}
        )
        self.assertEqual(response.status_code, 302)  # Redirects
        # New order should be created
        self.assertEqual(
            ProductionOrder.objects.filter(star=homeworld).count(),
            initial_count + 1
        )
        # Verify the order type
        order = ProductionOrder.objects.filter(star=homeworld).first()
        self.assertEqual(order.order_type, 'BUILD_MINE')

    def test_toggle_production_order_repeat(self):
        """Production order repeat can be toggled from the list button."""
        game = default_game(stars=5)
        player = game.players.first()
        homeworld = player.homeworld
        order = ProductionOrder.objects.create(
            game=game,
            star=homeworld,
            order_type='BUILD_MINE',
            repeat=False,
        )

        user, account = get_default_user()
        client = Client()
        client.force_login(user)

        response = client.post(
            reverse('dj4xol:toggle_production_order_repeat', args=[game.short_id, order.short_id]),
            {'x': homeworld.x, 'y': homeworld.y, 'sel': homeworld.short_id}
        )
        self.assertEqual(response.status_code, 302)
        order.refresh_from_db()
        self.assertTrue(order.repeat)

        response = client.post(
            reverse('dj4xol:toggle_production_order_repeat', args=[game.short_id, order.short_id]),
            {'x': homeworld.x, 'y': homeworld.y, 'sel': homeworld.short_id}
        )
        self.assertEqual(response.status_code, 302)
        order.refresh_from_db()
        self.assertFalse(order.repeat)

    def test_toggle_production_order_repeat_ignored_for_administration(self):
        """Administration construction should not allow repeat toggling."""
        game = default_game(stars=5)
        player = game.players.first()
        homeworld = player.homeworld
        order = ProductionOrder.objects.create(
            game=game,
            star=homeworld,
            order_type='BUILD_ADMINISTRATION',
            repeat=False,
        )

        user, account = get_default_user()
        client = Client()
        client.force_login(user)

        response = client.post(
            reverse(
                'dj4xol:toggle_production_order_repeat',
                args=[game.short_id, order.short_id]
            ),
            {'x': homeworld.x, 'y': homeworld.y, 'sel': homeworld.short_id}
        )
        self.assertEqual(response.status_code, 302)
        order.refresh_from_db()
        self.assertFalse(order.repeat)

    def test_add_administration_order_forces_repeat_off(self):
        """Administration orders should ignore repeat when added."""
        game = default_game(stars=5)
        player = game.players.first()
        homeworld = player.homeworld
        self._unlock_administration(player)

        user, account = get_default_user()
        client = Client()
        client.force_login(user)

        response = client.post(
            reverse('dj4xol:add_production', args=[game.short_id]),
            {
                'star': homeworld.short_id,
                'order_type': 'BUILD_ADMINISTRATION',
                'quantity': 9,
                'repeat': 'on',
            }
        )
        self.assertEqual(response.status_code, 302)

        order = ProductionOrder.objects.get(
            star=homeworld,
            order_type='BUILD_ADMINISTRATION',
        )
        self.assertEqual(order.quantity, 1)
        self.assertFalse(order.repeat)

    def test_add_remove_administration_order_forces_repeat_off(self):
        """Administration removal should ignore repeat when added."""
        game = default_game(stars=5)
        player = game.players.first()
        homeworld = player.homeworld
        homeworld.has_administration = True
        homeworld.save(update_fields=['has_administration'])
        self._unlock_administration(player)

        user, account = get_default_user()
        client = Client()
        client.force_login(user)

        response = client.post(
            reverse('dj4xol:add_production', args=[game.short_id]),
            {
                'star': homeworld.short_id,
                'order_type': 'REMOVE_ADMINISTRATION',
                'quantity': 9,
                'repeat': 'on',
            }
        )
        self.assertEqual(response.status_code, 302)

        order = ProductionOrder.objects.get(
            star=homeworld,
            order_type='REMOVE_ADMINISTRATION',
        )
        self.assertEqual(order.quantity, 1)
        self.assertFalse(order.repeat)


class TestServerSettingsView(TestCase):
    def setUp(self):
        self.user, _ = get_default_user()
        self.client = Client()
        self.client.force_login(self.user)

    def test_non_staff_cannot_access_server_settings(self):
        response = self.client.get(reverse('dj4xol:server_settings'))
        self.assertEqual(response.status_code, 403)
        self.assertContains(response, 'Staff access is required.', status_code=403)

    def test_staff_can_view_and_save_server_settings(self):
        self.user.is_staff = True
        self.user.save(update_fields=['is_staff'])

        response = self.client.get(reverse('dj4xol:server_settings'))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'General (web)')
        self.assertContains(response, 'Email')
        self.assertContains(response, 'AI Integration')
        self.assertContains(response, 'Profanity Filter')
        self.assertContains(response, 'Public Server URL')
        self.assertContains(response, 'Used for links in emails')
        self.assertContains(response, 'Enable Spectator Mode')
        self.assertContains(response, 'Enable Profanity Filter')
        self.assertContains(response, 'Profanity Whitelist')
        self.assertContains(response, 'Profanity Blacklist')

        response = self.client.post(
            reverse('dj4xol:server_settings'),
            {
                'server_name': 'DJ4XOL Production',
                'server_tagline': 'Live server',
                'server_admin': 'Admin User',
                'server_contact': 'admin@example.test',
                'server_url': 'https://example.test/this/path/is/longer/than/thirty/chars',
                'server_welcome': 'Welcome to the production cluster.',
                'allow_self_signup': 'on',
                'enable_email': 'on',
                'enable_spectator_mode': 'on',
                'enable_gpt': '',
                'enable_debug_actions': '',
                'enable_play_api': 'on',
                'enable_profanity_filter': '',
                'profanity_filter_whitelist': 'scunthorpe',
                'profanity_filter_blacklist': 'void',
            },
            follow=True,
        )
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'Server settings updated.')
        self.assertContains(response, 'form-message-banner')
        self.assertNotContains(response, 'data-panel="alerts"')

        self.assertEqual(ServerSettings.get('server_name'), 'DJ4XOL Production')
        self.assertEqual(ServerSettings.get('server_contact'), 'admin@example.test')
        self.assertEqual(
            ServerSettings.get('server_url'),
            'https://example.test/this/path/is/longer/than/thirty/chars',
        )
        self.assertEqual(
            ServerSettings.objects.get(key='server_url').long_value,
            'https://example.test/this/path/is/longer/than/thirty/chars',
        )
        self.assertEqual(
            ServerSettings.get('server_welcome'),
            'Welcome to the production cluster.',
        )
        self.assertEqual(ServerSettings.get('enable_email'), 'True')
        self.assertEqual(ServerSettings.get('enable_spectator_mode'), 'True')
        self.assertEqual(ServerSettings.get('enable_gpt'), 'False')
        self.assertEqual(ServerSettings.get('enable_profanity_filter'), 'False')
        self.assertEqual(ServerSettings.get('profanity_filter_whitelist'), 'scunthorpe')
        self.assertEqual(ServerSettings.get('profanity_filter_blacklist'), 'void')

    def test_staff_server_settings_normalises_public_server_url(self):
        self.user.is_staff = True
        self.user.save(update_fields=['is_staff'])

        response = self.client.post(
            reverse('dj4xol:server_settings'),
            {
                'server_name': 'DJ4XOL Production',
                'server_tagline': '',
                'server_admin': '',
                'server_contact': '',
                'server_url': 'https://example.test/4x/',
                'server_welcome': '',
                'allow_self_signup': 'on',
                'enable_email': '',
                'enable_spectator_mode': '',
                'enable_gpt': '',
                'enable_debug_actions': '',
                'enable_play_api': 'on',
                'enable_profanity_filter': 'on',
                'profanity_filter_whitelist': '',
                'profanity_filter_blacklist': '',
            },
            follow=True,
        )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(ServerSettings.get('server_url'), 'https://example.test')


class TestGameDetailRendering(TestCase):
    def test_selected_object_renders_detail_panel(self):
        game = default_game(stars=5, fleets=1)
        player = game.players.first()
        target = player.homeworld
        user, _ = get_default_user()
        client = Client()
        client.force_login(user)

        response = client.get(
            reverse('dj4xol:game', args=[game.short_id]),
            {'x': target.x, 'y': target.y, 'sel': target.short_id},
        )
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'data-panel="detail"')
        self.assertContains(response, 'id="detail"')

    def test_no_scanners_hides_scanner_controls_and_overlay(self):
        game = default_game(stars=5, fleets=0)
        game.no_scanners = True
        game.save(update_fields=['no_scanners'])
        player = game.players.first()
        target = player.homeworld
        user, _ = get_default_user()
        client = Client()
        client.force_login(user)

        response = client.get(
            reverse('dj4xol:game', args=[game.short_id]),
            {'x': target.x, 'y': target.y, 'sel': target.short_id},
        )
        self.assertEqual(response.status_code, 200)
        self.assertNotContains(response, 'starmap-scanners')
        self.assertNotContains(response, 'scanner-range-overlay')
        self.assertContains(response, 'play-terminal-overlay')
        self.assertContains(response, 'playCliBootstrapUrl')

    def test_toggle_production_order_repeat_blocked_when_turned_in(self):
        """Repeat toggle should be blocked when player has turned in."""
        game = default_game(stars=5)
        player = game.players.first()
        player.turned_in = True
        player.save(update_fields=['turned_in'])
        homeworld = player.homeworld
        order = ProductionOrder.objects.create(
            game=game,
            star=homeworld,
            order_type='BUILD_MINE',
            repeat=False,
        )

        user, account = get_default_user()
        client = Client()
        client.force_login(user)
        response = client.post(
            reverse('dj4xol:toggle_production_order_repeat', args=[game.short_id, order.short_id])
        )
        self.assertEqual(response.status_code, 302)
        order.refresh_from_db()
        self.assertFalse(order.repeat)


class TestProfileView(TestCase):
    def test_profile_shows_turned_in_status_for_my_quorum_game(self):
        game = default_game(stars=5)
        player = game.players.first()
        player.turned_in = True
        player.save(update_fields=['turned_in'])

        user, _ = get_default_user()
        client = Client()
        client.force_login(user)

        response = client.get(reverse('dj4xol:profile'))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'Turned in')


class TestPreJoinNavigation(TestCase):
    def test_join_game_hides_in_game_navigation_links(self):
        game = default_game(stars=5)
        user, _ = get_default_user()
        client = Client()
        client.force_login(user)

        response = client.get(reverse('dj4xol:join_game', args=[game.short_id]))
        self.assertEqual(response.status_code, 200)
        self.assertNotContains(response, 'class="nav-link-game"')
        self.assertNotContains(response, '>Research<', html=True)


class TestRenameObjectView(TestCase):
    def setUp(self):
        self.game = default_game(stars=5, fleets=1)
        self.player = self.game.players.first()
        self.fleet = self.player.fleets.first()
        self.user, _ = get_default_user()
        self.client = Client()
        self.client.force_login(self.user)

    def test_rename_rejects_markup_characters(self):
        response = self.client.post(
            reverse('dj4xol:rename_object', args=[self.game.short_id, self.fleet.short_id]),
            {'name': 'Bad <Fleet>'},
        )
        self.assertEqual(response.status_code, 400)
        self.assertEqual(
            response.json()['error'],
            'Name contains unsupported characters. Use plain ASCII letters, numbers, spaces, and simple punctuation only.',
        )

    def test_rename_rejects_blocked_profanity(self):
        response = self.client.post(
            reverse('dj4xol:rename_object', args=[self.game.short_id, self.fleet.short_id]),
            {'name': 'fuckfleet'},
        )
        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.json()['error'], 'Name contains blocked profanity.')


class TestPlayCliWebApi(TestCase):
    def setUp(self):
        self.game = default_game(stars=6, fleets=1)
        self.player = self.game.players.first()
        self.user, self.account = get_default_user()
        self.client = Client()
        self.client.force_login(self.user)
        self.origin = 'http://testserver'

    def test_bootstrap_returns_initial_transcript_for_member(self):
        response = self.client.get(
            reverse('dj4xol:play_cli_bootstrap', args=[self.game.short_id])
        )
        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertTrue(payload['ok'])
        joined = '\n'.join(payload['lines'])
        self.assertIn('Connected: game=%s year=%s' % (self.game.short_id, self.game.year), joined)
        self.assertIn('Type /help for available commands.', joined)

    def test_command_endpoint_allows_read_only_command(self):
        response = self.client.post(
            reverse('dj4xol:play_cli_command', args=[self.game.short_id]),
            data=json.dumps({'command': '/status'}),
            content_type='application/json',
            HTTP_ORIGIN=self.origin,
        )
        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertTrue(payload['ok'])
        joined = '\n'.join(payload['lines'])
        self.assertIn('year: %s' % self.game.year, joined)
        self.assertIn('turn_scheme:', joined)

    def test_command_endpoint_allows_fleets_all_filter(self):
        response = self.client.post(
            reverse('dj4xol:play_cli_command', args=[self.game.short_id]),
            data=json.dumps({'command': '/fleets all'}),
            content_type='application/json',
            HTTP_ORIGIN=self.origin,
        )
        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertTrue(payload['ok'])

    def test_command_endpoint_blocks_done_command(self):
        response = self.client.post(
            reverse('dj4xol:play_cli_command', args=[self.game.short_id]),
            data=json.dumps({'command': '/done'}),
            content_type='application/json',
            HTTP_ORIGIN=self.origin,
        )
        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertFalse(payload['ok'])
        self.assertIn('does not support that command', '\n'.join(payload['lines']))
        self.player.refresh_from_db()
        self.assertFalse(self.player.turned_in)

    def test_command_endpoint_allows_orders_clear(self):
        fleet = self.player.fleets.first()
        FleetOrders.objects.create(
            game=self.game,
            fleet=fleet,
            order_type='SCUTTLE',
            position=1,
        )

        response = self.client.post(
            reverse('dj4xol:play_cli_command', args=[self.game.short_id]),
            data=json.dumps({'command': '/orders %s clear' % fleet.short_id}),
            content_type='application/json',
            HTTP_ORIGIN=self.origin,
        )
        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertTrue(payload['ok'])
        self.assertTrue(payload['mutated'])
        self.assertEqual(fleet.orders.count(), 0)

    def test_command_endpoint_allows_orders_add(self):
        fleet = self.player.fleets.first()
        response = self.client.post(
            reverse('dj4xol:play_cli_command', args=[self.game.short_id]),
            data=json.dumps({'command': '/orders %s add SCUTTLE' % fleet.short_id}),
            content_type='application/json',
            HTTP_ORIGIN=self.origin,
        )
        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertTrue(payload['ok'])
        self.assertTrue(payload['mutated'])
        self.assertEqual(fleet.orders.count(), 1)
        self.assertIn('type: SCUTTLE', '\n'.join(payload['lines']))

    def test_command_endpoint_allows_research_allocation_update(self):
        category = ResearchCategory.objects.filter(enabled=True).order_by('id').first()
        response = self.client.post(
            reverse('dj4xol:play_cli_command', args=[self.game.short_id]),
            data=json.dumps({'command': '/research %s 55' % category.code}),
            content_type='application/json',
            HTTP_ORIGIN=self.origin,
        )
        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertTrue(payload['ok'])
        self.assertTrue(payload['mutated'])
        row = self.player.research_progress.get(category=category)
        self.assertEqual(row.allocation_percent, 55.0)
        self.assertIn('allocation_percent: 55.0', '\n'.join(payload['lines']))

    def test_command_endpoint_supports_exit(self):
        response = self.client.post(
            reverse('dj4xol:play_cli_command', args=[self.game.short_id]),
            data=json.dumps({'command': '/exit'}),
            content_type='application/json',
            HTTP_ORIGIN=self.origin,
        )
        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertTrue(payload['ok'])
        self.assertTrue(payload['close_overlay'])
        self.assertFalse(payload['mutated'])

    def test_detail_command_returns_navigation_target(self):
        response = self.client.post(
            reverse('dj4xol:play_cli_command', args=[self.game.short_id]),
            data=json.dumps({'command': '/detail %s' % self.player.homeworld.short_id}),
            content_type='application/json',
            HTTP_ORIGIN=self.origin,
        )
        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertTrue(payload['ok'])
        self.assertEqual(payload['navigate_to']['sel'], self.player.homeworld.short_id)
        self.assertEqual(payload['navigate_to']['x'], self.player.homeworld.x)
        self.assertEqual(payload['navigate_to']['y'], self.player.homeworld.y)
        self.assertTrue(payload['navigate_to']['locate'])

    def test_non_member_cannot_access_play_cli_endpoints(self):
        outsider_user = User.objects.create_user('outsider_cli', 'outsider@test.com', 'pass')
        Account.objects.create(django_user=outsider_user, alias='OUT')
        client = Client()
        client.force_login(outsider_user)

        bootstrap = client.get(
            reverse('dj4xol:play_cli_bootstrap', args=[self.game.short_id])
        )
        command = client.post(
            reverse('dj4xol:play_cli_command', args=[self.game.short_id]),
            data=json.dumps({'command': '/status'}),
            content_type='application/json',
            HTTP_ORIGIN='http://testserver',
        )
        self.assertEqual(bootstrap.status_code, 403)
        self.assertEqual(command.status_code, 403)

    def test_play_api_can_be_disabled(self):
        ServerSettings.objects.update_or_create(
            key='enable_play_api',
            defaults={'value': 'False', 'description': 'Enable web Play CLI API'},
        )

        page = self.client.get(reverse('dj4xol:game', args=[self.game.short_id]))
        bootstrap = self.client.get(
            reverse('dj4xol:play_cli_bootstrap', args=[self.game.short_id])
        )
        command = self.client.post(
            reverse('dj4xol:play_cli_command', args=[self.game.short_id]),
            data=json.dumps({'command': '/status'}),
            content_type='application/json',
            HTTP_ORIGIN=self.origin,
        )

        self.assertEqual(page.status_code, 200)
        self.assertNotContains(page, 'play-terminal-overlay')
        self.assertNotContains(page, 'play_terminal.js')
        self.assertContains(page, 'window.playCliEnabled = false;')
        self.assertEqual(bootstrap.status_code, 404)
        self.assertEqual(command.status_code, 404)

    def test_command_endpoint_rejects_wrong_origin(self):
        response = self.client.post(
            reverse('dj4xol:play_cli_command', args=[self.game.short_id]),
            data=json.dumps({'command': '/status'}),
            content_type='application/json',
            HTTP_ORIGIN='https://evil.example',
        )
        self.assertEqual(response.status_code, 403)
        self.assertEqual(response.json()['error'], 'Origin mismatch')


class TestDetailPanelReportTiers(TestCase):
    def setUp(self):
        self.game = default_game(stars=8, fleets=0)
        self.player = self.game.players.first()
        self.star = self.game.stars.filter(player__isnull=True).first()
        self.user, _ = get_default_user()
        self.client = Client()
        self.client.force_login(self.user)

    def _get_detail_response(self, obj):
        return self.client.get(
            reverse('dj4xol:game', args=[self.game.short_id]),
            {'x': obj.x, 'y': obj.y, 'sel': obj.short_id},
        )

    def test_basic_star_report_shows_unknown_resources_note(self):
        Report.objects.create(
            game=self.game,
            player=self.player,
            year=self.game.year,
            target_type='star',
            target_id=self.star.id,
            cached_report=json.dumps({
                'name': self.star.name,
                'x': self.star.x,
                'y': self.star.y,
                'gravity': self.star.gravity,
                'temperature': self.star.temperature,
                'radiation': self.star.radiation,
                'report_tier': 'basic',
            }),
        )
        response = self._get_detail_response(self.star)
        self.assertContains(response, 'data-section="environmentals"')
        self.assertContains(response, 'data-section="resources"')
        self.assertContains(response, 'Mineral composition unknown.')
        self.assertNotContains(response, 'data-section="infrastructure"')

    def test_advanced_star_report_shows_resources_no_infrastructure(self):
        Report.objects.create(
            game=self.game,
            player=self.player,
            year=self.game.year,
            target_type='star',
            target_id=self.star.id,
            cached_report=json.dumps({
                'name': self.star.name,
                'x': self.star.x,
                'y': self.star.y,
                'gravity': self.star.gravity,
                'temperature': self.star.temperature,
                'radiation': self.star.radiation,
                'player_name': 'Enemy',
                'colonists': 1000,
                'ironium_yield': 50,
                'boranium_yield': 40,
                'germanium_yield': 30,
                'ironium_inventory': 200,
                'boranium_inventory': 150,
                'germanium_inventory': 100,
                'report_tier': 'advanced',
            }),
        )
        response = self._get_detail_response(self.star)
        self.assertContains(response, 'data-section="resources"')
        self.assertNotContains(response, 'data-section="infrastructure"')

    def test_advanced_star_report_shows_base_resources_even_when_empty(self):
        Report.objects.create(
            game=self.game,
            player=self.player,
            year=self.game.year,
            target_type='star',
            target_id=self.star.id,
            cached_report=json.dumps({
                'name': self.star.name,
                'x': self.star.x,
                'y': self.star.y,
                'gravity': self.star.gravity,
                'temperature': self.star.temperature,
                'radiation': self.star.radiation,
                'player_name': 'Enemy',
                'colonists': 0,
                'ironium_yield': 0,
                'boranium_yield': 0,
                'germanium_yield': 0,
                'ironium_inventory': 0,
                'boranium_inventory': 0,
                'germanium_inventory': 0,
                'report_tier': 'advanced',
            }),
        )
        response = self._get_detail_response(self.star)
        self.assertContains(response, 'data-section="resources"')
        self.assertContains(response, 'Ironium')
        self.assertContains(response, 'Boranium')
        self.assertContains(response, 'Germanium')

    def test_encounter_star_report_shows_infrastructure(self):
        Report.objects.create(
            game=self.game,
            player=self.player,
            year=self.game.year,
            target_type='star',
            target_id=self.star.id,
            cached_report=json.dumps({
                'name': self.star.name,
                'x': self.star.x,
                'y': self.star.y,
                'gravity': self.star.gravity,
                'temperature': self.star.temperature,
                'radiation': self.star.radiation,
                'player_name': 'Enemy',
                'colonists': 1200,
                'ironium_yield': 50,
                'boranium_yield': 40,
                'germanium_yield': 30,
                'ironium_inventory': 200,
                'boranium_inventory': 150,
                'germanium_inventory': 100,
                'mines': 3,
                'factories': 4,
                'factories_bp': 12,
                'labs': 2,
                'labs_rp': 8,
                'defenses': 1,
                'defenses_tooltip': None,
                'shipyards': 1,
                'jobs_count': 10,
                'jobs_employment': 0.5,
                'report_tier': 'encounter',
            }),
        )
        response = self._get_detail_response(self.star)
        self.assertContains(response, 'data-section="infrastructure"')

    def test_advanced_fleet_report_hides_capabilities(self):
        self.game.joinable = True
        self.game.save(update_fields=['joinable'])
        other_user = User.objects.create_user('detail_enemy', 'de@test.com', 'pass')
        other_account = Account.objects.create(django_user=other_user)
        factory = GameFactory(game=self.game)
        enemy_player = factory.join_player(other_account, get_default_race())
        enemy_fleet = Fleet.objects.create(
            game=self.game,
            player=enemy_player,
            name='Enemy Fleet',
            x=self.star.x,
            y=self.star.y,
            ship_count=6,
            integrity=90,
        )
        Report.objects.create(
            game=self.game,
            player=self.player,
            year=self.game.year,
            target_type='fleet',
            target_id=enemy_fleet.id,
            cached_report=json.dumps({
                'name': enemy_fleet.name,
                'x': enemy_fleet.x,
                'y': enemy_fleet.y,
                'ship_count': 6,
                'integrity': 90,
                'cargo_capacity': 100,
                'fuel': 50.0,
                'max_fuel': 50.0,
                'report_tier': 'advanced',
            }),
        )
        response = self._get_detail_response(enemy_fleet)
        self.assertContains(response, 'data-section="composition"')
        self.assertNotContains(response, 'Bombs')
        self.assertNotContains(response, 'Wormhole Drive')
        self.assertNotContains(response, '__blur.png')

    def test_basic_fleet_report_obfuscates_name_in_detail_selector(self):
        self.game.joinable = True
        self.game.save(update_fields=['joinable'])
        other_user = User.objects.create_user('detail_enemy_basic', 'deb@test.com', 'pass')
        other_account = Account.objects.create(django_user=other_user)
        factory = GameFactory(game=self.game)
        enemy_player = factory.join_player(other_account, get_default_race())
        enemy_fleet = Fleet.objects.create(
            game=self.game,
            player=enemy_player,
            name='Leakable Fleet Name',
            x=self.star.x,
            y=self.star.y,
            ship_count=3,
            integrity=88,
        )
        Report.objects.create(
            game=self.game,
            player=self.player,
            year=self.game.year,
            target_type='fleet',
            target_id=enemy_fleet.id,
            cached_report=json.dumps({
                'name': format_basic_unknown_fleet_name(enemy_fleet),
                'x': enemy_fleet.x,
                'y': enemy_fleet.y,
                'report_tier': 'basic',
            }),
        )

        response = self._get_detail_response(enemy_fleet)
        self.assertContains(response, format_basic_unknown_fleet_name(enemy_fleet))
        self.assertNotContains(response, 'Leakable Fleet Name')

    def test_encounter_fleet_report_shows_capabilities(self):
        self.game.joinable = True
        self.game.save(update_fields=['joinable'])
        other_user = User.objects.create_user('detail_enemy2', 'de2@test.com', 'pass')
        other_account = Account.objects.create(django_user=other_user)
        factory = GameFactory(game=self.game)
        enemy_player = factory.join_player(other_account, get_default_race())
        enemy_fleet = Fleet.objects.create(
            game=self.game,
            player=enemy_player,
            name='Enemy Fleet',
            x=self.star.x,
            y=self.star.y,
            ship_count=6,
            integrity=90,
            max_safe_warp=8,
            has_bombs='CONVENTIONAL',
            has_wormhole_drive=True,
        )
        Report.objects.create(
            game=self.game,
            player=self.player,
            year=self.game.year,
            target_type='fleet',
            target_id=enemy_fleet.id,
            cached_report=json.dumps({
                'name': enemy_fleet.name,
                'x': enemy_fleet.x,
                'y': enemy_fleet.y,
                'ship_count': 6,
                'integrity': 90,
                'max_safe_warp': 8,
                'has_bombs': 'CONVENTIONAL',
                'has_wormhole_drive': True,
                'report_tier': 'encounter',
            }),
        )
        response = self._get_detail_response(enemy_fleet)
        self.assertContains(response, 'Bombs')
        self.assertContains(response, 'Wormhole Drive')

    def test_basic_star_report_blurs_thumbnail(self):
        Report.objects.create(
            game=self.game,
            player=self.player,
            year=self.game.year,
            target_type='star',
            target_id=self.star.id,
            cached_report=json.dumps({
                'name': self.star.name,
                'x': self.star.x,
                'y': self.star.y,
                'gravity': self.star.gravity,
                'temperature': self.star.temperature,
                'radiation': self.star.radiation,
                'report_tier': 'basic',
            }),
        )
        response = self._get_detail_response(self.star)
        self.assertContains(response, '__blur.png')

    def test_basic_salvage_report_shows_total_and_type_with_blurred_thumbnail(self):
        salvage = Salvage.objects.create(
            game=self.game,
            x=self.star.x + 1,
            y=self.star.y + 1,
            salvage_type=Salvage.TYPE_ANCIENT_DEBRIS,
            ironium_inventory=13,
            boranium_inventory=7,
        )
        Report.objects.create(
            game=self.game,
            player=self.player,
            year=self.game.year,
            target_type='salvage',
            target_id=salvage.id,
            cached_report=json.dumps({
                'name': salvage.name,
                'x': salvage.x,
                'y': salvage.y,
                'salvage_type': salvage.salvage_type,
                'total_minerals': salvage.total_minerals,
                'report_tier': 'basic',
            }),
        )
        response = self._get_detail_response(salvage)
        self.assertContains(response, '__blur.png')
        self.assertContains(response, format_basic_hidden_salvage_name(salvage))
        self.assertNotContains(response, salvage.name)
        self.assertContains(response, 'data-section="salvage"')
        self.assertContains(response, 'data-section="salvage-contents"')
        self.assertContains(response, 'Type')
        self.assertContains(response, 'Ancient Debris')
        self.assertContains(response, 'total: 20kt')
        self.assertContains(response, 'Mineral composition unknown.')
        self.assertNotContains(response, 'Ironium')


class TestFleetOrderViews(TestCase):
    def test_fleet_order_panel_shows_give_fleet_option(self):
        game = default_game(stars=5, fleets=1)
        player = game.players.first()
        fleet = player.fleets.first()
        user, _ = get_default_user()
        client = Client()
        client.force_login(user)

        response = client.get(
            reverse('dj4xol:game', args=[game.short_id]),
            {'x': fleet.x, 'y': fleet.y, 'sel': fleet.short_id},
        )
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, '>Give Fleet<')
        self.assertNotContains(response, '>Transfer Fleet<')

    def test_bomb_order_creation_requires_bomb_capability(self):
        game = default_game(stars=5, fleets=1)
        player = game.players.first()
        fleet = player.fleets.first()
        target_star = game.stars.exclude(id=player.homeworld_id).first()
        user, _ = get_default_user()
        client = Client()
        client.force_login(user)

        response = client.post(
            reverse('dj4xol:add_fleet_order', args=[game.short_id]),
            {
                'fleet': fleet.short_id,
                'order_type': 'BOMB',
                'bomb_target': target_star.short_id,
            }
        )
        self.assertEqual(response.status_code, 302)
        self.assertFalse(fleet.orders.filter(order_type='BOMB').exists())

        fleet.has_bombs = 'CONVENTIONAL'
        fleet.save(update_fields=['has_bombs'])
        response = client.post(
            reverse('dj4xol:add_fleet_order', args=[game.short_id]),
            {
                'fleet': fleet.short_id,
                'order_type': 'BOMB',
                'bomb_target': target_star.short_id,
            }
        )
        self.assertEqual(response.status_code, 302)
        self.assertTrue(fleet.orders.filter(order_type='BOMB').exists())
        self.assertFalse(fleet.orders.filter(order_type='BOMB').first().repeat)

    def test_toggle_repeat_allowed_for_bomb_orders(self):
        game = default_game(stars=5, fleets=1)
        player = game.players.first()
        fleet = player.fleets.first()
        target_star = game.stars.exclude(id=player.homeworld_id).first()
        order = FleetOrders.objects.create(
            game=game,
            fleet=fleet,
            order_type='BOMB',
            target_star=target_star,
            repeat=False,
        )
        user, _ = get_default_user()
        client = Client()
        client.force_login(user)

        response = client.post(
            reverse('dj4xol:toggle_fleet_order_repeat', args=[game.short_id, order.short_id])
        )
        self.assertEqual(response.status_code, 302)
        order.refresh_from_db()
        self.assertTrue(order.repeat)

    def test_remotemine_order_creation_requires_miners(self):
        game = default_game(stars=5, fleets=1)
        player = game.players.first()
        fleet = player.fleets.first()
        target_star = game.stars.exclude(id=player.homeworld_id).first()
        user, _ = get_default_user()
        client = Client()
        client.force_login(user)

        response = client.post(
            reverse('dj4xol:add_fleet_order', args=[game.short_id]),
            {
                'fleet': fleet.short_id,
                'order_type': 'REMOTEMINE',
                'remotemine_target': target_star.short_id,
            }
        )
        self.assertEqual(response.status_code, 302)
        self.assertFalse(fleet.orders.filter(order_type='REMOTEMINE').exists())

        fleet.has_miners = 'SMALL'
        fleet.save(update_fields=['has_miners'])
        response = client.post(
            reverse('dj4xol:add_fleet_order', args=[game.short_id]),
            {
                'fleet': fleet.short_id,
                'order_type': 'REMOTEMINE',
                'remotemine_target': target_star.short_id,
            }
        )
        self.assertEqual(response.status_code, 302)
        self.assertTrue(fleet.orders.filter(order_type='REMOTEMINE').exists())
        self.assertFalse(fleet.orders.filter(order_type='REMOTEMINE').first().repeat)

    def test_bomb_order_creation_respects_repeat_checkbox(self):
        game = default_game(stars=5, fleets=1)
        player = game.players.first()
        fleet = player.fleets.first()
        fleet.has_bombs = 'CONVENTIONAL'
        fleet.save(update_fields=['has_bombs'])
        target_star = game.stars.exclude(id=player.homeworld_id).first()
        user, _ = get_default_user()
        client = Client()
        client.force_login(user)

        response = client.post(
            reverse('dj4xol:add_fleet_order', args=[game.short_id]),
            {
                'fleet': fleet.short_id,
                'order_type': 'BOMB',
                'bomb_target': target_star.short_id,
                'repeat': 'on',
            }
        )
        self.assertEqual(response.status_code, 302)
        order = fleet.orders.filter(order_type='BOMB').first()
        self.assertIsNotNone(order)
        self.assertTrue(order.repeat)

    def test_remotemine_order_creation_respects_repeat_checkbox(self):
        game = default_game(stars=5, fleets=1)
        player = game.players.first()
        fleet = player.fleets.first()
        fleet.has_miners = 'SMALL'
        fleet.save(update_fields=['has_miners'])
        target_star = game.stars.exclude(id=player.homeworld_id).first()
        user, _ = get_default_user()
        client = Client()
        client.force_login(user)

        response = client.post(
            reverse('dj4xol:add_fleet_order', args=[game.short_id]),
            {
                'fleet': fleet.short_id,
                'order_type': 'REMOTEMINE',
                'remotemine_target': target_star.short_id,
                'repeat': 'on',
            }
        )
        self.assertEqual(response.status_code, 302)
        order = fleet.orders.filter(order_type='REMOTEMINE').first()
        self.assertIsNotNone(order)
        self.assertTrue(order.repeat)

    def test_toggle_repeat_allowed_for_remotemine_orders(self):
        game = default_game(stars=5, fleets=1)
        player = game.players.first()
        fleet = player.fleets.first()
        target_star = game.stars.exclude(id=player.homeworld_id).first()
        order = FleetOrders.objects.create(
            game=game,
            fleet=fleet,
            order_type='REMOTEMINE',
            target_star=target_star,
            repeat=False,
        )
        user, _ = get_default_user()
        client = Client()
        client.force_login(user)

        response = client.post(
            reverse('dj4xol:toggle_fleet_order_repeat', args=[game.short_id, order.short_id])
        )
        self.assertEqual(response.status_code, 302)
        order.refresh_from_db()
        self.assertTrue(order.repeat)

    def test_intercept_order_wormhole_speed_is_clamped_to_13(self):
        game = default_game(stars=5, fleets=2)
        player = game.players.first()
        fleet = player.fleets.first()
        target_fleet = player.fleets.exclude(id=fleet.id).first()
        fleet.has_wormhole_drive = True
        fleet.save(update_fields=['has_wormhole_drive'])
        user, _ = get_default_user()
        client = Client()
        client.force_login(user)

        response = client.post(
            reverse('dj4xol:add_fleet_order', args=[game.short_id]),
            {
                'fleet': fleet.short_id,
                'order_type': 'INTERCEPT',
                'target_fleet': target_fleet.short_id,
                'warpfactor': '14',
            }
        )
        self.assertEqual(response.status_code, 302)
        order = fleet.orders.filter(order_type='INTERCEPT').first()
        self.assertIsNotNone(order)
        self.assertEqual(order.warpfactor, 13)

    def test_patrol_order_wormhole_intercept_speed_is_clamped_to_13(self):
        game = default_game(stars=5, fleets=1)
        player = game.players.first()
        fleet = player.fleets.first()
        target_star = game.stars.exclude(id=player.homeworld_id).first()
        fleet.has_wormhole_drive = True
        fleet.save(update_fields=['has_wormhole_drive'])
        user, _ = get_default_user()
        client = Client()
        client.force_login(user)

        response = client.post(
            reverse('dj4xol:add_fleet_order', args=[game.short_id]),
            {
                'fleet': fleet.short_id,
                'order_type': 'PATROL',
                'patrol_target': 'star:%s' % target_star.short_id,
                'target_star': target_star.short_id,
                'intercept_speed': '14',
                'patrol_radius': '15',
            }
        )
        self.assertEqual(response.status_code, 302)
        order = fleet.orders.filter(order_type='PATROL').first()
        self.assertIsNotNone(order)
        self.assertEqual(order.intercept_speed, 13)

    def test_bomb_order_creation_persists_bomb_until_parameter(self):
        game = default_game(stars=5, fleets=1)
        player = game.players.first()
        fleet = player.fleets.first()
        fleet.has_bombs = 'CONVENTIONAL'
        fleet.save(update_fields=['has_bombs'])
        target_star = game.stars.exclude(id=player.homeworld_id).first()
        user, _ = get_default_user()
        client = Client()
        client.force_login(user)

        response = client.post(
            reverse('dj4xol:add_fleet_order', args=[game.short_id]),
            {
                'fleet': fleet.short_id,
                'order_type': 'BOMB',
                'bomb_target': target_star.short_id,
                'bomb_until': 'DEFENSES_ZERO',
            }
        )
        self.assertEqual(response.status_code, 302)
        order = fleet.orders.filter(order_type='BOMB').first()
        self.assertIsNotNone(order)
        self.assertEqual(order.bomb_until, 'DEFENSES_ZERO')

    def test_bomb_order_creation_accepts_once_completion(self):
        game = default_game(stars=5, fleets=1)
        player = game.players.first()
        fleet = player.fleets.first()
        fleet.has_bombs = 'CONVENTIONAL'
        fleet.save(update_fields=['has_bombs'])
        target_star = game.stars.exclude(id=player.homeworld_id).first()
        user, _ = get_default_user()
        client = Client()
        client.force_login(user)

        response = client.post(
            reverse('dj4xol:add_fleet_order', args=[game.short_id]),
            {
                'fleet': fleet.short_id,
                'order_type': 'BOMB',
                'bomb_target': target_star.short_id,
                'bomb_until': 'ONCE',
            }
        )
        self.assertEqual(response.status_code, 302)
        order = fleet.orders.filter(order_type='BOMB').first()
        self.assertIsNotNone(order)
        self.assertEqual(order.bomb_until, 'ONCE')

    def test_remotemine_order_creation_persists_mine_until_full_parameter(self):
        game = default_game(stars=5, fleets=1)
        player = game.players.first()
        fleet = player.fleets.first()
        fleet.has_miners = 'SMALL'
        fleet.save(update_fields=['has_miners'])
        target_star = game.stars.exclude(id=player.homeworld_id).first()
        user, _ = get_default_user()
        client = Client()
        client.force_login(user)

        response = client.post(
            reverse('dj4xol:add_fleet_order', args=[game.short_id]),
            {
                'fleet': fleet.short_id,
                'order_type': 'REMOTEMINE',
                'remotemine_target': target_star.short_id,
                'mine_until_full': '0',
            }
        )
        self.assertEqual(response.status_code, 302)
        order = fleet.orders.filter(order_type='REMOTEMINE').first()
        self.assertIsNotNone(order)
        self.assertFalse(order.mine_until_full)
