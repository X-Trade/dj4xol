import json

from django.contrib.auth.models import User
from django.test import TestCase

from ..factory import GameFactory
from ..models import Account, Report, Anomaly, Fleet, Salvage, PlayerDiplomaticStance
from ..starmap import StarMap
from ._util import default_game, get_default_race


class TestStarMap(TestCase):
    def test_render_map(self):
        game = default_game(fleets=1)
        player = game.players.first()
        starmap = StarMap(game, player)
        html = starmap.render_map()
        self.assertIn('class="mapstar', html)
        self.assertIn('class="mapfleet', html)

    def test_stars_are_dimmed_without_report_and_bright_with_report(self):
        game = default_game(stars=8, fleets=0)
        player = game.players.first()
        unknown_star = game.stars.filter(player__isnull=True).first()
        self.assertIsNotNone(unknown_star)

        starmap = StarMap(game, player)
        html = starmap.render_map()
        self.assertIn(
            f'data-object-id="{unknown_star.short_id}"',
            html,
        )
        self.assertIn('mapstar-unexplored', html)

        Report.objects.create(
            game=game,
            player=player,
            year=game.year,
            target_type='star',
            target_id=unknown_star.id,
            cached_report='{}',
        )
        starmap = StarMap(game, player)
        html = starmap.render_map()
        self.assertIn('mapstar-explored', html)

    def test_map_objects_include_selection_data_attributes(self):
        game = default_game(stars=5, fleets=1)
        player = game.players.first()
        starmap = StarMap(game, player, dest_mode=True)
        html = starmap.render_map()
        self.assertIn('data-map-object="1"', html)
        self.assertIn('data-object-type="star"', html)
        self.assertIn('data-object-type="fleet"', html)

    def test_multi_star_stack_uses_homeworld_as_primary_selection_target(self):
        game = default_game(stars=2, fleets=0)
        player = game.players.first()
        home = player.homeworld
        other_star = game.stars.exclude(pk=home.pk).first()
        other_star.x = home.x
        other_star.y = home.y
        other_star.save(update_fields=['x', 'y'])

        starmap = StarMap(game, player)
        html = starmap.render_map()

        self.assertIn(f'title="{home.name}"', html)
        self.assertIn(f'sel={home.short_id}', html)
        self.assertIn(f'data-object-id="{home.short_id}"', html)
        self.assertNotIn(f'data-object-id="{other_star.short_id}"', html)

    def test_wormhole_anomaly_uses_wormhole_css_class(self):
        game = default_game(stars=5, fleets=0)
        player = game.players.first()
        Anomaly.objects.create(
            game=game,
            x=20,
            y=20,
            name='Pair A',
            anomaly_type=Anomaly.TYPE_WORMHOLE,
        )
        starmap = StarMap(game, player)
        html = starmap.render_map()
        self.assertIn('mapanomaly-wormhole', html)

    def test_salvage_requires_report_to_render_on_player_map(self):
        game = default_game(stars=5, fleets=0)
        player = game.players.first()
        salvage = Salvage.objects.create(
            game=game,
            x=24,
            y=24,
            ironium_inventory=40,
            boranium_inventory=10,
            germanium_inventory=5,
        )

        starmap = StarMap(game, player)
        html = starmap.render_map()
        self.assertNotIn(f'data-object-id="{salvage.short_id}"', html)

        Report.objects.create(
            game=game,
            player=player,
            year=game.year,
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

        starmap = StarMap(game, player)
        html = starmap.render_map()
        self.assertIn(f'data-object-id="{salvage.short_id}"', html)

    def test_basic_scanner_fleet_map_title_is_obfuscated(self):
        game = default_game(stars=5, fleets=0)
        player1 = game.players.first()
        user2 = User.objects.create_user('fleet_map_enemy', 'fme@test.com', 'pass')
        account2 = Account.objects.create(django_user=user2)
        factory = GameFactory(game=game)
        player2 = factory.join_player(account2, get_default_race())

        scanner = Fleet.objects.create(
            game=game,
            player=player1,
            name='Our Scanner',
            x=20,
            y=20,
            basic_scanner_range=6,
            advanced_scanner_range=0,
        )
        enemy_fleet = Fleet.objects.create(
            game=game,
            player=player2,
            name='Leaky Fleet Name',
            x=scanner.x + 3,
            y=scanner.y,
        )

        starmap = StarMap(game, player1)
        html = starmap.render_map()
        self.assertIn('title="Unknown Fleet"', html)
        self.assertNotIn('title="Leaky Fleet Name"', html)
        self.assertIn(f'data-object-id="{enemy_fleet.short_id}"', html)

    def test_basic_ancient_debris_map_title_is_hidden(self):
        game = default_game(stars=5, fleets=0)
        player = game.players.first()
        salvage = Salvage.objects.create(
            game=game,
            x=24,
            y=24,
            salvage_type=Salvage.TYPE_ANCIENT_DEBRIS,
            ironium_inventory=40,
            boranium_inventory=10,
            germanium_inventory=5,
        )
        Report.objects.create(
            game=game,
            player=player,
            year=game.year,
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

        starmap = StarMap(game, player)
        html = starmap.render_map()
        self.assertIn('title="???"', html)
        self.assertNotIn(salvage.name, html)

    def test_rift_anomaly_has_deterministic_variable_height_style(self):
        game = default_game(stars=5, fleets=0)
        player = game.players.first()
        rift = Anomaly.objects.create(
            game=game,
            x=22,
            y=22,
            name='Rift Height Check',
            anomaly_type=Anomaly.TYPE_RIFT,
        )
        starmap = StarMap(game, player)
        html = starmap.render_map()
        self.assertIn(f'data-object-id="{rift.short_id}"', html)
        self.assertIn('--rift-height:', html)

    def test_basic_star_reports_hide_enemy_ownership_on_map(self):
        factory = GameFactory()
        factory.set_map_size(100, 100)
        user1 = User.objects.create_user('scanner_map_1', 's1@test.com', 'pass')
        account1 = Account.objects.create(django_user=user1)
        factory.set_owner(account1)
        factory.create_stars(12)
        game = factory.save()
        game.joinable = True
        game.save(update_fields=['joinable'])

        player1 = factory.join_player(account1, get_default_race())
        user2 = User.objects.create_user('scanner_map_2', 's2@test.com', 'pass')
        account2 = Account.objects.create(django_user=user2)
        player2 = factory.join_player(account2, get_default_race())
        enemy_star = player2.homeworld

        occupied = set(
            game.stars.exclude(id=enemy_star.id).values_list('x', 'y')
        )
        target = None
        for x in range(1, int(game.map_size_x)):
            for y in range(1, int(game.map_size_y)):
                if (x, y) not in occupied:
                    target = (x, y)
                    break
            if target:
                break
        self.assertIsNotNone(target)
        enemy_star.x, enemy_star.y = target
        enemy_star.save(update_fields=['x', 'y'])

        Report.objects.create(
            game=game,
            player=player1,
            year=game.year,
            target_type='star',
            target_id=enemy_star.id,
            cached_report=json.dumps({
                'name': enemy_star.name,
                'x': enemy_star.x,
                'y': enemy_star.y,
                'report_tier': 'basic',
            }),
        )
        starmap = StarMap(game, player1)
        html = starmap.render_map()
        needle = f'data-object-id="{enemy_star.short_id}"'
        idx = html.find(needle)
        self.assertNotEqual(idx, -1)
        start = html.rfind('<', 0, idx)
        end = html.find('>', idx)
        tag = html[start:end]
        self.assertIn('mapstar', tag)
        self.assertNotIn('mapstar-enemy', tag)

        Report.objects.filter(
            game=game,
            player=player1,
            target_type='star',
            target_id=enemy_star.id,
        ).update(cached_report=json.dumps({
            'name': enemy_star.name,
            'x': enemy_star.x,
            'y': enemy_star.y,
            'report_tier': 'advanced',
        }))
        starmap = StarMap(game, player1)
        html = starmap.render_map()
        idx = html.find(needle)
        self.assertNotEqual(idx, -1)
        start = html.rfind('<', 0, idx)
        end = html.find('>', idx)
        tag = html[start:end]
        self.assertIn('mapstar-enemy', tag)

    def test_no_scanners_shows_enemy_fleets_and_star_ownership(self):
        user1 = User.objects.create_user('noscan_map_1', 'ns1@test.com', 'pass')
        account1 = Account.objects.create(django_user=user1)
        user2 = User.objects.create_user('noscan_map_2', 'ns2@test.com', 'pass')
        account2 = Account.objects.create(django_user=user2)

        factory = GameFactory()
        factory.set_map_size(100, 100)
        factory.set_owner(account1)
        factory.create_stars(12)
        game = factory.save()
        game.joinable = True
        game.no_scanners = True
        game.save(update_fields=['joinable', 'no_scanners'])

        player1 = factory.join_player(account1, get_default_race())
        player2 = factory.join_player(account2, get_default_race())
        enemy_star = player2.homeworld
        enemy_star.x = 42
        enemy_star.y = 42
        enemy_star.save(update_fields=['x', 'y'])

        enemy_fleet = Fleet.objects.create(
            game=game,
            player=player2,
            name='Visible Raider',
            x=45,
            y=45,
        )

        starmap = StarMap(game, player1)
        html = starmap.render_map()
        self.assertIn('mapfleet-enemy', html)
        self.assertIn(f'data-object-id="{enemy_fleet.short_id}"', html)

        needle = f'data-object-id="{enemy_star.short_id}"'
        idx = html.find(needle)
        self.assertNotEqual(idx, -1)
        start = html.rfind('<', 0, idx)
        end = html.find('>', idx)
        tag = html[start:end]
        self.assertIn('mapstar-enemy', tag)

    def test_no_scanners_shows_salvage_without_report(self):
        game = default_game(stars=5, fleets=0)
        player = game.players.first()
        game.no_scanners = True
        game.save(update_fields=['no_scanners'])
        salvage = Salvage.objects.create(
            game=game,
            x=26,
            y=26,
            ironium_inventory=30,
            boranium_inventory=5,
            germanium_inventory=0,
        )

        starmap = StarMap(game, player)
        html = starmap.render_map()
        self.assertIn(f'data-object-id="{salvage.short_id}"', html)

    def test_allied_intel_sharing_makes_enemy_fleet_visible(self):
        user1 = User.objects.create_user('share_map_1', 'sm1@test.com', 'pass')
        account1 = Account.objects.create(django_user=user1)
        user2 = User.objects.create_user('share_map_2', 'sm2@test.com', 'pass')
        account2 = Account.objects.create(django_user=user2)

        factory = GameFactory()
        factory.set_map_size(100, 100)
        factory.set_owner(account1)
        factory.create_stars(12)
        game = factory.save()
        game.joinable = True
        game.save(update_fields=['joinable'])

        player1 = factory.join_player(account1, get_default_race())
        player2 = factory.join_player(account2, get_default_race())
        enemy_fleet = Fleet.objects.create(
            game=game,
            player=player2,
            name='Hidden Scout',
            x=88,
            y=88,
            basic_scanner_range=0,
            advanced_scanner_range=0,
        )

        starmap = StarMap(game, player1)
        html = starmap.render_map()
        self.assertNotIn(f'data-object-id="{enemy_fleet.short_id}"', html)

        PlayerDiplomaticStance.objects.create(
            player=player2,
            target_player=player1,
            stance='ALLIED',
        )

        starmap = StarMap(game, player1)
        html = starmap.render_map()
        self.assertIn(f'data-object-id="{enemy_fleet.short_id}"', html)
        self.assertIn('mapfleet-allied', html)

        allied_star = player2.homeworld
        html_with_star = starmap.render_star(allied_star)
        self.assertIn('mapstar-allied', html_with_star)

    def test_unowned_fleet_uses_unexplored_grey_style(self):
        game = default_game(stars=5, fleets=0)
        player = game.players.first()
        derelict = Fleet.objects.create(
            game=game,
            player=None,
            name='Derelict',
            x=45,
            y=45,
        )

        starmap = StarMap(game, player)
        html = starmap.render_fleet(derelict)
        self.assertIn('mapfleet-unowned', html)
