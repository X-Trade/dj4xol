import json

from django.test import TestCase, Client
from django.urls import reverse
from django.contrib.auth.models import User
from ..models import FleetOrders, GameMessage, ProductionOrder, Report, Fleet, Account
from ..turn import GameTurn
from ..factory import GameFactory
from ._util import default_game, get_default_user, get_default_race


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

    def test_basic_star_report_shows_environment_only(self):
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
        self.assertNotContains(response, 'data-section="resources"')
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


class TestFleetOrderViews(TestCase):
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
