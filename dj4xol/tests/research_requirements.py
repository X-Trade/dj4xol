from django.test import TestCase

from ..models import (
    ProductionOrder,
    ResearchCategory,
    ResearchLevelRequirement,
    ResearchLevelPrerequisite,
    Technology,
)
from ..research import copy_default_requirements_to_category, ensure_player_research_rows
from ..turn import GameTurn
from ._util import default_game


class ResearchRequirementsTest(TestCase):
    def setUp(self):
        self.game = default_game(stars=5)
        self.player = self.game.players.first()
        self.star = self.player.homeworld

    def test_copy_default_requirements_to_category(self):
        category, _ = ResearchCategory.objects.get_or_create(
            code='REQ_ENERGY_A',
            defaults={'name': 'Req Energy A', 'enabled': True}
        )
        copy_default_requirements_to_category(category)
        self.assertTrue(
            ResearchLevelRequirement.objects.filter(
                category=category, level=1, rp_cost=50
            ).exists()
        )
        self.assertGreaterEqual(
            ResearchLevelRequirement.objects.filter(category=category).count(),
            26
        )

    def test_research_level_blocked_when_minerals_missing(self):
        category, _ = ResearchCategory.objects.get_or_create(
            code='REQ_ENERGY_B',
            defaults={'name': 'Req Energy B', 'enabled': True}
        )
        Technology.objects.create(
            category=category,
            level=1,
            name='Warp 3',
            tech_type='PROPULSION',
            params_json='{"max_warp_speed": 3}',
            enabled=True,
        )
        copy_default_requirements_to_category(category)
        requirement = ResearchLevelRequirement.objects.get(
            category=category,
            level=1
        )
        requirement.rp_cost = 50
        requirement.ironium_cost = 100
        requirement.boranium_cost = 0
        requirement.germanium_cost = 0
        requirement.save()

        self.star.labs = 10
        self.star.factories = 0
        self.star.mines = 0
        self.star.defenses = 0
        self.star.shipyards = 0
        self.star.colonists = 10000
        self.star.ironium_inventory = 90
        self.star.boranium_inventory = 0
        self.star.germanium_inventory = 0
        self.star.save()

        row = next(
            item for item in ensure_player_research_rows(self.player)
            if item.category_id == category.id
        )
        row.allocation_percent = 100
        row.save(update_fields=['allocation_percent'])

        GameTurn(self.game).research()
        row.refresh_from_db()
        self.star.refresh_from_db()
        self.assertEqual(row.current_level, 0.0)
        self.assertGreater(int(row.stored_rp), 0)
        self.assertEqual(row.ironium_paid, 90)
        self.assertEqual(self.star.ironium_inventory, 0)

    def test_research_minerals_consumed_after_production(self):
        category, _ = ResearchCategory.objects.get_or_create(
            code='REQ_ENERGY_C',
            defaults={'name': 'Req Energy C', 'enabled': True}
        )
        Technology.objects.create(
            category=category,
            level=1,
            name='Warp 3',
            tech_type='PROPULSION',
            params_json='{"max_warp_speed": 3}',
            enabled=True,
        )
        copy_default_requirements_to_category(category)
        requirement = ResearchLevelRequirement.objects.get(
            category=category,
            level=1
        )
        requirement.rp_cost = 50
        requirement.ironium_cost = 100
        requirement.boranium_cost = 0
        requirement.germanium_cost = 0
        requirement.save()

        self.star.labs = 10
        self.star.factories = 0
        self.star.mines = 0
        self.star.defenses = 0
        self.star.shipyards = 0
        self.star.colonists = 10000
        self.star.ironium_inventory = 120
        self.star.boranium_inventory = 0
        self.star.germanium_inventory = 0
        self.star.save()

        ProductionOrder.objects.create(
            game=self.game,
            star=self.star,
            order_type='BUILD_MINE',
            quantity=1,
        )

        row = next(
            item for item in ensure_player_research_rows(self.player)
            if item.category_id == category.id
        )
        row.allocation_percent = 100
        row.save(update_fields=['allocation_percent'])

        turn = GameTurn(self.game)
        turn.production()
        turn.research()

        row.refresh_from_db()
        self.star.refresh_from_db()
        self.assertGreaterEqual(row.current_level, 1.0)
        self.assertLessEqual(self.star.ironium_inventory, 20)

    def test_research_level_blocked_by_prerequisites(self):
        primary, _ = ResearchCategory.objects.get_or_create(
            code='REQ_GATED_A',
            defaults={'name': 'Req Gated A', 'enabled': True}
        )
        secondary, _ = ResearchCategory.objects.get_or_create(
            code='REQ_GATED_B',
            defaults={'name': 'Req Gated B', 'enabled': True}
        )
        Technology.objects.create(
            category=primary,
            level=1,
            name='Gate Test Tech',
            tech_type='PROPULSION',
            params_json='{\"max_warp_speed\": 3}',
            enabled=True,
        )
        copy_default_requirements_to_category(primary)
        copy_default_requirements_to_category(secondary)
        requirement = ResearchLevelRequirement.objects.get(
            category=primary,
            level=1,
        )
        requirement.rp_cost = 10
        requirement.ironium_cost = 0
        requirement.boranium_cost = 0
        requirement.germanium_cost = 0
        requirement.save()

        ResearchLevelPrerequisite.objects.create(
            category=primary,
            level=1,
            requires_category=secondary,
            min_level=1,
        )

        self.star.labs = 50
        self.star.factories = 0
        self.star.mines = 0
        self.star.defenses = 0
        self.star.shipyards = 0
        self.star.colonists = 10000
        self.star.save()

        rows = ensure_player_research_rows(self.player)
        primary_row = next(row for row in rows if row.category_id == primary.id)
        secondary_row = next(row for row in rows if row.category_id == secondary.id)
        primary_row.allocation_percent = 100
        secondary_row.allocation_percent = 0
        primary_row.save(update_fields=['allocation_percent'])
        secondary_row.save(update_fields=['allocation_percent'])

        GameTurn(self.game).research()
        primary_row.refresh_from_db()
        self.assertEqual(primary_row.current_level, 0.0)
        self.assertGreater(primary_row.stored_rp, 0)

        secondary_row.current_level = 1
        secondary_row.save(update_fields=['current_level'])

        GameTurn(self.game).research()
        primary_row.refresh_from_db()
        self.assertGreaterEqual(primary_row.current_level, 1.0)
