from django.test import TestCase

from ..models import Fleet, FleetOrders, ProductionOrder, ResearchCategory, Technology
from ..colony_rules import calculate_employment_percent
from ..research import (
    ensure_player_research_rows,
    get_player_administration_profile,
    get_player_available_production_orders,
    get_player_production_costs,
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
            1: {'bp': 120, 'ironium': 300, 'boranium': 0, 'germanium': 450},
            2: {'bp': 90, 'ironium': 225, 'boranium': 0, 'germanium': 325},
            3: {'bp': 70, 'ironium': 175, 'boranium': 0, 'germanium': 250},
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
            450,
        )

        ProductionOrder.objects.create(
            game=self.game,
            star=self.star,
            order_type='BUILD_ADMINISTRATION',
            quantity=1,
        )
        options = get_player_available_production_orders(self.player, self.star)
        self.assertNotIn('BUILD_ADMINISTRATION', [item['value'] for item in options])

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
        self.assertEqual(self.star.ironium_inventory, 310)

    def test_higher_administration_levels_reduce_build_cost(self):
        self._create_administration_tech(1, 1)
        level_one_costs = get_player_production_costs(self.player)
        self.assertEqual(level_one_costs['BUILD_ADMINISTRATION']['bp'], 120)
        self.assertEqual(level_one_costs['BUILD_ADMINISTRATION']['ironium'], 300)
        self.assertEqual(level_one_costs['BUILD_ADMINISTRATION']['germanium'], 450)

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
        self.star.ironium_inventory = 0
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
        self.star.ironium_inventory = 0
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

    def test_level_two_prioritises_mine_when_queue_resources_exceed_one_year(self):
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
        self.star.ironium_inventory = 0
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

        self.assertGreaterEqual(len(planned), 1)
        self.assertEqual(planned[0], 'BUILD_MINE')

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
        self.star.ironium_inventory = 0
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
        self.star.ironium_inventory = 0
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
        self.assertEqual(administration['cost']['germanium'], 450)

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
        self.assertEqual(self.star.labs, 0)

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
