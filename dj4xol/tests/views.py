import re
import json
import uuid
from datetime import timedelta
from unittest.mock import patch

from django.core import mail
from django.test import TestCase, Client
from django.test.utils import override_settings
from django.urls import reverse
from django.contrib.auth.models import User
from django.utils import timezone
from ..models import (
    Account,
    DiplomaticContract,
    Fleet,
    FleetOrders,
    Game,
    GameMessage,
    GameInvitation,
    HullDesign,
    Player,
    PlayerDiplomaticStance,
    PlayerTechnologyGrant,
    ProductionOrder,
    Report,
    ResearchCategory,
    Salvage,
    Anomaly,
    PlayerStarMarker,
    ServerRace,
    ServerRaceType,
    ServerSettings,
    Technology,
)
from ..forms import JoinGameForm, NewGameForm
from ..research import (
    ensure_player_research_rows,
    get_player_tech_effects,
    get_player_unlocked_technologies,
)
from ..diplomacy import (
    combat_chance_modifier_percent,
    combat_chance_percent,
    combat_chance_with_diplomacy_percent,
    combat_readiness_multiplier,
)
from ..diplomatic_contracts import (
    accept_contract,
    apply_world_resource_delivery,
    decline_contract,
    extend_contract,
    format_contract_statement,
    format_contract_summary,
    grant_player_technology,
    mark_countered,
    refresh_contract_integrity,
    vague_threat_phrase,
    VAGUE_THREAT_PHRASES,
)
from ..play_cli_web import execute_browser_command
from ..views import _diplomacy_parse_contract
from ..turn import (
    GameTurn,
    format_basic_hidden_salvage_name,
    format_basic_unknown_fleet_name,
)
from ..factory import GameFactory
from ._util import default_game, get_default_user, get_default_race, get_default_race_type


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
        self.assertContains(response, 'Copyright &copy; Bradley Gray 2026')

    def test_staff_home_shows_server_settings_action(self):
        user, _ = get_default_user()
        user.is_staff = True
        user.save(update_fields=['is_staff'])
        client = Client()
        client.force_login(user)

        response = client.get(reverse('dj4xol:index'))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'Server Settings')
        self.assertContains(response, 'Help Page Editor')

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
    def test_message_history_uses_panel_layout(self):
        game = default_game(stars=5)
        player = game.players.first()
        GameMessage.objects.create(game=game, player=player, year=game.year, message="Panel test")
        user = player.account.django_user
        client = Client()
        client.force_login(user)

        response = client.get(reverse('dj4xol:message_history', args=[game.short_id]))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'message-history-columns')
        self.assertContains(response, 'data-panel="filters"')
        self.assertContains(response, 'data-panel="messages"')

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
        messages = player.messages.order_by('-year', '-priority', '-id')[:1000]
        self.assertEqual(len(messages), 1000)

    def test_message_history_orders_priority_first_within_year(self):
        game = default_game(stars=5)
        player = game.players.first()
        GameMessage.objects.create(
            game=game,
            player=player,
            year=2402,
            priority=False,
            message="Normal current year",
        )
        priority_msg = GameMessage.objects.create(
            game=game,
            player=player,
            year=2402,
            priority=True,
            message="Priority current year",
        )
        older_priority = GameMessage.objects.create(
            game=game,
            player=player,
            year=2401,
            priority=True,
            message="Priority older year",
        )
        user = player.account.django_user
        client = Client()
        client.force_login(user)

        response = client.get(reverse('dj4xol:message_history', args=[game.short_id]))

        self.assertEqual(response.status_code, 200)
        page_messages = list(response.context['page_obj'].object_list[:3])
        self.assertEqual(page_messages[0].id, priority_msg.id)
        self.assertEqual(page_messages[1].year, 2402)
        self.assertEqual(page_messages[1].priority, False)
        self.assertEqual(page_messages[2].id, older_priority.id)

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

    def test_production_costs_panel_starts_hidden_with_costs_label(self):
        game = default_game(stars=5)
        player = game.players.first()
        homeworld = player.homeworld
        user, _ = get_default_user()
        client = Client()
        client.force_login(user)

        response = client.get(
            reverse('dj4xol:game', args=[game.short_id]),
            {'x': homeworld.x, 'y': homeworld.y, 'sel': homeworld.short_id},
        )

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'id="production-costs-panel"', html=False)
        self.assertContains(response, 'order-params--costs order-params--columns is-empty', html=False)
        self.assertContains(response, 'Select a production item to view costs.')

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
        self.assertContains(response, 'Allow Player Public Races')
        self.assertContains(response, 'Enable Spectator Mode')
        self.assertContains(response, 'Enable Profanity Filter')
        self.assertContains(response, 'Profanity Whitelist')
        self.assertContains(response, 'Profanity Blacklist')
        self.assertContains(response, 'Send Verification Emails')

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
                'allow_player_public_races': 'on',
                'enable_spectator_mode': 'on',
                'max_diplomatic_requests_per_race_per_turn': '3',
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
        self.assertEqual(ServerSettings.get('allow_player_public_races'), 'True')
        self.assertEqual(ServerSettings.get('enable_spectator_mode'), 'True')
        self.assertEqual(ServerSettings.get('max_diplomatic_requests_per_race_per_turn'), '3')
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
                'allow_player_public_races': '',
                'enable_spectator_mode': '',
                'max_diplomatic_requests_per_race_per_turn': '2',
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

    def test_staff_can_send_verification_emails_to_unverified_accounts(self):
        self.user.is_staff = True
        self.user.save(update_fields=['is_staff'])
        ServerSettings.objects.update_or_create(
            key='enable_email',
            defaults={
                'value': 'True',
                'description': 'Enable email',
            }
        )
        ServerSettings.objects.update_or_create(
            key='server_url',
            defaults={
                'value': 'https://example.test',
                'description': 'Server URL',
            }
        )

        unverified_user = User.objects.create_user(
            'unverifiedpilot', 'unverified@example.com', 'pass1234'
        )
        unverified_account = Account.objects.create(
            django_user=unverified_user,
            alias='unverifiedpilot',
            email='unverified@example.com',
            full_name='Unverified Pilot',
        )
        verified_user = User.objects.create_user(
            'verifiedpilot', 'verified@example.com', 'pass1234'
        )
        verified_account = Account.objects.create(
            django_user=verified_user,
            alias='verifiedpilot',
            email='verified@example.com',
            full_name='Verified Pilot',
            email_verified=True,
        )
        no_email_user = User.objects.create_user(
            'noemailpilot', 'noemail@example.com', 'pass1234'
        )
        Account.objects.create(
            django_user=no_email_user,
            alias='noemailpilot',
            email='',
            full_name='No Email Pilot',
        )

        response = self.client.post(
            reverse('dj4xol:send_unverified_email_verifications'),
            follow=True,
        )

        self.assertEqual(response.status_code, 200)
        self.assertContains(
            response,
            'Sent verification email to 1 unverified account.',
        )
        self.assertEqual(len(mail.outbox), 1)
        self.assertEqual(mail.outbox[0].to, ['unverified@example.com'])
        self.assertIn(
            unverified_account.email_verification_key,
            mail.outbox[0].body,
        )
        self.assertNotIn(
            verified_account.email_verification_key,
            mail.outbox[0].body,
        )


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

    def test_fleet_detail_shows_in_orbit_when_stationary_at_star(self):
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
        self.assertContains(response, 'In orbit')
        self.assertNotContains(response, 'Travelling at:')
        self.assertNotContains(response, 'Heading:')

    def test_fleet_detail_shows_stopped_when_stationary_in_empty_space(self):
        game = default_game(stars=5, fleets=1)
        player = game.players.first()
        fleet = player.fleets.first()
        user, _ = get_default_user()
        client = Client()
        client.force_login(user)

        empty_coords = None
        for x in range(int(game.map_size_x)):
            for y in range(int(game.map_size_y)):
                if game.stars.filter(x=x, y=y).exists():
                    continue
                if x == fleet.x and y == fleet.y:
                    continue
                empty_coords = (x, y)
                break
            if empty_coords:
                break
        self.assertIsNotNone(empty_coords)

        fleet.x, fleet.y = empty_coords
        fleet.save(update_fields=['x', 'y'])

        response = client.get(
            reverse('dj4xol:game', args=[game.short_id]),
            {'x': fleet.x, 'y': fleet.y, 'sel': fleet.short_id},
        )
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'Stopped')
        self.assertNotContains(response, 'Travelling at:')
        self.assertNotContains(response, 'Heading:')

    def test_fleet_detail_moving_summary_omits_colons(self):
        game = default_game(stars=5, fleets=1)
        player = game.players.first()
        fleet = player.fleets.first()
        user, _ = get_default_user()
        client = Client()
        client.force_login(user)
        fleet.travel_warp = 6
        fleet.heading = 247.5
        fleet.save(update_fields=['travel_warp', 'heading'])

        response = client.get(
            reverse('dj4xol:game', args=[game.short_id]),
            {'x': fleet.x, 'y': fleet.y, 'sel': fleet.short_id},
        )
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'Travelling at Warp 6 | Heading ')
        self.assertNotContains(response, 'Travelling at:')
        self.assertNotContains(response, 'Heading:')

    def test_fleet_detail_moving_summary_shows_warp_advantage(self):
        game = default_game(stars=5, fleets=1)
        player = game.players.first()
        fleet = player.fleets.first()
        user, _ = get_default_user()
        client = Client()
        client.force_login(user)
        fleet.travel_warp = 5
        fleet.warp_advantage = 0.9
        fleet.heading = 247.5
        fleet.save(update_fields=['travel_warp', 'warp_advantage', 'heading'])

        response = client.get(
            reverse('dj4xol:game', args=[game.short_id]),
            {'x': fleet.x, 'y': fleet.y, 'sel': fleet.short_id},
        )
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'Travelling at Warp 5.9 | Heading ')

    def test_star_detail_factories_tooltip_shows_manufacturing_multiplier(self):
        game = default_game(stars=5, fleets=0)
        player = game.players.first()
        player.race_type.manufacturing_multiplier = 1.2
        player.race_type.save(update_fields=['manufacturing_multiplier'])
        target = player.homeworld
        target.factories = 5
        target.colonists = 5000
        target.save(update_fields=['factories', 'colonists'])
        user, _ = get_default_user()
        client = Client()
        client.force_login(user)

        response = client.get(
            reverse('dj4xol:game', args=[game.short_id]),
            {'x': target.x, 'y': target.y, 'sel': target.short_id},
        )
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'BP/Year (+20%)')


@override_settings(EMAIL_BACKEND='django.core.mail.backends.locmem.EmailBackend')
class TestProfileView(TestCase):
    def setUp(self):
        ServerSettings.objects.update_or_create(
            key='enable_email',
            defaults={'value': 'True', 'description': 'Enable outbound email'},
        )
        ServerSettings.objects.update_or_create(
            key='server_url',
            defaults={'value': 'https://example.test', 'description': 'Server URL'},
        )

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

    def test_profile_can_delete_owned_game(self):
        game = default_game(stars=5)
        user, account = get_default_user()
        game.owner = account
        game.save(update_fields=['owner'])
        client = Client()
        client.force_login(user)

        response = client.post(reverse('dj4xol:delete_owned_game', args=[game.short_id]))

        self.assertEqual(response.status_code, 302)
        self.assertEqual(response.url, reverse('dj4xol:profile'))
        self.assertFalse(Game.objects.filter(id=game.id).exists())

    def test_profile_delete_owned_game_emails_other_players(self):
        game = default_game(stars=6, fleets=0)
        owner_user, owner_account = get_default_user()
        owner_player = game.players.first()
        owner_player.account = owner_account
        owner_player.save(update_fields=['account'])
        game.owner = owner_account
        game.save(update_fields=['owner'])

        other_user = User.objects.create_user('delete_notify_other', 'other@example.com', 'pw')
        other_account = Account.objects.create(
            django_user=other_user,
            alias='OTHR',
            email='other@example.com',
            full_name='Other Player',
            email_verified=True,
            email_game_updates=True,
            email_game_rollups_per_day=1,
        )
        Player.objects.create(
            game=game,
            account=other_account,
            name='Other Race',
            plural_name='Other Races',
            race_type=get_default_race_type(),
        )

        silent_user = User.objects.create_user('delete_notify_silent', 'silent@example.com', 'pw')
        silent_account = Account.objects.create(
            django_user=silent_user,
            alias='SLNT',
            email='silent@example.com',
            full_name='Silent Player',
            email_verified=True,
            email_game_updates=False,
            email_game_rollups_per_day=0,
        )
        Player.objects.create(
            game=game,
            account=silent_account,
            name='Silent Race',
            plural_name='Silent Races',
            race_type=get_default_race_type(),
        )

        client = Client()
        client.force_login(owner_user)

        response = client.post(reverse('dj4xol:delete_owned_game', args=[game.short_id]))

        self.assertEqual(response.status_code, 302)
        self.assertFalse(Game.objects.filter(id=game.id).exists())
        self.assertEqual(len(mail.outbox), 1)
        message = mail.outbox[0]
        self.assertEqual(message.to, ['other@example.com'])
        self.assertIn('%s was deleted' % game.name, message.subject)
        self.assertIn('deleted by its owner', message.body)
        self.assertIn(owner_account.alias, message.body)


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

    def test_join_game_redirects_to_new_player_homeworld(self):
        game = default_game(stars=8)
        game.joinable = True
        game.save(update_fields=['joinable'])

        joiner_user = User.objects.create_user('joiner_user', 'joiner@example.com', 'pass')
        joiner_account = Account.objects.create(django_user=joiner_user)
        race = ServerRace.objects.create(
            name='JoinerRace',
            plural_name='JoinerRaces',
            race_type=get_default_race_type(),
            owner=joiner_account,
        )

        client = Client()
        client.force_login(joiner_user)
        response = client.post(
            reverse('dj4xol:join_game', args=[game.short_id]),
            {'race': str(race.id)},
        )
        self.assertEqual(response.status_code, 302)

        player = game.players.filter(account=joiner_account).first()
        self.assertIsNotNone(player)
        self.assertIsNotNone(player.homeworld)

        game_url = reverse('dj4xol:game', args=[game.short_id])
        self.assertTrue(response.url.startswith(game_url + '?'))
        self.assertIn('x=%s' % int(player.homeworld.x), response.url)
        self.assertIn('y=%s' % int(player.homeworld.y), response.url)
        self.assertIn('sel=%s' % player.homeworld.short_id, response.url)

    @override_settings(EMAIL_BACKEND='django.core.mail.backends.locmem.EmailBackend')
    def test_join_game_sends_owner_email_for_public_join(self):
        ServerSettings.objects.update_or_create(
            key='enable_email',
            defaults={'value': 'True', 'description': 'Enable outbound email'},
        )
        ServerSettings.objects.update_or_create(
            key='server_url',
            defaults={'value': 'https://example.test', 'description': 'Server URL'},
        )
        game = default_game(stars=8)
        game.joinable = True
        game.save(update_fields=['joinable'])
        owner = game.owner
        owner.email = 'owner@example.test'
        owner.email_verified = True
        owner.email_game_updates = True
        owner.save(update_fields=['email', 'email_verified', 'email_game_updates'])

        joiner_user = User.objects.create_user('join_public_user', 'join-public@example.com', 'pass')
        joiner_account = Account.objects.create(
            django_user=joiner_user,
            alias='JoinPublic',
            full_name='Join Public',
            email='join-public@example.com',
        )
        race = ServerRace.objects.create(
            name='JoinPublicRace',
            plural_name='JoinPublicRaces',
            race_type=get_default_race_type(),
            owner=joiner_account,
        )

        client = Client()
        client.force_login(joiner_user)
        response = client.post(
            reverse('dj4xol:join_game', args=[game.short_id]),
            {'race': str(race.id)},
        )

        self.assertEqual(response.status_code, 302)
        self.assertEqual(len(mail.outbox), 1)
        message = mail.outbox[0]
        self.assertEqual(message.to, ['owner@example.test'])
        self.assertIn('Account JoinPublic has joined your game', message.body)
        self.assertIn('Join source: public joinability', message.body)

    @override_settings(EMAIL_BACKEND='django.core.mail.backends.locmem.EmailBackend')
    def test_join_game_sends_owner_email_for_invited_join(self):
        ServerSettings.objects.update_or_create(
            key='enable_email',
            defaults={'value': 'True', 'description': 'Enable outbound email'},
        )
        ServerSettings.objects.update_or_create(
            key='server_url',
            defaults={'value': 'https://example.test', 'description': 'Server URL'},
        )
        game = default_game(stars=8)
        game.joinable = False
        game.save(update_fields=['joinable'])
        owner = game.owner
        owner.email = 'owner@example.test'
        owner.email_verified = True
        owner.email_game_updates = True
        owner.save(update_fields=['email', 'email_verified', 'email_game_updates'])

        joiner_user = User.objects.create_user('join_invited_user', 'join-invited@example.com', 'pass')
        joiner_account = Account.objects.create(
            django_user=joiner_user,
            alias='JoinInvited',
            full_name='Join Invited',
            email='join-invited@example.com',
        )
        GameInvitation.objects.create(game=game, account=joiner_account)
        race = ServerRace.objects.create(
            name='JoinInvitedRace',
            plural_name='JoinInvitedRaces',
            race_type=get_default_race_type(),
            owner=joiner_account,
        )

        client = Client()
        client.force_login(joiner_user)
        response = client.post(
            reverse('dj4xol:join_game', args=[game.short_id]),
            {'race': str(race.id)},
        )

        self.assertEqual(response.status_code, 302)
        self.assertEqual(len(mail.outbox), 1)
        message = mail.outbox[0]
        self.assertEqual(message.to, ['owner@example.test'])
        self.assertIn('Account JoinInvited has joined your game', message.body)
        self.assertIn('Join source: invitation', message.body)


class TestRaceCreationView(TestCase):
    def setUp(self):
        self.user, self.account = get_default_user()
        self.client = Client()
        self.client.force_login(self.user)
        self.race_type = get_default_race_type()
        self.race_type.enabled = True
        self.race_type.save(update_fields=['enabled'])

    def _race_payload(self, name):
        return {
            'name': name,
            'plural_name': '%sP' % name[:15],
            'homeworld_name': '',
            'race_type': self.race_type.code,
            'description': 'Test race notes',
            'gravity_center': '1.0',
            'gravity_width': '1.0',
            'temperature_center': '1.0',
            'temperature_width': '1.0',
            'radiation_center': '1.0',
            'radiation_width': '1.0',
            'starting_tech_level': '0',
            'starting_colonists': '20',
            'starting_mines': '4',
            'starting_factories': '2',
            'starting_labs': '1',
            'starting_shipyards': '1',
            'starting_fleets': '2',
        }

    def test_create_race_hides_public_checkbox_for_non_staff_by_default(self):
        response = self.client.get(reverse('dj4xol:create_race'))
        self.assertEqual(response.status_code, 200)
        self.assertNotContains(response, 'id="id_public"')

    def test_create_race_shows_race_type_browser_link(self):
        response = self.client.get(reverse('dj4xol:create_race'))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, reverse('dj4xol:help_race_types'))
        self.assertContains(response, 'Browse')

    def test_create_race_includes_race_type_behavior_config_and_state_script(self):
        self.race_type.ignores_gravity = True
        self.race_type.race_creation_points_balance = -6.5
        self.race_type.description = 'A disciplined specialist race.'
        self.race_type.save(update_fields=['ignores_gravity', 'race_creation_points_balance', 'description'])

        response = self.client.get(reverse('dj4xol:create_race'))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'id="race-type-behaviors-json"')
        self.assertContains(response, '"%s"' % self.race_type.code)
        self.assertContains(response, '"ignores_gravity": true')
        self.assertContains(response, '"race_creation_points_balance": -6.5')
        self.assertContains(response, '"description": "A disciplined specialist race."')
        self.assertContains(response, "dj4xol/js/race_form_state.js")

    def test_create_race_renders_race_type_description_placeholder(self):
        response = self.client.get(reverse('dj4xol:create_race'))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'id="race-type-description"')

    def test_create_race_marks_inline_race_type_points_target(self):
        response = self.client.get(reverse('dj4xol:create_race'))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'data-race-type-browser-link="1"')

    def test_create_race_prefills_race_type_from_query_param(self):
        alt_type = ServerRaceType.objects.create(
            code='RSEL',
            name='Selectable',
            enabled=True,
            description='',
        )
        response = self.client.get(
            reverse('dj4xol:create_race'),
            {'race_type': alt_type.code},
        )
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'option value="%s" selected' % alt_type.code, html=False)

    def test_create_race_has_no_blank_race_type_option(self):
        response = self.client.get(reverse('dj4xol:create_race'))
        self.assertEqual(response.status_code, 200)
        self.assertNotContains(response, '---------')

    def test_create_race_staff_public_detaches_owner(self):
        self.user.is_staff = True
        self.user.save(update_fields=['is_staff'])

        response = self.client.get(reverse('dj4xol:create_race'))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'id="id_public"')

        payload = self._race_payload('AdminPublicRace')
        payload['public'] = 'on'
        response = self.client.post(reverse('dj4xol:create_race'), payload)
        self.assertEqual(response.status_code, 302)

        race = ServerRace.objects.get(name='AdminPublicRace')
        self.assertTrue(race.public)
        self.assertIsNone(race.owner)

    def test_create_race_player_public_enabled_keeps_owner(self):
        ServerSettings.objects.update_or_create(
            key='allow_player_public_races',
            defaults={
                'value': 'True',
                'description': 'Allow players to publish public races',
            },
        )
        response = self.client.get(reverse('dj4xol:create_race'))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'id="id_public"')

        payload = self._race_payload('PlayerPublicRace')
        payload['public'] = 'on'
        response = self.client.post(reverse('dj4xol:create_race'), payload)
        self.assertEqual(response.status_code, 302)

        race = ServerRace.objects.get(name='PlayerPublicRace')
        self.assertTrue(race.public)
        self.assertEqual(race.owner, self.account)

    def test_create_race_ignored_habitability_posts_save_as_defaults(self):
        ignored_type = ServerRaceType.objects.create(
            code='IGNG',
            name='Ignored Gravity',
            enabled=True,
            ignores_gravity=True,
            description='',
        )
        payload = self._race_payload('IgnoreGrav')
        payload['race_type'] = ignored_type.code
        payload['gravity_center'] = '1.70'
        payload['gravity_width'] = '0.20'

        response = self.client.post(reverse('dj4xol:create_race'), payload)

        self.assertEqual(response.status_code, 302)
        race = ServerRace.objects.get(name='IgnoreGrav')
        self.assertEqual(race.gravity_center, 1.0)
        self.assertEqual(race.gravity_width, 1.0)

    def test_edit_race_prefills_form_and_shows_warning(self):
        race = ServerRace.objects.create(
            owner=self.account,
            name='Editable Race',
            plural_name='Editable Races',
            race_type=self.race_type,
            description='Before',
        )

        response = self.client.get(reverse('dj4xol:edit_race', args=[race.short_id]))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'Edit Custom Race')
        self.assertContains(response, 'players already using this race in active games keep the stats they copied when they joined')
        self.assertContains(response, 'value="Editable Race"', html=False)

    def test_edit_race_updates_owned_race(self):
        race = ServerRace.objects.create(
            owner=self.account,
            name='Original Race',
            plural_name='Original Races',
            race_type=self.race_type,
        )
        payload = self._race_payload('Updated Race')

        response = self.client.post(reverse('dj4xol:edit_race', args=[race.short_id]), payload)

        self.assertEqual(response.status_code, 302)
        self.assertEqual(response.url, reverse('dj4xol:profile'))
        race.refresh_from_db()
        self.assertEqual(race.name, 'Updated Race')
        self.assertEqual(race.plural_name, 'Updated RaceP')

    def test_delete_race_removes_owned_race(self):
        race = ServerRace.objects.create(
            owner=self.account,
            name='Disposable Race',
            plural_name='Disposable Races',
            race_type=self.race_type,
        )

        response = self.client.post(reverse('dj4xol:delete_race', args=[race.short_id]))

        self.assertEqual(response.status_code, 302)
        self.assertEqual(response.url, reverse('dj4xol:profile'))
        self.assertFalse(ServerRace.objects.filter(pk=race.pk).exists())


class TestOnboardingRaceView(TestCase):
    def setUp(self):
        self.user, self.account = get_default_user()
        self.account.onboarding_step = Account.ONBOARDING_STEP_RACE
        self.account.save(update_fields=['onboarding_step'])
        self.client = Client()
        self.client.force_login(self.user)
        self.race_type = get_default_race_type()
        self.race_type.enabled = True
        self.race_type.save(update_fields=['enabled'])

    def test_onboarding_race_hides_skip_without_public_server_races(self):
        response = self.client.get(reverse('dj4xol:onboarding_race'))
        self.assertEqual(response.status_code, 200)
        self.assertNotContains(response, 'Skip for now')

    def test_onboarding_race_shows_skip_with_public_server_races(self):
        ServerRace.objects.create(
            name='ServerStarter',
            plural_name='ServerStarters',
            race_type=self.race_type,
            public=True,
            owner=None,
        )
        response = self.client.get(reverse('dj4xol:onboarding_race'))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'Skip for now')

    def test_onboarding_race_shows_race_type_browser_link(self):
        response = self.client.get(reverse('dj4xol:onboarding_race'))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, reverse('dj4xol:help_race_types'))
        self.assertContains(response, 'Browse')

    def test_onboarding_race_includes_race_type_behavior_config_and_state_script(self):
        self.race_type.ignores_temperature = True
        self.race_type.description = 'Optimised for rapid frontier expansion.'
        self.race_type.save(update_fields=['ignores_temperature', 'description'])

        response = self.client.get(reverse('dj4xol:onboarding_race'))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'id="race-type-behaviors-json"')
        self.assertContains(response, '"%s"' % self.race_type.code)
        self.assertContains(response, '"ignores_temperature": true')
        self.assertContains(response, '"description": "Optimised for rapid frontier expansion."')
        self.assertContains(response, "dj4xol/js/race_form_state.js")

    def test_onboarding_race_skip_marks_onboarding_complete(self):
        self.account.onboarding_step = Account.ONBOARDING_STEP_RACE
        self.account.save(update_fields=['onboarding_step'])
        ServerRace.objects.create(
            name='ServerStarter',
            plural_name='ServerStarters',
            race_type=self.race_type,
            public=True,
            owner=None,
        )

        response = self.client.post(reverse('dj4xol:onboarding_race'), {'action': 'skip'})

        self.assertEqual(response.status_code, 302)
        self.assertEqual(response.url, reverse('dj4xol:index'))
        self.account.refresh_from_db()
        self.assertEqual(self.account.onboarding_step, Account.ONBOARDING_STEP_COMPLETE)


class TestRaceTypeHelpView(TestCase):
    def setUp(self):
        self.user, self.account = get_default_user()
        self.client = Client()
        self.client.force_login(self.user)
        self.race_type = get_default_race_type()
        self.race_type.enabled = True
        self.race_type.save(update_fields=['enabled'])

    def test_help_race_types_renders_single_panel_with_effects(self):
        self.race_type.diplomacy_multiplier = 1.2
        self.race_type.scan_multiplier = 0.8
        self.race_type.race_creation_points_balance = -4.0
        self.race_type.save(update_fields=['diplomacy_multiplier', 'scan_multiplier', 'race_creation_points_balance'])

        response = self.client.get(
            reverse('dj4xol:help_race_types'),
            {'race_type': self.race_type.code},
        )

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'Race Type Effects')
        self.assertContains(response, self.race_type.name)
        self.assertContains(response, 'Diplomacy')
        self.assertContains(response, '+20%')
        self.assertContains(response, 'Scanners')
        self.assertContains(response, '-20%')
        self.assertContains(response, 'Race Balance Points')
        self.assertContains(response, '-4.00 pts')
        self.assertContains(response, 'Race Traits')
        self.assertContains(response, 'Special Technologies')

    def test_help_race_types_lists_matching_race_gated_technologies_for_selected_type(self):
        sci = ServerRaceType.objects.get(code='SCI')

        response = self.client.get(
            reverse('dj4xol:help_race_types'),
            {'race_type': sci.code},
        )

        self.assertEqual(response.status_code, 200)
        rows = response.context['special_technology_rows']
        names = [row['name'] for row in rows]
        self.assertIn('Mini Cloak', names)
        self.assertIn('Prototype Wormhole Drive', names)

    def test_help_race_types_joat_lists_cloak_technologies_when_not_no_stealth(self):
        joat = ServerRaceType.objects.get(code='JOAT')

        response = self.client.get(
            reverse('dj4xol:help_race_types'),
            {'race_type': joat.code},
        )

        self.assertEqual(response.status_code, 200)
        names = [row['name'] for row in response.context['special_technology_rows']]
        self.assertNotIn('Chameleon Cloak', names)
        self.assertNotIn('Advanced Cloak', names)
        self.assertNotIn('Tactical Cloak', names)
        self.assertNotIn('Super Cloak', names)
        self.assertNotIn('Prototype Cloak', names)
        self.assertNotIn('Standard Cloak', names)
        self.assertNotIn('Advanced Cloak Projector', names)

    def test_help_race_types_no_stealth_race_shows_civilian_cloaks_as_excluded(self):
        breeders = ServerRaceType.objects.get(code='BRED')

        response = self.client.get(
            reverse('dj4xol:help_race_types'),
            {'race_type': breeders.code},
        )

        self.assertEqual(response.status_code, 200)
        rows = response.context['special_technology_rows']
        names = [row['name'] for row in rows]
        self.assertNotIn('Chameleon Cloak', names)
        self.assertNotIn('Advanced Cloak', names)
        self.assertNotIn('Tactical Cloak', names)
        self.assertNotIn('Super Cloak', names)
        prototype = next(row for row in rows if row['name'] == 'Prototype Cloak')
        standard = next(row for row in rows if row['name'] == 'Standard Cloak')
        projector = next(row for row in rows if row['name'] == 'Advanced Cloak Projector')
        self.assertTrue(prototype['is_excluded'])
        self.assertTrue(standard['is_excluded'])
        self.assertTrue(projector['is_excluded'])

    def test_help_race_types_war_shows_not_war_technologies_as_excluded(self):
        war = ServerRaceType.objects.get(code='WAR')

        response = self.client.get(
            reverse('dj4xol:help_race_types'),
            {'race_type': war.code},
        )

        self.assertEqual(response.status_code, 200)
        rows = response.context['special_technology_rows']
        frigate = next(row for row in rows if row['name'] == 'Frigate Hull')
        self.assertTrue(frigate['is_excluded'])
        self.assertContains(response, 'race-type-tech-item--excluded')

    def test_help_race_types_war_lists_war_cloaks_and_excludes_civilian_cloaks(self):
        war = ServerRaceType.objects.get(code='WAR')

        response = self.client.get(
            reverse('dj4xol:help_race_types'),
            {'race_type': war.code},
        )

        self.assertEqual(response.status_code, 200)
        rows = response.context['special_technology_rows']
        names = [row['name'] for row in rows]
        self.assertIn('Chameleon Cloak', names)
        self.assertIn('Advanced Cloak', names)
        self.assertIn('Tactical Cloak', names)
        self.assertIn('Super Cloak', names)
        prototype = next(row for row in rows if row['name'] == 'Prototype Cloak')
        standard = next(row for row in rows if row['name'] == 'Standard Cloak')
        projector = next(row for row in rows if row['name'] == 'Advanced Cloak Projector')
        self.assertTrue(prototype['is_excluded'])
        self.assertTrue(standard['is_excluded'])
        self.assertTrue(projector['is_excluded'])

    def test_help_race_types_use_type_link_returns_to_create_race(self):
        response = self.client.get(
            reverse('dj4xol:help_race_types'),
            {'return_to': 'create_race', 'race_type': self.race_type.code},
        )

        self.assertEqual(response.status_code, 200)
        self.assertContains(
            response,
            '%s?race_type=%s' % (reverse('dj4xol:create_race'), self.race_type.code),
        )

    def test_help_race_types_without_return_to_shows_back_to_help_only(self):
        response = self.client.get(
            reverse('dj4xol:help_race_types'),
            {'race_type': self.race_type.code},
        )

        self.assertEqual(response.status_code, 200)
        self.assertContains(
            response,
            '%s' % reverse('dj4xol:help_index'),
        )
        self.assertContains(response, 'Back to Help')
        self.assertNotContains(response, 'Use This Type')
        self.assertNotContains(response, 'Back to Race Creation')

    def test_help_race_types_orders_choices_by_display_order_then_name(self):
        later = ServerRaceType.objects.create(
            code='ZZZZ',
            name='Later',
            display_order=100,
            enabled=True,
            description='',
        )
        earlier = ServerRaceType.objects.create(
            code='AAAA',
            name='Earlier',
            display_order=0,
            enabled=True,
            description='',
        )
        response = self.client.get(reverse('dj4xol:help_race_types'))
        self.assertEqual(response.status_code, 200)
        content = response.content.decode('utf-8')
        self.assertLess(content.index('value="%s"' % earlier.code), content.index('value="%s"' % later.code))

    def test_create_race_orders_race_types_by_display_order_then_name(self):
        later = ServerRaceType.objects.create(
            code='ZZZZ',
            name='Later',
            display_order=100,
            enabled=True,
            description='',
        )
        earlier = ServerRaceType.objects.create(
            code='AAAA',
            name='Earlier',
            display_order=0,
            enabled=True,
            description='',
        )
        response = self.client.get(reverse('dj4xol:create_race'))
        self.assertEqual(response.status_code, 200)
        content = response.content.decode('utf-8')
        self.assertLess(content.index('value="%s"' % earlier.code), content.index('value="%s"' % later.code))

    def test_help_race_types_use_type_link_returns_to_onboarding_race(self):
        response = self.client.get(
            reverse('dj4xol:help_race_types'),
            {'return_to': 'onboarding_race', 'race_type': self.race_type.code},
        )

        self.assertEqual(response.status_code, 200)
        self.assertContains(
            response,
            '%s?race_type=%s' % (reverse('dj4xol:onboarding_race'), self.race_type.code),
        )


class TestRaceChoiceOrdering(TestCase):
    def setUp(self):
        self.user, self.account = get_default_user()
        other_user = User.objects.create_user('other_user', 'other@example.com', 'pass')
        self.other_account = Account.objects.create(django_user=other_user)
        self.race_type = get_default_race_type()

    def test_race_choices_show_suffixes_and_order(self):
        mine = ServerRace.objects.create(
            name='ZuluMine',
            plural_name='ZuluMines',
            race_type=self.race_type,
            owner=self.account,
            public=False,
        )
        server = ServerRace.objects.create(
            name='AlphaServer',
            plural_name='AlphaServers',
            race_type=self.race_type,
            owner=None,
            public=True,
        )
        other = ServerRace.objects.create(
            name='BetaOther',
            plural_name='BetaOthers',
            race_type=self.race_type,
            owner=self.other_account,
            public=True,
        )

        join_form = JoinGameForm(self.account)
        join_choices = list(join_form.fields['race'].queryset)
        self.assertEqual(join_choices, [mine, server, other])
        self.assertEqual(join_form.fields['race'].label_from_instance(mine), 'ZuluMine (yours)')
        self.assertEqual(join_form.fields['race'].label_from_instance(server), 'AlphaServer (server)')
        self.assertEqual(join_form.fields['race'].label_from_instance(other), 'BetaOther')

        new_game_form = NewGameForm(self.account)
        new_game_choices = list(new_game_form.fields['race'].queryset)
        self.assertEqual(new_game_choices, [mine, server, other])
        self.assertEqual(new_game_form.fields['race'].label_from_instance(mine), 'ZuluMine (yours)')
        self.assertEqual(new_game_form.fields['race'].label_from_instance(server), 'AlphaServer (server)')
        self.assertEqual(new_game_form.fields['race'].label_from_instance(other), 'BetaOther')


class TestResearchView(TestCase):
    def setUp(self):
        self.game = default_game(stars=5)
        self.player = self.game.players.first()
        self.player.race_type.research_multiplier = 1.2
        self.player.race_type.save(update_fields=['research_multiplier'])
        self.player.homeworld.labs = 10
        self.player.homeworld.colonists = 10000
        self.player.homeworld.save(update_fields=['labs', 'colonists'])
        self.user, self.account = get_default_user()
        self.client = Client()
        self.client.force_login(self.user)

    def test_research_budget_shows_research_multiplier_suffix(self):
        response = self.client.get(reverse('dj4xol:research', args=[self.game.short_id]))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'RP/Year')
        self.assertContains(response, '(+20%)')


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

    def test_rename_allowed_after_turn_in(self):
        self.player.turned_in = True
        self.player.save(update_fields=['turned_in'])

        response = self.client.post(
            reverse('dj4xol:rename_object', args=[self.game.short_id, self.fleet.short_id]),
            {'name': 'Late Rename'},
        )

        self.assertEqual(response.status_code, 200)
        self.fleet.refresh_from_db()
        self.assertEqual(self.fleet.name, 'Late Rename')


class TestStarMarkerView(TestCase):
    def setUp(self):
        self.game = default_game(stars=6, fleets=0)
        self.player = self.game.players.first()
        self.reported_star = self.game.stars.filter(player__isnull=True).exclude(
            id=self.player.homeworld_id
        ).first()
        self.hidden_star = self.game.stars.filter(player__isnull=True).exclude(
            id=self.player.homeworld_id
        ).exclude(id=self.reported_star.id).first()
        Report.objects.create(
            game=self.game,
            player=self.player,
            year=self.game.year,
            target_type='star',
            target_id=self.reported_star.id,
            cached_report=json.dumps({
                'name': self.reported_star.name,
                'x': self.reported_star.x,
                'y': self.reported_star.y,
                'gravity': self.reported_star.gravity,
                'temperature': self.reported_star.temperature,
                'radiation': self.reported_star.radiation,
                'report_tier': 'basic',
            }),
        )
        self.user, _ = get_default_user()
        self.client = Client()
        self.client.force_login(self.user)

    def test_set_star_marker_on_reported_star(self):
        response = self.client.post(
            reverse('dj4xol:set_star_marker', args=[self.game.short_id, self.reported_star.short_id]),
            {'marker_type': 'CIRCLE', 'marker_color': 'BLUE'},
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()['marker_type'], 'CIRCLE')
        self.assertEqual(response.json()['marker_color'], 'BLUE')
        self.assertTrue(
            PlayerStarMarker.objects.filter(
                player=self.player,
                star=self.reported_star,
                marker_type='CIRCLE',
                marker_color='BLUE',
            ).exists()
        )

    def test_set_star_marker_allowed_after_turn_in(self):
        self.player.turned_in = True
        self.player.save(update_fields=['turned_in'])

        response = self.client.post(
            reverse('dj4xol:set_star_marker', args=[self.game.short_id, self.reported_star.short_id]),
            {'marker_type': 'X'},
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()['marker_type'], 'X')
        self.assertEqual(response.json()['marker_color'], 'BLUE')
        self.assertTrue(
            PlayerStarMarker.objects.filter(
                player=self.player,
                star=self.reported_star,
                marker_type='X',
                marker_color='BLUE',
            ).exists()
        )

    def test_game_turn_lock_keeps_marker_button_active(self):
        self.player.turned_in = True
        self.player.save(update_fields=['turned_in'])
        star = self.player.homeworld

        response = self.client.get(
            reverse('dj4xol:game', args=[self.game.short_id]),
            {
                'x': star.x,
                'y': star.y,
                'sel': star.short_id,
            },
        )

        self.assertEqual(response.status_code, 200)
        self.assertContains(
            response,
            'class="detail-action-btn marker-btn"',
            html=False,
        )
        self.assertContains(
            response,
            'class="detail-action-btn rename-control"',
            html=False,
        )
        self.assertContains(
            response,
            'data-marker-colour="BLUE"',
            html=False,
        )
        self.assertNotContains(
            response,
            'data-marker-colour="WHITE"',
            html=False,
        )
        self.assertContains(response, "'.rename-control'", html=False)
        self.assertNotContains(response, "'.rename-btn'", html=False)

    def test_missing_marker_colour_defaults_to_blue(self):
        response = self.client.post(
            reverse('dj4xol:set_star_marker', args=[self.game.short_id, self.reported_star.short_id]),
            {'marker_type': 'CIRCLE'},
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()['marker_color'], 'BLUE')
        self.assertTrue(
            PlayerStarMarker.objects.filter(
                player=self.player,
                star=self.reported_star,
                marker_type='CIRCLE',
                marker_color='BLUE',
            ).exists()
        )

    def test_clear_star_marker(self):
        PlayerStarMarker.objects.create(
            player=self.player,
            star=self.reported_star,
            marker_type=PlayerStarMarker.TYPE_X,
        )

        response = self.client.post(
            reverse('dj4xol:set_star_marker', args=[self.game.short_id, self.reported_star.short_id]),
            {'marker_type': 'CLEAR'},
        )

        self.assertEqual(response.status_code, 200)
        self.assertFalse(
            PlayerStarMarker.objects.filter(
                player=self.player,
                star=self.reported_star,
            ).exists()
        )

    def test_rejects_star_marker_without_intel(self):
        response = self.client.post(
            reverse('dj4xol:set_star_marker', args=[self.game.short_id, self.hidden_star.short_id]),
            {'marker_type': 'X'},
        )

        self.assertEqual(response.status_code, 403)
        self.assertEqual(response.json()['error'], 'You do not have intel on this star')

    def test_satellite_star_marker_is_saved_on_primary_star(self):
        primary = self.player.homeworld
        satellite = self.reported_star
        satellite.x = primary.x
        satellite.y = primary.y
        satellite.save(update_fields=['x', 'y'])

        response = self.client.post(
            reverse('dj4xol:set_star_marker', args=[self.game.short_id, satellite.short_id]),
            {'marker_type': 'X'},
        )

        self.assertEqual(response.status_code, 200)
        self.assertTrue(
            PlayerStarMarker.objects.filter(
                player=self.player,
                star=primary,
                marker_type='X',
            ).exists()
        )
        self.assertFalse(
            PlayerStarMarker.objects.filter(
                player=self.player,
                star=satellite,
            ).exists()
        )

    def test_set_star_marker_reanchors_location_marker_to_current_primary_star(self):
        primary = self.player.homeworld
        promoted = self.reported_star
        promoted.x = primary.x
        promoted.y = primary.y
        promoted.save(update_fields=['x', 'y'])

        PlayerStarMarker.objects.create(
            player=self.player,
            star=primary,
            marker_type=PlayerStarMarker.TYPE_CIRCLE,
            marker_color=PlayerStarMarker.COLOR_BLUE,
        )

        primary.player = None
        primary.colonists = 0
        primary.save(update_fields=['player', 'colonists'])
        promoted.player = self.player
        promoted.colonists = 1000
        promoted.save(update_fields=['player', 'colonists'])

        response = self.client.post(
            reverse('dj4xol:set_star_marker', args=[self.game.short_id, promoted.short_id]),
            {'marker_type': 'X', 'marker_color': 'RED'},
        )

        self.assertEqual(response.status_code, 200)
        self.assertTrue(
            PlayerStarMarker.objects.filter(
                player=self.player,
                star=promoted,
                marker_type='X',
                marker_color='RED',
            ).exists()
        )
        self.assertFalse(
            PlayerStarMarker.objects.filter(
                player=self.player,
                star=primary,
            ).exists()
        )

    def test_marker_popover_targets_current_primary_star_for_promoted_stack(self):
        primary = self.player.homeworld
        promoted = self.reported_star
        promoted.x = primary.x
        promoted.y = primary.y
        promoted.player = self.player
        promoted.colonists = 1000
        promoted.save(update_fields=['x', 'y', 'player', 'colonists'])

        primary.player = None
        primary.colonists = 0
        primary.save(update_fields=['player', 'colonists'])

        PlayerStarMarker.objects.create(
            player=self.player,
            star=promoted,
            marker_type=PlayerStarMarker.TYPE_X,
            marker_color=PlayerStarMarker.COLOR_RED,
        )

        response = self.client.get(
            reverse('dj4xol:game', args=[self.game.short_id]),
            {
                'x': primary.x,
                'y': primary.y,
                'sel': primary.short_id,
            },
        )

        self.assertEqual(response.status_code, 200)
        self.assertContains(
            response,
            "var starId = '%s';" % promoted.short_id,
            html=False,
        )
        self.assertContains(
            response,
            "var markerStarObjectId = '%s';" % promoted.short_id,
            html=False,
        )
        self.assertNotContains(
            response,
            'applyMarkerState(getSelectedMarkerType(), getSelectedMarkerColor());',
            html=False,
        )

    def test_rejects_invalid_marker_colour(self):
        response = self.client.post(
            reverse('dj4xol:set_star_marker', args=[self.game.short_id, self.reported_star.short_id]),
            {'marker_type': 'X', 'marker_color': 'ORANGE'},
        )

        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.json()['error'], 'Invalid marker colour')


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

    def test_command_endpoint_allows_diplomacy_summary(self):
        response = self.client.post(
            reverse('dj4xol:play_cli_command', args=[self.game.short_id]),
            data=json.dumps({'command': '/diplomacy'}),
            content_type='application/json',
            HTTP_ORIGIN=self.origin,
        )
        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertTrue(payload['ok'])
        self.assertIn('our_stance_raw: NEUTRAL', '\n'.join(payload['lines']))

    def test_command_endpoint_allows_diplomacy_update(self):
        response = self.client.post(
            reverse('dj4xol:play_cli_command', args=[self.game.short_id]),
            data=json.dumps({'command': '/diplomacy default hostile'}),
            content_type='application/json',
            HTTP_ORIGIN=self.origin,
        )
        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertTrue(payload['ok'])
        self.assertTrue(payload['mutated'])
        self.player.refresh_from_db()
        self.assertEqual(self.player.pending_default_diplomatic_stance, 'HOSTILE')

    def test_execute_browser_command_supports_clear(self):
        payload = execute_browser_command(self.game, self.player, '/clear')
        self.assertTrue(payload['ok'])
        self.assertTrue(payload['clear_output'])
        self.assertFalse(payload['mutated'])
        self.assertEqual(payload['lines'], [])

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

    def test_detail_command_navigation_uses_last_known_report_coordinates_for_hidden_fleet(self):
        report_x = self.player.homeworld.x + 7
        report_y = self.player.homeworld.y + 3
        hidden_fleet = Fleet.objects.create(
            game=self.game,
            player=None,
            name='Derelict Echo',
            x=self.player.homeworld.x + 20,
            y=self.player.homeworld.y + 20,
            ship_count=3,
        )
        report = Report.objects.create(
            game=self.game,
            player=self.player,
            year=self.game.year - 1,
            target_type='fleet',
            target_id=hidden_fleet.id,
            cached_report='{}',
        )
        report.set_report_data({
            'name': hidden_fleet.name,
            'x': report_x,
            'y': report_y,
            'report_tier': 'advanced',
            'player_name': 'Abandoned',
            'ship_count': 3,
            'integrity': 100,
            'travel_warp': 0,
            'heading': 0.0,
        })
        report.save(update_fields=['cached_report'])

        response = self.client.post(
            reverse('dj4xol:play_cli_command', args=[self.game.short_id]),
            data=json.dumps({'command': '/detail %s' % hidden_fleet.short_id}),
            content_type='application/json',
            HTTP_ORIGIN=self.origin,
        )
        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertTrue(payload['ok'])
        self.assertEqual(payload['navigate_to']['sel'], hidden_fleet.short_id)
        self.assertEqual(payload['navigate_to']['x'], report_x)
        self.assertEqual(payload['navigate_to']['y'], report_y)
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
                'basic_scanner_range': 6,
                'advanced_scanner_range': 2,
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
        self.assertContains(response, 'Scanners')
        self.assertContains(response, '6ly/2ly')

    def test_advanced_anomaly_report_shows_danger(self):
        anomaly = Anomaly.objects.create(
            game=self.game,
            x=self.star.x + 2,
            y=self.star.y + 1,
            name='Hazard Rift',
            anomaly_type='RIFT',
            stability=65,
        )
        Report.objects.create(
            game=self.game,
            player=self.player,
            year=self.game.year,
            target_type='anomaly',
            target_id=anomaly.id,
            cached_report=json.dumps({
                'name': anomaly.name,
                'x': anomaly.x,
                'y': anomaly.y,
                'anomaly_type': anomaly.anomaly_type,
                'description': anomaly.description,
                'heading': anomaly.heading,
                'stability': anomaly.stability,
                'danger_level': 'HIGH',
                'report_tier': 'advanced',
            }),
        )
        response = self._get_detail_response(anomaly)
        self.assertContains(response, 'Danger')
        self.assertContains(response, 'High')

    def test_advanced_ancient_debris_report_shows_danger(self):
        ancient = Salvage.objects.create(
            game=self.game,
            x=self.star.x + 3,
            y=self.star.y + 1,
            salvage_type='ANCIENT_DEBRIS',
        )
        Report.objects.create(
            game=self.game,
            player=self.player,
            year=self.game.year,
            target_type='salvage',
            target_id=ancient.id,
            cached_report=json.dumps({
                'name': ancient.name,
                'x': ancient.x,
                'y': ancient.y,
                'salvage_type': 'ANCIENT_DEBRIS',
                'danger_level': 'HIGH',
                'total_minerals': 0,
                'report_tier': 'advanced',
            }),
        )
        response = self._get_detail_response(ancient)
        self.assertContains(response, 'Danger')
        self.assertContains(response, 'High')

    def test_unowned_star_with_leftover_infrastructure_shows_abandoned_owner(self):
        self.star.player = None
        self.star.mines = 2
        self.star.factories = 1
        self.star.save(update_fields=['player', 'mines', 'factories'])
        Fleet.objects.create(
            game=self.game,
            player=self.player,
            name='Surveyor',
            x=self.star.x,
            y=self.star.y,
        )

        response = self._get_detail_response(self.star)
        self.assertContains(response, 'Abandoned')
        self.assertNotContains(response, 'Unowned')

    def test_unowned_star_report_with_leftover_infrastructure_shows_abandoned_owner(self):
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
                'colonists': 0,
                'mines': 1,
                'factories': 0,
                'factories_bp': 0,
                'labs': 0,
                'labs_rp': 0,
                'defenses': 0,
                'defenses_tooltip': None,
                'shipyards': 0,
                'jobs_count': 1000,
                'jobs_employment': 0.0,
                'report_tier': 'encounter',
            }),
        )
        response = self._get_detail_response(self.star)
        self.assertContains(response, 'Abandoned')
        self.assertNotContains(response, 'Unowned')

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
        self.assertNotContains(response, 'Max Warp')
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
        self.assertNotContains(response, 'Max Warp')

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
        self.assertContains(response, 'Max Warp')
        self.assertContains(response, 'Bombs')
        self.assertContains(response, 'Wormhole Drive')

    def test_encounter_fleet_report_without_level_fields_hides_capabilities(self):
        self.game.joinable = True
        self.game.save(update_fields=['joinable'])
        other_user = User.objects.create_user('detail_enemy2b', 'de2b@test.com', 'pass')
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
                'report_tier': 'encounter',
            }),
        )
        response = self._get_detail_response(enemy_fleet)
        self.assertNotContains(response, 'data-section="capabilities"')

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

    def test_basic_ancient_debris_report_hides_type_with_blurred_thumbnail(self):
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
        self.assertContains(response, '???')
        self.assertNotContains(response, 'Ancient Debris')
        self.assertContains(response, 'total: 20kt')
        self.assertContains(response, 'Mineral composition unknown.')
        self.assertNotContains(response, 'Ironium')


class TestFleetOrderViews(TestCase):
    def test_game_view_uses_stable_layout_wrappers(self):
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
        self.assertContains(response, 'game-page', html=False)
        self.assertContains(
            response,
            'class="columns game-layout two-column"',
            html=False,
        )
        self.assertContains(
            response,
            'class="game-right-stack column-right"',
            html=False,
        )
        self.assertContains(
            response,
            'class="game-messages-slot column-left"',
            html=False,
        )

    def test_staff_game_view_hides_reset_ui_button_but_keeps_helpers(self):
        game = default_game(stars=5, fleets=1)
        player = game.players.first()
        user, _ = get_default_user()
        user.is_staff = True
        user.save(update_fields=['is_staff'])
        client = Client()
        client.force_login(user)

        response = client.get(
            reverse('dj4xol:game', args=[game.short_id]),
            {'x': player.homeworld.x, 'y': player.homeworld.y, 'sel': player.homeworld.short_id},
        )

        self.assertEqual(response.status_code, 200)
        self.assertNotContains(response, 'Reset UI')
        self.assertContains(response, 'window.clearGameUiState = function()', html=False)
        self.assertContains(response, 'window.listGameUiStateKeys = function()', html=False)

    def test_classic_game_view_does_not_load_lcars_stylesheet(self):
        game = default_game(stars=5, fleets=1)
        player = game.players.first()
        user, account = get_default_user()
        account.theme = 'classic'
        account.save(update_fields=['theme'])
        client = Client()
        client.force_login(user)

        response = client.get(
            reverse('dj4xol:game', args=[game.short_id]),
            {'x': player.homeworld.x, 'y': player.homeworld.y, 'sel': player.homeworld.short_id},
        )

        self.assertEqual(response.status_code, 200)
        self.assertNotContains(response, 'theme-lcars.css', html=False)

    def test_staff_debug_actions_keep_detail_panel_markup_balanced(self):
        game = default_game(stars=5, fleets=1)
        player = game.players.first()
        user, _ = get_default_user()
        user.is_superuser = True
        user.is_staff = True
        user.save(update_fields=['is_superuser', 'is_staff'])
        ServerSettings.objects.update_or_create(
            key='enable_debug_actions',
            defaults={'value': 'True'},
        )
        client = Client()
        client.force_login(user)

        response = client.get(
            reverse('dj4xol:game', args=[game.short_id]),
            {
                'x': player.homeworld.x,
                'y': player.homeworld.y,
                'sel': player.homeworld.short_id,
            },
        )

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'debug-actions panel-footer', html=False)
        self.assertContains(response, 'Create Fleet')
        self.assertRegex(
            response.content.decode('utf-8'),
            re.compile(
                r'<div class="debug-actions panel-footer">.*?</div>\s*</div>\s*</div>\s*<script>',
                re.S,
            ),
        )

    def test_orders_panel_shows_popout_button(self):
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
        self.assertContains(response, 'id="order-params-popout-toggle"', html=False)
        self.assertContains(response, 'id="order-params-overlay"', html=False)
        self.assertContains(response, 'id="order-params-overlay-add"', html=False)
        self.assertContains(response, 'id="order-params-overlay-title">Order Parameters<', html=False)

    def test_non_repeatable_fleet_order_types_disable_repeat_checkbox_in_form(self):
        game = default_game(stars=5, fleets=1)
        player = game.players.first()
        fleet = player.fleets.first()
        user, _ = get_default_user()
        client = Client()
        client.force_login(user)

        response = client.get(
            reverse('dj4xol:game', args=[game.short_id]),
            {
                'x': fleet.x,
                'y': fleet.y,
                'sel': fleet.short_id,
                'order_type': 'COLONISE',
            },
        )

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'class="repeat-checkbox is-disabled"', html=False)
        self.assertContains(response, 'id="repeat-checkbox" disabled', html=False)

    def test_refuel_button_logic_is_scoped_to_refuel_orders(self):
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
        self.assertContains(
            response,
            "if (!orderType || orderType.value !== 'REFUEL') {",
            html=False,
        )
        self.assertContains(
            response,
            'orderTypeInput.value = currentType;\n        setOrderAddDisabled(false);',
            html=False,
        )

    def test_move_and_patrol_defaults_follow_fleet_max_safe_warp(self):
        game = default_game(stars=5, fleets=1)
        player = game.players.first()
        fleet = player.fleets.first()
        fleet.max_safe_warp = 8
        fleet.save(update_fields=['max_safe_warp'])
        user, _ = get_default_user()
        client = Client()
        client.force_login(user)

        response = client.get(
            reverse('dj4xol:game', args=[game.short_id]),
            {'x': fleet.x, 'y': fleet.y, 'sel': fleet.short_id},
        )

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'name="warpfactor" id="warpfactor-input" value="8"', html=False)
        self.assertContains(response, 'id="warp-slider"', html=False)
        self.assertContains(response, 'data-max-safe-warp="8"', html=False)
        self.assertContains(
            response,
            'name="intercept_speed" id="intercept-speed-input" value="8"',
            html=False,
        )
        self.assertContains(response, 'id="intercept-speed-slider"', html=False)

    def test_move_target_selection_preserves_requested_warp(self):
        game = default_game(stars=5, fleets=1)
        player = game.players.first()
        fleet = player.fleets.first()
        user, _ = get_default_user()
        client = Client()
        client.force_login(user)

        response = client.get(
            reverse('dj4xol:game', args=[game.short_id]),
            {
                'x': fleet.x,
                'y': fleet.y,
                'sel': fleet.short_id,
                'order_type': 'MOVE',
                'warp': '7',
                'dest_x': fleet.x + 3,
                'dest_y': fleet.y + 1,
            },
        )

        self.assertEqual(response.status_code, 200)
        self.assertContains(
            response,
            'name="warpfactor" id="warpfactor-input" value="7"',
            html=False,
        )
        self.assertContains(
            response,
            'id="warp-slider"',
            html=False,
        )
        self.assertContains(
            response,
            'id="dest-set-link"',
            html=False,
        )
        self.assertContains(response, 'warp=7', html=False)

    def test_move_single_target_render_includes_explicit_anomaly_target(self):
        game = default_game(stars=5, fleets=2)
        player = game.players.first()
        fleet = player.fleets.order_by('id').first()
        anomaly = Anomaly.objects.create(
            game=game,
            x=fleet.x + 3,
            y=fleet.y + 2,
            name='Nebula 2',
            anomaly_type='NEBULA',
        )
        user, _ = get_default_user()
        client = Client()
        client.force_login(user)

        response = client.get(
            reverse('dj4xol:game', args=[game.short_id]),
            {
                'x': fleet.x,
                'y': fleet.y,
                'sel': fleet.short_id,
                'dest_anomaly': anomaly.short_id,
                'order_type': 'MOVE',
            },
        )

        self.assertEqual(response.status_code, 200)
        self.assertContains(
            response,
            'id="move-single-target-value"',
            html=False,
        )
        self.assertContains(
            response,
            'data-target="anomaly:%s"' % anomaly.short_id,
            html=False,
        )
        self.assertContains(response, 'initializeMoveTarget();', html=False)

    def test_move_single_target_render_includes_explicit_fleet_target(self):
        game = default_game(stars=5, fleets=2)
        player = game.players.first()
        fleets = list(player.fleets.order_by('id'))
        fleet = fleets[0]
        target_fleet = fleets[1]
        target_fleet.x = fleet.x + 4
        target_fleet.y = fleet.y + 1
        target_fleet.save(update_fields=['x', 'y'])
        user, _ = get_default_user()
        client = Client()
        client.force_login(user)

        response = client.get(
            reverse('dj4xol:game', args=[game.short_id]),
            {
                'x': fleet.x,
                'y': fleet.y,
                'sel': fleet.short_id,
                'dest_fleet': target_fleet.short_id,
                'order_type': 'MOVE',
            },
        )

        self.assertEqual(response.status_code, 200)
        self.assertContains(
            response,
            'id="move-single-target-value"',
            html=False,
        )
        self.assertContains(
            response,
            'data-target="fleet:%s"' % target_fleet.short_id,
            html=False,
        )
        self.assertNotContains(
            response,
            'id="add-order-btn" disabled',
            html=False,
        )

    def test_add_fleet_order_move_can_target_anomaly_with_other_origin_fleet(self):
        game = default_game(stars=5, fleets=2)
        player = game.players.first()
        fleets = list(player.fleets.order_by('id'))
        fleet = fleets[0]
        anomaly = Anomaly.objects.create(
            game=game,
            x=fleet.x + 3,
            y=fleet.y + 2,
            name='Nebula 2',
            anomaly_type='NEBULA',
        )
        user, _ = get_default_user()
        client = Client()
        client.force_login(user)

        response = client.post(
            reverse('dj4xol:add_fleet_order', args=[game.short_id]),
            {
                'fleet': fleet.short_id,
                'order_type': 'MOVE',
                'target_anomaly': anomaly.short_id,
                'warpfactor': '5',
                'x': fleet.x,
                'y': fleet.y,
                'sel': fleet.short_id,
            },
        )

        self.assertEqual(response.status_code, 302)
        order = fleet.orders.get(order_type='MOVE')
        self.assertEqual(order.target_kind, 'OBJECT')
        self.assertEqual(order.target_short_id, anomaly.short_id)
        self.assertEqual(order.x, anomaly.x)
        self.assertEqual(order.y, anomaly.y)

    def test_add_fleet_order_move_can_target_salvage_with_other_origin_fleet(self):
        game = default_game(stars=5, fleets=2)
        player = game.players.first()
        fleets = list(player.fleets.order_by('id'))
        fleet = fleets[0]
        salvage = Salvage.objects.create(
            game=game,
            x=fleet.x + 2,
            y=fleet.y + 1,
            ironium_inventory=15,
            boranium_inventory=0,
            germanium_inventory=0,
        )
        user, _ = get_default_user()
        client = Client()
        client.force_login(user)

        response = client.post(
            reverse('dj4xol:add_fleet_order', args=[game.short_id]),
            {
                'fleet': fleet.short_id,
                'order_type': 'MOVE',
                'target_salvage': salvage.short_id,
                'warpfactor': '5',
                'x': fleet.x,
                'y': fleet.y,
                'sel': fleet.short_id,
            },
        )

        self.assertEqual(response.status_code, 302)
        order = fleet.orders.get(order_type='MOVE')
        self.assertEqual(order.target_salvage_id, salvage.id)
        self.assertEqual(order.target_kind, 'OBJECT')
        self.assertEqual(order.target_short_id, salvage.short_id)
        self.assertEqual(order.x, salvage.x)
        self.assertEqual(order.y, salvage.y)

    def test_add_fleet_order_move_can_target_empty_space_with_other_origin_fleet(self):
        game = default_game(stars=5, fleets=2)
        player = game.players.first()
        fleets = list(player.fleets.order_by('id'))
        fleet = fleets[0]
        user, _ = get_default_user()
        client = Client()
        client.force_login(user)

        response = client.post(
            reverse('dj4xol:add_fleet_order', args=[game.short_id]),
            {
                'fleet': fleet.short_id,
                'order_type': 'MOVE',
                'target_x': str(fleet.x + 4),
                'target_y': str(fleet.y + 3),
                'warpfactor': '5',
                'x': fleet.x,
                'y': fleet.y,
                'sel': fleet.short_id,
            },
        )

        self.assertEqual(response.status_code, 302)
        order = fleet.orders.get(order_type='MOVE')
        self.assertEqual(order.target_kind, 'SPACE')
        self.assertIsNone(order.target_short_id)
        self.assertEqual(order.x, fleet.x + 4)
        self.assertEqual(order.y, fleet.y + 3)


class TestHullDesignViews(TestCase):
    def setUp(self):
        self.user, _ = get_default_user()
        self.user.is_staff = True
        self.user.save(update_fields=['is_staff'])
        self.client = Client()
        self.client.force_login(self.user)
        self.energy = ResearchCategory.objects.create(
            code='HULL_ENERGY',
            name='Hull Energy',
            display_order=1,
            enabled=True,
        )
        self.construction = ResearchCategory.objects.create(
            code='HULL_CONSTRUCTION',
            name='Hull Construction',
            display_order=2,
            enabled=True,
        )

    def test_hull_design_list_shows_unlinked_hull_techs(self):
        tech = Technology.objects.create(
            category=self.energy,
            level=9,
            name='Test Hull Tech',
            tech_type='HULL',
            params_json='{}',
        )

        response = self.client.get(reverse('dj4xol:hull_design_list'))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'Unlinked hull techs:')
        self.assertContains(response, tech.name)
        self.assertContains(
            response,
            '?technology=%s' % tech.id,
            html=False,
        )

    def test_hull_design_editor_includes_scanner_slot_type(self):
        response = self.client.get(reverse('dj4xol:hull_design_new'))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, '"value": "SCANNER"', html=False)
        self.assertContains(response, '"label": "Scanner"', html=False)

    def test_hull_design_new_creates_linked_hull_technology(self):
        response = self.client.post(
            reverse('dj4xol:hull_design_new'),
            {
                'name': 'Admin Scout',
                'thumbnail_class': 'scout',
                'offense_offset': '2',
                'defense_offset': '3',
                'ironium_cost': '10',
                'boranium_cost': '20',
                'germanium_cost': '30',
                'resource_x_cost': '0',
                'resource_y_cost': '0',
                'resource_z_cost': '0',
                'cargo_capacity': '80',
                'fuel_capacity': '120',
                'cargo_hold_grid_width': '0',
                'cargo_hold_grid_height': '0',
                'enabled': 'on',
                'tech_name': 'Admin Scout Hull',
                'tech_category': str(self.energy.id),
                'tech_level': '7',
                'tech_display_order': '2',
                'tech_description': 'Admin-created hull tech.',
                'tech_enabled': 'on',
                'slots_json': '[]',
            },
        )

        self.assertEqual(response.status_code, 302)
        hull = HullDesign.objects.get(name='Admin Scout')
        self.assertIsNotNone(hull.technology)
        self.assertEqual(hull.technology.tech_type, 'HULL')
        self.assertEqual(hull.technology.category_id, self.energy.id)
        self.assertEqual(hull.technology.level, 7)
        self.assertEqual(hull.technology.name, 'Admin Scout Hull')
        self.assertEqual(
            json.loads(hull.technology.params_json),
            {
                'defense_level': 0.3,
                'hull_thumbnail_class': 'scout',
                'max_cargo_capacity': 80,
                'max_fuel': 120,
                'offense_level': 0.2,
            },
        )

    def test_hull_design_edit_updates_linked_hull_technology(self):
        tech = Technology.objects.create(
            category=self.energy,
            level=5,
            name='Old Hull Tech',
            description='Old description.',
            tech_type='HULL',
            display_order=1,
            enabled=True,
            params_json=json.dumps({
                'race_type': 'SCI',
                'max_cargo_capacity': 50,
                'max_fuel': 60,
                'hull_thumbnail_class': 'scout',
                'offense_level': 0.0,
                'defense_level': 0.0,
            }),
        )
        hull = HullDesign.objects.create(
            technology=tech,
            name='Linked Hull',
            thumbnail_class='scout',
            cargo_capacity=50,
            fuel_capacity=60,
            enabled=True,
        )

        response = self.client.post(
            reverse('dj4xol:hull_design_edit', args=[hull.id]),
            {
                'technology_id': str(tech.id),
                'name': 'Linked Hull',
                'thumbnail_class': 'fighter',
                'offense_offset': '4',
                'defense_offset': '5',
                'ironium_cost': '0',
                'boranium_cost': '0',
                'germanium_cost': '0',
                'resource_x_cost': '0',
                'resource_y_cost': '0',
                'resource_z_cost': '0',
                'cargo_capacity': '140',
                'fuel_capacity': '180',
                'cargo_hold_grid_width': '0',
                'cargo_hold_grid_height': '0',
                'enabled': 'on',
                'tech_name': 'Updated Hull Tech',
                'tech_category': str(self.construction.id),
                'tech_level': '11',
                'tech_display_order': '4',
                'tech_description': 'Updated description.',
                'tech_enabled': 'on',
                'slots_json': '[]',
            },
        )

        self.assertEqual(response.status_code, 302)
        hull.refresh_from_db()
        tech.refresh_from_db()
        self.assertEqual(tech.category_id, self.construction.id)
        self.assertEqual(tech.level, 11)
        self.assertEqual(tech.name, 'Updated Hull Tech')
        self.assertEqual(tech.description, 'Updated description.')
        params = json.loads(tech.params_json)
        self.assertEqual(params.get('race_type'), 'SCI')
        self.assertEqual(params.get('max_cargo_capacity'), 140)
        self.assertEqual(params.get('max_fuel'), 180)
        self.assertEqual(params.get('hull_thumbnail_class'), 'fighter')
        self.assertEqual(params.get('offense_level'), 0.4)
        self.assertEqual(params.get('defense_level'), 0.5)

    def test_debug_actions_drop_debug_prefix(self):
        game = default_game(stars=5, fleets=1)
        player = game.players.first()
        fleet = player.fleets.first()
        user, _ = get_default_user()
        user.is_superuser = True
        user.is_staff = True
        user.save(update_fields=['is_superuser', 'is_staff'])
        ServerSettings.objects.update_or_create(
            key='enable_debug_actions',
            defaults={'value': 'True'},
        )
        client = Client()
        client.force_login(user)

        response = client.get(
            reverse('dj4xol:game', args=[game.short_id]),
            {'x': fleet.x, 'y': fleet.y, 'sel': fleet.short_id},
        )

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'Create Fleet')
        self.assertContains(response, 'Create Anomaly')
        self.assertNotContains(response, 'Debug:')


class TestDiplomacyView(TestCase):
    def _create_contact_star_report(self, game, viewer, owner, star, report_tier='encounter'):
        star.player = owner
        star.save(update_fields=['player'])
        Report.objects.create(
            game=game,
            player=viewer,
            year=game.year,
            target_type='star',
            target_id=star.id,
            cached_report=json.dumps({
                'name': star.name,
                'x': star.x,
                'y': star.y,
                'player_name': owner.name,
                'report_tier': report_tier,
            }),
        )

    def test_diplomacy_page_lists_contact_and_default(self):
        game = default_game(stars=5, fleets=0)
        game.turn_scheme = 'HOURLY'
        game.next_generation = timezone.now() + timedelta(hours=1)
        game.save(update_fields=['turn_scheme', 'next_generation'])
        player = game.players.first()
        race_type = get_default_race_type()
        other_account_user = User.objects.create_user('diplo_other', 'diplo_other@test.com', 'pass')
        other_account = Account.objects.create(django_user=other_account_user, alias='DIP2')
        other_player = Player.objects.create(
            game=game,
            account=other_account,
            name='Other Race',
            plural_name='Other Races',
            race_type=race_type,
        )
        contact_star = game.stars.exclude(id=player.homeworld_id).first()
        contact_star.player = other_player
        contact_star.save(update_fields=['player'])
        Report.objects.create(
            game=game,
            player=player,
            year=game.year,
            target_type='star',
            target_id=contact_star.id,
            cached_report=json.dumps({
                'name': contact_star.name,
                'x': contact_star.x,
                'y': contact_star.y,
                'player_name': other_player.name,
                'report_tier': 'encounter',
            }),
        )
        user, _ = get_default_user()
        client = Client()
        client.force_login(user)

        response = client.get(
            reverse('dj4xol:diplomacy', args=[game.short_id]),
            {'target': other_player.short_id},
        )

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'Default')
        self.assertContains(response, other_player.name)
        self.assertContains(response, 'Encounter Combat')
        self.assertNotContains(response, 'Update Standing')
        self.assertContains(response, 'Current Effects')
        self.assertNotContains(response, 'Effects They Grant')
        self.assertContains(response, 'id="next-turn-countdown"', html=False)
        self.assertContains(response, 'window.currentYear = %s;' % game.year)
        self.assertContains(response, 'window.gameStatusUrl =')

    def test_diplomacy_page_includes_panel_toggle_and_lcars_variant_scripts(self):
        game = default_game(stars=5, fleets=0)
        user, _ = get_default_user()
        client = Client()
        client.force_login(user)

        response = client.get(reverse('dj4xol:diplomacy', args=[game.short_id]))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "panel.classList.toggle('open');", html=False)
        self.assertContains(response, "lcars-variant-1', 'lcars-variant-2', 'lcars-variant-3", html=False)

    def test_diplomacy_disables_draft_negotiation_button_when_turned_in(self):
        game = default_game(stars=5, fleets=0)
        player = game.players.first()
        player.turned_in = True
        player.save(update_fields=['turned_in'])
        race_type = get_default_race_type()
        other_account_user = User.objects.create_user('diplo_locked_toggle', 'diplo_locked_toggle@test.com', 'pass')
        other_account = Account.objects.create(django_user=other_account_user, alias='DLT2')
        other_player = Player.objects.create(
            game=game,
            account=other_account,
            name='Locked Toggle Race',
            plural_name='Locked Toggle Races',
            race_type=race_type,
        )
        self._create_contact_star_report(
            game,
            player,
            other_player,
            game.stars.exclude(id=player.homeworld_id).first(),
        )
        user, _ = get_default_user()
        client = Client()
        client.force_login(user)

        response = client.get(
            reverse('dj4xol:diplomacy', args=[game.short_id]),
            {'target': other_player.short_id},
        )

        self.assertEqual(response.status_code, 200)
        self.assertContains(
            response,
            'id="diplomacy-compose-toggle-button" class="diplomacy-action-button" disabled',
            html=False,
        )
        self.assertContains(response, 'class="classic turned-in"', html=False)

    def test_diplomacy_hashes_out_compose_form_when_turned_in(self):
        game = default_game(stars=5, fleets=0)
        player = game.players.first()
        player.turned_in = True
        player.save(update_fields=['turned_in'])
        race_type = get_default_race_type()
        other_account_user = User.objects.create_user('diplo_locked_form', 'diplo_locked_form@test.com', 'pass')
        other_account = Account.objects.create(django_user=other_account_user, alias='DLF')
        other_player = Player.objects.create(
            game=game,
            account=other_account,
            name='Locked Form Race',
            plural_name='Locked Form Races',
            race_type=race_type,
        )
        self._create_contact_star_report(
            game,
            player,
            other_player,
            game.stars.exclude(id=player.homeworld_id).first(),
        )
        user, _ = get_default_user()
        client = Client()
        client.force_login(user)

        response = client.get(
            reverse('dj4xol:diplomacy', args=[game.short_id]),
            {'target': other_player.short_id, 'compose': '1'},
        )

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'diplomacy-compose-form diplomacy-compose-locked', html=False)
        self.assertContains(response, 'name="temperature" class="compose-token" disabled', html=False)
        self.assertContains(
            response,
            '<button type="submit" class="diplomacy-action-button" disabled>Send</button>',
            html=False,
        )
        self.assertContains(response, 'window.__applyDiplomacyLock = applyDiplomacyLock;', html=False)

    def test_diplomacy_limits_requests_per_race_per_turn_with_warning(self):
        game = default_game(stars=5, fleets=0)
        player = game.players.first()
        race_type = get_default_race_type()
        other_account_user = User.objects.create_user('diplo_limit_target', 'diplo_limit_target@test.com', 'pass')
        other_account = Account.objects.create(django_user=other_account_user, alias='DLT')
        other_player = Player.objects.create(
            game=game,
            account=other_account,
            name='Limit Race',
            plural_name='Limit Races',
            race_type=race_type,
        )
        contact_star = game.stars.exclude(id=player.homeworld_id).first()
        contact_star.player = other_player
        contact_star.save(update_fields=['player'])
        Report.objects.create(
            game=game,
            player=player,
            year=game.year,
            target_type='star',
            target_id=contact_star.id,
            cached_report=json.dumps({
                'name': contact_star.name,
                'x': contact_star.x,
                'y': contact_star.y,
                'player_name': other_player.name,
                'report_tier': 'encounter',
            }),
        )
        ServerSettings.objects.update_or_create(
            key='max_diplomatic_requests_per_race_per_turn',
            defaults={
                'value': '2',
                'description': 'Maximum diplomatic requests per race per turn',
            },
        )
        for _idx in range(2):
            DiplomaticContract.objects.create(
                game=game,
                sender=player,
                recipient=other_player,
                temperature='REQUEST',
                status='SENT',
                sent_year=game.year,
                expires_year=game.year + 24,
                request_clause_type='STANCE',
                request_stance='NEUTRAL',
                offer_clause_type='NOTHING',
            )

        user, _ = get_default_user()
        client = Client()
        client.force_login(user)
        response = client.post(
            reverse('dj4xol:diplomacy', args=[game.short_id]),
            {
                'target': other_player.short_id,
                'action': 'send_contract',
                'temperature': 'REQUEST',
                'deadline_years': '24',
                'extend_on_accept_years': '0',
                'request_clause_type': 'STANCE',
                'request_stance': 'WARM',
                'offer_clause_type': 'NOTHING',
            },
        )

        self.assertEqual(response.status_code, 200)
        self.assertContains(
            response,
            'You have already sent the maximum of 2 diplomatic requests to Limit Race this turn.',
        )
        self.assertContains(response, 'form-message-banner')
        self.assertEqual(
            DiplomaticContract.objects.filter(
                game=game,
                sender=player,
                recipient=other_player,
                sent_year=game.year,
            ).count(),
            2,
        )

    def test_diplomacy_same_turn_revoke_creates_no_status_messages(self):
        game = default_game(stars=5, fleets=0)
        player = game.players.first()
        race_type = get_default_race_type()
        other_user = User.objects.create_user('diplo_revoke_silent', 'diplo_revoke_silent@test.com', 'pass')
        other_account = Account.objects.create(django_user=other_user, alias='DRS')
        other_player = Player.objects.create(
            game=game,
            account=other_account,
            name='Revoke Race',
            plural_name='Revoke Races',
            race_type=race_type,
        )
        contact_star = game.stars.exclude(id=player.homeworld_id).first()
        contact_star.player = other_player
        contact_star.save(update_fields=['player'])
        Report.objects.create(
            game=game,
            player=player,
            year=game.year,
            target_type='star',
            target_id=contact_star.id,
            cached_report=json.dumps({
                'name': contact_star.name,
                'x': contact_star.x,
                'y': contact_star.y,
                'player_name': other_player.name,
                'report_tier': 'encounter',
            }),
        )
        contract = DiplomaticContract.objects.create(
            game=game,
            sender=player,
            recipient=other_player,
            temperature='REQUEST',
            status='SENT',
            sent_year=game.year,
            expires_year=game.year + 24,
            request_clause_type='RESOURCE_TO_WORLD',
            request_ironium=25,
            offer_clause_type='NOTHING',
        )

        user, _ = get_default_user()
        client = Client()
        client.force_login(user)
        response = client.post(
            reverse('dj4xol:diplomacy', args=[game.short_id]),
            {
                'target': other_player.short_id,
                'action': 'revoke_contract',
                'contract_id': contract.short_id,
            },
        )

        self.assertEqual(response.status_code, 302)
        contract.refresh_from_db()
        self.assertEqual(contract.status, DiplomaticContract.STATUS_REVOKED)
        self.assertFalse(
            GameMessage.objects.filter(
                game=game,
                category='DIPLOMATIC',
                message__contains='Diplomatic request revoked:',
            ).exists()
        )

    def test_diplomacy_older_revoke_still_creates_status_messages(self):
        game = default_game(stars=5, fleets=0)
        game.year += 1
        game.save(update_fields=['year'])
        player = game.players.first()
        race_type = get_default_race_type()
        other_user = User.objects.create_user('diplo_revoke_logged', 'diplo_revoke_logged@test.com', 'pass')
        other_account = Account.objects.create(django_user=other_user, alias='DRL')
        other_player = Player.objects.create(
            game=game,
            account=other_account,
            name='Older Race',
            plural_name='Older Races',
            race_type=race_type,
        )
        contact_star = game.stars.exclude(id=player.homeworld_id).first()
        contact_star.player = other_player
        contact_star.save(update_fields=['player'])
        Report.objects.create(
            game=game,
            player=player,
            year=game.year,
            target_type='star',
            target_id=contact_star.id,
            cached_report=json.dumps({
                'name': contact_star.name,
                'x': contact_star.x,
                'y': contact_star.y,
                'player_name': other_player.name,
                'report_tier': 'encounter',
            }),
        )
        contract = DiplomaticContract.objects.create(
            game=game,
            sender=player,
            recipient=other_player,
            temperature='REQUEST',
            status='SENT',
            sent_year=game.year - 1,
            expires_year=game.year + 23,
            request_clause_type='STANCE',
            request_stance='WARM',
            offer_clause_type='NOTHING',
        )

        user, _ = get_default_user()
        client = Client()
        client.force_login(user)
        response = client.post(
            reverse('dj4xol:diplomacy', args=[game.short_id]),
            {
                'target': other_player.short_id,
                'action': 'revoke_contract',
                'contract_id': contract.short_id,
            },
        )

        self.assertEqual(response.status_code, 302)
        contract.refresh_from_db()
        self.assertEqual(contract.status, DiplomaticContract.STATUS_REVOKED)
        self.assertEqual(
            GameMessage.objects.filter(
                game=game,
                category='DIPLOMATIC',
                message__contains='Diplomatic request revoked:',
            ).count(),
            2,
        )
    def test_diplomacy_post_updates_default_and_specific_stance(self):
        game = default_game(stars=5, fleets=0)
        player = game.players.first()
        race_type = get_default_race_type()
        other_account_user = User.objects.create_user('diplo_target', 'diplo_target@test.com', 'pass')
        other_account = Account.objects.create(django_user=other_account_user, alias='DIP3')
        other_player = Player.objects.create(
            game=game,
            account=other_account,
            name='Target Race',
            plural_name='Target Races',
            race_type=race_type,
        )
        contact_star = game.stars.exclude(id=player.homeworld_id).first()
        contact_star.player = other_player
        contact_star.save(update_fields=['player'])
        Report.objects.create(
            game=game,
            player=player,
            year=game.year,
            target_type='star',
            target_id=contact_star.id,
            cached_report=json.dumps({
                'name': contact_star.name,
                'x': contact_star.x,
                'y': contact_star.y,
                'player_name': other_player.name,
                'report_tier': 'advanced',
            }),
        )
        user, _ = get_default_user()
        client = Client()
        client.force_login(user)

        response = client.post(
            reverse('dj4xol:diplomacy', args=[game.short_id]),
            {
                'target': other_player.short_id,
                'stance_default': 'COLD',
                'stance_%s' % other_player.short_id: 'ALLIED',
            },
        )

        self.assertEqual(response.status_code, 302)
        player.refresh_from_db()
        self.assertEqual(player.default_diplomatic_stance, 'NEUTRAL')
        self.assertEqual(player.pending_default_diplomatic_stance, 'COLD')
        row = PlayerDiplomaticStance.objects.get(player=player, target_player=other_player)
        self.assertEqual(row.stance, 'NEUTRAL')
        self.assertEqual(row.pending_stance, 'ALLIED')

    def test_diplomacy_page_lists_contact_from_stance_row_without_report(self):
        game = default_game(stars=5, fleets=0)
        player = game.players.first()
        race_type = get_default_race_type()
        other_account_user = User.objects.create_user('diplo_stance_only', 'diplo_stance_only@test.com', 'pass')
        other_account = Account.objects.create(django_user=other_account_user, alias='DIP4')
        other_player = Player.objects.create(
            game=game,
            account=other_account,
            name='Stance Race',
            plural_name='Stance Races',
            race_type=race_type,
        )
        PlayerDiplomaticStance.objects.create(
            player=player,
            target_player=other_player,
            stance='COLD',
        )
        user, _ = get_default_user()
        client = Client()
        client.force_login(user)

        response = client.get(reverse('dj4xol:diplomacy', args=[game.short_id]))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'Stance Race')

    def test_diplomacy_chance_scale_matches_anchor_values(self):
        self.assertEqual(combat_chance_percent('HOSTILE', 'HOSTILE'), 100)
        self.assertEqual(combat_chance_percent('HOSTILE', 'COLD'), 100)
        self.assertEqual(combat_chance_percent('HOSTILE', 'NEUTRAL'), 98)
        self.assertEqual(combat_chance_percent('HOSTILE', 'WARM'), 95)
        self.assertEqual(combat_chance_percent('HOSTILE', 'ALLIED'), 90)
        self.assertEqual(combat_chance_percent('ALLIED', 'HOSTILE'), 90)
        self.assertEqual(combat_chance_percent('NEUTRAL', 'NEUTRAL'), 30)
        self.assertEqual(combat_chance_percent('NEUTRAL', 'WARM'), 8)
        self.assertEqual(combat_chance_percent('WARM', 'WARM'), 1)
        self.assertEqual(combat_chance_percent('ALLIED', 'ALLIED'), 0)

    def test_diplomacy_readiness_modifier_favors_more_hostile_side(self):
        self.assertEqual(combat_readiness_multiplier('HOSTILE', 'ALLIED'), 1.4)
        self.assertEqual(combat_readiness_multiplier('ALLIED', 'HOSTILE'), 0.6)
        self.assertEqual(combat_readiness_multiplier('NEUTRAL', 'NEUTRAL'), 1.0)

    def test_persuasion_modifier_reduces_and_increases_effective_encounter_chance(self):
        game = default_game(stars=5, fleets=0)
        player = game.players.first()
        persuasive_type = ServerRaceType.objects.create(
            code='PSA1',
            name='Persuasive A',
            enabled=True,
            description='',
            diplomacy_multiplier=2.0,
        )
        player.race_type = persuasive_type
        player.save(update_fields=['race_type'])
        other_account_user = User.objects.create_user('diplo_persuasion', 'diplo_persuasion@test.com', 'pass')
        other_account = Account.objects.create(django_user=other_account_user, alias='DIP5')
        other_race_type = ServerRaceType.objects.create(
            code='PSB1',
            name='Persuasive B',
            enabled=True,
            description='',
            diplomacy_multiplier=0.5,
        )
        other_player = Player.objects.create(
            game=game,
            account=other_account,
            name='Persuasion Race',
            plural_name='Persuasion Races',
            race_type=other_race_type,
        )

        self.assertEqual(combat_chance_modifier_percent(player, other_player), 0)
        self.assertEqual(
            combat_chance_with_diplomacy_percent('NEUTRAL', 'NEUTRAL', player, other_player),
            30,
        )

        other_race_type.diplomacy_multiplier = 2.0
        other_race_type.save(update_fields=['diplomacy_multiplier'])
        self.assertEqual(combat_chance_modifier_percent(player, other_player), -50)

    def test_diplomacy_can_send_and_accept_contracts(self):
        game = default_game(stars=5, fleets=0)
        player = game.players.first()
        race_type = get_default_race_type()
        other_user = User.objects.create_user('diplo_contract_target', 'diplo_contract_target@test.com', 'pass')
        other_account = Account.objects.create(django_user=other_user, alias='DCT')
        other_player = Player.objects.create(
            game=game,
            account=other_account,
            name='Contract Race',
            plural_name='Contract Races',
            race_type=race_type,
        )
        contact_star = game.stars.exclude(id=player.homeworld_id).first()
        contact_star.player = other_player
        contact_star.save(update_fields=['player'])
        Report.objects.create(
            game=game,
            player=player,
            year=game.year,
            target_type='star',
            target_id=contact_star.id,
            cached_report=json.dumps({
                'name': contact_star.name,
                'x': contact_star.x,
                'y': contact_star.y,
                'player_name': other_player.name,
                'report_tier': 'encounter',
            }),
        )

        tech = Technology.objects.filter(enabled=True).order_by('level', 'id').first()
        other_rows = ensure_player_research_rows(other_player)
        target_row = next(row for row in other_rows if row.category_id == tech.category_id)
        target_row.current_level = tech.level
        target_row.save(update_fields=['current_level'])
        tech = get_player_unlocked_technologies(other_player)[0]

        user, _ = get_default_user()
        client = Client()
        client.force_login(user)
        response = client.post(
            reverse('dj4xol:diplomacy', args=[game.short_id]),
            {
                'target': other_player.short_id,
                'action': 'send_contract',
                'temperature': 'PROPOSE',
                'deadline_years': '24',
                'extend_on_accept_years': '0',
                'request_clause_type': 'STANCE',
                'request_stance': 'WARM',
                'offer_clause_type': 'NOTHING',
            },
        )
        self.assertEqual(response.status_code, 302)
        contract = DiplomaticContract.objects.get(
            sender=player,
            recipient=other_player,
            request_clause_type='STANCE',
        )
        self.assertEqual(contract.status, DiplomaticContract.STATUS_SENT)

        tech_contract = DiplomaticContract.objects.create(
            game=game,
            sender=player,
            recipient=other_player,
            temperature='PROPOSE',
            status='SENT',
            sent_year=game.year,
            expires_year=game.year + 24,
            request_clause_type='TECHNOLOGY',
            request_technology=tech,
            offer_clause_type='NOTHING',
        )

        other_client = Client()
        other_client.force_login(other_user)
        response = other_client.post(
            reverse('dj4xol:diplomacy', args=[game.short_id]),
            {
                'target': player.short_id,
                'action': 'accept_contract',
                'contract_id': tech_contract.short_id,
            },
        )
        self.assertEqual(response.status_code, 302)
        tech_contract.refresh_from_db()
        self.assertEqual(tech_contract.status, DiplomaticContract.STATUS_FULFILLED)
        self.assertTrue(
            PlayerTechnologyGrant.objects.filter(player=player, technology=tech).exists()
        )
        self.assertIn(tech.id, {item.id for item in get_player_unlocked_technologies(player)})

    def test_diplomacy_technology_exchange_grants_correct_tech_to_each_player(self):
        game = default_game(stars=5, fleets=0)
        player = game.players.first()
        race_type = get_default_race_type()
        other_user = User.objects.create_user('diplo_contract_tech_exchange', 'diplo_contract_tech_exchange@test.com', 'pass')
        other_account = Account.objects.create(django_user=other_user, alias='DTE')
        other_player = Player.objects.create(
            game=game,
            account=other_account,
            name='Exchange Race',
            plural_name='Exchange Races',
            race_type=race_type,
        )
        contact_star = game.stars.exclude(id=player.homeworld_id).first()
        contact_star.player = other_player
        contact_star.save(update_fields=['player'])
        Report.objects.create(
            game=game,
            player=player,
            year=game.year,
            target_type='star',
            target_id=contact_star.id,
            cached_report=json.dumps({
                'name': contact_star.name,
                'x': contact_star.x,
                'y': contact_star.y,
                'player_name': other_player.name,
                'report_tier': 'encounter',
            }),
        )

        propulsion = ResearchCategory.objects.create(
            code='DIPLOXPROP',
            name='Diplomatic Propulsion',
            enabled=True,
        )
        construction = ResearchCategory.objects.create(
            code='DIPLOXHULL',
            name='Diplomatic Hulls',
            enabled=True,
        )
        player_tech = Technology.objects.create(
            category=construction,
            level=4,
            name='Gifted Freighter Hull',
            tech_type='HULL',
            params_json='{"max_cargo_capacity": 350, "max_fuel": 180, "hull_thumbnail_class": "freighter"}',
            enabled=True,
        )
        other_tech = Technology.objects.create(
            category=propulsion,
            level=4,
            name='Gifted Warp 8',
            tech_type='PROPULSION',
            params_json='{"max_warp_speed": 8, "fuel_efficiency": 1.2}',
            enabled=True,
        )
        player_rows = ensure_player_research_rows(player)
        for row in player_rows:
            row.current_level = float(player_tech.level) if row.category_id == player_tech.category_id else 0.0
            row.save(update_fields=['current_level'])
        other_rows = ensure_player_research_rows(other_player)
        for row in other_rows:
            row.current_level = float(other_tech.level) if row.category_id == other_tech.category_id else 0.0
            row.save(update_fields=['current_level'])

        self.assertIn(player_tech.id, {item.id for item in get_player_unlocked_technologies(player)})
        self.assertNotIn(player_tech.id, {item.id for item in get_player_unlocked_technologies(other_player)})
        self.assertIn(other_tech.id, {item.id for item in get_player_unlocked_technologies(other_player)})
        self.assertNotIn(other_tech.id, {item.id for item in get_player_unlocked_technologies(player)})

        contract = DiplomaticContract.objects.create(
            game=game,
            sender=player,
            recipient=other_player,
            temperature='PROPOSE',
            status='SENT',
            sent_year=game.year,
            expires_year=game.year + 24,
            request_clause_type='TECHNOLOGY',
            request_technology=other_tech,
            offer_condition_type='EXCHANGE',
            offer_clause_type='TECHNOLOGY',
            offer_technology=player_tech,
        )

        other_client = Client()
        other_client.force_login(other_user)
        response = other_client.post(
            reverse('dj4xol:diplomacy', args=[game.short_id]),
            {
                'target': player.short_id,
                'action': 'accept_contract',
                'contract_id': contract.short_id,
            },
        )

        self.assertEqual(response.status_code, 302)
        contract.refresh_from_db()
        self.assertEqual(contract.status, DiplomaticContract.STATUS_FULFILLED)

        player_grant = PlayerTechnologyGrant.objects.get(player=player, technology=other_tech)
        self.assertEqual(player_grant.source_contract_id, contract.id)
        self.assertEqual(player_grant.granted_by_player_id, other_player.id)

        other_grant = PlayerTechnologyGrant.objects.get(player=other_player, technology=player_tech)
        self.assertEqual(other_grant.source_contract_id, contract.id)
        self.assertEqual(other_grant.granted_by_player_id, player.id)

        self.assertIn(other_tech.id, {item.id for item in get_player_unlocked_technologies(player)})
        self.assertIn(player_tech.id, {item.id for item in get_player_unlocked_technologies(other_player)})

        player_effects = get_player_tech_effects(player)
        self.assertEqual(player_effects['max_warp_speed'], 8)
        self.assertGreaterEqual(player_effects['fuel_efficiency'], 1.2)

        other_effects = get_player_tech_effects(other_player)
        self.assertEqual(other_effects['max_cargo_capacity'], 350)
        self.assertEqual(other_effects['max_fuel'], 180)
        self.assertEqual(other_effects['hull_thumbnail_class'], 'freighter')

    def test_diplomacy_offer_colony_report_transfers_ownership_report_on_accept(self):
        game = default_game(stars=5, fleets=0)
        player = game.players.first()
        race_type = get_default_race_type()
        other_user = User.objects.create_user('diplo_report_colony_offer', 'diplo_report_colony_offer@test.com', 'pass')
        other_account = Account.objects.create(django_user=other_user, alias='DRC')
        other_player = Player.objects.create(
            game=game,
            account=other_account,
            name='Report Colony Race',
            plural_name='Report Colony Races',
            race_type=race_type,
        )
        contact_star = game.stars.exclude(id=player.homeworld_id).order_by('id').first()
        contact_star.player = other_player
        contact_star.colonists = 42000
        contact_star.save(update_fields=['player', 'colonists'])
        Report.objects.create(
            game=game,
            player=player,
            year=game.year - 2,
            target_type='star',
            target_id=contact_star.id,
            cached_report=json.dumps({
                'name': contact_star.name,
                'x': contact_star.x,
                'y': contact_star.y,
                'player_name': other_player.name,
                'colonists': 42000,
                'gravity': contact_star.gravity,
                'temperature': contact_star.temperature,
                'radiation': contact_star.radiation,
                'report_tier': 'encounter',
            }),
        )

        contract = DiplomaticContract.objects.create(
            game=game,
            sender=player,
            recipient=other_player,
            temperature='PROPOSE',
            status='SENT',
            sent_year=game.year,
            expires_year=game.year + 24,
            request_clause_type='NOTHING',
            offer_condition_type='EXCHANGE',
            offer_clause_type='REPORT',
            offer_report_target_type='star',
            offer_report_target_id=contact_star.id,
        )

        other_client = Client()
        other_client.force_login(other_user)
        response = other_client.post(
            reverse('dj4xol:diplomacy', args=[game.short_id]),
            {'target': player.short_id, 'action': 'accept_contract', 'contract_id': contract.short_id},
        )

        self.assertEqual(response.status_code, 302)
        shared_report = Report.objects.get(player=other_player, target_type='star', target_id=contact_star.id)
        shared_data = shared_report.get_report_data()
        self.assertEqual(shared_data.get('report_tier'), 'ownership')
        self.assertEqual(shared_data.get('player_name'), other_player.name)
        self.assertEqual(shared_report.year, game.year - 2)
        self.assertNotIn('colonists', shared_data)

    def test_diplomacy_request_colony_report_accepts_without_existing_owner_report_row(self):
        game = default_game(stars=5, fleets=0)
        player = game.players.first()
        race_type = get_default_race_type()
        other_user = User.objects.create_user('diplo_report_request_live_owner', 'diplo_report_request_live_owner@test.com', 'pass')
        other_account = Account.objects.create(django_user=other_user, alias='DRL')
        other_player = Player.objects.create(
            game=game,
            account=other_account,
            name='Live Owner Race',
            plural_name='Live Owner Races',
            race_type=race_type,
        )
        target_star = game.stars.exclude(id=player.homeworld_id).order_by('id').first()
        target_star.player = other_player
        target_star.colonists = 42000
        target_star.save(update_fields=['player', 'colonists'])
        other_player.homeworld = target_star
        other_player.save(update_fields=['homeworld'])
        Report.objects.create(
            game=game,
            player=player,
            year=game.year,
            target_type='star',
            target_id=target_star.id,
            cached_report=json.dumps({
                'name': target_star.name,
                'x': target_star.x,
                'y': target_star.y,
                'player_name': other_player.name,
                'report_tier': 'ownership',
            }),
        )

        contract = DiplomaticContract.objects.create(
            game=game,
            sender=player,
            recipient=other_player,
            temperature='PROPOSE',
            status='SENT',
            sent_year=game.year,
            expires_year=game.year + 24,
            request_clause_type='REPORT',
            request_report_target_type='star',
            request_report_target_id=target_star.id,
            offer_condition_type='EXCHANGE',
            offer_clause_type='NOTHING',
        )

        other_client = Client()
        other_client.force_login(other_user)
        response = other_client.post(
            reverse('dj4xol:diplomacy', args=[game.short_id]),
            {'target': player.short_id, 'action': 'accept_contract', 'contract_id': contract.short_id},
        )

        self.assertEqual(response.status_code, 302)
        contract.refresh_from_db()
        self.assertEqual(contract.status, DiplomaticContract.STATUS_FULFILLED)
        shared_report = Report.objects.get(player=player, target_type='star', target_id=target_star.id)
        shared_data = shared_report.get_report_data()
        self.assertEqual(shared_data.get('report_tier'), 'ownership')
        self.assertEqual(shared_data.get('player_name'), other_player.name)

    def test_diplomacy_report_choices_only_include_directional_colonies_and_advanced_intel(self):
        game = default_game(stars=5, fleets=0)
        player = game.players.first()
        race_type = get_default_race_type()
        other_user = User.objects.create_user('diplo_report_choices', 'diplo_report_choices@test.com', 'pass')
        other_account = Account.objects.create(django_user=other_user, alias='DRQ')
        other_player = Player.objects.create(
            game=game,
            account=other_account,
            name='Report Choice Race',
            plural_name='Report Choice Races',
            race_type=race_type,
        )
        player_colony = game.stars.exclude(id=player.homeworld_id).order_by('id').first()
        player_recent_colony = game.stars.exclude(id__in=[player.homeworld_id, player_colony.id]).order_by('id').first()
        other_colony = game.stars.exclude(id__in=[player.homeworld_id, player_colony.id, player_recent_colony.id]).order_by('id').first()
        hidden_star = game.stars.exclude(id__in=[player.homeworld_id, player_colony.id, player_recent_colony.id, other_colony.id]).order_by('id').first()
        player_colony.player = player
        player_colony.save(update_fields=['player'])
        player_recent_colony.player = player
        player_recent_colony.save(update_fields=['player'])
        other_colony.player = other_player
        hidden_star.player = other_player
        other_colony.save(update_fields=['player'])
        hidden_star.save(update_fields=['player'])
        other_player.homeworld = other_colony
        other_player.save(update_fields=['homeworld'])
        Report.objects.create(
            game=game,
            player=player,
            year=game.year,
            target_type='star',
            target_id=player_colony.id,
            cached_report=json.dumps({
                'name': player_colony.name,
                'x': player_colony.x,
                'y': player_colony.y,
                'player_name': player.name,
                'report_tier': 'ownership',
            }),
        )
        Report.objects.create(
            game=game,
            player=other_player,
            year=game.year,
            target_type='star',
            target_id=other_colony.id,
            cached_report=json.dumps({
                'name': other_colony.name,
                'x': other_colony.x,
                'y': other_colony.y,
                'player_name': other_player.name,
                'report_tier': 'ownership',
            }),
        )
        Report.objects.create(
            game=game,
            player=player,
            year=game.year,
            target_type='star',
            target_id=other_colony.id,
            cached_report=json.dumps({
                'name': other_colony.name,
                'x': other_colony.x,
                'y': other_colony.y,
                'player_name': other_player.name,
                'report_tier': 'ownership',
            }),
        )
        anomaly = Anomaly.objects.create(
            game=game,
            name='Abyssal Rift',
            x=player_colony.x + 3,
            y=player_colony.y + 2,
            anomaly_type='WORMHOLE',
            description='A stable rift.',
            heading=45,
            stability=80,
        )
        ancient = Salvage.objects.create(
            game=game,
            x=player_colony.x + 4,
            y=player_colony.y + 4,
            salvage_type='ANCIENT_DEBRIS',
        )
        wreck = Salvage.objects.create(
            game=game,
            x=player_colony.x + 5,
            y=player_colony.y + 5,
            salvage_type='WRECKAGE',
        )
        Report.objects.create(
            game=game,
            player=player,
            year=game.year,
            target_type='anomaly',
            target_id=anomaly.id,
            cached_report=json.dumps({
                'name': anomaly.name,
                'x': anomaly.x,
                'y': anomaly.y,
                'anomaly_type': anomaly.anomaly_type,
                'description': anomaly.description,
                'heading': anomaly.heading,
                'stability': anomaly.stability,
                'report_tier': 'advanced',
            }),
        )
        Report.objects.create(
            game=game,
            player=other_player,
            year=game.year,
            target_type='anomaly',
            target_id=anomaly.id,
            cached_report=json.dumps({
                'name': anomaly.name,
                'x': anomaly.x,
                'y': anomaly.y,
                'anomaly_type': anomaly.anomaly_type,
                'description': anomaly.description,
                'heading': anomaly.heading,
                'stability': anomaly.stability,
                'report_tier': 'advanced',
            }),
        )
        Report.objects.create(
            game=game,
            player=player,
            year=game.year,
            target_type='salvage',
            target_id=ancient.id,
            cached_report=json.dumps({
                'name': ancient.name,
                'x': ancient.x,
                'y': ancient.y,
                'salvage_type': 'ANCIENT_DEBRIS',
                'total_minerals': 0,
                'report_tier': 'advanced',
            }),
        )
        Report.objects.create(
            game=game,
            player=other_player,
            year=game.year,
            target_type='salvage',
            target_id=ancient.id,
            cached_report=json.dumps({
                'name': ancient.name,
                'x': ancient.x,
                'y': ancient.y,
                'salvage_type': 'ANCIENT_DEBRIS',
                'total_minerals': 0,
                'report_tier': 'advanced',
            }),
        )
        Report.objects.create(
            game=game,
            player=player,
            year=game.year,
            target_type='salvage',
            target_id=wreck.id,
            cached_report=json.dumps({
                'name': wreck.name,
                'x': wreck.x,
                'y': wreck.y,
                'salvage_type': 'WRECKAGE',
                'total_minerals': 0,
                'report_tier': 'encounter',
            }),
        )
        Report.objects.create(
            game=game,
            player=player,
            year=game.year,
            target_type='anomaly',
            target_id=uuid.uuid4(),
            cached_report=json.dumps({
                'name': 'Shallow Echo',
                'x': 1,
                'y': 1,
                'anomaly_type': 'WORMHOLE',
                'report_tier': 'basic',
            }),
        )
        vanished_anomaly_id = uuid.uuid4()
        vanished_ancient_id = uuid.uuid4()
        Report.objects.create(
            game=game,
            player=player,
            year=game.year,
            target_type='anomaly',
            target_id=vanished_anomaly_id,
            cached_report=json.dumps({
                'name': 'Unknown Anomaly',
                'x': 2,
                'y': 2,
                'anomaly_type': 'WORMHOLE',
                'report_tier': 'advanced',
            }),
        )
        Report.objects.create(
            game=game,
            player=other_player,
            year=game.year,
            target_type='anomaly',
            target_id=vanished_anomaly_id,
            cached_report=json.dumps({
                'name': 'Unknown Anomaly',
                'x': 2,
                'y': 2,
                'anomaly_type': 'WORMHOLE',
                'report_tier': 'advanced',
            }),
        )
        Report.objects.create(
            game=game,
            player=player,
            year=game.year,
            target_type='salvage',
            target_id=vanished_ancient_id,
            cached_report=json.dumps({
                'name': 'Unknown Ancient Debris',
                'x': 3,
                'y': 3,
                'salvage_type': 'ANCIENT_DEBRIS',
                'report_tier': 'advanced',
            }),
        )
        Report.objects.create(
            game=game,
            player=other_player,
            year=game.year,
            target_type='salvage',
            target_id=vanished_ancient_id,
            cached_report=json.dumps({
                'name': 'Unknown Ancient Debris',
                'x': 3,
                'y': 3,
                'salvage_type': 'ANCIENT_DEBRIS',
                'report_tier': 'advanced',
            }),
        )

        user, _ = get_default_user()
        client = Client()
        client.force_login(user)
        response = client.get(
            reverse('dj4xol:diplomacy', args=[game.short_id]),
            {'target': other_player.short_id, 'compose': '1'},
        )

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'grant us report')
        self.assertContains(response, 'grant them report')
        self.assertContains(response, player_colony.name)
        self.assertContains(response, player_recent_colony.name)
        self.assertContains(response, '%s (their home)' % other_colony.name)
        self.assertContains(response, anomaly.name)
        self.assertContains(response, ancient.name)
        self.assertContains(response, 'value="star:%s"' % player_colony.id)
        self.assertContains(response, 'value="star:%s"' % player_recent_colony.id)
        self.assertContains(response, 'value="star:%s"' % other_colony.id)
        self.assertNotContains(response, 'value="star:%s"' % hidden_star.id)
        self.assertNotContains(response, wreck.name)
        self.assertNotContains(response, 'Shallow Echo')
        self.assertNotContains(response, 'Unknown Anomaly')
        self.assertNotContains(response, 'Unknown Ancient Debris')
        self.assertNotContains(response, 'colony %s' % player_colony.name)
        self.assertNotContains(response, 'anomaly %s' % anomaly.name)
        self.assertNotContains(response, 'ancient debris %s' % ancient.name)

    def test_diplomacy_colony_lists_put_homeworld_first(self):
        game = default_game(stars=6, fleets=0)
        player = game.players.first()
        race_type = get_default_race_type()
        other_user = User.objects.create_user('diplo_home_first', 'diplo_home_first@test.com', 'pass')
        other_account = Account.objects.create(django_user=other_user, alias='DHF')
        other_player = Player.objects.create(
            game=game,
            account=other_account,
            name='Home First Race',
            plural_name='Home First Races',
            race_type=race_type,
        )
        known_stars = list(game.stars.exclude(id=player.homeworld_id).order_by('id')[:3])
        other_home = known_stars[1]
        other_colony_a = known_stars[0]
        other_colony_b = known_stars[2]
        for star in (other_home, other_colony_a, other_colony_b):
            star.player = other_player
            star.save(update_fields=['player'])
            self._create_contact_star_report(game, player, other_player, star)
        other_player.homeworld = other_home
        other_player.save(update_fields=['homeworld'])

        user, _ = get_default_user()
        client = Client()
        client.force_login(user)
        response = client.get(
            reverse('dj4xol:diplomacy', args=[game.short_id]),
            {'target': other_player.short_id, 'compose': '1'},
        )

        self.assertEqual(response.status_code, 200)
        choices = response.context['request_colony_choices']
        self.assertGreaterEqual(len(choices), 3)
        self.assertEqual(choices[0]['label'], '%s (their home)' % other_home.name)
        remaining_labels = [choice['label'] for choice in choices[1:3]]
        self.assertIn(other_colony_a.name, remaining_labels)
        self.assertIn(other_colony_b.name, remaining_labels)

    def test_diplomacy_report_offer_can_be_granted_on_resource_completion(self):
        game = default_game(stars=5, fleets=0)
        player = game.players.first()
        race_type = get_default_race_type()
        other_user = User.objects.create_user('diplo_report_deferred', 'diplo_report_deferred@test.com', 'pass')
        other_account = Account.objects.create(django_user=other_user, alias='DRD')
        other_player = Player.objects.create(
            game=game,
            account=other_account,
            name='Deferred Report Race',
            plural_name='Deferred Report Races',
            race_type=race_type,
        )
        anomaly = Anomaly.objects.create(
            game=game,
            name='Veiled Rift',
            x=30,
            y=30,
            anomaly_type='WORMHOLE',
            description='Hidden wormhole.',
            heading=90,
            stability=65,
        )
        Report.objects.create(
            game=game,
            player=player,
            year=game.year,
            target_type='anomaly',
            target_id=anomaly.id,
            cached_report=json.dumps({
                'name': anomaly.name,
                'x': anomaly.x,
                'y': anomaly.y,
                'anomaly_type': anomaly.anomaly_type,
                'description': anomaly.description,
                'heading': anomaly.heading,
                'stability': anomaly.stability,
                'report_tier': 'encounter',
            }),
        )
        contract = DiplomaticContract.objects.create(
            game=game,
            sender=player,
            recipient=other_player,
            temperature='PROPOSE',
            status='ACCEPTED',
            sent_year=game.year,
            accepted_year=game.year,
            expires_year=game.year + 24,
            request_clause_type='RESOURCE_TO_WORLD',
            request_ironium=25,
            offer_condition_type='EXCHANGE',
            offer_clause_type='REPORT',
            offer_report_target_type='anomaly',
            offer_report_target_id=anomaly.id,
        )

        apply_world_resource_delivery(
            provider_player=other_player,
            receiving_player=player,
            bundle={'ironium': 25},
            year=game.year,
        )

        contract.refresh_from_db()
        self.assertEqual(contract.status, DiplomaticContract.STATUS_FULFILLED)
        shared_report = Report.objects.get(player=other_player, target_type='anomaly', target_id=anomaly.id)
        self.assertEqual(shared_report.get_report_data().get('report_tier'), 'encounter')

    def test_diplomacy_summary_keeps_do_nothing_exchange_wording(self):
        game = default_game(stars=5, fleets=0)
        player = game.players.first()
        race_type = get_default_race_type()
        other_user = User.objects.create_user('diplo_do_nothing_summary', 'diplo_do_nothing_summary@test.com', 'pass')
        other_account = Account.objects.create(django_user=other_user, alias='DDS')
        other_player = Player.objects.create(
            game=game,
            account=other_account,
            name='Summary Race',
            plural_name='Summary Races',
            race_type=race_type,
        )
        tech = Technology.objects.filter(enabled=True).order_by('level', 'id').first()
        contract = DiplomaticContract.objects.create(
            game=game,
            sender=player,
            recipient=other_player,
            temperature='DEMAND',
            status='SENT',
            sent_year=game.year,
            expires_year=game.year + 24,
            request_clause_type='NOTHING',
            offer_condition_type='EXCHANGE',
            offer_clause_type='TECHNOLOGY',
            offer_technology=tech,
        )

        summary = format_contract_summary(
            contract,
            viewer=other_player,
            include_links=False,
            include_sender_account=False,
        )

        self.assertIn('demand that we do nothing, in exchange they grant us technology', summary.lower())
        self.assertIn(tech.name, summary)
        self.assertNotIn('demands technology', summary.lower())

    def test_diplomacy_summary_includes_give_verb_for_transferred_fleet_resources(self):
        game = default_game(stars=5, fleets=0)
        player = game.players.first()
        race_type = get_default_race_type()
        other_user = User.objects.create_user('diplo_summary_giveverb', 'diplo_summary_giveverb@test.com', 'pass')
        other_account = Account.objects.create(django_user=other_user, alias='DSGV')
        other_player = Player.objects.create(
            game=game,
            account=other_account,
            name='Bradoid',
            plural_name='Bradoids',
            race_type=race_type,
        )
        tech = Technology.objects.filter(enabled=True).order_by('level', 'id').first()
        contract = DiplomaticContract.objects.create(
            game=game,
            sender=other_player,
            recipient=player,
            temperature='PROPOSE',
            status='SENT',
            sent_year=game.year,
            expires_year=game.year + 24,
            request_clause_type='RESOURCE_ON_GIVEN_FLEET',
            request_germanium=100,
            offer_condition_type='EXCHANGE',
            offer_clause_type='TECHNOLOGY',
            offer_technology=tech,
        )

        summary = format_contract_summary(
            contract,
            viewer=player,
            include_links=False,
            include_sender_account=False,
        )

        self.assertIn('propose that we give them a fleet carrying 100kt Germanium'.lower(), summary.lower())
        self.assertIn('in exchange they grant us technology', summary.lower())
        self.assertIn(tech.name, summary)

    def test_diplomacy_statement_matches_form_style_for_recipient(self):
        game = default_game(stars=5, fleets=0)
        player = game.players.first()
        race_type = get_default_race_type()
        other_user = User.objects.create_user('diplo_statement_recipient', 'diplo_statement_recipient@test.com', 'pass')
        other_account = Account.objects.create(django_user=other_user, alias='DSR')
        other_player = Player.objects.create(
            game=game,
            account=other_account,
            name='Statement Race',
            plural_name='Statement Races',
            race_type=race_type,
        )
        tech = Technology.objects.filter(enabled=True).order_by('level', 'id').first()
        contract = DiplomaticContract.objects.create(
            game=game,
            sender=player,
            recipient=other_player,
            temperature='DEMAND',
            status='SENT',
            sent_year=game.year,
            expires_year=game.year + 24,
            request_clause_type='NOTHING',
            offer_condition_type='EXCHANGE',
            offer_clause_type='TECHNOLOGY',
            offer_technology=tech,
        )

        statement = format_contract_statement(
            contract,
            viewer=other_player,
            include_links=False,
            include_sender_account=False,
        )

        self.assertIn('testers demand that we do nothing, in exchange they grant us technology', statement.lower())
        self.assertIn(tech.name, statement)
        self.assertNotIn('(admin)', statement)

    def test_diplomacy_statement_matches_form_style_for_sender(self):
        game = default_game(stars=5, fleets=0)
        player = game.players.first()
        race_type = get_default_race_type()
        other_user = User.objects.create_user('diplo_statement_sender', 'diplo_statement_sender@test.com', 'pass')
        other_account = Account.objects.create(django_user=other_user, alias='DSS')
        other_player = Player.objects.create(
            game=game,
            account=other_account,
            name='Receiver Race',
            plural_name='Receiver Races',
            race_type=race_type,
        )
        tech = Technology.objects.filter(enabled=True).order_by('level', 'id').first()
        contract = DiplomaticContract.objects.create(
            game=game,
            sender=player,
            recipient=other_player,
            temperature='DEMAND',
            status='SENT',
            sent_year=game.year,
            expires_year=game.year + 24,
            request_clause_type='NOTHING',
            offer_condition_type='EXCHANGE',
            offer_clause_type='TECHNOLOGY',
            offer_technology=tech,
        )

        statement = format_contract_statement(
            contract,
            viewer=player,
            include_links=False,
            include_sender_account=False,
        )

        self.assertIn('we demand that receiver races do nothing, in exchange we grant them technology', statement.lower())
        self.assertIn(tech.name, statement)
        self.assertNotIn('(admin)', statement)

    def test_diplomacy_statement_uses_vague_threat_wording_cleanly(self):
        game = default_game(stars=5, fleets=0)
        player = game.players.first()
        race_type = get_default_race_type()
        other_user = User.objects.create_user('diplo_statement_threat', 'diplo_statement_threat@test.com', 'pass')
        other_account = Account.objects.create(django_user=other_user, alias='DST')
        other_player = Player.objects.create(
            game=game,
            account=other_account,
            name='Threat Receiver',
            plural_name='Threat Receivers',
            race_type=race_type,
        )
        contract = DiplomaticContract.objects.create(
            game=game,
            sender=player,
            recipient=other_player,
            temperature='DEMAND',
            status='SENT',
            sent_year=game.year,
            expires_year=game.year + 24,
            request_clause_type='NOTHING',
            offer_condition_type='OR_ELSE',
            offer_clause_type='VAGUE_THREAT',
        )

        sender_statement = format_contract_statement(
            contract,
            viewer=player,
            include_links=False,
            include_sender_account=False,
        )
        recipient_statement = format_contract_statement(
            contract,
            viewer=other_player,
            include_links=False,
            include_sender_account=False,
        )
        summary = format_contract_summary(
            contract,
            viewer=other_player,
            include_links=False,
            include_sender_account=False,
        )
        phrase = vague_threat_phrase(contract)

        self.assertIn(phrase, VAGUE_THREAT_PHRASES)
        self.assertEqual(phrase, vague_threat_phrase(contract))
        self.assertIn(('we demand that threat receivers do nothing, or else we %s.' % phrase).lower(), sender_statement.lower())
        self.assertIn(('testers demand that we do nothing, or else they %s.' % phrase).lower(), recipient_statement.lower())
        self.assertIn(('demand that we do nothing, or else they %s.' % phrase).lower(), summary.lower())

    def test_diplomacy_form_allows_or_else_with_do_nothing_request(self):
        game = default_game(stars=5, fleets=0)
        player = game.players.first()
        race_type = get_default_race_type()
        other_user = User.objects.create_user('diplo_or_else_nothing', 'diplo_or_else_nothing@test.com', 'pass')
        other_account = Account.objects.create(django_user=other_user, alias='DON')
        other_player = Player.objects.create(
            game=game,
            account=other_account,
            name='Ridiculous Race',
            plural_name='Ridiculous Races',
            race_type=race_type,
        )
        contract, errors = _diplomacy_parse_contract(
            player,
            other_player,
            {
                'temperature': 'DEMAND',
                'request_clause_type': 'NOTHING',
                'offer_condition_type': 'OR_ELSE',
                'offer_clause_type': 'VAGUE_THREAT',
                'deadline_years': '24',
                'extend_on_accept_years': '0',
            },
            available_offer_techs={},
            available_request_techs={},
            available_request_stars={},
            available_offer_stars={},
            available_request_reports={},
            available_offer_reports={},
        )
        self.assertEqual(errors, [])
        self.assertEqual(contract.request_clause_type, DiplomaticContract.CLAUSE_NOTHING)
        self.assertEqual(contract.offer_condition_type, DiplomaticContract.CONDITION_OR_ELSE)
        self.assertEqual(contract.offer_clause_type, DiplomaticContract.CLAUSE_VAGUE_THREAT)

    def test_do_nothing_or_else_only_triggers_consequence_on_decline_not_accept(self):
        game = default_game(stars=5, fleets=0)
        player = game.players.first()
        race_type = get_default_race_type()
        other_user = User.objects.create_user('diplo_or_else_outcome', 'diplo_or_else_outcome@test.com', 'pass')
        other_account = Account.objects.create(django_user=other_user, alias='DOO')
        other_player = Player.objects.create(
            game=game,
            account=other_account,
            name='Outcome Race',
            plural_name='Outcome Races',
            race_type=race_type,
        )

        accepted_contract = DiplomaticContract.objects.create(
            game=game,
            sender=player,
            recipient=other_player,
            temperature='DEMAND',
            status='SENT',
            sent_year=game.year,
            expires_year=game.year + 24,
            request_clause_type='NOTHING',
            offer_condition_type='OR_ELSE',
            offer_clause_type='STANCE',
            offer_stance='HOSTILE',
        )
        ok, _message = accept_contract(accepted_contract, other_player)
        self.assertTrue(ok)
        accepted_contract.refresh_from_db()
        self.assertEqual(accepted_contract.status, DiplomaticContract.STATUS_FULFILLED)
        self.assertFalse(
            PlayerDiplomaticStance.objects.filter(
                player=player,
                target_player=other_player,
            ).exists()
        )

        declined_contract = DiplomaticContract.objects.create(
            game=game,
            sender=player,
            recipient=other_player,
            temperature='DEMAND',
            status='SENT',
            sent_year=game.year,
            expires_year=game.year + 24,
            request_clause_type='NOTHING',
            offer_condition_type='OR_ELSE',
            offer_clause_type='STANCE',
            offer_stance='HOSTILE',
        )
        ok, _message = decline_contract(declined_contract, other_player)
        self.assertTrue(ok)
        stance = PlayerDiplomaticStance.objects.get(
            player=player,
            target_player=other_player,
        )
        self.assertEqual(stance.pending_stance, 'HOSTILE')

    def test_accept_contract_status_messages_use_correct_perspective_and_priority(self):
        game = default_game(stars=5, fleets=0)
        player = game.players.first()
        race_type = get_default_race_type()
        other_user = User.objects.create_user('diplo_accept_msg', 'diplo_accept_msg@test.com', 'pass')
        other_account = Account.objects.create(django_user=other_user, alias='DAM')
        other_player = Player.objects.create(
            game=game,
            account=other_account,
            name='Accept Race',
            plural_name='Accept Races',
            race_type=race_type,
        )
        contract = DiplomaticContract.objects.create(
            game=game,
            sender=player,
            recipient=other_player,
            temperature='REQUEST',
            status='SENT',
            sent_year=game.year,
            expires_year=game.year + 24,
            request_clause_type='RESOURCE_TO_WORLD',
            request_ironium=25,
            offer_clause_type='NOTHING',
        )

        ok, _message = accept_contract(contract, other_player)

        self.assertTrue(ok)
        sender_msg = player.messages.filter(category='DIPLOMATIC').latest('id')
        recipient_msg = other_player.messages.filter(category='DIPLOMATIC').latest('id')
        self.assertTrue(sender_msg.priority)
        self.assertTrue(recipient_msg.priority)
        self.assertIn('Diplomatic request accepted by Accept Races:', sender_msg.message)
        self.assertIn('We accepted diplomatic request from Testers:', recipient_msg.message)

    def test_decline_contract_status_messages_use_correct_perspective_and_priority(self):
        game = default_game(stars=5, fleets=0)
        player = game.players.first()
        race_type = get_default_race_type()
        other_user = User.objects.create_user('diplo_decline_msg', 'diplo_decline_msg@test.com', 'pass')
        other_account = Account.objects.create(django_user=other_user, alias='DDM')
        other_player = Player.objects.create(
            game=game,
            account=other_account,
            name='Decline Race',
            plural_name='Decline Races',
            race_type=race_type,
        )
        contract = DiplomaticContract.objects.create(
            game=game,
            sender=player,
            recipient=other_player,
            temperature='REQUEST',
            status='SENT',
            sent_year=game.year,
            expires_year=game.year + 24,
            request_clause_type='STANCE',
            request_stance='COLD',
            offer_clause_type='NOTHING',
        )

        ok, _message = decline_contract(contract, other_player)

        self.assertTrue(ok)
        sender_msg = player.messages.filter(category='DIPLOMATIC').latest('id')
        recipient_msg = other_player.messages.filter(category='DIPLOMATIC').latest('id')
        self.assertTrue(sender_msg.priority)
        self.assertTrue(recipient_msg.priority)
        self.assertIn('Diplomatic request declined by Decline Races:', sender_msg.message)
        self.assertIn('We declined diplomatic request from Testers:', recipient_msg.message)

    def test_expired_contract_status_messages_use_correct_perspective_and_priority(self):
        game = default_game(stars=5, fleets=0)
        player = game.players.first()
        race_type = get_default_race_type()
        other_user = User.objects.create_user('diplo_expire_msg', 'diplo_expire_msg@test.com', 'pass')
        other_account = Account.objects.create(django_user=other_user, alias='DEM')
        other_player = Player.objects.create(
            game=game,
            account=other_account,
            name='Expire Race',
            plural_name='Expire Races',
            race_type=race_type,
        )
        contract = DiplomaticContract.objects.create(
            game=game,
            sender=player,
            recipient=other_player,
            temperature='REQUEST',
            status='SENT',
            sent_year=game.year,
            expires_year=game.year - 1,
            request_clause_type='STANCE',
            request_stance='NEUTRAL',
            offer_clause_type='NOTHING',
        )

        refresh_contract_integrity(game)

        contract.refresh_from_db()
        self.assertEqual(contract.status, DiplomaticContract.STATUS_EXPIRED)
        sender_msg = player.messages.filter(category='DIPLOMATIC').latest('id')
        recipient_msg = other_player.messages.filter(category='DIPLOMATIC').latest('id')
        self.assertTrue(sender_msg.priority)
        self.assertTrue(recipient_msg.priority)
        self.assertIn('Diplomatic request to Expire Races expired:', sender_msg.message)
        self.assertIn('Diplomatic request from Testers expired:', recipient_msg.message)

    def test_extend_contract_helper_increases_expiry(self):
        game = default_game(stars=5, fleets=0)
        player = game.players.first()
        race_type = get_default_race_type()
        other_user = User.objects.create_user('diplo_extend_helper', 'diplo_extend_helper@test.com', 'pass')
        other_account = Account.objects.create(django_user=other_user, alias='DEH')
        other_player = Player.objects.create(
            game=game,
            account=other_account,
            name='Extend Race',
            plural_name='Extend Races',
            race_type=race_type,
        )
        contract = DiplomaticContract.objects.create(
            game=game,
            sender=player,
            recipient=other_player,
            temperature='REQUEST',
            status='SENT',
            sent_year=game.year,
            expires_year=game.year + 24,
            request_clause_type='STANCE',
            request_stance='WARM',
            offer_clause_type='NOTHING',
        )

        ok, message = extend_contract(contract, player, 6)

        self.assertTrue(ok)
        self.assertEqual(message, 'Request extended.')
        contract.refresh_from_db()
        self.assertEqual(contract.expires_year, game.year + 30)

    def test_diplomacy_can_send_technology_request_and_offer_from_form(self):
        game = default_game(stars=5, fleets=0)
        player = game.players.first()
        race_type = get_default_race_type()
        other_user = User.objects.create_user('diplo_contract_tech_form', 'diplo_contract_tech_form@test.com', 'pass')
        other_account = Account.objects.create(django_user=other_user, alias='DTF')
        other_player = Player.objects.create(
            game=game,
            account=other_account,
            name='Tech Race',
            plural_name='Tech Races',
            race_type=race_type,
        )
        contact_star = game.stars.exclude(id=player.homeworld_id).first()
        contact_star.player = other_player
        contact_star.save(update_fields=['player'])
        Report.objects.create(
            game=game,
            player=player,
            year=game.year,
            target_type='star',
            target_id=contact_star.id,
            cached_report=json.dumps({
                'name': contact_star.name,
                'x': contact_star.x,
                'y': contact_star.y,
                'player_name': other_player.name,
                'report_tier': 'encounter',
            }),
        )
        player_tech = get_player_unlocked_technologies(player)[0]
        other_rows = ensure_player_research_rows(other_player)
        target_row = next(row for row in other_rows if row.category_id == player_tech.category_id)
        target_row.current_level = player_tech.level
        target_row.save(update_fields=['current_level'])
        other_tech = get_player_unlocked_technologies(other_player)[0]

        user, _ = get_default_user()
        client = Client()
        client.force_login(user)
        response = client.post(
            reverse('dj4xol:diplomacy', args=[game.short_id]),
            {
                'target': other_player.short_id,
                'action': 'send_contract',
                'temperature': 'PROPOSE',
                'deadline_years': '24',
                'extend_on_accept_years': '0',
                'request_clause_type': 'TECHNOLOGY',
                'request_technology': str(other_tech.id),
                'offer_condition_type': 'EXCHANGE',
                'offer_clause_type': 'TECHNOLOGY',
                'offer_technology': str(player_tech.id),
            },
        )

        self.assertEqual(response.status_code, 302)
        contract = DiplomaticContract.objects.get(
            sender=player,
            recipient=other_player,
            request_clause_type='TECHNOLOGY',
            offer_clause_type='TECHNOLOGY',
        )
        self.assertEqual(contract.request_technology_id, other_tech.id)
        self.assertEqual(contract.offer_technology_id, player_tech.id)

    def test_diplomacy_compose_only_lists_known_foreign_colonies_for_request(self):
        game = default_game(stars=6, fleets=0)
        player = game.players.first()
        race_type = get_default_race_type()
        other_user = User.objects.create_user('diplo_known_colony', 'diplo_known_colony@test.com', 'pass')
        other_account = Account.objects.create(django_user=other_user, alias='DKC')
        other_player = Player.objects.create(
            game=game,
            account=other_account,
            name='Known Colony Race',
            plural_name='Known Colony Races',
            race_type=race_type,
        )
        known_colony = game.stars.exclude(id=player.homeworld_id).order_by('id').first()
        hidden_colony = game.stars.exclude(id__in=[player.homeworld_id, known_colony.id]).order_by('id').first()
        known_colony.colonists = 60
        known_colony.save(update_fields=['colonists'])
        hidden_colony.player = other_player
        hidden_colony.colonists = 45
        hidden_colony.save(update_fields=['player', 'colonists'])
        self._create_contact_star_report(game, player, other_player, known_colony)

        user, _ = get_default_user()
        client = Client()
        client.force_login(user)
        response = client.get(
            reverse('dj4xol:diplomacy', args=[game.short_id]),
            {'target': other_player.short_id, 'compose': '1'},
        )

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'name="request_star"')
        self.assertContains(response, 'value="%s"' % known_colony.id)
        self.assertContains(response, '>%s</option>' % known_colony.name, html=False)
        self.assertNotContains(response, 'value="%s"' % hidden_colony.id)
        self.assertNotContains(response, '>%s</option>' % hidden_colony.name, html=False)

    def test_diplomacy_can_request_colony_from_form_and_accept_transfers_owner(self):
        game = default_game(stars=5, fleets=0)
        player = game.players.first()
        race_type = get_default_race_type()
        other_user = User.objects.create_user('diplo_request_colony', 'diplo_request_colony@test.com', 'pass')
        other_account = Account.objects.create(django_user=other_user, alias='DRC')
        other_player = Player.objects.create(
            game=game,
            account=other_account,
            name='Colony Request Race',
            plural_name='Colony Request Races',
            race_type=race_type,
        )
        contact_star = game.stars.exclude(id=player.homeworld_id).order_by('id').first()
        contact_star.colonists = 75
        contact_star.save(update_fields=['colonists'])
        self._create_contact_star_report(game, player, other_player, contact_star)

        user, _ = get_default_user()
        client = Client()
        client.force_login(user)
        response = client.post(
            reverse('dj4xol:diplomacy', args=[game.short_id]),
            {
                'target': other_player.short_id,
                'action': 'send_contract',
                'temperature': 'PROPOSE',
                'deadline_years': '24',
                'extend_on_accept_years': '0',
                'request_clause_type': 'SPECIFIC_COLONY',
                'request_star': str(contact_star.id),
                'offer_clause_type': 'NOTHING',
            },
        )

        self.assertEqual(response.status_code, 302)
        contract = DiplomaticContract.objects.get(
            sender=player,
            recipient=other_player,
            request_clause_type='SPECIFIC_COLONY',
        )
        self.assertEqual(contract.request_star_id, contact_star.id)

        other_client = Client()
        other_client.force_login(other_user)
        response = other_client.post(
            reverse('dj4xol:diplomacy', args=[game.short_id]),
            {
                'target': player.short_id,
                'action': 'accept_contract',
                'contract_id': contract.short_id,
            },
        )

        self.assertEqual(response.status_code, 302)
        contract.refresh_from_db()
        contact_star.refresh_from_db()
        self.assertEqual(contract.status, DiplomaticContract.STATUS_FULFILLED)
        self.assertEqual(contact_star.player_id, player.id)

    def test_diplomacy_can_offer_colony_and_accept_transfers_owner(self):
        game = default_game(stars=6, fleets=0)
        player = game.players.first()
        race_type = get_default_race_type()
        other_user = User.objects.create_user('diplo_offer_colony', 'diplo_offer_colony@test.com', 'pass')
        other_account = Account.objects.create(django_user=other_user, alias='DOC')
        other_player = Player.objects.create(
            game=game,
            account=other_account,
            name='Colony Offer Race',
            plural_name='Colony Offer Races',
            race_type=race_type,
        )
        contact_star = game.stars.exclude(id=player.homeworld_id).order_by('id').first()
        self._create_contact_star_report(game, player, other_player, contact_star)
        offered_colony = game.stars.exclude(id__in=[player.homeworld_id, contact_star.id]).order_by('id').first()
        offered_colony.player = player
        offered_colony.colonists = 55
        offered_colony.save(update_fields=['player', 'colonists'])

        user, _ = get_default_user()
        client = Client()
        client.force_login(user)
        response = client.post(
            reverse('dj4xol:diplomacy', args=[game.short_id]),
            {
                'target': other_player.short_id,
                'action': 'send_contract',
                'temperature': 'PROPOSE',
                'deadline_years': '24',
                'extend_on_accept_years': '0',
                'request_clause_type': 'NOTHING',
                'offer_condition_type': 'EXCHANGE',
                'offer_clause_type': 'SPECIFIC_COLONY',
                'offer_star': str(offered_colony.id),
            },
        )

        self.assertEqual(response.status_code, 302)
        contract = DiplomaticContract.objects.get(
            sender=player,
            recipient=other_player,
            offer_clause_type='SPECIFIC_COLONY',
        )
        self.assertEqual(contract.offer_star_id, offered_colony.id)

        other_client = Client()
        other_client.force_login(other_user)
        response = other_client.post(
            reverse('dj4xol:diplomacy', args=[game.short_id]),
            {
                'target': player.short_id,
                'action': 'accept_contract',
                'contract_id': contract.short_id,
            },
        )

        self.assertEqual(response.status_code, 302)
        contract.refresh_from_db()
        offered_colony.refresh_from_db()
        self.assertEqual(contract.status, DiplomaticContract.STATUS_FULFILLED)
        self.assertEqual(offered_colony.player_id, other_player.id)

    def test_diplomacy_specific_fleet_offer_includes_preview_report_by_default(self):
        game = default_game(stars=5, fleets=0)
        player = game.players.first()
        race_type = get_default_race_type()
        other_user = User.objects.create_user('diplo_fleet_preview', 'diplo_fleet_preview@test.com', 'pass')
        other_account = Account.objects.create(django_user=other_user, alias='DFP')
        other_player = Player.objects.create(
            game=game,
            account=other_account,
            name='Preview Race',
            plural_name='Preview Races',
            race_type=race_type,
        )
        contact_star = game.stars.exclude(id=player.homeworld_id).order_by('id').first()
        self._create_contact_star_report(game, player, other_player, contact_star)
        offered_fleet = Fleet.objects.create(
            game=game,
            player=player,
            name='Sales Pitch',
            x=player.homeworld.x,
            y=player.homeworld.y,
            ship_count=2,
            integrity=100,
            ironium_inventory=12,
        )

        user, _ = get_default_user()
        client = Client()
        client.force_login(user)
        response = client.post(
            reverse('dj4xol:diplomacy', args=[game.short_id]),
            {
                'target': other_player.short_id,
                'action': 'send_contract',
                'temperature': 'PROPOSE',
                'deadline_years': '24',
                'extend_on_accept_years': '0',
                'request_clause_type': 'NOTHING',
                'offer_condition_type': 'EXCHANGE',
                'offer_clause_type': 'SPECIFIC_FLEET',
                'offer_fleet': str(offered_fleet.id),
                'offer_fleet_include_report': '1',
            },
        )

        self.assertEqual(response.status_code, 302)
        contract = DiplomaticContract.objects.get(
            sender=player,
            recipient=other_player,
            offer_clause_type='SPECIFIC_FLEET',
            offer_fleet=offered_fleet,
        )
        self.assertTrue(contract.offer_fleet_include_report)
        preview_report = Report.objects.get(
            game=game,
            player=other_player,
            target_type='fleet',
            target_id=offered_fleet.id,
        )
        cached = json.loads(preview_report.cached_report)
        self.assertEqual(cached.get('report_tier'), 'encounter')
        self.assertEqual(cached.get('name'), offered_fleet.name)
        self.assertEqual(cached.get('ironium_inventory'), 12)

    def test_diplomacy_specific_fleet_offer_can_skip_preview_report(self):
        game = default_game(stars=5, fleets=0)
        player = game.players.first()
        race_type = get_default_race_type()
        other_user = User.objects.create_user('diplo_no_fleet_preview', 'diplo_no_fleet_preview@test.com', 'pass')
        other_account = Account.objects.create(django_user=other_user, alias='DNP')
        other_player = Player.objects.create(
            game=game,
            account=other_account,
            name='No Preview Race',
            plural_name='No Preview Races',
            race_type=race_type,
        )
        contact_star = game.stars.exclude(id=player.homeworld_id).order_by('id').first()
        self._create_contact_star_report(game, player, other_player, contact_star)
        offered_fleet = Fleet.objects.create(
            game=game,
            player=player,
            name='Silent Sale',
            x=player.homeworld.x,
            y=player.homeworld.y,
            ship_count=2,
            integrity=100,
        )

        user, _ = get_default_user()
        client = Client()
        client.force_login(user)
        response = client.post(
            reverse('dj4xol:diplomacy', args=[game.short_id]),
            {
                'target': other_player.short_id,
                'action': 'send_contract',
                'temperature': 'PROPOSE',
                'deadline_years': '24',
                'extend_on_accept_years': '0',
                'request_clause_type': 'NOTHING',
                'offer_condition_type': 'EXCHANGE',
                'offer_clause_type': 'SPECIFIC_FLEET',
                'offer_fleet': str(offered_fleet.id),
            },
        )

        self.assertEqual(response.status_code, 302)
        contract = DiplomaticContract.objects.get(
            sender=player,
            recipient=other_player,
            offer_clause_type='SPECIFIC_FLEET',
            offer_fleet=offered_fleet,
        )
        self.assertFalse(contract.offer_fleet_include_report)
        self.assertFalse(
            Report.objects.filter(
                game=game,
                player=other_player,
                target_type='fleet',
                target_id=offered_fleet.id,
            ).exists()
        )

    def test_diplomacy_specific_fleet_transfer_resets_travel_warp_but_keeps_heading(self):
        game = default_game(stars=5, fleets=0)
        player = game.players.first()
        race_type = get_default_race_type()
        other_user = User.objects.create_user('diplo_offer_fleet', 'diplo_offer_fleet@test.com', 'pass')
        other_account = Account.objects.create(django_user=other_user, alias='DOF')
        other_player = Player.objects.create(
            game=game,
            account=other_account,
            name='Fleet Offer Race',
            plural_name='Fleet Offer Races',
            race_type=race_type,
        )
        contact_star = game.stars.exclude(id=player.homeworld_id).order_by('id').first()
        self._create_contact_star_report(game, player, other_player, contact_star)
        offered_fleet = Fleet.objects.create(
            game=game,
            player=player,
            name='Treaty Courier',
            x=player.homeworld.x,
            y=player.homeworld.y,
            ship_count=2,
            integrity=100,
            heading=271.5,
            travel_warp=6,
        )

        contract = DiplomaticContract.objects.create(
            game=game,
            sender=player,
            recipient=other_player,
            temperature='PROPOSE',
            status='SENT',
            sent_year=game.year,
            expires_year=game.year + 24,
            request_clause_type='NOTHING',
            offer_condition_type='EXCHANGE',
            offer_clause_type='SPECIFIC_FLEET',
            offer_fleet=offered_fleet,
        )

        other_client = Client()
        other_client.force_login(other_user)
        response = other_client.post(
            reverse('dj4xol:diplomacy', args=[game.short_id]),
            {
                'target': player.short_id,
                'action': 'accept_contract',
                'contract_id': contract.short_id,
            },
        )

        self.assertEqual(response.status_code, 302)
        contract.refresh_from_db()
        offered_fleet.refresh_from_db()
        self.assertEqual(contract.status, DiplomaticContract.STATUS_FULFILLED)
        self.assertEqual(offered_fleet.player_id, other_player.id)
        self.assertEqual(offered_fleet.travel_warp, 0)
        self.assertAlmostEqual(float(offered_fleet.heading), 271.5, places=1)

    def test_diplomacy_colony_transfer_evacuates_population_into_owner_orbiting_fleets(self):
        game = default_game(stars=6, fleets=1)
        player = game.players.first()
        race_type = get_default_race_type()
        other_user = User.objects.create_user('diplo_colony_evac', 'diplo_colony_evac@test.com', 'pass')
        other_account = Account.objects.create(django_user=other_user, alias='DCE')
        other_player = Player.objects.create(
            game=game,
            account=other_account,
            name='Evac Race',
            plural_name='Evac Races',
            race_type=race_type,
        )
        contact_star = game.stars.exclude(id=player.homeworld_id).order_by('id').first()
        self._create_contact_star_report(game, player, other_player, contact_star)
        offered_colony = game.stars.exclude(id__in=[player.homeworld_id, contact_star.id]).order_by('id').first()
        offered_colony.player = player
        offered_colony.colonists = 80000
        offered_colony.save(update_fields=['player', 'colonists'])

        orbiting_fleet = player.fleets.first()
        orbiting_fleet.x = offered_colony.x
        orbiting_fleet.y = offered_colony.y
        orbiting_fleet.cargo_capacity = 60
        orbiting_fleet.colonists = 0
        orbiting_fleet.save(update_fields=['x', 'y', 'cargo_capacity', 'colonists'])

        user, _ = get_default_user()
        client = Client()
        client.force_login(user)
        response = client.post(
            reverse('dj4xol:diplomacy', args=[game.short_id]),
            {
                'target': other_player.short_id,
                'action': 'send_contract',
                'temperature': 'PROPOSE',
                'deadline_years': '24',
                'extend_on_accept_years': '0',
                'request_clause_type': 'NOTHING',
                'offer_condition_type': 'EXCHANGE',
                'offer_clause_type': 'SPECIFIC_COLONY',
                'offer_star': str(offered_colony.id),
            },
        )

        self.assertEqual(response.status_code, 302)
        contract = DiplomaticContract.objects.get(
            sender=player,
            recipient=other_player,
            offer_clause_type='SPECIFIC_COLONY',
        )

        other_client = Client()
        other_client.force_login(other_user)
        response = other_client.post(
            reverse('dj4xol:diplomacy', args=[game.short_id]),
            {
                'target': player.short_id,
                'action': 'accept_contract',
                'contract_id': contract.short_id,
            },
        )

        self.assertEqual(response.status_code, 302)
        offered_colony.refresh_from_db()
        orbiting_fleet.refresh_from_db()
        self.assertEqual(offered_colony.player_id, other_player.id)
        self.assertEqual(orbiting_fleet.colonists, 60)
        self.assertEqual(offered_colony.colonists, 20000)

    def test_diplomacy_shows_colony_transfer_warnings_in_compose_and_accept_views(self):
        game = default_game(stars=6, fleets=0)
        player = game.players.first()
        race_type = get_default_race_type()
        other_user = User.objects.create_user('diplo_colony_warning', 'diplo_colony_warning@test.com', 'pass')
        other_account = Account.objects.create(django_user=other_user, alias='DCW')
        other_player = Player.objects.create(
            game=game,
            account=other_account,
            name='Warning Race',
            plural_name='Warning Races',
            race_type=race_type,
        )
        contact_star = game.stars.exclude(id=player.homeworld_id).order_by('id').first()
        self._create_contact_star_report(game, player, other_player, contact_star)
        offered_colony = game.stars.exclude(id__in=[player.homeworld_id, contact_star.id]).order_by('id').first()
        offered_colony.player = player
        offered_colony.colonists = 50000
        offered_colony.save(update_fields=['player', 'colonists'])

        user, _ = get_default_user()
        client = Client()
        client.force_login(user)
        compose_response = client.post(
            reverse('dj4xol:diplomacy', args=[game.short_id]),
            {
                'target': other_player.short_id,
                'action': 'send_contract',
                'temperature': 'PROPOSE',
                'deadline_years': '24',
                'extend_on_accept_years': '0',
                'request_clause_type': 'NOTHING',
                'offer_condition_type': 'EXCHANGE',
                'offer_clause_type': 'SPECIFIC_COLONY',
            },
        )

        self.assertEqual(compose_response.status_code, 200)
        self.assertContains(compose_response, 'up to 75% of its population may evacuate into your orbiting fleets')

        contract = DiplomaticContract.objects.create(
            game=game,
            sender=other_player,
            recipient=player,
            temperature='REQUEST',
            status='SENT',
            sent_year=game.year,
            expires_year=game.year + 24,
            request_clause_type='SPECIFIC_COLONY',
            request_star=offered_colony,
            offer_clause_type='NOTHING',
        )

        accept_response = client.get(
            reverse('dj4xol:diplomacy', args=[game.short_id]),
            {'target': other_player.short_id, 'contract': contract.short_id},
        )

        self.assertEqual(accept_response.status_code, 200)
        self.assertContains(accept_response, 'accepting this request will transfer the colony immediately')

    def test_diplomacy_homeworld_label_and_warning_show_when_offering_homeworld(self):
        game = default_game(stars=5, fleets=0)
        player = game.players.first()
        race_type = get_default_race_type()
        other_user = User.objects.create_user('diplo_homeworld_warning', 'diplo_homeworld_warning@test.com', 'pass')
        other_account = Account.objects.create(django_user=other_user, alias='DHW')
        other_player = Player.objects.create(
            game=game,
            account=other_account,
            name='Homeworld Warning Race',
            plural_name='Homeworld Warning Races',
            race_type=race_type,
        )
        contact_star = game.stars.exclude(id=player.homeworld_id).order_by('id').first()
        self._create_contact_star_report(game, player, other_player, contact_star)

        user, _ = get_default_user()
        client = Client()
        client.force_login(user)
        response = client.get(
            reverse('dj4xol:diplomacy', args=[game.short_id]),
            {'target': other_player.short_id, 'compose': '1'},
        )

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, '%s (home)' % player.homeworld.name)

        player.turned_in = True
        player.save(update_fields=['turned_in'])
        response = client.post(
            reverse('dj4xol:diplomacy', args=[game.short_id]),
            {
                'target': other_player.short_id,
                'action': 'send_contract',
                'temperature': 'PROPOSE',
                'deadline_years': '24',
                'extend_on_accept_years': '0',
                'request_clause_type': 'NOTHING',
                'offer_condition_type': 'EXCHANGE',
                'offer_clause_type': 'SPECIFIC_COLONY',
                'offer_star': str(player.homeworld_id),
            },
        )

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'you are giving away your homeworld')

        player.turned_in = False
        player.save(update_fields=['turned_in'])
        contract = DiplomaticContract.objects.create(
            game=game,
            sender=other_player,
            recipient=player,
            temperature='REQUEST',
            status='SENT',
            sent_year=game.year,
            expires_year=game.year + 24,
            request_clause_type='SPECIFIC_COLONY',
            request_star=player.homeworld,
            offer_clause_type='NOTHING',
        )
        response = client.get(
            reverse('dj4xol:diplomacy', args=[game.short_id]),
            {'target': other_player.short_id, 'contract': contract.short_id},
        )

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'accepting this request will give away your homeworld')

    def test_diplomacy_giving_homeworld_reassigns_to_next_most_populous_colony(self):
        game = default_game(stars=6, fleets=0)
        player = game.players.first()
        race_type = get_default_race_type()
        other_user = User.objects.create_user('diplo_homeworld_reassign', 'diplo_homeworld_reassign@test.com', 'pass')
        other_account = Account.objects.create(django_user=other_user, alias='DHR')
        other_player = Player.objects.create(
            game=game,
            account=other_account,
            name='Homeworld Reassign Race',
            plural_name='Homeworld Reassign Races',
            race_type=race_type,
        )
        contact_star = game.stars.exclude(id=player.homeworld_id).order_by('id').first()
        self._create_contact_star_report(game, player, other_player, contact_star)
        secondary = game.stars.exclude(id__in=[player.homeworld_id, contact_star.id]).order_by('id').first()
        secondary.player = player
        secondary.colonists = 90000
        secondary.save(update_fields=['player', 'colonists'])

        contract = DiplomaticContract.objects.create(
            game=game,
            sender=player,
            recipient=other_player,
            temperature='PROPOSE',
            status='SENT',
            sent_year=game.year,
            expires_year=game.year + 24,
            request_clause_type='NOTHING',
            offer_condition_type='EXCHANGE',
            offer_clause_type='SPECIFIC_COLONY',
            offer_star=player.homeworld,
        )

        other_client = Client()
        other_client.force_login(other_user)
        response = other_client.post(
            reverse('dj4xol:diplomacy', args=[game.short_id]),
            {
                'target': player.short_id,
                'action': 'accept_contract',
                'contract_id': contract.short_id,
            },
        )

        self.assertEqual(response.status_code, 302)
        player.refresh_from_db()
        self.assertFalse(player.defeated)
        self.assertEqual(player.homeworld_id, secondary.id)

    def test_diplomacy_giving_homeworld_without_replacement_defeats_player(self):
        game = default_game(stars=5, fleets=0)
        player = game.players.first()
        race_type = get_default_race_type()
        other_user = User.objects.create_user('diplo_homeworld_defeat', 'diplo_homeworld_defeat@test.com', 'pass')
        other_account = Account.objects.create(django_user=other_user, alias='DHD')
        other_player = Player.objects.create(
            game=game,
            account=other_account,
            name='Homeworld Defeat Race',
            plural_name='Homeworld Defeat Races',
            race_type=race_type,
        )
        contact_star = game.stars.exclude(id=player.homeworld_id).order_by('id').first()
        self._create_contact_star_report(game, player, other_player, contact_star)

        contract = DiplomaticContract.objects.create(
            game=game,
            sender=player,
            recipient=other_player,
            temperature='PROPOSE',
            status='SENT',
            sent_year=game.year,
            expires_year=game.year + 24,
            request_clause_type='NOTHING',
            offer_condition_type='EXCHANGE',
            offer_clause_type='SPECIFIC_COLONY',
            offer_star=player.homeworld,
        )

        other_client = Client()
        other_client.force_login(other_user)
        response = other_client.post(
            reverse('dj4xol:diplomacy', args=[game.short_id]),
            {
                'target': player.short_id,
                'action': 'accept_contract',
                'contract_id': contract.short_id,
            },
        )

        self.assertEqual(response.status_code, 302)
        player.refresh_from_db()
        self.assertTrue(player.defeated)
        self.assertIsNone(player.homeworld_id)

    def test_diplomacy_homeworld_for_colony_swap_avoids_defeat_and_rehomes_both_players(self):
        game = default_game(stars=5, fleets=0)
        player = game.players.first()
        player.homeworld.colonists = 70000
        player.homeworld.save(update_fields=['colonists'])
        race_type = get_default_race_type()
        other_user = User.objects.create_user('diplo_homeworld_swap', 'diplo_homeworld_swap@test.com', 'pass')
        other_account = Account.objects.create(django_user=other_user, alias='DHS')
        other_player = Player.objects.create(
            game=game,
            account=other_account,
            name='Swap Race',
            plural_name='Swap Races',
            race_type=race_type,
            homeworld=game.stars.exclude(id=player.homeworld_id).order_by('id').first(),
        )
        other_player.homeworld.player = other_player
        other_player.homeworld.colonists = 65000
        other_player.homeworld.save(update_fields=['player', 'colonists'])
        self._create_contact_star_report(game, player, other_player, other_player.homeworld)

        contract = DiplomaticContract.objects.create(
            game=game,
            sender=player,
            recipient=other_player,
            temperature='PROPOSE',
            status='SENT',
            sent_year=game.year,
            expires_year=game.year + 24,
            request_clause_type='SPECIFIC_COLONY',
            request_star=other_player.homeworld,
            offer_condition_type='EXCHANGE',
            offer_clause_type='SPECIFIC_COLONY',
            offer_star=player.homeworld,
        )

        other_client = Client()
        other_client.force_login(other_user)
        response = other_client.post(
            reverse('dj4xol:diplomacy', args=[game.short_id]),
            {
                'target': player.short_id,
                'action': 'accept_contract',
                'contract_id': contract.short_id,
            },
        )

        self.assertEqual(response.status_code, 302)
        player.refresh_from_db()
        other_player.refresh_from_db()
        self.assertFalse(player.defeated)
        self.assertFalse(other_player.defeated)
        self.assertEqual(player.homeworld_id, contract.request_star_id)
        self.assertEqual(other_player.homeworld_id, contract.offer_star_id)

    def test_accept_contract_specific_colony_creates_priority_transfer_messages(self):
        game = default_game(stars=5, fleets=0)
        player = game.players.first()
        extra_colony = game.stars.exclude(id=player.homeworld_id).order_by('id').first()
        extra_colony.player = player
        extra_colony.colonists = 45000
        extra_colony.save(update_fields=['player', 'colonists'])
        race_type = get_default_race_type()
        other_user = User.objects.create_user('diplo_colony_msg', 'diplo_colony_msg@test.com', 'pass')
        other_account = Account.objects.create(django_user=other_user, alias='DCM')
        other_player = Player.objects.create(
            game=game,
            account=other_account,
            name='Recipient Race',
            plural_name='Recipient Races',
            race_type=race_type,
        )

        contract = DiplomaticContract.objects.create(
            game=game,
            sender=player,
            recipient=other_player,
            temperature='PROPOSE',
            status='SENT',
            sent_year=game.year,
            expires_year=game.year + 24,
            request_clause_type='NOTHING',
            offer_condition_type='EXCHANGE',
            offer_clause_type='SPECIFIC_COLONY',
            offer_star=extra_colony,
        )

        ok, _message = accept_contract(contract, other_player)

        self.assertTrue(ok)
        extra_colony.refresh_from_db()
        self.assertEqual(extra_colony.player_id, other_player.id)
        self.assertTrue(
            player.messages.filter(message__icontains=extra_colony.name, priority=True).exists()
        )
        self.assertTrue(
            other_player.messages.filter(message__icontains=extra_colony.name, priority=True).exists()
        )

    def test_diplomacy_colony_names_are_clickable_in_contract_list_and_messages(self):
        game = default_game(stars=5, fleets=0)
        player = game.players.first()
        race_type = get_default_race_type()
        other_user = User.objects.create_user('diplo_colony_link', 'diplo_colony_link@test.com', 'pass')
        other_account = Account.objects.create(django_user=other_user, alias='DCL')
        other_player = Player.objects.create(
            game=game,
            account=other_account,
            name='Link Race',
            plural_name='Link Races',
            race_type=race_type,
        )
        contact_star = game.stars.exclude(id=player.homeworld_id).order_by('id').first()
        self._create_contact_star_report(game, player, other_player, contact_star)
        contract = DiplomaticContract.objects.create(
            game=game,
            sender=other_player,
            recipient=player,
            temperature='REQUEST',
            status='SENT',
            sent_year=game.year,
            expires_year=game.year + 24,
            request_clause_type='SPECIFIC_COLONY',
            request_star=contact_star,
            offer_clause_type='NOTHING',
        )

        user, _ = get_default_user()
        client = Client()
        client.force_login(user)
        diplo_response = client.get(
            reverse('dj4xol:diplomacy', args=[game.short_id]),
            {'target': other_player.short_id},
        )
        game_response = client.get(reverse('dj4xol:game', args=[game.short_id]))

        self.assertEqual(diplo_response.status_code, 200)
        self.assertContains(diplo_response, '?sel=%s' % contact_star.short_id)
        self.assertEqual(game_response.status_code, 200)
        self.assertContains(game_response, '?sel=%s' % contact_star.short_id)
        self.assertContains(game_response, 'Respond</a>', html=False)

    def test_diplomacy_compose_form_uses_narrative_layout_and_grouped_technology_choices(self):
        game = default_game(stars=5, fleets=0)
        player = game.players.first()
        race_type = get_default_race_type()
        other_user = User.objects.create_user('diplo_contract_grouped', 'diplo_contract_grouped@test.com', 'pass')
        other_account = Account.objects.create(django_user=other_user, alias='DCG')
        other_player = Player.objects.create(
            game=game,
            account=other_account,
            name='Grouped Race',
            plural_name='Grouped Races',
            race_type=race_type,
        )
        contact_star = game.stars.exclude(id=player.homeworld_id).first()
        contact_star.player = other_player
        contact_star.save(update_fields=['player'])
        Report.objects.create(
            game=game,
            player=player,
            year=game.year,
            target_type='star',
            target_id=contact_star.id,
            cached_report=json.dumps({
                'name': contact_star.name,
                'x': contact_star.x,
                'y': contact_star.y,
                'player_name': other_player.name,
                'report_tier': 'encounter',
            }),
        )
        tech = Technology.objects.filter(enabled=True).order_by('level', 'id').first()
        other_rows = ensure_player_research_rows(other_player)
        target_row = next(row for row in other_rows if row.category_id == tech.category_id)
        target_row.current_level = tech.level
        target_row.save(update_fields=['current_level'])

        user, _ = get_default_user()
        client = Client()
        client.force_login(user)
        response = client.get(
            reverse('dj4xol:diplomacy', args=[game.short_id]),
            {'target': other_player.short_id, 'compose': '1'},
        )

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'diplomacy-compose-narrative')
        self.assertContains(response, 'name="offer_condition_type"')
        self.assertContains(response, 'that they')
        self.assertContains(response, 'grant us technology')
        self.assertContains(response, 'grant them technology')
        self.assertContains(response, 'in exchange')
        self.assertContains(response, '<optgroup label=')

    def test_diplomacy_decline_can_trigger_or_else_stance_without_demand_temperature(self):
        game = default_game(stars=5, fleets=0)
        player = game.players.first()
        race_type = get_default_race_type()
        other_user = User.objects.create_user('diplo_or_else_target', 'diplo_or_else_target@test.com', 'pass')
        other_account = Account.objects.create(django_user=other_user, alias='DCO')
        other_player = Player.objects.create(
            game=game,
            account=other_account,
            name='Or Else Race',
            plural_name='Or Else Races',
            race_type=race_type,
        )
        contact_star = game.stars.exclude(id=player.homeworld_id).first()
        contact_star.player = other_player
        contact_star.save(update_fields=['player'])
        Report.objects.create(
            game=game,
            player=player,
            year=game.year,
            target_type='star',
            target_id=contact_star.id,
            cached_report=json.dumps({
                'name': contact_star.name,
                'x': contact_star.x,
                'y': contact_star.y,
                'player_name': other_player.name,
                'report_tier': 'encounter',
            }),
        )
        contract = DiplomaticContract.objects.create(
            game=game,
            sender=player,
            recipient=other_player,
            temperature='PROPOSE',
            offer_condition_type='OR_ELSE',
            status='SENT',
            sent_year=game.year,
            expires_year=game.year + 24,
            request_clause_type='STANCE',
            request_stance='NEUTRAL',
            offer_clause_type='STANCE',
            offer_stance='HOSTILE',
        )

        other_client = Client()
        other_client.force_login(other_user)
        response = other_client.post(
            reverse('dj4xol:diplomacy', args=[game.short_id]),
            {
                'target': player.short_id,
                'action': 'decline_contract',
                'contract_id': contract.short_id,
            },
        )

        self.assertEqual(response.status_code, 302)
        contract.refresh_from_db()
        self.assertEqual(contract.status, DiplomaticContract.STATUS_DECLINED)
        stance = PlayerDiplomaticStance.objects.get(player=player, target_player=other_player)
        self.assertEqual(stance.pending_stance, 'HOSTILE')

    def test_diplomacy_allied_detail_can_toggle_reveal_cloaked_fleets(self):
        game = default_game(stars=5, fleets=0)
        player = game.players.first()
        race_type = get_default_race_type()
        other_user = User.objects.create_user('diplo_cloak_target', 'diplo_cloak_target@test.com', 'pass')
        other_account = Account.objects.create(django_user=other_user, alias='DCL')
        other_player = Player.objects.create(
            game=game,
            account=other_account,
            name='Cloak Ally',
            plural_name='Cloak Allies',
            race_type=race_type,
        )
        contact_star = game.stars.exclude(id=player.homeworld_id).first()
        self._create_contact_star_report(game, player, other_player, contact_star)
        PlayerDiplomaticStance.objects.create(
            player=player,
            target_player=other_player,
            stance='ALLIED',
        )

        user, _ = get_default_user()
        client = Client()
        client.force_login(user)

        response = client.get(
            reverse('dj4xol:diplomacy', args=[game.short_id]),
            {'target': other_player.short_id},
        )
        self.assertContains(response, 'Reveal cloaked fleets')

        response = client.post(
            reverse('dj4xol:diplomacy', args=[game.short_id]),
            {
                'target': other_player.short_id,
                'action': 'toggle_reveal_cloaked',
                'reveal_cloaked_fleets': '1',
            },
        )
        self.assertEqual(response.status_code, 302)

        stance = PlayerDiplomaticStance.objects.get(player=player, target_player=other_player)
        self.assertTrue(stance.reveal_cloaked_fleets)

    def test_diplomacy_compose_shows_delivery_warning_for_direct_world_delivery_at_cold_stance(self):
        game = default_game(stars=5, fleets=0)
        player = game.players.first()
        player.default_diplomatic_stance = 'COLD'
        player.save(update_fields=['default_diplomatic_stance'])
        player.turned_in = True
        player.save(update_fields=['turned_in'])
        race_type = get_default_race_type()
        other_user = User.objects.create_user('diplo_delivery_warn', 'diplo_delivery_warn@test.com', 'pass')
        other_account = Account.objects.create(django_user=other_user, alias='DDW')
        other_player = Player.objects.create(
            game=game,
            account=other_account,
            name='Delivery Race',
            plural_name='Delivery Races',
            race_type=race_type,
        )
        contact_star = game.stars.exclude(id=player.homeworld_id).first()
        contact_star.player = other_player
        contact_star.save(update_fields=['player'])
        Report.objects.create(
            game=game,
            player=player,
            year=game.year,
            target_type='star',
            target_id=contact_star.id,
            cached_report=json.dumps({
                'name': contact_star.name,
                'x': contact_star.x,
                'y': contact_star.y,
                'player_name': other_player.name,
                'report_tier': 'encounter',
            }),
        )

        user, _ = get_default_user()
        client = Client()
        client.force_login(user)
        response = client.post(
            reverse('dj4xol:diplomacy', args=[game.short_id]),
            {
                'target': other_player.short_id,
                'action': 'send_contract',
                'temperature': 'REQUEST',
                'request_clause_type': 'RESOURCE_TO_WORLD',
                'request_ironium': '10',
                'offer_clause_type': 'NOTHING',
            },
        )

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'likely to be shot down by your colony defences')

    def test_diplomacy_counter_uses_button_and_compose_panel_renders_above_requests(self):
        game = default_game(stars=5, fleets=0)
        player = game.players.first()
        race_type = get_default_race_type()
        other_user = User.objects.create_user('diplo_counter_button', 'diplo_counter_button@test.com', 'pass')
        other_account = Account.objects.create(django_user=other_user, alias='DCB')
        other_player = Player.objects.create(
            game=game,
            account=other_account,
            name='Counter Race',
            plural_name='Counter Races',
            race_type=race_type,
        )
        contact_star = game.stars.exclude(id=player.homeworld_id).first()
        contact_star.player = other_player
        contact_star.save(update_fields=['player'])
        Report.objects.create(
            game=game,
            player=player,
            year=game.year,
            target_type='star',
            target_id=contact_star.id,
            cached_report=json.dumps({
                'name': contact_star.name,
                'x': contact_star.x,
                'y': contact_star.y,
                'player_name': other_player.name,
                'report_tier': 'encounter',
            }),
        )
        contract = DiplomaticContract.objects.create(
            game=game,
            sender=other_player,
            recipient=player,
            temperature='REQUEST',
            status='SENT',
            sent_year=game.year,
            expires_year=game.year + 24,
            request_clause_type='STANCE',
            request_stance='NEUTRAL',
            offer_clause_type='NOTHING',
        )

        user, _ = get_default_user()
        client = Client()
        client.force_login(user)
        response = client.get(
            reverse('dj4xol:diplomacy', args=[game.short_id]),
            {'target': other_player.short_id, 'compose': '1', 'counter': contract.short_id},
        )

        self.assertEqual(response.status_code, 200)
        self.assertContains(
            response,
            '<button type="submit" class="diplomacy-action-button">Counter</button>',
            html=True,
        )
        body = response.content.decode('utf-8')
        self.assertLess(body.index('Counter Offer'), body.index('diplomacy-contract-list'))

    def test_diplomacy_request_list_includes_status_classes(self):
        game = default_game(stars=5, fleets=0)
        player = game.players.first()
        race_type = get_default_race_type()
        other_user = User.objects.create_user('diplo_status_classes', 'diplo_status_classes@test.com', 'pass')
        other_account = Account.objects.create(django_user=other_user, alias='DSC')
        other_player = Player.objects.create(
            game=game,
            account=other_account,
            name='Status Race',
            plural_name='Status Races',
            race_type=race_type,
        )
        contact_star = game.stars.exclude(id=player.homeworld_id).first()
        contact_star.player = other_player
        contact_star.save(update_fields=['player'])
        Report.objects.create(
            game=game,
            player=player,
            year=game.year,
            target_type='star',
            target_id=contact_star.id,
            cached_report=json.dumps({
                'name': contact_star.name,
                'x': contact_star.x,
                'y': contact_star.y,
                'player_name': other_player.name,
                'report_tier': 'encounter',
            }),
        )
        DiplomaticContract.objects.create(
            game=game,
            sender=other_player,
            recipient=player,
            temperature='REQUEST',
            status='ACCEPTED',
            sent_year=game.year,
            expires_year=game.year + 24,
            request_clause_type='STANCE',
            request_stance='WARM',
            offer_clause_type='NOTHING',
        )
        DiplomaticContract.objects.create(
            game=game,
            sender=other_player,
            recipient=player,
            temperature='REQUEST',
            status='COUNTERED',
            sent_year=game.year,
            expires_year=game.year + 24,
            request_clause_type='STANCE',
            request_stance='NEUTRAL',
            offer_clause_type='NOTHING',
        )
        DiplomaticContract.objects.create(
            game=game,
            sender=other_player,
            recipient=player,
            temperature='REQUEST',
            status='EXPIRED',
            sent_year=game.year,
            expires_year=game.year + 24,
            request_clause_type='STANCE',
            request_stance='COLD',
            offer_clause_type='NOTHING',
        )

        user, _ = get_default_user()
        client = Client()
        client.force_login(user)
        response = client.get(
            reverse('dj4xol:diplomacy', args=[game.short_id]),
            {'target': other_player.short_id},
        )

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'diplomacy-contract-status-accepted')
        self.assertContains(response, 'diplomacy-contract-status-countered')
        self.assertContains(response, 'diplomacy-contract-status-expired')

    def test_incoming_sent_contract_displays_received_status_label(self):
        game = default_game(stars=5, fleets=0)
        player = game.players.first()
        race_type = get_default_race_type()
        other_user = User.objects.create_user('diplo_received_status', 'diplo_received_status@test.com', 'pass')
        other_account = Account.objects.create(django_user=other_user, alias='DRS')
        other_player = Player.objects.create(
            game=game,
            account=other_account,
            name='Sender Race',
            plural_name='Sender Races',
            race_type=race_type,
        )
        contact_star = game.stars.exclude(id=player.homeworld_id).first()
        contact_star.player = other_player
        contact_star.save(update_fields=['player'])
        Report.objects.create(
            game=game,
            player=player,
            year=game.year,
            target_type='star',
            target_id=contact_star.id,
            cached_report=json.dumps({
                'name': contact_star.name,
                'x': contact_star.x,
                'y': contact_star.y,
                'player_name': other_player.name,
                'report_tier': 'encounter',
            }),
        )
        DiplomaticContract.objects.create(
            game=game,
            sender=other_player,
            recipient=player,
            temperature='REQUEST',
            status='SENT',
            sent_year=game.year,
            expires_year=game.year + 24,
            request_clause_type='STANCE',
            request_stance='WARM',
            offer_clause_type='NOTHING',
        )

        user, _ = get_default_user()
        client = Client()
        client.force_login(user)
        response = client.get(
            reverse('dj4xol:diplomacy', args=[game.short_id]),
            {'target': other_player.short_id},
        )

        self.assertContains(response, 'Status: <span class="diplomacy-contract-status-value">Received</span>', html=True)
        self.assertNotContains(response, 'Status: <span class="diplomacy-contract-status-value">Sent</span>', html=True)

    def test_outgoing_sent_contract_shows_extend_controls(self):
        game = default_game(stars=5, fleets=0)
        player = game.players.first()
        race_type = get_default_race_type()
        other_user = User.objects.create_user('diplo_extend_controls', 'diplo_extend_controls@test.com', 'pass')
        other_account = Account.objects.create(django_user=other_user, alias='DEC')
        other_player = Player.objects.create(
            game=game,
            account=other_account,
            name='Extend Control Race',
            plural_name='Extend Control Races',
            race_type=race_type,
        )
        contact_star = game.stars.exclude(id=player.homeworld_id).first()
        contact_star.player = other_player
        contact_star.save(update_fields=['player'])
        Report.objects.create(
            game=game,
            player=player,
            year=game.year,
            target_type='star',
            target_id=contact_star.id,
            cached_report=json.dumps({
                'name': contact_star.name,
                'x': contact_star.x,
                'y': contact_star.y,
                'player_name': other_player.name,
                'report_tier': 'encounter',
            }),
        )
        contract = DiplomaticContract.objects.create(
            game=game,
            sender=player,
            recipient=other_player,
            temperature='REQUEST',
            status='SENT',
            sent_year=game.year,
            expires_year=game.year + 24,
            request_clause_type='STANCE',
            request_stance='WARM',
            offer_clause_type='NOTHING',
        )

        user, _ = get_default_user()
        client = Client()
        client.force_login(user)
        response = client.get(
            reverse('dj4xol:diplomacy', args=[game.short_id]),
            {'target': other_player.short_id},
        )

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, '>Extend</button>', html=False)
        self.assertContains(response, 'contract-extend-%s' % contract.short_id)
        self.assertContains(response, 'name="extend_years"', html=False)

    def test_outgoing_sent_contract_renders_extend_form_below_action_row(self):
        game = default_game(stars=5, fleets=0)
        player = game.players.first()
        race_type = get_default_race_type()
        other_user = User.objects.create_user('diplo_extend_layout', 'diplo_extend_layout@test.com', 'pass')
        other_account = Account.objects.create(django_user=other_user, alias='DEL')
        other_player = Player.objects.create(
            game=game,
            account=other_account,
            name='Extend Layout Race',
            plural_name='Extend Layout Races',
            race_type=race_type,
        )
        contact_star = game.stars.exclude(id=player.homeworld_id).first()
        contact_star.player = other_player
        contact_star.save(update_fields=['player'])
        Report.objects.create(
            game=game,
            player=player,
            year=game.year,
            target_type='star',
            target_id=contact_star.id,
            cached_report=json.dumps({
                'name': contact_star.name,
                'x': contact_star.x,
                'y': contact_star.y,
                'player_name': other_player.name,
                'report_tier': 'encounter',
            }),
        )
        contract = DiplomaticContract.objects.create(
            game=game,
            sender=player,
            recipient=other_player,
            temperature='REQUEST',
            status='SENT',
            sent_year=game.year,
            expires_year=game.year + 24,
            request_clause_type='STANCE',
            request_stance='WARM',
            offer_clause_type='NOTHING',
        )

        user, _ = get_default_user()
        client = Client()
        client.force_login(user)
        response = client.get(
            reverse('dj4xol:diplomacy', args=[game.short_id]),
            {'target': other_player.short_id},
        )

        self.assertEqual(response.status_code, 200)
        self.assertRegex(
            response.content.decode('utf-8'),
            re.compile(
                r'class="diplomacy-contract-actions">.*?>Extend</button>\s*</div>\s*<form[^>]+class="diplomacy-contract-extend-form"[^>]+id="contract-extend-%s"' % contract.short_id,
                re.S,
            ),
        )

    def test_diplomacy_view_can_extend_outgoing_sent_contract(self):
        game = default_game(stars=5, fleets=0)
        player = game.players.first()
        race_type = get_default_race_type()
        other_user = User.objects.create_user('diplo_extend_post', 'diplo_extend_post@test.com', 'pass')
        other_account = Account.objects.create(django_user=other_user, alias='DEP')
        other_player = Player.objects.create(
            game=game,
            account=other_account,
            name='Extend Post Race',
            plural_name='Extend Post Races',
            race_type=race_type,
        )
        contact_star = game.stars.exclude(id=player.homeworld_id).first()
        contact_star.player = other_player
        contact_star.save(update_fields=['player'])
        Report.objects.create(
            game=game,
            player=player,
            year=game.year,
            target_type='star',
            target_id=contact_star.id,
            cached_report=json.dumps({
                'name': contact_star.name,
                'x': contact_star.x,
                'y': contact_star.y,
                'player_name': other_player.name,
                'report_tier': 'encounter',
            }),
        )
        contract = DiplomaticContract.objects.create(
            game=game,
            sender=player,
            recipient=other_player,
            temperature='REQUEST',
            status='SENT',
            sent_year=game.year,
            expires_year=game.year + 24,
            request_clause_type='STANCE',
            request_stance='WARM',
            offer_clause_type='NOTHING',
        )

        user, _ = get_default_user()
        client = Client()
        client.force_login(user)
        response = client.post(
            reverse('dj4xol:diplomacy', args=[game.short_id]),
            {
                'target': other_player.short_id,
                'action': 'extend_contract',
                'contract_id': contract.short_id,
                'extend_years': '6',
            },
        )

        self.assertEqual(response.status_code, 302)
        contract.refresh_from_db()
        self.assertEqual(contract.expires_year, game.year + 30)

    def test_mark_countered_uses_recipient_perspective_in_recipient_message(self):
        game = default_game(stars=5, fleets=0)
        player = game.players.first()
        race_type = get_default_race_type()
        other_user = User.objects.create_user('diplo_counter_msg', 'diplo_counter_msg@test.com', 'pass')
        other_account = Account.objects.create(django_user=other_user, alias='DCM')
        other_player = Player.objects.create(
            game=game,
            account=other_account,
            name='Counter Race',
            plural_name='Counter Races',
            race_type=race_type,
        )
        original = DiplomaticContract.objects.create(
            game=game,
            sender=other_player,
            recipient=player,
            temperature='REQUEST',
            status='SENT',
            sent_year=game.year,
            expires_year=game.year + 24,
            request_clause_type='STANCE',
            request_stance='NEUTRAL',
            offer_clause_type='NOTHING',
        )
        counter = DiplomaticContract.objects.create(
            game=game,
            sender=player,
            recipient=other_player,
            temperature='REQUEST',
            status='SENT',
            sent_year=game.year,
            expires_year=game.year + 24,
            request_clause_type='STANCE',
            request_stance='WARM',
            offer_clause_type='NOTHING',
            countered_from=original,
        )

        mark_countered(original, counter)

        sender_msg = other_player.messages.filter(category='DIPLOMATIC').latest('id').message
        recipient_msg = player.messages.filter(category='DIPLOMATIC').latest('id').message
        self.assertTrue(sender_msg.startswith('Diplomatic request countered: We '))
        self.assertIn('Counter Race', recipient_msg)
        self.assertNotIn('Diplomatic request countered: We ', recipient_msg)

    def test_main_game_messages_include_incoming_contract_alert(self):
        game = default_game(stars=5, fleets=0)
        player = game.players.first()
        race_type = get_default_race_type()
        other_user = User.objects.create_user('diplo_alert_target', 'diplo_alert_target@test.com', 'pass')
        other_account = Account.objects.create(django_user=other_user, alias='DCA')
        other_player = Player.objects.create(
            game=game,
            account=other_account,
            name='Alert Race',
            plural_name='Alert Races',
            race_type=race_type,
        )
        contract = DiplomaticContract.objects.create(
            game=game,
            sender=other_player,
            recipient=player,
            temperature='REQUEST',
            status='SENT',
            sent_year=game.year,
            expires_year=game.year + 24,
            request_clause_type='STANCE',
            request_stance='NEUTRAL',
            offer_clause_type='NOTHING',
        )

        user, _ = get_default_user()
        client = Client()
        client.force_login(user)
        response = client.get(reverse('dj4xol:game', args=[game.short_id]))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'Respond</a>', html=False)
        self.assertNotContains(response, '>Diplomatic request</a>', html=False)
        self.assertContains(response, 'diplomatic-priority')
        self.assertContains(response, 'Year %s' % contract.sent_year)
        self.assertNotContains(response, '(%s)' % other_account.alias)

    def test_main_game_messages_keep_unfulfilled_accepted_request_at_top(self):
        game = default_game(stars=5, fleets=0)
        player = game.players.first()
        race_type = get_default_race_type()
        other_user = User.objects.create_user('diplo_accept_alert', 'diplo_accept_alert@test.com', 'pass')
        other_account = Account.objects.create(django_user=other_user, alias='DAA')
        other_player = Player.objects.create(
            game=game,
            account=other_account,
            name='Accepted Race',
            plural_name='Accepted Races',
            race_type=race_type,
        )
        contract = DiplomaticContract.objects.create(
            game=game,
            sender=player,
            recipient=other_player,
            temperature='REQUEST',
            status='ACCEPTED',
            sent_year=game.year,
            accepted_year=game.year,
            expires_year=game.year + 24,
            request_clause_type='RESOURCE_TO_WORLD',
            request_ironium=25,
            offer_clause_type='NOTHING',
        )

        user, _ = get_default_user()
        client = Client()
        client.force_login(user)
        response = client.get(reverse('dj4xol:game', args=[game.short_id]))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'Awaiting from Accepted Races:')
        self.assertContains(response, '25kt Ironium')
        self.assertContains(response, 'Complete by Year %s' % (game.year + 24))
        self.assertContains(response, 'View</a>', html=False)
        self.assertContains(
            response,
            '?target=%s&contract=%s' % (other_player.short_id, contract.short_id),
            html=False,
        )

    def test_main_game_messages_do_not_pin_accepted_immediate_report_requests(self):
        game = default_game(stars=5, fleets=0)
        player = game.players.first()
        race_type = get_default_race_type()
        other_user = User.objects.create_user('diplo_accept_report_pin', 'diplo_accept_report_pin@test.com', 'pass')
        other_account = Account.objects.create(django_user=other_user, alias='DAR')
        other_player = Player.objects.create(
            game=game,
            account=other_account,
            name='Report Accepted Race',
            plural_name='Report Accepted Races',
            race_type=race_type,
        )
        target_star = game.stars.exclude(id=player.homeworld_id).order_by('id').first()
        target_star.player = other_player
        target_star.save(update_fields=['player'])
        Report.objects.create(
            game=game,
            player=player,
            year=game.year,
            target_type='star',
            target_id=target_star.id,
            cached_report=json.dumps({
                'name': target_star.name,
                'x': target_star.x,
                'y': target_star.y,
                'player_name': other_player.name,
                'report_tier': 'ownership',
            }),
        )
        contract = DiplomaticContract.objects.create(
            game=game,
            sender=player,
            recipient=other_player,
            temperature='REQUEST',
            status='ACCEPTED',
            sent_year=game.year,
            accepted_year=game.year,
            expires_year=game.year + 24,
            request_clause_type='REPORT',
            request_report_target_type='star',
            request_report_target_id=target_star.id,
            offer_clause_type='NOTHING',
        )

        user, _ = get_default_user()
        client = Client()
        client.force_login(user)
        response = client.get(reverse('dj4xol:game', args=[game.short_id]))

        self.assertEqual(response.status_code, 200)
        self.assertNotContains(response, 'active-contract-%s' % contract.short_id, html=False)
        self.assertNotContains(response, 'Awaiting from Report Accepted Race:', html=False)

    def test_diplomacy_rejects_direct_world_colonist_contracts(self):
        game = default_game(stars=5, fleets=0)
        player = game.players.first()
        race_type = get_default_race_type()
        other_user = User.objects.create_user('diplo_colonist_target', 'diplo_colonist_target@test.com', 'pass')
        other_account = Account.objects.create(django_user=other_user, alias='DCC')
        other_player = Player.objects.create(
            game=game,
            account=other_account,
            name='Cargo Race',
            plural_name='Cargo Races',
            race_type=race_type,
        )
        contact_star = game.stars.exclude(id=player.homeworld_id).first()
        contact_star.player = other_player
        contact_star.save(update_fields=['player'])
        Report.objects.create(
            game=game,
            player=player,
            year=game.year,
            target_type='star',
            target_id=contact_star.id,
            cached_report=json.dumps({
                'name': contact_star.name,
                'x': contact_star.x,
                'y': contact_star.y,
                'player_name': other_player.name,
                'report_tier': 'encounter',
            }),
        )

        user, _ = get_default_user()
        client = Client()
        client.force_login(user)
        response = client.post(
            reverse('dj4xol:diplomacy', args=[game.short_id]),
            {
                'target': other_player.short_id,
                'action': 'send_contract',
                'temperature': 'REQUEST',
                'deadline_years': '24',
                'extend_on_accept_years': '0',
                'request_clause_type': 'RESOURCE_TO_WORLD',
                'request_colonists': '5',
                'offer_clause_type': 'NOTHING',
            },
        )

        self.assertEqual(response.status_code, 200)
        self.assertContains(
            response,
            'Colonists must currently be requested on a transferred fleet',
        )

    def test_diplomacy_page_shows_signed_persuasion_modifier_next_to_base_chance(self):
        game = default_game(stars=5, fleets=0)
        player = game.players.first()
        player_type = ServerRaceType.objects.create(
            code='PSV1',
            name='View Persuasive A',
            enabled=True,
            description='',
            diplomacy_multiplier=2.0,
        )
        other_type = ServerRaceType.objects.create(
            code='PSV2',
            name='View Persuasive B',
            enabled=True,
            description='',
            diplomacy_multiplier=2.0,
        )
        player.race_type = player_type
        player.save(update_fields=['race_type'])
        other_account_user = User.objects.create_user('diplo_other_mod', 'diplo_other_mod@test.com', 'pass')
        other_account = Account.objects.create(django_user=other_account_user, alias='DIP6')
        other_player = Player.objects.create(
            game=game,
            account=other_account,
            name='Other Race',
            plural_name='Other Races',
            race_type=other_type,
        )
        contact_star = game.stars.exclude(id=player.homeworld_id).first()
        contact_star.player = other_player
        contact_star.save(update_fields=['player'])
        Report.objects.create(
            game=game,
            player=player,
            year=game.year,
            target_type='star',
            target_id=contact_star.id,
            cached_report=json.dumps({
                'name': contact_star.name,
                'x': contact_star.x,
                'y': contact_star.y,
                'player_name': other_player.name,
                'report_tier': 'encounter',
            }),
        )
        user, _ = get_default_user()
        client = Client()
        client.force_login(user)

        response = client.get(
            reverse('dj4xol:diplomacy', args=[game.short_id]),
            {'target': other_player.short_id},
        )

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, '30% (-50%)')

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

    def test_give_recipients_only_include_discovered_players(self):
        from ..objectdetails import DetailBuilder

        game = default_game(stars=5, fleets=1)
        player = game.players.first()
        fleet = player.fleets.first()
        race_type = get_default_race_type()
        other_user = User.objects.create_user('give_recipient_other', 'gro@test.com', 'pass')
        other_account = Account.objects.create(django_user=other_user, alias='GRO')
        other_player = Player.objects.create(
            game=game,
            account=other_account,
            name='Hidden Race',
            plural_name='Hidden Races',
            race_type=race_type,
        )

        detail = DetailBuilder(
            game,
            x=fleet.x,
            y=fleet.y,
            selected=fleet.short_id,
            player=player,
        ).build_detail()
        recipient_values = [row['value'] for row in detail.get('transfer_recipients', [])]
        self.assertNotIn(other_player.short_id, recipient_values)

        PlayerDiplomaticStance.objects.create(
            player=player,
            target_player=other_player,
            stance='HOSTILE',
        )
        detail = DetailBuilder(
            game,
            x=fleet.x,
            y=fleet.y,
            selected=fleet.short_id,
            player=player,
        ).build_detail()
        recipient_values = [row['value'] for row in detail.get('transfer_recipients', [])]
        self.assertIn(other_player.short_id, recipient_values)

    def test_add_give_order_rejects_undiscovered_player(self):
        game = default_game(stars=5, fleets=1)
        player = game.players.first()
        fleet = player.fleets.first()
        race_type = get_default_race_type()
        other_user = User.objects.create_user('give_post_other', 'gpo@test.com', 'pass')
        other_account = Account.objects.create(django_user=other_user, alias='GPO')
        other_player = Player.objects.create(
            game=game,
            account=other_account,
            name='Undiscovered Race',
            plural_name='Undiscovered Races',
            race_type=race_type,
        )
        user, _ = get_default_user()
        client = Client()
        client.force_login(user)

        response = client.post(
            reverse('dj4xol:add_fleet_order', args=[game.short_id]),
            {
                'fleet': fleet.short_id,
                'order_type': 'GIVE',
                'transfer_player': other_player.short_id,
                'x': fleet.x,
                'y': fleet.y,
                'sel': fleet.short_id,
            },
        )
        self.assertEqual(response.status_code, 302)
        self.assertFalse(
            FleetOrders.objects.filter(
                fleet=fleet,
                order_type='GIVE',
                transfer_player=other_player,
            ).exists()
        )

    def test_add_fleet_order_redirect_suppresses_auto_locate(self):
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
                'order_type': 'MOVE',
                'target_star': target_star.short_id,
                'x': fleet.x,
                'y': fleet.y,
                'sel': fleet.short_id,
            }
        )
        self.assertEqual(response.status_code, 302)
        self.assertIn('no_locate=1', response.url)

    def test_add_fleet_order_can_edit_existing_order(self):
        game = default_game(stars=5, fleets=1)
        player = game.players.first()
        fleet = player.fleets.first()
        target_star = player.homeworld
        order = FleetOrders.objects.create(
            game=game,
            fleet=fleet,
            order_type='TRANSFER',
            target_star=target_star,
            transfer_type='LOAD',
            transfer_ironium=12,
        )
        user, _ = get_default_user()
        client = Client()
        client.force_login(user)

        response = client.post(
            reverse('dj4xol:add_fleet_order', args=[game.short_id]),
            {
                'fleet': fleet.short_id,
                'edit_order': order.short_id,
                'order_type': 'TRANSFER',
                'transfer_target': 'star:%s' % target_star.short_id,
                'transfer_type': 'UNLOAD',
                'transfer_ironium': '34',
                'transfer_colonists': '56',
                'repeat': 'on',
                'x': fleet.x,
                'y': fleet.y,
                'sel': fleet.short_id,
            }
        )

        self.assertEqual(response.status_code, 302)
        self.assertEqual(fleet.orders.count(), 1)
        order.refresh_from_db()
        self.assertEqual(order.order_type, 'TRANSFER')
        self.assertEqual(order.target_star_id, target_star.id)
        self.assertEqual(order.transfer_type, 'UNLOAD')
        self.assertEqual(order.transfer_ironium, 34)
        self.assertEqual(order.transfer_colonists, 56)
        self.assertTrue(order.repeat)

    def test_add_fleet_order_creates_refuel_order_for_friendly_fleet(self):
        game = default_game(stars=5, fleets=2)
        player = game.players.first()
        fleet = player.fleets.order_by('id').first()
        target_fleet = player.fleets.exclude(id=fleet.id).first()
        user, _ = get_default_user()
        client = Client()
        client.force_login(user)

        response = client.post(
            reverse('dj4xol:add_fleet_order', args=[game.short_id]),
            {
                'fleet': fleet.short_id,
                'order_type': 'REFUEL',
                'target_fleet': target_fleet.short_id,
                'warpfactor': '6',
                'transfer_fuel': '12.5',
                'repeat': 'on',
                'x': fleet.x,
                'y': fleet.y,
                'sel': fleet.short_id,
            }
        )

        self.assertEqual(response.status_code, 302)
        order = fleet.orders.get(order_type='REFUEL')
        self.assertEqual(order.target_fleet_id, target_fleet.id)
        self.assertAlmostEqual(order.transfer_fuel, 12.5, places=4)
        self.assertTrue(order.repeat)

    def test_add_fleet_order_allows_refuel_to_neutral_fleet(self):
        game = default_game(stars=5, fleets=1)
        player = game.players.first()
        fleet = player.fleets.first()
        game.joinable = True
        game.save(update_fields=['joinable'])
        other_user = User.objects.create_user('refuel_enemy', 'refuel_enemy@test.com', 'pass')
        other_account = Account.objects.create(django_user=other_user, alias='RFE')
        enemy_player = GameFactory(game).join_player(other_account, get_default_race())
        PlayerDiplomaticStance.objects.create(
            player=player,
            target_player=enemy_player,
            stance='NEUTRAL',
        )
        target_fleet = enemy_player.fleets.first()
        user, _ = get_default_user()
        client = Client()
        client.force_login(user)

        response = client.post(
            reverse('dj4xol:add_fleet_order', args=[game.short_id]),
            {
                'fleet': fleet.short_id,
                'order_type': 'REFUEL',
                'target_fleet': target_fleet.short_id,
                'warpfactor': '6',
                'transfer_fuel': '12.5',
                'x': fleet.x,
                'y': fleet.y,
                'sel': fleet.short_id,
            }
        )

        self.assertEqual(response.status_code, 302)
        order = fleet.orders.get(order_type='REFUEL')
        self.assertEqual(order.target_fleet_id, target_fleet.id)
        self.assertAlmostEqual(order.transfer_fuel, 12.5, places=4)

    def test_add_fleet_order_rejects_refuel_to_cold_fleet(self):
        game = default_game(stars=5, fleets=1)
        player = game.players.first()
        fleet = player.fleets.first()
        game.joinable = True
        game.save(update_fields=['joinable'])
        other_user = User.objects.create_user('refuel_cold', 'refuel_cold@test.com', 'pass')
        other_account = Account.objects.create(django_user=other_user, alias='RFC')
        other_player = GameFactory(game).join_player(other_account, get_default_race())
        PlayerDiplomaticStance.objects.create(
            player=player,
            target_player=other_player,
            stance='COLD',
        )
        target_fleet = other_player.fleets.first()
        user, _ = get_default_user()
        client = Client()
        client.force_login(user)

        response = client.post(
            reverse('dj4xol:add_fleet_order', args=[game.short_id]),
            {
                'fleet': fleet.short_id,
                'order_type': 'REFUEL',
                'target_fleet': target_fleet.short_id,
                'warpfactor': '6',
                'transfer_fuel': '12.5',
                'x': fleet.x,
                'y': fleet.y,
                'sel': fleet.short_id,
            }
        )

        self.assertEqual(response.status_code, 302)
        self.assertFalse(fleet.orders.filter(order_type='REFUEL').exists())

    def test_add_fleet_order_does_not_edit_move_orders(self):
        game = default_game(stars=5, fleets=2)
        player = game.players.first()
        fleet = player.fleets.first()
        target_star = game.stars.exclude(id=player.homeworld_id).first()
        target_fleet = player.fleets.exclude(id=fleet.id).first()
        order = FleetOrders.objects.create(
            game=game,
            fleet=fleet,
            order_type='MOVE',
            target_star=target_star,
            warpfactor=5,
            original_warpfactor=5,
        )
        user, _ = get_default_user()
        client = Client()
        client.force_login(user)

        response = client.post(
            reverse('dj4xol:add_fleet_order', args=[game.short_id]),
            {
                'fleet': fleet.short_id,
                'edit_order': order.short_id,
                'order_type': 'INTERCEPT',
                'target_fleet': target_fleet.short_id,
                'warpfactor': '8',
                'repeat': 'on',
                'x': fleet.x,
                'y': fleet.y,
                'sel': fleet.short_id,
            }
        )

        self.assertEqual(response.status_code, 302)
        order.refresh_from_db()
        self.assertEqual(order.order_type, 'MOVE')
        self.assertEqual(order.target_star_id, target_star.id)
        self.assertEqual(order.warpfactor, 5)
        self.assertFalse(order.repeat)

    def test_add_fleet_order_redirect_suppresses_auto_locate_when_player_turned_in(self):
        game = default_game(stars=5, fleets=1)
        player = game.players.first()
        fleet = player.fleets.first()
        player.turned_in = True
        player.save(update_fields=['turned_in'])
        user, _ = get_default_user()
        client = Client()
        client.force_login(user)

        response = client.post(
            reverse('dj4xol:add_fleet_order', args=[game.short_id]),
            {
                'fleet': fleet.short_id,
                'order_type': 'MOVE',
                'x': fleet.x,
                'y': fleet.y,
                'sel': fleet.short_id,
            }
        )
        self.assertEqual(response.status_code, 302)
        self.assertIn('no_locate=1', response.url)
        self.assertEqual(fleet.orders.count(), 0)

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
