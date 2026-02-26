from django.test import TestCase

from ..models import Fleet, FleetOrders, ProductionOrder, ResearchCategory, Technology
from ..research import (
    build_research_budget,
    ensure_player_research_rows,
    get_player_tech_effects,
    get_player_colony_defense_level,
)
from ..turn import (
    GameTurn,
    MERGE_COMBAT_RETENTION,
    normalize_ship_count,
    tech_level_to_multiplier,
    multiplier_to_tech_level,
)
from ._util import default_game


class ResearchTurnTest(TestCase):
    def setUp(self):
        self.game = default_game(stars=5)
        self.player = self.game.players.first()
        self.star = self.player.homeworld

    def _reset_research_catalog(self):
        Technology.objects.all().delete()
        ResearchCategory.objects.all().delete()

    def test_build_lab_production_order(self):
        self.star.labs = 0
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
        self._reset_research_catalog()
        category = ResearchCategory.objects.create(
            code='RT_ENERGY_A', name='Energy', enabled=True
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
        row = next(item for item in rows if item.category_id == category.id)
        for item in rows:
            item.allocation_percent = 100.0 if item.id == row.id else 0.0
            item.save(update_fields=['allocation_percent'])

        GameTurn(self.game).research()
        row.refresh_from_db()
        self.assertGreaterEqual(row.current_level, 1.0)
        self.assertGreaterEqual(int(row.stored_rp), 0)

    def test_research_budget_can_include_unused_buildpoints(self):
        self.player.convert_unused_buildpoints_to_research = True
        self.player.save(update_fields=['convert_unused_buildpoints_to_research'])
        self.star.mines = 0
        self.star.factories = 10
        self.star.defenses = 0
        self.star.shipyards = 0
        self.star.labs = 0
        self.star.colonists = 10000
        self.star.buildpoints_consumed = 30
        self.star.save()

        budget = build_research_budget(self.player)
        self.assertEqual(budget['lab_generated_rp'], 0)
        self.assertEqual(budget['converted_rp'], 35)
        self.assertEqual(budget['generated_rp'], 35)

    def test_leftover_balance_points_convert_to_one_time_research_bonus(self):
        category = ResearchCategory.objects.create(
            code='LEFT', name='Leftover', enabled=True
        )
        Technology.objects.create(
            category=category,
            level=1,
            name='Primer',
            tech_type='GENERAL',
            params_json='{}',
        )
        self.player.spend_leftover_points_on_research = True
        self.player.leftover_points = 3.0
        self.player.save(update_fields=['spend_leftover_points_on_research', 'leftover_points'])
        self.star.mines = 0
        self.star.factories = 0
        self.star.defenses = 0
        self.star.shipyards = 0
        self.star.labs = 0
        self.star.colonists = 10000
        self.star.buildpoints_consumed = 0
        self.star.save()

        budget_before = build_research_budget(self.player)
        self.assertEqual(budget_before['leftover_bonus_rp'], 30)
        self.assertEqual(budget_before['generated_rp'], 30)

        GameTurn(self.game).research()
        self.player.refresh_from_db()
        self.assertEqual(self.player.leftover_points, 0.0)

        budget_after = build_research_budget(self.player)
        self.assertEqual(budget_after['leftover_bonus_rp'], 0)

    def test_new_fleet_uses_unlocked_propulsion(self):
        self._reset_research_catalog()
        category = ResearchCategory.objects.create(
            code='RT_ENERGY_B', name='Energy', enabled=True
        )
        hull_category = ResearchCategory.objects.create(
            code='CONSTR', name='Construction', enabled=True
        )
        Technology.objects.create(
            category=category,
            level=1,
            name='Warp 7',
            tech_type='PROPULSION',
            params_json='{"max_warp_speed": 7, "fuel_efficiency": 1.15, "overmax_fuel_penalty": 0.85}',
        )
        Technology.objects.create(
            category=hull_category,
            level=6,
            name='Freighter Hull',
            tech_type='HULL',
            params_json='{"max_cargo_capacity": 400, "max_fuel": 200, "hull_thumbnail_class": "freighter", "defense_level": 0.2}',
        )
        rows = ensure_player_research_rows(self.player)
        for row in rows:
            row.current_level = 6.0
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
        self.assertGreaterEqual(new_fleet.max_safe_warp, 7)
        self.assertGreaterEqual(new_fleet.cargo_capacity, 400)
        self.assertEqual(new_fleet.fuel, 200.0)
        self.assertEqual(new_fleet.max_fuel, 200.0)
        self.assertGreaterEqual(new_fleet.fuel_efficiency, 1.0)
        self.assertLessEqual(new_fleet.overmax_fuel_penalty, 1.0)
        self.assertGreaterEqual(new_fleet.defense_level, 0.2)
        self.assertIn('/freighter/', new_fleet.thumbnail_path)

    def test_merge_preserves_proportional_combat_with_tradeoff(self):
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
        expected_attack_mult = (
            (
                normalize_ship_count(10) * tech_level_to_multiplier(0.0) +
                normalize_ship_count(1) * tech_level_to_multiplier(10.0)
            ) * MERGE_COMBAT_RETENTION
        ) / normalize_ship_count(11)
        expected_defense_mult = (
            (
                10 * tech_level_to_multiplier(0.0) +
                1 * tech_level_to_multiplier(10.0)
            ) * MERGE_COMBAT_RETENTION
        ) / 11.0
        self.assertAlmostEqual(
            fleet_b.offense_level,
            multiplier_to_tech_level(expected_attack_mult),
            places=4,
        )
        self.assertAlmostEqual(
            fleet_b.defense_level,
            multiplier_to_tech_level(expected_defense_mult),
            places=4,
        )

    def test_tech_effects_use_latest_per_type_and_sum_properties(self):
        self._reset_research_catalog()
        energy = ResearchCategory.objects.create(
            code='RT_ENERGY_C', name='Energy', enabled=True
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
        self._reset_research_catalog()
        energy = ResearchCategory.objects.create(
            code='ENER2', name='Energy2', enabled=True
        )
        materials = ResearchCategory.objects.create(
            code='MAT2', name='Materials2', enabled=True
        )

        Technology.objects.create(
            category=energy,
            level=99,
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
            level=99,
            name='Hybrid Core',
            tech_type='SHIELD',
            params_json='{"offense_level": 0.5, "defense_level": 0.5}',
            enabled=True,
        )

        rows = ensure_player_research_rows(self.player)
        for row in rows:
            row.current_level = 99.0
            row.save(update_fields=['current_level'])

        effects = get_player_tech_effects(self.player)
        self.assertAlmostEqual(effects['offense_level'], 1.75, places=4)
        self.assertAlmostEqual(effects['defense_level'], 0.5, places=4)

    def test_tech_effects_ignore_infrastructure_for_fleet_modifiers(self):
        self._reset_research_catalog()
        energy = ResearchCategory.objects.create(
            code='ENI', name='Energy-I', enabled=True
        )
        infra = ResearchCategory.objects.create(
            code='INI', name='Infra-I', enabled=True
        )
        Technology.objects.create(
            category=energy,
            level=99,
            name='Beam Core',
            tech_type='ENERGY_WEAPON',
            params_json='{"offense_level": 1.0}',
            enabled=True,
        )
        Technology.objects.create(
            category=infra,
            level=1,
            name='Defense Grid',
            tech_type='INFRASTRUCTURE',
            params_json='{"offense_level": 99.0, "defense_level": 99.0}',
            enabled=True,
        )

        rows = ensure_player_research_rows(self.player)
        for row in rows:
            row.current_level = 99.0
            row.save(update_fields=['current_level'])

        effects = get_player_tech_effects(self.player)
        self.assertAlmostEqual(effects['offense_level'], 1.0, places=4)
        self.assertAlmostEqual(effects['defense_level'], 0.0, places=4)

    def test_colony_defense_uses_latest_unlocked_technology(self):
        energy = ResearchCategory.objects.create(
            code='ECOL', name='EcoLogistics', enabled=True
        )
        weapons = ResearchCategory.objects.create(
            code='WCOL', name='War College', enabled=True
        )
        Technology.objects.create(
            category=energy,
            level=2,
            name='Planetary Barrier I',
            tech_type='INFRASTRUCTURE',
            params_json='{"colony_defense_level": 0.4}',
            display_order=10,
            enabled=True,
        )
        Technology.objects.create(
            category=weapons,
            level=3,
            name='Planetary Barrier II',
            tech_type='INFRASTRUCTURE',
            params_json='{"colony_defense_level": 0.7}',
            display_order=20,
            enabled=True,
        )
        Technology.objects.create(
            category=weapons,
            level=4,
            name='Planetary Barrier III',
            tech_type='INFRASTRUCTURE',
            params_json='{"colony_defense_level": 1.0}',
            display_order=30,
            enabled=True,
        )

        rows = ensure_player_research_rows(self.player)
        for row in rows:
            row.current_level = 3.0
            row.save(update_fields=['current_level'])

        self.assertAlmostEqual(
            get_player_colony_defense_level(self.player), 0.7, places=4
        )
