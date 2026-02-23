from ..starmap import StarMap
from ..models import Report
from ._util import default_game
from django.test import TestCase


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
