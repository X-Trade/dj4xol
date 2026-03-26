from django.test import TestCase

from ..models import Fleet, FleetOrders, ProductionOrder, ResearchCategory, Salvage, Technology
from ..colony_rules import calculate_employment_percent
from ..research import (
    ensure_player_research_rows,
    get_player_administration_profile,
    get_player_available_production_orders,
    get_player_dyson_sphere_profile,
    get_player_production_costs,
    get_player_terraforming_profile,
)
from ..objectdetails import DetailBuilder
from ..turn import GameTurn
from ..micromanager_rules import (
    get_micromanager_candidate_orders,
    plan_micromanager_orders,
)
from ._util import default_game
from unittest.mock import patch


class AdministrationAutomationTest(TestCase):
    def setUp(self):
        self.game = default_game(stars=5)
        self.player = self.game.players.first()
        self.star = self.player.homeworld

    def _unlock_category_level(self, category, level):
        rows = ensure_player_research_rows(self.player)
        target = None
        for row in rows:
            if row.category_id == category.id:
                target = row
                break
        if target is None:
            raise AssertionError('Research row not created for category %s' % category.id)
        target.current_level = float(level)
        target.save(update_fields=['current_level'])
        return target

    def _create_administration_tech(self, tech_level, administration_level):
        category = ResearchCategory.objects.create(
            code='AUTO%s' % tech_level,
            name='Automation %s' % tech_level,
            enabled=True,
        )
        build_cost = {
            1: {'bp': 120, 'ironium': 350, 'boranium': 0, 'germanium': 250},
            2: {'bp': 90, 'ironium': 225, 'boranium': 0, 'germanium': 325},
            3: {'bp': 70, 'ironium': 175, 'boranium': 0, 'germanium': 250},
            4: {'bp': 60, 'ironium': 100, 'boranium': 0, 'germanium': 260},
        }[administration_level]
        Technology.objects.create(
            category=category,
            level=tech_level,
            name='Administration %s' % administration_level,
            tech_type='INFRASTRUCTURE',
            params_json=(
                '{"administration_level": %s, "production_cost_overrides": '
                '{"BUILD_ADMINISTRATION": {"bp": %s, "ironium": %s, '
                '"boranium": %s, "germanium": %s, "colonists": 0}}}'
            ) % (
                administration_level,
                build_cost['bp'],
                build_cost['ironium'],
                build_cost['boranium'],
                build_cost['germanium'],
            ),
        )
        self._unlock_category_level(category, tech_level)
        return category

    def _create_terraforming_tech(self, tech_level, rate):
        category = ResearchCategory.objects.create(
            code='TFRM%s' % tech_level,
            name='Terraform %s' % tech_level,
            enabled=True,
        )
        Technology.objects.create(
            category=category,
            level=tech_level,
            name='Terraforming Relay %s' % tech_level,
            tech_type='INFRASTRUCTURE',
            params_json='{"terraforming_rate": %s}' % rate,
        )
        self._unlock_category_level(category, tech_level)
        return category

    def _create_dyson_sphere_tech(self, tech_level=24):
        category = ResearchCategory.objects.create(
            code='DYSON%s' % tech_level,
            name='Dyson %s' % tech_level,
            enabled=True,
        )
        Technology.objects.create(
            category=category,
            level=tech_level,
            name='Dyson Sphere',
            tech_type='INFRASTRUCTURE',
            params_json=(
                '{"dyson_sphere": true, "production_cost_overrides": '
                '{"BUILD_DYSON_SPHERE": {"bp": 2000, "ironium": 1000, '
                '"boranium": 500, "germanium": 600, "resource_x": 200, '
                '"resource_y": 0, "resource_z": 100, "colonists": 0}}}'
            ),
        )
        self._unlock_category_level(category, tech_level)
        return category

    def test_administration_order_available_only_when_unlocked_and_needed(self):
        options = get_player_available_production_orders(self.player, self.star)
        self.assertNotIn('BUILD_ADMINISTRATION', [item['value'] for item in options])

        self._create_administration_tech(1, 1)
        profile = get_player_administration_profile(self.player)
        self.assertEqual(profile.get('level'), 1)

        options = get_player_available_production_orders(self.player, self.star)
        self.assertIn('BUILD_ADMINISTRATION', [item['value'] for item in options])
        administration = next(
            item for item in options
            if item['value'] == 'BUILD_ADMINISTRATION'
        )
        self.assertFalse(administration['repeat_allowed'])
        self.assertEqual(
            get_player_production_costs(self.player)['BUILD_ADMINISTRATION']['germanium'],
            250,
        )

        ProductionOrder.objects.create(
            game=self.game,
            star=self.star,
            order_type='BUILD_ADMINISTRATION',
            quantity=1,
        )
        options = get_player_available_production_orders(self.player, self.star)
        self.assertNotIn('BUILD_ADMINISTRATION', [item['value'] for item in options])

    def test_non_terraforming_infrastructure_does_not_override_terraforming(self):
        self._create_terraforming_tech(3, 0.1)
        self._create_administration_tech(4, 2)

        profile = get_player_terraforming_profile(self.player)

        self.assertAlmostEqual(profile.get('rate', 0.0), 0.1)
        self.assertIsNotNone(profile.get('tech'))
        self.assertEqual(profile['tech'].name, 'Terraforming Relay 3')

    def test_no_terraforming_race_gets_no_terraforming_profile(self):
        self.player.race_type.has_no_terraforming = True
        self.player.race_type.save(update_fields=['has_no_terraforming'])
        self._create_terraforming_tech(3, 0.1)

        profile = get_player_terraforming_profile(self.player)

        self.assertEqual(profile.get('rate'), 0.0)
        self.assertEqual(profile.get('costs'), {})
        self.assertIsNone(profile.get('tech'))

    def test_advanced_terraforming_gate_blocks_higher_tier_unlock_without_trait(self):
        self._create_terraforming_tech(7, 0.01)
        gated = ResearchCategory.objects.create(
            code='TFRM10',
            name='Terraform 10',
            enabled=True,
        )
        Technology.objects.create(
            category=gated,
            level=10,
            name='Terraforming Relay 10',
            tech_type='INFRASTRUCTURE',
            params_json=(
                '{"terraforming_rate": 0.02, '
                '"race_type": "has only_basic_terraforming == False"}'
            ),
        )
        self._unlock_category_level(gated, 10)

        profile = get_player_terraforming_profile(self.player)

        self.assertAlmostEqual(profile.get('rate', 0.0), 0.02)
        self.assertEqual(profile['tech'].name, 'Terraforming Relay 10')

    def test_only_basic_terraforming_blocks_higher_tier_terraforming(self):
        self.player.race_type.only_basic_terraforming = True
        self.player.race_type.save(
            update_fields=['only_basic_terraforming']
        )
        self._create_terraforming_tech(7, 0.01)
        gated = ResearchCategory.objects.create(
            code='TFRM10A',
            name='Terraform 10A',
            enabled=True,
        )
        Technology.objects.create(
            category=gated,
            level=10,
            name='Terraforming Relay 10A',
            tech_type='INFRASTRUCTURE',
            params_json=(
                '{"terraforming_rate": 0.02, '
                '"race_type": "has only_basic_terraforming == False"}'
            ),
        )
        self._unlock_category_level(gated, 10)

        profile = get_player_terraforming_profile(self.player)

        self.assertAlmostEqual(profile.get('rate', 0.0), 0.01)
        self.assertEqual(profile['tech'].name, 'Terraforming Relay 7')

        self.star.production_orders.all().delete()
        self.star.has_administration = True
        self.star.save(update_fields=['has_administration'])
        options = get_player_available_production_orders(self.player, self.star)
        self.assertNotIn('BUILD_ADMINISTRATION', [item['value'] for item in options])

    def test_build_administration_order_completes(self):
        self._create_administration_tech(1, 1)
        self.star.colonists = 200_000
        self.star.factories = 20
        self.star.ironium_inventory = 1_000
        self.star.boranium_inventory = 1_000
        self.star.germanium_inventory = 1_000
        self.star.save()

        ProductionOrder.objects.create(
            game=self.game,
            star=self.star,
            order_type='BUILD_ADMINISTRATION',
            quantity=1,
        )

        GameTurn(self.game).production()
        self.star.refresh_from_db()
        self.assertTrue(self.star.has_administration)

    def test_remove_administration_order_available_with_negative_ironium_refund(self):
        self._create_administration_tech(2, 2)
        self.star.has_administration = True
        self.star.save(update_fields=['has_administration'])

        options = get_player_available_production_orders(self.player, self.star)
        self.assertIn('REMOVE_ADMINISTRATION', [item['value'] for item in options])
        costs = get_player_production_costs(self.player)
        self.assertEqual(costs['REMOVE_ADMINISTRATION']['bp'], 40)
        self.assertEqual(costs['REMOVE_ADMINISTRATION']['ironium'], -225)

    def test_remove_administration_order_completes_and_refunds_ironium(self):
        self._create_administration_tech(1, 1)
        self.star.has_administration = True
        self.star.colonists = 200_000
        self.star.factories = 20
        self.star.ironium_inventory = 10
        self.star.save(update_fields=[
            'has_administration', 'colonists', 'factories',
            'ironium_inventory',
        ])
        ProductionOrder.objects.create(
            game=self.game,
            star=self.star,
            order_type='REMOVE_ADMINISTRATION',
            position=1,
            quantity=1,
        )

        GameTurn(self.game).production()
        self.star.refresh_from_db()

        self.assertFalse(self.star.has_administration)
        self.assertEqual(self.star.ironium_inventory, 360)

    def test_dyson_sphere_order_available_only_when_unlocked_and_needed(self):
        options = get_player_available_production_orders(self.player, self.star)
        self.assertNotIn('BUILD_DYSON_SPHERE', [item['value'] for item in options])

        self._create_dyson_sphere_tech()
        profile = get_player_dyson_sphere_profile(self.player)
        self.assertTrue(profile.get('unlocked'))

        options = get_player_available_production_orders(self.player, self.star)
        self.assertIn('BUILD_DYSON_SPHERE', [item['value'] for item in options])
        dyson = next(
            item for item in options
            if item['value'] == 'BUILD_DYSON_SPHERE'
        )
        self.assertFalse(dyson['repeat_allowed'])
        costs = get_player_production_costs(self.player)
        self.assertEqual(costs['BUILD_DYSON_SPHERE']['bp'], 2000)
        self.assertEqual(costs['BUILD_DYSON_SPHERE']['ironium'], 1000)
        self.assertEqual(costs['BUILD_DYSON_SPHERE']['resource_x'], 200)
        self.assertEqual(costs['BUILD_DYSON_SPHERE']['resource_z'], 100)

        ProductionOrder.objects.create(
            game=self.game,
            star=self.star,
            order_type='BUILD_DYSON_SPHERE',
            quantity=1,
        )
        options = get_player_available_production_orders(self.player, self.star)
        self.assertNotIn('BUILD_DYSON_SPHERE', [item['value'] for item in options])

    def test_build_dyson_sphere_order_completes_once(self):
        self._create_dyson_sphere_tech()
        self.star.mines = 0
        self.star.factories = 200
        self.star.labs = 0
        self.star.defenses = 0
        self.star.shipyards = 0
        self.star.colonists = 500_000
        self.star.ironium_inventory = 5_000
        self.star.boranium_inventory = 5_000
        self.star.germanium_inventory = 5_000
        self.star.resource_x_inventory = 500
        self.star.resource_z_inventory = 500
        self.star.save(update_fields=[
            'mines',
            'factories',
            'labs',
            'defenses',
            'shipyards',
            'colonists',
            'ironium_inventory',
            'boranium_inventory',
            'germanium_inventory',
            'resource_x_inventory',
            'resource_z_inventory',
        ])

        ProductionOrder.objects.create(
            game=self.game,
            star=self.star,
            order_type='BUILD_DYSON_SPHERE',
            quantity=3,
            repeat=True,
        )

        GameTurn(self.game).production()
        self.star.refresh_from_db()

        self.assertTrue(self.star.has_dyson_sphere)
        self.assertEqual(self.star.ironium_inventory, 4000)
        self.assertEqual(self.star.boranium_inventory, 4500)
        self.assertEqual(self.star.germanium_inventory, 4400)
        self.assertEqual(self.star.resource_x_inventory, 300)
        self.assertEqual(self.star.resource_z_inventory, 400)
        self.assertFalse(
            self.star.production_orders.filter(order_type='BUILD_DYSON_SPHERE').exists()
        )

    def test_higher_administration_levels_reduce_build_cost(self):
        self._create_administration_tech(1, 1)
        level_one_costs = get_player_production_costs(self.player)
        self.assertEqual(level_one_costs['BUILD_ADMINISTRATION']['bp'], 120)
        self.assertEqual(level_one_costs['BUILD_ADMINISTRATION']['ironium'], 350)
        self.assertEqual(level_one_costs['BUILD_ADMINISTRATION']['germanium'], 250)

        self._create_administration_tech(2, 2)
        level_two_costs = get_player_production_costs(self.player)
        self.assertEqual(level_two_costs['BUILD_ADMINISTRATION']['bp'], 90)
        self.assertEqual(level_two_costs['BUILD_ADMINISTRATION']['ironium'], 225)
        self.assertEqual(level_two_costs['BUILD_ADMINISTRATION']['germanium'], 325)

        self._create_administration_tech(3, 3)
        level_three_costs = get_player_production_costs(self.player)
        self.assertEqual(level_three_costs['BUILD_ADMINISTRATION']['bp'], 70)
        self.assertEqual(level_three_costs['BUILD_ADMINISTRATION']['ironium'], 175)
        self.assertEqual(level_three_costs['BUILD_ADMINISTRATION']['germanium'], 250)

        self._create_administration_tech(4, 4)
        level_four_costs = get_player_production_costs(self.player)
        self.assertEqual(level_four_costs['BUILD_ADMINISTRATION']['bp'], 60)
        self.assertEqual(level_four_costs['BUILD_ADMINISTRATION']['ironium'], 100)
        self.assertEqual(level_four_costs['BUILD_ADMINISTRATION']['germanium'], 260)

    def test_player_added_orders_stay_ahead_of_micromanager_orders(self):
        self._create_administration_tech(1, 1)
        self.player.race_type.population_growth_multiplier = 0
        self.player.race_type.save(update_fields=['population_growth_multiplier'])
        self.star.has_administration = True
        self.star.colonists = 20_000
        self.star.mines = 0
        self.star.factories = 0
        self.star.labs = 0
        self.star.defenses = 0
        self.star.shipyards = 0
        self.star.ironium_inventory = 500
        self.star.boranium_inventory = 0
        self.star.germanium_inventory = 0
        self.star.ironium_yield = 100
        self.star.boranium_yield = 100
        self.star.germanium_yield = 100
        self.star.save()

        ProductionOrder.objects.create(
            game=self.game,
            star=self.star,
            order_type='BUILD_FACTORY',
            position=1,
            quantity=1,
        )
        GameTurn(self.game)._refresh_administration_production_queue(self.star)

        orders = list(self.star.production_orders.order_by('position'))
        self.assertGreaterEqual(len(orders), 2)
        self.assertFalse(orders[0].added_by_micromanager)
        self.assertTrue(orders[1].added_by_micromanager)

    def test_level_one_projects_player_factory_order_before_planning_auto(self):
        self._create_administration_tech(1, 1)
        self.player.race_type.population_growth_multiplier = 0
        self.player.race_type.save(update_fields=['population_growth_multiplier'])
        self.star.has_administration = True
        self.star.colonists = 20_000
        self.star.mines = 1
        self.star.factories = 0
        self.star.labs = 0
        self.star.defenses = 0
        self.star.shipyards = 0
        self.star.ironium_inventory = 500
        self.star.boranium_inventory = 0
        self.star.germanium_inventory = 0
        self.star.ironium_yield = 100
        self.star.boranium_yield = 100
        self.star.germanium_yield = 100
        self.star.save()

        ProductionOrder.objects.create(
            game=self.game,
            star=self.star,
            order_type='BUILD_FACTORY',
            position=1,
            quantity=1,
        )
        GameTurn(self.game)._refresh_administration_production_queue(self.star)

        orders = list(self.star.production_orders.order_by('position'))
        self.assertGreaterEqual(len(orders), 2)
        self.assertEqual(orders[0].order_type, 'BUILD_FACTORY')
        self.assertFalse(orders[0].added_by_micromanager)
        self.assertEqual(orders[1].order_type, 'BUILD_MINE')
        self.assertTrue(orders[1].added_by_micromanager)

    def test_candidate_orders_put_first_mine_first(self):
        self._create_administration_tech(1, 1)
        self.player.race_type.population_growth_multiplier = 0
        self.player.race_type.save(update_fields=['population_growth_multiplier'])
        self.star.has_administration = True
        self.star.colonists = 20_000
        self.star.mines = 0
        self.star.factories = 3
        self.star.labs = 0
        self.star.defenses = 0
        self.star.shipyards = 0
        self.star.ironium_yield = 100
        self.star.boranium_yield = 100
        self.star.germanium_yield = 100
        self.star.save()

        candidates = get_micromanager_candidate_orders(
            self.player, self.star, 1
        )

        self.assertGreaterEqual(len(candidates), 1)
        self.assertEqual(candidates[0], 'BUILD_MINE')

    def test_candidate_orders_put_first_factory_before_other_support(self):
        self._create_administration_tech(2, 2)
        self.player.race_type.population_growth_multiplier = 0
        self.player.race_type.save(update_fields=['population_growth_multiplier'])
        self.star.has_administration = True
        self.star.colonists = 100_000
        self.star.mines = 20
        self.star.factories = 0
        self.star.labs = 0
        self.star.defenses = 0
        self.star.shipyards = 0
        self.star.ironium_inventory = 10
        self.star.boranium_inventory = 0
        self.star.germanium_inventory = 0
        self.star.ironium_yield = 0
        self.star.boranium_yield = 0
        self.star.germanium_yield = 0
        self.star.save()

        candidates = get_micromanager_candidate_orders(
            self.player, self.star, 2, fleets_in_orbit=2
        )

        self.assertGreaterEqual(len(candidates), 1)
        self.assertEqual(candidates[0], 'BUILD_FACTORY')
        self.assertNotEqual(candidates[0], 'BUILD_SHIPYARD')

    def test_level_one_can_manage_defenses_but_not_labs_or_shipyards(self):
        self._create_administration_tech(1, 1)
        self.player.race_type.population_growth_multiplier = 0
        self.player.race_type.save(update_fields=['population_growth_multiplier'])
        self.star.has_administration = True
        self.star.colonists = 100_000
        self.star.mines = 10
        self.star.factories = 10
        self.star.labs = 0
        self.star.defenses = 0
        self.star.shipyards = 0
        self.star.ironium_inventory = 200
        self.star.boranium_inventory = 0
        self.star.germanium_inventory = 0
        self.star.ironium_yield = 0
        self.star.boranium_yield = 0
        self.star.germanium_yield = 0
        self.star.save()

        candidates = get_micromanager_candidate_orders(
            self.player,
            self.star,
            1,
            fleets_in_orbit=3,
        )

        self.assertIn('BUILD_DEFENSE', candidates)
        self.assertNotIn('BUILD_LAB', candidates)
        self.assertNotIn('BUILD_SHIPYARD', candidates)

    def test_level_one_can_seed_one_lab_and_shipyard_with_clear_surplus(self):
        self._create_administration_tech(1, 1)
        self.player.race_type.population_growth_multiplier = 0
        self.player.race_type.save(update_fields=['population_growth_multiplier'])
        self.star.has_administration = True
        self.star.colonists = 100_000
        self.star.mines = 20
        self.star.factories = 30
        self.star.labs = 0
        self.star.defenses = 0
        self.star.shipyards = 0
        self.star.ironium_inventory = 2_000
        self.star.boranium_inventory = 2_000
        self.star.germanium_inventory = 2_000
        self.star.ironium_yield = 0
        self.star.boranium_yield = 0
        self.star.germanium_yield = 0
        self.star.save()

        candidates = get_micromanager_candidate_orders(
            self.player,
            self.star,
            1,
            cost_map=get_player_production_costs(self.player),
        )

        self.assertIn('BUILD_LAB', candidates)
        self.assertIn('BUILD_SHIPYARD', candidates)

    def test_level_one_does_not_seed_lab_or_shipyard_without_surplus(self):
        self._create_administration_tech(1, 1)
        self.player.race_type.population_growth_multiplier = 0
        self.player.race_type.save(update_fields=['population_growth_multiplier'])
        self.star.has_administration = True
        self.star.colonists = 100_000
        self.star.mines = 20
        self.star.factories = 30
        self.star.labs = 0
        self.star.defenses = 0
        self.star.shipyards = 0
        self.star.ironium_inventory = 100
        self.star.boranium_inventory = 10
        self.star.germanium_inventory = 10
        self.star.ironium_yield = 0
        self.star.boranium_yield = 0
        self.star.germanium_yield = 0
        self.star.save()

        candidates = get_micromanager_candidate_orders(
            self.player,
            self.star,
            1,
            cost_map=get_player_production_costs(self.player),
        )

        self.assertNotIn('BUILD_LAB', candidates)
        self.assertNotIn('BUILD_SHIPYARD', candidates)

    def test_level_one_ignores_safe_mine_cap_but_level_two_respects_it(self):
        self._create_administration_tech(2, 2)
        self.player.race_type.population_growth_multiplier = 0
        self.player.race_type.save(update_fields=['population_growth_multiplier'])
        self.star.has_administration = True
        self.star.colonists = 100_000
        self.star.mines = 4
        self.star.factories = 0
        self.star.labs = 0
        self.star.defenses = 0
        self.star.shipyards = 0
        self.star.ironium_inventory = 1_000
        self.star.boranium_inventory = 1_000
        self.star.germanium_inventory = 1_000
        self.star.ironium_yield = 10
        self.star.boranium_yield = 0
        self.star.germanium_yield = 0
        self.star.resource_x_yield = 0
        self.star.resource_y_yield = 0
        self.star.resource_z_yield = 0
        self.star.save()

        level_one_candidates = get_micromanager_candidate_orders(
            self.player,
            self.star,
            1,
            cost_map=get_player_production_costs(self.player),
        )
        level_two_candidates = get_micromanager_candidate_orders(
            self.player,
            self.star,
            2,
            cost_map=get_player_production_costs(self.player),
        )

        self.assertIn('BUILD_MINE', level_one_candidates)
        self.assertNotIn('BUILD_MINE', level_two_candidates)

    def test_level_two_prioritises_factory_when_queue_bp_exceeds_one_year(self):
        self._create_administration_tech(2, 2)
        self.player.race_type.population_growth_multiplier = 0
        self.player.race_type.save(update_fields=['population_growth_multiplier'])
        self.star.has_administration = True
        self.star.colonists = 20_000
        self.star.mines = 10
        self.star.factories = 1
        self.star.labs = 0
        self.star.defenses = 0
        self.star.shipyards = 0
        self.star.ironium_inventory = 10_000
        self.star.boranium_inventory = 10_000
        self.star.germanium_inventory = 10_000
        self.star.ironium_yield = 100
        self.star.boranium_yield = 100
        self.star.germanium_yield = 100
        self.star.save()
        ProductionOrder.objects.create(
            game=self.game,
            star=self.star,
            order_type='BUILD_SHIPYARD',
            position=1,
            quantity=2,
        )

        planned = plan_micromanager_orders(
            self.player,
            self.star,
            2,
            fleets_in_orbit=1,
            cost_map=get_player_production_costs(self.player),
            queue_requirements={'bp': 200, 'ironium': 500, 'boranium': 100,
                                'germanium': 200, 'resource_x': 0,
                                'resource_y': 0, 'resource_z': 0},
        )

        self.assertGreaterEqual(len(planned), 1)
        self.assertEqual(planned[0], 'BUILD_FACTORY')

    def test_level_two_prefers_support_when_factories_run_ahead_of_balance(self):
        self._create_administration_tech(2, 2)
        self.player.race_type.population_growth_multiplier = 0
        self.player.race_type.save(update_fields=['population_growth_multiplier'])
        self.star.has_administration = True
        self.star.colonists = 60_000
        self.star.mines = 10
        self.star.factories = 20
        self.star.labs = 5
        self.star.defenses = 4
        self.star.shipyards = 0
        self.star.ironium_inventory = 5_000
        self.star.boranium_inventory = 5_000
        self.star.germanium_inventory = 5_000
        self.star.ironium_yield = 0
        self.star.boranium_yield = 0
        self.star.germanium_yield = 0
        self.star.save()

        candidates = get_micromanager_candidate_orders(
            self.player,
            self.star,
            2,
            cost_map=get_player_production_costs(self.player),
        )

        self.assertGreaterEqual(len(candidates), 1)
        self.assertEqual(candidates[0], 'BUILD_DEFENSE')

    def test_level_two_falls_back_to_factory_when_support_is_unaffordable(self):
        self._create_administration_tech(2, 2)
        self.player.race_type.population_growth_multiplier = 0
        self.player.race_type.save(update_fields=['population_growth_multiplier'])
        self.star.has_administration = True
        self.star.colonists = 5_000_000
        self.star.mines = 10
        self.star.factories = 100
        self.star.labs = 5
        self.star.defenses = 5
        self.star.shipyards = 0
        self.star.ironium_inventory = 200
        self.star.boranium_inventory = 0
        self.star.germanium_inventory = 0
        self.star.ironium_yield = 0
        self.star.boranium_yield = 0
        self.star.germanium_yield = 0
        self.star.save()

        planned = plan_micromanager_orders(
            self.player,
            self.star,
            2,
            fleets_in_orbit=0,
            cost_map=get_player_production_costs(self.player),
        )

        self.assertGreaterEqual(len(planned), 1)
        self.assertEqual(planned[0], 'BUILD_FACTORY')

    def test_level_two_stops_when_queue_already_exceeds_one_year_resources(self):
        self._create_administration_tech(2, 2)
        self.player.race_type.population_growth_multiplier = 0
        self.player.race_type.save(update_fields=['population_growth_multiplier'])
        self.star.has_administration = True
        self.star.colonists = 20_000
        self.star.mines = 1
        self.star.factories = 10
        self.star.labs = 0
        self.star.defenses = 0
        self.star.shipyards = 0
        self.star.ironium_inventory = 200
        self.star.boranium_inventory = 0
        self.star.germanium_inventory = 0
        self.star.ironium_yield = 100
        self.star.boranium_yield = 0
        self.star.germanium_yield = 100
        self.star.save()

        planned = plan_micromanager_orders(
            self.player,
            self.star,
            2,
            fleets_in_orbit=1,
            cost_map=get_player_production_costs(self.player),
            queue_requirements={'bp': 40, 'ironium': 400, 'boranium': 0,
                                'germanium': 200, 'resource_x': 0,
                                'resource_y': 0, 'resource_z': 0},
        )

        self.assertEqual(planned, [])

    def test_micromanager_can_spend_growth_resources_for_overemployed_mechanical_colony(self):
        self._create_administration_tech(2, 2)
        self.star.has_administration = True
        self.star.colonists = 60_000
        self.star.mines = 10
        self.star.factories = 20
        self.star.labs = 10
        self.star.defenses = 10
        self.star.shipyards = 0
        self.star.gravity = self.player.gravity_center
        self.star.temperature = self.player.temperature_center
        self.star.radiation = self.player.radiation_center
        self.player.race_type.population_growth_multiplier = 0.8
        self.player.race_type.population_growth_uses_resources = True
        self.player.race_type.save(update_fields=[
            'population_growth_multiplier',
            'population_growth_uses_resources',
        ])
        self.star.ironium_inventory = 7
        self.star.boranium_inventory = 5
        self.star.germanium_inventory = 1_000
        self.star.ironium_yield = 100
        self.star.boranium_yield = 100
        self.star.germanium_yield = 100
        self.star.save()

        planned = plan_micromanager_orders(
            self.player,
            self.star,
            2,
            fleets_in_orbit=0,
            cost_map=get_player_production_costs(self.player),
        )

        self.assertIn('BUILD_FACTORY', planned)

    def test_tier_three_mechanical_does_not_queue_colonist_growth_orders(self):
        self._create_administration_tech(3, 3)
        self.star.has_administration = True
        self.star.colonists = 100_000
        self.star.mines = 30
        self.star.factories = 30
        self.star.labs = 15
        self.star.defenses = 15
        self.star.shipyards = 0
        self.player.race_type.is_mechanical = True
        self.player.race_type.save(update_fields=['is_mechanical'])
        self.star.ironium_inventory = 500_000
        self.star.boranium_inventory = 500_000
        self.star.germanium_inventory = 500_000
        self.star.ironium_yield = 0
        self.star.boranium_yield = 0
        self.star.germanium_yield = 0
        self.star.save()

        planned = plan_micromanager_orders(
            self.player,
            self.star,
            3,
            fleets_in_orbit=0,
            cost_map=get_player_production_costs(self.player),
        )

        self.assertNotIn('BUILD_COLONISTS_1K', planned)
        self.assertNotIn('BUILD_COLONISTS_1M', planned)

    def test_tier_four_mechanical_can_queue_colonist_growth_from_45_percent(self):
        self._create_administration_tech(4, 4)
        self.star.has_administration = True
        self.star.colonists = 100_000
        self.star.mines = 20
        self.star.factories = 20
        self.star.labs = 5
        self.star.defenses = 5
        self.star.shipyards = 0
        self.player.race_type.is_mechanical = True
        self.player.race_type.save(update_fields=['is_mechanical'])
        self.star.ironium_inventory = 500
        self.star.boranium_inventory = 500
        self.star.germanium_inventory = 500
        self.star.ironium_yield = 0
        self.star.boranium_yield = 0
        self.star.germanium_yield = 0
        self.star.save()

        planned = plan_micromanager_orders(
            self.player,
            self.star,
            4,
            fleets_in_orbit=0,
            cost_map=get_player_production_costs(self.player),
        )

        self.assertIn('BUILD_COLONISTS_1K', planned)

    def test_tier_four_mechanical_1k_growth_ignores_planning_resource_caps(self):
        self._create_administration_tech(4, 4)
        self.star.has_administration = True
        self.star.colonists = 100_000
        self.star.mines = 20
        self.star.factories = 20
        self.star.labs = 5
        self.star.defenses = 5
        self.star.shipyards = 0
        self.player.race_type.is_mechanical = True
        self.player.race_type.save(update_fields=['is_mechanical'])
        self.star.ironium_inventory = 500
        self.star.boranium_inventory = 500
        self.star.germanium_inventory = 500
        self.star.ironium_yield = 0
        self.star.boranium_yield = 0
        self.star.germanium_yield = 0
        self.star.save()

        planned = plan_micromanager_orders(
            self.player,
            self.star,
            4,
            fleets_in_orbit=0,
            cost_map=get_player_production_costs(self.player),
            queue_requirements={
                'bp': 0,
                'ironium': 10_000,
                'boranium': 0,
                'germanium': 0,
                'resource_x': 0,
                'resource_y': 0,
                'resource_z': 0,
            },
        )

        self.assertIn('BUILD_COLONISTS_1K', planned)

    def test_tier_four_mechanical_prioritises_colonists_at_90_percent_employment(self):
        self._create_administration_tech(4, 4)
        self.star.has_administration = True
        self.star.colonists = 100_000
        self.star.mines = 30
        self.star.factories = 30
        self.star.labs = 15
        self.star.defenses = 15
        self.star.shipyards = 0
        self.player.race_type.is_mechanical = True
        self.player.race_type.save(update_fields=['is_mechanical'])
        self.star.ironium_inventory = 300_000
        self.star.boranium_inventory = 120_000
        self.star.germanium_inventory = 120_000
        self.star.ironium_yield = 0
        self.star.boranium_yield = 0
        self.star.germanium_yield = 0
        self.star.save()

        planned = plan_micromanager_orders(
            self.player,
            self.star,
            4,
            fleets_in_orbit=0,
            cost_map=get_player_production_costs(self.player),
        )

        self.assertTrue(planned)
        self.assertEqual(planned[0], 'BUILD_COLONISTS_1M')

    def test_micromanager_can_spend_surplus_after_growth_reserve(self):
        self._create_administration_tech(2, 2)
        self.star.has_administration = True
        self.star.colonists = 60_000
        self.star.mines = 10
        self.star.factories = 20
        self.star.labs = 10
        self.star.defenses = 10
        self.star.shipyards = 0
        self.star.gravity = self.player.gravity_center
        self.star.temperature = self.player.temperature_center
        self.star.radiation = self.player.radiation_center
        self.player.race_type.population_growth_multiplier = 0.8
        self.player.race_type.population_growth_uses_resources = True
        self.player.race_type.save(update_fields=[
            'population_growth_multiplier',
            'population_growth_uses_resources',
        ])
        self.star.ironium_inventory = 500
        self.star.boranium_inventory = 500
        self.star.germanium_inventory = 1_000
        self.star.ironium_yield = 100
        self.star.boranium_yield = 100
        self.star.germanium_yield = 100
        self.star.save()

        planned = plan_micromanager_orders(
            self.player,
            self.star,
            2,
            fleets_in_orbit=0,
            cost_map=get_player_production_costs(self.player),
            queue_requirements={
                'bp': 1_000,
                'ironium': 0,
                'boranium': 0,
                'germanium': 0,
                'resource_x': 0,
                'resource_y': 0,
                'resource_z': 0,
            },
        )

        self.assertTrue(planned)

    def test_micromanager_coalesces_adjacent_orders_into_quantities(self):
        self._create_administration_tech(1, 1)
        self.player.race_type.population_growth_multiplier = 0
        self.player.race_type.save(update_fields=['population_growth_multiplier'])
        self.star.has_administration = True
        self.star.colonists = 20_000
        self.star.mines = 0
        self.star.factories = 0
        self.star.labs = 0
        self.star.defenses = 0
        self.star.shipyards = 0
        self.star.ironium_inventory = 200
        self.star.boranium_inventory = 0
        self.star.germanium_inventory = 0
        self.star.ironium_yield = 0
        self.star.boranium_yield = 0
        self.star.germanium_yield = 0
        self.star.save()

        GameTurn(self.game)._refresh_administration_production_queue(self.star)

        orders = list(
            self.star.production_orders.filter(
                added_by_micromanager=True
            ).order_by('position')
        )
        self.assertEqual(len(orders), 1)
        self.assertEqual(orders[0].order_type, 'BUILD_FACTORY')
        self.assertGreater(orders[0].quantity, 1)

    def test_micromanager_reuses_zero_progress_orders_when_refreshing(self):
        self._create_administration_tech(1, 1)
        self.player.race_type.population_growth_multiplier = 0
        self.player.race_type.save(update_fields=['population_growth_multiplier'])
        self.star.has_administration = True
        self.star.colonists = 20_000
        self.star.mines = 0
        self.star.factories = 0
        self.star.labs = 0
        self.star.defenses = 0
        self.star.shipyards = 0
        self.star.ironium_inventory = 200
        self.star.boranium_inventory = 0
        self.star.germanium_inventory = 0
        self.star.ironium_yield = 0
        self.star.boranium_yield = 0
        self.star.germanium_yield = 0
        self.star.save()

        game_turn = GameTurn(self.game)
        game_turn._refresh_administration_production_queue(self.star)
        first = self.star.production_orders.get(added_by_micromanager=True)

        game_turn._refresh_administration_production_queue(self.star)
        second = self.star.production_orders.get(added_by_micromanager=True)

        self.assertEqual(first.id, second.id)
        self.assertEqual(second.order_type, 'BUILD_FACTORY')
        self.assertGreater(second.quantity, 1)

    def test_micromanager_merges_new_run_into_matching_progressed_order(self):
        self._create_administration_tech(1, 1)
        self.player.race_type.population_growth_multiplier = 0
        self.player.race_type.save(update_fields=['population_growth_multiplier'])
        self.star.has_administration = True
        self.star.colonists = 20_000
        self.star.mines = 0
        self.star.factories = 0
        self.star.labs = 0
        self.star.defenses = 0
        self.star.shipyards = 0
        self.star.ironium_inventory = 200
        self.star.boranium_inventory = 0
        self.star.germanium_inventory = 0
        self.star.ironium_yield = 0
        self.star.boranium_yield = 0
        self.star.germanium_yield = 0
        self.star.save()
        order = ProductionOrder.objects.create(
            game=self.game,
            star=self.star,
            order_type='BUILD_FACTORY',
            position=1,
            quantity=12,
            completed=10,
            added_by_micromanager=True,
        )

        GameTurn(self.game)._refresh_administration_production_queue(self.star)
        order.refresh_from_db()

        self.assertEqual(
            self.star.production_orders.filter(
                added_by_micromanager=True
            ).count(),
            1,
        )
        self.assertEqual(order.quantity, 20)

    def test_level_two_queues_deeper_and_adds_support_when_jobs_are_critical(self):
        self._create_administration_tech(2, 2)
        self.player.race_type.population_growth_multiplier = 0
        self.player.race_type.save(update_fields=['population_growth_multiplier'])
        self.star.has_administration = True
        self.star.colonists = 2_000_000_000
        self.star.mines = 10
        self.star.factories = 1000
        self.star.labs = 0
        self.star.defenses = 4
        self.star.shipyards = 0
        self.star.ironium_inventory = 100_000
        self.star.boranium_inventory = 100_000
        self.star.germanium_inventory = 100_000
        self.star.ironium_yield = 0
        self.star.boranium_yield = 0
        self.star.germanium_yield = 0
        self.star.save()
        self.player.fleets.all().delete()

        GameTurn(self.game)._refresh_administration_production_queue(self.star)

        orders = list(
            self.star.production_orders.filter(
                added_by_micromanager=True
            ).order_by('position')
        )
        self.assertGreaterEqual(len(orders), 2)
        self.assertEqual(
            len(orders),
            len(set(order.order_type for order in orders)),
        )
        self.assertEqual(orders[0].order_type, 'BUILD_SHIPYARD')
        self.assertGreater(
            sum(
                order.quantity for order in orders
                if order.order_type == 'BUILD_DEFENSE'
            ),
            4,
        )
        self.assertGreater(
            sum(
                order.quantity for order in orders
                if order.order_type == 'BUILD_LAB'
            ),
            0,
        )
        self.assertGreater(
            sum(
                order.quantity for order in orders
                if order.order_type in ('BUILD_LAB', 'BUILD_DEFENSE')
            ),
            sum(
                order.quantity for order in orders
                if order.order_type == 'BUILD_FACTORY'
            ),
        )

    def test_level_one_auto_queue_is_limited_by_one_year_affordable_output(self):
        self._create_administration_tech(1, 1)
        self.player.race_type.population_growth_multiplier = 0
        self.player.race_type.save(update_fields=['population_growth_multiplier'])
        self.star.has_administration = True
        self.star.colonists = 2_000_000_000
        self.star.mines = 10
        self.star.factories = 10
        self.star.labs = 0
        self.star.defenses = 0
        self.star.shipyards = 0
        self.star.ironium_inventory = 250
        self.star.boranium_inventory = 0
        self.star.germanium_inventory = 0
        self.star.ironium_yield = 0
        self.star.boranium_yield = 0
        self.star.germanium_yield = 0
        self.star.save()

        GameTurn(self.game)._refresh_administration_production_queue(self.star)

        orders = list(
            self.star.production_orders.filter(
                added_by_micromanager=True
            ).order_by('position')
        )
        self.assertEqual(len(orders), 1)
        self.assertEqual(orders[0].order_type, 'BUILD_FACTORY')
        self.assertEqual(orders[0].quantity, 12)

    def test_level_two_converts_repeat_shipyard_order_to_auto_and_reduces_it(self):
        self._create_administration_tech(2, 2)
        self.player.race_type.population_growth_multiplier = 0
        self.player.race_type.save(update_fields=['population_growth_multiplier'])
        self.star.has_administration = True
        self.star.colonists = 100_000
        self.star.mines = 20
        self.star.factories = 20
        self.star.labs = 0
        self.star.defenses = 0
        self.star.shipyards = 0
        self.star.ironium_inventory = 5_000
        self.star.boranium_inventory = 5_000
        self.star.germanium_inventory = 5_000
        self.star.ironium_yield = 0
        self.star.boranium_yield = 0
        self.star.germanium_yield = 0
        self.star.save()
        self.player.fleets.all().delete()
        Fleet.objects.create(
            game=self.game,
            player=self.player,
            name='Orbit One',
            x=self.star.x,
            y=self.star.y,
        )
        order = ProductionOrder.objects.create(
            game=self.game,
            star=self.star,
            order_type='BUILD_SHIPYARD',
            position=1,
            quantity=4,
            repeat=True,
        )

        GameTurn(self.game)._refresh_administration_production_queue(self.star)
        order.refresh_from_db()

        self.assertTrue(order.added_by_micromanager)
        self.assertFalse(order.repeat)
        self.assertEqual(order.order_type, 'BUILD_SHIPYARD')
        self.assertEqual(order.quantity, 1)

    def test_level_two_can_delete_unstarted_repeat_player_infrastructure(self):
        self._create_administration_tech(2, 2)
        self.player.race_type.population_growth_multiplier = 0
        self.player.race_type.save(update_fields=['population_growth_multiplier'])
        self.star.has_administration = True
        self.star.colonists = 20_000
        self.star.mines = 10
        self.star.factories = 10
        self.star.labs = 0
        self.star.defenses = 0
        self.star.shipyards = 0
        self.star.ironium_inventory = 5_000
        self.star.boranium_inventory = 5_000
        self.star.germanium_inventory = 5_000
        self.star.ironium_yield = 0
        self.star.boranium_yield = 0
        self.star.germanium_yield = 0
        self.star.save()
        ProductionOrder.objects.create(
            game=self.game,
            star=self.star,
            order_type='BUILD_LAB',
            position=1,
            quantity=3,
            repeat=True,
        )

        GameTurn(self.game)._refresh_administration_production_queue(self.star)

        self.assertFalse(self.star.production_orders.exists())

    def test_level_two_can_queue_shipyard_when_under_five_year_horizon(self):
        self._create_administration_tech(2, 2)
        self.player.race_type.population_growth_multiplier = 0
        self.player.race_type.save(update_fields=['population_growth_multiplier'])
        self.star.has_administration = True
        self.star.colonists = 100_000
        self.star.mines = 10
        self.star.factories = 5
        self.star.labs = 0
        self.star.defenses = 0
        self.star.shipyards = 0
        self.star.ironium_inventory = 250
        self.star.boranium_inventory = 50
        self.star.germanium_inventory = 100
        self.star.ironium_yield = 0
        self.star.boranium_yield = 0
        self.star.germanium_yield = 0
        self.star.save()

        planned = plan_micromanager_orders(
            self.player,
            self.star,
            2,
            fleets_in_orbit=1,
            cost_map=get_player_production_costs(self.player),
        )

        self.assertGreaterEqual(len(planned), 1)
        self.assertEqual(planned[0], 'BUILD_SHIPYARD')

    def test_level_three_queues_dyson_when_under_nine_year_horizon(self):
        self._create_administration_tech(3, 3)
        self._create_dyson_sphere_tech()
        self.player.race_type.population_growth_multiplier = 0
        self.player.race_type.save(update_fields=['population_growth_multiplier'])
        self.star.has_administration = True
        self.star.has_dyson_sphere = False
        self.star.colonists = 2_000_000_000
        self.star.mines = 60
        self.star.factories = 300
        self.star.labs = 20
        self.star.defenses = 20
        self.star.shipyards = 0
        self.star.ironium_inventory = 1_000
        self.star.boranium_inventory = 500
        self.star.germanium_inventory = 600
        self.star.resource_x_inventory = 200
        self.star.resource_z_inventory = 100
        self.star.ironium_yield = 0
        self.star.boranium_yield = 0
        self.star.germanium_yield = 0
        self.star.resource_x_yield = 0
        self.star.resource_y_yield = 0
        self.star.resource_z_yield = 0
        self.star.save()

        planned = plan_micromanager_orders(
            self.player,
            self.star,
            3,
            fleets_in_orbit=0,
            dyson_available=True,
            cost_map=get_player_production_costs(self.player),
            limit=1,
        )

        self.assertGreaterEqual(len(planned), 1)
        self.assertEqual(planned[0], 'BUILD_DYSON_SPHERE')

    def test_level_three_skips_dyson_when_over_nine_year_horizon(self):
        self._create_administration_tech(3, 3)
        self._create_dyson_sphere_tech()
        self.player.race_type.population_growth_multiplier = 0
        self.player.race_type.save(update_fields=['population_growth_multiplier'])
        self.star.has_administration = True
        self.star.has_dyson_sphere = False
        self.star.colonists = 2_000_000_000
        self.star.mines = 10
        self.star.factories = 10
        self.star.labs = 0
        self.star.defenses = 0
        self.star.shipyards = 0
        self.star.ironium_inventory = 1_000
        self.star.boranium_inventory = 500
        self.star.germanium_inventory = 600
        self.star.resource_x_inventory = 200
        self.star.resource_z_inventory = 100
        self.star.ironium_yield = 0
        self.star.boranium_yield = 0
        self.star.germanium_yield = 0
        self.star.resource_x_yield = 0
        self.star.resource_y_yield = 0
        self.star.resource_z_yield = 0
        self.star.save()

        planned = plan_micromanager_orders(
            self.player,
            self.star,
            3,
            fleets_in_orbit=0,
            dyson_available=True,
            cost_map=get_player_production_costs(self.player),
            limit=1,
        )

        self.assertNotIn('BUILD_DYSON_SPHERE', planned)

    def test_level_three_skips_dyson_when_it_would_exceed_max_jobs(self):
        self._create_administration_tech(3, 3)
        self._create_dyson_sphere_tech()
        self.player.race_type.population_growth_multiplier = 0
        self.player.race_type.save(update_fields=['population_growth_multiplier'])
        self.star.has_administration = True
        self.star.has_dyson_sphere = False
        self.star.colonists = 600_000
        self.star.mines = 60
        self.star.factories = 40
        self.star.labs = 20
        self.star.defenses = 20
        self.star.shipyards = 0
        self.star.ironium_inventory = 1_000
        self.star.boranium_inventory = 500
        self.star.germanium_inventory = 600
        self.star.resource_x_inventory = 200
        self.star.resource_z_inventory = 100
        self.star.ironium_yield = 0
        self.star.boranium_yield = 0
        self.star.germanium_yield = 0
        self.star.resource_x_yield = 0
        self.star.resource_y_yield = 0
        self.star.resource_z_yield = 0
        self.star.save()

        planned = plan_micromanager_orders(
            self.player,
            self.star,
            3,
            fleets_in_orbit=0,
            dyson_available=True,
            cost_map=get_player_production_costs(self.player),
            limit=1,
        )

        self.assertNotIn('BUILD_DYSON_SPHERE', planned)

    def test_level_two_skips_shipyard_when_it_would_exceed_max_jobs(self):
        self._create_administration_tech(2, 2)
        self.player.race_type.population_growth_multiplier = 0
        self.player.race_type.save(update_fields=['population_growth_multiplier'])
        self.star.has_administration = True
        self.star.colonists = 12_000
        self.star.mines = 2
        self.star.factories = 0
        self.star.labs = 0
        self.star.defenses = 0
        self.star.shipyards = 0
        self.star.ironium_inventory = 5_000
        self.star.boranium_inventory = 5_000
        self.star.germanium_inventory = 5_000
        self.star.ironium_yield = 0
        self.star.boranium_yield = 0
        self.star.germanium_yield = 0
        self.star.save()

        candidates = get_micromanager_candidate_orders(
            self.player,
            self.star,
            2,
            fleets_in_orbit=1,
            cost_map=get_player_production_costs(self.player),
        )

        self.assertNotIn('BUILD_SHIPYARD', candidates)

    def test_detail_builder_marks_micromanager_orders_and_disables_admin_repeat(self):
        self._create_administration_tech(1, 1)
        self.star.has_administration = True
        self.star.save(update_fields=['has_administration'])
        ProductionOrder.objects.create(
            game=self.game,
            star=self.star,
            order_type='BUILD_ADMINISTRATION',
            position=1,
            repeat=False,
        )
        ProductionOrder.objects.create(
            game=self.game,
            star=self.star,
            order_type='BUILD_MINE',
            position=2,
            repeat=False,
            added_by_micromanager=True,
        )

        details = DetailBuilder(
            self.game,
            x=self.star.x,
            y=self.star.y,
            selected=self.star.short_id.lower(),
            player=self.player,
        ).build_detail()

        self.assertEqual(details['production_orders'][0]['type'], 'BUILD_ADMINISTRATION')
        self.assertFalse(details['production_orders'][0]['repeat_allowed'])
        self.assertTrue(details['production_orders'][1]['added_by_micromanager'])

    def test_infrastructure_detail_shows_administration_level(self):
        self._create_administration_tech(1, 1)
        self.star.has_administration = True
        self.star.save(update_fields=['has_administration'])

        details = DetailBuilder(
            self.game,
            x=self.star.x,
            y=self.star.y,
            selected=self.star.short_id.lower(),
            player=self.player,
        ).build_detail()

        self.assertEqual(details['infrastructure']['Administration'], 'Level 1')

    def test_available_production_details_mark_admin_repeat_disallowed(self):
        self._create_administration_tech(1, 1)
        details = DetailBuilder(
            self.game,
            x=self.star.x,
            y=self.star.y,
            selected=self.star.short_id.lower(),
            player=self.player,
        ).build_detail()

        administration = next(
            item for item in details['production_order_choices']
            if item['value'] == 'BUILD_ADMINISTRATION'
        )
        self.assertFalse(administration['repeat_allowed'])
        self.assertEqual(administration['cost']['germanium'], 250)

    def test_available_production_details_show_remove_administration_refund(self):
        self._create_administration_tech(2, 2)
        self.star.has_administration = True
        self.star.save(update_fields=['has_administration'])
        details = DetailBuilder(
            self.game,
            x=self.star.x,
            y=self.star.y,
            selected=self.star.short_id.lower(),
            player=self.player,
        ).build_detail()

        remove_administration = next(
            item for item in details['production_order_choices']
            if item['value'] == 'REMOVE_ADMINISTRATION'
        )
        self.assertFalse(remove_administration['repeat_allowed'])
        self.assertEqual(remove_administration['cost']['ironium'], -225)

    def test_administration_level_one_queues_then_builds_mines_and_factories(self):
        self._create_administration_tech(1, 1)
        self.player.race_type.population_growth_multiplier = 0
        self.player.race_type.save(update_fields=['population_growth_multiplier'])
        self.star.has_administration = True
        self.star.colonists = 20_000
        self.star.mines = 0
        self.star.factories = 0
        self.star.labs = 0
        self.star.defenses = 0
        self.star.shipyards = 0
        self.star.ironium_inventory = 500
        self.star.boranium_inventory = 0
        self.star.germanium_inventory = 0
        self.star.ironium_yield = 100
        self.star.boranium_yield = 100
        self.star.germanium_yield = 100
        self.star.save()

        turn = GameTurn(self.game)
        turn.production()
        self.star.refresh_from_db()
        queued = list(
            self.star.production_orders.filter(
                added_by_micromanager=True
            ).order_by('position')
        )
        self.assertGreaterEqual(len(queued), 1)
        self.assertEqual(queued[0].order_type, 'BUILD_MINE')
        self.assertGreaterEqual(queued[0].quantity, 1)

        turn.production()
        self.star.refresh_from_db()

        self.assertGreater(self.star.mines, self.star.factories)
        self.assertGreaterEqual(self.star.mines, self.star.factories * 2)
        self.assertGreaterEqual(calculate_employment_percent(self.star), 50)
        self.assertLessEqual(calculate_employment_percent(self.star), 60)
        self.assertEqual(self.star.labs, 0)
        self.assertEqual(self.star.shipyards, 0)

    def test_administration_level_two_queues_then_adds_shipyards(self):
        self._create_administration_tech(2, 2)
        self.player.race_type.population_growth_multiplier = 0
        self.player.race_type.save(update_fields=['population_growth_multiplier'])
        self.star.has_administration = True
        self.star.colonists = 100_000
        self.star.mines = 20
        self.star.factories = 20
        self.star.labs = 0
        self.star.defenses = 0
        self.star.shipyards = 0
        self.star.ironium_inventory = 5_000
        self.star.boranium_inventory = 5_000
        self.star.germanium_inventory = 5_000
        self.star.ironium_yield = 30
        self.star.boranium_yield = 30
        self.star.germanium_yield = 30
        self.star.save()

        self.player.fleets.all().delete()
        Fleet.objects.create(
            game=self.game,
            player=self.player,
            name='Orbit One',
            x=self.star.x,
            y=self.star.y,
        )
        Fleet.objects.create(
            game=self.game,
            player=self.player,
            name='Orbit Two',
            x=self.star.x,
            y=self.star.y,
        )

        turn = GameTurn(self.game)
        turn.production()
        self.star.refresh_from_db()
        queued = list(
            self.star.production_orders.filter(
                added_by_micromanager=True
            ).order_by('position')
        )
        self.assertGreaterEqual(len(queued), 1)
        self.assertEqual(queued[0].order_type, 'BUILD_SHIPYARD')

        turn.production()
        self.star.refresh_from_db()

        self.assertEqual(self.star.shipyards, 2)
        self.assertEqual(self.star.factories, 20)
        self.assertLessEqual(self.star.labs, 1)

    def test_administration_level_three_queues_then_terraforms(self):
        self._create_administration_tech(3, 3)
        self._create_terraforming_tech(3, 0.1)
        self.player.race_type.population_growth_multiplier = 0
        self.player.race_type.save(update_fields=['population_growth_multiplier'])
        self.star.has_administration = True
        self.star.colonists = 100_000
        self.star.mines = 20
        self.star.factories = 30
        self.star.shipyards = 10
        self.star.ironium_inventory = 10_000
        self.star.boranium_inventory = 10_000
        self.star.germanium_inventory = 10_000
        self.star.ironium_yield = 30
        self.star.boranium_yield = 30
        self.star.germanium_yield = 30
        self.star.gravity = 0.0
        self.star.temperature = self.player.temperature_center
        self.star.radiation = self.player.radiation_center
        self.star.save()
        self.player.fleets.all().delete()

        turn = GameTurn(self.game)
        turn.production()
        self.star.refresh_from_db()
        queued = list(
            self.star.production_orders.filter(
                added_by_micromanager=True
            ).order_by('position')
        )
        self.assertGreaterEqual(len(queued), 1)
        self.assertEqual(queued[0].order_type, 'TERRAFORM_GRAVITY')

        turn.production()
        self.star.refresh_from_db()

        self.assertAlmostEqual(self.star.gravity, 0.1, places=4)

    def test_administration_level_four_dispatches_weak_idle_fleet_for_resupply(self):
        self._create_administration_tech(4, 4)
        self.star.has_administration = True
        self.star.colonists = 100_000
        self.star.mines = 10
        self.star.factories = 10
        self.star.labs = 0
        self.star.defenses = 0
        self.star.shipyards = 0
        self.star.ironium_inventory = 0
        self.star.boranium_inventory = 0
        self.star.germanium_inventory = 0
        self.star.ironium_yield = 0
        self.star.boranium_yield = 0
        self.star.germanium_yield = 0
        self.star.save()

        donor = self.game.stars.exclude(id=self.star.id).first()
        donor.player = self.player
        donor.colonists = 100_000
        donor.mines = 0
        donor.factories = 0
        donor.labs = 0
        donor.defenses = 0
        donor.shipyards = 0
        donor.ironium_inventory = 500
        donor.boranium_inventory = 0
        donor.germanium_inventory = 0
        donor.ironium_yield = 0
        donor.boranium_yield = 0
        donor.germanium_yield = 0
        donor.save()

        ProductionOrder.objects.create(
            game=self.game,
            star=self.star,
            order_type='BUILD_FACTORY',
            quantity=1,
            position=1,
        )

        self.player.fleets.all().delete()
        strong = Fleet.objects.create(
            game=self.game,
            player=self.player,
            name='Strong Guard',
            x=self.star.x,
            y=self.star.y,
            ship_count=5,
            offense_level=5,
            defense_level=5,
        )
        weak = Fleet.objects.create(
            game=self.game,
            player=self.player,
            name='Weak Courier',
            x=self.star.x,
            y=self.star.y,
            ship_count=1,
            offense_level=1,
            defense_level=1,
        )

        turn = GameTurn(self.game)
        turn._refresh_administration_fleet_dispatch_queue(self.star)

        self.assertFalse(strong.orders.exists())
        weak_orders = list(weak.orders.order_by('position', 'id'))
        self.assertEqual(len(weak_orders), 4)
        self.assertTrue(all(order.added_by_micromanager for order in weak_orders))
        self.assertEqual(weak_orders[0].order_type, 'MOVE')
        self.assertEqual(weak_orders[1].order_type, 'TRANSFER')
        self.assertEqual(weak_orders[1].transfer_type, 'LOAD')
        self.assertEqual(weak_orders[2].order_type, 'MOVE')
        self.assertEqual(weak_orders[3].order_type, 'TRANSFER')
        self.assertEqual(weak_orders[3].transfer_type, 'UNLOAD')
        self.assertEqual(weak_orders[0].target_star_id, donor.id)
        self.assertIsNone(weak_orders[0].target_salvage_id)
        self.assertEqual(weak_orders[1].target_star_id, donor.id)
        self.assertIsNone(weak_orders[1].target_salvage_id)
        self.assertEqual(weak_orders[2].target_star_id, self.star.id)
        self.assertEqual(weak_orders[3].target_star_id, self.star.id)

        cost_map = get_player_production_costs(self.player)
        expected_transfers = turn._transfer_amounts_for_need_and_supply(
            turn._resource_deficits_for_star(self.star, cost_map),
            turn._resource_surplus_for_star(donor, cost_map, reserve_factor=1),
            weak.cargo_remaining,
        )
        for key in (
            'ironium',
            'boranium',
            'germanium',
            'resource_x',
            'resource_y',
            'resource_z',
        ):
            self.assertEqual(
                getattr(weak_orders[1], 'transfer_%s' % key),
                int(expected_transfers.get(key, 0) or 0),
            )
            self.assertEqual(
                getattr(weak_orders[3], 'transfer_%s' % key),
                int(expected_transfers.get(key, 0) or 0),
            )

        details = DetailBuilder(
            self.game,
            x=weak.x,
            y=weak.y,
            selected=weak.short_id.lower(),
            player=self.player,
        ).build_detail()
        self.assertTrue(details['fleet_orders'][0]['added_by_micromanager'])

    def test_administration_level_three_does_not_dispatch_fleet_resupply(self):
        self._create_administration_tech(3, 3)
        self.star.has_administration = True
        self.star.colonists = 100_000
        self.star.mines = 10
        self.star.factories = 10
        self.star.ironium_inventory = 0
        self.star.ironium_yield = 0
        self.star.save()

        donor = self.game.stars.exclude(id=self.star.id).first()
        donor.player = self.player
        donor.colonists = 100_000
        donor.ironium_inventory = 500
        donor.ironium_yield = 0
        donor.save()

        ProductionOrder.objects.create(
            game=self.game,
            star=self.star,
            order_type='BUILD_FACTORY',
            quantity=1,
            position=1,
        )
        fleet = Fleet.objects.create(
            game=self.game,
            player=self.player,
            name='Idle Fleet',
            x=self.star.x,
            y=self.star.y,
        )

        turn = GameTurn(self.game)
        turn._refresh_administration_fleet_dispatch_queue(self.star)

        self.assertFalse(fleet.orders.exists())

    def test_ai_micromanager_level_five_can_queue_fleet_build_with_three_year_horizon(self):
        self.player.is_ai = True
        self.player.ai_module = 'micromanager'
        self.player.save(update_fields=['is_ai', 'ai_module'])
        self.star.has_administration = False
        self.star.colonists = 12_000
        self.star.mines = 0
        self.star.factories = 2  # 20 BP/year, below one-year BUILD_FLEET cost.
        self.star.labs = 0
        self.star.defenses = 0
        self.star.shipyards = 1
        self.star.ironium_inventory = 1_000
        self.star.boranium_inventory = 1_000
        self.star.germanium_inventory = 1_000
        self.star.ironium_yield = 0
        self.star.boranium_yield = 0
        self.star.germanium_yield = 0
        self.star.save()
        self.player.fleets.all().delete()
        self.star.production_orders.all().delete()

        turn = GameTurn(self.game)
        turn._refresh_administration_fleet_dispatch_queue(self.star)

        order = self.star.production_orders.filter(
            order_type='BUILD_FLEET',
            added_by_micromanager=True,
        ).first()
        self.assertIsNotNone(order)
        self.assertEqual(order.quantity, 1)

    def test_ai_micromanager_level_five_not_downgraded_by_admin_level_one_unlock(self):
        self.player.is_ai = True
        self.player.ai_module = 'micromanager'
        self.player.save(update_fields=['is_ai', 'ai_module'])
        self._create_administration_tech(1, 1)
        self.star.has_administration = False
        self.star.colonists = 12_000
        self.star.mines = 0
        self.star.factories = 2
        self.star.labs = 0
        self.star.defenses = 0
        self.star.shipyards = 1
        self.star.ironium_inventory = 1_000
        self.star.boranium_inventory = 1_000
        self.star.germanium_inventory = 1_000
        self.star.ironium_yield = 0
        self.star.boranium_yield = 0
        self.star.germanium_yield = 0
        self.star.save()
        self.player.fleets.all().delete()
        self.star.production_orders.all().delete()

        turn = GameTurn(self.game)
        turn._refresh_administration_fleet_dispatch_queue(self.star)

        order = self.star.production_orders.filter(
            order_type='BUILD_FLEET',
            added_by_micromanager=True,
        ).first()
        self.assertIsNotNone(order)
        self.assertEqual(order.quantity, 1)

    def test_ai_micromanager_locked_terraform_order_is_not_executed(self):
        self.player.is_ai = True
        self.player.ai_module = 'micromanager'
        self.player.save(update_fields=['is_ai', 'ai_module'])
        self.star.has_administration = False
        self.star.gravity = 0.25
        self.star.temperature = self.player.temperature_center
        self.star.radiation = self.player.radiation_center
        self.star.colonists = 200_000
        self.star.factories = 0
        self.star.mines = 0
        self.star.shipyards = 0
        self.star.production_orders.all().delete()
        self.star.save(update_fields=[
            'has_administration',
            'gravity',
            'temperature',
            'radiation',
            'colonists',
            'factories',
            'mines',
            'shipyards',
        ])
        initial_gravity = float(self.star.gravity)

        order = ProductionOrder.objects.create(
            game=self.game,
            star=self.star,
            order_type='TERRAFORM_GRAVITY',
            quantity=1,
            position=1,
            added_by_micromanager=True,
        )

        GameTurn(self.game).production()

        self.star.refresh_from_db()
        self.assertAlmostEqual(float(self.star.gravity), initial_gravity)
        self.assertFalse(
            ProductionOrder.objects.filter(id=order.id).exists()
        )

    def test_ai_micromanager_level_five_populates_production_queue_without_built_administration(self):
        self.player.is_ai = True
        self.player.ai_module = 'micromanager'
        self.player.save(update_fields=['is_ai', 'ai_module'])
        self.star.has_administration = False
        self.star.colonists = 200_000
        self.star.mines = 0
        self.star.factories = 0
        self.star.labs = 0
        self.star.defenses = 0
        self.star.shipyards = 0
        self.star.ironium_inventory = 2_000
        self.star.boranium_inventory = 2_000
        self.star.germanium_inventory = 2_000
        self.star.ironium_yield = 50
        self.star.boranium_yield = 50
        self.star.germanium_yield = 50
        self.star.save(update_fields=[
            'has_administration',
            'colonists',
            'mines',
            'factories',
            'labs',
            'defenses',
            'shipyards',
            'ironium_inventory',
            'boranium_inventory',
            'germanium_inventory',
            'ironium_yield',
            'boranium_yield',
            'germanium_yield',
        ])
        self.star.production_orders.all().delete()

        turn = GameTurn(self.game)
        turn._refresh_administration_production_queue(self.star)

        orders = list(self.star.production_orders.filter(
            added_by_micromanager=True,
        ).order_by('position', 'id'))
        self.assertTrue(orders)
        self.assertIn(orders[0].order_type, {'BUILD_MINE', 'BUILD_FACTORY', 'BUILD_DEFENSE'})

    def test_ai_micromanager_level_five_dispatches_one_idle_fleet_for_colonise(self):
        self.player.is_ai = True
        self.player.ai_module = 'micromanager'
        self.player.save(update_fields=['is_ai', 'ai_module'])
        self.star.has_administration = False
        self.star.colonists = 200_000
        self.star.mines = 0
        self.star.factories = 0
        self.star.labs = 0
        self.star.defenses = 0
        self.star.shipyards = 1
        self.star.ironium_inventory = 0
        self.star.boranium_inventory = 0
        self.star.germanium_inventory = 0
        self.star.ironium_yield = 0
        self.star.boranium_yield = 0
        self.star.germanium_yield = 0
        self.star.save()
        self.star.production_orders.all().delete()
        self.player.fleets.all().delete()

        target = self.game.stars.exclude(id=self.star.id).first()
        target.player = None
        target.x = int(self.star.x) + 1
        target.y = int(self.star.y)
        target.gravity = self.player.gravity_center
        target.temperature = self.player.temperature_center
        target.radiation = self.player.radiation_center
        target.colonists = 0
        target.save(update_fields=[
            'player', 'x', 'y', 'gravity', 'temperature', 'radiation', 'colonists',
        ])

        strong = Fleet.objects.create(
            game=self.game,
            player=self.player,
            name='Strong Guard',
            x=self.star.x,
            y=self.star.y,
            ship_count=5,
            offense_level=5,
            defense_level=5,
            cargo_capacity=120,
        )
        weak = Fleet.objects.create(
            game=self.game,
            player=self.player,
            name='Weak Colony',
            x=self.star.x,
            y=self.star.y,
            ship_count=1,
            offense_level=1,
            defense_level=1,
            cargo_capacity=120,
        )

        turn = GameTurn(self.game)
        turn._refresh_administration_fleet_dispatch_queue(self.star)

        colonise_fleets = []
        for fleet in (strong, weak):
            if fleet.orders.filter(order_type='COLONISE').exists():
                colonise_fleets.append(fleet)
        self.assertEqual(len(colonise_fleets), 1)
        routed = colonise_fleets[0]
        route_orders = list(routed.orders.order_by('position', 'id'))
        self.assertTrue(any(o.order_type == 'COLONISE' for o in route_orders))
        self.assertTrue(any(o.order_type == 'TRANSFER' and o.transfer_type == 'LOAD' for o in route_orders))
        load_order = next(
            o for o in route_orders
            if o.order_type == 'TRANSFER' and o.transfer_type == 'LOAD'
        )
        self.assertGreaterEqual(int(load_order.transfer_colonists or 0), 5)

    def test_ai_micromanager_level_five_prioritises_early_colonise_before_logistics(self):
        self.player.is_ai = True
        self.player.ai_module = 'micromanager'
        self.player.save(update_fields=['is_ai', 'ai_module'])
        self.star.has_administration = False
        self.star.colonists = 220_000
        self.star.mines = 0
        self.star.factories = 0
        self.star.labs = 0
        self.star.defenses = 0
        self.star.shipyards = 0
        self.star.ironium_inventory = 0
        self.star.boranium_inventory = 0
        self.star.germanium_inventory = 0
        self.star.ironium_yield = 0
        self.star.boranium_yield = 0
        self.star.germanium_yield = 0
        self.star.save(update_fields=[
            'has_administration',
            'colonists',
            'mines',
            'factories',
            'labs',
            'defenses',
            'shipyards',
            'ironium_inventory',
            'boranium_inventory',
            'germanium_inventory',
            'ironium_yield',
            'boranium_yield',
            'germanium_yield',
        ])
        self.star.production_orders.all().delete()
        self.player.fleets.all().delete()

        donor = self.game.stars.exclude(id=self.star.id).first()
        donor.player = self.player
        donor.colonists = 150_000
        donor.ironium_inventory = 800
        donor.boranium_inventory = 800
        donor.germanium_inventory = 800
        donor.save(update_fields=[
            'player',
            'colonists',
            'ironium_inventory',
            'boranium_inventory',
            'germanium_inventory',
        ])

        ProductionOrder.objects.create(
            game=self.game,
            star=self.star,
            order_type='BUILD_FACTORY',
            quantity=1,
            position=1,
        )

        target = self.game.stars.exclude(id__in=[self.star.id, donor.id]).first()
        target.player = None
        target.x = int(self.star.x) + 1
        target.y = int(self.star.y)
        target.gravity = self.player.gravity_center
        target.temperature = self.player.temperature_center
        target.radiation = self.player.radiation_center
        target.colonists = 0
        target.save(update_fields=[
            'player', 'x', 'y', 'gravity', 'temperature', 'radiation', 'colonists',
        ])

        strong = Fleet.objects.create(
            game=self.game,
            player=self.player,
            name='Home Patrol',
            x=self.star.x,
            y=self.star.y,
            ship_count=6,
            offense_level=6,
            defense_level=6,
            cargo_capacity=120,
        )
        weak = Fleet.objects.create(
            game=self.game,
            player=self.player,
            name='Colony Scout',
            x=self.star.x,
            y=self.star.y,
            ship_count=1,
            offense_level=1,
            defense_level=1,
            cargo_capacity=120,
        )

        turn = GameTurn(self.game)
        turn._refresh_administration_fleet_dispatch_queue(self.star)

        self.assertTrue(strong.orders.filter(
            order_type='PATROL',
            repeat=True,
            added_by_micromanager=True,
        ).exists())
        self.assertTrue(weak.orders.filter(
            order_type='COLONISE',
            added_by_micromanager=True,
        ).exists())

        transfer_orders = FleetOrders.objects.filter(
            fleet__in=[strong, weak],
            order_type='TRANSFER',
        )
        self.assertFalse(transfer_orders.filter(transfer_ironium__gt=0).exists())
        self.assertFalse(transfer_orders.filter(transfer_boranium__gt=0).exists())
        self.assertFalse(transfer_orders.filter(transfer_germanium__gt=0).exists())
        self.assertFalse(transfer_orders.filter(transfer_resource_x__gt=0).exists())
        self.assertFalse(transfer_orders.filter(transfer_resource_y__gt=0).exists())
        self.assertFalse(transfer_orders.filter(transfer_resource_z__gt=0).exists())

    def test_ai_micromanager_level_five_assigns_patrol_orders_from_idle_fleets(self):
        self.player.is_ai = True
        self.player.ai_module = 'micromanager'
        self.player.save(update_fields=['is_ai', 'ai_module'])
        self.star.has_administration = False
        self.star.colonists = 200_000
        self.star.mines = 0
        self.star.factories = 0
        self.star.labs = 0
        self.star.defenses = 0
        self.star.shipyards = 1
        self.star.save(update_fields=[
            'has_administration',
            'colonists',
            'mines',
            'factories',
            'labs',
            'defenses',
            'shipyards',
        ])
        self.star.production_orders.all().delete()
        self.player.fleets.all().delete()

        fleets = []
        for idx in range(4):
            fleets.append(Fleet.objects.create(
                game=self.game,
                player=self.player,
                name='Patrol Candidate %s' % idx,
                x=self.star.x,
                y=self.star.y,
                ship_count=1 + idx,
                offense_level=1 + idx,
                defense_level=1 + idx,
            ))

        turn = GameTurn(self.game)
        with patch.object(
            GameTurn,
            '_best_colonise_target_for_colony',
            return_value=None,
        ):
            turn._refresh_administration_fleet_dispatch_queue(self.star)

        patrol_assigned = [
            fleet for fleet in fleets
            if fleet.orders.filter(
                order_type='PATROL',
                repeat=True,
                added_by_micromanager=True,
            ).exists()
        ]
        self.assertEqual(len(patrol_assigned), 1)

    def test_ai_micromanager_level_five_assigns_minimum_one_patrol_when_possible(self):
        self.player.is_ai = True
        self.player.ai_module = 'micromanager'
        self.player.save(update_fields=['is_ai', 'ai_module'])
        self.star.has_administration = False
        self.star.colonists = 200_000
        self.star.shipyards = 1
        self.star.save(update_fields=['has_administration', 'colonists', 'shipyards'])
        self.star.production_orders.all().delete()
        self.player.fleets.all().delete()
        fleet = Fleet.objects.create(
            game=self.game,
            player=self.player,
            name='Solo Defender',
            x=self.star.x,
            y=self.star.y,
            ship_count=3,
            offense_level=3,
            defense_level=3,
        )

        turn = GameTurn(self.game)
        with patch.object(
            GameTurn,
            '_best_colonise_target_for_colony',
            return_value=None,
        ):
            turn._refresh_administration_fleet_dispatch_queue(self.star)

        self.assertTrue(fleet.orders.filter(
            order_type='PATROL',
            repeat=True,
            added_by_micromanager=True,
        ).exists())

    def test_administration_level_four_can_collect_from_asteroids_when_colonies_cannot_spare(self):
        self._create_administration_tech(4, 4)
        self.star.has_administration = True
        self.star.colonists = 100_000
        self.star.mines = 10
        self.star.factories = 10
        self.star.labs = 0
        self.star.defenses = 0
        self.star.shipyards = 0
        self.star.ironium_inventory = 0
        self.star.boranium_inventory = 0
        self.star.germanium_inventory = 0
        self.star.ironium_yield = 0
        self.star.boranium_yield = 0
        self.star.germanium_yield = 0
        self.star.save()

        donor = self.game.stars.exclude(id=self.star.id).first()
        donor.player = self.player
        donor.colonists = 100_000
        donor.ironium_inventory = 0
        donor.boranium_inventory = 0
        donor.germanium_inventory = 0
        donor.ironium_yield = 0
        donor.boranium_yield = 0
        donor.germanium_yield = 0
        donor.save()

        salvage = Salvage.objects.create(
            game=self.game,
            x=int(self.star.x) + 1,
            y=int(self.star.y),
            salvage_type=Salvage.TYPE_ASTEROID_FIELD,
            ironium_inventory=500,
        )

        ProductionOrder.objects.create(
            game=self.game,
            star=self.star,
            order_type='BUILD_FACTORY',
            quantity=1,
            position=1,
        )

        self.player.fleets.all().delete()
        strong = Fleet.objects.create(
            game=self.game,
            player=self.player,
            name='Strong Guard',
            x=self.star.x,
            y=self.star.y,
            ship_count=5,
            offense_level=5,
            defense_level=5,
        )
        weak = Fleet.objects.create(
            game=self.game,
            player=self.player,
            name='Weak Courier',
            x=self.star.x,
            y=self.star.y,
            ship_count=1,
            offense_level=1,
            defense_level=1,
        )

        turn = GameTurn(self.game)
        turn._refresh_administration_fleet_dispatch_queue(self.star)

        self.assertFalse(strong.orders.exists())
        weak_orders = list(weak.orders.order_by('position', 'id'))
        self.assertEqual(len(weak_orders), 4)
        self.assertEqual(weak_orders[0].order_type, 'MOVE')
        self.assertEqual(weak_orders[0].target_salvage_id, salvage.id)
        self.assertEqual(weak_orders[1].order_type, 'TRANSFER')
        self.assertEqual(weak_orders[1].transfer_type, 'LOAD')
        self.assertEqual(weak_orders[1].target_salvage_id, salvage.id)
        self.assertEqual(weak_orders[2].order_type, 'MOVE')
        self.assertEqual(weak_orders[2].target_star_id, self.star.id)
        self.assertEqual(weak_orders[3].order_type, 'TRANSFER')
        self.assertEqual(weak_orders[3].transfer_type, 'UNLOAD')
        self.assertEqual(weak_orders[3].target_star_id, self.star.id)

    def test_administration_level_four_can_send_outbound_excess_delivery(self):
        self._create_administration_tech(4, 4)
        self.star.has_administration = True
        self.star.colonists = 100_000
        self.star.mines = 0
        self.star.factories = 0
        self.star.labs = 0
        self.star.defenses = 0
        self.star.shipyards = 0
        self.star.ironium_inventory = 1_000
        self.star.boranium_inventory = 0
        self.star.germanium_inventory = 0
        self.star.ironium_yield = 0
        self.star.boranium_yield = 0
        self.star.germanium_yield = 0
        self.star.save()
        self.star.production_orders.all().delete()

        needy = self.game.stars.exclude(id=self.star.id).first()
        needy.player = self.player
        needy.colonists = 100_000
        needy.ironium_inventory = 0
        needy.boranium_inventory = 0
        needy.germanium_inventory = 0
        needy.ironium_yield = 0
        needy.boranium_yield = 0
        needy.germanium_yield = 0
        needy.save()
        needy.production_orders.all().delete()
        ProductionOrder.objects.create(
            game=self.game,
            star=needy,
            order_type='BUILD_FACTORY',
            quantity=1,
            position=1,
        )

        self.player.fleets.all().delete()
        strong = Fleet.objects.create(
            game=self.game,
            player=self.player,
            name='Strong Guard',
            x=self.star.x,
            y=self.star.y,
            ship_count=5,
            offense_level=5,
            defense_level=5,
        )
        weak = Fleet.objects.create(
            game=self.game,
            player=self.player,
            name='Weak Courier',
            x=self.star.x,
            y=self.star.y,
            ship_count=1,
            offense_level=1,
            defense_level=1,
        )

        turn = GameTurn(self.game)
        turn._refresh_administration_fleet_dispatch_queue(self.star)

        self.assertFalse(strong.orders.exists())
        weak_orders = list(weak.orders.order_by('position', 'id'))
        self.assertEqual(len(weak_orders), 4)
        self.assertEqual(weak_orders[0].order_type, 'TRANSFER')
        self.assertEqual(weak_orders[0].transfer_type, 'LOAD')
        self.assertEqual(weak_orders[0].target_star_id, self.star.id)
        self.assertEqual(weak_orders[1].order_type, 'MOVE')
        self.assertEqual(weak_orders[1].target_star_id, needy.id)
        self.assertEqual(weak_orders[2].order_type, 'TRANSFER')
        self.assertEqual(weak_orders[2].transfer_type, 'UNLOAD')
        self.assertEqual(weak_orders[2].target_star_id, needy.id)
        self.assertEqual(weak_orders[3].order_type, 'MOVE')
        self.assertEqual(weak_orders[3].target_star_id, self.star.id)

        cost_map = get_player_production_costs(self.player)
        expected_transfers = turn._transfer_amounts_for_need_and_supply(
            turn._resource_deficits_for_star(needy, cost_map),
            turn._resource_surplus_for_star(self.star, cost_map, reserve_factor=2),
            weak.cargo_remaining,
        )
        for key in (
            'ironium',
            'boranium',
            'germanium',
            'resource_x',
            'resource_y',
            'resource_z',
        ):
            self.assertEqual(
                getattr(weak_orders[0], 'transfer_%s' % key),
                int(expected_transfers.get(key, 0) or 0),
            )
            self.assertEqual(
                getattr(weak_orders[2], 'transfer_%s' % key),
                int(expected_transfers.get(key, 0) or 0),
            )

    def test_micromanager_keeps_one_auto_order_per_type_over_multiple_years(self):
        self._create_administration_tech(2, 2)
        self.player.race_type.population_growth_multiplier = 0
        self.player.race_type.save(update_fields=['population_growth_multiplier'])
        self.star.has_administration = True
        self.star.colonists = 2_000_000
        self.star.mines = 10
        self.star.factories = 200
        self.star.labs = 0
        self.star.defenses = 0
        self.star.shipyards = 0
        self.star.ironium_inventory = 100_000
        self.star.boranium_inventory = 100_000
        self.star.germanium_inventory = 100_000
        self.star.ironium_yield = 0
        self.star.boranium_yield = 0
        self.star.germanium_yield = 0
        self.star.save()
        self.player.fleets.all().delete()

        ProductionOrder.objects.create(
            game=self.game,
            star=self.star,
            order_type='BUILD_FACTORY',
            position=1,
            quantity=3,
            repeat=False,
        )
        ProductionOrder.objects.create(
            game=self.game,
            star=self.star,
            order_type='BUILD_DEFENSE',
            position=2,
            quantity=5,
            repeat=True,
        )
        ProductionOrder.objects.create(
            game=self.game,
            star=self.star,
            order_type='BUILD_LAB',
            position=3,
            quantity=4,
            repeat=True,
        )

        turn = GameTurn(self.game)

        for _ in range(5):
            turn.production()
            self.star.refresh_from_db()
            auto_orders = list(
                self.star.production_orders.filter(
                    added_by_micromanager=True
                ).order_by('position')
            )
            auto_types = [order.order_type for order in auto_orders]
            self.assertEqual(len(auto_types), len(set(auto_types)))

    def test_bombardment_can_destroy_administration(self):
        self.star.has_administration = True
        self.star.colonists = 50_000
        self.star.defenses = 0
        self.star.save(update_fields=[
            'has_administration', 'colonists', 'defenses',
        ])

        fleet = Fleet.objects.create(
            game=self.game,
            player=self.player,
            name='Bomber',
            x=self.star.x,
            y=self.star.y,
            ship_count=5,
            has_bombs='CONVENTIONAL',
        )
        order = FleetOrders.objects.create(
            game=self.game,
            fleet=fleet,
            order_type='BOMB',
            target_star=self.star,
        )

        with patch.object(
            GameTurn,
            '_resolve_planetary_defense_fire_against_fleet',
            return_value={
                'destroyed': False,
                'integrity_lost': 0,
                'ships_lost': 0,
                'defense_mult': 1.0,
            },
        ), patch(
            'dj4xol.turn.bombardment_damage_k',
            return_value=1,
        ):
            GameTurn(self.game)._execute_bomb_order(fleet, order)

        self.star.refresh_from_db()
        self.assertFalse(self.star.has_administration)
