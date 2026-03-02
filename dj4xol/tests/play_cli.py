from io import StringIO
from types import SimpleNamespace
from unittest.mock import patch

from django.contrib.auth.models import User
from django.core.management import call_command, CommandError
from django.test import TestCase

from ..factory import GameFactory
from ..models import (
    Account,
    FleetOrders,
    GameMessage,
    PlayerResearch,
    ProductionOrder,
    ResearchCategory,
    Report,
)
from ..research import ensure_player_research_rows
from ._util import get_default_race, get_default_race_type


class PlayCommandTest(TestCase):
    def setUp(self):
        get_default_race_type()
        self.user1 = User.objects.create_user('play_user1', 'p1@test.com', 'pass')
        self.user2 = User.objects.create_user('play_user2', 'p2@test.com', 'pass')
        self.account1 = Account.objects.create(django_user=self.user1, alias='P1')
        self.account2 = Account.objects.create(django_user=self.user2, alias='P2')

        factory = GameFactory()
        factory.set_map_size(80, 80)
        factory.set_owner(self.account1)
        factory.create_stars(8)
        self.game = factory.save()
        self.game.joinable = True
        self.game.save(update_fields=['joinable'])
        self.player1 = factory.join_player(self.account1, get_default_race())
        self.player2 = factory.join_player(self.account2, get_default_race())

    def _run_play(self, *args, input_values=None, auth_user=None):
        out = StringIO()
        input_values = input_values or []
        with patch('builtins.input', side_effect=input_values):
            if auth_user is not None:
                with patch('dj4xol.management.commands.play.getpass.getpass', return_value='pass'), \
                     patch('dj4xol.management.commands.play.authenticate', return_value=auth_user):
                    call_command('play', *args, stdout=out)
            else:
                call_command('play', *args, stdout=out)
        return out.getvalue()

    def test_colonies_command_outputs_star_resource_inventory_fields(self):
        output = self._run_play(
            self.game.short_id,
            '--no-auth',
            '--player',
            self.player1.short_id,
            input_values=['/colonies', '/exit'],
        )
        self.assertIn('%s:' % self.player1.homeworld.short_id, output)
        self.assertIn('ironium_kt', output)
        self.assertIn('boranium_kt', output)
        self.assertIn('germanium_kt', output)
        self.assertIn('colonists_kt', output)

    def test_stars_command_respects_player_knowledge_status(self):
        output = self._run_play(
            self.game.short_id,
            '--no-auth',
            '--player',
            self.player1.short_id,
            input_values=['/stars', '/exit'],
        )
        self.assertIn('%s:' % self.player1.homeworld.short_id, output)
        self.assertIn('status: colonised_owned, habitable', output)
        self.assertIn('status: unknown', output)

    def test_stars_command_shows_owner_for_explored_enemy_colony(self):
        enemy_home = self.player2.homeworld
        Report.objects.create(
            game=self.game,
            player=self.player1,
            year=self.game.year,
            target_type='star',
            target_id=enemy_home.id,
            cached_report='{}',
        )
        output = self._run_play(
            self.game.short_id,
            '--no-auth',
            '--player',
            self.player1.short_id,
            input_values=['/stars', '/exit'],
        )
        self.assertIn('status: colonised_other', output)
        self.assertIn('owner_player: %s' % self.player2.name, output)

    def test_fleets_command_outputs_fleet_summary(self):
        FleetOrders.objects.create(
            game=self.game,
            fleet=self.player1.fleets.first(),
            order_type='MOVE',
            x=10,
            y=10,
            position=1,
        )
        output = self._run_play(
            self.game.short_id,
            '--no-auth',
            '--player',
            self.player1.short_id,
            input_values=['/fleets', '/exit'],
        )
        self.assertIn('%s:' % self.player1.fleets.first().short_id, output)
        self.assertIn('ship_count', output)
        self.assertIn('number_of_orders', output)
        self.assertIn('integrity_pct', output)
        self.assertIn('max_safe_warp', output)
        self.assertIn('position: (', output)

    def test_orders_command_lists_fleet_orders(self):
        fleet = self.player1.fleets.first()
        FleetOrders.objects.create(
            game=self.game,
            fleet=fleet,
            order_type='MOVE',
            x=12,
            y=13,
            warpfactor=7,
            position=1,
        )
        output = self._run_play(
            self.game.short_id,
            '--no-auth',
            '--player',
            self.player1.short_id,
            input_values=['/orders %s' % fleet.short_id, '/exit'],
        )
        self.assertIn('%s:' % fleet.short_id, output)
        self.assertIn('type: MOVE', output)
        self.assertIn('warpfactor: 7', output)
        self.assertIn('position: (12, 13)', output)

    def test_orders_list_alias_works(self):
        fleet = self.player1.fleets.first()
        FleetOrders.objects.create(
            game=self.game,
            fleet=fleet,
            order_type='MOVE',
            x=8,
            y=9,
            warpfactor=5,
            position=1,
        )
        output = self._run_play(
            self.game.short_id,
            '--no-auth',
            '--player',
            self.player1.short_id,
            input_values=['/orders %s list' % fleet.short_id, '/exit'],
        )
        self.assertIn('%s:' % fleet.short_id, output)
        self.assertIn('type: MOVE', output)
        self.assertIn('position: (8, 9)', output)

    def test_orders_clear_removes_all_fleet_orders(self):
        fleet = self.player1.fleets.first()
        FleetOrders.objects.create(game=self.game, fleet=fleet, order_type='MOVE', x=1, y=1, position=1)
        FleetOrders.objects.create(game=self.game, fleet=fleet, order_type='SCUTTLE', position=2)
        self.assertEqual(fleet.orders.count(), 2)

        self._run_play(
            self.game.short_id,
            '--no-auth',
            '--player',
            self.player1.short_id,
            input_values=['/orders %s clear' % fleet.short_id, '/exit'],
        )
        self.assertEqual(fleet.orders.count(), 0)

    def test_orders_add_move_and_transfer(self):
        fleets = list(self.player1.fleets.order_by('id'))
        source = fleets[0]
        target = fleets[1]
        target.ironium_inventory = 123
        target.save(update_fields=['ironium_inventory'])

        self._run_play(
            self.game.short_id,
            '--no-auth',
            '--player',
            self.player1.short_id,
            input_values=[
                '/orders %s add MOVE (25,25) warp=7 repeat' % source.short_id,
                '/orders %s add TRANSFER %s load repeat' % (source.short_id, target.short_id),
                '/exit',
            ],
        )

        orders = list(source.orders.order_by('position', 'id'))
        self.assertEqual(len(orders), 2)
        self.assertEqual(orders[0].order_type, 'MOVE')
        self.assertEqual((orders[0].x, orders[0].y), (25, 25))
        self.assertEqual(orders[0].warpfactor, 7)
        self.assertTrue(orders[0].repeat)
        self.assertEqual(orders[1].order_type, 'TRANSFER')
        self.assertEqual(orders[1].target_fleet_id, target.id)
        self.assertEqual(orders[1].transfer_type, 'LOAD')
        self.assertTrue(orders[1].repeat)
        self.assertEqual(orders[1].transfer_ironium, 123)

    def test_orders_add_move_wormhole_requires_drive(self):
        fleet = self.player1.fleets.first()
        output = self._run_play(
            self.game.short_id,
            '--no-auth',
            '--player',
            self.player1.short_id,
            input_values=[
                '/orders %s add MOVE (25,25) warp=wormhole' % fleet.short_id,
                '/exit',
            ],
        )
        self.assertIn('warp=wormhole requires a fleet with a wormhole drive.', output)

    def test_orders_add_move_wormhole_sets_warpfactor_14(self):
        fleet = self.player1.fleets.first()
        fleet.has_wormhole_drive = True
        fleet.save(update_fields=['has_wormhole_drive'])
        self._run_play(
            self.game.short_id,
            '--no-auth',
            '--player',
            self.player1.short_id,
            input_values=[
                '/orders %s add MOVE (25,25) warp=wormhole repeat' % fleet.short_id,
                '/exit',
            ],
        )
        order = fleet.orders.filter(order_type='MOVE').first()
        self.assertIsNotNone(order)
        self.assertEqual(order.warpfactor, 14)
        self.assertTrue(order.repeat)

    def test_orders_add_bomb_requires_bombs_and_targets_star(self):
        fleet = self.player1.fleets.first()
        target_star = self.player2.homeworld

        output = self._run_play(
            self.game.short_id,
            '--no-auth',
            '--player',
            self.player1.short_id,
            input_values=[
                '/orders %s add BOMB %s' % (fleet.short_id, target_star.short_id),
                '/exit',
            ],
        )
        self.assertIn('BOMB requires a fleet with bombs.', output)
        self.assertFalse(fleet.orders.filter(order_type='BOMB').exists())

        fleet.has_bombs = 'CONVENTIONAL'
        fleet.save(update_fields=['has_bombs'])
        self._run_play(
            self.game.short_id,
            '--no-auth',
            '--player',
            self.player1.short_id,
            input_values=[
                '/orders %s add BOMB %s' % (fleet.short_id, target_star.short_id),
                '/exit',
            ],
        )
        bomb_order = fleet.orders.filter(order_type='BOMB').first()
        self.assertIsNotNone(bomb_order)
        self.assertEqual(bomb_order.target_star_id, target_star.id)
        self.assertFalse(bomb_order.repeat)

    def test_orders_add_bomb_accepts_bomb_until_parameter(self):
        fleet = self.player1.fleets.first()
        target_star = self.player2.homeworld
        fleet.has_bombs = 'CONVENTIONAL'
        fleet.save(update_fields=['has_bombs'])

        self._run_play(
            self.game.short_id,
            '--no-auth',
            '--player',
            self.player1.short_id,
            input_values=[
                '/orders %s add BOMB %s bomb_until=defenses_zero' % (fleet.short_id, target_star.short_id),
                '/exit',
            ],
        )
        bomb_order = fleet.orders.filter(order_type='BOMB').first()
        self.assertIsNotNone(bomb_order)
        self.assertEqual(bomb_order.bomb_until, 'DEFENSES_ZERO')

    def test_orders_add_bomb_accepts_once_parameter(self):
        fleet = self.player1.fleets.first()
        target_star = self.player2.homeworld
        fleet.has_bombs = 'CONVENTIONAL'
        fleet.save(update_fields=['has_bombs'])

        self._run_play(
            self.game.short_id,
            '--no-auth',
            '--player',
            self.player1.short_id,
            input_values=[
                '/orders %s add BOMB %s bomb_until=once' % (fleet.short_id, target_star.short_id),
                '/exit',
            ],
        )
        bomb_order = fleet.orders.filter(order_type='BOMB').first()
        self.assertIsNotNone(bomb_order)
        self.assertEqual(bomb_order.bomb_until, 'ONCE')

    def test_orders_add_remotemine_requires_miners_and_targets_star(self):
        fleet = self.player1.fleets.first()
        target_star = self.player2.homeworld

        output = self._run_play(
            self.game.short_id,
            '--no-auth',
            '--player',
            self.player1.short_id,
            input_values=[
                '/orders %s add REMOTEMINE %s' % (fleet.short_id, target_star.short_id),
                '/exit',
            ],
        )
        self.assertIn('REMOTEMINE requires a fleet with remote miners.', output)
        self.assertFalse(fleet.orders.filter(order_type='REMOTEMINE').exists())

        fleet.has_miners = 'SMALL'
        fleet.save(update_fields=['has_miners'])
        self._run_play(
            self.game.short_id,
            '--no-auth',
            '--player',
            self.player1.short_id,
            input_values=[
                '/orders %s add REMOTEMINE %s' % (fleet.short_id, target_star.short_id),
                '/exit',
            ],
        )
        order = fleet.orders.filter(order_type='REMOTEMINE').first()
        self.assertIsNotNone(order)
        self.assertEqual(order.target_star_id, target_star.id)
        self.assertFalse(order.repeat)

    def test_orders_add_remotemine_accepts_mine_until_full_parameter(self):
        fleet = self.player1.fleets.first()
        target_star = self.player2.homeworld
        fleet.has_miners = 'SMALL'
        fleet.save(update_fields=['has_miners'])

        self._run_play(
            self.game.short_id,
            '--no-auth',
            '--player',
            self.player1.short_id,
            input_values=[
                '/orders %s add REMOTEMINE %s mine_until_full=0' % (fleet.short_id, target_star.short_id),
                '/exit',
            ],
        )
        order = fleet.orders.filter(order_type='REMOTEMINE').first()
        self.assertIsNotNone(order)
        self.assertFalse(order.mine_until_full)

    def test_orders_add_and_clear_star_production(self):
        star = self.player1.homeworld
        self._run_play(
            self.game.short_id,
            '--no-auth',
            '--player',
            self.player1.short_id,
            input_values=[
                '/orders %s add mine 4 repeat' % star.short_id,
                '/orders %s clear' % star.short_id,
                '/exit',
            ],
        )
        self.assertEqual(star.production_orders.count(), 0)

        self._run_play(
            self.game.short_id,
            '--no-auth',
            '--player',
            self.player1.short_id,
            input_values=['/orders %s add mine 4 repeat' % star.short_id, '/exit'],
        )
        order = star.production_orders.first()
        self.assertIsNotNone(order)
        self.assertEqual(order.order_type, 'BUILD_MINE')
        self.assertEqual(order.quantity, 4)
        self.assertTrue(order.repeat)

    def test_detail_command_shows_current_detail_for_owned_object(self):
        home = self.player1.homeworld
        home.gravity = 1.2345
        home.temperature = 0.9876
        home.radiation = 1.999
        home.save(update_fields=['gravity', 'temperature', 'radiation'])

        output = self._run_play(
            self.game.short_id,
            '--no-auth',
            '--player',
            self.player1.short_id,
            input_values=['/detail %s' % self.player1.homeworld.short_id, '/exit'],
        )
        self.assertIn('%s:' % self.player1.homeworld.short_id, output)
        self.assertIn('selected_id: %s' % self.player1.homeworld.short_id, output)
        self.assertIn('is_current: true', output)
        self.assertIn('is_star: true', output)
        self.assertIn('value: 1.23', output)
        self.assertIn('value: 0.99', output)
        self.assertIn('value: 2.0', output)
        self.assertIn('percent: 61.7', output)

    def test_detail_command_shows_unexplored_placeholder_for_unknown_enemy_star(self):
        output = self._run_play(
            self.game.short_id,
            '--no-auth',
            '--player',
            self.player1.short_id,
            input_values=['/detail %s' % self.player2.homeworld.short_id, '/exit'],
        )
        self.assertIn('%s:' % self.player2.homeworld.short_id, output)
        self.assertIn('selected_id: %s' % self.player2.homeworld.short_id, output)
        self.assertIn('unexplored: true', output)
        self.assertIn('is_star: true', output)

    def test_priority_messages_shown_on_login_and_messages_filters_work(self):
        GameMessage.objects.create(
            game=self.game,
            player=self.player1,
            message='Priority combat alert',
            year=self.game.year,
            category='COMBAT',
            priority=True,
        )
        GameMessage.objects.create(
            game=self.game,
            player=self.player1,
            message='General note',
            year=self.game.year,
            category='GENERAL',
            priority=False,
        )

        output = self._run_play(
            self.game.short_id,
            '--no-auth',
            '--player',
            self.player1.short_id,
            input_values=['/messages priority=1 category=COMBAT limit=5', '/exit'],
        )
        self.assertIn('Priority messages (year %s):' % self.game.year, output)
        self.assertIn('priority_messages:', output)
        self.assertNotIn('\nmessages:\n', output)
        self.assertIn('Priority combat alert', output)
        self.assertNotIn('General note', output)

    def test_messages_command_defaults_match_game_panel_filter(self):
        self.player1.messages_seen_year = self.game.year - 1
        self.player1.save(update_fields=['messages_seen_year'])
        GameMessage.objects.create(
            game=self.game,
            player=self.player1,
            message='From prior seen year',
            year=self.game.year - 1,
            category='GENERAL',
            priority=False,
        )
        GameMessage.objects.create(
            game=self.game,
            player=self.player1,
            message='Too old',
            year=self.game.year - 2,
            category='GENERAL',
            priority=False,
        )

        output = self._run_play(
            self.game.short_id,
            '--no-auth',
            '--player',
            self.player1.short_id,
            input_values=['/messages', '/exit'],
        )
        self.assertIn('From prior seen year', output)
        self.assertNotIn('Too old', output)

    def test_connect_updates_last_seen_year(self):
        self.player1.last_seen_year = self.game.year - 5
        self.player1.save(update_fields=['last_seen_year'])

        self._run_play(
            self.game.short_id,
            '--no-auth',
            '--player',
            self.player1.short_id,
            input_values=['/exit'],
        )
        self.player1.refresh_from_db()
        self.assertEqual(self.player1.last_seen_year, self.game.year)

    def test_non_staff_cannot_select_other_players_with_auth(self):
        with patch('builtins.input', side_effect=[]), \
             patch('dj4xol.management.commands.play.getpass.getpass', return_value='pass'), \
             patch('dj4xol.management.commands.play.authenticate', return_value=self.user1):
            with self.assertRaises(CommandError):
                call_command(
                    'play',
                    self.game.short_id,
                    '--user',
                    self.user1.username,
                    '--player',
                    self.player2.short_id,
                )

    def test_research_overview_command_outputs_budget_and_categories(self):
        ensure_player_research_rows(self.player1)
        output = self._run_play(
            self.game.short_id,
            '--no-auth',
            '--player',
            self.player1.short_id,
            input_values=['/research', '/exit'],
        )
        self.assertIn('budget:', output)
        self.assertIn('categories:', output)
        category = ResearchCategory.objects.filter(enabled=True).order_by('display_order', 'name').first()
        self.assertIsNotNone(category)
        self.assertIn('%s:' % category.code, output)
        self.assertIn('allocation_percent', output)

    def test_research_category_detail_command_outputs_eta_and_upcoming(self):
        ensure_player_research_rows(self.player1)
        category = ResearchCategory.objects.filter(enabled=True).order_by('display_order', 'name').first()
        self.assertIsNotNone(category)
        output = self._run_play(
            self.game.short_id,
            '--no-auth',
            '--player',
            self.player1.short_id,
            input_values=['/research %s' % category.code, '/exit'],
        )
        self.assertIn('%s:' % category.code, output)
        self.assertIn('next_level_eta_years', output)
        self.assertIn('upcoming_technologies', output)

    def test_research_set_allocation_rebalances_non_singular(self):
        rows = ensure_player_research_rows(self.player1)
        self.assertTrue(len(rows) > 0)
        category = rows[0].category
        output = self._run_play(
            self.game.short_id,
            '--no-auth',
            '--player',
            self.player1.short_id,
            input_values=['/research %s 50' % category.code, '/exit'],
        )
        self.assertIn('%s:' % category.code, output)
        rows = list(
            PlayerResearch.objects.filter(player=self.player1)
            .select_related('category')
            .order_by('category__display_order', 'category__name')
        )
        total = sum(float(row.allocation_percent) for row in rows)
        self.assertEqual(int(round(total)), 100)
        focused = [row for row in rows if row.category_id == category.id][0]
        if len(rows) > 1:
            self.assertEqual(int(round(focused.allocation_percent)), 50)
        else:
            self.assertEqual(int(round(focused.allocation_percent)), 100)

    def test_research_set_allocation_singular_sets_focus_to_100(self):
        self.player1.singular_research = True
        self.player1.save(update_fields=['singular_research'])
        rows = ensure_player_research_rows(self.player1)
        self.assertTrue(len(rows) > 0)
        category = rows[-1].category
        self._run_play(
            self.game.short_id,
            '--no-auth',
            '--player',
            self.player1.short_id,
            input_values=['/research %s 1' % category.code, '/exit'],
        )
        rows = list(PlayerResearch.objects.filter(player=self.player1))
        focused = [row for row in rows if row.category_id == category.id][0]
        self.assertEqual(int(round(focused.allocation_percent)), 100)
        for row in rows:
            if row.category_id != category.id:
                self.assertEqual(int(round(row.allocation_percent)), 0)

    def test_one_shot_command_runs_and_exits_without_prompt(self):
        output = self._run_play(
            self.game.short_id,
            '--no-auth',
            '--player',
            self.player1.short_id,
            '-c',
            '/colonies',
            input_values=[],
        )
        self.assertIn('Connected: game=', output)
        self.assertIn('colonists_kt', output)
        self.assertIn('Disconnected.', output)

    def test_interactive_session_loads_and_saves_history(self):
        calls = []

        def _record(name):
            def _inner(*args, **kwargs):
                calls.append((name, args, kwargs))
            return _inner

        fake_readline = SimpleNamespace(
            read_history_file=_record('read_history_file'),
            write_history_file=_record('write_history_file'),
            set_history_length=_record('set_history_length'),
            add_history=_record('add_history'),
        )
        with patch('dj4xol.management.commands.play.readline', fake_readline):
            self._run_play(
                self.game.short_id,
                '--no-auth',
                '--player',
                self.player1.short_id,
                input_values=['/colonies', '/exit'],
            )

        names = [name for name, _args, _kwargs in calls]
        self.assertIn('read_history_file', names)
        self.assertIn('add_history', names)
        self.assertIn('set_history_length', names)
        self.assertIn('write_history_file', names)

    def test_done_non_quorum_exits_without_turning_in(self):
        self.game.turn_scheme = 'OWNER'
        self.game.save(update_fields=['turn_scheme'])
        self.player1.turned_in = False
        self.player1.save(update_fields=['turned_in'])

        output = self._run_play(
            self.game.short_id,
            '--no-auth',
            '--player',
            self.player1.short_id,
            input_values=['/done', '/colonies'],
        )
        self.player1.refresh_from_db()
        self.assertFalse(self.player1.turned_in)
        self.assertIn('Turn-in skipped: game turn scheme is OWNER.', output)
        self.assertNotIn('colonists_kt', output)

    def test_done_quorum_marks_player_turned_in_and_exits(self):
        self.game.turn_scheme = 'QUORUM'
        self.game.save(update_fields=['turn_scheme'])
        self.player1.turned_in = False
        self.player1.save(update_fields=['turned_in'])

        output = self._run_play(
            self.game.short_id,
            '--no-auth',
            '--player',
            self.player1.short_id,
            input_values=['/done', '/colonies'],
        )
        self.player1.refresh_from_db()
        self.assertTrue(self.player1.turned_in)
        self.assertIn('Player marked ready for turn generation.', output)
        self.assertNotIn('colonists_kt', output)
