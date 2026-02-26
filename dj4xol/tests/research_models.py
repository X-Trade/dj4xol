from django.test import TestCase

from ..models import ResearchCategory, Technology
from ..research import ensure_player_research_rows, get_player_unlocked_technologies
from ._util import default_game


class ResearchModelsTest(TestCase):
    def setUp(self):
        self.game = default_game(stars=5)
        self.player = self.game.players.first()
        self.energy, _ = ResearchCategory.objects.get_or_create(
            code='MOD_ENERGY',
            defaults={'name': 'Model Energy', 'display_order': 10, 'enabled': True}
        )
        self.electronics, _ = ResearchCategory.objects.get_or_create(
            code='MOD_ELECT',
            defaults={'name': 'Model Electronics', 'display_order': 20, 'enabled': True}
        )

    def test_ensure_player_research_rows_created(self):
        rows = ensure_player_research_rows(self.player)
        category_ids = {r.category_id for r in rows}
        self.assertIn(self.energy.id, category_ids)
        self.assertIn(self.electronics.id, category_ids)
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

        unlocked = list(get_player_unlocked_technologies(self.player))
        self.assertTrue(any(item.name == 'Warp 6' for item in unlocked))
