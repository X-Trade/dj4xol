from io import StringIO
from datetime import timedelta
from types import SimpleNamespace
from unittest.mock import patch

from django.contrib.auth.models import User
from django.core.management import call_command, CommandError
from django.test import TestCase
from django.utils import timezone

from ..factory import GameFactory
from ..models import (
    Account,
    Anomaly,
    Fleet,
    FleetOrders,
    GameMessage,
    PlayerNote,
    PlayerResearch,
    ProductionOrder,
    ResearchCategory,
    ResearchLevelPrerequisite,
    ResearchLevelRequirement,
    Report,
    Salvage,
)
from ..research import ensure_player_research_rows
from ..turn import GameTurn
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

    def test_colonies_command_outputs_secret_resources_when_present(self):
        home = self.player1.homeworld
        home.resource_x_inventory = 12
        home.resource_y_inventory = 0
        home.resource_z_inventory = 0
        home.save(update_fields=[
            'resource_x_inventory',
            'resource_y_inventory',
            'resource_z_inventory',
        ])
        output = self._run_play(
            self.game.short_id,
            '--no-auth',
            '--player',
            self.player1.short_id,
            input_values=['/colonies', '/exit'],
        )
        self.assertIn('resource_x_kt', output)
        self.assertNotIn('resource_y_kt', output)
        self.assertNotIn('resource_z_kt', output)

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
        self.assertIn('owner: %s' % self.player1.name, output)
        self.assertIn('is_owned: true', output)
        self.assertIn('visibility: current', output)

    def test_fleets_command_outputs_secret_resources_when_present(self):
        fleet = self.player1.fleets.first()
        fleet.resource_y_inventory = 9
        fleet.save(update_fields=['resource_y_inventory'])
        output = self._run_play(
            self.game.short_id,
            '--no-auth',
            '--player',
            self.player1.short_id,
            input_values=['/fleets', '/exit'],
        )
        self.assertIn('resource_y_kt', output)

    def test_fleets_all_shows_abandoned_owner_name_for_derelict_fleet(self):
        derelict = Fleet.objects.create(
            game=self.game,
            player=None,
            name='Drifter',
            x=self.player1.homeworld.x,
            y=self.player1.homeworld.y,
            ship_count=3,
        )
        output = self._run_play(
            self.game.short_id,
            '--no-auth',
            '--player',
            self.player1.short_id,
            input_values=['/fleets all', '/detail %s' % derelict.short_id, '/exit'],
        )
        self.assertIn('%s:' % derelict.short_id, output)
        self.assertIn('owner: Abandoned', output)

    def test_fleets_all_shows_known_other_fleet_with_owner(self):
        enemy_fleet = Fleet.objects.create(
            game=self.game,
            player=self.player2,
            name='Enemy Scout',
            x=self.player1.homeworld.x + 2,
            y=self.player1.homeworld.y + 1,
            ship_count=6,
        )
        report = Report.objects.create(
            game=self.game,
            player=self.player1,
            year=self.game.year - 1,
            target_type='fleet',
            target_id=enemy_fleet.id,
            cached_report='{}',
        )
        report.set_report_data({
            'name': enemy_fleet.name,
            'x': enemy_fleet.x,
            'y': enemy_fleet.y,
            'player_name': self.player2.name,
            'ship_count': enemy_fleet.ship_count,
            'report_tier': 'advanced',
        })
        report.save()

        output = self._run_play(
            self.game.short_id,
            '--no-auth',
            '--player',
            self.player1.short_id,
            input_values=['/fleets all', '/exit'],
        )
        self.assertIn('%s:' % enemy_fleet.short_id, output)
        self.assertIn('owner: %s' % self.player2.name, output)
        self.assertIn('is_owned: false', output)
        self.assertIn('visibility: current', output)
        self.assertIn('ship_count: 6', output)

    def test_fleets_other_excludes_owned_and_unknown_enemy_fleets(self):
        known_enemy = Fleet.objects.create(
            game=self.game,
            player=self.player2,
            name='Known Raider',
            x=self.player1.homeworld.x + 4,
            y=self.player1.homeworld.y + 2,
            ship_count=4,
        )
        hidden_enemy = Fleet.objects.create(
            game=self.game,
            player=self.player2,
            name='Hidden Raider',
            x=self.player2.homeworld.x + 5,
            y=self.player2.homeworld.y + 5,
            ship_count=8,
        )
        report = Report.objects.create(
            game=self.game,
            player=self.player1,
            year=self.game.year - 2,
            target_type='fleet',
            target_id=known_enemy.id,
            cached_report='{}',
        )
        report.set_report_data({
            'name': known_enemy.name,
            'x': known_enemy.x,
            'y': known_enemy.y,
            'player_name': self.player2.name,
            'ship_count': known_enemy.ship_count,
            'report_tier': 'basic',
        })
        report.save()

        output = self._run_play(
            self.game.short_id,
            '--no-auth',
            '--player',
            self.player1.short_id,
            input_values=['/fleets other', '/exit'],
        )
        self.assertIn('%s:' % known_enemy.short_id, output)
        self.assertNotIn('%s:' % self.player1.fleets.first().short_id, output)
        self.assertNotIn('%s:' % hidden_enemy.short_id, output)

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

    def test_orders_list_includes_remotemine_focus(self):
        fleet = self.player1.fleets.first()
        star = self.game.stars.exclude(pk=self.player1.homeworld.pk).first()
        FleetOrders.objects.create(
            game=self.game,
            fleet=fleet,
            order_type='REMOTEMINE',
            target_star=star,
            mine_until_full=True,
            remotemine_focus='ironium,boranium',
            position=1,
        )
        output = self._run_play(
            self.game.short_id,
            '--no-auth',
            '--player',
            self.player1.short_id,
            input_values=['/orders %s' % fleet.short_id, '/exit'],
        )
        self.assertIn('type: REMOTEMINE', output)
        self.assertIn('remotemine_focus: ironium,boranium', output)
        self.assertIn('mine_until_full: true', output)

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

    def test_orders_add_give_and_abandon(self):
        fleet = self.player1.fleets.order_by('id').first()

        self._run_play(
            self.game.short_id,
            '--no-auth',
            '--player',
            self.player1.short_id,
            input_values=[
                '/orders %s add GIVE %s' % (fleet.short_id, self.player2.short_id),
                '/orders %s add ABANDON' % fleet.short_id,
                '/exit',
            ],
        )

        orders = list(fleet.orders.order_by('position', 'id'))
        self.assertEqual(len(orders), 2)
        self.assertEqual(orders[0].order_type, 'GIVE')
        self.assertEqual(orders[0].transfer_player_id, self.player2.id)
        self.assertFalse(orders[0].repeat)
        self.assertEqual(orders[1].order_type, 'GIVE')
        self.assertIsNone(orders[1].transfer_player_id)
        self.assertFalse(orders[1].repeat)

    def test_orders_add_transfer_executes_secret_resources(self):
        fleets = list(self.player1.fleets.order_by('id'))
        source = fleets[0]
        target = fleets[1] if len(fleets) > 1 else Fleet.objects.create(
            game=self.game,
            player=self.player1,
            name='Transfer Target',
            x=source.x,
            y=source.y,
            cargo_capacity=100,
        )
        target.x = source.x
        target.y = source.y
        target.resource_x_inventory = 5
        target.resource_y_inventory = 3
        target.save(update_fields=['x', 'y', 'resource_x_inventory', 'resource_y_inventory'])

        self._run_play(
            self.game.short_id,
            '--no-auth',
            '--player',
            self.player1.short_id,
            input_values=[
                '/orders %s add TRANSFER %s load resource_x=5 resource_y=3' % (
                    source.short_id, target.short_id
                ),
                '/exit',
            ],
        )
        GameTurn(self.game).generate_turn()

        source.refresh_from_db()
        target.refresh_from_db()
        self.assertEqual(source.resource_x_inventory, 5)
        self.assertEqual(source.resource_y_inventory, 3)
        self.assertEqual(target.resource_x_inventory, 0)
        self.assertEqual(target.resource_y_inventory, 0)

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

    def test_orders_add_intercept_wormhole_is_rejected(self):
        fleet = self.player1.fleets.first()
        fleet.has_wormhole_drive = True
        fleet.save(update_fields=['has_wormhole_drive'])
        target = self.player1.fleets.exclude(id=fleet.id).first()
        if target is None:
            target = self.player2.fleets.first()
        output = self._run_play(
            self.game.short_id,
            '--no-auth',
            '--player',
            self.player1.short_id,
            input_values=[
                '/orders %s add INTERCEPT %s warp=wormhole' % (fleet.short_id, target.short_id),
                '/exit',
            ],
        )
        self.assertIn('warp=wormhole is only supported for MOVE orders.', output)

    def test_orders_add_patrol_wormhole_intercept_speed_is_rejected(self):
        fleet = self.player1.fleets.first()
        fleet.has_wormhole_drive = True
        fleet.save(update_fields=['has_wormhole_drive'])
        target_star = self.player1.homeworld
        output = self._run_play(
            self.game.short_id,
            '--no-auth',
            '--player',
            self.player1.short_id,
            input_values=[
                '/orders %s add PATROL %s intercept_speed=wormhole' % (fleet.short_id, target_star.short_id),
                '/exit',
            ],
        )
        self.assertIn('intercept_speed=wormhole is only supported for MOVE orders.', output)

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

    def test_orders_add_remotemine_accepts_focus_for_large_miners(self):
        fleet = self.player1.fleets.first()
        fleet.has_miners = 'LARGE'
        fleet.save(update_fields=['has_miners'])
        star = self.game.stars.exclude(pk=self.player1.homeworld.pk).first()
        star.player = None
        star.ironium_yield = 100
        star.boranium_yield = 100
        star.germanium_yield = 0
        star.resource_x_yield = 0
        star.resource_y_yield = 0
        star.resource_z_yield = 0
        star.save(update_fields=[
            'player',
            'ironium_yield',
            'boranium_yield',
            'germanium_yield',
            'resource_x_yield',
            'resource_y_yield',
            'resource_z_yield',
        ])

        self._run_play(
            self.game.short_id,
            '--no-auth',
            '--player',
            self.player1.short_id,
            input_values=[
                '/orders %s add REMOTEMINE %s focus=boranium' % (fleet.short_id, star.short_id),
                '/exit',
            ],
        )
        order = fleet.orders.filter(order_type='REMOTEMINE').first()
        self.assertIsNotNone(order)
        self.assertEqual(order.remotemine_focus, 'boranium')

    def test_orders_add_remotemine_ignores_focus_for_small_miners(self):
        fleet = self.player1.fleets.first()
        fleet.has_miners = 'SMALL'
        fleet.save(update_fields=['has_miners'])
        target_star = self.player2.homeworld

        self._run_play(
            self.game.short_id,
            '--no-auth',
            '--player',
            self.player1.short_id,
            input_values=[
                '/orders %s add REMOTEMINE %s focus=boranium' % (fleet.short_id, target_star.short_id),
                '/exit',
            ],
        )
        order = fleet.orders.filter(order_type='REMOTEMINE').first()
        self.assertIsNotNone(order)
        self.assertEqual(order.remotemine_focus, '')

    def test_orders_add_remotemine_mines_secret_resources(self):
        fleet = self.player1.fleets.first()
        fleet.has_miners = 'SMALL'
        fleet.save(update_fields=['has_miners'])
        star = self.game.stars.exclude(pk=self.player1.homeworld.pk).first()
        star.player = None
        star.ironium_yield = 0
        star.boranium_yield = 0
        star.germanium_yield = 0
        star.resource_x_yield = 100
        star.resource_y_yield = 0
        star.resource_z_yield = 0
        star.save(update_fields=[
            'player',
            'ironium_yield',
            'boranium_yield',
            'germanium_yield',
            'resource_x_yield',
            'resource_y_yield',
            'resource_z_yield',
        ])
        fleet.x = star.x
        fleet.y = star.y
        fleet.save(update_fields=['x', 'y'])

        self._run_play(
            self.game.short_id,
            '--no-auth',
            '--player',
            self.player1.short_id,
            input_values=[
                '/orders %s add REMOTEMINE %s' % (fleet.short_id, star.short_id),
                '/exit',
            ],
        )

        GameTurn(self.game).generate_turn()
        fleet.refresh_from_db()
        self.assertEqual(fleet.resource_x_inventory, 10)

        output = self._run_play(
            self.game.short_id,
            '--no-auth',
            '--player',
            self.player1.short_id,
            input_values=['/fleets', '/exit'],
        )
        self.assertIn('resource_x_kt', output)

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

    def test_orders_add_rejects_hidden_enemy_fleet_target(self):
        source_fleet = self.player1.fleets.first()
        hidden_fleet = Fleet.objects.create(
            game=self.game,
            player=self.player2,
            name='Shadow Talon',
            x=self.player2.homeworld.x + 11,
            y=self.player2.homeworld.y + 2,
            ship_count=3,
        )

        output = self._run_play(
            self.game.short_id,
            '--no-auth',
            '--player',
            self.player1.short_id,
            input_values=[
                '/orders %s add INTERCEPT %s' % (source_fleet.short_id, hidden_fleet.short_id),
                '/exit',
            ],
        )
        source_fleet.refresh_from_db()
        self.assertIn('Unknown target token: %s' % hidden_fleet.short_id, output)
        self.assertEqual(source_fleet.orders.count(), 0)

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

    def test_anomalies_command_lists_known_current_anomalies(self):
        anomaly = Anomaly.objects.create(
            game=self.game,
            x=self.player1.homeworld.x,
            y=self.player1.homeworld.y,
            name='Home Rift',
            anomaly_type=Anomaly.TYPE_RIFT,
            stability=77,
            heading=12.34,
        )
        hidden = Anomaly.objects.create(
            game=self.game,
            x=self.player2.homeworld.x,
            y=self.player2.homeworld.y,
            name='Hidden Nebula',
            anomaly_type=Anomaly.TYPE_NEBULA,
            stability=44,
        )

        output = self._run_play(
            self.game.short_id,
            '--no-auth',
            '--player',
            self.player1.short_id,
            input_values=['/anomalies', '/exit'],
        )
        self.assertIn('%s:' % anomaly.short_id, output)
        self.assertIn('name: Home Rift', output)
        self.assertIn('visibility: current', output)
        self.assertIn('anomaly_type: RIFT', output)
        self.assertIn('stability_pct: 77', output)
        self.assertIn('%s:' % hidden.short_id, output)
        self.assertIn('name: Hidden Nebula', output)
        self.assertIn('visibility: visible', output)
        self.assertNotIn('stability_pct: 44', output)

    def test_salvage_command_lists_known_current_salvage(self):
        salvage = Salvage.objects.create(
            game=self.game,
            x=self.player1.homeworld.x,
            y=self.player1.homeworld.y,
            ironium_inventory=11,
            boranium_inventory=7,
            germanium_inventory=5,
        )
        Salvage.objects.create(
            game=self.game,
            x=self.player2.homeworld.x,
            y=self.player2.homeworld.y,
            ironium_inventory=100,
        )
        Report.objects.create(
            game=self.game,
            player=self.player1,
            year=self.game.year,
            target_type='salvage',
            target_id=salvage.id,
            cached_report='{"name": "%s", "x": %s, "y": %s, "salvage_type": "%s", "total_minerals": %s, "report_tier": "basic"}'
            % (salvage.name, salvage.x, salvage.y, salvage.salvage_type, salvage.total_minerals),
        )

        output = self._run_play(
            self.game.short_id,
            '--no-auth',
            '--player',
            self.player1.short_id,
            input_values=['/salvage', '/exit'],
        )
        self.assertIn('%s:' % salvage.short_id, output)
        self.assertIn('visibility: current', output)
        self.assertIn('total_minerals_kt: 23', output)
        self.assertNotIn('total_minerals_kt: 100', output)

    def test_salvage_command_lists_visible_salvage_without_report_in_no_scanners_game(self):
        self.game.no_scanners = True
        self.game.save(update_fields=['no_scanners'])
        salvage = Salvage.objects.create(
            game=self.game,
            x=self.player2.homeworld.x,
            y=self.player2.homeworld.y,
            ironium_inventory=100,
        )

        output = self._run_play(
            self.game.short_id,
            '--no-auth',
            '--player',
            self.player1.short_id,
            input_values=['/salvage', '/detail %s' % salvage.short_id, '/exit'],
        )
        self.assertIn('%s:' % salvage.short_id, output)
        self.assertIn('visibility: visible', output)
        self.assertIn('unexplored: true', output)

    def test_detail_command_supports_anomalies(self):
        anomaly = Anomaly.objects.create(
            game=self.game,
            x=self.player1.homeworld.x,
            y=self.player1.homeworld.y,
            name='Detail Wormhole',
            anomaly_type=Anomaly.TYPE_WORMHOLE,
            stability=61,
        )

        output = self._run_play(
            self.game.short_id,
            '--no-auth',
            '--player',
            self.player1.short_id,
            input_values=['/detail %s' % anomaly.short_id, '/exit'],
        )
        self.assertIn('%s:' % anomaly.short_id, output)
        self.assertIn('selected_id: %s' % anomaly.short_id, output)
        self.assertIn('is_anomaly: true', output)
        self.assertIn('anomaly_type: WORMHOLE', output)
        self.assertIn('stability: 61', output)

    def test_detail_command_supports_exact_quoted_name_lookup(self):
        home = self.player1.homeworld
        home.name = 'Null Haven'
        home.save(update_fields=['name'])

        output = self._run_play(
            self.game.short_id,
            '--no-auth',
            '--player',
            self.player1.short_id,
            input_values=['/detail "Null Haven"', '/exit'],
        )
        self.assertIn('%s:' % home.short_id, output)
        self.assertIn('name: Null Haven', output)

    def test_detail_command_does_not_reveal_hidden_enemy_fleet_by_short_id(self):
        hidden_fleet = Fleet.objects.create(
            game=self.game,
            player=self.player2,
            name='Hidden Fang',
            x=self.player2.homeworld.x + 7,
            y=self.player2.homeworld.y + 6,
            ship_count=5,
        )

        output = self._run_play(
            self.game.short_id,
            '--no-auth',
            '--player',
            self.player1.short_id,
            input_values=['/detail %s' % hidden_fleet.short_id, '/exit'],
        )
        self.assertIn('Object not found in this game: %s' % hidden_fleet.short_id, output)
        self.assertNotIn('Hidden Fang', output)
        self.assertNotIn('selected_id: %s' % hidden_fleet.short_id, output)

    def test_detail_command_marks_last_known_position_for_stale_fleet_report(self):
        enemy_fleet = Fleet.objects.create(
            game=self.game,
            player=self.player2,
            name='Wraith Wing',
            x=self.player1.homeworld.x + 2,
            y=self.player1.homeworld.y + 1,
            ship_count=5,
            integrity=88,
        )
        report = Report.objects.create(
            game=self.game,
            player=self.player1,
            year=self.game.year - 1,
            target_type='fleet',
            target_id=enemy_fleet.id,
            cached_report='{}',
        )
        report.set_report_data({
            'name': 'Unknown Fleet',
            'x': self.player1.homeworld.x + 9,
            'y': self.player1.homeworld.y + 4,
            'report_tier': 'advanced',
            'player_name': self.player2.name,
            'ship_count': 5,
            'integrity': 88,
            'travel_warp': 7,
            'heading': 222.2,
        })
        report.save(update_fields=['cached_report'])

        enemy_fleet.x = self.player2.homeworld.x + 15
        enemy_fleet.y = self.player2.homeworld.y + 11
        enemy_fleet.save(update_fields=['x', 'y'])

        output = self._run_play(
            self.game.short_id,
            '--no-auth',
            '--player',
            self.player1.short_id,
            input_values=['/detail %s' % enemy_fleet.short_id, '/exit'],
        )
        self.assertIn('position_status: last_known', output)
        self.assertIn(
            'last_known_position: Empty Space (%s, %s)' % (
                self.player1.homeworld.x + 9,
                self.player1.homeworld.y + 4,
            ),
            output,
        )
        self.assertIn('last_known_report_year: %s' % (self.game.year - 1), output)
        self.assertIn('travel_warp: 7', output)
        self.assertIn('heading: 222.2', output)

    def test_detail_command_does_not_reveal_hidden_salvage_by_short_id(self):
        hidden_salvage = Salvage.objects.create(
            game=self.game,
            x=self.player2.homeworld.x + 9,
            y=self.player2.homeworld.y + 4,
            ironium_inventory=12,
            boranium_inventory=8,
        )

        output = self._run_play(
            self.game.short_id,
            '--no-auth',
            '--player',
            self.player1.short_id,
            input_values=['/detail %s' % hidden_salvage.short_id, '/exit'],
        )
        self.assertIn('Object not found in this game: %s' % hidden_salvage.short_id, output)
        self.assertNotIn('selected_id: %s' % hidden_salvage.short_id, output)

    def test_detail_command_shows_basic_salvage_report_total_without_inventory_breakdown(self):
        salvage = Salvage.objects.create(
            game=self.game,
            x=self.player1.homeworld.x,
            y=self.player1.homeworld.y + 1,
            salvage_type=Salvage.TYPE_ANCIENT_DEBRIS,
            ironium_inventory=13,
            boranium_inventory=7,
        )
        Report.objects.create(
            game=self.game,
            player=self.player1,
            year=self.game.year,
            target_type='salvage',
            target_id=salvage.id,
            cached_report='{"name": "%s", "x": %s, "y": %s, "salvage_type": "%s", "total_minerals": %s, "report_tier": "basic"}'
            % (salvage.name, salvage.x, salvage.y, salvage.salvage_type, salvage.total_minerals),
        )

        output = self._run_play(
            self.game.short_id,
            '--no-auth',
            '--player',
            self.player1.short_id,
            input_values=['/detail %s' % salvage.short_id, '/exit'],
        )
        self.assertIn('salvage_type: ANCIENT_DEBRIS', output)
        self.assertIn('total: 20', output)
        self.assertIn('thumbnail_blurred: true', output)
        self.assertNotIn('Ironium', output)

    def test_salvages_alias_is_removed(self):
        output = self._run_play(
            self.game.short_id,
            '--no-auth',
            '--player',
            self.player1.short_id,
            input_values=['/salvages', '/exit'],
        )
        self.assertIn('Unknown command. Type /help.', output)

    def test_help_command_supports_filtered_command_help(self):
        output = self._run_play(
            self.game.short_id,
            '--no-auth',
            '--player',
            self.player1.short_id,
            input_values=['/help rename', '/exit'],
        )
        self.assertIn('Usage: /rename <fleet_or_colony_id_or_"Exact Name"> "New Name"', output)
        self.assertIn('Renames one of your own fleets or colonies.', output)

    def test_inline_help_supports_subcommand_help(self):
        output = self._run_play(
            self.game.short_id,
            '--no-auth',
            '--player',
            self.player1.short_id,
            input_values=['/notes add help', '/exit'],
        )
        self.assertIn('Usage: /notes add [id] text', output)
        self.assertIn('If id is omitted, the next numeric id is used.', output)

    def test_help_command_supports_orders_add_subcommand_help(self):
        output = self._run_play(
            self.game.short_id,
            '--no-auth',
            '--player',
            self.player1.short_id,
            input_values=['/help orders add', '/exit'],
        )
        self.assertIn('Usage: /orders <fleet_id> add <ORDER_TYPE> <params...>', output)
        self.assertIn('Run /orders <id> add to print the target-specific YAML syntax block.', output)

    def test_rename_command_renames_owned_fleet_by_exact_name(self):
        fleet = self.player1.fleets.first()
        fleet.name = 'Old Spear'
        fleet.save(update_fields=['name'])

        output = self._run_play(
            self.game.short_id,
            '--no-auth',
            '--player',
            self.player1.short_id,
            input_values=['/rename "Old Spear" "New Spear"', '/exit'],
        )
        fleet.refresh_from_db()
        self.assertEqual(fleet.name, 'New Spear')
        self.assertIn('Renamed Fleet <%s>' % fleet.short_id, output)

    def test_notes_command_adds_lists_and_removes_notes(self):
        output = self._run_play(
            self.game.short_id,
            '--no-auth',
            '--player',
            self.player1.short_id,
            input_values=[
                '/notes add "Scout the east flank"',
                '/notes add 7 "Claim the rift"',
                '/notes',
                '/notes remove 1',
                '/exit',
            ],
        )
        notes = list(PlayerNote.objects.filter(player=self.player1).order_by('note_id'))
        self.assertEqual([note.note_id for note in notes], [7])
        self.assertEqual(notes[0].text, 'Claim the rift')
        self.assertIn('Saved note 1.', output)
        self.assertIn('Saved note 7.', output)
        self.assertIn('1: Scout the east flank', output)
        self.assertIn('7: Claim the rift', output)
        self.assertIn('Removed note 1.', output)

    def test_messages_command_formats_locate_links_for_cli(self):
        fleet = self.player1.fleets.first()
        GameMessage.objects.create(
            game=self.game,
            player=self.player1,
            year=self.game.year,
            category='GENERAL',
            message=(
                '<a href="/4x/%s/?x=%s&y=%s&sel=%s&locate=1">%s</a> reached '
                '<a href="/4x/%s/?x=1&y=2&locate=1">Empty Space (1, 2)</a>.'
            ) % (
                self.game.short_id,
                fleet.x,
                fleet.y,
                fleet.short_id,
                fleet.name,
                self.game.short_id,
            ),
        )

        output = self._run_play(
            self.game.short_id,
            '--no-auth',
            '--player',
            self.player1.short_id,
            input_values=['/messages limit=5', '/exit'],
        )
        self.assertIn('%s <%s> reached Empty Space (1, 2).' % (fleet.name, fleet.short_id), output)
        self.assertNotIn('<a href=', output)

    def test_reports_command_lists_known_objects_with_minimal_fields(self):
        enemy_fleet = Fleet.objects.create(
            game=self.game,
            player=self.player2,
            name='Enemy Scout',
            x=self.player1.homeworld.x + 2,
            y=self.player1.homeworld.y + 1,
            ship_count=6,
        )
        report = Report.objects.create(
            game=self.game,
            player=self.player1,
            year=self.game.year - 1,
            target_type='fleet',
            target_id=enemy_fleet.id,
            cached_report='{}',
        )
        report.set_report_data({
            'name': enemy_fleet.name,
            'x': enemy_fleet.x,
            'y': enemy_fleet.y,
            'player_name': self.player2.name,
            'ship_count': enemy_fleet.ship_count,
            'report_tier': 'advanced',
        })
        report.save()

        anomaly = Anomaly.objects.create(
            game=self.game,
            x=self.player1.homeworld.x + 3,
            y=self.player1.homeworld.y + 2,
            name='Known Rift',
            anomaly_type=Anomaly.TYPE_RIFT,
        )
        anomaly_report = Report.objects.create(
            game=self.game,
            player=self.player1,
            year=self.game.year - 2,
            target_type='anomaly',
            target_id=anomaly.id,
            cached_report='{}',
        )
        anomaly_report.set_report_data({
            'name': anomaly.name,
            'x': anomaly.x,
            'y': anomaly.y,
            'anomaly_type': anomaly.anomaly_type,
            'report_tier': 'basic',
        })
        anomaly_report.save()

        hidden_anomaly = Anomaly.objects.create(
            game=self.game,
            x=self.player2.homeworld.x,
            y=self.player2.homeworld.y,
            name='Visible Only Nebula',
            anomaly_type=Anomaly.TYPE_NEBULA,
        )

        output = self._run_play(
            self.game.short_id,
            '--no-auth',
            '--player',
            self.player1.short_id,
            input_values=['/reports', '/exit'],
        )
        self.assertIn('%s:' % self.player1.homeworld.short_id, output)
        self.assertIn('name: %s' % self.player1.homeworld.name, output)
        self.assertIn('report_year: %s' % self.game.year, output)
        self.assertIn('owner: %s' % self.player1.name, output)
        self.assertIn('object_class: star', output)
        self.assertIn('%s:' % enemy_fleet.short_id, output)
        self.assertIn('name: Enemy Scout', output)
        self.assertIn('fleet_count: 6', output)
        self.assertIn('%s:' % anomaly.short_id, output)
        self.assertIn('name: Known Rift', output)
        self.assertIn('subclass: Rift', output)
        self.assertNotIn('%s:' % hidden_anomaly.short_id, output)

    def test_status_command_shows_quorum_progress(self):
        self.player2.turned_in = True
        self.player2.save(update_fields=['turned_in'])

        output = self._run_play(
            self.game.short_id,
            '--no-auth',
            '--player',
            self.player1.short_id,
            input_values=['/status', '/exit'],
        )
        self.assertIn('year: %s' % self.game.year, output)
        self.assertIn('turn_scheme: QUORUM', output)
        self.assertIn('turned_in: false', output)
        self.assertIn('active_players: 2', output)
        self.assertIn('ready_players: 1', output)

    def test_status_command_shows_next_generation_when_scheduled(self):
        self.game.turn_scheme = 'DAILY'
        self.game.next_generation = timezone.now() + timedelta(hours=2, minutes=30)
        self.game.save(update_fields=['turn_scheme', 'next_generation'])

        output = self._run_play(
            self.game.short_id,
            '--no-auth',
            '--player',
            self.player1.short_id,
            input_values=['/status', '/exit'],
        )
        self.assertIn('turn_scheme: DAILY', output)
        self.assertIn('next_generation:', output)
        self.assertIn('time_to_next_turn:', output)

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

    def test_research_category_detail_includes_prerequisites(self):
        primary, _ = ResearchCategory.objects.get_or_create(
            code='REQ_CLI_A',
            defaults={'name': 'Req CLI A', 'enabled': True}
        )
        secondary, _ = ResearchCategory.objects.get_or_create(
            code='REQ_CLI_B',
            defaults={'name': 'Req CLI B', 'enabled': True}
        )
        ensure_player_research_rows(self.player1)
        ResearchLevelPrerequisite.objects.create(
            category=primary,
            level=1,
            requires_category=secondary,
            min_level=2,
        )
        secondary_row = PlayerResearch.objects.filter(
            player=self.player1, category=secondary
        ).first()
        if secondary_row is None:
            secondary_row = PlayerResearch.objects.create(
                player=self.player1, category=secondary, current_level=1
            )
        else:
            secondary_row.current_level = 1
            secondary_row.save(update_fields=['current_level'])

        output = self._run_play(
            self.game.short_id,
            '--no-auth',
            '--player',
            self.player1.short_id,
            input_values=['/research %s' % primary.code, '/exit'],
        )
        self.assertIn('next_level_prerequisites', output)
        self.assertIn('required: 2', output)
        self.assertIn('current: 1', output)
        self.assertIn('met: false', output)

    def test_research_category_detail_includes_secret_resource_requirements(self):
        category = ResearchCategory.objects.filter(code='ENERGY').first()
        self.assertIsNotNone(category)
        rows = ensure_player_research_rows(self.player1)
        energy_row = next(row for row in rows if row.category_id == category.id)
        energy_row.current_level = 0
        energy_row.stored_rp = 0
        energy_row.save(update_fields=['current_level', 'stored_rp'])

        requirement = ResearchLevelRequirement.objects.get(
            category=category, level=1
        )
        requirement.resource_x_cost = 10
        requirement.save(update_fields=['resource_x_cost'])

        output = self._run_play(
            self.game.short_id,
            '--no-auth',
            '--player',
            self.player1.short_id,
            input_values=['/research %s' % category.code, '/exit'],
        )
        self.assertIn('next_level_resource_requirements', output)
        self.assertIn('label: ???', output)
        self.assertIn('cost: 10', output)

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
