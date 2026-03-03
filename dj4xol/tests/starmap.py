import json

from django.contrib.auth.models import User
from django.test import TestCase

from ..factory import GameFactory
from ..models import Account, Report, Anomaly
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
