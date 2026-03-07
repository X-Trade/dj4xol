from django.test import TestCase

from ..models import Fleet, FleetOrders, ProductionOrder, ResearchCategory, Technology
from ..colony_rules import calculate_employment_percent
from ..research import (
    ensure_player_research_rows,
    get_player_administration_profile,
    get_player_available_production_orders,
)
from ..objectdetails import DetailBuilder
from ..turn import GameTurn
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
        Technology.objects.create(
            category=category,
            level=tech_level,
            name='Administration %s' % administration_level,
            tech_type='INFRASTRUCTURE',
            params_json='{"administration_level": %s}' % administration_level,
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
        self.star.colonists = 10_000
        self.star.factories = 5
        self.star.ironium_inventory = 500
        self.star.boranium_inventory = 500
        self.star.germanium_inventory = 500
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

    def test_player_added_orders_stay_ahead_of_micromanager_orders(self):
        self._create_administration_tech(1, 1)
        self.player.race_type.population_growth_multiplier = 0
        self.player.race_type.save(update_fields=['population_growth_multiplier'])
        self.star.has_administration = True
        self.star.colonists = 20_000
        self.star.mines = 0
        self.star.factories = 0
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

    def test_administration_level_one_builds_mines_and_factories(self):
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

        GameTurn(self.game).production()
        self.star.refresh_from_db()

        self.assertGreater(self.star.mines, self.star.factories)
        self.assertGreaterEqual(self.star.mines, self.star.factories * 2)
        self.assertGreaterEqual(calculate_employment_percent(self.star), 50)
        self.assertLessEqual(calculate_employment_percent(self.star), 60)
        self.assertEqual(self.star.labs, 0)
        self.assertEqual(self.star.shipyards, 0)

    def test_administration_level_two_adds_shipyards_for_orbital_fleets(self):
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

        GameTurn(self.game).production()
        self.star.refresh_from_db()

        self.assertEqual(self.star.shipyards, 2)
        self.assertEqual(self.star.factories, 20)
        self.assertEqual(self.star.labs, 0)

    def test_administration_level_three_can_terraform(self):
        self._create_administration_tech(3, 3)
        self._create_terraforming_tech(3, 0.1)
        self.player.race_type.population_growth_multiplier = 0
        self.player.race_type.save(update_fields=['population_growth_multiplier'])
        self.star.has_administration = True
        self.star.colonists = 100_000
        self.star.mines = 20
        self.star.factories = 30
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

        GameTurn(self.game).production()
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
