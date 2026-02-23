from django.test import TestCase

from ..models import ResearchCategory, Technology
from ..research import ensure_player_research_rows, get_player_unlocked_technologies
from ._util import default_game


class ResearchModelsTest(TestCase):
    def setUp(self):
        self.game = default_game(stars=5)
        self.player = self.game.players.first()
        self.energy = ResearchCategory.objects.create(
            code='ENERGY', name='Energy', display_order=10, enabled=True
        )
        self.electronics = ResearchCategory.objects.create(
            code='ELECT', name='Electronics', display_order=20, enabled=True
        )

    def test_ensure_player_research_rows_created(self):
        rows = ensure_player_research_rows(self.player)
        self.assertEqual(len(rows), 2)
        self.assertAlmostEqual(sum(r.allocation_percent for r in rows), 100.0, places=5)

    def test_unlocked_technology_from_current_level(self):
        Technology.objects.create(
            category=self.energy,
            level=1,
            name='Warp 6',
            tech_type='PROPULSION',
            params_json='{"max_warp_speed": 6}',
            enabled=True,
        )
        rows = ensure_player_research_rows(self.player)
        for row in rows:
            if row.category_id == self.energy.id:
                row.current_level = 1.0
                row.save()

        unlocked = get_player_unlocked_technologies(self.player)
        self.assertEqual(len(unlocked), 1)
        self.assertEqual(unlocked[0].name, 'Warp 6')
