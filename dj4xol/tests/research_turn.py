from django.test import TestCase

from ..models import Fleet, FleetOrders, ProductionOrder, ResearchCategory, Technology
from ..research import ensure_player_research_rows, get_player_tech_effects
from ..turn import GameTurn
from ._util import default_game


class ResearchTurnTest(TestCase):
    def setUp(self):
        self.game = default_game(stars=5)
        self.player = self.game.players.first()
        self.star = self.player.homeworld

    def test_build_lab_production_order(self):
        self.star.factories = 10
        self.star.ironium_inventory = 1000
        self.star.boranium_inventory = 1000
        self.star.germanium_inventory = 1000
        self.star.save()

        ProductionOrder.objects.create(
            game=self.game,
            star=self.star,
            order_type='BUILD_LAB',
            quantity=1,
        )
        GameTurn(self.game).production()
        self.star.refresh_from_db()
        self.assertEqual(self.star.labs, 1)

    def test_research_progression_from_labs(self):
        category = ResearchCategory.objects.create(
            code='ENERGY', name='Energy', enabled=True
        )
        Technology.objects.create(
            category=category,
            level=1,
            name='Warp 6',
            tech_type='PROPULSION',
            params_json='{"max_warp_speed": 6}',
        )
        Technology.objects.create(
            category=category,
            level=2,
            name='Warp 7',
            tech_type='PROPULSION',
            params_json='{"max_warp_speed": 7}',
        )

        self.star.mines = 0
        self.star.factories = 0
        self.star.defenses = 0
        self.star.shipyards = 0
        self.star.labs = 10
        self.star.colonists = 10000
        self.star.save()

        rows = ensure_player_research_rows(self.player)
        row = rows[0]
        row.allocation_percent = 100.0
        row.save()

        GameTurn(self.game).research()
        row.refresh_from_db()
        self.assertEqual(row.current_level, 2.0)
        self.assertEqual(int(row.stored_rp), 70)

    def test_new_fleet_uses_unlocked_propulsion(self):
        category = ResearchCategory.objects.create(
            code='ENERGY', name='Energy', enabled=True
        )
        Technology.objects.create(
            category=category,
            level=1,
            name='Warp 7',
            tech_type='PROPULSION',
            params_json='{"max_warp_speed": 7}',
        )
        rows = ensure_player_research_rows(self.player)
        for row in rows:
            row.current_level = 1.0
            row.save()

        existing_ids = set(Fleet.objects.filter(player=self.player).values_list('id', flat=True))
        self.star.mines = 0
        self.star.defenses = 0
        self.star.labs = 0
        self.star.shipyards = 1
        self.star.factories = 100
        self.star.colonists = 200000
        self.star.ironium_inventory = 1000
        self.star.boranium_inventory = 1000
        self.star.germanium_inventory = 1000
        self.star.save()

        ProductionOrder.objects.create(
            game=self.game,
            star=self.star,
            order_type='BUILD_FLEET',
            quantity=1,
        )
        GameTurn(self.game).production()
        new_fleet = Fleet.objects.filter(player=self.player).exclude(id__in=existing_ids).first()
        self.assertIsNotNone(new_fleet)
        self.assertEqual(new_fleet.max_safe_warp, 7)

    def test_merge_uses_weighted_tech_levels(self):
        fleet_a = Fleet.objects.create(
            game=self.game,
            player=self.player,
            name='Fleet A',
            x=self.star.x,
            y=self.star.y,
            ship_count=10,
            offense_level=0.0,
            defense_level=0.0,
        )
        fleet_b = Fleet.objects.create(
            game=self.game,
            player=self.player,
            name='Fleet B',
            x=self.star.x,
            y=self.star.y,
            ship_count=1,
            offense_level=10.0,
            defense_level=10.0,
        )
        order = FleetOrders.objects.create(
            game=self.game,
            fleet=fleet_a,
            order_type='MERGE',
            target_fleet=fleet_b,
        )

        result = GameTurn(self.game)._execute_merge_order(fleet_a, order)
        self.assertEqual(result, 'executed')
        fleet_b.refresh_from_db()
        self.assertAlmostEqual(fleet_b.offense_level, 10.0 / 11.0, places=4)
        self.assertAlmostEqual(fleet_b.defense_level, 10.0 / 11.0, places=4)

    def test_tech_effects_use_latest_per_type_and_sum_properties(self):
        energy = ResearchCategory.objects.create(
            code='ENERGY', name='Energy', enabled=True
        )
        electronics = ResearchCategory.objects.create(
            code='ELEC', name='Electronics', enabled=True
        )
        # ENERGY_WEAPON: latest level should win for this tech_type selection (L2).
        Technology.objects.create(
            category=energy,
            level=1,
            name='Mass Drivers I',
            tech_type='ENERGY_WEAPON',
            params_json='{"offense_level": 1}',
            enabled=True,
        )
        Technology.objects.create(
            category=energy,
            level=2,
            name='Mass Drivers II',
            tech_type='ENERGY_WEAPON',
            params_json='{"offense_level": 0.5}',
            enabled=True,
        )
        # SHIELD highest contributes its own properties, including offense bonus.
        Technology.objects.create(
            category=electronics,
            level=1,
            name='Field Couplers',
            tech_type='SHIELD',
            params_json='{"defense_level": 1, "offense_level": 1}',
            enabled=True,
        )
        Technology.objects.create(
            category=electronics,
            level=1,
            name='Warp Theory',
            tech_type='PROPULSION',
            params_json='{"max_warp_speed": 4}',
            enabled=True,
        )

        rows = ensure_player_research_rows(self.player)
        for row in rows:
            row.current_level = 2.0
            row.save(update_fields=['current_level'])

        effects = get_player_tech_effects(self.player)
        # offense: 2^0.5 * 2^1 => 2^1.5, represented back as level 1.5
        self.assertAlmostEqual(effects['offense_level'], 1.5, places=4)
        self.assertAlmostEqual(effects['defense_level'], 1.0, places=4)
        self.assertEqual(effects['max_warp_speed'], 4)

    def test_tech_effects_stack_log_levels_additively(self):
        energy = ResearchCategory.objects.create(
            code='ENER2', name='Energy2', enabled=True
        )
        materials = ResearchCategory.objects.create(
            code='MAT2', name='Materials2', enabled=True
        )

        Technology.objects.create(
            category=energy,
            level=1,
            name='Weapon Core',
            tech_type='ENERGY_WEAPON',
            params_json='{"offense_level": 1.25}',
            enabled=True,
        )
        Technology.objects.create(
            category=materials,
            level=1,
            name='Shield Core',
            tech_type='SHIELD',
            params_json='{"defense_level": 0.75}',
            enabled=True,
        )
        Technology.objects.create(
            category=materials,
            level=1,
            name='Hybrid Core',
            tech_type='SHIELD',
            params_json='{"offense_level": 0.5, "defense_level": 0.5}',
            enabled=True,
        )

        rows = ensure_player_research_rows(self.player)
        for row in rows:
            row.current_level = 1.0
            row.save(update_fields=['current_level'])

        effects = get_player_tech_effects(self.player)
        self.assertAlmostEqual(effects['offense_level'], 1.75, places=4)
        self.assertAlmostEqual(effects['defense_level'], 1.25, places=4)
