from ..turn import (
    GameTurn,
    KT_PER_MINE,
    HOMEWORLD_MIN_YIELD,
    NOVA_ASTEROID_FIELD_EXPOSED_POTENTIAL_FRACTION,
    NOVA_ASTEROID_FIELD_SPAWN_CHANCE,
    NOVA_BLACK_HOLE_SPAWN_CHANCE,
    NOVA_STAR_DESTRUCTION_CHANCE,
    YIELD_DEPLETION_RATE,
    apply_population_change,
    calculate_fleet_defense_multiplier,
    calculate_fleet_strength,
)
from ..objectdetails import DetailBuilder
from ..colony_rules import (
    habitability_proportion,
    calculate_growth_factor,
    calculate_habitability_factor,
    capacity_modifier,
    effective_capacity,
    BILLION,
    calculate_employment_percent,
    calculate_economy_percent,
    calculate_available_buildpoints,
    calculate_effective_defenses,
    calculate_productivity_percent,
    calculate_productivity_multiplier,
    calculate_economy_factor,
    COLONISTS_PER_JOB,
    BUILDPOINTS_PER_FACTORY,
)
from ..models import ProductionOrder, GameMessage, Fleet, FleetOrders, Star, Salvage, Anomaly, Account, Player, PlayerDiplomaticStance, Report, ServerRaceType, DiplomaticContract
from ..factory import GameFactory
from ..research import ensure_player_research_rows, get_global_research_max_level
from ..chance_rules import transfer_raid_success_chance
from ..hazard_rules import DANGER_HIGH, DANGER_LOW, DANGER_MEDIUM, DANGER_NONE
from ..messages import format_map_object
from django.test import TestCase
from ._util import default_game, get_default_race, get_default_race_type
from unittest.mock import patch, PropertyMock
from django.contrib.auth.models import User
import random


def _pin_test_star(star, game, x=64, y=64):
    x = min(int(game.map_size_x) - 2, int(x))
    y = min(int(game.map_size_y) - 2, int(y))
    for conflict in Star.objects.filter(game=game, x=x, y=y).exclude(id=star.id).order_by('id'):
        for idx in range(5, min(int(game.map_size_x), int(game.map_size_y)), 5):
            if idx == x and idx == y:
                continue
            if not Star.objects.filter(game=game, x=idx, y=idx).exclude(id=conflict.id).exists():
                conflict.x = idx
                conflict.y = idx
                conflict.save(update_fields=['x', 'y'])
                break
    star.x = x
    star.y = y
    star.save(update_fields=['x', 'y'])
    return x, y


class TestGameTurn(TestCase):
    def test_generate_turn(self):
        game = default_game()
        game.year = 1000
        game.save()
        GameTurn(game).generate_turn()
        self.assertEqual(game.year, 1001)

    def test_multiple_turns(self):
        game = default_game()
        game.year = 1000
        game.save()
        GameTurn(game).generate_turns(5)
        self.assertEqual(game.year, 1005)

    def test_refuses_empty_game(self):
        from ._util import default_game_factory, get_default_user
        factory = default_game_factory()
        game = factory.save()  # No players joined
        with self.assertRaises(Exception):
            GameTurn(game).generate_turn()

    def test_allied_stances_can_prevent_encounter_combat(self):
        user1 = User.objects.create_user('diplo_combat_1', 'dc1@test.com', 'pass')
        user2 = User.objects.create_user('diplo_combat_2', 'dc2@test.com', 'pass')
        account1 = Account.objects.create(django_user=user1, alias='DC1')
        account2 = Account.objects.create(django_user=user2, alias='DC2')
        factory = GameFactory()
        factory.set_map_size(100, 100)
        factory.set_owner(account1)
        factory.create_stars(8)
        game = factory.save()
        player1 = factory.join_player(account1, get_default_race())
        player2 = factory.join_player(account2, get_default_race(), invited=True)
        fleet1 = player1.fleets.first()
        fleet2 = player2.fleets.first()
        fleet1.x = fleet2.x = 25
        fleet1.y = fleet2.y = 25
        fleet1.save(update_fields=['x', 'y'])
        fleet2.save(update_fields=['x', 'y'])
        PlayerDiplomaticStance.objects.create(player=player1, target_player=player2, stance='ALLIED')
        PlayerDiplomaticStance.objects.create(player=player2, target_player=player1, stance='ALLIED')

        with patch('dj4xol.turn.random.random', return_value=0.99):
            GameTurn(game)._resolve_battle_at_location(25, 25, [fleet1, fleet2])

        self.assertEqual(Report.objects.filter(game=game, player=player1).count(), 0)
        self.assertEqual(Report.objects.filter(game=game, player=player2).count(), 0)

    def test_hostile_stances_force_encounter_combat(self):
        user1 = User.objects.create_user('diplo_combat_3', 'dc3@test.com', 'pass')
        user2 = User.objects.create_user('diplo_combat_4', 'dc4@test.com', 'pass')
        account1 = Account.objects.create(django_user=user1, alias='DC3')
        account2 = Account.objects.create(django_user=user2, alias='DC4')
        factory = GameFactory()
        factory.set_map_size(100, 100)
        factory.set_owner(account1)
        factory.create_stars(8)
        game = factory.save()
        player1 = factory.join_player(account1, get_default_race())
        player2 = factory.join_player(account2, get_default_race(), invited=True)
        fleet1 = player1.fleets.first()
        fleet2 = player2.fleets.first()
        fleet1.x = fleet2.x = 30
        fleet1.y = fleet2.y = 30
        fleet1.save(update_fields=['x', 'y'])
        fleet2.save(update_fields=['x', 'y'])
        PlayerDiplomaticStance.objects.create(player=player1, target_player=player2, stance='HOSTILE')
        PlayerDiplomaticStance.objects.create(player=player2, target_player=player1, stance='HOSTILE')

        with patch('dj4xol.turn.random.random', return_value=0.99):
            GameTurn(game)._resolve_battle_at_location(30, 30, [fleet1, fleet2])

        self.assertTrue(Report.objects.filter(game=game, player=player1).exists())
        self.assertTrue(Report.objects.filter(game=game, player=player2).exists())

    def test_pending_stance_applies_at_turn_start_and_notifies_target(self):
        user1 = User.objects.create_user('diplo_snapshot_1', 'ds1@test.com', 'pass')
        user2 = User.objects.create_user('diplo_snapshot_2', 'ds2@test.com', 'pass')
        account1 = Account.objects.create(django_user=user1, alias='DS1')
        account2 = Account.objects.create(django_user=user2, alias='DS2')
        factory = GameFactory()
        factory.set_map_size(200, 200)
        factory.set_owner(account1)
        factory.create_stars(10)
        game = factory.save()
        player1 = factory.join_player(account1, get_default_race())
        player2 = factory.join_player(account2, get_default_race(), invited=True)

        scanner = Fleet.objects.create(
            game=game,
            player=player1,
            name='Shared Scanner',
            x=90,
            y=90,
            ship_count=1,
            integrity=100,
            basic_scanner_range=6,
            advanced_scanner_range=0,
        )
        shared_star = game.stars.exclude(id=player1.homeworld_id).exclude(id=player2.homeworld_id).first()
        shared_star.player = player1
        shared_star.x = scanner.x + 4
        shared_star.y = scanner.y
        shared_star.save(update_fields=['player', 'x', 'y'])

        stance_row = PlayerDiplomaticStance.objects.create(
            player=player1,
            target_player=player2,
            stance='NEUTRAL',
            pending_stance='ALLIED',
        )

        GameTurn(game).generate_scanner_reports()
        self.assertFalse(
            Report.objects.filter(
                player=player2,
                target_type='star',
                target_id=shared_star.id,
            ).exists()
        )

        GameTurn(game).generate_turn()
        stance_row.refresh_from_db()
        self.assertEqual(stance_row.stance, 'ALLIED')

        self.assertTrue(
            Report.objects.filter(
                player=player2,
                target_type='star',
                target_id=shared_star.id,
            ).exists()
        )
        notice = player2.messages.filter(
            category='DIPLOMATIC',
            message__contains='has changed their stance with us',
        ).order_by('-id').first()
        self.assertIsNotNone(notice)
        self.assertIn('?target=%s' % player1.short_id, notice.message)
        self.assertIn('They are now Allied.', notice.message)

    def test_refuses_if_already_generating(self):
        """Turn generation should fail if is_generating flag is set."""
        game = default_game()
        game.is_generating = True
        game.save()
        with self.assertRaises(Exception) as context:
            GameTurn(game).generate_turn()
        self.assertIn('already in progress', str(context.exception))

    def test_clears_generating_flag_on_success(self):
        """is_generating flag should be cleared after successful turn."""
        game = default_game()
        self.assertFalse(game.is_generating)
        GameTurn(game).generate_turn()
        game.refresh_from_db()
        self.assertFalse(game.is_generating)

    def test_keeps_generating_flag_on_error(self):
        """is_generating flag should remain set if turn generation fails."""
        game = default_game()
        self.assertFalse(game.is_generating)
        # Mock _process_year to raise an error after lock is acquired
        with patch.object(GameTurn, '_process_year', side_effect=Exception("simulated error")):
            with self.assertRaises(Exception):
                GameTurn(game).generate_turn()
        game.refresh_from_db()
        self.assertTrue(game.is_generating)


class TestDetailBuilderEta(TestCase):
    def test_wormhole_eta_is_always_one_year(self):
        eta = DetailBuilder._estimate_eta_years(0, 0, 1000, 1000, 14)
        self.assertEqual(eta, 1)


class TestHabitabilityProportion(TestCase):
    def test_at_centre(self):
        """Value at centre returns 1.0."""
        self.assertEqual(habitability_proportion(0.5, 1.5, 1.0, 1.0), 1.0)

    def test_at_max_edge(self):
        """Value at max edge returns 0.0."""
        self.assertAlmostEqual(habitability_proportion(0.5, 1.5, 1.0, 1.5), 0.0)

    def test_at_min_edge(self):
        """Value at min edge returns 0.0."""
        self.assertAlmostEqual(habitability_proportion(0.5, 1.5, 1.0, 0.5), 0.0)

    def test_beyond_max(self):
        """Value beyond max returns negative."""
        result = habitability_proportion(0.5, 1.5, 1.0, 2.0)
        self.assertLess(result, 0)

    def test_below_min(self):
        """Value below min returns negative."""
        result = habitability_proportion(0.5, 1.5, 1.0, 0.0)
        self.assertLess(result, 0)


class TestCapacityModifier(TestCase):
    """Test capacity modifier with 10bn soft cap."""
    SOFT_CAP = 10 * BILLION

    def test_low_population_near_full_growth(self):
        """Low populations should have near-full growth modifier."""
        modifier = capacity_modifier(1000, self.SOFT_CAP)
        self.assertGreater(modifier, 0.9)

    def test_one_billion_still_good_growth(self):
        """At 1bn (10% of cap), growth should still be ~95%."""
        modifier = capacity_modifier(1 * BILLION, self.SOFT_CAP)
        self.assertGreater(modifier, 0.9)

    def test_five_billion_reduced_growth(self):
        """At 5bn (50% of cap), growth should be noticeably reduced."""
        modifier = capacity_modifier(5 * BILLION, self.SOFT_CAP)
        self.assertGreater(modifier, 0.5)
        self.assertLess(modifier, 0.9)

    def test_at_soft_cap_near_zero(self):
        """At soft cap, growth should be ~0."""
        modifier = capacity_modifier(self.SOFT_CAP, self.SOFT_CAP)
        self.assertAlmostEqual(modifier, 0.0, places=1)

    def test_above_soft_cap_negative(self):
        """Above soft cap, growth should be negative."""
        modifier = capacity_modifier(15 * BILLION, self.SOFT_CAP)
        self.assertLess(modifier, 0)

    def test_double_soft_cap_rapid_decline(self):
        """At 2x soft cap, should have rapid decline."""
        modifier = capacity_modifier(20 * BILLION, self.SOFT_CAP)
        self.assertLess(modifier, -0.9)

    def test_smaller_cap_scales_correctly(self):
        """Smaller soft cap should shift the curve proportionally."""
        small_cap = 1 * BILLION
        # At 10% of cap, should still have good growth
        modifier = capacity_modifier(100_000_000, small_cap)
        self.assertGreater(modifier, 0.9)
        # At cap, should be ~0
        modifier = capacity_modifier(small_cap, small_cap)
        self.assertAlmostEqual(modifier, 0.0, places=1)


class TestEffectiveCapacity(TestCase):
    def test_perfect_habitability_keeps_near_full_capacity(self):
        game = default_game(stars=5)
        player = game.players.first()
        star = player.homeworld
        star.base_capacity = 10000  # 10bn
        star.gravity = player.gravity_center
        star.temperature = player.temperature_center
        star.radiation = player.radiation_center
        cap = effective_capacity(player, star)
        self.assertEqual(cap, 10_000_000_000)

    def test_half_habitability_scales_to_millions(self):
        game = default_game(stars=5)
        player = game.players.first()
        star = player.homeworld
        star.base_capacity = 10000  # 10bn
        # Halfway from center to habitable edge => proportion 0.5 per env.
        star.gravity = player.gravity_center + ((player.hab_max('gravity') - player.gravity_center) * 0.5)
        star.temperature = player.temperature_center + ((player.hab_max('temperature') - player.temperature_center) * 0.5)
        star.radiation = player.radiation_center + ((player.hab_max('radiation') - player.radiation_center) * 0.5)
        cap = effective_capacity(player, star)
        self.assertGreaterEqual(cap, 1_000_000)
        self.assertLess(cap, 1_000_000_000)

    def test_edge_habitability_has_minimum_capacity_floor(self):
        game = default_game(stars=5)
        player = game.players.first()
        star = player.homeworld
        star.base_capacity = 10000
        star.gravity = player.hab_max('gravity')
        star.temperature = player.hab_max('temperature')
        star.radiation = player.hab_max('radiation')
        cap = effective_capacity(player, star)
        self.assertEqual(cap, 1_000_000)

    def test_ignored_environment_counts_as_fully_habitable(self):
        game = default_game(stars=5)
        player = game.players.first()
        star = player.homeworld
        star.base_capacity = 10000
        star.gravity = player.gravity_center
        star.temperature = player.temperature_center
        star.radiation = player.radiation_center
        star.mines = 0
        star.factories = 0
        star.labs = 0
        star.defenses = 0
        star.shipyards = 0
        baseline_factor = calculate_habitability_factor(player, star)

        star.gravity = 2.0
        player.race_type.ignores_gravity = True
        player.race_type.save(update_fields=['ignores_gravity'])

        self.assertAlmostEqual(calculate_habitability_factor(player, star), baseline_factor)
        self.assertEqual(effective_capacity(player, star), 10_000_000_000)

    def test_population_cap_multiplier_scales_capacity(self):
        game = default_game(stars=5)
        player = game.players.first()
        star = player.homeworld
        star.base_capacity = 10000
        star.gravity = player.gravity_center
        star.temperature = player.temperature_center
        star.radiation = player.radiation_center

        player.race_type.population_cap_multiplier = 50
        player.race_type.save(update_fields=['population_cap_multiplier'])
        self.assertEqual(effective_capacity(player, star), 500_000_000_000)

        player.race_type.population_cap_multiplier = 1000
        player.race_type.save(update_fields=['population_cap_multiplier'])
        self.assertEqual(effective_capacity(player, star), 10_000_000_000_000)


class TestPopulationGrowth(TestCase):
    def test_growth_on_perfect_homeworld(self):
        """Population grows on perfectly habitable planet."""
        game = default_game(stars=5)
        player = game.players.first()
        homeworld = player.homeworld
        initial_pop = homeworld.colonists
        GameTurn(game).generate_turn()
        homeworld.refresh_from_db()
        self.assertGreater(homeworld.colonists, initial_pop)

    def test_low_growth_at_edge(self):
        """Population growth is low/negative at edge of habitability."""
        game = default_game(stars=5)
        player = game.players.first()
        homeworld = player.homeworld
        # Set environmentals to edge of habitable range
        homeworld.gravity = player.hab_max('gravity')
        homeworld.temperature = player.hab_max('temperature')
        homeworld.radiation = player.hab_max('radiation')
        homeworld.colonists = 1000
        homeworld.save()
        GameTurn(game).generate_turn()
        homeworld.refresh_from_db()
        # At edge of habitability, growth should be much lower than optimal
        # (may be slight decline or very slow growth depending on balance)
        self.assertLess(homeworld.colonists, 1100)  # Not growing rapidly

    def test_decline_outside_range(self):
        """Population declines when outside habitable range."""
        game = default_game(stars=5)
        player = game.players.first()
        homeworld = player.homeworld
        # Set environmentals way outside range
        homeworld.gravity = 2.0  # way above hab_max of 1.5
        homeworld.temperature = 2.0
        homeworld.radiation = 2.0
        homeworld.colonists = 1000
        homeworld.save()
        GameTurn(game).generate_turn()
        homeworld.refresh_from_db()
        self.assertLess(homeworld.colonists, 1000)

    def test_growth_uses_ironium_before_two_thousand_births(self):
        game = default_game(stars=5)
        player = game.players.first()
        homeworld = player.homeworld
        player.race_type.population_growth_uses_resources = True
        player.race_type.save(update_fields=['population_growth_uses_resources'])

        homeworld.gravity = player.gravity_center
        homeworld.temperature = player.temperature_center
        homeworld.radiation = player.radiation_center
        homeworld.colonists = 15000
        homeworld.mines = 0
        homeworld.factories = 0
        homeworld.labs = 0
        homeworld.defenses = 0
        homeworld.shipyards = 0
        factor = calculate_growth_factor(player, homeworld)
        self.assertGreater(apply_population_change(homeworld.colonists, factor) - homeworld.colonists, 1000)

        homeworld.ironium_inventory = 1
        homeworld.boranium_inventory = 5000
        homeworld.save()

        GameTurn(game).population_growth()
        homeworld.refresh_from_db()

        self.assertEqual(homeworld.colonists, 16000)
        self.assertEqual(homeworld.ironium_inventory, 0)
        self.assertEqual(homeworld.boranium_inventory, 5000)

    def test_growth_uses_ironium_and_boranium_after_two_thousand_births(self):
        game = default_game(stars=5)
        player = game.players.first()
        homeworld = player.homeworld
        player.race_type.population_growth_uses_resources = True
        player.race_type.save(update_fields=['population_growth_uses_resources'])

        homeworld.gravity = player.gravity_center
        homeworld.temperature = player.temperature_center
        homeworld.radiation = player.radiation_center
        homeworld.colonists = 50000
        homeworld.mines = 0
        homeworld.factories = 0
        homeworld.labs = 0
        homeworld.defenses = 0
        homeworld.shipyards = 0
        factor = calculate_growth_factor(player, homeworld)
        baseline_growth = apply_population_change(homeworld.colonists, factor) - homeworld.colonists
        self.assertGreater(baseline_growth, 2000)

        homeworld.ironium_inventory = 3
        homeworld.boranium_inventory = 1
        homeworld.save()

        GameTurn(game).population_growth()
        homeworld.refresh_from_db()

        self.assertEqual(homeworld.colonists, 50000 + baseline_growth)
        self.assertEqual(homeworld.ironium_inventory, 0)
        self.assertEqual(homeworld.boranium_inventory, 0)

    def test_population_growth_multiplier_can_suppress_decline(self):
        game = default_game(stars=5)
        player = game.players.first()
        player.race_type.population_growth_multiplier = 0.0
        player.race_type.save(update_fields=['population_growth_multiplier'])
        homeworld = player.homeworld
        homeworld.gravity = 2.0
        homeworld.temperature = 2.0
        homeworld.radiation = 2.0
        homeworld.colonists = 1000
        homeworld.save()
        GameTurn(game).generate_turn()
        homeworld.refresh_from_db()
        self.assertEqual(homeworld.colonists, 1000)

    def test_empty_planet_loses_ownership(self):
        """Planet with zero population loses player ownership."""
        game = default_game(stars=5)
        player = game.players.first()
        # Find a non-homeworld star and colonize it minimally
        other_star = game.stars.exclude(pk=player.homeworld.pk).first()
        other_star.player = player
        other_star.colonists = 1
        # Make it extremely uninhabitable
        other_star.gravity = 2.0
        other_star.temperature = 2.0
        other_star.radiation = 2.0
        other_star.save()
        # Generate enough turns to kill off population
        for _ in range(10):
            GameTurn(game).generate_turn()
        other_star.refresh_from_db()
        self.assertEqual(other_star.colonists, 0)
        self.assertIsNone(other_star.player)

    def test_environmental_death_creates_message(self):
        """Deaths from environmental conditions should create a message."""
        game = default_game(stars=5)
        player = game.players.first()
        other_star = game.stars.exclude(pk=player.homeworld.pk).first()
        other_star.player = player
        other_star.colonists = 100000  # Large pop so some survive first turn
        # All factors outside habitable range to ensure negative habitability
        other_star.gravity = 1.7  # Outside hab_max of 1.5
        other_star.temperature = 1.7  # Outside hab_max of 1.5
        other_star.radiation = 1.7  # Outside hab_max of 1.5
        other_star.save()
        initial_messages = player.messages.count()
        GameTurn(game).generate_turn()
        other_star.refresh_from_db()
        # Colony should still exist but have lost colonists
        self.assertGreater(other_star.colonists, 0)
        self.assertLess(other_star.colonists, 100000)
        # Should have created at least one message about deaths
        self.assertGreater(player.messages.count(), initial_messages)
        # Check any message for environmental death keywords
        keywords = (
            'perished', 'died', 'lost', 'succumbed', 'claimed', 'fatal',
            'environment', 'harsh', 'hostile', 'inhospitable', 'hazard', 'exposure'
        )
        messages = list(player.messages.order_by('-id'))
        self.assertTrue(
            any(any(k in msg.message.lower() for k in keywords) for msg in messages),
            f"Expected death-related message, got: {messages[0].message if messages else 'none'}"
        )

    def test_colony_abandoned_creates_message(self):
        """Abandoned colonies should create a message."""
        game = default_game(stars=5)
        player = game.players.first()
        other_star = game.stars.exclude(pk=player.homeworld.pk).first()
        other_star.player = player
        other_star.colonists = 1
        other_star.gravity = 2.0
        other_star.temperature = 2.0
        other_star.radiation = 2.0
        other_star.save()
        # Generate turns until colony is abandoned
        for _ in range(10):
            GameTurn(game).generate_turn()
        # Should have a message about abandonment (various wordings)
        abandon_msgs = [m for m in player.messages.all()
                       if 'abandon' in m.message.lower() or
                          'lost' in m.message.lower() or
                          'fallen silent' in m.message.lower() or
                          'no more' in m.message.lower()]
        self.assertGreater(len(abandon_msgs), 0)

    def test_overcrowding_death_uses_overcrowding_message(self):
        """Overcrowding deaths on habitable worlds should not be environmental."""
        game = default_game(stars=5)
        player = game.players.first()
        homeworld = player.homeworld

        # Keep world habitable, but force severe over-capacity.
        homeworld.gravity = player.gravity_center
        homeworld.temperature = player.temperature_center
        homeworld.radiation = player.radiation_center
        cap = effective_capacity(player, homeworld)
        homeworld.colonists = cap * 2
        homeworld.save()

        initial_env = player.messages.filter(category='ENVIRONMENTAL').count()
        initial_pop = player.messages.filter(category='POPULATION').count()

        GameTurn(game).generate_turn()

        self.assertEqual(
            player.messages.filter(category='ENVIRONMENTAL').count(), initial_env
        )
        self.assertGreater(
            player.messages.filter(category='POPULATION').count(), initial_pop
        )


class TestTerraforming(TestCase):
    def test_terraforming_moves_toward_ideal(self):
        """Terraform helper moves environmental value toward player's ideal."""
        game = default_game(stars=5)
        player = game.players.first()
        homeworld = player.homeworld
        rows = ensure_player_research_rows(player)
        construction = next(
            row for row in rows if row.category.code == 'CONSTRUCTION'
        )
        construction.current_level = 7
        construction.save(update_fields=['current_level'])
        # Set gravity away from player's ideal
        player_ideal = player.gravity_center
        if player_ideal >= 0.3:
            homeworld.gravity = player_ideal - 0.3
        else:
            homeworld.gravity = min(2.0, player_ideal + 0.3)
        homeworld.save()

        order = ProductionOrder(
            game=game,
            star=homeworld,
            order_type='TERRAFORM_GRAVITY',
        )
        initial_gravity = homeworld.gravity
        GameTurn(game)._apply_terraform_order(homeworld, order)
        homeworld.refresh_from_db()
        self.assertGreater(homeworld.gravity, initial_gravity)
        self.assertLess(homeworld.gravity, player_ideal)

    def test_terraforming_multiple_factors(self):
        """Terraform helper handles multiple environmental factors."""
        game = default_game(stars=5)
        player = game.players.first()
        homeworld = player.homeworld
        rows = ensure_player_research_rows(player)
        construction = next(
            row for row in rows if row.category.code == 'CONSTRUCTION'
        )
        construction.current_level = 7
        construction.save(update_fields=['current_level'])
        gravity_ideal = player.gravity_center
        temp_ideal = player.temperature_center
        homeworld.gravity = max(0.0, gravity_ideal - 0.3)
        homeworld.temperature = min(2.0, temp_ideal + 0.3)
        homeworld.save()
        order_g = ProductionOrder(game=game, star=homeworld, order_type='TERRAFORM_GRAVITY')
        order_t = ProductionOrder(game=game, star=homeworld, order_type='TERRAFORM_TEMPERATURE')
        initial_g = homeworld.gravity
        initial_t = homeworld.temperature
        turn = GameTurn(game)
        turn._apply_terraform_order(homeworld, order_g)
        turn._apply_terraform_order(homeworld, order_t)
        homeworld.refresh_from_db()
        self.assertGreater(homeworld.gravity, initial_g)
        self.assertLess(homeworld.temperature, initial_t)

    def test_terraforming_multiplier_modifies_effect_strength(self):
        game = default_game(stars=5)
        player = game.players.first()
        player.race_type.terraforming_multiplier = 2.0
        player.race_type.save(update_fields=['terraforming_multiplier'])
        homeworld = player.homeworld
        rows = ensure_player_research_rows(player)
        construction = next(
            row for row in rows if row.category.code == 'CONSTRUCTION'
        )
        construction.current_level = 7
        construction.save(update_fields=['current_level'])
        player_ideal = player.gravity_center
        homeworld.gravity = max(0.0, player_ideal - 0.3)
        homeworld.save(update_fields=['gravity'])

        initial_gravity = homeworld.gravity
        order = ProductionOrder(
            game=game,
            star=homeworld,
            order_type='TERRAFORM_GRAVITY',
        )
        GameTurn(game)._apply_terraform_order(homeworld, order)
        homeworld.refresh_from_db()

        expected = initial_gravity + ((player_ideal - initial_gravity) * 0.02)
        self.assertAlmostEqual(homeworld.gravity, expected, places=6)


class TestRandomEvents(TestCase):
    def test_random_events_disabled_by_default(self):
        """Random events should not occur when disabled."""
        game = default_game(stars=5)
        self.assertFalse(game.random_events)
        player = game.players.first()
        initial_messages = player.messages.count()
        # Run many turns - no random event messages should appear
        with patch('dj4xol.turn.random.random', return_value=0.001):  # Would trigger if enabled
            GameTurn(game).generate_turns(10)
        # Only growth/environmental messages, no random event messages
        for msg in player.messages.all():
            self.assertNotIn('planetoid', msg.message.lower())
            self.assertNotIn('meteor', msg.message.lower())
            self.assertNotIn('population boom', msg.message.lower())
            self.assertNotIn('vanished', msg.message.lower())

    def test_random_events_can_trigger(self):
        """Random events should occur when enabled and roll succeeds."""
        game = default_game(stars=5)
        game.random_events = True
        game.save()
        player = game.players.first()
        homeworld = player.homeworld
        initial_messages = player.messages.count()
        # Force a random event to trigger
        with patch('dj4xol.turn.random.random', return_value=0.001):  # Below 0.01 threshold
            with patch('dj4xol.turn.random.choice', side_effect=lambda x: x[0]):
                GameTurn(game).generate_turn()
        # Should have at least one new message (could be growth + event)
        self.assertGreater(player.messages.count(), initial_messages)

    def test_population_boom_increases_colonists(self):
        """Population boom event should increase colonists."""
        game = default_game(stars=5)
        game.random_events = True
        game.save()
        player = game.players.first()
        homeworld = player.homeworld
        initial_pop = homeworld.colonists
        turn = GameTurn(game)
        turn._apply_population_boom(homeworld)
        homeworld.refresh_from_db()
        self.assertGreater(homeworld.colonists, initial_pop)
        # Check message was created (contains 'colonist' or 'births')
        msg = player.messages.order_by('-id').first()
        self.assertTrue(
            'colonist' in msg.message.lower() or 'births' in msg.message.lower(),
            f"Expected population message, got: {msg.message}"
        )

    def test_mining_discovery_increases_surface_resources(self):
        """Mining discovery should increase surface resources."""
        game = default_game(stars=5)
        game.random_events = True
        game.save()
        player = game.players.first()
        homeworld = player.homeworld
        homeworld.ironium_inventory = 0
        homeworld.boranium_inventory = 0
        homeworld.germanium_inventory = 0
        homeworld.save()
        total_before = homeworld.ironium_inventory + homeworld.boranium_inventory + homeworld.germanium_inventory
        turn = GameTurn(game)
        turn._apply_mining_discovery(homeworld)
        homeworld.refresh_from_db()
        total_after = homeworld.ironium_inventory + homeworld.boranium_inventory + homeworld.germanium_inventory
        self.assertGreater(total_after, total_before)

    def test_mining_accident_deaths_reduces_colonists(self):
        """Mining accident should reduce colonists."""
        game = default_game(stars=5)
        game.random_events = True
        game.save()
        player = game.players.first()
        homeworld = player.homeworld
        homeworld.colonists = 10000
        homeworld.save()
        turn = GameTurn(game)
        turn._apply_mining_accident_deaths(homeworld)
        homeworld.refresh_from_db()
        self.assertLess(homeworld.colonists, 10000)

    def test_colony_vanished_clears_colony(self):
        """Colony vanished event should remove all colonists and ownership."""
        game = default_game(stars=5)
        game.random_events = True
        game.save()
        player = game.players.first()
        # Use a non-homeworld star
        other_star = game.stars.exclude(pk=player.homeworld.pk).first()
        other_star.player = player
        other_star.colonists = 5000
        other_star.save()
        turn = GameTurn(game)
        turn._apply_colony_vanished(other_star)
        other_star.refresh_from_db()
        self.assertEqual(other_star.colonists, 0)
        self.assertIsNone(other_star.player)
        # Check message mentions vanished/dark/abandoned/lost
        msg = player.messages.order_by('-id').first()
        msg_lower = msg.message.lower()
        self.assertTrue(
            'vanish' in msg_lower or 'dark' in msg_lower or
            'abandoned' in msg_lower or 'contact' in msg_lower,
            f"Expected colony vanished message, got: {msg.message}"
        )

    def test_planetoid_event_moves_toward_ideal_when_positive(self):
        """Positive planetoid event should move environment toward player's ideal."""
        game = default_game(stars=5)
        game.random_events = True
        game.save()
        player = game.players.first()
        homeworld = player.homeworld
        # Set environment away from ideal
        homeworld.gravity = 0.5  # Player ideal is 1.0
        homeworld.save()
        turn = GameTurn(game)
        # Force positive intensity
        with patch('dj4xol.turn.random.uniform', return_value=0.4):
            with patch('dj4xol.turn.random.sample', return_value=['gravity']):
                with patch('dj4xol.turn.random.randint', return_value=1):
                    turn._apply_planetoid_event(homeworld)
        homeworld.refresh_from_db()
        # Should have moved toward ideal (1.0)
        self.assertGreater(homeworld.gravity, 0.5)

    def test_planetoid_event_moves_away_from_ideal_when_negative(self):
        """Negative planetoid event should move environment away from player's ideal."""
        game = default_game(stars=5)
        game.random_events = True
        game.save()
        player = game.players.first()
        homeworld = player.homeworld
        # Set environment at ideal
        homeworld.gravity = 1.0  # Player ideal is 1.0
        homeworld.save()
        turn = GameTurn(game)
        # Force negative intensity
        with patch('dj4xol.turn.random.uniform', side_effect=[-.4, 0.1]):
            with patch('dj4xol.turn.random.sample', return_value=['gravity']):
                with patch('dj4xol.turn.random.randint', return_value=1):
                    turn._apply_planetoid_event(homeworld)
        homeworld.refresh_from_db()
        # Should have moved away from ideal
        self.assertNotEqual(homeworld.gravity, 1.0)


class TestAnomalyInteractions(TestCase):
    @staticmethod
    def _find_location_far_from_stars(game):
        star_positions = list(game.stars.values_list('x', 'y'))
        max_x = max(2, int(game.map_size_x) - 1)
        max_y = max(2, int(game.map_size_y) - 1)
        min_x = 5 if max_x > 10 else 2
        min_y = 5 if max_y > 10 else 2
        max_scan_x = max_x - 3 if max_x > 10 else max_x
        max_scan_y = max_y - 3 if max_y > 10 else max_y
        for x in range(min_x, max_scan_x):
            for y in range(min_y, max_scan_y):
                if all((((sx - x) ** 2) + ((sy - y) ** 2)) > 1 for sx, sy in star_positions):
                    return x, y
        raise AssertionError('No star-safe coordinate found for comet test setup.')

    def test_low_danger_roll_1_has_no_effect(self):
        game = default_game()
        game.anomalies_enabled = True
        game.save(update_fields=['anomalies_enabled'])
        fleet = game.fleets.first()
        if fleet is None:
            player = game.players.first()
            fleet = Fleet.objects.create(
                game=game,
                player=player,
                name='Anomaly Probe',
                x=player.homeworld.x,
                y=player.homeworld.y,
            )
        Anomaly.objects.create(
            game=game,
            x=fleet.x,
            y=fleet.y,
            name='Silent Rift',
            anomaly_type=Anomaly.TYPE_RIFT,
        )
        fleet.integrity = 87
        fleet.ironium_inventory = 123
        fleet.save(update_fields=['integrity', 'ironium_inventory'])
        turn = GameTurn(game)
        with patch('dj4xol.turn.anomaly_danger_level', return_value=DANGER_LOW):
            with patch('dj4xol.turn.random.randint', return_value=1):
                turn.anomaly_interactions()
        fleet.refresh_from_db()
        self.assertEqual(fleet.integrity, 87)
        self.assertEqual(fleet.ironium_inventory, 123)
        self.assertFalse(GameMessage.objects.filter(
            game=game, player=fleet.player, category='RANDOM'
        ).exists())

    def test_anomaly_research_roll_sends_message(self):
        game = default_game()
        game.anomalies_enabled = True
        game.save(update_fields=['anomalies_enabled'])
        player = game.players.first()
        game.fleets.all().delete()
        fleet = Fleet.objects.create(
            game=game,
            player=player,
            name='Anomaly Probe',
            x=player.homeworld.x,
            y=player.homeworld.y,
        )
        Anomaly.objects.create(
            game=game,
            x=fleet.x,
            y=fleet.y,
            name='Research Nebula',
            anomaly_type=Anomaly.TYPE_NEBULA,
        )
        turn = GameTurn(game)
        with patch('dj4xol.turn.random.randint', return_value=6):
            with patch('dj4xol.turn.anomaly_danger_level', return_value=DANGER_MEDIUM):
                with patch('dj4xol.turn.random.random', side_effect=[0.9, 0.1, 0.0]):
                    turn.anomaly_interactions()
        self.assertTrue(GameMessage.objects.filter(
            game=game,
            player=fleet.player,
            category='RANDOM',
            message__icontains='bonus RP',
        ).exists())

    def test_anomaly_research_converts_secret_resources(self):
        game = default_game()
        game.anomalies_enabled = True
        game.save(update_fields=['anomalies_enabled'])
        player = game.players.first()
        game.fleets.all().delete()
        fleet = Fleet.objects.create(
            game=game,
            player=player,
            name='Anomaly Probe',
            x=player.homeworld.x,
            y=player.homeworld.y,
            advanced_scanner_range=1,
            resource_x_inventory=5,
            resource_y_inventory=4,
            resource_z_inventory=3,
        )
        Anomaly.objects.create(
            game=game,
            x=fleet.x,
            y=fleet.y,
            name='Research Nebula',
            anomaly_type=Anomaly.TYPE_NEBULA,
            stability=100,
        )
        row = ensure_player_research_rows(player)[0]
        captured = {}

        def _record_bonus(player_arg, category_id, bonus_rp):
            captured['category_id'] = category_id
            captured['bonus_rp'] = bonus_rp
            return {'old_level': 0, 'new_level': 0}

        with patch('dj4xol.turn.random.randint', return_value=6):
            with patch('dj4xol.turn.random.random', side_effect=[0.9, 0.1, 0.0]):
                with patch('dj4xol.turn.random.choice', return_value=row):
                    with patch('dj4xol.turn.anomaly_danger_level', return_value=DANGER_MEDIUM):
                        with patch('dj4xol.turn.apply_research_bonus_rp', side_effect=_record_bonus):
                            GameTurn(game).anomaly_interactions()

        fleet.refresh_from_db()
        self.assertEqual(fleet.resource_x_inventory, 0)
        self.assertEqual(fleet.resource_y_inventory, 0)
        self.assertEqual(fleet.resource_z_inventory, 0)
        self.assertEqual(captured.get('category_id'), row.category_id)
        self.assertEqual(captured.get('bonus_rp'), 142)

    def test_low_danger_anomaly_research_converts_secret_resources_with_reward_scaling(self):
        game = default_game()
        game.anomalies_enabled = True
        game.save(update_fields=['anomalies_enabled'])
        player = game.players.first()
        game.fleets.all().delete()
        fleet = Fleet.objects.create(
            game=game,
            player=player,
            name='Cautious Probe',
            x=21,
            y=21,
            advanced_scanner_range=1,
            resource_x_inventory=5,
            resource_y_inventory=4,
            resource_z_inventory=3,
        )
        anomaly = Anomaly.objects.create(
            game=game,
            x=21,
            y=21,
            name='Gentle Comet',
            anomaly_type=Anomaly.TYPE_COMET,
            stability=100,
        )
        row = ensure_player_research_rows(player)[0]
        captured = {}

        def _record_bonus(player_arg, category_id, bonus_rp):
            captured['category_id'] = category_id
            captured['bonus_rp'] = bonus_rp
            return {'old_level': 0, 'new_level': 0}

        with patch('dj4xol.turn.random.randint', return_value=6):
            with patch('dj4xol.turn.random.random', side_effect=[0.9, 0.1, 0.0]):
                with patch('dj4xol.turn.random.choice', return_value=row):
                    with patch('dj4xol.turn.anomaly_danger_level', return_value=DANGER_LOW):
                        with patch('dj4xol.turn.apply_research_bonus_rp', side_effect=_record_bonus):
                            GameTurn(game).anomaly_interactions()

        fleet.refresh_from_db()
        self.assertEqual(fleet.resource_x_inventory, 0)
        self.assertEqual(fleet.resource_y_inventory, 0)
        self.assertEqual(fleet.resource_z_inventory, 0)
        self.assertEqual(captured.get('category_id'), row.category_id)
        self.assertEqual(captured.get('bonus_rp'), 34)

    def test_anomaly_damage_and_destroy_send_messages(self):
        game = default_game()
        game.anomalies_enabled = True
        game.save(update_fields=['anomalies_enabled'])
        player = game.players.first()
        game.fleets.all().delete()
        fleet = Fleet.objects.create(
            game=game,
            player=player,
            name='Fragile Scout',
            x=player.homeworld.x,
            y=player.homeworld.y,
            integrity=100,
        )
        Anomaly.objects.create(
            game=game,
            x=fleet.x,
            y=fleet.y,
            name='Deep Rift',
            anomaly_type=Anomaly.TYPE_RIFT,
        )
        turn = GameTurn(game)
        with patch('dj4xol.turn.anomaly_danger_level', return_value=DANGER_HIGH):
            with patch('dj4xol.turn.random.randint', side_effect=[2, 12]):
                turn.anomaly_interactions()
        self.assertTrue(GameMessage.objects.filter(
            game=game,
            player=player,
            category='RANDOM',
            message__icontains='integrity damage',
        ).exists())
        damage_msg = GameMessage.objects.filter(
            game=game,
            player=player,
            category='RANDOM',
            message__icontains='integrity damage',
        ).latest('id')
        self.assertIn(fleet.short_id, damage_msg.message)
        with patch('dj4xol.turn.anomaly_danger_level', return_value=DANGER_HIGH):
            with patch('dj4xol.turn.random.randint', return_value=4):
                turn.anomaly_interactions()
        self.assertFalse(Fleet.objects.filter(id=fleet.id).exists())
        self.assertTrue(GameMessage.objects.filter(
            game=game,
            player=player,
            category='RANDOM',
            message__icontains='lost whilst exploring',
        ).exists())

    def test_anomaly_reports_are_persisted(self):
        game = default_game()
        game.anomalies_enabled = True
        game.save(update_fields=['anomalies_enabled'])
        player = game.players.first()
        fleet = game.fleets.first()
        if fleet is None:
            fleet = Fleet.objects.create(
                game=game,
                player=player,
                name='Surveyor',
                x=player.homeworld.x,
                y=player.homeworld.y,
            )
        anomaly = Anomaly.objects.create(
            game=game,
            x=fleet.x,
            y=fleet.y,
            name='Comet Trace',
            anomaly_type=Anomaly.TYPE_COMET,
        )
        turn = GameTurn(game)
        turn.generate_reports()
        from ..models import Report
        report = Report.objects.filter(
            game=game,
            player=player,
            target_type='anomaly',
            target_id=anomaly.id,
        ).first()
        self.assertIsNotNone(report)
        data = report.get_report_data()
        self.assertEqual(data.get('anomaly_type'), Anomaly.TYPE_COMET)
        self.assertEqual(data.get('name'), 'Comet Trace')
        self.assertIn('heading', data)
        self.assertIn('stability', data)
        self.assertEqual(data.get('stability'), anomaly.stability)

    def test_spawn_anomaly_respects_star_based_cap(self):
        game = default_game(stars=10)
        game.anomalies_enabled = True
        game.save(update_fields=['anomalies_enabled'])
        player = game.players.first()
        max_allowed = 2
        for idx in range(max_allowed):
            Anomaly.objects.create(
                game=game,
                x=player.homeworld.x + idx + 1,
                y=player.homeworld.y + idx + 1,
                name='Cap %s' % idx,
                anomaly_type=Anomaly.TYPE_RIFT,
            )
        before = Anomaly.objects.filter(game=game).count()
        turn = GameTurn(game)
        with patch('dj4xol.turn.random.random', side_effect=[1.0, 1.0, 0.0]):
            turn.spawn_anomalies()
        after = Anomaly.objects.filter(game=game).count()
        self.assertEqual(before, after)

    def test_special_salvage_can_spawn_even_when_anomalies_are_at_cap(self):
        game = default_game(stars=10)
        game.anomalies_enabled = True
        game.save(update_fields=['anomalies_enabled'])
        player = game.players.first()
        for idx in range(2):
            Anomaly.objects.create(
                game=game,
                x=player.homeworld.x + idx + 1,
                y=player.homeworld.y + idx + 1,
                name='Cap %s' % idx,
                anomaly_type=Anomaly.TYPE_RIFT,
            )
        turn = GameTurn(game)
        with patch.object(turn, '_random_empty_spawn_point', return_value=(50, 50)):
            with patch('dj4xol.turn.random.random', return_value=0.0):
                turn.spawn_anomalies()
        self.assertEqual(Anomaly.objects.filter(game=game).count(), 2)
        self.assertTrue(Salvage.objects.filter(
            game=game, salvage_type=Salvage.TYPE_ANCIENT_DEBRIS
        ).exists())

    def test_spawn_anomaly_uses_empty_map_boost(self):
        game = default_game(stars=10)
        game.anomalies_enabled = True
        game.save(update_fields=['anomalies_enabled'])
        turn = GameTurn(game)
        with patch.object(turn, '_random_empty_spawn_point', return_value=(50, 50)):
            with patch('dj4xol.turn.random.random', side_effect=[1.0, 1.0, 0.44, 0.1]):
                with patch('dj4xol.turn.random.choice', return_value=Anomaly.TYPE_RIFT):
                    turn.spawn_anomalies()
        self.assertTrue(Anomaly.objects.filter(
            game=game, anomaly_type=Anomaly.TYPE_RIFT, x=50, y=50
        ).exists())

    def test_spawn_anomaly_chance_scales_down_with_cap_fill(self):
        game = default_game(stars=10)
        game.anomalies_enabled = True
        game.save(update_fields=['anomalies_enabled'])
        Anomaly.objects.create(
            game=game,
            x=40,
            y=40,
            name='Existing Rift',
            anomaly_type=Anomaly.TYPE_RIFT,
        )
        turn = GameTurn(game)
        with patch.object(turn, '_random_empty_spawn_point', return_value=(50, 50)):
            with patch('dj4xol.turn.random.random', side_effect=[1.0, 1.0, 0.3]):
                with patch('dj4xol.turn.random.choice', return_value=Anomaly.TYPE_RIFT):
                    turn.spawn_anomalies()
        self.assertEqual(Anomaly.objects.filter(game=game).count(), 1)

    def test_spawned_wormhole_names_are_serial(self):
        game = default_game(stars=10, fleets=0)
        game.anomalies_enabled = True
        game.save(update_fields=['anomalies_enabled'])
        game.fleets.all().delete()
        for idx, star in enumerate(game.stars.order_by('id'), start=1):
            star.x = idx
            star.y = 1
            star.save(update_fields=['x', 'y'])
        turn = GameTurn(game)
        randint_values = [50, 50, 60, 60]
        with patch('dj4xol.turn.ASTEROID_FIELD_SPAWN_SHARE', 0.0), \
             patch('dj4xol.turn.ANCIENT_DEBRIS_SPAWN_SHARE', 0.0):
            with patch('dj4xol.turn.random.random', return_value=0.0):
                with patch('dj4xol.turn.random.choice', return_value=Anomaly.TYPE_WORMHOLE):
                    with patch('dj4xol.turn.random.randint', side_effect=lambda *_: (
                        randint_values.pop(0) if randint_values else 7
                    )):
                        turn.spawn_anomalies()
        wormholes = list(Anomaly.objects.filter(
            game=game,
            anomaly_type=Anomaly.TYPE_WORMHOLE,
        ).order_by('id'))
        self.assertEqual(len(wormholes), 2)
        self.assertEqual(wormholes[0].name, 'Wormhole 1')
        self.assertEqual(wormholes[1].name, 'Wormhole 2')

    def test_comet_drift_moves_stochastically_by_heading(self):
        game = default_game()
        game.anomalies_enabled = True
        game.save(update_fields=['anomalies_enabled'])
        game.stars.all().delete()
        x, y = (50, 50)
        comet = Anomaly.objects.create(
            game=game,
            x=x,
            y=y,
            name='Drifter',
            anomaly_type=Anomaly.TYPE_COMET,
            heading=0.0,
        )
        turn = GameTurn(game)
        for _ in range(20):
            turn.move_comets()
            game.year += 1
            game.save(update_fields=['year'])
        comet.refresh_from_db()
        self.assertEqual(comet.x, x)
        self.assertLess(comet.y, y)
        self.assertAlmostEqual(float(comet.heading), 0.0, places=3)

    def test_comet_drift_is_destroyed_on_map_edge_exit(self):
        game = default_game()
        game.anomalies_enabled = True
        game.save(update_fields=['anomalies_enabled'])
        game.stars.all().delete()
        comet = Anomaly.objects.create(
            game=game,
            x=1,
            y=40,
            name='Wall Skimmer',
            anomaly_type=Anomaly.TYPE_COMET,
            heading=270.0,
        )
        turn = GameTurn(game)
        for _ in range(20):
            turn.move_comets()
            game.year += 1
            game.save(update_fields=['year'])
            if not Anomaly.objects.filter(id=comet.id).exists():
                break
        self.assertFalse(Anomaly.objects.filter(id=comet.id).exists())

    def test_comet_bends_towards_star_at_1ly_by_up_to_60_degrees(self):
        game = default_game()
        game.anomalies_enabled = True
        game.save(update_fields=['anomalies_enabled'])
        game.stars.all().delete()
        x, y = (50, 50)
        Star.objects.create(
            game=game,
            name='Bend Anchor',
            x=x + 1,
            y=y,
        )
        comet = Anomaly.objects.create(
            game=game,
            x=x,
            y=y,
            name='Bender',
            anomaly_type=Anomaly.TYPE_COMET,
            heading=0.0,
        )
        turn = GameTurn(game)
        turn.move_comets()
        comet.refresh_from_db()
        self.assertAlmostEqual(float(comet.heading), 60.0, places=3)

    def test_comet_on_star_allows_large_course_change(self):
        game = default_game()
        game.anomalies_enabled = True
        game.save(update_fields=['anomalies_enabled'])
        game.stars.all().delete()
        x, y = (50, 50)
        Star.objects.create(
            game=game,
            name='Direct Overlap',
            x=x,
            y=y,
        )
        comet = Anomaly.objects.create(
            game=game,
            x=x,
            y=y,
            name='Close Pass',
            anomaly_type=Anomaly.TYPE_COMET,
            heading=10.0,
        )
        turn = GameTurn(game)
        with patch('dj4xol.turn.random.uniform', return_value=179.0):
            turn.move_comets()
        comet.refresh_from_db()
        self.assertAlmostEqual(float(comet.heading), 189.0, places=3)

    def test_comet_does_not_bend_for_star_behind(self):
        game = default_game()
        game.anomalies_enabled = True
        game.save(update_fields=['anomalies_enabled'])
        game.stars.all().delete()
        x, y = (50, 50)
        Star.objects.create(
            game=game,
            name='Rear Star',
            x=x,
            y=y + 1,
        )
        comet = Anomaly.objects.create(
            game=game,
            x=x,
            y=y,
            name='Forward Drifter',
            anomaly_type=Anomaly.TYPE_COMET,
            heading=0.0,
        )
        turn = GameTurn(game)
        turn.move_comets()
        comet.refresh_from_db()
        self.assertAlmostEqual(float(comet.heading), 0.0, places=3)

    def test_anomaly_decay_applies_below_90_stability(self):
        game = default_game()
        game.anomalies_enabled = True
        game.save(update_fields=['anomalies_enabled'])
        anomaly = Anomaly.objects.create(
            game=game,
            x=30,
            y=30,
            name='Unstable',
            anomaly_type=Anomaly.TYPE_RIFT,
            stability=80,
        )
        turn = GameTurn(game)
        with patch('dj4xol.turn.random.random', side_effect=[0.0, 1.0]):
            turn.decay_anomalies()
        anomaly.refresh_from_db()
        self.assertEqual(anomaly.stability, 79)

    def test_anomaly_above_90_stability_remains_stable(self):
        game = default_game()
        game.anomalies_enabled = True
        game.save(update_fields=['anomalies_enabled'])
        anomaly = Anomaly.objects.create(
            game=game,
            x=31,
            y=31,
            name='Stable',
            anomaly_type=Anomaly.TYPE_RIFT,
            stability=95,
        )
        turn = GameTurn(game)
        with patch('dj4xol.turn.random.random', side_effect=[0.0, 0.0]):
            turn.decay_anomalies()
        anomaly.refresh_from_db()
        self.assertEqual(anomaly.stability, 95)

    def test_anomaly_at_29_stability_can_collapse(self):
        game = default_game()
        game.anomalies_enabled = True
        game.save(update_fields=['anomalies_enabled'])
        anomaly = Anomaly.objects.create(
            game=game,
            x=31,
            y=31,
            name='Collapsing',
            anomaly_type=Anomaly.TYPE_RIFT,
            stability=29,
        )
        turn = GameTurn(game)
        with patch('dj4xol.turn.random.random', side_effect=[1.0, 0.0]):
            turn.decay_anomalies()
        self.assertFalse(Anomaly.objects.filter(id=anomaly.id).exists())

    def test_anomaly_at_30_stability_does_not_collapse(self):
        game = default_game()
        game.anomalies_enabled = True
        game.save(update_fields=['anomalies_enabled'])
        anomaly = Anomaly.objects.create(
            game=game,
            x=32,
            y=32,
            name='Threshold',
            anomaly_type=Anomaly.TYPE_RIFT,
            stability=30,
        )
        turn = GameTurn(game)
        with patch('dj4xol.turn.random.random', side_effect=[1.0, 0.0]):
            turn.decay_anomalies()
        self.assertTrue(Anomaly.objects.filter(id=anomaly.id).exists())

    def test_anomaly_collapse_retargets_orders_and_warns_once_per_player(self):
        game = default_game(stars=3, fleets=0)
        game.anomalies_enabled = True
        game.save(update_fields=['anomalies_enabled'])
        player = game.players.first()
        home = player.homeworld
        anomaly = Anomaly.objects.create(
            game=game,
            x=home.x + 3,
            y=home.y + 3,
            name='Survey Rift',
            anomaly_type=Anomaly.TYPE_RIFT,
            stability=29,
        )
        fleet_a = Fleet.objects.create(
            game=game, player=player, name='Scout A', x=home.x, y=home.y
        )
        fleet_b = Fleet.objects.create(
            game=game, player=player, name='Scout B', x=home.x, y=home.y
        )
        order_a = FleetOrders.objects.create(
            game=game,
            fleet=fleet_a,
            order_type='MOVE',
            target_kind='OBJECT',
            target_short_id=anomaly.short_id,
        )
        order_b = FleetOrders.objects.create(
            game=game,
            fleet=fleet_b,
            order_type='MOVE',
            target_kind='OBJECT',
            target_short_id=anomaly.short_id,
        )
        with patch('dj4xol.turn.random.random', side_effect=[1.0, 0.0]), \
             patch(
                 'dj4xol.messages.AnomalyTargetLostMessageFactory.format_message',
                 return_value='Scout warning at Empty Space (0, 0).'
             ):
            GameTurn(game).decay_anomalies()

        order_a.refresh_from_db()
        order_b.refresh_from_db()
        self.assertEqual(order_a.target_kind, 'SPACE')
        self.assertEqual(order_b.target_kind, 'SPACE')
        self.assertIsNone(order_a.target_short_id)
        self.assertIsNone(order_b.target_short_id)
        self.assertEqual((order_a.x, order_a.y), (anomaly.x, anomaly.y))
        self.assertEqual((order_b.x, order_b.y), (anomaly.x, anomaly.y))
        messages = list(player.messages.filter(message__contains='Survey Rift'))
        self.assertEqual(len(messages), 0)
        warning_messages = list(player.messages.filter(message__contains='Scout warning'))
        self.assertEqual(len(warning_messages), 1)

    def test_wormhole_collapse_warns_with_enter_wording(self):
        game = default_game(stars=3, fleets=0)
        game.anomalies_enabled = True
        game.save(update_fields=['anomalies_enabled'])
        player = game.players.first()
        home = player.homeworld
        a = Anomaly.objects.create(
            game=game,
            x=home.x + 4,
            y=home.y + 4,
            name='Wormhole 1',
            anomaly_type=Anomaly.TYPE_WORMHOLE,
            stability=10,
        )
        b = Anomaly.objects.create(
            game=game,
            x=home.x + 8,
            y=home.y + 8,
            name='Wormhole 2',
            anomaly_type=Anomaly.TYPE_WORMHOLE,
            stability=100,
            wormhole_pair=a,
        )
        a.wormhole_pair = b
        a.save(update_fields=['wormhole_pair'])
        fleet = Fleet.objects.create(
            game=game, player=player, name='Gate Runner', x=home.x, y=home.y
        )
        order = FleetOrders.objects.create(
            game=game,
            fleet=fleet,
            order_type='MOVE',
            target_kind='OBJECT',
            target_short_id=a.short_id,
        )
        with patch('dj4xol.turn.random.random', side_effect=[0.0, 0.0, 1.0, 1.0, 1.0, 1.0]), \
             patch('dj4xol.turn.random.randint', return_value=25), \
             patch('dj4xol.messages.random.choice', return_value=('collapsed', 'into')):
            GameTurn(game).decay_anomalies()

        order.refresh_from_db()
        self.assertEqual(order.target_kind, 'SPACE')
        msg = player.messages.filter(message__contains='Wormhole 1').latest('id')
        self.assertIn('orders to enter Wormhole 1', msg.message)
        self.assertIn('collapsed into', msg.message)
        self.assertNotIn('sel=%s' % a.short_id, msg.message)

    def test_low_stability_increases_anomaly_rewards(self):
        game = default_game()
        game.anomalies_enabled = True
        game.save(update_fields=['anomalies_enabled'])
        player = game.players.first()
        game.fleets.all().delete()
        fleet = Fleet.objects.create(
            game=game,
            player=player,
            name='Reward Probe',
            x=20,
            y=20,
            advanced_scanner_range=1,
        )
        anomaly = Anomaly.objects.create(
            game=game,
            x=20,
            y=20,
            name='Reward Rift',
            anomaly_type=Anomaly.TYPE_RIFT,
            stability=0,
        )
        turn = GameTurn(game)
        with patch('dj4xol.turn.anomaly_danger_level', return_value=DANGER_HIGH):
            with patch('dj4xol.turn.random.random', side_effect=[0.9, 0.1, 0.0]):
                turn._apply_anomaly_research_boon(fleet, anomaly)
        self.assertTrue(GameMessage.objects.filter(
            game=game,
            player=player,
            category='RANDOM',
            message__icontains='240 bonus RP',
        ).exists())

    def test_cargo_loss_roll_without_cargo_converts_to_integrity_damage(self):
        game = default_game()
        game.anomalies_enabled = True
        game.save(update_fields=['anomalies_enabled'])
        player = game.players.first()
        game.fleets.all().delete()
        fleet = Fleet.objects.create(
            game=game,
            player=player,
            name='Empty Freighter',
            x=25,
            y=25,
            integrity=100,
            ironium_inventory=0,
            boranium_inventory=0,
            germanium_inventory=0,
            colonists=0,
        )
        anomaly = Anomaly.objects.create(
            game=game,
            x=25,
            y=25,
            name='Cargo Shear',
            anomaly_type=Anomaly.TYPE_RIFT,
            stability=100,
        )
        turn = GameTurn(game)
        with patch('dj4xol.turn.anomaly_danger_level', return_value=DANGER_MEDIUM):
            with patch('dj4xol.turn.random.uniform', return_value=0.3):
                with patch('dj4xol.turn.random.randint', return_value=12):
                    turn._apply_anomaly_cargo_loss(fleet, anomaly)
        fleet.refresh_from_db()
        self.assertEqual(fleet.integrity, 92)
        self.assertTrue(GameMessage.objects.filter(
            game=game,
            player=player,
            category='RANDOM',
            message__icontains='integrity damage',
        ).exists())
        msg = GameMessage.objects.filter(
            game=game,
            player=player,
            category='RANDOM',
            message__icontains='integrity damage',
        ).latest('id')
        self.assertIn(fleet.short_id, msg.message)

    def test_low_danger_anomaly_replaces_direct_destruction_with_integrity_damage(self):
        game = default_game()
        game.anomalies_enabled = True
        game.save(update_fields=['anomalies_enabled'])
        player = game.players.first()
        game.fleets.all().delete()
        fleet = Fleet.objects.create(
            game=game,
            player=player,
            name='Comet Chaser',
            x=26,
            y=26,
            integrity=100,
        )
        Anomaly.objects.create(
            game=game,
            x=26,
            y=26,
            name='Trail Comet',
            anomaly_type=Anomaly.TYPE_COMET,
            stability=100,
        )
        with patch('dj4xol.turn.random.randint', side_effect=[4, 10]):
            GameTurn(game).anomaly_interactions()
        fleet.refresh_from_db()
        self.assertEqual(fleet.integrity, 98)
        self.assertTrue(Fleet.objects.filter(id=fleet.id).exists())

    def test_black_hole_high_danger_destroy_roll_destroys_fleet(self):
        game = default_game()
        game.anomalies_enabled = True
        game.save(update_fields=['anomalies_enabled'])
        player = game.players.first()
        game.fleets.all().delete()
        fleet = Fleet.objects.create(
            game=game,
            player=player,
            name='Doomed Scout',
            x=27,
            y=27,
            integrity=100,
        )
        Anomaly.objects.create(
            game=game,
            x=27,
            y=27,
            name='Abyss',
            anomaly_type=Anomaly.TYPE_BLACK_HOLE,
            stability=100,
        )
        turn = GameTurn(game)
        with patch('dj4xol.turn.anomaly_danger_level', return_value=DANGER_HIGH):
            with patch('dj4xol.turn.random.randint', return_value=4):
                turn.anomaly_interactions()
        self.assertFalse(Fleet.objects.filter(id=fleet.id).exists())

    def test_black_hole_high_danger_damage_roll_can_heavily_damage_fleet(self):
        game = default_game()
        game.anomalies_enabled = True
        game.save(update_fields=['anomalies_enabled'])
        player = game.players.first()
        game.fleets.all().delete()
        fleet = Fleet.objects.create(
            game=game,
            player=player,
            name='Heavy Hit',
            x=28,
            y=28,
            integrity=100,
        )
        Anomaly.objects.create(
            game=game,
            x=28,
            y=28,
            name='Maw',
            anomaly_type=Anomaly.TYPE_BLACK_HOLE,
            stability=100,
        )
        turn = GameTurn(game)
        with patch('dj4xol.turn.anomaly_danger_level', return_value=DANGER_HIGH):
            with patch('dj4xol.turn.random.randint', side_effect=[2, 30]):
                turn.anomaly_interactions()
        fleet.refresh_from_db()
        self.assertEqual(fleet.integrity, 65)

    def test_black_hole_reward_uses_generic_danger_scaling(self):
        game = default_game()
        game.anomalies_enabled = True
        game.save(update_fields=['anomalies_enabled'])
        player = game.players.first()
        game.fleets.all().delete()
        fleet = Fleet.objects.create(
            game=game,
            player=player,
            name='Brave Probe',
            x=29,
            y=29,
            integrity=100,
            advanced_scanner_range=1,
        )
        Anomaly.objects.create(
            game=game,
            x=29,
            y=29,
            name='Scholar\'s End',
            anomaly_type=Anomaly.TYPE_BLACK_HOLE,
            stability=100,
        )
        turn = GameTurn(game)
        captured = {}

        def _record_bonus(player_arg, category_id, bonus_rp):
            captured['category_id'] = category_id
            captured['bonus_rp'] = bonus_rp
            return {'old_level': 0, 'new_level': 0}

        with patch('dj4xol.turn.anomaly_danger_level', return_value=DANGER_HIGH):
            with patch('dj4xol.turn.random.randint', return_value=5):
                with patch('dj4xol.turn.random.random', side_effect=[0.9, 0.1, 0.0]):
                    with patch('dj4xol.turn.apply_research_bonus_rp', side_effect=_record_bonus):
                        turn.anomaly_interactions()
        self.assertIsNotNone(captured.get('category_id'))
        self.assertEqual(captured.get('bonus_rp'), 177)

    def test_anomaly_breakthrough_can_complete_category(self):
        game = default_game()
        game.anomalies_enabled = True
        game.save(update_fields=['anomalies_enabled'])
        player = game.players.first()
        game.fleets.all().delete()
        fleet = Fleet.objects.create(
            game=game,
            player=player,
            name='Insight Probe',
            x=36,
            y=36,
            advanced_scanner_range=1,
        )
        anomaly = Anomaly.objects.create(
            game=game,
            x=36,
            y=36,
            name='Idea Storm',
            anomaly_type=Anomaly.TYPE_RIFT,
            stability=0,
        )
        row = ensure_player_research_rows(player)[0]
        old_level = int(row.current_level or 0)
        max_level = int(get_global_research_max_level() or 0)
        with patch(
            'dj4xol.turn.random.choice',
            side_effect=lambda seq: row if seq and hasattr(seq[0], 'category_id') else seq[0]
        ):
            GameTurn(game)._apply_anomaly_breakthrough(player, anomaly)
        row.refresh_from_db()
        self.assertGreater(int(row.current_level or 0), old_level)
        self.assertEqual(int(row.current_level or 0), max_level)
        self.assertTrue(GameMessage.objects.filter(
            game=game,
            player=player,
            category='RANDOM',
            message__icontains='Anomaly breakthrough',
        ).exists())

    def test_black_hole_high_danger_destroy_message_uses_generic_anomaly_wording(self):
        game = default_game()
        game.anomalies_enabled = True
        game.save(update_fields=['anomalies_enabled'])
        player = game.players.first()
        game.fleets.all().delete()
        fleet = Fleet.objects.create(
            game=game,
            player=player,
            name='Critical Scout',
            x=35,
            y=35,
            integrity=100,
        )
        anomaly = Anomaly.objects.create(
            game=game,
            x=35,
            y=35,
            name='Singularity',
            anomaly_type=Anomaly.TYPE_BLACK_HOLE,
            stability=100,
        )
        turn = GameTurn(game)
        with patch('dj4xol.turn.anomaly_danger_level', return_value=DANGER_HIGH):
            with patch('dj4xol.turn.random.randint', return_value=4):
                turn.anomaly_interactions()

        self.assertFalse(Fleet.objects.filter(id=fleet.id).exists())
        self.assertFalse(Salvage.objects.filter(game=game, x=35, y=35).exists())
        msgs = list(GameMessage.objects.filter(game=game, player=player, category='RANDOM'))
        self.assertEqual(len(msgs), 1)
        self.assertIn('lost whilst exploring', msgs[0].message.lower())
        self.assertIn('sel=%s' % anomaly.short_id, msgs[0].message)
        self.assertNotIn('(35, 35)', msgs[0].message)

    def test_format_location_prefers_anomaly_link_over_star(self):
        from ..messages import format_location

        game = default_game()
        player = game.players.first()
        star = game.stars.first()
        anomaly = Anomaly.objects.create(
            game=game,
            x=star.x,
            y=star.y,
            name='Overlay Rift',
            anomaly_type=Anomaly.TYPE_RIFT,
        )
        location = format_location(x=star.x, y=star.y, link=True, game=game)
        self.assertIn('sel=%s' % anomaly.short_id, location)
        self.assertNotIn('sel=%s' % star.short_id, location)

    def test_wormhole_interaction_transports_and_reports_both_ends(self):
        from ..models import Report

        game = default_game()
        game.anomalies_enabled = True
        game.save(update_fields=['anomalies_enabled'])
        game.stars.all().delete()
        player = game.players.first()
        game.fleets.all().delete()
        fleet = Fleet.objects.create(
            game=game,
            player=player,
            name='Transit Probe',
            x=10,
            y=10,
            integrity=100,
        )
        a = Anomaly.objects.create(
            game=game,
            x=10,
            y=10,
            name='WH-1',
            anomaly_type=Anomaly.TYPE_WORMHOLE,
            stability=100,
        )
        b = Anomaly.objects.create(
            game=game,
            x=40,
            y=40,
            name='WH-1',
            anomaly_type=Anomaly.TYPE_WORMHOLE,
            stability=100,
            wormhole_pair=a,
        )
        a.wormhole_pair = b
        a.save(update_fields=['wormhole_pair'])

        with patch('dj4xol.turn.random.random', return_value=1.0), \
             patch('dj4xol.turn.random.shuffle', lambda vals: None):
            GameTurn(game).anomaly_interactions()

        fleet.refresh_from_db()
        self.assertNotEqual((fleet.x, fleet.y), (10, 10))
        self.assertNotEqual((fleet.x, fleet.y), (40, 40))
        dist = (((fleet.x - b.x) ** 2) + ((fleet.y - b.y) ** 2)) ** 0.5
        self.assertTrue(4.0 <= dist <= 8.0)
        self.assertTrue(Report.objects.filter(
            game=game, player=player, target_type='anomaly', target_id=a.id
        ).exists())
        self.assertTrue(Report.objects.filter(
            game=game, player=player, target_type='anomaly', target_id=b.id
        ).exists())
        self.assertFalse(GameMessage.objects.filter(
            game=game,
            player=player,
            category='RANDOM',
            message__icontains='bonus RP',
        ).exists())

    def test_wormhole_first_traversal_message_is_non_priority_and_not_repeated(self):
        game = default_game()
        game.anomalies_enabled = True
        game.save(update_fields=['anomalies_enabled'])
        game.stars.all().delete()
        player = game.players.first()
        game.fleets.all().delete()
        fleet = Fleet.objects.create(
            game=game,
            player=player,
            name='Transit Probe',
            x=10,
            y=10,
            integrity=100,
        )
        a = Anomaly.objects.create(
            game=game,
            x=10,
            y=10,
            name='Wormhole 1',
            anomaly_type=Anomaly.TYPE_WORMHOLE,
            stability=100,
        )
        b = Anomaly.objects.create(
            game=game,
            x=40,
            y=40,
            name='Wormhole 2',
            anomaly_type=Anomaly.TYPE_WORMHOLE,
            stability=100,
            wormhole_pair=a,
        )
        a.wormhole_pair = b
        a.save(update_fields=['wormhole_pair'])

        turn = GameTurn(game)
        with patch('dj4xol.turn.random.random', return_value=1.0):
            turn._apply_wormhole_interaction(fleet, a)

        msg = player.messages.latest('id')
        self.assertFalse(msg.priority)
        self.assertIn('emerged from', msg.message)
        self.assertIn(fleet.short_id, msg.message)
        self.assertIn(b.short_id, msg.message)
        self.assertIn('locate=1', msg.message)

        first_message_count = player.messages.count()
        fleet.x = a.x
        fleet.y = a.y
        fleet.save(update_fields=['x', 'y'])

        with patch('dj4xol.turn.random.random', return_value=1.0):
            turn._apply_wormhole_interaction(fleet, a)

        self.assertEqual(player.messages.count(), first_message_count)

    def test_wormhole_first_traversal_message_still_fires_if_reports_exist(self):
        game = default_game()
        game.anomalies_enabled = True
        game.save(update_fields=['anomalies_enabled'])
        game.stars.all().delete()
        player = game.players.first()
        game.fleets.all().delete()
        fleet = Fleet.objects.create(
            game=game,
            player=player,
            name='Known Hole Probe',
            x=10,
            y=10,
            integrity=100,
        )
        a = Anomaly.objects.create(
            game=game,
            x=10,
            y=10,
            name='Known Wormhole A',
            anomaly_type=Anomaly.TYPE_WORMHOLE,
            stability=95,
        )
        b = Anomaly.objects.create(
            game=game,
            x=40,
            y=40,
            name='Known Wormhole B',
            anomaly_type=Anomaly.TYPE_WORMHOLE,
            stability=95,
            wormhole_pair=a,
        )
        a.wormhole_pair = b
        a.save(update_fields=['wormhole_pair'])

        turn = GameTurn(game)
        turn._create_or_update_report(player, 'anomaly', a, game.year)
        turn._create_or_update_report(player, 'anomaly', b, game.year)

        self.assertEqual(player.messages.count(), 0)

        with patch('dj4xol.turn.random.random', return_value=1.0):
            turn._apply_wormhole_interaction(fleet, a)

        msg = player.messages.latest('id')
        self.assertFalse(msg.priority)
        self.assertIn('traversed wormhole', msg.message)
        self.assertIn('emerged from', msg.message)

        a_report = Report.objects.get(
            game=game, player=player, target_type='anomaly', target_id=a.id
        )
        b_report = Report.objects.get(
            game=game, player=player, target_type='anomaly', target_id=b.id
        )
        self.assertTrue(a_report.get_report_data().get('wormhole_traversed'))
        self.assertTrue(b_report.get_report_data().get('wormhole_traversed'))

    def test_wormhole_reverse_traversal_does_not_repeat_clean_message(self):
        game = default_game()
        game.anomalies_enabled = True
        game.save(update_fields=['anomalies_enabled'])
        game.stars.all().delete()
        player = game.players.first()
        game.fleets.all().delete()
        fleet = Fleet.objects.create(
            game=game,
            player=player,
            name='Round Trip Probe',
            x=10,
            y=10,
            integrity=100,
        )
        a = Anomaly.objects.create(
            game=game,
            x=10,
            y=10,
            name='Round Trip A',
            anomaly_type=Anomaly.TYPE_WORMHOLE,
            stability=95,
        )
        b = Anomaly.objects.create(
            game=game,
            x=40,
            y=40,
            name='Round Trip B',
            anomaly_type=Anomaly.TYPE_WORMHOLE,
            stability=95,
            wormhole_pair=a,
        )
        a.wormhole_pair = b
        a.save(update_fields=['wormhole_pair'])

        turn = GameTurn(game)
        with patch('dj4xol.turn.random.random', return_value=1.0):
            turn._apply_wormhole_interaction(fleet, a)

        first_message_count = player.messages.count()
        fleet.x = b.x
        fleet.y = b.y
        fleet.save(update_fields=['x', 'y'])

        with patch('dj4xol.turn.random.random', return_value=1.0):
            turn._apply_wormhole_interaction(fleet, b)

        self.assertEqual(player.messages.count(), first_message_count)

    def test_wormhole_high_instability_can_apply_damage(self):
        game = default_game()
        game.anomalies_enabled = True
        game.save(update_fields=['anomalies_enabled'])
        game.stars.all().delete()
        player = game.players.first()
        game.fleets.all().delete()
        fleet = Fleet.objects.create(
            game=game,
            player=player,
            name='Bruised Probe',
            x=11,
            y=11,
            integrity=100,
        )
        a = Anomaly.objects.create(
            game=game,
            x=11,
            y=11,
            name='WH-2',
            anomaly_type=Anomaly.TYPE_WORMHOLE,
            stability=0,
        )
        b = Anomaly.objects.create(
            game=game,
            x=30,
            y=30,
            name='WH-2',
            anomaly_type=Anomaly.TYPE_WORMHOLE,
            stability=0,
            wormhole_pair=a,
        )
        a.wormhole_pair = b
        a.save(update_fields=['wormhole_pair'])

        with patch('dj4xol.turn.anomaly_danger_level', return_value=DANGER_MEDIUM), \
             patch('dj4xol.turn.random.random', side_effect=[1.0, 0.0]), \
             patch('dj4xol.turn.random.randint', return_value=25), \
             patch('dj4xol.turn.random.shuffle', lambda vals: None):
            GameTurn(game).anomaly_interactions()
        fleet.refresh_from_db()
        self.assertEqual(fleet.integrity, 75)
        msg = player.messages.latest('id')
        self.assertFalse(msg.priority)
        self.assertIn('25% integrity damage', msg.message)
        self.assertIn('emerged from', msg.message)

    def test_asteroid_field_damage_sends_non_priority_message(self):
        game = default_game()
        player = game.players.first()
        game.fleets.all().delete()
        fleet = Fleet.objects.create(
            game=game,
            player=player,
            name='Salvage Scout',
            x=41,
            y=41,
            integrity=100,
        )
        salvage = Salvage.objects.create(
            game=game,
            x=fleet.x,
            y=fleet.y,
            salvage_type=Salvage.TYPE_ASTEROID_FIELD,
        )

        with patch('dj4xol.turn.salvage_danger_level', return_value=DANGER_LOW):
            with patch('dj4xol.turn.roll_chance', return_value=True):
                with patch('dj4xol.turn.random.randint', return_value=6):
                    GameTurn(game).salvage_interactions()

        fleet.refresh_from_db()
        self.assertEqual(fleet.integrity, 98)
        msg = player.messages.latest('id')
        self.assertFalse(msg.priority)
        self.assertIn('Asteroid Field', msg.message)
        self.assertIn('2% integrity damage', msg.message)
        self.assertIn(fleet.short_id, msg.message)

    def test_low_danger_plain_salvage_uses_light_damage_path(self):
        game = default_game()
        player = game.players.first()
        game.fleets.all().delete()
        fleet = Fleet.objects.create(
            game=game,
            player=player,
            name='Wreck Diver',
            x=42,
            y=42,
            integrity=100,
        )
        Salvage.objects.create(
            game=game,
            x=fleet.x,
            y=fleet.y,
            salvage_type=Salvage.TYPE_SALVAGE,
            danger_level=DANGER_LOW,
        )

        with patch('dj4xol.turn.roll_chance', return_value=True):
            with patch('dj4xol.turn.random.randint', return_value=6):
                GameTurn(game).salvage_interactions()

        fleet.refresh_from_db()
        self.assertEqual(fleet.integrity, 98)
        msg = player.messages.latest('id')
        self.assertFalse(msg.priority)
        self.assertIn('Salvage', msg.message)
        self.assertIn('2% integrity damage', msg.message)
        self.assertIn(fleet.short_id, msg.message)

    def test_wormhole_below_30_stability_can_instantly_destroy(self):
        game = default_game()
        game.anomalies_enabled = True
        game.save(update_fields=['anomalies_enabled'])
        game.stars.all().delete()
        player = game.players.first()
        game.fleets.all().delete()
        fleet = Fleet.objects.create(
            game=game,
            player=player,
            name='Risky Transit',
            x=12,
            y=12,
            integrity=100,
        )
        a = Anomaly.objects.create(
            game=game,
            x=12,
            y=12,
            name='WH-3',
            anomaly_type=Anomaly.TYPE_WORMHOLE,
            stability=0,
        )
        b = Anomaly.objects.create(
            game=game,
            x=32,
            y=32,
            name='WH-3',
            anomaly_type=Anomaly.TYPE_WORMHOLE,
            stability=0,
            wormhole_pair=a,
        )
        a.wormhole_pair = b
        a.save(update_fields=['wormhole_pair'])

        with patch('dj4xol.turn.anomaly_danger_level', return_value=DANGER_MEDIUM), \
             patch('dj4xol.turn.random.random', return_value=0.0):
            GameTurn(game).anomaly_interactions()

        self.assertFalse(Fleet.objects.filter(id=fleet.id).exists())
        self.assertTrue(GameMessage.objects.filter(
            game=game,
            player=player,
            category='RANDOM',
            message__icontains='catastrophic wormhole transit',
        ).exists())

    def test_wormhole_at_30_stability_has_no_instant_destruction_roll(self):
        game = default_game()
        game.anomalies_enabled = True
        game.save(update_fields=['anomalies_enabled'])
        game.stars.all().delete()
        player = game.players.first()
        game.fleets.all().delete()
        fleet = Fleet.objects.create(
            game=game,
            player=player,
            name='Safer Transit',
            x=13,
            y=13,
            integrity=100,
        )
        a = Anomaly.objects.create(
            game=game,
            x=13,
            y=13,
            name='WH-4',
            anomaly_type=Anomaly.TYPE_WORMHOLE,
            stability=30,
        )
        b = Anomaly.objects.create(
            game=game,
            x=33,
            y=33,
            name='WH-4',
            anomaly_type=Anomaly.TYPE_WORMHOLE,
            stability=30,
            wormhole_pair=a,
        )
        a.wormhole_pair = b
        a.save(update_fields=['wormhole_pair'])

        with patch('dj4xol.turn.random.random', return_value=1.0), \
             patch('dj4xol.turn.random.shuffle', lambda vals: None):
            GameTurn(game).anomaly_interactions()

        self.assertTrue(Fleet.objects.filter(id=fleet.id).exists())

    def test_wormhole_none_danger_disables_transit_hazards(self):
        game = default_game()
        game.anomalies_enabled = True
        game.save(update_fields=['anomalies_enabled'])
        game.stars.all().delete()
        player = game.players.first()
        game.fleets.all().delete()
        fleet = Fleet.objects.create(
            game=game,
            player=player,
            name='Gentle Transit',
            x=14,
            y=14,
            integrity=100,
        )
        a = Anomaly.objects.create(
            game=game,
            x=14,
            y=14,
            name='WH-Safe-A',
            anomaly_type=Anomaly.TYPE_WORMHOLE,
            stability=0,
        )
        b = Anomaly.objects.create(
            game=game,
            x=34,
            y=34,
            name='WH-Safe-B',
            anomaly_type=Anomaly.TYPE_WORMHOLE,
            stability=0,
            wormhole_pair=a,
        )
        a.wormhole_pair = b
        a.save(update_fields=['wormhole_pair'])

        with patch('dj4xol.turn.anomaly_danger_level', return_value=DANGER_NONE), \
             patch('dj4xol.turn.random.random', side_effect=[0.0, 0.0]):
            GameTurn(game)._apply_wormhole_interaction(fleet, a)

        fleet.refresh_from_db()
        self.assertEqual(fleet.integrity, 100)
        self.assertNotEqual((fleet.x, fleet.y), (14, 14))
        self.assertTrue(Fleet.objects.filter(id=fleet.id).exists())

    def test_wormhole_low_danger_softens_low_stability_transit_risk(self):
        game = default_game()
        game.anomalies_enabled = True
        game.save(update_fields=['anomalies_enabled'])
        game.stars.all().delete()
        player = game.players.first()
        game.fleets.all().delete()
        fleet = Fleet.objects.create(
            game=game,
            player=player,
            name='Softened Transit',
            x=17,
            y=17,
            integrity=100,
        )
        a = Anomaly.objects.create(
            game=game,
            x=17,
            y=17,
            name='WH-Soft-A',
            anomaly_type=Anomaly.TYPE_WORMHOLE,
            stability=0,
        )
        b = Anomaly.objects.create(
            game=game,
            x=37,
            y=37,
            name='WH-Soft-B',
            anomaly_type=Anomaly.TYPE_WORMHOLE,
            stability=0,
            wormhole_pair=a,
        )
        a.wormhole_pair = b
        a.save(update_fields=['wormhole_pair'])

        with patch('dj4xol.turn.anomaly_danger_level', return_value=DANGER_LOW), \
             patch('dj4xol.turn.random.random', side_effect=[0.2, 1.0]):
            GameTurn(game)._apply_wormhole_interaction(fleet, a)

        self.assertTrue(Fleet.objects.filter(id=fleet.id).exists())
        fleet.refresh_from_db()
        self.assertEqual(fleet.integrity, 100)
        self.assertNotEqual((fleet.x, fleet.y), (17, 17))

    def test_wormhole_endpoint_extinction_transforms_pair_or_deletes(self):
        game = default_game()
        game.anomalies_enabled = True
        game.save(update_fields=['anomalies_enabled'])
        a = Anomaly.objects.create(
            game=game,
            x=15,
            y=15,
            name='WH-Decay',
            anomaly_type=Anomaly.TYPE_WORMHOLE,
            stability=10,
        )
        b = Anomaly.objects.create(
            game=game,
            x=25,
            y=25,
            name='WH-Decay',
            anomaly_type=Anomaly.TYPE_WORMHOLE,
            stability=100,
            wormhole_pair=a,
        )
        a.wormhole_pair = b
        a.save(update_fields=['wormhole_pair'])

        with patch('dj4xol.turn.random.random', side_effect=[0.0, 0.0, 0.0]):
            GameTurn(game).decay_anomalies()

        self.assertFalse(Anomaly.objects.filter(id=a.id).exists())
        self.assertFalse(Anomaly.objects.filter(id=b.id).exists())

    def test_wormhole_endpoint_extinction_can_create_unstable_black_hole(self):
        game = default_game()
        game.anomalies_enabled = True
        game.save(update_fields=['anomalies_enabled'])
        a = Anomaly.objects.create(
            game=game,
            x=16,
            y=16,
            name='WH-Decay2',
            anomaly_type=Anomaly.TYPE_WORMHOLE,
            stability=10,
        )
        b = Anomaly.objects.create(
            game=game,
            x=26,
            y=26,
            name='WH-Decay2',
            anomaly_type=Anomaly.TYPE_WORMHOLE,
            stability=100,
            wormhole_pair=a,
        )
        a.wormhole_pair = b
        a.save(update_fields=['wormhole_pair'])

        with patch('dj4xol.turn.random.random', side_effect=[0.0, 0.0, 0.75, 0.25, 1.0, 1.0, 1.0]):
            GameTurn(game).decay_anomalies()

        self.assertFalse(Anomaly.objects.filter(id=a.id).exists())
        b.refresh_from_db()
        self.assertEqual(b.anomaly_type, Anomaly.TYPE_BLACK_HOLE)
        self.assertTrue(0 <= int(b.stability) < 50)


class TestEconomicCalculations(TestCase):
    """Tests for economic factor calculations."""

    def test_employment_percent_no_colonists(self):
        """Empty star returns 0% employment."""
        game = default_game()
        star = game.stars.first()
        star.colonists = 0
        star.mines = 5
        star.factories = 5
        self.assertEqual(calculate_employment_percent(star), 0)

    def test_employment_percent_full_employment(self):
        """When jobs >= colonists, employment is 100%."""
        game = default_game()
        star = game.stars.first()
        star.colonists = 10000
        star.mines = 5
        star.factories = 5  # 10 jobs * 1000 = 10000 capacity
        self.assertEqual(calculate_employment_percent(star), 100)

    def test_employment_percent_over_employment_capped(self):
        """More jobs than colonists still caps at 100%."""
        game = default_game()
        star = game.stars.first()
        star.colonists = 5000
        star.mines = 5
        star.factories = 5  # 10000 job capacity, only 5000 colonists
        self.assertEqual(calculate_employment_percent(star), 100)

    def test_employment_percent_partial(self):
        """Partial employment calculates correctly."""
        game = default_game()
        star = game.stars.first()
        star.colonists = 20000
        star.mines = 5
        star.factories = 5  # 10000 job capacity / 20000 = 50%
        self.assertEqual(calculate_employment_percent(star), 50)

    def test_available_buildpoints(self):
        """Buildpoints equal factories * BUILDPOINTS_PER_FACTORY when fully staffed."""
        game = default_game()
        star = game.stars.first()
        star.mines = 0
        star.labs = 0
        star.shipyards = 0
        star.defenses = 0
        star.factories = 7
        star.colonists = 7000  # Fully staff the factories
        star.save(update_fields=[
            'mines',
            'labs',
            'shipyards',
            'defenses',
            'factories',
            'colonists',
        ])
        self.assertEqual(calculate_available_buildpoints(star), 7 * BUILDPOINTS_PER_FACTORY)

    def test_available_buildpoints_respects_manufacturing_multiplier(self):
        game = default_game()
        player = game.players.first()
        star = player.homeworld
        star.factories = 7
        star.colonists = 7000
        star.save(update_fields=['factories', 'colonists'])
        baseline = calculate_available_buildpoints(star)
        player.race_type.manufacturing_multiplier = 1.5
        player.race_type.save(update_fields=['manufacturing_multiplier'])
        star = star.__class__.objects.get(pk=star.pk)
        self.assertEqual(
            calculate_available_buildpoints(star),
            int(baseline * 1.5),
        )

    def test_available_buildpoints_no_factories(self):
        """No factories means no buildpoints."""
        game = default_game()
        star = game.stars.first()
        star.factories = 0
        self.assertEqual(calculate_available_buildpoints(star), 0)

    def test_productivity_percent_no_factories(self):
        """No factories returns 0% productivity (avoid division by zero)."""
        game = default_game()
        star = game.stars.first()
        star.factories = 0
        self.assertEqual(calculate_productivity_percent(star), 0)

    def test_productivity_percent_no_consumption(self):
        """With factories but no consumption, productivity is 0%."""
        game = default_game()
        star = game.stars.first()
        star.factories = 10
        # No buildpoints consumed yet (not implemented)
        self.assertEqual(calculate_productivity_percent(star), 0)

    def test_productivity_multiplier_key_points(self):
        """Productivity curve should match key design points."""
        self.assertAlmostEqual(
            calculate_productivity_multiplier(1.0), 1.0, places=3
        )
        self.assertAlmostEqual(
            calculate_productivity_multiplier(0.5), 1.5, places=3
        )
        self.assertAlmostEqual(
            calculate_productivity_multiplier(0.1), 0.5, places=3
        )
        self.assertAlmostEqual(
            calculate_productivity_multiplier(0.01), 0.25, places=3
        )

    def test_productivity_multiplier_has_minimum_floor(self):
        """Any non-zero staffing should keep at least 20% productivity."""
        self.assertGreaterEqual(calculate_productivity_multiplier(0.001), 0.2)

    def test_economy_percent_employment_only(self):
        """With full employment, economy should be positive."""
        game = default_game()
        star = game.stars.first()
        star.colonists = 10000
        star.mines = 5
        star.factories = 5  # 100% employment
        economy = calculate_economy_percent(star)
        self.assertGreater(economy, 0)
        self.assertLessEqual(economy, 100)

    def test_economy_percent_minimum_zero(self):
        """With no employment, economy should be very low."""
        game = default_game()
        star = game.stars.first()
        star.colonists = 100000
        star.mines = 0
        star.factories = 0  # 0% employment
        economy = calculate_economy_percent(star)
        self.assertLess(economy, 50)  # Should be well below 50%

    def test_economy_factor_range(self):
        """Economy factor should be in 0-1 range (coefficient form)."""
        game = default_game()
        star = game.stars.first()
        star.colonists = 10000
        star.mines = 5
        star.factories = 5  # Full employment
        factor = calculate_economy_factor(star)
        self.assertGreaterEqual(factor, 0)
        self.assertLessEqual(factor, 1)

    def test_economy_boosts_habitability_factor(self):
        """Economy factor should boost habitability calculation."""
        from ..turn import calculate_habitability_factor
        game = default_game()
        player = game.players.first()
        star = player.homeworld
        star.shipyards = 0
        star.save()

        race = player.race_type
        race.population_growth_multiplier = 0
        race.save()

        # Get baseline habitability with no economy
        star.mines = 0
        star.factories = 0
        star.defenses = 0
        star.shipyards = 0
        star.colonists = 10000
        baseline = calculate_habitability_factor(player, star)

        # Add full employment
        star.colonists = 10000
        star.mines = 5
        star.factories = 5  # 100% employment -> 50% economy -> 0.5 factor
        boosted = calculate_habitability_factor(player, star)

        # Economy adds to environmental factors before /3 averaging
        # So boosted should be higher than baseline
        self.assertGreater(boosted, baseline)

    def test_build_mine_order(self):
        """BUILD_MINE order should increment mines count."""
        game = default_game()
        player = game.players.first()
        star = player.homeworld
        star.shipyards = 0
        star.save()
        star.mines = 0
        star.ironium_inventory = 100  # Provide resources for building
        star.save()

        ProductionOrder.objects.create(game=game, star=star, order_type='BUILD_MINE')
        GameTurn(game).generate_turn()

        star.refresh_from_db()
        self.assertEqual(star.mines, 1)

    def test_build_factory_order(self):
        """BUILD_FACTORY order should increment factories count."""
        game = default_game()
        player = game.players.first()
        star = player.homeworld
        star.factories = 0
        star.ironium_inventory = 100  # Provide resources for building
        star.save()

        ProductionOrder.objects.create(game=game, star=star, order_type='BUILD_FACTORY')
        GameTurn(game).generate_turn()

        star.refresh_from_db()
        self.assertEqual(star.factories, 1)

    def test_build_mine_order_uses_unemployed_colonists_over_multiple_turns(self):
        """Mine construction should use free workforce and carry partial progress."""
        game = default_game()
        player = game.players.first()
        star = player.homeworld
        star.mines = 1
        star.factories = 0
        star.labs = 0
        star.shipyards = 0
        star.defenses = 0
        star.colonists = 1500
        star.ironium_inventory = 100
        star.save(update_fields=[
            'mines', 'factories', 'labs', 'shipyards', 'defenses',
            'colonists', 'ironium_inventory',
        ])

        order = ProductionOrder.objects.create(
            game=game,
            star=star,
            order_type='BUILD_MINE',
        )

        GameTurn(game).production()

        star.refresh_from_db()
        order.refresh_from_db()
        self.assertEqual(star.mines, 1)
        self.assertEqual(order.spent_bp, 500)
        self.assertEqual(order.spent_ironium, 10)

        GameTurn(game).production()

        star.refresh_from_db()
        self.assertEqual(star.mines, 2)
        self.assertFalse(
            ProductionOrder.objects.filter(id=order.id).exists()
        )

    def test_build_factory_order_can_finish_two_items_with_two_thousand_free_colonists(self):
        """Two colonist-built items should complete in one turn with 2000 free colonists."""
        game = default_game()
        player = game.players.first()
        star = player.homeworld
        star.mines = 0
        star.factories = 0
        star.labs = 0
        star.shipyards = 0
        star.defenses = 0
        star.colonists = 2000
        star.ironium_inventory = 100
        star.save(update_fields=[
            'mines', 'factories', 'labs', 'shipyards', 'defenses',
            'colonists', 'ironium_inventory',
        ])

        ProductionOrder.objects.create(
            game=game,
            star=star,
            order_type='BUILD_FACTORY',
            quantity=2,
        )

        GameTurn(game).production()

        star.refresh_from_db()
        self.assertEqual(star.factories, 2)

    def test_mining_extracts_minerals(self):
        """Mines should extract minerals to surface inventory."""
        game = default_game()
        player = game.players.first()
        star = player.homeworld
        star.mines = 5
        star.ironium_yield = 50  # 50% yield
        star.boranium_yield = 30  # 30% yield
        star.germanium_yield = 20  # 20% yield
        star.ironium_inventory = 0
        star.boranium_inventory = 0
        star.germanium_inventory = 0
        star.save()

        GameTurn(game).generate_turn()

        star.refresh_from_db()
        # Mines should produce some minerals
        total = star.ironium_inventory + star.boranium_inventory + star.germanium_inventory
        self.assertGreater(total, 0)

    def test_mining_no_mines(self):
        """No mines should not extract any minerals."""
        game = default_game()
        player = game.players.first()
        star = player.homeworld
        star.mines = 0
        star.ironium_inventory = 0
        star.boranium_inventory = 0
        star.germanium_inventory = 0
        star.save()

        GameTurn(game).generate_turn()

        star.refresh_from_db()
        self.assertEqual(star.ironium_inventory, 0)
        self.assertEqual(star.boranium_inventory, 0)
        self.assertEqual(star.germanium_inventory, 0)

    def test_mining_accumulates(self):
        """Mining should accumulate surface minerals over turns."""
        game = default_game()
        player = game.players.first()
        star = player.homeworld
        star.mines = 2
        star.ironium_yield = 100  # 100% yield (only ironium)
        star.boranium_yield = 0
        star.germanium_yield = 0
        star.ironium_inventory = 100  # Start with some
        star.save()

        GameTurn(game).generate_turn()

        star.refresh_from_db()
        # Mining should have added to the existing inventory
        self.assertGreater(star.ironium_inventory, 100)

    def test_secret_resource_yield_depletes(self):
        """Secret resource yields should deplete with heavy mining."""
        game = default_game(stars=5)
        player = game.players.first()
        star = game.stars.exclude(pk=player.homeworld.pk).first()

        star.player = player
        star.colonists = 20000000  # 20M colonists to staff 20k mines
        star.mines = 20000
        star.factories = 0
        star.labs = 0
        star.defenses = 0
        star.shipyards = 0
        star.resource_x_yield = 100
        star.resource_x_inventory = 0
        star.ironium_yield = 0
        star.boranium_yield = 0
        star.germanium_yield = 0
        star.save()

        initial_yield = star.resource_x_yield
        GameTurn(game).mining()

        star.refresh_from_db()
        self.assertLess(star.resource_x_yield, initial_yield)

    def test_mining_low_yield_has_chance(self):
        """Low yield resources should still have a chance to produce."""
        game = default_game()
        player = game.players.first()
        star = player.homeworld
        star.mines = 10
        star.ironium_yield = 1  # 1% yield
        star.boranium_yield = 99  # 99% yield
        star.germanium_yield = 0
        star.ironium_inventory = 0
        star.boranium_inventory = 0
        star.save()

        # Run many turns - ironium should eventually produce something
        produced_ironium = False
        for _ in range(100):
            GameTurn(game).generate_turn()
            star.refresh_from_db()
            if star.ironium_inventory > 0:
                produced_ironium = True
                break

        self.assertTrue(produced_ironium, "Low yield should occasionally produce")

    def test_mining_homeworld_yield_floor(self):
        """Homeworld yields should not drop below minimum."""
        game = default_game()
        player = game.players.first()
        star = player.homeworld
        star.mines = 100  # Many mines to force depletion
        star.ironium_yield = HOMEWORLD_MIN_YIELD  # At the floor
        star.boranium_yield = 0
        star.germanium_yield = 0
        star.save()

        # Run several turns
        for _ in range(10):
            GameTurn(game).generate_turn()

        star.refresh_from_db()
        self.assertGreaterEqual(star.ironium_yield, HOMEWORLD_MIN_YIELD)

    def test_mining_non_homeworld_produces_minerals(self):
        """Non-homeworld mining produces minerals over time."""
        game = default_game(stars=5)
        player = game.players.first()
        # Get a non-homeworld star
        other_star = game.stars.exclude(pk=player.homeworld.pk).first()
        other_star.player = player
        other_star.colonists = 1000
        other_star.mines = 10
        other_star.ironium_yield = 50  # 50% yield
        other_star.boranium_yield = 30
        other_star.germanium_yield = 20
        other_star.ironium_inventory = 0
        other_star.boranium_inventory = 0
        other_star.germanium_inventory = 0
        other_star.save()

        # Run a few turns
        for _ in range(5):
            GameTurn(game).generate_turn()

        other_star.refresh_from_db()
        # Should have produced minerals
        total_minerals = (other_star.ironium_inventory +
                         other_star.boranium_inventory +
                         other_star.germanium_inventory)
        self.assertGreater(total_minerals, 0)


class TestFleetTransferOrderExecution(TestCase):
    """Test fleet transfer order execution and movement behavior."""

    def test_transfer_order_creation(self):
        """Test creation of transfer orders with all parameters."""
        from ..models import FleetOrders, Fleet

        game = default_game()
        player = game.players.first()
        star = player.homeworld

        fleet = Fleet.objects.create(
            game=game,
            player=player,
            name="Transfer Fleet",
            x=star.x,
            y=star.y
        )

        order = FleetOrders.objects.create(
            game=game,
            fleet=fleet,
            order_type='TRANSFER',
            target_star=star,
            transfer_type='LOAD',
            transfer_ironium=1000,
            transfer_boranium=500,
            transfer_germanium=200,
            transfer_colonists=100,
            repeat=True
        )

        self.assertEqual(order.order_type, 'TRANSFER')
        self.assertEqual(order.target_star, star)
        self.assertEqual(order.transfer_type, 'LOAD')
        self.assertEqual(order.transfer_ironium, 1000)
        self.assertEqual(order.transfer_boranium, 500)
        self.assertEqual(order.transfer_germanium, 200)
        self.assertEqual(order.transfer_colonists, 100)
        self.assertTrue(order.repeat)

    def test_get_destination_coordinates_from_star(self):
        """Test order destination coordinate resolution for star targets."""
        from ..models import FleetOrders, Fleet

        game = default_game()
        player = game.players.first()
        star = player.homeworld

        fleet = Fleet.objects.create(game=game, player=player, name="Test Fleet", x=10, y=10)

        order = FleetOrders.objects.create(
            game=game,
            fleet=fleet,
            order_type='TRANSFER',
            target_star=star
        )

        x, y = order.get_destination_coordinates()
        self.assertEqual(x, star.x)
        self.assertEqual(y, star.y)

    def test_get_destination_coordinates_from_fleet(self):
        """Test order destination coordinate resolution for fleet targets."""
        from ..models import FleetOrders, Fleet

        game = default_game()
        player = game.players.first()

        fleet1 = Fleet.objects.create(game=game, player=player, name="Fleet 1", x=10, y=10)
        fleet2 = Fleet.objects.create(game=game, player=player, name="Fleet 2", x=25, y=30)

        order = FleetOrders.objects.create(
            game=game,
            fleet=fleet1,
            order_type='TRANSFER',
            target_fleet=fleet2
        )

        x, y = order.get_destination_coordinates()
        self.assertEqual(x, 25)
        self.assertEqual(y, 30)

    def test_get_destination_coordinates_from_xy(self):
        """Test order destination coordinate resolution for coordinate targets."""
        from ..models import FleetOrders, Fleet

        game = default_game()
        player = game.players.first()

        fleet = Fleet.objects.create(game=game, player=player, name="Test Fleet", x=10, y=10)

        order = FleetOrders.objects.create(
            game=game,
            fleet=fleet,
            order_type='TRANSFER',
            x=50,
            y=75
        )

        x, y = order.get_destination_coordinates()
        self.assertEqual(x, 50)
        self.assertEqual(y, 75)

    def test_transfer_load_from_star_at_location(self):
        """Test instant transfer execution when fleet is at star location."""
        from ..models import FleetOrders, Fleet

        game = default_game()
        player = game.players.first()
        star = player.homeworld

        # Set up star with resources
        star.ironium_inventory = 2000
        star.boranium_inventory = 1000
        star.germanium_inventory = 500
        star.colonists = 50000  # 50k individuals
        star.save()

        # Create fleet at same location
        fleet = Fleet.objects.create(
            game=game,
            player=player,
            name="Cargo Fleet",
            x=star.x,
            y=star.y,
            cargo_capacity=1000
        )

        # Create load order
        order = FleetOrders.objects.create(
            game=game,
            fleet=fleet,
            order_type='TRANSFER',
            target_star=star,
            transfer_type='LOAD',
            transfer_ironium=500,
            transfer_boranium=300,
            transfer_germanium=100,
            transfer_colonists=50  # 50kt = 50k individuals
        )

        # Generate turn - should execute transfer instantly
        GameTurn(game).generate_turn()

        # Refresh objects
        star.refresh_from_db()
        fleet.refresh_from_db()

        # Star should have resources removed
        self.assertEqual(star.ironium_inventory, 1500)  # 2000 - 500
        self.assertEqual(star.boranium_inventory, 700)   # 1000 - 300
        self.assertEqual(star.germanium_inventory, 400)  # 500 - 100
        self.assertEqual(star.colonists, 0)            # 50000 - 50000

        # Fleet should have resources added
        self.assertEqual(fleet.ironium_inventory, 500)
        self.assertEqual(fleet.boranium_inventory, 300)
        self.assertEqual(fleet.germanium_inventory, 100)
        self.assertEqual(fleet.colonists, 50)  # 50k individuals stored as 50kt

        # Order should be deleted
        self.assertEqual(fleet.orders.count(), 0)

    def test_transfer_unload_to_star_at_location(self):
        """Test instant unload transfer execution."""
        from ..models import FleetOrders, Fleet

        game = default_game()
        player = game.players.first()
        star = player.homeworld

        race = player.race_type
        race.population_growth_multiplier = 0
        race.save()

        # Set up star with some existing resources
        star.ironium_inventory = 100
        star.boranium_inventory = 50
        star.germanium_inventory = 25
        star.colonists = 5000  # 5k individuals
        star.mines = 0
        star.ironium_yield = 0
        star.boranium_yield = 0
        star.germanium_yield = 0
        star.save()

        # Create fleet with cargo at same location
        fleet = Fleet.objects.create(
            game=game,
            player=player,
            name="Cargo Fleet",
            x=star.x,
            y=star.y,
            ironium_inventory=25,
            boranium_inventory=15,
            germanium_inventory=15,
            colonists=10  # 10k individuals stored as 10kt
        )

        # Create unload order
        order = FleetOrders.objects.create(
            game=game,
            fleet=fleet,
            order_type='TRANSFER',
            target_star=star,
            transfer_type='UNLOAD',
            transfer_ironium=20,
            transfer_boranium=15,
            transfer_germanium=15,
            transfer_colonists=10
        )

        original_colonists = star.colonists
        # Generate turn
        GameTurn(game).generate_turn()

        # Refresh objects
        star.refresh_from_db()
        fleet.refresh_from_db()

        # Star should have resources added
        self.assertEqual(star.ironium_inventory, 120)   # 100 + 20
        self.assertEqual(star.boranium_inventory, 65)  # 50 + 15
        self.assertEqual(star.germanium_inventory, 40) # 25 + 15
        self.assertEqual(star.colonists, original_colonists + 10000)  # +10k colonists

        # Fleet should have resources removed
        self.assertEqual(fleet.ironium_inventory, 5)
        self.assertEqual(fleet.boranium_inventory, 0)
        self.assertEqual(fleet.germanium_inventory, 0)
        self.assertEqual(fleet.colonists, 0)

        # Order should be deleted
        self.assertEqual(fleet.orders.count(), 0)

    def test_transfer_proportional_allocation(self):
        """Test proportional allocation when fleet capacity insufficient."""
        from ..models import FleetOrders, Fleet

        game = default_game()
        player = game.players.first()
        star = player.homeworld

        # Set up star with abundant resources
        star.ironium_inventory = 5000
        star.boranium_inventory = 5000
        star.germanium_inventory = 5000
        star.colonists = 100000
        star.save()

        # Create small capacity fleet
        fleet = Fleet.objects.create(
            game=game,
            player=player,
            name="Small Fleet",
            x=star.x,
            y=star.y,
            cargo_capacity=1000  # Only 1000kt capacity
        )

        # Try to load 4000kt total (more than capacity)
        order = FleetOrders.objects.create(
            game=game,
            fleet=fleet,
            order_type='TRANSFER',
            target_star=star,
            transfer_type='LOAD',
            transfer_ironium=1000,   # 25% of request
            transfer_boranium=1000,  # 25% of request
            transfer_germanium=1000, # 25% of request
            transfer_colonists=1000  # 25% of request
        )

        # Generate turn
        GameTurn(game).generate_turn()

        # Refresh objects
        star.refresh_from_db()
        fleet.refresh_from_db()

        # Should transfer exactly 1000kt total, proportionally allocated
        # Each resource gets 1000/4000 = 25% of what was requested
        self.assertEqual(fleet.ironium_inventory, 250)   # 1000 * 0.25
        self.assertEqual(fleet.boranium_inventory, 250)  # 1000 * 0.25
        self.assertEqual(fleet.germanium_inventory, 250) # 1000 * 0.25
        # Colonists are limited by available population (100000 individuals = 100kt)
        self.assertEqual(fleet.colonists, 100)

        # Total cargo reflects colonist availability cap
        self.assertEqual(fleet.cargo_used, 850)

        # Star should have corresponding amounts removed
        self.assertEqual(star.ironium_inventory, 4750)  # 5000 - 250
        self.assertEqual(star.boranium_inventory, 4750)
        self.assertEqual(star.germanium_inventory, 4750)
        self.assertEqual(star.colonists, 0)  # 100000 individuals transferred (100kt)

    def test_transfer_overprovision_includes_secret_resources(self):
        """Overprovisioned transfers should allocate secret resources proportionally."""
        from ..models import FleetOrders, Fleet

        game = default_game()
        player = game.players.first()
        star = player.homeworld

        star.ironium_inventory = 1000
        star.resource_x_inventory = 1000
        star.colonists = 0
        star.save()

        fleet = Fleet.objects.create(
            game=game,
            player=player,
            name="Secret Cargo Fleet",
            x=star.x,
            y=star.y,
            cargo_capacity=100
        )

        order = FleetOrders.objects.create(
            game=game,
            fleet=fleet,
            order_type='TRANSFER',
            target_star=star,
            transfer_type='LOAD',
            transfer_ironium=100,
            transfer_resource_x=100,
        )

        GameTurn(game).generate_turn()

        star.refresh_from_db()
        fleet.refresh_from_db()

        self.assertEqual(fleet.ironium_inventory, 50)
        self.assertEqual(fleet.resource_x_inventory, 50)
        self.assertEqual(fleet.cargo_used, 100)
        self.assertEqual(star.ironium_inventory, 950)
        self.assertEqual(star.resource_x_inventory, 950)

    def test_transfer_move_then_execute(self):
        """Test transfer that requires movement first."""
        from ..models import FleetOrders, Fleet

        game = default_game(stars=5)
        player = game.players.first()
        source_star = player.homeworld

        # Fix coordinates for deterministic distance
        source_star.x = 10
        source_star.y = 10
        source_star.save()

        target_star = game.stars.exclude(pk=source_star.pk).first()
        target_star.x = 20
        target_star.y = 20
        target_star.ironium_inventory = 1000
        target_star.save()

        # Create fleet at source
        fleet = Fleet.objects.create(
            game=game,
            player=player,
            name="Mobile Fleet",
            x=source_star.x,
            y=source_star.y
        )

        # Create move then transfer orders for distant star
        FleetOrders.objects.create(
            game=game,
            fleet=fleet,
            order_type='MOVE',
            target_star=target_star,
            warpfactor=1
        )

        order = FleetOrders.objects.create(
            game=game,
            fleet=fleet,
            order_type='TRANSFER',
            target_star=target_star,
            transfer_type='LOAD',
            transfer_ironium=100
        )

        # First turn - should move toward target
        GameTurn(game).generate_turn()

        fleet.refresh_from_db()
        # Fleet should have moved but not reached destination
        self.assertNotEqual((fleet.x, fleet.y), (source_star.x, source_star.y))  # Has moved
        self.assertNotEqual((fleet.x, fleet.y), (target_star.x, target_star.y))  # But hasn't arrived

        # Order should still exist
        self.assertTrue(fleet.orders.filter(order_type='TRANSFER').exists())

        # Fleet cargo should be unchanged (no transfer yet)
        self.assertEqual(fleet.ironium_inventory, 0)

        # Generate several more turns until fleet arrives
        reached = False
        for _ in range(500):  # Max attempts to avoid infinite loop
            if fleet.x == target_star.x and fleet.y == target_star.y:
                reached = True
                break
            GameTurn(game).generate_turn()
            fleet.refresh_from_db()
            if fleet.orders.count() == 0:
                reached = (fleet.x == target_star.x and fleet.y == target_star.y)
                break

        # Fleet should now be at target and transfer should have executed
        # in the same turn as arrival.
        self.assertTrue(reached)
        self.assertEqual(fleet.x, target_star.x)
        self.assertEqual(fleet.y, target_star.y)
        self.assertEqual(fleet.orders.count(), 0)  # Transfer completed
        self.assertEqual(fleet.ironium_inventory, 100)  # Transfer executed

    def test_move_diagonal_at_warp_one(self):
        """Fleet should move diagonally at warp 1 when target is diagonal."""
        from ..models import FleetOrders, Fleet

        game = default_game()
        player = game.players.first()

        fleet = Fleet.objects.create(
            game=game,
            player=player,
            name="Diagonal Mover",
            x=10,
            y=10,
            max_safe_warp=1
        )

        FleetOrders.objects.create(
            game=game,
            fleet=fleet,
            order_type='MOVE',
            x=11,
            y=11,
            warpfactor=1
        )

        GameTurn(game).generate_turn()
        fleet.refresh_from_db()

        self.assertEqual(fleet.x, 11)
        self.assertEqual(fleet.y, 11)

    def test_transfer_fleet_target_waiting(self):
        """Test transfer waiting behavior when target fleet is not at expected location."""
        from ..models import FleetOrders, Fleet

        game = default_game()
        player = game.players.first()

        # Use explicit coordinates within map bounds
        fleet1 = Fleet.objects.create(
            game=game,
            player=player,
            name="Transfer Fleet",
            x=10,
            y=10,
            ironium_inventory=1000
        )

        fleet2 = Fleet.objects.create(
            game=game,
            player=player,
            name="Target Fleet",
            x=10,
            y=10
        )

        # Create transfer order from fleet1 to fleet2
        order = FleetOrders.objects.create(
            game=game,
            fleet=fleet1,
            order_type='TRANSFER',
            target_fleet=fleet2,
            transfer_type='UNLOAD',
            transfer_ironium=500
        )

        # Move target fleet away (still within bounds)
        fleet2.x = 20
        fleet2.y = 20
        fleet2.save()

        # Generate turn
        GameTurn(game).generate_turn()

        fleet1.refresh_from_db()

        # Transfer should not have executed (waiting for target)
        self.assertEqual(fleet1.ironium_inventory, 1000)  # Unchanged
        self.assertEqual(fleet1.orders.count(), 1)  # Order still exists

    def test_transfer_repeat_functionality(self):
        """Test repeating transfer orders."""
        from ..models import FleetOrders, Fleet

        game = default_game()
        player = game.players.first()
        star = player.homeworld

        # Set up star with lots of resources
        star.ironium_inventory = 10000
        star.mines = 0
        star.ironium_yield = 0
        star.boranium_yield = 0
        star.germanium_yield = 0
        star.save()

        fleet = Fleet.objects.create(
            game=game,
            player=player,
            name="Repeat Fleet",
            x=star.x,
            y=star.y
        )

        # Create repeating transfer order
        order = FleetOrders.objects.create(
            game=game,
            fleet=fleet,
            order_type='TRANSFER',
            target_star=star,
            transfer_type='LOAD',
            transfer_ironium=100,
            repeat=True
        )
        original_order_id = order.id

        # Generate turn
        GameTurn(game).generate_turn()

        fleet.refresh_from_db()
        star.refresh_from_db()

        # Transfer should have executed
        self.assertEqual(fleet.ironium_inventory, 100)
        self.assertEqual(star.ironium_inventory, 9900)

        # Original order should be deleted, new repeat order should exist
        self.assertFalse(FleetOrders.objects.filter(id=original_order_id).exists())
        self.assertEqual(fleet.orders.count(), 1)

        new_order = fleet.orders.first()
        self.assertNotEqual(new_order.id, original_order_id)
        self.assertTrue(new_order.repeat)
        self.assertEqual(new_order.transfer_ironium, 100)

    def test_effective_location_calculation(self):
        """Test calculation of fleet effective location with move orders."""
        from ..models import FleetOrders, Fleet
        from ..objectdetails import DetailBuilder

        game = default_game(stars=5)
        player = game.players.first()
        source_star = player.homeworld

        # Find target stars
        target_stars = game.stars.exclude(pk=source_star.pk)[:2]
        star_a = target_stars[0]
        star_b = target_stars[1]

        fleet = Fleet.objects.create(
            game=game,
            player=player,
            name="Moving Fleet",
            x=source_star.x,
            y=source_star.y
        )

        # Create move orders: source -> star_a -> star_b
        FleetOrders.objects.create(
            game=game,
            fleet=fleet,
            order_type='MOVE',
            target_star=star_a,
            warpfactor=5
        )

        FleetOrders.objects.create(
            game=game,
            fleet=fleet,
            order_type='MOVE',
            target_star=star_b,
            warpfactor=5
        )

        # Build detail to get effective location
        builder = DetailBuilder(game, fleet.x, fleet.y, fleet.short_id, player)
        effective_x, effective_y = builder.get_fleet_effective_location()

        # Should be star_b location (final destination)
        self.assertEqual(effective_x, star_b.x)
        self.assertEqual(effective_y, star_b.y)

    def test_transfer_targets_include_future_positions(self):
        """Test that transfer targets include fleets that will be at the effective location."""
        from ..models import FleetOrders, Fleet
        from ..objectdetails import DetailBuilder

        game = default_game(stars=5)
        player = game.players.first()

        # Get two stars
        stars = game.stars.all()[:2]
        star_a = stars[0]
        star_b = stars[1]

        # Create fleet1 at star_a with order to move to star_b
        fleet1 = Fleet.objects.create(
            game=game,
            player=player,
            name="Moving Fleet",
            x=star_a.x,
            y=star_a.y
        )

        FleetOrders.objects.create(
            game=game,
            fleet=fleet1,
            order_type='MOVE',
            target_star=star_b,
            warpfactor=5
        )

        # Create fleet2 that will also move to star_b
        fleet2 = Fleet.objects.create(
            game=game,
            player=player,
            name="Other Fleet",
            x=star_a.x + 5,
            y=star_a.y + 5
        )

        FleetOrders.objects.create(
            game=game,
            fleet=fleet2,
            order_type='MOVE',
            target_star=star_b,
            warpfactor=5
        )

        # Get transfer targets for fleet1
        builder = DetailBuilder(game, fleet1.x, fleet1.y, fleet1.short_id, player)
        targets = builder.get_transfer_targets()['targets']

        # Should include star_b and fleet2 (both will be at star_b)
        target_names = [t['name'] for t in targets]
        self.assertIn(star_b.name, target_names)
        self.assertIn(fleet2.name, target_names)

        # Should not include fleet1 itself
        self.assertNotIn(fleet1.name, target_names)

    def test_destination_targets_order_homeworld_stars_then_fleets(self):
        game = default_game(stars=5, fleets=0)
        game.joinable = True
        game.save(update_fields=['joinable'])
        player = game.players.first()
        home = player.homeworld
        other_star = game.stars.exclude(pk=home.pk).first()
        other_star.x = home.x
        other_star.y = home.y
        other_star.save(update_fields=['x', 'y'])

        own_fleet = Fleet.objects.create(
            game=game,
            player=player,
            name='Alpha Fleet',
            x=home.x,
            y=home.y,
            basic_scanner_range=6,
        )

        other_user = User.objects.create_user('ordering_enemy', 'oe@test.com', 'pass')
        other_account = Account.objects.create(django_user=other_user)
        enemy_player = GameFactory(game=game).join_player(other_account, get_default_race())
        enemy_fleet = Fleet.objects.create(
            game=game,
            player=enemy_player,
            name='Beta Fleet',
            x=home.x,
            y=home.y,
        )

        builder = DetailBuilder(game, home.x, home.y, own_fleet.short_id, player)
        targets = builder.get_destination_targets(home.x, home.y)['targets']

        star_targets = [t for t in targets if t['type'] == 'star']
        fleet_targets = [t for t in targets if t['type'] == 'fleet']

        self.assertEqual(star_targets[0]['short_id'], home.short_id)
        self.assertEqual(star_targets[0]['display_label'], '%s (home)' % home.name)
        self.assertEqual(
            [t['short_id'] for t in star_targets[1:]],
            sorted([other_star.short_id]),
        )
        own_fleet_index = next(
            i for i, target in enumerate(fleet_targets)
            if target['short_id'] == own_fleet.short_id
        )
        enemy_fleet_index = next(
            i for i, target in enumerate(fleet_targets)
            if target['short_id'] == enemy_fleet.short_id
        )
        self.assertLess(own_fleet_index, enemy_fleet_index)
        self.assertFalse(fleet_targets[enemy_fleet_index].get('is_owned'))
        self.assertEqual(
            [t['type'] for t in targets[:4]],
            ['star', 'star', 'fleet', 'fleet'],
        )

    def test_destination_targets_obfuscate_unresolved_enemy_fleet_names(self):
        game = default_game(stars=5, fleets=0)
        game.joinable = True
        game.save(update_fields=['joinable'])
        player = game.players.first()
        home = player.homeworld

        own_fleet = Fleet.objects.create(
            game=game,
            player=player,
            name='Alpha Fleet',
            x=home.x,
            y=home.y,
            basic_scanner_range=6,
            advanced_scanner_range=0,
        )
        other_user = User.objects.create_user('order_obf_enemy', 'oob@test.com', 'pass')
        other_account = Account.objects.create(django_user=other_user)
        enemy_player = GameFactory(game=game).join_player(other_account, get_default_race())
        enemy_fleet = Fleet.objects.create(
            game=game,
            player=enemy_player,
            name='Leaky Enemy Name',
            x=home.x,
            y=home.y,
        )

        builder = DetailBuilder(game, home.x, home.y, own_fleet.short_id, player)
        targets = builder.get_destination_targets(home.x, home.y)['targets']
        enemy_target = next(
            target for target in targets
            if target['type'] == 'fleet' and target['short_id'] == enemy_fleet.short_id
        )

        self.assertEqual(enemy_target['name'], 'Unknown Fleet')
        self.assertIn('Unknown Fleet', enemy_target['display_label'])
        self.assertNotIn('Leaky Enemy Name', enemy_target['display_label'])

    def test_transfer_targets_order_future_fleets_after_current_fleets(self):
        game = default_game(stars=5, fleets=0)
        player = game.players.first()
        home = player.homeworld
        other_star = game.stars.exclude(pk=home.pk).first()
        other_star.x = home.x
        other_star.y = home.y
        other_star.save(update_fields=['x', 'y'])

        fleet1 = Fleet.objects.create(
            game=game,
            player=player,
            name='Selected Fleet',
            x=home.x + 4,
            y=home.y + 4,
        )
        FleetOrders.objects.create(
            game=game,
            fleet=fleet1,
            order_type='MOVE',
            target_star=home,
            warpfactor=5,
        )

        current_fleet = Fleet.objects.create(
            game=game,
            player=player,
            name='Current Fleet',
            x=home.x,
            y=home.y,
        )
        future_fleet = Fleet.objects.create(
            game=game,
            player=player,
            name='Future Fleet',
            x=home.x + 8,
            y=home.y + 8,
        )
        FleetOrders.objects.create(
            game=game,
            fleet=future_fleet,
            order_type='MOVE',
            target_star=home,
            warpfactor=5,
        )

        builder = DetailBuilder(game, fleet1.x, fleet1.y, fleet1.short_id, player)
        targets = builder.get_transfer_targets()['targets']

        self.assertEqual(
            [target['type'] for target in targets[:4]],
            ['star', 'star', 'fleet', 'fleet'],
        )
        self.assertEqual(targets[0]['short_id'], home.short_id)
        self.assertEqual(targets[0]['display_label'], '%s (home)' % home.name)
        current_fleet_index = next(
            i for i, target in enumerate(targets)
            if target['short_id'] == current_fleet.short_id
        )
        future_fleet_index = next(
            i for i, target in enumerate(targets)
            if target['short_id'] == future_fleet.short_id
        )
        self.assertLess(current_fleet_index, future_fleet_index)
        self.assertFalse(targets[current_fleet_index]['is_future'])
        self.assertTrue(targets[future_fleet_index]['is_future'])

    def test_objects_here_order_homeworld_stars_then_fleets(self):
        game = default_game(stars=5, fleets=0)
        game.joinable = True
        game.save(update_fields=['joinable'])
        player = game.players.first()
        home = player.homeworld
        other_star = game.stars.exclude(pk=home.pk).first()
        other_star.x = home.x
        other_star.y = home.y
        other_star.save(update_fields=['x', 'y'])

        own_fleet = Fleet.objects.create(
            game=game,
            player=player,
            name='Visible Own Fleet',
            x=home.x,
            y=home.y,
            basic_scanner_range=6,
        )

        other_user = User.objects.create_user('objects_enemy', 'obj@test.com', 'pass')
        other_account = Account.objects.create(django_user=other_user)
        enemy_player = GameFactory(game=game).join_player(other_account, get_default_race())
        enemy_fleet = Fleet.objects.create(
            game=game,
            player=enemy_player,
            name='Visible Enemy Fleet',
            x=home.x,
            y=home.y,
        )

        detail = DetailBuilder(
            game, x=home.x, y=home.y, selected=home.short_id, player=player
        ).build_detail()
        objects_here = detail['objects_here']

        self.assertEqual(
            [obj['type'] for obj in objects_here[:4]],
            ['star', 'star', 'fleet', 'fleet'],
        )
        self.assertEqual(objects_here[0]['short_id'], home.short_id)
        self.assertEqual(objects_here[0]['display_label'], '%s (home)' % home.name)
        own_fleet_index = next(
            i for i, obj in enumerate(objects_here)
            if obj['short_id'] == own_fleet.short_id
        )
        enemy_fleet_index = next(
            i for i, obj in enumerate(objects_here)
            if obj['short_id'] == enemy_fleet.short_id
        )
        self.assertLess(own_fleet_index, enemy_fleet_index)

    def test_owned_non_homeworld_star_uses_colony_label(self):
        game = default_game(stars=5, fleets=0)
        player = game.players.first()
        home = player.homeworld
        colony = game.stars.exclude(pk=home.pk).first()
        colony.player = player
        colony.x = home.x
        colony.y = home.y
        colony.save(update_fields=['player', 'x', 'y'])

        detail = DetailBuilder(
            game, x=home.x, y=home.y, selected=home.short_id, player=player
        ).build_detail()
        stars_here = [obj for obj in detail['objects_here'] if obj['type'] == 'star']

        colony_entry = next(
            obj for obj in stars_here if obj['short_id'] == colony.short_id
        )
        self.assertEqual(stars_here[0]['short_id'], home.short_id)
        self.assertEqual(stars_here[0]['display_label'], '%s (home)' % home.name)
        self.assertEqual(colony_entry['display_label'], '%s (colony)' % colony.name)

    def test_get_fleet_orders_handles_missing_target_star_relation(self):
        """Detail builder should not crash if target_star relation becomes stale."""
        game = default_game(stars=3)
        player = game.players.first()
        home = player.homeworld
        target = game.stars.exclude(pk=home.pk).first()

        fleet = Fleet.objects.create(
            game=game,
            player=player,
            name="UI Safe Fleet",
            x=home.x,
            y=home.y,
        )
        FleetOrders.objects.create(
            game=game,
            fleet=fleet,
            order_type='BOMB',
            target_star=target,
            x=target.x,
            y=target.y,
        )

        builder = DetailBuilder(game, fleet.x, fleet.y, fleet.short_id, player)
        with patch.object(FleetOrders, 'target_star', new_callable=PropertyMock, side_effect=Star.DoesNotExist):
            orders = builder.get_fleet_orders()

        self.assertEqual(len(orders), 1)
        self.assertEqual(orders[0]['order_type'], 'BOMB')

    def test_get_fleet_orders_obfuscates_unresolved_enemy_fleet_targets(self):
        game = default_game(stars=5, fleets=0)
        game.joinable = True
        game.save(update_fields=['joinable'])
        player = game.players.first()
        home = player.homeworld
        own_fleet = Fleet.objects.create(
            game=game,
            player=player,
            name='Interceptor',
            x=home.x,
            y=home.y,
            basic_scanner_range=6,
            advanced_scanner_range=0,
        )
        other_user = User.objects.create_user('order_queue_enemy', 'oqe@test.com', 'pass')
        other_account = Account.objects.create(django_user=other_user)
        enemy_player = GameFactory(game=game).join_player(other_account, get_default_race())
        enemy_fleet = Fleet.objects.create(
            game=game,
            player=enemy_player,
            name='Leaky Queue Name',
            x=home.x,
            y=home.y,
        )
        FleetOrders.objects.create(
            game=game,
            fleet=own_fleet,
            order_type='INTERCEPT',
            target_fleet=enemy_fleet,
            warpfactor=5,
        )

        builder = DetailBuilder(game, own_fleet.x, own_fleet.y, own_fleet.short_id, player)
        orders = builder.get_fleet_orders()

        self.assertEqual(len(orders), 1)
        self.assertEqual(orders[0]['target'], 'Unknown Fleet')
        self.assertNotIn('Leaky Queue Name', orders[0]['target'])

    def test_get_fleet_orders_uses_last_known_report_position_for_hidden_enemy_target(self):
        game = default_game(stars=5, fleets=0)
        game.joinable = True
        game.save(update_fields=['joinable'])
        player = game.players.first()
        home = player.homeworld
        own_fleet = Fleet.objects.create(
            game=game,
            player=player,
            name='Tracker',
            x=home.x,
            y=home.y,
            basic_scanner_range=6,
            advanced_scanner_range=0,
        )
        other_user = User.objects.create_user('order_report_enemy', 'ore@test.com', 'pass')
        other_account = Account.objects.create(django_user=other_user)
        enemy_player = GameFactory(game=game).join_player(other_account, get_default_race())
        enemy_fleet = Fleet.objects.create(
            game=game,
            player=enemy_player,
            name='Ghost Fleet',
            x=home.x + 2,
            y=home.y,
        )
        report = Report.objects.create(
            game=game,
            player=player,
            year=game.year - 1,
            target_type='fleet',
            target_id=enemy_fleet.id,
            cached_report='{}',
        )
        report.set_report_data({
            'name': 'Unknown Fleet',
            'x': home.x + 5,
            'y': home.y + 4,
            'report_tier': 'basic',
        })
        report.save(update_fields=['cached_report'])

        enemy_fleet.x = home.x + 20
        enemy_fleet.y = home.y + 20
        enemy_fleet.save(update_fields=['x', 'y'])

        FleetOrders.objects.create(
            game=game,
            fleet=own_fleet,
            order_type='INTERCEPT',
            target_fleet=enemy_fleet,
            warpfactor=5,
        )

        builder = DetailBuilder(game, own_fleet.x, own_fleet.y, own_fleet.short_id, player)
        orders = builder.get_fleet_orders()

        self.assertEqual(len(orders), 1)
        self.assertEqual(
            orders[0]['target_link'],
            '?x=%s&y=%s&sel=%s&locate=1' % (home.x + 5, home.y + 4, enemy_fleet.short_id),
        )

    def test_refuel_targets_include_neutral_and_warmer_but_not_cold(self):
        game = default_game(stars=10, fleets=0)
        game.joinable = True
        game.save(update_fields=['joinable'])
        player = game.players.first()
        home = player.homeworld

        source_fleet = Fleet.objects.create(
            game=game,
            player=player,
            name='Source Fleet',
            x=home.x,
            y=home.y,
            basic_scanner_range=6,
        )
        own_target = Fleet.objects.create(
            game=game,
            player=player,
            name='Own Target',
            x=home.x,
            y=home.y,
        )

        def add_foreign_target(username, alias, stance):
            other_user = User.objects.create_user(
                username,
                '%s@test.com' % username,
                'pass',
            )
            other_account = Account.objects.create(
                django_user=other_user,
                alias=alias,
            )
            other_player = GameFactory(game).join_player(
                other_account,
                get_default_race(),
            )
            PlayerDiplomaticStance.objects.create(
                player=player,
                target_player=other_player,
                stance=stance,
            )
            return Fleet.objects.create(
                game=game,
                player=other_player,
                name='%s Fleet' % stance.title(),
                x=home.x,
                y=home.y,
            )

        neutral_fleet = add_foreign_target('refuel_neutral', 'RFN', 'NEUTRAL')
        warm_fleet = add_foreign_target('refuel_warm', 'RFW', 'WARM')
        allied_fleet = add_foreign_target('refuel_allied', 'RFA', 'ALLIED')
        cold_fleet = add_foreign_target('refuel_cold_turn', 'RFC', 'COLD')
        hostile_fleet = add_foreign_target('refuel_hostile', 'RFH', 'HOSTILE')

        builder = DetailBuilder(game, home.x, home.y, source_fleet.short_id, player)
        targets = builder.get_refuel_targets()['targets']
        target_ids = {target['short_id'] for target in targets}

        self.assertIn(own_target.short_id, target_ids)
        self.assertIn(neutral_fleet.short_id, target_ids)
        self.assertIn(warm_fleet.short_id, target_ids)
        self.assertIn(allied_fleet.short_id, target_ids)
        self.assertNotIn(cold_fleet.short_id, target_ids)
        self.assertNotIn(hostile_fleet.short_id, target_ids)

    def test_coordinate_selection_prefers_player_homeworld_star(self):
        game = default_game(stars=5, fleets=0)
        player = game.players.first()
        home = player.homeworld
        other_star = game.stars.exclude(pk=home.pk).first()
        other_star.x = home.x
        other_star.y = home.y
        other_star.save(update_fields=['x', 'y'])

        detail = DetailBuilder(
            game,
            x=home.x,
            y=home.y,
            selected=None,
            player=player,
        ).build_detail()

        self.assertEqual(detail['selected_id'], home.short_id)
        self.assertEqual(detail['name'], home.name)

    def test_get_actual_target_handles_cached_none_target_star(self):
        """Order target resolution should handle cached missing star relation."""
        game = default_game(stars=3)
        player = game.players.first()
        home = player.homeworld
        target = game.stars.exclude(pk=home.pk).first()

        fleet = Fleet.objects.create(
            game=game,
            player=player,
            name="Cached None Fleet",
            x=home.x,
            y=home.y,
        )
        order = FleetOrders.objects.create(
            game=game,
            fleet=fleet,
            order_type='MOVE',
            target_star=target,
            x=target.x,
            y=target.y,
            warpfactor=5,
        )

        # Simulate a stale related-object cache where FK id remains but object cache is None.
        order._target_star_cache = None
        obj, x, y, kind = order.get_actual_target()
        self.assertIsNone(obj)
        self.assertEqual(kind, 'space')
        self.assertEqual((x, y), (target.x, target.y))

    def test_get_actual_target_prefers_target_short_id_for_object(self):
        game = default_game(stars=3)
        player = game.players.first()
        home = player.homeworld
        target = game.stars.exclude(pk=home.pk).first()
        fleet = Fleet.objects.create(
            game=game, player=player, name="ShortId Fleet", x=home.x, y=home.y
        )
        order = FleetOrders.objects.create(
            game=game,
            fleet=fleet,
            order_type='MOVE',
            target_short_id=target.short_id,
            target_kind='OBJECT',
        )
        obj, x, y, kind = order.get_actual_target()
        self.assertEqual(kind, 'star')
        self.assertEqual(obj.id, target.id)
        self.assertEqual((x, y), (target.x, target.y))

    def test_get_actual_target_resolves_anomaly_short_id(self):
        game = default_game(stars=2, fleets=0)
        player = game.players.first()
        home = player.homeworld
        anomaly = Anomaly.objects.create(
            game=game, x=home.x + 2, y=home.y + 2, name='Spatial Rift'
        )
        fleet = Fleet.objects.create(
            game=game, player=player, name="Anomaly Scanner", x=home.x, y=home.y
        )
        order = FleetOrders.objects.create(
            game=game,
            fleet=fleet,
            order_type='MOVE',
            target_short_id=anomaly.short_id,
            target_kind='OBJECT',
        )
        obj, x, y, kind = order.get_actual_target()
        self.assertEqual(kind, 'anomaly')
        self.assertEqual(obj.id, anomaly.id)
        self.assertEqual((x, y), (anomaly.x, anomaly.y))

    def test_get_actual_target_converts_deleted_salvage_target_to_space_coordinates(self):
        game = default_game(stars=2, fleets=0)
        player = game.players.first()
        salvage = Salvage.objects.create(
            game=game,
            x=12,
            y=12,
            ironium_inventory=90,
            boranium_inventory=10,
            germanium_inventory=0,
        )
        fleet = Fleet.objects.create(
            game=game,
            player=player,
            name="Recovery Ship",
            x=12,
            y=12,
        )
        order = FleetOrders.objects.create(
            game=game,
            fleet=fleet,
            order_type='TRANSFER',
            transfer_type='LOAD',
            target_salvage=salvage,
            target_kind='OBJECT',
            target_short_id=salvage.short_id,
            x=salvage.x,
            y=salvage.y,
        )

        salvage.delete()
        order.refresh_from_db()

        obj, x, y, kind = order.get_actual_target()
        self.assertIsNone(obj)
        self.assertEqual(kind, 'space')
        self.assertEqual((x, y), (12, 12))

    def test_repeat_transfer_with_salvage_target_does_not_error(self):
        """Repeat transfer to salvage should not error when creating repeat order."""
        from ..models import FleetOrders, Salvage

        game = default_game()
        player = game.players.first()

        salvage = Salvage.objects.create(
            game=game, x=10, y=10,
            ironium_inventory=100, boranium_inventory=0, germanium_inventory=0
        )

        fleet = Fleet.objects.create(
            game=game, player=player, name="Salvager",
            x=10, y=10, ship_count=1, integrity=100
        )

        FleetOrders.objects.create(
            game=game, fleet=fleet, order_type='TRANSFER',
            repeat=True, transfer_type='LOAD', target_salvage=salvage
        )

        GameTurn(game).generate_turn()
        self.assertTrue(fleet.orders.filter(order_type='TRANSFER', repeat=True).exists())

    def test_repeat_move_with_empty_space_target_is_kept(self):
        """Repeat move to empty space should preserve repeat order."""
        from ..models import FleetOrders

        game = default_game()
        player = game.players.first()

        fleet = Fleet.objects.create(
            game=game, player=player, name="Explorer",
            x=1, y=1, ship_count=1, integrity=100
        )

        FleetOrders.objects.create(
            game=game, fleet=fleet, order_type='MOVE',
            repeat=True, x=0, y=0, warpfactor=3
        )

        GameTurn(game).generate_turn()
        self.assertTrue(fleet.orders.filter(order_type='MOVE', repeat=True).exists())

    def test_repeat_order_with_missing_target_is_discarded(self):
        """Repeat order with missing target should be discarded."""
        from ..models import FleetOrders, Star

        game = default_game(stars=2)
        player = game.players.first()
        star = game.stars.first()

        fleet = Fleet.objects.create(
            game=game, player=player, name="Scout",
            x=star.x, y=star.y, ship_count=1, integrity=100
        )

        order = FleetOrders.objects.create(
            game=game, fleet=fleet, order_type='MOVE',
            repeat=True, target_star=star, warpfactor=3
        )

        Star.objects.filter(id=star.id).delete()
        GameTurn(game).generate_turn()
        self.assertFalse(fleet.orders.filter(id=order.id).exists())
        self.assertFalse(fleet.orders.filter(order_type='MOVE', repeat=True).exists())


class TestFirstContactMessages(TestCase):
    def _create_two_player_game(self):
        get_default_race_type()
        user1 = User.objects.create_user('contact_p1', 'c1@test.com', 'pass')
        user2 = User.objects.create_user('contact_p2', 'c2@test.com', 'pass')
        account1 = Account.objects.create(django_user=user1)
        account2 = Account.objects.create(django_user=user2)

        factory = GameFactory()
        factory.set_map_size(100, 100)
        factory.set_owner(account1)
        factory.create_stars(5)
        game = factory.save()
        game.joinable = True
        game.save()
        player1 = factory.join_player(account1, get_default_race())
        player2 = factory.join_player(account2, get_default_race())
        player1.default_diplomatic_stance = 'HOSTILE'
        player2.default_diplomatic_stance = 'HOSTILE'
        player1.save(update_fields=['default_diplomatic_stance'])
        player2.save(update_fields=['default_diplomatic_stance'])
        return game, player1, player2

    def _create_scanner_fleet(
        self,
        game,
        player,
        x,
        y,
        basic_range,
        advanced_range,
        name='Watcher',
    ):
        return Fleet.objects.create(
            game=game,
            player=player,
            name=name,
            x=x,
            y=y,
            ship_count=1,
            integrity=100,
            basic_scanner_range=basic_range,
            advanced_scanner_range=advanced_range,
        )

    def test_first_contact_star_message(self):
        """First contact with an enemy star sends a diplomatic priority message."""
        game, player1, player2 = self._create_two_player_game()
        star = game.stars.exclude(player=player1).exclude(player__isnull=True).first()
        if not star:
            star = game.stars.exclude(player=player1).first()
            star.player = player2
            star.save()

        Fleet.objects.create(
            game=game, player=player1, name="Scout",
            x=star.x, y=star.y
        )

        GameTurn(game).generate_turn()
        msg = player1.messages.filter(category='DIPLOMATIC', priority=True).order_by('-id').first()
        self.assertIsNotNone(msg)

    def test_first_contact_fleet_message(self):
        """First contact with an enemy fleet sends a diplomatic priority message."""
        game, player1, player2 = self._create_two_player_game()
        x, y = 10, 10

        Fleet.objects.create(
            game=game, player=player1, name="Scout",
            x=x, y=y
        )
        Fleet.objects.create(
            game=game, player=player2, name="Stranger",
            x=x, y=y
        )

        GameTurn(game).generate_turn()
        msg = player1.messages.filter(category='DIPLOMATIC', priority=True).order_by('-id').first()
        self.assertIsNotNone(msg)

    def test_first_contact_copies_default_stance_into_new_entry(self):
        game, player1, player2 = self._create_two_player_game()
        player1.default_diplomatic_stance = 'WARM'
        player1.save(update_fields=['default_diplomatic_stance'])
        x, y = 10, 10

        Fleet.objects.create(
            game=game, player=player1, name="Scout",
            x=x, y=y
        )
        Fleet.objects.create(
            game=game, player=player2, name="Stranger",
            x=x, y=y
        )

        GameTurn(game).generate_turn()

        row = PlayerDiplomaticStance.objects.get(
            player=player1,
            target_player=player2,
        )
        self.assertEqual(row.stance, 'WARM')

    def test_in_situ_fleet_contact_does_not_repeat_first_contact_next_turn(self):
        game, player1, player2 = self._create_two_player_game()
        player1.default_diplomatic_stance = 'COLD'
        player1.save(update_fields=['default_diplomatic_stance'])
        x, y = 10, 10

        Fleet.objects.create(
            game=game, player=player1, name="Scout",
            x=x, y=y
        )
        Fleet.objects.create(
            game=game, player=player2, name="Stranger",
            x=x, y=y
        )

        GameTurn(game).generate_turn()
        GameTurn(game).generate_turn()

        self.assertEqual(
            player1.messages.filter(category='DIPLOMATIC', priority=True).count(),
            1,
        )
        row = PlayerDiplomaticStance.objects.get(
            player=player1,
            target_player=player2,
        )
        self.assertEqual(row.stance, 'COLD')

    def test_advanced_scanner_range_triggers_first_contact_message(self):
        """Advanced scanner intel should trigger first contact once ownership is known."""
        game, player1, player2 = self._create_two_player_game()
        enemy_fleet = Fleet.objects.create(
            game=game,
            player=player2,
            name="Stranger",
            x=20,
            y=20,
            ship_count=1,
            integrity=100,
        )
        self._create_scanner_fleet(
            game,
            player1,
            x=14,
            y=20,
            basic_range=6,
            advanced_range=6,
        )

        GameTurn(game).generate_scanner_reports()

        messages = player1.messages.filter(category='DIPLOMATIC', priority=True)
        self.assertEqual(messages.count(), 1)
        self.assertIn(player2.name, messages.first().message)
        self.assertEqual(
            player2.messages.filter(category='DIPLOMATIC', priority=True).count(),
            0,
        )
        report = Report.objects.get(
            player=player1,
            target_type='fleet',
            target_id=enemy_fleet.id,
        )
        self.assertEqual(report.get_report_data().get('player_name'), player2.name)

    def test_basic_scanner_range_does_not_trigger_first_contact_message(self):
        """Basic scanner intel should not trigger first contact without ownership."""
        game, player1, player2 = self._create_two_player_game()
        enemy_fleet = Fleet.objects.create(
            game=game,
            player=player2,
            name="Stranger",
            x=20,
            y=20,
            ship_count=1,
            integrity=100,
        )
        self._create_scanner_fleet(
            game,
            player1,
            x=14,
            y=20,
            basic_range=6,
            advanced_range=0,
        )

        GameTurn(game).generate_scanner_reports()

        self.assertFalse(
            player1.messages.filter(category='DIPLOMATIC', priority=True).exists()
        )
        report = Report.objects.get(
            player=player1,
            target_type='fleet',
            target_id=enemy_fleet.id,
        )
        self.assertEqual(report.get_report_data().get('report_tier'), 'basic')
        self.assertIsNone(report.get_report_data().get('player_name'))

    def test_scanner_first_contact_only_fires_once_per_race(self):
        """Star and fleet reports in the same scan should still only message once."""
        game, player1, player2 = self._create_two_player_game()
        enemy_star = player2.homeworld
        enemy_star.x = 20
        enemy_star.y = 20
        enemy_star.save(update_fields=['x', 'y'])
        Fleet.objects.create(
            game=game,
            player=player2,
            name="Stranger",
            x=20,
            y=20,
            ship_count=1,
            integrity=100,
        )
        self._create_scanner_fleet(
            game,
            player1,
            x=14,
            y=20,
            basic_range=6,
            advanced_range=6,
        )

        GameTurn(game).generate_scanner_reports()

        self.assertEqual(
            player1.messages.filter(category='DIPLOMATIC', priority=True).count(),
            1,
        )

    def test_scanner_first_contact_is_not_repeated_by_later_encounter(self):
        """Once ownership is known, later encounters should not resend first contact."""
        game, player1, player2 = self._create_two_player_game()
        enemy_fleet = Fleet.objects.create(
            game=game,
            player=player2,
            name="Stranger",
            x=20,
            y=20,
            ship_count=1,
            integrity=100,
        )
        scout = self._create_scanner_fleet(
            game,
            player1,
            x=14,
            y=20,
            basic_range=6,
            advanced_range=6,
        )

        GameTurn(game).generate_scanner_reports()
        scout.x = enemy_fleet.x
        scout.y = enemy_fleet.y
        scout.save(update_fields=['x', 'y'])

        GameTurn(game).first_contact_checks()

        self.assertEqual(
            player1.messages.filter(category='DIPLOMATIC', priority=True).count(),
            1,
        )


class TestHabitableWorldMessages(TestCase):
    def test_habitable_world_message_once(self):
        """Habitable world message should only fire on first report."""
        game = default_game(stars=1)
        player = game.players.first()
        star = game.stars.first()
        star.gravity = 1.0
        star.temperature = 1.0
        star.radiation = 1.0
        star.player = None
        star.save()

        Fleet.objects.create(
            game=game, player=player, name="Scout",
            x=star.x, y=star.y
        )

        GameTurn(game).generate_turn()
        count_after_first = player.messages.filter(category='ENVIRONMENTAL').count()
        self.assertGreater(count_after_first, 0)

        GameTurn(game).generate_turn()
        count_after_second = player.messages.filter(category='ENVIRONMENTAL').count()
        self.assertEqual(count_after_first, count_after_second)


class TestFleetOrdersRepeat(TestCase):
    """Test fleet order repeat functionality."""

    def test_repeat_order_requeued_on_completion(self):
        """When a fleet completes a repeat order, it should be requeued at bottom."""
        game = default_game(stars=10, fleets=1)
        player = game.players.first()
        fleet = game.fleets.first()

        # Position fleet at 0,0 and create order to move to 5,5 (distance=~7) with repeat=True
        fleet.x = 0
        fleet.y = 0
        fleet.max_safe_warp = 13  # Prevent warp damage
        fleet.save()

        from ..models import FleetOrders
        order = FleetOrders.objects.create(
            game=game,
            fleet=fleet,
            warpfactor=10,  # Fast enough to complete in one turn
            x=5,
            y=5,
            repeat=True
        )

        # Verify fleet has one order before turn
        self.assertEqual(fleet.orders.count(), 1)
        original_order_id = order.id

        # Generate turn - should complete movement and requeue order
        GameTurn(game).generate_turn()

        # Refresh fleet and check position
        fleet.refresh_from_db()
        self.assertEqual(fleet.x, 5)
        self.assertEqual(fleet.y, 5)

        # Original order should be deleted, new order should exist
        self.assertFalse(FleetOrders.objects.filter(id=original_order_id).exists())
        self.assertEqual(fleet.orders.count(), 1)

        # New order should have same properties
        new_order = fleet.orders.first()
        self.assertEqual(new_order.warpfactor, 10)
        self.assertEqual(new_order.x, 5)
        self.assertEqual(new_order.y, 5)
        self.assertTrue(new_order.repeat)
        self.assertNotEqual(new_order.id, original_order_id)

    def test_non_repeat_order_deleted_on_completion(self):
        """When a fleet completes a non-repeat order, it should be deleted."""
        game = default_game(stars=10, fleets=1)
        player = game.players.first()
        fleet = game.fleets.first()

        # Position fleet and create non-repeat order
        fleet.x = 0
        fleet.y = 0
        fleet.max_safe_warp = 13  # Prevent warp damage
        fleet.save()

        from ..models import FleetOrders
        order = FleetOrders.objects.create(
            game=game,
            fleet=fleet,
            warpfactor=10,
            x=5,
            y=5,
            repeat=False
        )

        # Verify fleet has one order
        self.assertEqual(fleet.orders.count(), 1)

        # Generate turn
        GameTurn(game).generate_turn()

        # Fleet should be at destination, order should be gone
        fleet.refresh_from_db()
        self.assertEqual(fleet.x, 5)
        self.assertEqual(fleet.y, 5)
        self.assertEqual(fleet.orders.count(), 0)

    def test_repeat_order_with_target_star(self):
        """Repeat orders with target_star should preserve the star reference."""
        game = default_game(stars=10, fleets=1)
        player = game.players.first()
        fleet = game.fleets.first()
        target_star = game.stars.exclude(pk=player.homeworld.pk).first()

        # Position fleet close to target
        fleet.x = target_star.x - 3  # 3 units away
        fleet.y = target_star.y
        fleet.save()

        from ..models import FleetOrders
        order = FleetOrders.objects.create(
            game=game,
            fleet=fleet,
            warpfactor=5,
            target_star=target_star,
            repeat=True
        )

        # Generate turn
        GameTurn(game).generate_turn()

        # Fleet should be at star, order should be requeued
        fleet.refresh_from_db()
        self.assertEqual(fleet.x, target_star.x)
        self.assertEqual(fleet.y, target_star.y)
        self.assertEqual(fleet.orders.count(), 1)

        # New order should reference same star
        new_order = fleet.orders.first()
        self.assertEqual(new_order.target_star, target_star)
        self.assertTrue(new_order.repeat)

    def test_partial_movement_no_repeat(self):
        """Orders not completed should not be repeated, even if repeat=True."""
        game = default_game(stars=10, fleets=1)
        player = game.players.first()
        fleet = game.fleets.first()

        # Position fleet far from target
        fleet.x = 1
        fleet.y = 1
        fleet.save()

        from ..models import FleetOrders
        order = FleetOrders.objects.create(
            game=game,
            fleet=fleet,
            warpfactor=5,  # Not fast enough to reach in one turn
            x=20,
            y=20,
            repeat=True
        )
        original_order_id = order.id

        # Generate turn
        GameTurn(game).generate_turn()

        # Fleet should have moved but not completed journey
        fleet.refresh_from_db()
        self.assertNotEqual((fleet.x, fleet.y), (20, 20))  # Hasn't reached destination
        self.assertNotEqual((fleet.x, fleet.y), (1, 1))    # But has moved

        # Original order should still exist (not completed)
        self.assertTrue(FleetOrders.objects.filter(id=original_order_id).exists())
        self.assertEqual(fleet.orders.count(), 1)


class TestShortIdCollisionDetection(TestCase):
    """Test XOR-based short_id generation."""

    def test_deterministic_generation(self):
        """XOR-based short_id generation should be deterministic and collision-resistant."""
        game = default_game()
        player = game.players.first()

        # Create multiple messages - should all have unique short_ids due to XOR entropy
        messages = []
        for i in range(10):
            msg = GameMessage.objects.create(
                game=game,
                player=player,
                message=f"Test message {i}",
                year=2400
            )
            messages.append(msg)

        # All should have unique short_ids (very high probability with XOR approach)
        short_ids = [msg.short_id for msg in messages]
        self.assertEqual(len(short_ids), len(set(short_ids)), "All short_ids should be unique")

        # All should be exactly 12 characters (4 game + 8 XOR)
        for short_id in short_ids:
            self.assertEqual(len(short_id), 12, f"short_id '{short_id}' should be exactly 12 chars")
            # Should start with game prefix
            self.assertTrue(short_id.startswith(game.short_id[:4]))

    def test_short_id_unchanged_on_resave(self):
        """Resaving an existing object should not change its short_id."""
        game = default_game()
        player = game.players.first()

        msg = GameMessage.objects.create(
            game=game,
            player=player,
            message="Original message",
            year=2400
        )
        original_short_id = msg.short_id

        # Modify and save
        msg.message = "Updated message"
        msg.save()

        # short_id should be unchanged
        self.assertEqual(msg.short_id, original_short_id)

    def test_same_uuid_produces_same_short_id(self):
        """Same UUID should always produce the same short_id (deterministic)."""
        from ..models import GameMessage
        import uuid

        game = default_game()
        player = game.players.first()

        # Create a UUID and use it twice
        test_uuid = uuid.UUID('01234567-89ab-cdef-0123-456789abcdef')

        # Create first message with specific UUID
        msg1 = GameMessage(
            id=test_uuid,
            game=game,
            player=player,
            message="First message",
            year=2400
        )
        msg1.save()

        # Create second message with same UUID in different instance
        msg2 = GameMessage(
            id=test_uuid,
            game=game,
            player=player,
            message="Second message",
            year=2401
        )
        # Manually generate short_id to test determinism
        expected_short_id = msg2._generate_short_id_from_uuid(test_uuid.int)

        # Should be identical
        self.assertEqual(msg1.short_id, expected_short_id)

    def test_different_games_different_prefixes(self):
        """Objects in different games should have different short_id prefixes."""
        from ..models import GameMessage

        game1 = default_game()
        game2 = default_game()  # Different game

        player1 = game1.players.first()
        player2 = game2.players.first()

        msg1 = GameMessage.objects.create(
            game=game1,
            player=player1,
            message="Message in game 1",
            year=2400
        )

        msg2 = GameMessage.objects.create(
            game=game2,
            player=player2,
            message="Message in game 2",
            year=2400
        )

        # Should have different prefixes (first 4 characters)
        self.assertNotEqual(msg1.short_id[:4], msg2.short_id[:4])
        self.assertEqual(msg1.short_id[:4], game1.short_id[:4])
        self.assertEqual(msg2.short_id[:4], game2.short_id[:4])


class TestGameDisplayMethods(TestCase):
    """Test Game model display methods."""

    def test_get_turn_scheme_short_display_with_description(self):
        """Turn scheme with description should return only the short part."""
        game = default_game()

        # Test schemes with descriptions
        game.turn_scheme = 'QUORUM'
        game.save()
        self.assertEqual(game.get_turn_scheme_short_display(), 'Quorum')

        game.turn_scheme = 'OWNER'
        game.save()
        self.assertEqual(game.get_turn_scheme_short_display(), 'Owner')

    def test_get_turn_scheme_short_display_without_description(self):
        """Turn scheme without description should return the full display."""
        game = default_game()

        # Test schemes without descriptions
        game.turn_scheme = 'HOURLY'
        game.save()
        self.assertEqual(game.get_turn_scheme_short_display(), 'Hourly')

        game.turn_scheme = 'DAILY'
        game.save()
        self.assertEqual(game.get_turn_scheme_short_display(), 'Daily')

        game.turn_scheme = 'WEEKLY'
        game.save()
        self.assertEqual(game.get_turn_scheme_short_display(), 'Weekly')


class TestFleetCargo(TestCase):
    """Test Fleet cargo capacity and inventory."""

    def test_default_cargo_capacity(self):
        """New fleets should have 100kt cargo capacity and empty inventory."""
        game = default_game()
        player = game.players.first()

        fleet = Fleet.objects.create(
            game=game,
            player=player,
            name="Test Fleet",
            x=5,
            y=5
        )

        self.assertEqual(fleet.cargo_capacity, 100)
        self.assertEqual(fleet.ironium_inventory, 0)
        self.assertEqual(fleet.boranium_inventory, 0)
        self.assertEqual(fleet.germanium_inventory, 0)
        self.assertEqual(fleet.colonists, 0)
        self.assertEqual(fleet.fuel, 50.0)
        self.assertEqual(fleet.max_fuel, 50.0)

    def test_cargo_calculations(self):
        """Test cargo_used and cargo_remaining properties."""
        game = default_game()
        player = game.players.first()

        fleet = Fleet.objects.create(
            game=game,
            player=player,
            name="Test Fleet",
            x=5,
            y=5,
            cargo_capacity=1000,
            ironium_inventory=100,
            boranium_inventory=200,
            germanium_inventory=300,
            colonists=400
        )

        # Total cargo used: 100 + 200 + 300 + 400 = 1,000kt
        self.assertEqual(fleet.cargo_used, 1000)
        # Remaining: 1,000 - 1,000 = 0kt (full)
        self.assertEqual(fleet.cargo_remaining, 0)

    def test_cargo_used_includes_secret_resources(self):
        """Secret resources should contribute to cargo usage."""
        game = default_game()
        player = game.players.first()

        fleet = Fleet.objects.create(
            game=game,
            player=player,
            name="Secret Cargo",
            x=5,
            y=5,
            cargo_capacity=1000,
            ironium_inventory=100,
            resource_x_inventory=200,
            resource_y_inventory=50,
            colonists=25
        )

        self.assertEqual(fleet.cargo_used, 375)
        self.assertEqual(fleet.cargo_remaining, 625)

    def test_full_cargo_capacity(self):
        """Test fleet at maximum capacity."""
        game = default_game()
        player = game.players.first()

        fleet = Fleet.objects.create(
            game=game,
            player=player,
            name="Full Fleet",
            x=5,
            y=5,
            cargo_capacity=1000,
            colonists=1000  # Full capacity with colonists only
        )

        self.assertEqual(fleet.cargo_used, 1000)
        self.assertEqual(fleet.cargo_remaining, 0)

    def test_mixed_cargo(self):
        """Test mixed cargo types respecting 1 colonist = 1kt equivalence."""
        game = default_game()
        player = game.players.first()

        fleet = Fleet.objects.create(
            game=game,
            player=player,
            name="Mixed Fleet",
            x=5,
            y=5,
            cargo_capacity=1000,
            ironium_inventory=250,   # 250kt ironium
            boranium_inventory=250,  # 250kt boranium
            germanium_inventory=250, # 250kt germanium
            colonists=250            # 250k colonists = 250kt equivalent
        )

        # Total: 1,000kt exactly at capacity
        self.assertEqual(fleet.cargo_used, 1000)
        self.assertEqual(fleet.cargo_remaining, 0)

    def test_object_details_includes_fleet_cargo(self):
        """Test that fleet cargo information is included in object details."""
        from ..objectdetails import DetailBuilder

        game = default_game()
        player = game.players.first()

        fleet = Fleet.objects.create(
            game=game,
            player=player,
            name="Cargo Fleet",
            x=10,
            y=10,
            cargo_capacity=1000,
            ironium_inventory=500,
            boranium_inventory=300,
            germanium_inventory=150,
            colonists=50,
            warp_advantage=0.9,
        )

        # Build details for the fleet (note: process_selected converts to lowercase)
        detail_builder = DetailBuilder(game, x=10, y=10, selected=fleet.short_id.lower(), player=player)
        details = detail_builder.build_detail()

        self.assertIsNotNone(details)
        self.assertTrue(details['is_fleet'])
        self.assertIsNotNone(details['fleet_cargo'])
        self.assertIsNotNone(details['fleet_inventory'])

        # Test cargo info
        cargo_info = details['fleet_cargo']
        self.assertEqual(cargo_info['capacity'], 1000)
        self.assertEqual(cargo_info['used'], 1000)  # 500+300+150+50
        self.assertEqual(cargo_info['remaining'], 0)  # 1000-1000
        self.assertEqual(cargo_info['ironium'], 500)
        self.assertEqual(cargo_info['boranium'], 300)
        self.assertEqual(cargo_info['germanium'], 150)
        self.assertEqual(cargo_info['colonists'], 50)
        self.assertEqual(cargo_info['fuel'], 50.0)
        self.assertEqual(cargo_info['max_fuel'], 50.0)
        self.assertEqual(cargo_info['offense_modifier'], '+0')
        self.assertEqual(cargo_info['defense_modifier'], '+0')
        self.assertIsNotNone(details['fleet_capabilities'])
        self.assertIn(
            {'label': 'Max Warp', 'value': '2 +0.9'},
            details['fleet_capabilities'],
        )

        # Test inventory display data
        inventory = details['fleet_inventory']
        self.assertEqual(inventory['fuel']['amount'], 50.0)
        self.assertEqual(inventory['fuel']['percent'], 100.0)
        self.assertEqual(inventory['fuel']['display'], '50.0mg')
        self.assertEqual(inventory['ironium']['amount'], 500)
        self.assertEqual(inventory['ironium']['percent'], 50.0)  # 500/1000 = 50%
        self.assertEqual(inventory['ironium']['display'], '500kt')

        self.assertEqual(inventory['boranium']['amount'], 300)
        self.assertEqual(inventory['boranium']['percent'], 30.0)  # 300/1000 = 30%
        self.assertEqual(inventory['boranium']['display'], '300kt')

        self.assertEqual(inventory['germanium']['amount'], 150)
        self.assertEqual(inventory['germanium']['percent'], 15.0)  # 150/1000 = 15%
        self.assertEqual(inventory['germanium']['display'], '150kt')
        self.assertEqual(inventory['colonists']['amount'], 50)
        self.assertEqual(inventory['colonists']['percent'], 5.0)  # 50/1000 = 5%
        self.assertEqual(inventory['colonists']['display'], '50k')

    def test_owned_fleet_scanner_range_shows_race_scan_multiplier_suffix(self):
        game = default_game(stars=2)
        player = game.players.first()
        player.race_type.scan_multiplier = 1.2
        player.race_type.save(update_fields=['scan_multiplier'])

        fleet = Fleet.objects.create(
            game=game,
            player=player,
            name='Scanner Fleet',
            x=10,
            y=10,
            ship_count=1,
            integrity=100,
            max_safe_warp=5,
            basic_scanner_range=6,
            advanced_scanner_range=2,
        )

        detail_builder = DetailBuilder(game, x=10, y=10, selected=fleet.short_id.lower(), player=player)
        details = detail_builder.build_detail()

        self.assertIn(
            {'label': 'Scanner Range', 'value': '6ly/2ly (+20%)'},
            details['fleet_capabilities'],
        )

    def test_object_details_fleet_composition_includes_tech_modifiers(self):
        from ..objectdetails import DetailBuilder

        game = default_game()
        player = game.players.first()

        fleet = Fleet.objects.create(
            game=game,
            player=player,
            name="Combat Fleet",
            x=8,
            y=8,
            ship_count=12,
            integrity=91,
            offense_level=1.1,
            defense_level=-0.4,
        )

        detail_builder = DetailBuilder(
            game, x=8, y=8, selected=fleet.short_id.lower(), player=player
        )
        details = detail_builder.build_detail()

        self.assertIsNotNone(details)
        self.assertEqual(details['fleet_cargo']['offense_modifier'], '+11')
        self.assertEqual(details['fleet_cargo']['defense_modifier'], '-4')

    def test_object_details_includes_star_mining_rates_for_owned_colony(self):
        """Owned colonies should include per-resource mining rates."""
        from ..objectdetails import DetailBuilder

        game = default_game()
        player = game.players.first()
        star = player.homeworld

        star.mines = 10
        star.factories = 0
        star.defenses = 0
        star.shipyards = 0
        star.colonists = 10000
        star.ironium_yield = 50
        star.boranium_yield = 30
        star.germanium_yield = 20
        star.save()

        detail_builder = DetailBuilder(
            game,
            x=star.x,
            y=star.y,
            selected=star.short_id.lower(),
            player=player,
        )
        details = detail_builder.build_detail()
        resources = details['resources']

        iron_rate = resources['ironium']['mining_rate']
        bor_rate = resources['boranium']['mining_rate']
        germ_rate = resources['germanium']['mining_rate']
        total_rate = iron_rate + bor_rate + germ_rate
        self.assertGreater(total_rate, 0)
        self.assertLessEqual(total_rate, star.mines * KT_PER_MINE)
        self.assertGreater(iron_rate, bor_rate)
        self.assertGreater(bor_rate, germ_rate)

    def test_object_details_includes_star_thumbnail(self):
        from ..objectdetails import DetailBuilder

        game = default_game()
        player = game.players.first()
        star = player.homeworld

        detail_builder = DetailBuilder(
            game,
            x=star.x,
            y=star.y,
            selected=star.short_id.lower(),
            player=player,
        )
        details = detail_builder.build_detail()
        self.assertIsNotNone(details)
        self.assertTrue(details['is_star'])
        self.assertIn('star_thumbnail', details)
        self.assertTrue(details['star_thumbnail'].startswith('dj4xol/images/thumbs/star/all/'))

    def test_object_details_includes_anomaly_thumbnail(self):
        from ..objectdetails import DetailBuilder
        from ..models import Anomaly

        game = default_game()
        player = game.players.first()
        anomaly = Anomaly.objects.create(
            game=game,
            name="Test Rift",
            x=5,
            y=6,
            anomaly_type=Anomaly.TYPE_RIFT,
        )
        Fleet.objects.create(
            game=game,
            player=player,
            name="Scout",
            x=anomaly.x,
            y=anomaly.y,
        )

        detail_builder = DetailBuilder(
            game,
            x=anomaly.x,
            y=anomaly.y,
            selected=anomaly.short_id.lower(),
            player=player,
        )
        details = detail_builder.build_detail()
        self.assertIsNotNone(details)
        self.assertTrue(details['is_anomaly'])
        self.assertIn('anomaly_thumbnail', details)
        self.assertTrue(details['anomaly_thumbnail'].startswith('dj4xol/images/thumbs/anomaly/'))

    def test_anomaly_assigns_thumbnail_when_missing(self):
        from ..models import Anomaly

        game = default_game()
        anomaly = Anomaly.objects.create(
            game=game,
            name="Random Anomaly",
            x=2,
            y=3,
            anomaly_type=Anomaly.TYPE_COMET,
        )
        self.assertTrue(anomaly.thumbnail_path)
        self.assertTrue(anomaly.thumbnail_path.startswith('dj4xol/images/thumbs/anomaly/'))

    def test_invalid_thumbnails_fallback_to_class(self):
        from ..models import Anomaly, Fleet

        game = default_game()
        player = game.players.first()

        fleet = Fleet.objects.create(
            game=game,
            player=player,
            name="Broken Thumb",
            x=1,
            y=1,
            thumbnail_path="dj4xol/images/thumbs/ship/scout/missing.png",
        )
        fleet_thumb = fleet.effective_thumbnail_path
        self.assertTrue(fleet_thumb.startswith('dj4xol/images/thumbs/ship/scout/'))

        anomaly = Anomaly.objects.create(
            game=game,
            name="Missing Nebula",
            x=3,
            y=4,
            anomaly_type=Anomaly.TYPE_NEBULA,
            thumbnail_path="dj4xol/images/thumbs/anomaly/nebula/missing.png",
        )
        anomaly_thumb = anomaly.effective_thumbnail_path
        self.assertTrue(anomaly_thumb.startswith('dj4xol/images/thumbs/anomaly/nebula/'))


class TestProductionProgress(TestCase):
    """Test production order progress calculations."""

    def test_new_production_order_zero_progress(self):
        """Test that newly created production orders show 0% progress."""
        from ..objectdetails import DetailBuilder
        from ..models import ProductionOrder, Star

        game = default_game()
        player = game.players.first()

        star = Star.objects.create(
            game=game,
            player=player,
            name="Test Star",
            x=10,
            y=10,
            colonists=10000,
        )

        # Create new production order with no spending (defaults)
        order = ProductionOrder.objects.create(
            game=game,
            star=star,
            order_type='BUILD_DEFENSE',
            quantity=1
            # All spent_* fields default to 0
        )

        detail_builder = DetailBuilder(game, x=10, y=10, selected=star.short_id.lower(), player=player)
        details = detail_builder.build_detail()

        production_order = details['production_orders'][0]

        # Should show 0% progress for new order
        self.assertEqual(production_order['progress_percent'], 0)
        self.assertEqual(production_order['resource_progress'], 0)
        self.assertEqual(production_order['labor_progress'], 0)

    def test_labor_only_progress(self):
        """Test progress for items that only require BP (no resources)."""
        from ..objectdetails import DetailBuilder
        from ..models import ProductionOrder, Star

        game = default_game()
        player = game.players.first()

        # Create a colonized star
        star = Star.objects.create(
            game=game,
            player=player,
            name="Test Star",
            x=10,
            y=10,
            colonists=10000,
        )

        # Create production order for BUILD_DEFENSE.
        # During turn generation, 10 BP has been allocated.
        order = ProductionOrder.objects.create(
            game=game,
            star=star,
            order_type='BUILD_DEFENSE',
            quantity=1,
            spent_bp=10,
            spent_ironium=100,  # Full ironium (simulates turn generation)
            spent_boranium=50,  # Full boranium
            spent_germanium=50  # Full germanium (total 200/200 = 100% of resources)
        )

        detail_builder = DetailBuilder(game, x=10, y=10, selected=star.short_id.lower(), player=player)
        details = detail_builder.build_detail()

        production_order = details['production_orders'][0]

        # Should have dual progress: resources 50% + labor contribution based on BP cost.
        labor_expected = int((10.0 / 50.0) * 50.0)
        self.assertEqual(production_order['has_labor'], True)
        self.assertEqual(production_order['resource_progress'], 50)  # All resources complete = 50%
        self.assertEqual(production_order['labor_progress'], labor_expected)
        self.assertEqual(production_order['progress_percent'], 50 + labor_expected)

    def test_colonist_labor_progress_counts_towards_partial_mine_construction(self):
        """Colonist-built mine orders should show partial labor progress."""
        from ..objectdetails import DetailBuilder
        from ..models import ProductionOrder, Star

        game = default_game()
        player = game.players.first()

        star = Star.objects.create(
            game=game,
            player=player,
            name="Colonist Progress Star",
            x=10,
            y=10,
            colonists=1500,
            mines=1,
        )

        ProductionOrder.objects.create(
            game=game,
            star=star,
            order_type='BUILD_MINE',
            quantity=1,
            spent_bp=500,
            spent_ironium=10,
        )

        detail_builder = DetailBuilder(
            game, x=10, y=10, selected=star.short_id.lower(), player=player
        )
        details = detail_builder.build_detail()
        production_order = details['production_orders'][0]

        self.assertEqual(production_order['has_labor'], True)
        self.assertEqual(production_order['resource_progress'], 50)
        self.assertEqual(production_order['labor_progress'], 25)
        self.assertEqual(production_order['progress_percent'], 75)

    def test_resource_only_progress(self):
        """Test progress for items that require both BP and resources."""
        from ..objectdetails import DetailBuilder
        from ..models import ProductionOrder, Star

        game = default_game()
        player = game.players.first()

        star = Star.objects.create(
            game=game,
            player=player,
            name="Test Star",
            x=10,
            y=10,
            colonists=10000,
        )

        # Create TERRAFORM_GRAVITY order using the current 50 BP / 500 total
        # mineral cost profile, then mark half of each side as spent.
        order = ProductionOrder.objects.create(
            game=game,
            star=star,
            order_type='TERRAFORM_GRAVITY',
            quantity=1,
            spent_bp=25,
            spent_ironium=175,
            spent_boranium=50,
            spent_germanium=25,
        )

        detail_builder = DetailBuilder(game, x=10, y=10, selected=star.short_id.lower(), player=player)
        details = detail_builder.build_detail()

        production_order = details['production_orders'][0]

        # Should have dual progress: resources 25% + labor 25% = 50%
        self.assertEqual(production_order['has_labor'], True)
        self.assertEqual(production_order['resource_progress'], 25)
        self.assertEqual(production_order['labor_progress'], 25)
        self.assertEqual(production_order['progress_percent'], 50)

    def test_resources_blocked_by_labor(self):
        """Test that resources show actual progress based on what was spent during turn generation."""
        from ..objectdetails import DetailBuilder
        from ..models import ProductionOrder, Star

        game = default_game()
        player = game.players.first()

        star = Star.objects.create(
            game=game,
            player=player,
            name="Test Star",
            x=10,
            y=10,
            colonists=10000,
        )

        # BUILD_DEFENSE with no BP spent and no resources allocated
        # This simulates what would happen if turn generation hadn't allocated anything yet
        order = ProductionOrder.objects.create(
            game=game,
            star=star,
            order_type='BUILD_DEFENSE',
            quantity=1,
            spent_bp=0,         # No BP allocated during turn generation
            spent_ironium=0,    # No resources allocated during turn generation
            spent_boranium=0,
            spent_germanium=0
        )

        detail_builder = DetailBuilder(game, x=10, y=10, selected=star.short_id.lower(), player=player)
        details = detail_builder.build_detail()

        production_order = details['production_orders'][0]

        # Should show no progress because nothing was allocated during turn generation
        self.assertEqual(production_order['resource_progress'], 0)   # No resources allocated
        self.assertEqual(production_order['labor_progress'], 0)      # No BP allocated
        self.assertEqual(production_order['progress_percent'], 0)    # No progress


class TestProductionRollupMessages(TestCase):
    def test_sends_single_rollup_message_per_star(self):
        game = default_game()
        player = game.players.first()
        star = player.homeworld

        turn = GameTurn(game)
        counts = {
            'mine': 3,
            'factory': 2,
            'lab': 1,
            'defense': 4,
            'shipyard': 1,
        }
        before = player.messages.count()
        turn._send_production_summary_messages(star, counts)

        self.assertEqual(player.messages.count(), before + 1)
        msg = player.messages.order_by('-id').first()
        self.assertIn('production', msg.message.lower())
        self.assertIn('3 mines', msg.message)
        self.assertIn('2 factories', msg.message)
        self.assertIn('1 lab', msg.message)
        self.assertIn('4 defenses', msg.message)
        self.assertIn('1 shipyard', msg.message)

    def test_no_rollup_when_nothing_completed(self):
        game = default_game()
        player = game.players.first()
        star = player.homeworld

        turn = GameTurn(game)
        before = player.messages.count()
        turn._send_production_summary_messages(star, {
            'mine': 0,
            'factory': 0,
            'lab': 0,
            'defense': 0,
            'shipyard': 0,
        })
        self.assertEqual(player.messages.count(), before)

    def test_sends_queue_completed_message_when_orders_become_empty(self):
        game = default_game()
        player = game.players.first()
        star = player.homeworld
        star.production_orders.all().delete()
        star.ironium_inventory = max(star.ironium_inventory, 100)
        star.save(update_fields=['ironium_inventory'])

        ProductionOrder.objects.create(
            game=game,
            star=star,
            order_type='BUILD_MINE',
            quantity=1,
            position=1,
            repeat=False,
        )

        before = player.messages.count()
        GameTurn(game).production()
        self.assertGreater(player.messages.count(), before)

        messages = list(player.messages.order_by('-id').values_list('message', flat=True))
        self.assertTrue(any(
            ('production queue' in m.lower()) or ('queued production orders' in m.lower())
            for m in messages
        ))

    def test_does_not_send_queue_completed_message_for_repeat_orders(self):
        game = default_game()
        player = game.players.first()
        star = player.homeworld
        star.production_orders.all().delete()
        star.ironium_inventory = max(star.ironium_inventory, 100)
        star.save(update_fields=['ironium_inventory'])

        ProductionOrder.objects.create(
            game=game,
            star=star,
            order_type='BUILD_MINE',
            quantity=1,
            position=1,
            repeat=True,
        )

        GameTurn(game).production()
        messages = list(player.messages.values_list('message', flat=True))
        self.assertFalse(any(
            ('production queue' in m.lower()) or ('queued production orders' in m.lower())
            for m in messages
        ))


class TestFleetTransferOrders(TestCase):
    """Test fleet transfer order functionality."""

    def test_resource_to_world_contract_fulfills_oldest_first(self):
        game = default_game(stars=8, fleets=0)
        player1 = game.players.first()
        game.joinable = True
        game.save(update_fields=['joinable'])
        other_user = User.objects.create_user('contract_transfer_user', 'contract_transfer@test.com', 'pass')
        other_account = Account.objects.create(django_user=other_user, alias='CTR')
        player2 = GameFactory(game).join_player(other_account, get_default_race())

        contract_old = DiplomaticContract.objects.create(
            game=game,
            sender=player1,
            recipient=player2,
            temperature='REQUEST',
            status='ACCEPTED',
            sent_year=game.year,
            accepted_year=game.year,
            expires_year=game.year + 24,
            request_clause_type='RESOURCE_TO_WORLD',
            request_ironium=3,
            offer_clause_type='NOTHING',
        )
        contract_new = DiplomaticContract.objects.create(
            game=game,
            sender=player1,
            recipient=player2,
            temperature='REQUEST',
            status='ACCEPTED',
            sent_year=game.year,
            accepted_year=game.year,
            expires_year=game.year + 24,
            request_clause_type='RESOURCE_TO_WORLD',
            request_ironium=4,
            offer_clause_type='NOTHING',
        )

        fleet = Fleet.objects.create(
            game=game,
            player=player2,
            name='Contract Hauler',
            x=player1.homeworld.x,
            y=player1.homeworld.y,
            cargo_capacity=20,
            ironium_inventory=5,
        )
        FleetOrders.objects.create(
            game=game,
            fleet=fleet,
            order_type='TRANSFER',
            target_star=player1.homeworld,
            transfer_type='UNLOAD',
            transfer_ironium=5,
        )

        GameTurn(game).generate_turn()

        contract_old.refresh_from_db()
        contract_new.refresh_from_db()
        self.assertEqual(contract_old.status, DiplomaticContract.STATUS_FULFILLED)
        self.assertEqual(contract_new.status, DiplomaticContract.STATUS_ACCEPTED)
        self.assertEqual(contract_new.progress_ironium, 2)

    def test_fleet_give_contract_fulfills_oldest_first(self):
        game = default_game(stars=8, fleets=0)
        player1 = game.players.first()
        game.joinable = True
        game.save(update_fields=['joinable'])
        other_user = User.objects.create_user('contract_give_user', 'contract_give@test.com', 'pass')
        other_account = Account.objects.create(django_user=other_user, alias='CTG')
        player2 = GameFactory(game).join_player(other_account, get_default_race())

        contract_old = DiplomaticContract.objects.create(
            game=game,
            sender=player1,
            recipient=player2,
            temperature='REQUEST',
            status='ACCEPTED',
            sent_year=game.year,
            accepted_year=game.year,
            expires_year=game.year + 24,
            request_clause_type='FLEET_BY_SHIP_COUNT',
            request_ship_count=2,
            offer_clause_type='NOTHING',
        )
        contract_new = DiplomaticContract.objects.create(
            game=game,
            sender=player1,
            recipient=player2,
            temperature='REQUEST',
            status='ACCEPTED',
            sent_year=game.year,
            accepted_year=game.year,
            expires_year=game.year + 24,
            request_clause_type='FLEET_BY_SHIP_COUNT',
            request_ship_count=3,
            offer_clause_type='NOTHING',
        )

        fleet = Fleet.objects.create(
            game=game,
            player=player2,
            name='Gift Fleet',
            x=player2.homeworld.x,
            y=player2.homeworld.y,
            ship_count=4,
        )
        FleetOrders.objects.create(
            game=game,
            fleet=fleet,
            order_type='GIVE',
            transfer_player=player1,
        )

        GameTurn(game).generate_turn()

        contract_old.refresh_from_db()
        contract_new.refresh_from_db()
        fleet.refresh_from_db()
        self.assertEqual(fleet.player_id, player1.id)
        self.assertEqual(contract_old.status, DiplomaticContract.STATUS_FULFILLED)
        self.assertEqual(contract_new.status, DiplomaticContract.STATUS_ACCEPTED)
        self.assertEqual(contract_new.progress_ship_count, 2)
        self.assertTrue(
            player1.messages.filter(message__icontains='Gift Fleet').exists()
        )
        self.assertTrue(
            player2.messages.filter(message__icontains='Gift Fleet').exists()
        )
        self.assertTrue(
            player1.messages.filter(message__icontains='Gift Fleet', priority=True).exists()
        )
        self.assertTrue(
            player2.messages.filter(message__icontains='Gift Fleet', priority=True).exists()
        )
        self.assertTrue(
            player1.messages.filter(message__icontains='Diplomatic request fulfilled').exists()
        )
        self.assertTrue(
            player2.messages.filter(message__icontains='Diplomatic request fulfilled').exists()
        )
        self.assertTrue(
            player1.messages.filter(message__icontains='Diplomatic request fulfilled', priority=True).exists()
        )
        self.assertTrue(
            player2.messages.filter(message__icontains='Diplomatic request fulfilled', priority=True).exists()
        )

    def test_multiple_instant_transfers(self):
        """Test multiple transfer orders executing in same turn."""
        from ..models import FleetOrders, Fleet

        game = default_game()
        player = game.players.first()
        star = player.homeworld

        # Set up star with resources
        star.ironium_inventory = 2000
        star.boranium_inventory = 2000
        star.mines = 0
        star.ironium_yield = 0
        star.boranium_yield = 0
        star.germanium_yield = 0
        star.save()

        fleet = Fleet.objects.create(
            game=game,
            player=player,
            name="Multi-Transfer Fleet",
            x=star.x,
            y=star.y,
            cargo_capacity=1000
        )

        # Create multiple transfer orders
        FleetOrders.objects.create(
            game=game,
            fleet=fleet,
            order_type='TRANSFER',
            target_star=star,
            transfer_type='LOAD',
            transfer_ironium=500
        )

        FleetOrders.objects.create(
            game=game,
            fleet=fleet,
            order_type='TRANSFER',
            target_star=star,
            transfer_type='LOAD',
            transfer_boranium=300
        )

        # Generate turn - both should execute instantly
        GameTurn(game).generate_turn()

        fleet.refresh_from_db()
        star.refresh_from_db()

        # Both transfers should have executed
        self.assertEqual(fleet.ironium_inventory, 500)
        self.assertEqual(fleet.boranium_inventory, 300)
        self.assertEqual(star.ironium_inventory, 1500)
        self.assertEqual(star.boranium_inventory, 1700)

        # No orders should remain
        self.assertEqual(fleet.orders.count(), 0)

    def test_transfer_order_waits_at_destination(self):
        """Transfer orders wait for fleet to be at destination (they don't move fleets)."""
        game = default_game(stars=5, fleets=1)
        player = game.players.first()
        fleet = game.fleets.first()
        target_star = game.stars.exclude(pk=player.homeworld.pk).first()

        # Position fleet away from target (ensure coordinates stay within 0-99 map bounds)
        original_x = (target_star.x + 20) % 80 + 10  # Offset but stay in bounds
        original_y = (target_star.y + 20) % 80 + 10
        fleet.x = original_x
        fleet.y = original_y
        fleet.ironium_inventory = 500
        fleet.boranium_inventory = 0
        fleet.germanium_inventory = 0
        fleet.colonists = 0
        fleet.save()

        from ..models import FleetOrders
        transfer_order = FleetOrders.objects.create(
            game=game,
            fleet=fleet,
            order_type='TRANSFER',
            transfer_type='UNLOAD',
            transfer_ironium=500,
            target_star=target_star
        )

        original_star_ironium = target_star.ironium_inventory

        # Generate turn - fleet should NOT move (Transfer orders don't move fleets)
        GameTurn(game).generate_turn()

        fleet.refresh_from_db()
        target_star.refresh_from_db()

        # Fleet should NOT have moved - Transfer orders wait, they don't move
        self.assertEqual(fleet.x, original_x)  # Still at original position

        # Transfer should not have executed (fleet not at destination)
        self.assertEqual(fleet.ironium_inventory, 500)  # Fleet still has cargo
        self.assertEqual(target_star.ironium_inventory, original_star_ironium)  # Star unchanged
        self.assertTrue(FleetOrders.objects.filter(id=transfer_order.id).exists())  # Order still waiting

    def test_transfer_unload_to_space_creates_salvage(self):
        """Unloading to empty space creates or updates salvage at the location."""
        from ..models import FleetOrders, Salvage

        game = default_game()
        player = game.players.first()

        occupied = {(s.x, s.y) for s in game.stars.all()}
        target_x, target_y = 40, 40
        if (target_x, target_y) in occupied:
            for x in range(0, 100):
                for y in range(0, 100):
                    if (x, y) not in occupied:
                        target_x, target_y = x, y
                        break
                else:
                    continue
                break

        fleet = Fleet.objects.create(
            game=game,
            player=player,
            name="Dump Fleet",
            x=target_x,
            y=target_y
        )
        fleet.ironium_inventory = 200
        fleet.boranium_inventory = 100
        fleet.germanium_inventory = 50
        fleet.colonists = 10
        fleet.save()

        Salvage.objects.create(
            game=game,
            x=target_x,
            y=target_y,
            ironium_inventory=10,
            boranium_inventory=5,
            germanium_inventory=0
        )

        FleetOrders.objects.create(
            game=game,
            fleet=fleet,
            order_type='TRANSFER',
            transfer_type='UNLOAD',
            transfer_ironium=50,
            transfer_boranium=25,
            transfer_germanium=10,
            transfer_colonists=5,
            x=target_x,
            y=target_y
        )

        GameTurn(game).generate_turn()

        fleet.refresh_from_db()
        salvage = Salvage.objects.get(game=game, x=target_x, y=target_y)

        self.assertEqual(fleet.ironium_inventory, 150)
        self.assertEqual(fleet.boranium_inventory, 75)
        self.assertEqual(fleet.germanium_inventory, 40)
        self.assertEqual(fleet.colonists, 5)

        self.assertEqual(salvage.ironium_inventory, 60)  # 10 + 50
        self.assertEqual(salvage.boranium_inventory, 30)  # 5 + 25
        self.assertEqual(salvage.germanium_inventory, 10)
        self.assertEqual(salvage.danger_level, 'NONE')

    def test_transfer_unload_to_space_kills_colonists_no_salvage(self):
        """Colonists unloaded to space are lost and not added to salvage."""
        from ..models import FleetOrders, Salvage

        game = default_game()
        player = game.players.first()

        occupied = {(s.x, s.y) for s in game.stars.all()}
        target_x, target_y = 12, 12
        if (target_x, target_y) in occupied:
            for x in range(0, 100):
                for y in range(0, 100):
                    if (x, y) not in occupied:
                        target_x, target_y = x, y
                        break
                else:
                    continue
                break

        fleet = Fleet.objects.create(
            game=game,
            player=player,
            name="Colonist Dump",
            x=target_x,
            y=target_y
        )
        fleet.ironium_inventory = 0
        fleet.boranium_inventory = 0
        fleet.germanium_inventory = 0
        fleet.colonists = 20
        fleet.save()

        FleetOrders.objects.create(
            game=game,
            fleet=fleet,
            order_type='TRANSFER',
            transfer_type='UNLOAD',
            transfer_colonists=20,
            x=target_x,
            y=target_y
        )

        GameTurn(game).generate_turn()

        fleet.refresh_from_db()
        self.assertEqual(fleet.colonists, 0)
        self.assertFalse(Salvage.objects.filter(game=game, x=target_x, y=target_y).exists())
        self.assertTrue(player.messages.filter(message__icontains="colonists").exists())

    def test_transfer_unload_to_space_minerals_and_colonists(self):
        """Minerals create salvage; colonists are lost when unloading to space."""
        from ..models import FleetOrders, Salvage

        game = default_game()
        player = game.players.first()

        occupied = {(s.x, s.y) for s in game.stars.all()}
        target_x, target_y = 22, 22
        if (target_x, target_y) in occupied:
            for x in range(0, 100):
                for y in range(0, 100):
                    if (x, y) not in occupied:
                        target_x, target_y = x, y
                        break
                else:
                    continue
                break

        fleet = Fleet.objects.create(
            game=game,
            player=player,
            name="Mixed Dump",
            x=target_x,
            y=target_y
        )
        fleet.ironium_inventory = 30
        fleet.boranium_inventory = 10
        fleet.germanium_inventory = 5
        fleet.colonists = 15
        fleet.save()

        FleetOrders.objects.create(
            game=game,
            fleet=fleet,
            order_type='TRANSFER',
            transfer_type='UNLOAD',
            transfer_ironium=30,
            transfer_boranium=10,
            transfer_germanium=5,
            transfer_colonists=15,
            x=target_x,
            y=target_y
        )

        GameTurn(game).generate_turn()

        fleet.refresh_from_db()
        salvage = Salvage.objects.get(game=game, x=target_x, y=target_y)

        self.assertEqual(fleet.colonists, 0)
        self.assertEqual(salvage.ironium_inventory, 30)
        self.assertEqual(salvage.boranium_inventory, 10)
        self.assertEqual(salvage.germanium_inventory, 5)
        self.assertTrue(player.messages.filter(message__icontains="colonists").exists())

    def test_asteroid_field_removed_when_depleted(self):
        """Asteroid field salvage should be removed when minerals are depleted."""
        game = default_game()
        player = game.players.first()

        occupied = {(s.x, s.y) for s in game.stars.all()}
        target_x, target_y = 30, 30
        if (target_x, target_y) in occupied:
            for x in range(0, 100):
                for y in range(0, 100):
                    if (x, y) not in occupied:
                        target_x, target_y = x, y
                        break
                else:
                    continue
                break

        salvage = Salvage.objects.create(
            game=game,
            x=target_x,
            y=target_y,
            salvage_type=Salvage.TYPE_ASTEROID_FIELD,
            ironium_inventory=20,
            boranium_inventory=5,
            germanium_inventory=0,
        )

        fleet = Fleet.objects.create(
            game=game,
            player=player,
            name="Field Hauler",
            x=target_x,
            y=target_y,
            cargo_capacity=100,
        )

        FleetOrders.objects.create(
            game=game,
            fleet=fleet,
            order_type='TRANSFER',
            transfer_type='LOAD',
            target_salvage=salvage,
        )

        GameTurn(game).generate_turn()

        fleet.refresh_from_db()
        self.assertFalse(Salvage.objects.filter(id=salvage.id).exists())
        self.assertEqual(fleet.ironium_inventory, 20)
        self.assertEqual(fleet.boranium_inventory, 5)
        self.assertEqual(fleet.germanium_inventory, 0)

    def test_salvage_collection_message_links_surviving_salvage_source(self):
        game = default_game()
        player = game.players.first()

        salvage = Salvage.objects.create(
            game=game,
            x=12,
            y=12,
            salvage_type=Salvage.TYPE_ASTEROID_FIELD,
            ironium_inventory=40,
            boranium_inventory=10,
            germanium_inventory=0,
        )
        fleet = Fleet.objects.create(
            game=game,
            player=player,
            name="Partial Loader",
            x=12,
            y=12,
            cargo_capacity=10,
        )

        FleetOrders.objects.create(
            game=game,
            fleet=fleet,
            order_type='TRANSFER',
            transfer_type='LOAD',
            target_salvage=salvage,
        )

        GameTurn(game).generate_turn()

        message = player.messages.filter(message__icontains='asteroid field').order_by('-id').first()
        salvage.refresh_from_db()
        self.assertIsNotNone(message)
        self.assertIn(format_map_object(salvage), message.message)

    def test_salvage_collection_message_uses_plain_text_when_salvage_depleted(self):
        game = default_game()
        player = game.players.first()

        salvage = Salvage.objects.create(
            game=game,
            x=13,
            y=13,
            salvage_type=Salvage.TYPE_ANCIENT_DEBRIS,
            ironium_inventory=8,
            boranium_inventory=4,
            germanium_inventory=0,
        )
        salvage_link = format_map_object(salvage)
        salvage_label = format_map_object(salvage, link=False)
        fleet = Fleet.objects.create(
            game=game,
            player=player,
            name="Full Loader",
            x=13,
            y=13,
            cargo_capacity=100,
        )

        FleetOrders.objects.create(
            game=game,
            fleet=fleet,
            order_type='TRANSFER',
            transfer_type='LOAD',
            target_salvage=salvage,
        )

        GameTurn(game).generate_turn()

        message = player.messages.filter(message__icontains='ancient debris').order_by('-id').first()
        self.assertIsNotNone(message)
        self.assertIn(salvage_label, message.message)
        self.assertNotIn(salvage_link, message.message)

    def test_transfer_invasion_changes_owner_on_success(self):
        """Transferring colonists to enemy colony can capture the star."""
        from ..models import FleetOrders

        game = default_game(stars=2)
        game.no_scanners = True
        game.save(update_fields=['no_scanners'])
        game.random_events = False
        game.save(update_fields=['random_events'])
        attacker = game.players.first()
        attacker_race = attacker.race_type
        attacker_race.population_growth_multiplier = 0
        attacker_race.save()
        defender = Player.objects.filter(game=game).exclude(id=attacker.id).first()
        if not defender:
            other_user = User.objects.create_user('inv_def', 'invdef@test.com', 'pass')
            other_account = Account.objects.create(django_user=other_user)
            defender = Player.objects.create(
                game=game,
                account=other_account,
                race_type=attacker.race_type,
            )
        defender_race = defender.race_type
        defender_race.population_growth_multiplier = 0
        defender_race.save()

        star = game.stars.exclude(pk=attacker.homeworld.pk).first()
        star.player = defender
        star.colonists = 2000
        star.defenses = 0
        star.save()

        fleet = Fleet.objects.create(
            game=game,
            player=attacker,
            name="Invader",
            x=star.x,
            y=star.y,
            colonists=10
        )

        FleetOrders.objects.create(
            game=game,
            fleet=fleet,
            order_type='TRANSFER',
            target_star=star,
            transfer_type='UNLOAD',
            transfer_colonists=10
        )

        GameTurn(game).generate_turn()

        star.refresh_from_db()
        fleet.refresh_from_db()

        self.assertEqual(star.player, attacker)
        # Invaders 10k - defenders 2k = 8k remaining
        self.assertEqual(star.colonists, 8000)
        self.assertEqual(fleet.colonists, 0)

        attacker_report = Report.objects.filter(
            game=game,
            player=attacker,
            target_type='star',
            target_id=star.id,
        ).first()
        self.assertIsNotNone(attacker_report)
        self.assertEqual(attacker_report.get_report_data().get('report_tier'), 'encounter')
        if defender:
            defender_report = Report.objects.filter(
                game=game,
                player=defender,
                target_type='fleet',
                target_id=fleet.id,
            ).first()
            self.assertIsNotNone(defender_report)
            self.assertEqual(defender_report.get_report_data().get('report_tier'), 'encounter')

    def test_transfer_invasion_destroyed_attacker_creates_no_reports(self):
        """If defenses destroy the attacker, no encounter reports should be created."""
        from ..models import FleetOrders

        game = default_game(stars=2)
        game.no_scanners = True
        game.save(update_fields=['no_scanners'])
        attacker = game.players.first()
        defender = Player.objects.filter(game=game).exclude(id=attacker.id).first()
        if not defender:
            other_user = User.objects.create_user('inv_def_destroy', 'invdefd@test.com', 'pass')
            other_account = Account.objects.create(django_user=other_user)
            defender = Player.objects.create(
                game=game,
                account=other_account,
                race_type=attacker.race_type,
            )

        star = game.stars.exclude(pk=attacker.homeworld.pk).first()
        star.player = defender
        star.colonists = 5000
        star.defenses = 10
        star.save()

        fleet = Fleet.objects.create(
            game=game,
            player=attacker,
            name="Doomed Invader",
            x=star.x,
            y=star.y,
            colonists=5,
            integrity=100,
            ship_count=1,
        )

        FleetOrders.objects.create(
            game=game,
            fleet=fleet,
            order_type='TRANSFER',
            target_star=star,
            transfer_type='UNLOAD',
            transfer_colonists=5
        )

        with patch.object(GameTurn, '_calculate_combat_damage', return_value={
            attacker: 200.0,
            defender: 0.0,
        }):
            GameTurn(game).generate_turn()

        self.assertFalse(Fleet.objects.filter(id=fleet.id).exists())
        self.assertFalse(Report.objects.filter(
            game=game,
            player=attacker,
            target_type='star',
            target_id=star.id,
        ).exists())
        self.assertFalse(Report.objects.filter(
            game=game,
            player=defender,
            target_type='fleet',
            target_id=fleet.id,
        ).exists())

    def test_transfer_invasion_fails_when_defenders_stronger(self):
        """Transferring colonists to enemy colony fails if defenders are stronger."""
        from ..models import FleetOrders

        game = default_game(stars=2)
        attacker = game.players.first()
        attacker_race = attacker.race_type
        attacker_race.population_growth_multiplier = 0
        attacker_race.save()
        defender = Player.objects.filter(game=game).exclude(id=attacker.id).first()
        if not defender:
            other_user = User.objects.create_user('inv_def2', 'invdef2@test.com', 'pass')
            other_account = Account.objects.create(django_user=other_user)
            defender = Player.objects.create(
                game=game,
                account=other_account,
                race_type=attacker.race_type,
            )
        defender_race = defender.race_type
        defender_race.population_growth_multiplier = 0
        defender_race.save()

        star = game.stars.exclude(pk=attacker.homeworld.pk).first()
        star.player = defender
        star.colonists = 20000
        star.defenses = 0
        star.save()

        fleet = Fleet.objects.create(
            game=game,
            player=attacker,
            name="Invader",
            x=star.x,
            y=star.y,
            colonists=5
        )

        FleetOrders.objects.create(
            game=game,
            fleet=fleet,
            order_type='TRANSFER',
            target_star=star,
            transfer_type='UNLOAD',
            transfer_colonists=5
        )

        GameTurn(game).generate_turn()

        star.refresh_from_db()
        fleet.refresh_from_db()

        self.assertEqual(star.player, defender)
        # Defenders 20k - invaders 5k = 15k remaining
        self.assertEqual(star.colonists, 15000)
        self.assertEqual(fleet.colonists, 0)

    def test_transfer_invasion_defenses_damage_fleet(self):
        """Planetary defenses should damage the invading fleet."""
        from ..models import FleetOrders

        game = default_game(stars=2)
        attacker = game.players.first()
        defender = Player.objects.filter(game=game).exclude(id=attacker.id).first()
        if not defender:
            other_user = User.objects.create_user('inv_def3', 'invdef3@test.com', 'pass')
            other_account = Account.objects.create(django_user=other_user)
            defender = Player.objects.create(
                game=game,
                account=other_account,
                race_type=attacker.race_type,
            )

        star = game.stars.exclude(pk=attacker.homeworld.pk).first()
        star.player = defender
        star.colonists = 1000
        star.defenses = 5
        star.save()

        fleet = Fleet.objects.create(
            game=game,
            player=attacker,
            name="Invader",
            x=star.x,
            y=star.y,
            colonists=2,
            integrity=100,
            ship_count=1
        )

        FleetOrders.objects.create(
            game=game,
            fleet=fleet,
            order_type='TRANSFER',
            target_star=star,
            transfer_type='UNLOAD',
            transfer_colonists=2
        )

        GameTurn(game).generate_turn()

        fleet.refresh_from_db()
        # Defenses should have reduced integrity
        self.assertLess(fleet.integrity, 100)

    def test_transfer_invasion_uses_colony_defense_technology(self):
        """Latest unlocked colony defense tech should strengthen defenses."""
        from ..models import FleetOrders, ResearchCategory, Technology
        from ..research import ensure_player_research_rows

        def _run_invasion(with_colony_tech):
            game = default_game(stars=2)
            attacker = game.players.first()
            defender = Player.objects.filter(game=game).exclude(id=attacker.id).first()
            if not defender:
                other_user = User.objects.create_user(
                    f'inv_def4_{"tech" if with_colony_tech else "base"}',
                    'invdef4@test.com',
                    'pass'
                )
                other_account = Account.objects.create(django_user=other_user)
                defender = Player.objects.create(
                    game=game,
                    account=other_account,
                    race_type=attacker.race_type,
                )

            star = game.stars.exclude(pk=attacker.homeworld.pk).first()
            star.player = defender
            star.colonists = 1000
            star.defenses = 5
            star.save()

            if with_colony_tech:
                category, _ = ResearchCategory.objects.get_or_create(
                    code='TEST_INVASION_CONSTRUCTION',
                    defaults={'name': 'Test Invasion Construction', 'enabled': True}
                )
                Technology.objects.create(
                    category=category,
                    level=2,
                    name='Planetary Bastion Grid',
                    tech_type='INFRASTRUCTURE',
                    params_json='{"colony_defense_level": 1.0}',
                    enabled=True,
                )
                for row in ensure_player_research_rows(defender):
                    row.current_level = 2.0
                    row.save(update_fields=['current_level'])

            fleet = Fleet.objects.create(
                game=game,
                player=attacker,
                name="Invader",
                x=star.x,
                y=star.y,
                colonists=2,
                integrity=100,
                ship_count=1
            )

            FleetOrders.objects.create(
                game=game,
                fleet=fleet,
                order_type='TRANSFER',
                target_star=star,
                transfer_type='UNLOAD',
                transfer_colonists=2
            )

            with patch('dj4xol.turn.roll_chance', return_value=False):
                GameTurn(game).generate_turn()

            fleet.refresh_from_db()
            return fleet.integrity

        base_integrity = _run_invasion(with_colony_tech=False)
        tech_integrity = _run_invasion(with_colony_tech=True)
        self.assertLess(tech_integrity, base_integrity)

    def test_transfer_raid_allied_stance_skips_defense_and_success_roll(self):
        from ..models import FleetOrders

        game = default_game(stars=2)
        attacker = game.players.first()
        defender = Player.objects.filter(game=game).exclude(id=attacker.id).first()
        if defender is None:
            other_user = User.objects.create_user('raid_allied_def', 'raid_allied_def@test.com', 'pass')
            other_account = Account.objects.create(django_user=other_user)
            defender = Player.objects.create(game=game, account=other_account, race_type=attacker.race_type)

        star = game.stars.exclude(pk=attacker.homeworld.pk).first()
        star.player = defender
        star.ironium_inventory = 200
        star.save(update_fields=['player', 'ironium_inventory'])

        fleet = Fleet.objects.create(
            game=game,
            player=attacker,
            name='Allied Raider',
            x=star.x,
            y=star.y,
            cargo_capacity=200,
            integrity=100,
            ship_count=1,
        )
        order = FleetOrders.objects.create(
            game=game,
            fleet=fleet,
            order_type='TRANSFER',
            transfer_type='LOAD',
            target_star=star,
            transfer_ironium=50,
        )

        PlayerDiplomaticStance.objects.create(
            player=defender,
            target_player=attacker,
            stance='ALLIED',
        )

        turn = GameTurn(game)
        with patch.object(GameTurn, '_resolve_transfer_raid_defense_fire') as defense_fire, \
             patch.object(GameTurn, '_transfer_raid_successful') as success_roll:
            result = turn._execute_transfer_order(fleet, order)

        self.assertEqual(result, 'executed')
        defense_fire.assert_not_called()
        success_roll.assert_not_called()
        star.refresh_from_db()
        fleet.refresh_from_db()
        self.assertEqual(star.ironium_inventory, 150)
        self.assertEqual(fleet.ironium_inventory, 50)

    def test_invasion_attacker_ground_force_multiplier_can_flip_outcome(self):
        game = default_game(stars=2)
        attacker = game.players.first()
        defender = Player.objects.filter(game=game).exclude(id=attacker.id).first()
        if defender is None:
            other_user = User.objects.create_user('inv_ground_att', 'inv_ground_att@test.com', 'pass')
            other_account = Account.objects.create(django_user=other_user)
            defender = Player.objects.create(game=game, account=other_account, race_type=attacker.race_type)

        attacker_type = ServerRaceType.objects.create(
            code='GFIA',
            name='Ground Force Invader',
            description='Attacker with stronger invasion troops.',
            ground_force_multiplier=1.5,
        )
        defender_type = ServerRaceType.objects.create(
            code='GFID',
            name='Ground Force Defender',
            description='Defender with standard ground troops.',
            ground_force_multiplier=1.0,
        )
        attacker.race_type = attacker_type
        defender.race_type = defender_type
        attacker.save(update_fields=['race_type'])
        defender.save(update_fields=['race_type'])

        star = game.stars.exclude(pk=attacker.homeworld.pk).first()
        star.player = defender
        star.colonists = 5000
        star.defenses = 0
        star.save(update_fields=['player', 'colonists', 'defenses'])

        fleet = Fleet.objects.create(
            game=game,
            player=attacker,
            name='Ground Force Invader',
            x=star.x,
            y=star.y,
            colonists=4,
            integrity=100,
            ship_count=1,
        )
        GameTurn(game)._handle_invasion(fleet, star, 4)
        star.refresh_from_db()
        self.assertEqual(star.player, attacker)
        self.assertEqual(star.colonists, 666)

    def test_invasion_defender_ground_force_multiplier_can_hold_colony(self):
        game = default_game(stars=2)
        attacker = game.players.first()
        defender = Player.objects.filter(game=game).exclude(id=attacker.id).first()
        if defender is None:
            other_user = User.objects.create_user('inv_ground_def', 'inv_ground_def@test.com', 'pass')
            other_account = Account.objects.create(django_user=other_user)
            defender = Player.objects.create(game=game, account=other_account, race_type=attacker.race_type)

        attacker_type = ServerRaceType.objects.create(
            code='GFD1',
            name='Light Infantry',
            description='Attacker with standard ground troops.',
            ground_force_multiplier=1.0,
        )
        defender_type = ServerRaceType.objects.create(
            code='GFD2',
            name='Heavy Infantry',
            description='Defender with stronger ground troops.',
            ground_force_multiplier=2.0,
        )
        attacker.race_type = attacker_type
        defender.race_type = defender_type
        attacker.save(update_fields=['race_type'])
        defender.save(update_fields=['race_type'])

        star = game.stars.exclude(pk=attacker.homeworld.pk).first()
        star.player = defender
        star.colonists = 4000
        star.defenses = 0
        star.save(update_fields=['player', 'colonists', 'defenses'])

        fleet = Fleet.objects.create(
            game=game,
            player=attacker,
            name='Ground Force Invader',
            x=star.x,
            y=star.y,
            colonists=6,
            integrity=100,
            ship_count=1,
        )
        GameTurn(game)._handle_invasion(fleet, star, 6)
        star.refresh_from_db()
        self.assertEqual(star.player, defender)
        self.assertEqual(star.colonists, 1000)

    def test_invasion_diplomatic_readiness_softly_biases_ground_force_comparison(self):
        game = default_game(stars=2)
        attacker = game.players.first()
        defender = Player.objects.filter(game=game).exclude(id=attacker.id).first()
        if defender is None:
            other_user = User.objects.create_user('inv_readiness_def', 'inv_readiness_def@test.com', 'pass')
            other_account = Account.objects.create(django_user=other_user)
            defender = Player.objects.create(game=game, account=other_account, race_type=attacker.race_type)

        PlayerDiplomaticStance.objects.create(
            player=attacker,
            target_player=defender,
            stance='HOSTILE',
        )
        PlayerDiplomaticStance.objects.create(
            player=defender,
            target_player=attacker,
            stance='ALLIED',
        )

        star = game.stars.exclude(pk=attacker.homeworld.pk).first()
        star.player = defender
        star.colonists = 5000
        star.defenses = 0
        star.save(update_fields=['player', 'colonists', 'defenses'])

        fleet = Fleet.objects.create(
            game=game,
            player=attacker,
            name='Readiness Invader',
            x=star.x,
            y=star.y,
            colonists=4,
            integrity=100,
            ship_count=1,
        )
        GameTurn(game)._handle_invasion(fleet, star, 4)
        star.refresh_from_db()
        self.assertEqual(star.player, attacker)
        self.assertEqual(star.colonists, 726)

    def test_hostile_orbit_hazard_allied_stance_blocks_strikes(self):
        game = default_game(stars=2)
        attacker = game.players.first()
        defender = Player.objects.filter(game=game).exclude(id=attacker.id).first()
        if defender is None:
            other_user = User.objects.create_user('orb_allied_def', 'orb_allied_def@test.com', 'pass')
            other_account = Account.objects.create(django_user=other_user)
            defender = Player.objects.create(game=game, account=other_account, race_type=attacker.race_type)

        PlayerDiplomaticStance.objects.create(
            player=defender,
            target_player=attacker,
            stance='ALLIED',
        )

        star = game.stars.exclude(pk=attacker.homeworld.pk).first()
        star.player = defender
        star.colonists = 10000
        star.defenses = 12
        star.save(update_fields=['player', 'colonists', 'defenses'])

        fleet = Fleet.objects.create(
            game=game,
            player=attacker,
            name='No-Strike Raider',
            x=star.x,
            y=star.y,
            integrity=100,
            ship_count=2,
        )

        with patch('dj4xol.turn.roll_chance', return_value=True):
            GameTurn(game).generate_turn()

        fleet.refresh_from_db()
        self.assertEqual(fleet.integrity, 100)

    def test_shipyard_repairs_prioritize_owner_before_allied_visitors(self):
        game = default_game(stars=2)
        owner = game.players.first()
        visitor = Player.objects.filter(game=game).exclude(id=owner.id).first()
        if visitor is None:
            other_user = User.objects.create_user('repair_visit_1', 'repair_visit_1@test.com', 'pass')
            other_account = Account.objects.create(django_user=other_user)
            visitor = Player.objects.create(game=game, account=other_account, race_type=owner.race_type)

        PlayerDiplomaticStance.objects.create(
            player=owner,
            target_player=visitor,
            stance='ALLIED',
        )

        star = owner.homeworld
        star.shipyards = 1
        star.save(update_fields=['shipyards'])

        owner_fleet = Fleet.objects.create(
            game=game, player=owner, name='Owner Repair', x=star.x, y=star.y, ship_count=1, integrity=0
        )
        visitor_fleet = Fleet.objects.create(
            game=game, player=visitor, name='Visitor Repair', x=star.x, y=star.y, ship_count=1, integrity=0
        )

        GameTurn(game)._repair_fleets_at_star(star, 1)
        owner_fleet.refresh_from_db()
        visitor_fleet.refresh_from_db()

        self.assertGreater(owner_fleet.integrity, 0)
        self.assertEqual(visitor_fleet.integrity, 0)

    def test_shipyard_repairs_scale_for_visitor_stance(self):
        def _run_for_stance(stance):
            game = default_game(stars=2)
            owner = game.players.first()
            visitor = Player.objects.filter(game=game).exclude(id=owner.id).first()
            if visitor is None:
                other_user = User.objects.create_user(
                    'repair_scale_%s' % stance.lower(),
                    'repair_scale_%s@test.com' % stance.lower(),
                    'pass'
                )
                other_account = Account.objects.create(django_user=other_user)
                visitor = Player.objects.create(game=game, account=other_account, race_type=owner.race_type)

            PlayerDiplomaticStance.objects.create(
                player=owner,
                target_player=visitor,
                stance=stance,
            )

            star = owner.homeworld
            star.shipyards = 4
            star.save(update_fields=['shipyards'])
            visitor_fleet = Fleet.objects.create(
                game=game,
                player=visitor,
                name='Scale %s' % stance,
                x=star.x,
                y=star.y,
                ship_count=4,
                integrity=0,
            )

            GameTurn(game)._repair_fleets_at_star(star, 4)
            visitor_fleet.refresh_from_db()
            return visitor_fleet.integrity

        self.assertEqual(_run_for_stance('ALLIED'), 100)
        self.assertEqual(_run_for_stance('WARM'), 50)
        self.assertEqual(_run_for_stance('NEUTRAL'), 25)

    def test_shipyard_refuels_scale_for_visitor_stance(self):
        def _run_for_stance(stance):
            game = default_game(stars=2)
            owner = game.players.first()
            visitor = Player.objects.filter(game=game).exclude(id=owner.id).first()
            if visitor is None:
                other_user = User.objects.create_user(
                    'refuel_scale_%s' % stance.lower(),
                    'refuel_scale_%s@test.com' % stance.lower(),
                    'pass'
                )
                other_account = Account.objects.create(django_user=other_user)
                visitor = Player.objects.create(game=game, account=other_account, race_type=owner.race_type)

            PlayerDiplomaticStance.objects.create(
                player=owner,
                target_player=visitor,
                stance=stance,
            )

            star = owner.homeworld
            star.shipyards = 4
            star.save(update_fields=['shipyards'])
            visitor_fleet = Fleet.objects.create(
                game=game,
                player=visitor,
                name='Refuel %s' % stance,
                x=star.x,
                y=star.y,
                ship_count=4,
                integrity=100,
                fuel=0.0,
                max_fuel=100.0,
            )

            GameTurn(game)._repair_fleets_at_star(star, 4)
            visitor_fleet.refresh_from_db()
            return float(visitor_fleet.fuel)

        self.assertAlmostEqual(_run_for_stance('ALLIED'), 100.0, places=4)
        self.assertAlmostEqual(_run_for_stance('WARM'), 50.0, places=4)
        self.assertAlmostEqual(_run_for_stance('NEUTRAL'), 25.0, places=4)

    def test_shipyard_service_capacity_is_per_ship_and_combines_refuel_and_repair(self):
        game = default_game(stars=2)
        owner = game.players.first()
        star = owner.homeworld
        star.shipyards = 1
        star.save(update_fields=['shipyards'])

        fleet = Fleet.objects.create(
            game=game,
            player=owner,
            name='Dual Service',
            x=star.x,
            y=star.y,
            ship_count=2,
            integrity=0,
            fuel=0.0,
            max_fuel=100.0,
        )

        GameTurn(game)._repair_fleets_at_star(star, 1)
        fleet.refresh_from_db()

        self.assertEqual(fleet.integrity, 50)
        self.assertAlmostEqual(fleet.fuel, 50.0, places=4)

    def test_hostile_orbit_can_take_defense_hazard_damage(self):
        game = default_game(stars=2)
        attacker = game.players.first()
        defender = Player.objects.filter(game=game).exclude(id=attacker.id).first()
        if not defender:
            other_user = User.objects.create_user('orb_def1', 'orbdef1@test.com', 'pass')
            other_account = Account.objects.create(django_user=other_user)
            defender = Player.objects.create(
                game=game,
                account=other_account,
                race_type=attacker.race_type,
            )

        star = game.stars.exclude(pk=attacker.homeworld.pk).first()
        star.player = defender
        star.colonists = 10000
        star.mines = 0
        star.factories = 0
        star.labs = 0
        star.shipyards = 0
        star.defenses = 12
        star.save(update_fields=[
            'player', 'colonists', 'mines', 'factories', 'labs', 'shipyards', 'defenses'
        ])

        fleet = Fleet.objects.create(
            game=game,
            player=attacker,
            name="Raider",
            x=star.x,
            y=star.y,
            integrity=100,
            ship_count=2,
        )

        with patch('dj4xol.turn.roll_chance', return_value=True):
            GameTurn(game).generate_turn()

        fleet.refresh_from_db()
        self.assertLess(fleet.integrity, 100)
        self.assertGreater(
            attacker.messages.filter(category='COMBAT').count(), 0
        )
        self.assertGreater(
            defender.messages.filter(category='COMBAT').count(), 0
        )

    def test_hostile_orbit_hazard_respects_trigger_roll(self):
        game = default_game(stars=2)
        attacker = game.players.first()
        defender = Player.objects.filter(game=game).exclude(id=attacker.id).first()
        if not defender:
            other_user = User.objects.create_user('orb_def2', 'orbdef2@test.com', 'pass')
            other_account = Account.objects.create(django_user=other_user)
            defender = Player.objects.create(
                game=game,
                account=other_account,
                race_type=attacker.race_type,
            )

        star = game.stars.exclude(pk=attacker.homeworld.pk).first()
        star.player = defender
        star.colonists = 10000
        star.mines = 0
        star.factories = 0
        star.labs = 0
        star.shipyards = 0
        star.defenses = 12
        star.save(update_fields=[
            'player', 'colonists', 'mines', 'factories', 'labs', 'shipyards', 'defenses'
        ])

        fleet = Fleet.objects.create(
            game=game,
            player=attacker,
            name="Scout",
            x=star.x,
            y=star.y,
            integrity=100,
            ship_count=1,
        )

        with patch('dj4xol.turn.roll_chance', return_value=False):
            GameTurn(game).generate_turn()

        fleet.refresh_from_db()
        self.assertEqual(fleet.integrity, 100)

    def test_hostile_orbit_hazard_uses_persuasion_bias_on_trigger_chance(self):
        game = default_game(stars=2)
        attacker = game.players.first()
        defender = Player.objects.filter(game=game).exclude(id=attacker.id).first()
        if not defender:
            other_user = User.objects.create_user('orb_def_persuasion', 'orb_def_persuasion@test.com', 'pass')
            other_account = Account.objects.create(django_user=other_user)
            defender = Player.objects.create(
                game=game,
                account=other_account,
                race_type=attacker.race_type,
            )

        attacker_type = ServerRaceType.objects.create(
            code='ODP1',
            name='Orbit Diplomatic A',
            enabled=True,
            description='',
            diplomacy_multiplier=2.0,
        )
        defender_type = ServerRaceType.objects.create(
            code='ODP2',
            name='Orbit Diplomatic B',
            enabled=True,
            description='',
            diplomacy_multiplier=2.0,
        )
        attacker.race_type = attacker_type
        attacker.save(update_fields=['race_type'])
        defender.race_type = defender_type
        defender.save(update_fields=['race_type'])

        PlayerDiplomaticStance.objects.create(
            player=defender,
            target_player=attacker,
            stance='HOSTILE',
        )

        star = game.stars.exclude(pk=attacker.homeworld.pk).first()
        star.player = defender
        star.colonists = 10000
        star.mines = 0
        star.factories = 0
        star.labs = 0
        star.shipyards = 0
        star.defenses = 12
        star.save(update_fields=[
            'player', 'colonists', 'mines', 'factories', 'labs', 'shipyards', 'defenses'
        ])

        fleet = Fleet.objects.create(
            game=game,
            player=attacker,
            name="Diplomatic Raider",
            x=star.x,
            y=star.y,
            integrity=100,
            ship_count=2,
        )

        with patch('dj4xol.turn.luck_ratio_chance', return_value=0.2), \
             patch('dj4xol.turn.roll_chance', return_value=False) as trigger_roll:
            GameTurn(game)._resolve_orbital_defense_hazard(star, fleet)

        trigger_roll.assert_called_once_with(0.1)

    def test_hostile_orbit_hazard_uses_colony_defense_technology(self):
        from ..models import ResearchCategory, Technology
        from ..research import ensure_player_research_rows

        def _run_hazard(with_colony_tech):
            game = default_game(stars=2)
            attacker = game.players.first()
            defender = Player.objects.filter(game=game).exclude(id=attacker.id).first()
            if not defender:
                other_user = User.objects.create_user(
                    f'orb_def3_{"tech" if with_colony_tech else "base"}',
                    'orbdef3@test.com',
                    'pass'
                )
                other_account = Account.objects.create(django_user=other_user)
                defender = Player.objects.create(
                    game=game,
                    account=other_account,
                    race_type=attacker.race_type,
                )

            star = game.stars.exclude(pk=attacker.homeworld.pk).first()
            star.player = defender
            star.colonists = 10000
            star.mines = 0
            star.factories = 0
            star.labs = 0
            star.shipyards = 0
            star.defenses = 12
            star.save(update_fields=[
                'player', 'colonists', 'mines', 'factories', 'labs', 'shipyards', 'defenses'
            ])

            if with_colony_tech:
                category = ResearchCategory.objects.create(
                    code='ORBITCONST', name='Orbit Construction', enabled=True
                )
                Technology.objects.create(
                    category=category,
                    level=2,
                    name='Planetary Tracking Grid',
                    tech_type='INFRASTRUCTURE',
                    params_json='{"colony_defense_level": 1.0}',
                    enabled=True,
                )
                for row in ensure_player_research_rows(defender):
                    row.current_level = 2.0
                    row.save(update_fields=['current_level'])

            fleet = Fleet.objects.create(
                game=game,
                player=attacker,
                name="Harrier",
                x=star.x,
                y=star.y,
                integrity=100,
                ship_count=2,
            )

            with patch('dj4xol.turn.roll_chance', return_value=True):
                GameTurn(game).generate_turn()
            fleet.refresh_from_db()
            return fleet.integrity

        base_integrity = _run_hazard(with_colony_tech=False)
        tech_integrity = _run_hazard(with_colony_tech=True)
        self.assertLess(tech_integrity, base_integrity)

    def test_owned_star_defenses_tooltip_shows_effective_and_modifier(self):
        from ..models import ResearchCategory, Technology
        from ..research import ensure_player_research_rows
        from ..objectdetails import DetailBuilder

        game = default_game(stars=2)
        player = game.players.first()
        star = player.homeworld
        star.mines = 0
        star.factories = 0
        star.labs = 0
        star.shipyards = 0
        star.defenses = 10
        star.colonists = 10000
        star.save(update_fields=[
            'mines', 'factories', 'labs', 'shipyards', 'defenses', 'colonists'
        ])

        category, _ = ResearchCategory.objects.get_or_create(
            code='TEST_TOOLTIP_CONSTRUCTION',
            defaults={'name': 'Test Tooltip Construction', 'enabled': True}
        )
        Technology.objects.create(
            category=category,
            level=2,
            name='Planetary Bastion Grid',
            tech_type='INFRASTRUCTURE',
            params_json='{"colony_defense_level": 1.1}',
            enabled=True,
        )
        for row in ensure_player_research_rows(player):
            row.current_level = 2.0
            row.save(update_fields=['current_level'])

        detail = DetailBuilder(
            game, x=star.x, y=star.y, selected=star.short_id, player=player
        ).build_detail()
        tooltip = detail['infrastructure']['DefensesTooltip']
        self.assertIsNotNone(tooltip)
        self.assertRegex(tooltip, r'^\d+\(\+\d+\)$')
        effective = int(tooltip.split('(')[0])
        self.assertGreater(effective, star.defenses)

    def test_unowned_star_defenses_has_no_effective_tooltip(self):
        from ..objectdetails import DetailBuilder

        game = default_game(stars=2)
        player = game.players.first()
        star = game.stars.exclude(pk=player.homeworld.pk).first()
        star.player = None
        star.defenses = 10
        star.save(update_fields=['player', 'defenses'])
        Fleet.objects.create(
            game=game, player=player, name='Scout', x=star.x, y=star.y
        )

        detail = DetailBuilder(
            game, x=star.x, y=star.y, selected=star.short_id, player=player
        ).build_detail()
        self.assertIsNone(detail['infrastructure']['DefensesTooltip'])

    def test_owned_star_defenses_tooltip_includes_staffing_effect(self):
        from ..objectdetails import DetailBuilder

        game = default_game(stars=2)
        player = game.players.first()
        star = player.homeworld
        star.mines = 0
        star.factories = 0
        star.labs = 0
        star.shipyards = 0
        star.defenses = 10
        star.colonists = 5000
        star.save(update_fields=[
            'mines', 'factories', 'labs', 'shipyards', 'defenses', 'colonists'
        ])

        detail = DetailBuilder(
            game, x=star.x, y=star.y, selected=star.short_id, player=player
        ).build_detail()
        self.assertEqual(detail['infrastructure']['DefensesTooltip'], '5(+0)')

    def test_owned_star_defenses_tooltip_shows_race_defense_multiplier(self):
        from ..objectdetails import DetailBuilder

        game = default_game(stars=2)
        player = game.players.first()
        player.race_type.defence_multiplier = 1.2
        player.race_type.save(update_fields=['defence_multiplier'])
        star = player.homeworld
        star.mines = 0
        star.factories = 0
        star.labs = 0
        star.shipyards = 0
        star.defenses = 10
        star.colonists = 10000
        star.save(update_fields=[
            'mines', 'factories', 'labs', 'shipyards', 'defenses', 'colonists'
        ])

        detail = DetailBuilder(
            game, x=star.x, y=star.y, selected=star.short_id, player=player
        ).build_detail()
        self.assertEqual(detail['infrastructure']['DefensesTooltip'], '12(+0) (+20%)')

    def test_owned_star_scanners_show_race_scan_multiplier_suffix(self):
        from ..objectdetails import DetailBuilder
        from ..models import ResearchCategory, Technology
        from ..research import ensure_player_research_rows

        game = default_game(stars=2)
        player = game.players.first()
        player.race_type.scan_multiplier = 1.2
        player.race_type.save(update_fields=['scan_multiplier'])
        star = player.homeworld

        Technology.objects.all().delete()
        ResearchCategory.objects.all().delete()
        category = ResearchCategory.objects.create(
            code='TEST_SCAN_INFRA',
            name='Test Scanner Infrastructure',
            enabled=True,
        )
        Technology.objects.create(
            category=category,
            level=1,
            name='Orbital Sensor Grid',
            tech_type='INFRASTRUCTURE',
            params_json='{"basic_scanner_range": 5, "advanced_scanner_range": 2}',
            enabled=True,
        )
        for row in ensure_player_research_rows(player):
            row.current_level = 1.0
            row.save(update_fields=['current_level'])

        detail = DetailBuilder(
            game, x=star.x, y=star.y, selected=star.short_id, player=player
        ).build_detail()
        self.assertEqual(detail['infrastructure']['Scanners'], '6ly/2ly (+20%)')

    def test_foreign_star_encounter_report_shows_scanners_without_trait_suffix(self):
        from ..objectdetails import DetailBuilder
        from ..models import Report, ResearchCategory, Technology
        from ..research import ensure_player_research_rows

        game = default_game(stars=2)
        player = game.players.first()
        other_user = User.objects.create_user('star_scan_enemy', 'star_scan_enemy@test.com', 'pass')
        other_account = Account.objects.create(django_user=other_user)
        other_player = Player.objects.create(
            game=game,
            account=other_account,
            race_type=player.race_type,
        )
        other_player.race_type.scan_multiplier = 1.2
        other_player.race_type.save(update_fields=['scan_multiplier'])

        Technology.objects.all().delete()
        ResearchCategory.objects.all().delete()
        category = ResearchCategory.objects.create(
            code='TEST_SCAN_FOREIGN_INFRA',
            name='Foreign Scanner Infrastructure',
            enabled=True,
        )
        Technology.objects.create(
            category=category,
            level=1,
            name='Orbital Sensor Grid',
            tech_type='INFRASTRUCTURE',
            params_json='{"basic_scanner_range": 5, "advanced_scanner_range": 2}',
            enabled=True,
        )
        for row in ensure_player_research_rows(other_player):
            row.current_level = 1.0
            row.save(update_fields=['current_level'])

        star = game.stars.exclude(pk=player.homeworld.pk).first()
        star.player = other_player
        star.mines = 1
        star.factories = 1
        star.labs = 1
        star.defenses = 1
        star.shipyards = 1
        star.save(update_fields=['player', 'mines', 'factories', 'labs', 'defenses', 'shipyards'])

        turn = GameTurn(game)
        report = Report.objects.create(
            game=game,
            player=player,
            year=game.year,
            target_type='star',
            target_id=star.id,
            cached_report='{}',
        )
        report.set_report_data(
            turn._build_report_data(player, star, 'star', report_tier='encounter')
        )
        report.save(update_fields=['cached_report'])

        self.assertIn('basic_scanner_range', report.get_report_data())
        self.assertIn('advanced_scanner_range', report.get_report_data())

        detail_builder = DetailBuilder(
            game, x=star.x, y=star.y, selected=star.short_id, player=player
        )
        detail_builder.selected_obj = star
        detail = detail_builder._build_detail_from_report(game.year)
        self.assertEqual(detail['infrastructure']['Scanners'], '6ly/2ly')

    def test_new_fleet_gets_thumbnail_path(self):
        game = default_game(stars=2)
        player = game.players.first()
        fleet = Fleet.objects.create(
            game=game,
            player=player,
            name="Thumbnail Test",
            x=player.homeworld.x,
            y=player.homeworld.y,
        )
        self.assertTrue(fleet.thumbnail_path)
        self.assertTrue(fleet.thumbnail_path.endswith('.png'))

    def test_selected_fleet_detail_includes_thumbnail(self):
        from ..objectdetails import DetailBuilder

        game = default_game(stars=2)
        player = game.players.first()
        fleet = Fleet.objects.create(
            game=game,
            player=player,
            name="Detail Thumb",
            x=player.homeworld.x,
            y=player.homeworld.y,
        )
        detail = DetailBuilder(
            game, x=fleet.x, y=fleet.y, selected=fleet.short_id, player=player
        ).build_detail()
        self.assertEqual(detail.get('fleet_thumbnail'), fleet.thumbnail_path)

    def test_transfer_colonists_to_unowned_star_random_failure(self):
        """Colonists transferred to unowned star usually fail to colonise."""
        from ..models import FleetOrders
        from unittest.mock import patch

        game = default_game(stars=2)
        player = game.players.first()
        star = game.stars.exclude(pk=player.homeworld.pk).first()
        star.player = None
        star.colonists = 0
        star.save()

        fleet = Fleet.objects.create(
            game=game,
            player=player,
            name="Settlers",
            x=star.x,
            y=star.y,
            colonists=5
        )

        FleetOrders.objects.create(
            game=game,
            fleet=fleet,
            order_type='TRANSFER',
            target_star=star,
            transfer_type='UNLOAD',
            transfer_colonists=5
        )

        with patch('dj4xol.turn.random.random', return_value=0.5):
            GameTurn(game).generate_turn()

        star.refresh_from_db()
        fleet.refresh_from_db()

        self.assertIsNone(star.player)
        self.assertEqual(star.colonists, 0)
        self.assertEqual(fleet.colonists, 0)

    def test_transfer_colonists_to_unowned_star_random_success(self):
        """Colonists transferred to unowned star can establish a colony."""
        from ..models import FleetOrders
        from unittest.mock import patch

        game = default_game(stars=2)
        player = game.players.first()
        race = player.race_type
        race.population_growth_multiplier = 0
        race.save()
        star = game.stars.exclude(pk=player.homeworld.pk).first()
        star.player = None
        star.colonists = 0
        star.save()

        fleet = Fleet.objects.create(
            game=game,
            player=player,
            name="Settlers",
            x=star.x,
            y=star.y,
            colonists=5
        )

        FleetOrders.objects.create(
            game=game,
            fleet=fleet,
            order_type='TRANSFER',
            target_star=star,
            transfer_type='UNLOAD',
            transfer_colonists=5
        )

        with patch('dj4xol.turn.random.random', return_value=0.01):
            GameTurn(game).generate_turn()

        star.refresh_from_db()
        fleet.refresh_from_db()

        self.assertEqual(star.player, player)
        self.assertEqual(star.colonists, 5000)
        self.assertEqual(fleet.colonists, 0)

    def test_transfer_minerals_to_other_player_generates_message(self):
        """Mineral transfer to another player's star sends a message to the owner."""
        from ..models import FleetOrders

        game = default_game(stars=2)
        player = game.players.first()

        other_player = Player.objects.filter(game=game).exclude(id=player.id).first()
        if not other_player:
            other_user = User.objects.create_user('gift_owner', 'gift@test.com', 'pass')
            other_account = Account.objects.create(django_user=other_user)
            other_player = Player.objects.create(
                game=game,
                account=other_account,
                race_type=player.race_type,
            )

        star = game.stars.exclude(pk=player.homeworld.pk).first()
        star.player = other_player
        star.save()

        fleet = Fleet.objects.create(
            game=game,
            player=player,
            name="Trader",
            x=star.x,
            y=star.y,
            ironium_inventory=40,
            boranium_inventory=20,
            germanium_inventory=0
        )

        FleetOrders.objects.create(
            game=game,
            fleet=fleet,
            order_type='TRANSFER',
            target_star=star,
            transfer_type='UNLOAD',
            transfer_ironium=40,
            transfer_boranium=20
        )

        GameTurn(game).generate_turn()

        self.assertTrue(other_player.messages.filter(message__icontains="mineral").exists())

    def test_give_order_transfers_fleet_and_creates_messages_and_report(self):
        from ..models import FleetOrders, Report
        from ..factory import GameFactory

        game = default_game(stars=2, fleets=0)
        player1 = game.players.first()
        other_user = User.objects.create_user('gift_receiver', 'gift_receiver@test.com', 'pass')
        other_account = Account.objects.create(django_user=other_user)
        game.joinable = True
        game.save(update_fields=['joinable'])
        factory = GameFactory(game=game)
        player2 = factory.join_player(other_account, get_default_race())
        game.fleets.all().delete()
        fleet = Fleet.objects.create(
            game=game,
            player=player1,
            name="Gift Ship",
            x=player1.homeworld.x,
            y=player1.homeworld.y,
            ironium_inventory=12,
            colonists=4,
            ship_count=1,
            integrity=100,
            heading=87.0,
            travel_warp=5,
        )

        FleetOrders.objects.create(
            game=game,
            fleet=fleet,
            order_type='GIVE',
            transfer_player=player2,
        )

        GameTurn(game).generate_turn()

        fleet.refresh_from_db()
        self.assertEqual(fleet.player_id, player2.id)
        self.assertEqual(fleet.orders.count(), 0)
        self.assertEqual(fleet.travel_warp, 0)
        self.assertAlmostEqual(float(fleet.heading), 87.0, places=1)

        sender_messages = list(player1.messages.filter(message__icontains="Gift Ship"))
        receiver_messages = list(player2.messages.filter(message__icontains="Gift Ship"))
        self.assertTrue(any(player2.name in msg.message for msg in sender_messages))
        self.assertTrue(any(player1.name in msg.message for msg in receiver_messages))

        report = Report.objects.get(
            game=game,
            player=player1,
            target_type='fleet',
            target_id=fleet.id,
        )
        data = report.get_report_data()
        self.assertEqual(data.get('report_tier'), 'encounter')
        self.assertEqual(data.get('player_name'), player2.name)

    def test_give_order_without_recipient_abandons_fleet_and_creates_report(self):
        from ..models import FleetOrders, Report

        game = default_game(stars=2, fleets=0)
        player = game.players.first()
        game.fleets.all().delete()
        fleet = Fleet.objects.create(
            game=game,
            player=player,
            name="Drifter",
            x=player.homeworld.x,
            y=player.homeworld.y,
            boranium_inventory=9,
            ship_count=1,
            integrity=100,
            heading=133.0,
            travel_warp=4,
        )

        FleetOrders.objects.create(
            game=game,
            fleet=fleet,
            order_type='GIVE',
        )

        GameTurn(game).generate_turn()

        fleet.refresh_from_db()
        self.assertIsNone(fleet.player)
        self.assertEqual(fleet.orders.count(), 0)
        self.assertEqual(fleet.travel_warp, 0)
        self.assertAlmostEqual(float(fleet.heading), 133.0, places=1)
        self.assertTrue(player.messages.filter(message__icontains="Drifter").exists())

        report = Report.objects.get(
            game=game,
            player=player,
            target_type='fleet',
            target_id=fleet.id,
        )
        data = report.get_report_data()
        self.assertEqual(data.get('report_tier'), 'encounter')
        self.assertEqual(data.get('player_name'), 'Abandoned')

    def test_load_transfer_from_star(self):
        """Test loading resources from star to fleet."""
        game = default_game(stars=5, fleets=1)
        player = game.players.first()
        fleet = game.fleets.first()
        target_star = game.stars.exclude(pk=player.homeworld.pk).first()

        # Position fleet at target star, set capacity, and clear cargo
        fleet.x = target_star.x
        fleet.y = target_star.y
        fleet.cargo_capacity = 1000
        fleet.ironium_inventory = 0
        fleet.boranium_inventory = 0
        fleet.germanium_inventory = 0
        fleet.colonists = 0
        fleet.save()

        # Star has resources
        target_star.ironium_inventory = 500
        target_star.boranium_inventory = 300
        target_star.save()

        from ..models import FleetOrders
        FleetOrders.objects.create(
            game=game,
            fleet=fleet,
            order_type='TRANSFER',
            transfer_type='LOAD',
            transfer_ironium=200,
            transfer_boranium=150,
            target_star=target_star
        )

        # Generate turn - should execute transfer immediately
        GameTurn(game).generate_turn()

        fleet.refresh_from_db()
        target_star.refresh_from_db()

        # Resources should have transferred
        self.assertEqual(fleet.ironium_inventory, 200)    # Fleet loaded ironium
        self.assertEqual(fleet.boranium_inventory, 150)   # Fleet loaded boranium
        self.assertEqual(target_star.ironium_inventory, 300)  # Star lost ironium
        self.assertEqual(target_star.boranium_inventory, 150)  # Star lost boranium

        # Order should be completed (deleted)
        self.assertEqual(fleet.orders.count(), 0)

    def test_unload_transfer_to_star(self):
        """Test unloading resources from fleet to star."""
        game = default_game(stars=5, fleets=1)
        player = game.players.first()
        fleet = game.fleets.first()
        target_star = game.stars.exclude(pk=player.homeworld.pk).first()

        # Position fleet at target star and give it cargo
        fleet.x = target_star.x
        fleet.y = target_star.y
        fleet.ironium_inventory = 300   # Fleet has cargo
        fleet.boranium_inventory = 0
        fleet.germanium_inventory = 200
        fleet.colonists = 0
        fleet.save()

        original_star_ironium = target_star.ironium_inventory
        original_star_germanium = target_star.germanium_inventory

        from ..models import FleetOrders
        FleetOrders.objects.create(
            game=game,
            fleet=fleet,
            order_type='TRANSFER',
            transfer_type='UNLOAD',
            transfer_ironium=150,
            transfer_germanium=100,
            target_star=target_star
        )

        # Generate turn
        GameTurn(game).generate_turn()

        fleet.refresh_from_db()
        target_star.refresh_from_db()

        # Resources should have transferred
        self.assertEqual(fleet.ironium_inventory, 150)  # Fleet lost ironium (300-150)
        self.assertEqual(fleet.germanium_inventory, 100)  # Fleet lost germanium (200-100)
        self.assertEqual(target_star.ironium_inventory, original_star_ironium + 150)  # Star gained
        self.assertEqual(target_star.germanium_inventory, original_star_germanium + 100)  # Star gained

        # Order should be completed
        self.assertEqual(fleet.orders.count(), 0)

    def test_unload_all_to_star(self):
        """Test UNLOAD_ALL transfers everything from fleet to star."""
        game = default_game(stars=5, fleets=1)
        player = game.players.first()
        race = player.race_type
        race.population_growth_multiplier = 0
        race.save()
        fleet = game.fleets.first()
        target_star = game.stars.exclude(pk=player.homeworld.pk).first()
        target_star.player = player
        target_star.save()

        # Position fleet at target star and give it cargo
        fleet.x = target_star.x
        fleet.y = target_star.y
        fleet.ironium_inventory = 300
        fleet.boranium_inventory = 150
        fleet.germanium_inventory = 200
        fleet.colonists = 50  # 50k colonists
        fleet.save()

        original_star_ironium = target_star.ironium_inventory
        original_star_boranium = target_star.boranium_inventory
        original_star_germanium = target_star.germanium_inventory
        original_star_colonists = target_star.colonists

        from ..models import FleetOrders
        FleetOrders.objects.create(
            game=game,
            fleet=fleet,
            order_type='TRANSFER',
            transfer_type='UNLOAD_ALL',
            target_star=target_star
        )

        # Generate turn
        GameTurn(game).generate_turn()

        fleet.refresh_from_db()
        target_star.refresh_from_db()

        # All cargo should have transferred
        self.assertEqual(fleet.ironium_inventory, 0)
        self.assertEqual(fleet.boranium_inventory, 0)
        self.assertEqual(fleet.germanium_inventory, 0)
        self.assertEqual(fleet.colonists, 0)

        # Star should have gained all cargo
        self.assertEqual(target_star.ironium_inventory, original_star_ironium + 300)
        self.assertEqual(target_star.boranium_inventory, original_star_boranium + 150)
        self.assertEqual(target_star.germanium_inventory, original_star_germanium + 200)
        # Colonists: fleet stores as thousands, star stores as individuals
        self.assertEqual(target_star.colonists, original_star_colonists + 50000)

        # Order should be completed
        self.assertEqual(fleet.orders.count(), 0)

    def test_unload_all_to_fleet(self):
        """Test UNLOAD_ALL transfers everything from fleet to another fleet."""
        from ..models import FleetOrders, Fleet

        game = default_game(stars=5, fleets=1)
        player = game.players.first()
        source_fleet = game.fleets.first()
        star = player.homeworld

        # Create target fleet at same location
        target_fleet = Fleet.objects.create(
            game=game,
            player=player,
            name="Target Fleet",
            x=star.x,
            y=star.y,
            cargo_capacity=1000
        )

        # Give source fleet cargo
        source_fleet.x = star.x
        source_fleet.y = star.y
        source_fleet.ironium_inventory = 300
        source_fleet.boranium_inventory = 150
        source_fleet.germanium_inventory = 200
        source_fleet.colonists = 50
        source_fleet.save()

        # Target fleet starts empty
        target_fleet.ironium_inventory = 0
        target_fleet.boranium_inventory = 0
        target_fleet.germanium_inventory = 0
        target_fleet.colonists = 0
        target_fleet.save()

        FleetOrders.objects.create(
            game=game,
            fleet=source_fleet,
            order_type='TRANSFER',
            transfer_type='UNLOAD_ALL',
            target_fleet=target_fleet
        )

        GameTurn(game).generate_turn()

        source_fleet.refresh_from_db()
        target_fleet.refresh_from_db()

        # Source fleet should be empty
        self.assertEqual(source_fleet.ironium_inventory, 0)
        self.assertEqual(source_fleet.boranium_inventory, 0)
        self.assertEqual(source_fleet.germanium_inventory, 0)
        self.assertEqual(source_fleet.colonists, 0)

        # Target fleet should have all cargo
        self.assertEqual(target_fleet.ironium_inventory, 300)
        self.assertEqual(target_fleet.boranium_inventory, 150)
        self.assertEqual(target_fleet.germanium_inventory, 200)
        self.assertEqual(target_fleet.colonists, 50)

        # Order should be completed
        self.assertEqual(source_fleet.orders.count(), 0)

    def test_proportional_loading_when_over_capacity(self):
        """Test proportional resource allocation when transfer would exceed fleet capacity."""
        game = default_game(stars=5, fleets=1)
        player = game.players.first()
        fleet = game.fleets.first()
        target_star = game.stars.exclude(pk=player.homeworld.pk).first()

        # Position fleet at target with existing cargo (almost full)
        fleet.x = target_star.x
        fleet.y = target_star.y
        fleet.cargo_capacity = 1000
        fleet.ironium_inventory = 0
        fleet.boranium_inventory = 0
        fleet.germanium_inventory = 0
        fleet.colonists = 900  # Fleet almost full (900kt of 1000kt capacity used)
        fleet.save()

        # Star has plenty of resources
        target_star.ironium_inventory = 1000
        target_star.boranium_inventory = 1000
        target_star.save()

        from ..models import FleetOrders
        FleetOrders.objects.create(
            game=game,
            fleet=fleet,
            order_type='TRANSFER',
            transfer_type='LOAD',
            transfer_ironium=80,   # Want 80kt
            transfer_boranium=40,  # Want 40kt (total 120kt requested)
            target_star=target_star
        )

        # Generate turn
        GameTurn(game).generate_turn()

        fleet.refresh_from_db()
        target_star.refresh_from_db()

        # Fleet can only take 100kt more (1000 - 900)
        # Proportions: ironium = 80/120 = 2/3, boranium = 40/120 = 1/3
        # Actual transfer: ironium = 100 * 2/3 = 66kt, boranium = 100 * 1/3 = 33kt
        expected_ironium = int(100 * 80/120)  # 66
        expected_boranium = int(100 * 40/120)  # 33

        self.assertEqual(fleet.ironium_inventory, expected_ironium)
        self.assertEqual(fleet.boranium_inventory, expected_boranium)
        self.assertEqual(fleet.colonists, 900)  # Unchanged

        # Star should have lost the same amounts
        self.assertEqual(target_star.ironium_inventory, 1000 - expected_ironium)
        self.assertEqual(target_star.boranium_inventory, 1000 - expected_boranium)

    def test_limited_by_star_resources(self):
        """Test loading limited by what's available at the star."""
        game = default_game(stars=5, fleets=1)
        player = game.players.first()
        fleet = game.fleets.first()
        target_star = game.stars.exclude(pk=player.homeworld.pk).first()

        # Position fleet at target and clear cargo
        fleet.x = target_star.x
        fleet.y = target_star.y
        fleet.cargo_capacity = 1000
        fleet.ironium_inventory = 0
        fleet.boranium_inventory = 0
        fleet.germanium_inventory = 0
        fleet.colonists = 0
        fleet.save()

        # Star has limited resources
        target_star.ironium_inventory = 50   # Less than requested
        target_star.boranium_inventory = 20  # Less than requested
        target_star.save()

        from ..models import FleetOrders
        FleetOrders.objects.create(
            game=game,
            fleet=fleet,
            order_type='TRANSFER',
            transfer_type='LOAD',
            transfer_ironium=200,  # Want more than star has
            transfer_boranium=100, # Want more than star has
            target_star=target_star
        )

        # Generate turn
        GameTurn(game).generate_turn()

        fleet.refresh_from_db()
        target_star.refresh_from_db()

        # Fleet should get only what was available
        self.assertEqual(fleet.ironium_inventory, 50)  # All available ironium
        self.assertEqual(fleet.boranium_inventory, 20)  # All available boranium

        # Star should be depleted of these resources
        self.assertEqual(target_star.ironium_inventory, 0)
        self.assertEqual(target_star.boranium_inventory, 0)

    def test_unload_limited_by_fleet_cargo(self):
        """Test unloading limited by what fleet actually has."""
        game = default_game(stars=5, fleets=1)
        player = game.players.first()
        race = player.race_type
        race.population_growth_multiplier = 0
        race.save()
        fleet = game.fleets.first()
        target_star = game.stars.exclude(pk=player.homeworld.pk).first()
        target_star.player = player
        target_star.save()

        # Position fleet at target with limited cargo
        fleet.x = target_star.x
        fleet.y = target_star.y
        fleet.ironium_inventory = 30   # Less than order requests
        fleet.boranium_inventory = 0
        fleet.germanium_inventory = 0
        fleet.colonists = 15  # Less than order requests (15k colonists = 15kt cargo)
        fleet.save()

        original_star_ironium = target_star.ironium_inventory
        original_star_colonists = target_star.colonists

        from ..models import FleetOrders
        FleetOrders.objects.create(
            game=game,
            fleet=fleet,
            order_type='TRANSFER',
            transfer_type='UNLOAD',
            transfer_ironium=100,   # Want to unload more than fleet has
            transfer_colonists=50,  # Want to unload more than fleet has (50k colonists)
            target_star=target_star
        )

        # Generate turn
        GameTurn(game).generate_turn()

        fleet.refresh_from_db()
        target_star.refresh_from_db()

        # Fleet should unload only what it had
        self.assertEqual(fleet.ironium_inventory, 0)  # Unloaded all 30
        self.assertEqual(fleet.colonists, 0)          # Unloaded all 15k

        # Star should receive what was actually unloaded
        # Note: star.colonists is in individuals, fleet.colonists is in thousands
        self.assertEqual(target_star.ironium_inventory, original_star_ironium + 30)
        self.assertEqual(target_star.colonists, original_star_colonists + 15000)  # 15k * 1000

    def test_transfer_order_repeats(self):
        """Test repeating transfer orders."""
        game = default_game(stars=5, fleets=1)
        player = game.players.first()
        fleet = game.fleets.first()
        target_star = game.stars.exclude(pk=player.homeworld.pk).first()

        # Position fleet at target
        fleet.x = target_star.x
        fleet.y = target_star.y
        fleet.ironium_inventory = 2000
        fleet.save()

        from ..models import FleetOrders
        order = FleetOrders.objects.create(
            game=game,
            fleet=fleet,
            order_type='TRANSFER',
            transfer_type='UNLOAD',
            transfer_ironium=1000,
            target_star=target_star,
            repeat=True
        )
        original_order_id = order.id

        # Generate turn - should execute and requeue
        GameTurn(game).generate_turn()

        fleet.refresh_from_db()

        # Fleet should have unloaded
        self.assertEqual(fleet.ironium_inventory, 1000)  # 2000 - 1000

        # Original order deleted, new order created
        self.assertFalse(FleetOrders.objects.filter(id=original_order_id).exists())
        self.assertEqual(fleet.orders.count(), 1)

        # New order should have same properties
        new_order = fleet.orders.first()
        self.assertEqual(new_order.order_type, 'TRANSFER')
        self.assertEqual(new_order.transfer_type, 'UNLOAD')
        self.assertEqual(new_order.transfer_ironium, 1000)
        self.assertEqual(new_order.target_star, target_star)
        self.assertTrue(new_order.repeat)
        self.assertNotEqual(new_order.id, original_order_id)


class TestResourceFieldNaming(TestCase):
    """Test that resource field renaming works correctly across all game systems."""

    def test_star_field_access(self):
        """Test that Star objects use the new field names correctly."""
        game = default_game()
        star = game.stars.first()

        # Test yield fields exist and are accessible
        self.assertIsNotNone(star.ironium_yield)
        self.assertIsNotNone(star.boranium_yield)
        self.assertIsNotNone(star.germanium_yield)

        # Test inventory fields exist and are accessible
        self.assertIsNotNone(star.ironium_inventory)
        self.assertIsNotNone(star.boranium_inventory)
        self.assertIsNotNone(star.germanium_inventory)

        # Test old field names don't exist
        self.assertFalse(hasattr(star, 'ironium'))
        self.assertFalse(hasattr(star, 'boranium'))
        self.assertFalse(hasattr(star, 'germanium'))
        self.assertFalse(hasattr(star, 'ironium_surface'))
        self.assertFalse(hasattr(star, 'boranium_surface'))
        self.assertFalse(hasattr(star, 'germanium_surface'))

    def test_fleet_field_access(self):
        """Test that Fleet objects use the new field names correctly."""
        game = default_game(fleets=1)
        fleet = game.fleets.first()

        # Test inventory fields exist and are accessible
        self.assertIsNotNone(fleet.ironium_inventory)
        self.assertIsNotNone(fleet.boranium_inventory)
        self.assertIsNotNone(fleet.germanium_inventory)

        # Test old field names don't exist
        self.assertFalse(hasattr(fleet, 'ironium'))
        self.assertFalse(hasattr(fleet, 'boranium'))
        self.assertFalse(hasattr(fleet, 'germanium'))

    def test_cargo_used_property(self):
        """Test that Fleet.cargo_used works with new field names."""
        game = default_game(fleets=1)
        fleet = game.fleets.first()

        # Set known values
        fleet.ironium_inventory = 100
        fleet.boranium_inventory = 200
        fleet.germanium_inventory = 300
        fleet.colonists = 400

        expected_cargo = 100 + 200 + 300 + 400
        self.assertEqual(fleet.cargo_used, expected_cargo)

    def test_mining_system_field_usage(self):
        """Test that mining system works with new field names."""
        game = default_game()
        star = game.stars.first()

        # Set up star with yields and verify mining can access them
        star.ironium_yield = 50
        star.boranium_yield = 25
        star.germanium_yield = 75
        star.ironium_inventory = 1000
        star.boranium_inventory = 1000
        star.germanium_inventory = 1000
        star.mines = 10
        star.colonists = 100000
        star.save()

        initial_ironium = star.ironium_inventory

        # Run mining
        GameTurn(game).mining()

        star.refresh_from_db()

        # Mining should have accessed yield fields and updated inventory
        self.assertGreaterEqual(star.ironium_inventory, initial_ironium)


class TestSecretResourceDetailPanel(TestCase):
    def test_detail_panel_secret_resource_labels(self):
        """Secret resources should display as ??? until discovered."""
        from ..objectdetails import DetailBuilder
        from ..secret_resources import get_secret_resource_name

        game = default_game()
        player = game.players.first()
        star = player.homeworld

        star.resource_x_yield = 60
        star.resource_x_inventory = 500
        star.save(update_fields=['resource_x_yield', 'resource_x_inventory'])

        player.discovered_resource_x = False
        player.save(update_fields=['discovered_resource_x'])

        detail = DetailBuilder(
            game,
            x=star.x,
            y=star.y,
            selected=star.short_id.lower(),
            player=player,
        ).build_detail()
        self.assertIn('resource_x', detail['resources'])
        self.assertEqual(detail['resources']['resource_x']['label'], '???')

        player.discovered_resource_x = True
        player.save(update_fields=['discovered_resource_x'])

        detail = DetailBuilder(
            game,
            x=star.x,
            y=star.y,
            selected=star.short_id.lower(),
            player=player,
        ).build_detail()
        self.assertEqual(
            detail['resources']['resource_x']['label'],
            get_secret_resource_name('resource_x'),
        )


class TestSecretResourceSalvageDiscovery(TestCase):
    def test_salvage_transfer_discovers_secret_resource(self):
        """Loading secret resources from salvage should reveal them and notify the player."""
        from ..models import Salvage, FleetOrders
        from ..secret_resources import get_secret_resource_name

        game = default_game(stars=5, fleets=1)
        player = game.players.first()
        account = player.account
        fleet = game.fleets.first()

        player.discovered_resource_x = False
        player.save(update_fields=['discovered_resource_x'])
        if account:
            account.discovered_resource_x = False
            account.save(update_fields=['discovered_resource_x'])

        salvage = Salvage.objects.create(
            game=game,
            x=fleet.x,
            y=fleet.y,
            salvage_type=Salvage.TYPE_ANCIENT_DEBRIS,
            ironium_inventory=10,
            boranium_inventory=4,
            germanium_inventory=4,
            resource_x_inventory=12,
        )

        FleetOrders.objects.create(
            game=game,
            fleet=fleet,
            order_type='TRANSFER',
            transfer_type='LOAD',
            target_salvage=salvage,
            transfer_resource_x=10,
        )

        GameTurn(game).fleet_movements()

        player.refresh_from_db()
        if account:
            account.refresh_from_db()
        self.assertTrue(player.discovered_resource_x)
        if account:
            self.assertTrue(account.discovered_resource_x)

        resource_name = get_secret_resource_name('resource_x').lower()
        self.assertTrue(
            player.messages.filter(message__icontains=resource_name).exists()
        )


class TestFleetOrderExecution(TestCase):
    """Test fleet order execution behavior fixes."""

    def test_refuel_order_intercepts_friendly_fleet_and_transfers_fuel(self):
        game = default_game(stars=5, fleets=0)
        player = game.players.first()
        source = Fleet.objects.create(
            game=game,
            player=player,
            name='Tanker',
            x=10,
            y=10,
            ship_count=1,
            integrity=100,
            fuel=30.0,
            max_fuel=50.0,
            max_safe_warp=9,
        )
        target = Fleet.objects.create(
            game=game,
            player=player,
            name='Escort',
            x=10,
            y=10,
            ship_count=1,
            integrity=100,
            fuel=5.0,
            max_fuel=20.0,
            max_safe_warp=9,
        )
        FleetOrders.objects.create(
            game=game,
            fleet=source,
            order_type='REFUEL',
            target_fleet=target,
            transfer_fuel=10.0,
        )

        turn = GameTurn(game)
        turn.fleet_movements()

        source.refresh_from_db()
        target.refresh_from_db()
        self.assertAlmostEqual(source.fuel, 20.0, places=4)
        self.assertAlmostEqual(target.fuel, 15.0, places=4)
        self.assertFalse(source.orders.filter(order_type='REFUEL').exists())

    def test_refuel_order_waits_while_target_is_out_of_range(self):
        game = default_game(stars=5, fleets=0)
        player = game.players.first()
        source = Fleet.objects.create(
            game=game,
            player=player,
            name='Tanker',
            x=10,
            y=10,
            ship_count=1,
            integrity=100,
            fuel=30.0,
            max_fuel=50.0,
            max_safe_warp=3,
        )
        target = Fleet.objects.create(
            game=game,
            player=player,
            name='Escort',
            x=30,
            y=10,
            ship_count=1,
            integrity=100,
            fuel=5.0,
            max_fuel=20.0,
            max_safe_warp=9,
        )
        order = FleetOrders.objects.create(
            game=game,
            fleet=source,
            order_type='REFUEL',
            target_fleet=target,
            transfer_fuel=10.0,
        )

        turn = GameTurn(game)
        turn.fleet_movements()

        source.refresh_from_db()
        target.refresh_from_db()
        self.assertNotEqual((source.x, source.y), (target.x, target.y))
        self.assertAlmostEqual(source.fuel, 30.0, places=4)
        self.assertAlmostEqual(target.fuel, 5.0, places=4)
        self.assertTrue(source.orders.filter(id=order.id).exists())

    def test_refuel_order_executes_after_preceding_intercept_reaches_target(self):
        game = default_game(stars=5, fleets=0)
        player = game.players.first()
        source = Fleet.objects.create(
            game=game,
            player=player,
            name='Tanker',
            x=10,
            y=10,
            ship_count=1,
            integrity=100,
            fuel=30.0,
            max_fuel=50.0,
            max_safe_warp=9,
        )
        target = Fleet.objects.create(
            game=game,
            player=player,
            name='Escort',
            x=12,
            y=10,
            ship_count=1,
            integrity=100,
            fuel=5.0,
            max_fuel=20.0,
            max_safe_warp=9,
        )
        FleetOrders.objects.create(
            game=game,
            fleet=source,
            position=1,
            order_type='INTERCEPT',
            target_fleet=target,
            warpfactor=5,
        )
        FleetOrders.objects.create(
            game=game,
            fleet=source,
            position=2,
            order_type='REFUEL',
            target_fleet=target,
            transfer_fuel=10.0,
        )

        turn = GameTurn(game)
        expected_move_cost = turn._movement_fuel_cost(source, 5)
        turn.fleet_movements()

        source.refresh_from_db()
        target.refresh_from_db()
        self.assertEqual((source.x, source.y), (target.x, target.y))
        self.assertAlmostEqual(source.fuel, 30.0 - expected_move_cost - 10.0, places=4)
        self.assertAlmostEqual(target.fuel, 15.0, places=4)
        self.assertFalse(source.orders.filter(order_type='REFUEL').exists())

    def test_refuel_order_can_transfer_fuel_to_other_players_fleet(self):
        game = default_game(stars=5, fleets=0)
        player = game.players.first()
        game.joinable = True
        game.save(update_fields=['joinable'])
        other_user = User.objects.create_user('refuel_target', 'refuel_target@test.com', 'pass')
        other_account = Account.objects.create(django_user=other_user, alias='RFT')
        other_player = GameFactory(game).join_player(other_account, get_default_race())
        source = Fleet.objects.create(
            game=game,
            player=player,
            name='Tanker',
            x=10,
            y=10,
            ship_count=1,
            integrity=100,
            fuel=30.0,
            max_fuel=50.0,
            max_safe_warp=9,
        )
        target = Fleet.objects.create(
            game=game,
            player=other_player,
            name='Foreign Escort',
            x=10,
            y=10,
            ship_count=1,
            integrity=100,
            fuel=5.0,
            max_fuel=20.0,
            max_safe_warp=9,
        )
        FleetOrders.objects.create(
            game=game,
            fleet=source,
            order_type='REFUEL',
            target_fleet=target,
            transfer_fuel=10.0,
        )

        turn = GameTurn(game)
        turn.fleet_movements()

        source.refresh_from_db()
        target.refresh_from_db()
        self.assertAlmostEqual(source.fuel, 20.0, places=4)
        self.assertAlmostEqual(target.fuel, 15.0, places=4)
        self.assertFalse(source.orders.filter(order_type='REFUEL').exists())

    def test_transfer_orders_execute_once_per_turn(self):
        """Test that repeating transfer orders only execute once per turn."""
        game = default_game(stars=5, fleets=1)
        player = game.players.first()
        fleet = game.fleets.first()
        target_star = game.stars.exclude(pk=player.homeworld.pk).first()

        # Position fleet at target star and clear its cargo
        fleet.x = target_star.x
        fleet.y = target_star.y
        fleet.cargo_capacity = 1000
        fleet.ironium_inventory = 0
        fleet.boranium_inventory = 0
        fleet.germanium_inventory = 0
        fleet.colonists = 0
        fleet.save()

        # Star has plenty of resources
        target_star.ironium_inventory = 1000
        target_star.save()

        # Create REPEATING transfer order for 10 ironium (small amount)
        from dj4xol.models import FleetOrders
        order = FleetOrders.objects.create(
            game=game,
            fleet=fleet,
            order_type='TRANSFER',
            transfer_type='LOAD',
            transfer_ironium=10,
            target_star=target_star,
            repeat=True
        )

        initial_fleet_ironium = fleet.ironium_inventory
        initial_star_ironium = target_star.ironium_inventory

        # Generate one turn
        GameTurn(game).generate_turn()

        fleet.refresh_from_db()
        target_star.refresh_from_db()

        # Should have transferred exactly 10 ironium (once), not multiple times
        self.assertEqual(fleet.ironium_inventory, initial_fleet_ironium + 10)
        self.assertEqual(target_star.ironium_inventory, initial_star_ironium - 10)

        # Order should still exist because it's set to repeat
        self.assertTrue(fleet.orders.filter(repeat=True).exists())

        # Generate another turn - should transfer another 10 (once again)
        fleet_before_second_turn = fleet.ironium_inventory
        star_before_second_turn = target_star.ironium_inventory

        GameTurn(game).generate_turn()

        fleet.refresh_from_db()
        target_star.refresh_from_db()

    def test_multiple_transfer_orders_execute_in_one_turn(self):
        """Test that multiple different transfer orders can execute in one turn."""
        game = default_game(stars=5, fleets=1)
        player = game.players.first()
        fleet = game.fleets.first()
        target_star = game.stars.exclude(pk=player.homeworld.pk).first()

        # Position fleet at target star and clear its cargo
        fleet.x = target_star.x
        fleet.y = target_star.y
        fleet.cargo_capacity = 1000
        fleet.ironium_inventory = 0
        fleet.boranium_inventory = 0
        fleet.germanium_inventory = 0
        fleet.colonists = 0
        fleet.save()

        # Star has plenty of resources
        target_star.ironium_inventory = 1000
        target_star.boranium_inventory = 1000
        target_star.germanium_inventory = 1000
        target_star.save()

        from dj4xol.models import FleetOrders
        # Create multiple transfer orders for different resources
        FleetOrders.objects.create(
            game=game,
            fleet=fleet,
            order_type='TRANSFER',
            transfer_type='LOAD',
            transfer_ironium=10,
            target_star=target_star
        )
        FleetOrders.objects.create(
            game=game,
            fleet=fleet,
            order_type='TRANSFER',
            transfer_type='LOAD',
            transfer_boranium=15,
            target_star=target_star
        )
        FleetOrders.objects.create(
            game=game,
            fleet=fleet,
            order_type='TRANSFER',
            transfer_type='LOAD',
            transfer_germanium=20,
            target_star=target_star
        )

        # Should have 3 orders initially
        self.assertEqual(fleet.orders.count(), 3)

        # Generate one turn - all transfers should execute
        GameTurn(game).generate_turn()

        fleet.refresh_from_db()
        target_star.refresh_from_db()

        # All transfers should have completed in one turn (passthrough behavior)
        self.assertEqual(fleet.ironium_inventory, 10)
        self.assertEqual(fleet.boranium_inventory, 15)
        self.assertEqual(fleet.germanium_inventory, 20)

        # All orders should be completed
        self.assertEqual(fleet.orders.count(), 0)

    def test_fleets_stop_at_move_destinations(self):
        """Test that fleets stop at each move destination for one turn."""
        game = default_game(stars=5, fleets=1)
        player = game.players.first()
        fleet = game.fleets.first()

        # Get two different stars as waypoints
        stars = list(game.stars.exclude(pk=player.homeworld.pk))
        star_a = stars[0]
        star_b = stars[1]

        # Position star_a and star_b close to fleet starting position for easier testing
        start_x, start_y = 50, 50
        fleet.x = start_x
        fleet.y = start_y
        fleet.max_safe_warp = 13  # Prevent warp damage
        fleet.save()

        # Position stars at manageable distances
        star_a.x = start_x + 10  # Close enough to reach in one turn
        star_a.y = start_y
        star_a.save()

        star_b.x = start_x + 20
        star_b.y = start_y
        star_b.save()

        # Create two move orders: go to Star A, then Star B
        from dj4xol.models import FleetOrders
        FleetOrders.objects.create(
            game=game,
            fleet=fleet,
            order_type='MOVE',
            target_star=star_a,
            warpfactor=10  # High speed to ensure arrival
        )
        FleetOrders.objects.create(
            game=game,
            fleet=fleet,
            order_type='MOVE',
            target_star=star_b,
            warpfactor=10
        )

        # Initially should have 2 orders
        self.assertEqual(fleet.orders.count(), 2)

        # Generate turn 1
        GameTurn(game).generate_turn()
        fleet.refresh_from_db()

        # Fleet should have reached Star A and stopped there
        self.assertEqual(fleet.x, star_a.x)
        self.assertEqual(fleet.y, star_a.y)

        # First order should be completed, second should remain
        self.assertEqual(fleet.orders.count(), 1)
        remaining_order = fleet.orders.first()
        self.assertEqual(remaining_order.target_star, star_b)

        # Generate turn 2
        GameTurn(game).generate_turn()
        fleet.refresh_from_db()

        # Now fleet should have reached Star B
        self.assertEqual(fleet.x, star_b.x)
        self.assertEqual(fleet.y, star_b.y)

        # All orders should be completed
        self.assertEqual(fleet.orders.count(), 0)


class TestFleetColoniseOrders(TestCase):
    """Test fleet colonise order functionality."""

    def test_colonise_deposits_all_cargo(self):
        """Colonise order should deposit all fleet cargo to the star."""
        game = default_game(stars=5, fleets=1)
        player = game.players.first()
        fleet = game.fleets.first()
        target_star = game.stars.exclude(pk=player.homeworld.pk).first()

        # Make star unowned, empty, and habitable for player's race
        target_star.player = None
        target_star.colonists = 0
        target_star.ironium_inventory = 0
        target_star.boranium_inventory = 0
        target_star.germanium_inventory = 0
        # Set environment to player's ideal to avoid population decline
        target_star.gravity = player.gravity_center
        target_star.temperature = player.temperature_center
        target_star.radiation = player.radiation_center
        target_star.save()

        # Position fleet at target star with cargo
        fleet.x = target_star.x
        fleet.y = target_star.y
        fleet.ironium_inventory = 100
        fleet.boranium_inventory = 200
        fleet.germanium_inventory = 150
        fleet.colonists = 50  # 50k colonists
        fleet.dry_mass = 0  # Zero dry mass for simpler test
        fleet.save()

        from ..models import FleetOrders
        FleetOrders.objects.create(
            game=game,
            fleet=fleet,
            order_type='COLONISE',
            target_star=target_star
        )

        GameTurn(game).generate_turn()

        target_star.refresh_from_db()

        # All cargo should have transferred to star (minerals exact, colonists may have growth)
        self.assertEqual(target_star.ironium_inventory, 100)
        self.assertEqual(target_star.boranium_inventory, 200)
        self.assertEqual(target_star.germanium_inventory, 150)
        # Colonists: 50k from fleet = 50000 individuals, plus possible growth
        self.assertGreaterEqual(target_star.colonists, 50000)
        # Star should now be owned by player
        self.assertEqual(target_star.player, player)

    def test_colonise_adds_bonus_materials(self):
        """Colonise order should add random bonus materials from dry_mass."""
        game = default_game(stars=5, fleets=1)
        player = game.players.first()
        fleet = game.fleets.first()
        target_star = game.stars.exclude(pk=player.homeworld.pk).first()

        # Clear star resources for clean test, make habitable
        target_star.player = None
        target_star.colonists = 0
        target_star.ironium_inventory = 0
        target_star.boranium_inventory = 0
        target_star.germanium_inventory = 0
        target_star.gravity = player.gravity_center
        target_star.temperature = player.temperature_center
        target_star.radiation = player.radiation_center
        target_star.save()

        # Position fleet at target star with colonists (required) but no minerals
        fleet.x = target_star.x
        fleet.y = target_star.y
        fleet.ironium_inventory = 0
        fleet.boranium_inventory = 0
        fleet.germanium_inventory = 0
        fleet.colonists = 1  # Minimum colonists required
        fleet.dry_mass = 100  # 100kt dry mass
        fleet.save()

        from ..models import FleetOrders
        FleetOrders.objects.create(
            game=game,
            fleet=fleet,
            order_type='COLONISE',
            target_star=target_star
        )

        GameTurn(game).generate_turn()

        target_star.refresh_from_db()

        # Total minerals should equal dry_mass (100kt) since fleet had none
        new_total = (target_star.ironium_inventory +
                    target_star.boranium_inventory +
                    target_star.germanium_inventory)
        self.assertEqual(new_total, 100)

    def test_colonise_on_unowned_star_with_existing_infrastructure_retains_it(self):
        game = default_game(stars=5, fleets=1)
        player = game.players.first()
        fleet = game.fleets.first()
        target_star = game.stars.exclude(pk=player.homeworld.pk).first()

        target_star.player = None
        target_star.colonists = 0
        target_star.mines = 4
        target_star.factories = 3
        target_star.labs = 2
        target_star.defenses = 1
        target_star.shipyards = 1
        target_star.save(update_fields=[
            'player', 'colonists', 'mines', 'factories', 'labs', 'defenses', 'shipyards'
        ])

        fleet_id = fleet.id
        fleet.x = target_star.x
        fleet.y = target_star.y
        fleet.colonists = 10
        fleet.dry_mass = 0
        fleet.save(update_fields=['x', 'y', 'colonists', 'dry_mass'])

        from ..models import FleetOrders
        FleetOrders.objects.create(
            game=game,
            fleet=fleet,
            order_type='COLONISE',
            target_star=target_star
        )

        GameTurn(game).generate_turn()

        target_star.refresh_from_db()
        self.assertFalse(Fleet.objects.filter(id=fleet_id).exists())
        self.assertEqual(target_star.player, player)
        self.assertEqual(target_star.mines, 4)
        self.assertEqual(target_star.factories, 3)
        self.assertEqual(target_star.labs, 2)
        self.assertEqual(target_star.defenses, 1)
        self.assertEqual(target_star.shipyards, 1)

    def test_colonise_destroys_fleet(self):
        """Colonise order should delete the fleet after execution."""
        game = default_game(stars=5, fleets=1)
        player = game.players.first()
        fleet = game.fleets.first()
        fleet_id = fleet.id
        target_star = game.stars.exclude(pk=player.homeworld.pk).first()

        # Position fleet at target star
        fleet.x = target_star.x
        fleet.y = target_star.y
        fleet.colonists = 1
        fleet.save()

        from ..models import FleetOrders
        FleetOrders.objects.create(
            game=game,
            fleet=fleet,
            order_type='COLONISE',
            target_star=target_star
        )

        # Fleet should exist before turn
        self.assertTrue(Fleet.objects.filter(id=fleet_id).exists())

        GameTurn(game).generate_turn()

        # Fleet should be deleted after colonise
        self.assertFalse(Fleet.objects.filter(id=fleet_id).exists())

    def test_colonise_waits_for_arrival(self):
        """Colonise order should wait until fleet arrives at target."""
        game = default_game(stars=5, fleets=1)
        player = game.players.first()
        fleet = game.fleets.first()
        fleet_id = fleet.id
        target_star = game.stars.exclude(pk=player.homeworld.pk).first()
        target_x, target_y = _pin_test_star(target_star, game)

        # Position fleet a short distance from target without landing on it.
        fleet.x = target_x + 10
        fleet.y = target_y
        fleet.colonists = 10  # Has colonists
        fleet.save()

        from ..models import FleetOrders
        FleetOrders.objects.create(
            game=game,
            fleet=fleet,
            order_type='COLONISE',
            target_star=target_star
        )

        GameTurn(game).generate_turn()

        # Fleet should still exist (waiting, not executed)
        self.assertTrue(Fleet.objects.filter(id=fleet_id).exists())

        # Order should still exist
        fleet.refresh_from_db()
        self.assertEqual(fleet.orders.count(), 1)
        self.assertEqual(fleet.orders.first().order_type, 'COLONISE')

    def test_colonise_converts_colonists(self):
        """Colonise should convert fleet colonists (thousands) to star colonists (individuals)."""
        game = default_game(stars=5, fleets=1)
        player = game.players.first()
        fleet = game.fleets.first()
        target_star = game.stars.exclude(pk=player.homeworld.pk).first()

        # Start with empty unowned star, make it habitable
        target_star.player = None
        target_star.colonists = 0
        # Set environment to player's ideal to avoid population decline
        target_star.gravity = player.gravity_center
        target_star.temperature = player.temperature_center
        target_star.radiation = player.radiation_center
        target_star.save()

        # Position fleet at target star with colonists
        fleet.x = target_star.x
        fleet.y = target_star.y
        fleet.colonists = 10  # 10k (10,000) colonists
        fleet.dry_mass = 0
        fleet.save()

        from ..models import FleetOrders
        FleetOrders.objects.create(
            game=game,
            fleet=fleet,
            order_type='COLONISE',
            target_star=target_star
        )

        GameTurn(game).generate_turn()

        target_star.refresh_from_db()

        # Star should have at least 10*1000 = 10000 colonists (may have growth)
        self.assertGreaterEqual(target_star.colonists, 10000)
        # Star should now be owned by player
        self.assertEqual(target_star.player, player)

    def test_colonise_with_move_orders(self):
        """Move then colonise should execute colonise immediately on arrival."""
        game = default_game(stars=5, fleets=1)
        player = game.players.first()
        fleet = game.fleets.first()
        fleet_id = fleet.id
        target_star = game.stars.exclude(pk=player.homeworld.pk).first()
        target_x, target_y = _pin_test_star(target_star, game)

        # Position fleet close to target (will reach in one turn)
        fleet.x = target_x - 5
        fleet.y = target_y
        fleet.ironium_inventory = 50
        fleet.colonists = 1
        fleet.dry_mass = 0
        fleet.max_safe_warp = 13  # Prevent warp damage
        fleet.save()

        original_star_ironium = target_star.ironium_inventory

        from ..models import FleetOrders
        # First move to star
        FleetOrders.objects.create(
            game=game,
            fleet=fleet,
            order_type='MOVE',
            target_star=target_star,
            warpfactor=10
        )
        # Then colonise
        FleetOrders.objects.create(
            game=game,
            fleet=fleet,
            order_type='COLONISE',
            target_star=target_star
        )

        # Turn 1: Fleet reaches star and colonise executes in same turn.
        GameTurn(game).generate_turn()

        # Fleet should be deleted
        self.assertFalse(Fleet.objects.filter(id=fleet_id).exists())

        # Cargo should have transferred
        target_star.refresh_from_db()
        self.assertEqual(target_star.ironium_inventory, original_star_ironium + 50)

    def test_colonise_ignores_repeat(self):
        """Colonise orders should ignore repeat flag (fleet is destroyed)."""
        game = default_game(stars=5, fleets=1)
        player = game.players.first()
        fleet = game.fleets.first()
        fleet_id = fleet.id
        target_star = game.stars.exclude(pk=player.homeworld.pk).first()

        # Position fleet at target
        fleet.x = target_star.x
        fleet.y = target_star.y
        fleet.colonists = 1
        fleet.save()

        from ..models import FleetOrders
        FleetOrders.objects.create(
            game=game,
            fleet=fleet,
            order_type='COLONISE',
            target_star=target_star,
            repeat=True  # Should be ignored
        )

        GameTurn(game).generate_turn()

        # Fleet should be deleted (not repeated)
        self.assertFalse(Fleet.objects.filter(id=fleet_id).exists())

        # No new orders should exist (fleet is gone)
        self.assertEqual(FleetOrders.objects.filter(fleet_id=fleet_id).count(), 0)

    def test_colonise_creates_message(self):
        """Colonise order should create a message for the player."""
        game = default_game(stars=5, fleets=1)
        player = game.players.first()
        fleet = game.fleets.first()
        target_star = game.stars.exclude(pk=player.homeworld.pk).first()

        # Position fleet at target with cargo
        fleet.x = target_star.x
        fleet.y = target_star.y
        fleet.ironium_inventory = 100
        fleet.dry_mass = 50
        fleet.save()

        initial_messages = player.messages.count()

        from ..models import FleetOrders
        FleetOrders.objects.create(
            game=game,
            fleet=fleet,
            order_type='COLONISE',
            target_star=target_star
        )

        GameTurn(game).generate_turn()

        # Should have at least one new message about colonisation
        self.assertGreater(player.messages.count(), initial_messages)

        # Find the colonise message
        colonise_msg = None
        for msg in player.messages.all():
            msg_lower = msg.message.lower()
            if 'colon' in msg_lower or 'established' in msg_lower:
                colonise_msg = msg
                break

        self.assertIsNotNone(colonise_msg, "Expected colonise message not found")

    def test_colonise_without_star_at_location(self):
        """Colonise order at empty space should be removed and message created."""
        game = default_game(stars=5, fleets=1)
        player = game.players.first()
        fleet = game.fleets.first()
        fleet_id = fleet.id

        # Find coordinates within map bounds that have no star
        empty_x, empty_y = 50, 50
        # Make sure no star is at this location (move any that are)
        for star in game.stars.filter(x=empty_x, y=empty_y):
            star.x = empty_x + 10
            star.save()

        # Position fleet at empty coordinates with colonists
        fleet.x = empty_x
        fleet.y = empty_y
        fleet.colonists = 10  # Has colonists
        fleet.save()

        self.assertFalse(game.stars.filter(x=empty_x, y=empty_y).exists())

        initial_messages = player.messages.count()

        from ..models import FleetOrders
        order = FleetOrders.objects.create(
            game=game,
            fleet=fleet,
            order_type='COLONISE',
            x=empty_x,
            y=empty_y
        )

        GameTurn(game).generate_turn()

        # Fleet should still exist (colonise had no target)
        self.assertTrue(Fleet.objects.filter(id=fleet_id).exists())

        # Order should be removed (invalid)
        self.assertFalse(FleetOrders.objects.filter(id=order.id).exists())

        # Should have a message about failed colonisation
        self.assertGreater(player.messages.count(), initial_messages)
        failed_msg = None
        for msg in player.messages.all():
            msg_lower = msg.message.lower()
            if 'abort' in msg_lower or 'cancel' in msg_lower or 'no' in msg_lower:
                failed_msg = msg
                break
        self.assertIsNotNone(failed_msg, "Expected colonise failed message not found")

    def test_colonise_fails_if_star_already_owned_by_self(self):
        """Colonise should fail when the star is already owned by the same player."""
        game = default_game(stars=2)
        player = game.players.first()
        star = player.homeworld

        fleet = Fleet.objects.create(
            game=game,
            player=player,
            name="Coloniser",
            x=star.x,
            y=star.y,
            colonists=10
        )

        from ..models import FleetOrders
        FleetOrders.objects.create(
            game=game,
            fleet=fleet,
            order_type='COLONISE',
            target_star=star
        )

        GameTurn(game).generate_turn()

        fleet.refresh_from_db()
        self.assertTrue(Fleet.objects.filter(id=fleet.id).exists())
        self.assertFalse(fleet.orders.filter(order_type='COLONISE').exists())
        self.assertTrue(player.messages.filter(message__icontains="already").exists())

    def test_colonise_fails_if_star_owned_by_other(self):
        """Colonise should fail when the star is owned by another player."""
        game = default_game(stars=2)
        player = game.players.first()

        other_player = Player.objects.filter(game=game).exclude(id=player.id).first()
        if not other_player:
            other_user = User.objects.create_user('other_owner', 'o@test.com', 'pass')
            other_account = Account.objects.create(django_user=other_user)
            other_player = Player.objects.create(
                game=game,
                account=other_account,
                race_type=player.race_type,
            )

        star = game.stars.exclude(pk=player.homeworld.pk).first()
        star.player = other_player
        star.colonists = 10000
        star.save()

        fleet = Fleet.objects.create(
            game=game,
            player=player,
            name="Coloniser",
            x=star.x,
            y=star.y,
            colonists=10
        )

        from ..models import FleetOrders
        FleetOrders.objects.create(
            game=game,
            fleet=fleet,
            order_type='COLONISE',
            target_star=star
        )

        GameTurn(game).generate_turn()

        fleet.refresh_from_db()
        self.assertTrue(Fleet.objects.filter(id=fleet.id).exists())
        self.assertFalse(fleet.orders.filter(order_type='COLONISE').exists())
        self.assertTrue(player.messages.filter(message__icontains=other_player.name).exists())

    def test_colonise_fails_without_colonists(self):
        """Colonise order should fail if fleet has no colonists."""
        game = default_game(stars=5, fleets=1)
        player = game.players.first()
        fleet = game.fleets.first()
        fleet_id = fleet.id
        target_star = game.stars.exclude(pk=player.homeworld.pk).first()

        # Position fleet at target star but with NO colonists
        fleet.x = target_star.x
        fleet.y = target_star.y
        fleet.colonists = 0  # No colonists!
        fleet.ironium_inventory = 100
        fleet.save()

        initial_messages = player.messages.count()

        from ..models import FleetOrders
        order = FleetOrders.objects.create(
            game=game,
            fleet=fleet,
            order_type='COLONISE',
            target_star=target_star
        )

        GameTurn(game).generate_turn()

        # Fleet should still exist (colonise failed)
        self.assertTrue(Fleet.objects.filter(id=fleet_id).exists())

        # Order should be removed
        self.assertFalse(FleetOrders.objects.filter(id=order.id).exists())

        # Fleet should still have its cargo (nothing transferred)
        fleet.refresh_from_db()
        self.assertEqual(fleet.ironium_inventory, 100)

        # Should have a message about failed colonisation (no colonists)
        self.assertGreater(player.messages.count(), initial_messages)
        failed_msg = None
        for msg in player.messages.all():
            msg_lower = msg.message.lower()
            if 'colonist' in msg_lower and ('no' in msg_lower or 'cannot' in msg_lower):
                failed_msg = msg
                break
        self.assertIsNotNone(failed_msg, "Expected 'no colonists' message not found")
        # Failed colonise messages should be priority
        self.assertTrue(failed_msg.priority, "Failed colonise message should have priority flag")


class TestWarpDamage(TestCase):
    """Tests for fleet damage from exceeding safe warp speed.

    All tests use fixed positions (1,1) -> (50,50) to ensure fleets stay
    within map bounds (100x100) and don't complete the journey in one turn.
    """

    def test_no_damage_at_safe_warp(self):
        """Fleet travelling at or below max_safe_warp takes no damage."""
        from ..models import FleetOrders, Fleet

        game = default_game()
        player = game.players.first()

        fleet = Fleet.objects.create(
            game=game, player=player, name="Safe Fleet",
            x=1, y=1, max_safe_warp=5, integrity=100
        )

        FleetOrders.objects.create(
            game=game, fleet=fleet, order_type='MOVE',
            x=50, y=50, warpfactor=5
        )

        GameTurn(game).generate_turn()

        fleet.refresh_from_db()
        self.assertEqual(fleet.integrity, 100)

    def test_no_damage_below_safe_warp(self):
        """Fleet travelling below max_safe_warp takes no damage."""
        from ..models import FleetOrders, Fleet

        game = default_game()
        player = game.players.first()

        fleet = Fleet.objects.create(
            game=game, player=player, name="Slow Fleet",
            x=1, y=1, max_safe_warp=8, integrity=100
        )

        FleetOrders.objects.create(
            game=game, fleet=fleet, order_type='MOVE',
            x=50, y=50, warpfactor=3
        )

        GameTurn(game).generate_turn()

        fleet.refresh_from_db()
        self.assertEqual(fleet.integrity, 100)

    def test_warp_9_below_safe_warp_no_damage(self):
        """Warp 9 with max_safe_warp=13 takes no damage."""
        from ..models import FleetOrders, Fleet

        game = default_game()
        player = game.players.first()

        fleet = Fleet.objects.create(
            game=game, player=player, name="Safe Fast Fleet",
            x=1, y=1, max_safe_warp=13, integrity=100
        )

        FleetOrders.objects.create(
            game=game, fleet=fleet, order_type='MOVE',
            x=50, y=50, warpfactor=9
        )

        GameTurn(game).generate_turn()

        fleet.refresh_from_db()
        self.assertEqual(fleet.integrity, 100)

    def test_zero_integrity_fleet_destroyed_at_turn_end(self):
        """Fleets with 0 integrity are destroyed during check_damaged_fleets."""
        from ..models import Fleet

        game = default_game()
        player = game.players.first()

        # Create fleet with 0 integrity
        fleet = Fleet.objects.create(
            game=game, player=player, name="Broken Fleet",
            x=50, y=50, max_safe_warp=13, integrity=0
        )
        fleet_id = fleet.id

        initial_messages = player.messages.count()

        GameTurn(game).generate_turn()

        # Fleet should be destroyed
        self.assertFalse(Fleet.objects.filter(id=fleet_id).exists())

        # Should have a destruction message
        self.assertGreater(player.messages.count(), initial_messages)

    def test_damage_when_roll_fails(self):
        """Fleet takes damage when roll_chance returns True."""
        from ..models import FleetOrders, Fleet

        game = default_game()
        player = game.players.first()

        fleet = Fleet.objects.create(
            game=game, player=player, name="Damaged Fleet",
            x=1, y=1, max_safe_warp=5, integrity=100
        )

        FleetOrders.objects.create(
            game=game, fleet=fleet, order_type='MOVE',
            x=50, y=50, warpfactor=9  # 4 excess
        )

        # Mock roll_chance to return True (damage occurs)
        # and the loss calculations
        with patch('dj4xol.turn.roll_chance', return_value=True), \
             patch('dj4xol.turn.calculate_integrity_loss', return_value=20), \
             patch('dj4xol.turn.calculate_cargo_loss_percent', return_value=0.1):
            GameTurn(game).generate_turn()

        fleet.refresh_from_db()
        self.assertEqual(fleet.integrity, 80)  # 100 - 20

    def test_no_damage_when_roll_passes(self):
        """Fleet survives when roll_chance returns False."""
        from ..models import FleetOrders, Fleet

        game = default_game()
        player = game.players.first()

        fleet = Fleet.objects.create(
            game=game, player=player, name="Lucky Fleet",
            x=1, y=1, max_safe_warp=5, integrity=100
        )

        FleetOrders.objects.create(
            game=game, fleet=fleet, order_type='MOVE',
            x=50, y=50, warpfactor=9  # 4 excess
        )

        # Mock roll_chance to return False (no damage)
        with patch('dj4xol.turn.roll_chance', return_value=False):
            GameTurn(game).generate_turn()

        fleet.refresh_from_db()
        self.assertEqual(fleet.integrity, 100)

    def test_overmax_damage_risk_only_checked_when_order_starts(self):
        """Overmax movement should not re-roll damage on later turns of the same order."""
        from ..models import FleetOrders, Fleet

        game = default_game()
        player = game.players.first()

        fleet = Fleet.objects.create(
            game=game, player=player, name="Persistent Runner",
            x=1, y=1, max_safe_warp=5, integrity=100
        )

        order = FleetOrders.objects.create(
            game=game, fleet=fleet, order_type='MOVE',
            x=90, y=90, warpfactor=9
        )

        with patch('dj4xol.turn.roll_chance', side_effect=[False, True]), \
             patch('dj4xol.turn.calculate_integrity_loss', return_value=25), \
             patch('dj4xol.turn.calculate_cargo_loss_percent', return_value=0.10):
            GameTurn(game).generate_turn()
            GameTurn(game).generate_turn()

        fleet.refresh_from_db()
        order.refresh_from_db()
        self.assertEqual(fleet.integrity, 100)
        self.assertTrue(order.overmax_risk_checked)
        self.assertEqual(order.warpfactor, 9)

    def test_repeat_order_restores_original_warpfactor_after_overmax_damage(self):
        """Repeated moves should queue with the originally ordered warp, not the reduced one."""
        from ..models import FleetOrders, Fleet

        game = default_game()
        player = game.players.first()

        fleet = Fleet.objects.create(
            game=game, player=player, name="Repeat Runner",
            x=10, y=10, max_safe_warp=6, integrity=100
        )

        order = FleetOrders.objects.create(
            game=game,
            fleet=fleet,
            order_type='MOVE',
            repeat=True,
            x=60,
            y=10,
            warpfactor=3,
            original_warpfactor=9,
            overmax_risk_checked=True,
        )

        GameTurn(game)._handle_repeating_order(order)

        repeat_order = FleetOrders.objects.exclude(id=order.id).get()
        self.assertEqual(repeat_order.warpfactor, 9)
        self.assertEqual(repeat_order.original_warpfactor, 9)
        self.assertFalse(repeat_order.overmax_risk_checked)

    def test_warp_10_destruction_when_first_roll_true(self):
        """Fleet at warp 10+ is destroyed when first roll_chance returns True."""
        from ..models import FleetOrders, Fleet

        game = default_game()
        player = game.players.first()

        fleet = Fleet.objects.create(
            game=game, player=player, name="Doomed Fleet",
            x=1, y=1, max_safe_warp=5, integrity=100
        )
        fleet_id = fleet.id

        FleetOrders.objects.create(
            game=game, fleet=fleet, order_type='MOVE',
            x=50, y=50, warpfactor=10
        )

        # First call is destruction check, return True
        with patch('dj4xol.turn.roll_chance', return_value=True):
            GameTurn(game).generate_turn()

        self.assertFalse(Fleet.objects.filter(id=fleet_id).exists())

    def test_warp_10_survives_when_rolls_false(self):
        """Fleet at warp 10+ survives when roll_chance returns False."""
        from ..models import FleetOrders, Fleet

        game = default_game()
        player = game.players.first()

        fleet = Fleet.objects.create(
            game=game, player=player, name="Lucky Fleet",
            x=1, y=1, max_safe_warp=5, integrity=100
        )
        fleet_id = fleet.id

        FleetOrders.objects.create(
            game=game, fleet=fleet, order_type='MOVE',
            x=50, y=50, warpfactor=10
        )

        # Both destruction and damage rolls fail
        with patch('dj4xol.turn.roll_chance', return_value=False):
            GameTurn(game).generate_turn()

        self.assertTrue(Fleet.objects.filter(id=fleet_id).exists())
        fleet.refresh_from_db()
        self.assertEqual(fleet.integrity, 100)

    def test_cargo_loss_on_damage(self):
        """Cargo is lost when fleet takes warp damage."""
        from ..models import FleetOrders, Fleet

        game = default_game()
        player = game.players.first()

        fleet = Fleet.objects.create(
            game=game, player=player, name="Cargo Fleet",
            x=1, y=1, max_safe_warp=5, integrity=100,
            ironium_inventory=1000, boranium_inventory=1000,
            germanium_inventory=1000
        )

        FleetOrders.objects.create(
            game=game, fleet=fleet, order_type='MOVE',
            x=50, y=50, warpfactor=8  # 3 excess
        )

        # Force damage with 30% cargo loss
        with patch('dj4xol.turn.roll_chance', return_value=True), \
             patch('dj4xol.turn.calculate_integrity_loss', return_value=10), \
             patch('dj4xol.turn.calculate_cargo_loss_percent', return_value=0.30):
            GameTurn(game).generate_turn()

        fleet.refresh_from_db()
        self.assertEqual(fleet.ironium_inventory, 700)
        self.assertEqual(fleet.boranium_inventory, 700)
        self.assertEqual(fleet.germanium_inventory, 700)

    def test_colonist_death_on_damage(self):
        """Colonists die when fleet takes warp damage."""
        from ..models import FleetOrders, Fleet

        game = default_game()
        player = game.players.first()

        fleet = Fleet.objects.create(
            game=game, player=player, name="Colonist Fleet",
            x=1, y=1, max_safe_warp=5, integrity=100,
            colonists=1000
        )

        FleetOrders.objects.create(
            game=game, fleet=fleet, order_type='MOVE',
            x=50, y=50, warpfactor=8  # 3 excess
        )

        # Force damage with 20% cargo/colonist loss
        with patch('dj4xol.turn.roll_chance', return_value=True), \
             patch('dj4xol.turn.calculate_integrity_loss', return_value=10), \
             patch('dj4xol.turn.calculate_cargo_loss_percent', return_value=0.20):
            GameTurn(game).generate_turn()

        fleet.refresh_from_db()
        self.assertEqual(fleet.colonists, 800)

    def test_damage_message_created(self):
        """Message is created when fleet takes damage."""
        from ..models import FleetOrders, Fleet

        game = default_game()
        player = game.players.first()

        initial_messages = player.messages.count()

        fleet = Fleet.objects.create(
            game=game, player=player, name="Msg Fleet",
            x=1, y=1, max_safe_warp=5, integrity=100
        )

        FleetOrders.objects.create(
            game=game, fleet=fleet, order_type='MOVE',
            x=50, y=50, warpfactor=8
        )

        # Force damage
        with patch('dj4xol.turn.roll_chance', return_value=True), \
             patch('dj4xol.turn.calculate_integrity_loss', return_value=10), \
             patch('dj4xol.turn.calculate_cargo_loss_percent', return_value=0.05):
            GameTurn(game).generate_turn()

        # Check for damage message
        self.assertGreater(player.messages.count(), initial_messages)
        damage_msg = player.messages.filter(message__icontains='warp').first()
        self.assertIsNotNone(damage_msg)

    def test_destruction_message_has_priority(self):
        """Priority message is created when fleet is destroyed at warp 10."""
        from ..models import FleetOrders, Fleet

        game = default_game()
        player = game.players.first()

        fleet = Fleet.objects.create(
            game=game, player=player, name="Doomed Fleet",
            x=1, y=1, max_safe_warp=5, integrity=100
        )
        fleet_id = fleet.id

        FleetOrders.objects.create(
            game=game, fleet=fleet, order_type='MOVE',
            x=50, y=50, warpfactor=10
        )

        # Force destruction
        with patch('dj4xol.turn.roll_chance', return_value=True):
            GameTurn(game).generate_turn()

        # Fleet destroyed
        self.assertFalse(Fleet.objects.filter(id=fleet_id).exists())

        # Check for priority destruction message
        destruction_msg = player.messages.filter(priority=True).first()
        self.assertIsNotNone(destruction_msg)

    def test_integrity_loss_destroys_fleet(self):
        """Fleet is destroyed when integrity reaches 0 from damage."""
        from ..models import FleetOrders, Fleet

        game = default_game()
        player = game.players.first()

        # Create fleet with low integrity
        fleet = Fleet.objects.create(
            game=game, player=player, name="Weak Fleet",
            x=1, y=1, max_safe_warp=5, integrity=10
        )
        fleet_id = fleet.id

        FleetOrders.objects.create(
            game=game, fleet=fleet, order_type='MOVE',
            x=50, y=50, warpfactor=9  # 4 excess
        )

        # Force damage that exceeds integrity
        with patch('dj4xol.turn.roll_chance', return_value=True), \
             patch('dj4xol.turn.calculate_integrity_loss', return_value=50), \
             patch('dj4xol.turn.calculate_cargo_loss_percent', return_value=0.05):
            GameTurn(game).generate_turn()

        # Fleet should be destroyed (10 - 50 <= 0)
        self.assertFalse(Fleet.objects.filter(id=fleet_id).exists())

    def test_warp_speed_reduced_after_damage(self):
        """Order warp speed is reduced after fleet takes damage."""
        from ..models import FleetOrders, Fleet

        game = default_game()
        player = game.players.first()

        # Place fleet near center of map, destination within bounds but far
        fleet = Fleet.objects.create(
            game=game, player=player, name="Fast Fleet",
            x=10, y=50, max_safe_warp=6, integrity=100
        )

        # Destination 50 ly away (will take multiple turns at warp 9)
        order = FleetOrders.objects.create(
            game=game, fleet=fleet, order_type='MOVE',
            x=60, y=50, warpfactor=9
        )

        # Force damage with low integrity loss (fleet survives)
        with patch('dj4xol.turn.roll_chance', return_value=True), \
             patch('dj4xol.turn.calculate_integrity_loss', return_value=5), \
             patch('dj4xol.turn.calculate_cargo_loss_percent', return_value=0.02):
            GameTurn(game).generate_turn()

        order.refresh_from_db()
        # Expected: min(max(2, 6//2), 6) = min(max(2, 3), 6) = 3
        self.assertEqual(order.warpfactor, 3)


class TestWormholeDriveMovement(TestCase):
    def test_wormhole_jump_can_arrive_exactly(self):
        game = default_game(stars=2)
        game.random_events = False
        game.save(update_fields=['random_events'])
        player = game.players.first()

        fleet = Fleet.objects.create(
            game=game,
            player=player,
            name='Wormhole Scout',
            x=0,
            y=0,
            has_wormhole_drive=True,
            fuel=999.0,
            max_fuel=999.0,
            max_safe_warp=5,
        )
        order = FleetOrders.objects.create(
            game=game, fleet=fleet, order_type='MOVE', x=40, y=40, warpfactor=14
        )
        destruction_chance = float(fleet.wormhole_destruction_chance or 0.0)

        def roll_map(chance):
            if abs(chance - destruction_chance) < 1e-9:
                return False
            if abs(chance - 0.20) < 1e-9:
                return False
            if abs(chance - 0.60) < 1e-9:
                return True
            if abs(chance - 0.75) < 1e-9:
                return False
            return False

        with patch('dj4xol.turn.roll_chance', side_effect=roll_map):
            GameTurn(game).generate_turn()

        fleet.refresh_from_db()
        self.assertEqual((fleet.x, fleet.y), (40, 40))
        self.assertFalse(FleetOrders.objects.filter(id=order.id).exists())

    def test_wormhole_jump_can_deviate(self):
        game = default_game(stars=2)
        game.random_events = False
        game.save(update_fields=['random_events'])
        player = game.players.first()

        fleet = Fleet.objects.create(
            game=game,
            player=player,
            name='Wormhole Drifter',
            x=0,
            y=0,
            has_wormhole_drive=True,
            fuel=999.0,
            max_fuel=999.0,
            max_safe_warp=5,
        )
        order = FleetOrders.objects.create(
            game=game, fleet=fleet, order_type='MOVE', x=50, y=50, warpfactor=14
        )
        destruction_chance = float(fleet.wormhole_destruction_chance or 0.0)

        def roll_map(chance):
            if abs(chance - destruction_chance) < 1e-9:
                return False
            if abs(chance - 0.20) < 1e-9:
                return False
            if abs(chance - 0.60) < 1e-9:
                return False
            if abs(chance - 0.75) < 1e-9:
                return True
            return False

        with patch('dj4xol.turn.roll_chance', side_effect=roll_map), \
             patch('dj4xol.turn.random.uniform', side_effect=[0.0, 7.0]):
            GameTurn(game).generate_turn()

        fleet.refresh_from_db()
        self.assertEqual((fleet.x, fleet.y), (57, 50))
        self.assertTrue(FleetOrders.objects.filter(id=order.id).exists())

    def test_wormhole_non_arrival_no_longer_stalls_movement(self):
        game = default_game(stars=2)
        game.random_events = False
        game.save(update_fields=['random_events'])
        player = game.players.first()

        fleet = Fleet.objects.create(
            game=game,
            player=player,
            name='Wormhole Reliable',
            x=0,
            y=0,
            has_wormhole_drive=True,
            fuel=999.0,
            max_fuel=999.0,
            max_safe_warp=5,
        )
        order = FleetOrders.objects.create(
            game=game, fleet=fleet, order_type='MOVE', x=40, y=40, warpfactor=14
        )
        destruction_chance = float(fleet.wormhole_destruction_chance or 0.0)

        def roll_map(chance):
            if abs(chance - destruction_chance) < 1e-9:
                return False
            if abs(chance - 0.20) < 1e-9:
                return False
            if abs(chance - 0.60) < 1e-9:
                return False
            if abs(chance - 0.75) < 1e-9:
                return False
            return False

        with patch('dj4xol.turn.roll_chance', side_effect=roll_map):
            GameTurn(game).generate_turn()

        fleet.refresh_from_db()
        self.assertEqual((fleet.x, fleet.y), (40, 40))
        self.assertFalse(FleetOrders.objects.filter(id=order.id).exists())

    def test_wormhole_jump_can_take_integrity_damage(self):
        game = default_game(stars=2)
        game.random_events = False
        game.save(update_fields=['random_events'])
        player = game.players.first()

        fleet = Fleet.objects.create(
            game=game,
            player=player,
            name='Wormhole Bruiser',
            x=0,
            y=0,
            has_wormhole_drive=True,
            integrity=100,
            fuel=999.0,
            max_fuel=999.0,
            max_safe_warp=5,
        )
        order = FleetOrders.objects.create(
            game=game, fleet=fleet, order_type='MOVE', x=100, y=0, warpfactor=14
        )
        destruction_chance = float(fleet.wormhole_destruction_chance or 0.0)

        def roll_map(chance):
            if abs(chance - destruction_chance) < 1e-9:
                return False
            if abs(chance - 0.20) < 1e-9:
                return True
            if abs(chance - 0.60) < 1e-9:
                return False
            return False

        with patch('dj4xol.turn.roll_chance', side_effect=roll_map), \
             patch('dj4xol.turn.random.randint', return_value=1):
            result = GameTurn(game)._execute_wormhole_jump(
                fleet, order, 100, 0, 100.0
            )

        self.assertEqual(result, 'arrived')
        self.assertEqual(fleet.integrity, 99)

    def test_wormhole_jump_can_destroy_fleet(self):
        game = default_game(stars=2)
        game.random_events = False
        game.save(update_fields=['random_events'])
        player = game.players.first()

        fleet = Fleet.objects.create(
            game=game,
            player=player,
            name='Wormhole Casualty',
            x=0,
            y=0,
            has_wormhole_drive=True,
            fuel=999.0,
            max_fuel=999.0,
            max_safe_warp=5,
        )
        FleetOrders.objects.create(
            game=game, fleet=fleet, order_type='MOVE', x=60, y=60, warpfactor=14
        )
        destruction_chance = float(fleet.wormhole_destruction_chance or 0.0)

        def roll_map(chance):
            if abs(chance - destruction_chance) < 1e-9:
                return True
            return False

        with patch('dj4xol.turn.roll_chance', side_effect=roll_map):
            GameTurn(game).generate_turn()

        self.assertFalse(Fleet.objects.filter(id=fleet.id).exists())
        self.assertTrue(
            player.messages.filter(message__icontains='wormhole').exists()
        )

    def test_wormhole_destruction_can_spawn_nearby_rift(self):
        game = default_game(stars=2)
        game.random_events = False
        game.anomalies_enabled = True
        game.save(update_fields=['random_events', 'anomalies_enabled'])
        player = game.players.first()

        fleet = Fleet.objects.create(
            game=game,
            player=player,
            name='Wormhole Rift Seed',
            x=20,
            y=20,
            has_wormhole_drive=True,
            fuel=999.0,
            max_fuel=999.0,
            max_safe_warp=5,
        )
        FleetOrders.objects.create(
            game=game, fleet=fleet, order_type='MOVE', x=60, y=60, warpfactor=14
        )
        destruction_chance = float(fleet.wormhole_destruction_chance or 0.0)

        def roll_map(chance):
            if abs(chance - destruction_chance) < 1e-9:
                return True
            return False

        with patch('dj4xol.turn.roll_chance', side_effect=roll_map), \
             patch('dj4xol.turn.random.random', return_value=0.0), \
             patch('dj4xol.turn.random.shuffle', lambda x: None):
            GameTurn(game)._execute_wormhole_jump(
                fleet, fleet.orders.first(), 60, 60, 60.0
            )

        rift = Anomaly.objects.filter(game=game, anomaly_type=Anomaly.TYPE_RIFT).first()
        self.assertIsNotNone(rift)
        if rift is not None:
            self.assertTrue(30 <= int(rift.stability) <= 91)
            start_dist = (((rift.x - 20) ** 2) + ((rift.y - 20) ** 2)) ** 0.5
            dest_dist = (((rift.x - 60) ** 2) + ((rift.y - 60) ** 2)) ** 0.5
            self.assertTrue(
                (4.0 <= start_dist <= 9.0) or (4.0 <= dest_dist <= 9.0)
            )
            self.assertFalse(Star.objects.filter(game=game, x=rift.x, y=rift.y).exists())

    def test_wormhole_destruction_can_spawn_nearby_wormhole(self):
        game = default_game(stars=2)
        game.random_events = False
        game.anomalies_enabled = True
        game.save(update_fields=['random_events', 'anomalies_enabled'])
        player = game.players.first()

        fleet = Fleet.objects.create(
            game=game,
            player=player,
            name='Wormhole Seed',
            x=20,
            y=20,
            has_wormhole_drive=True,
            fuel=999.0,
            max_fuel=999.0,
            max_safe_warp=5,
        )
        FleetOrders.objects.create(
            game=game, fleet=fleet, order_type='MOVE', x=60, y=60, warpfactor=14
        )
        destruction_chance = float(fleet.wormhole_destruction_chance or 0.0)

        def roll_map(chance):
            if abs(chance - destruction_chance) < 1e-9:
                return True
            return False

        random_values = [0.04, 0.6, 0.1, 0.2]
        with patch('dj4xol.turn.roll_chance', side_effect=roll_map), \
             patch('dj4xol.turn.random.random', side_effect=lambda: random_values.pop(0)), \
             patch('dj4xol.turn.random.shuffle', lambda x: None):
            GameTurn(game)._execute_wormhole_jump(
                fleet, fleet.orders.first(), 60, 60, 60.0
            )

        wormholes = list(Anomaly.objects.filter(
            game=game, anomaly_type=Anomaly.TYPE_WORMHOLE
        ).order_by('id'))
        self.assertEqual(len(wormholes), 2)
        for wormhole in wormholes:
            self.assertTrue(20 <= int(wormhole.stability) <= 60)
            self.assertFalse(Star.objects.filter(
                game=game, x=wormhole.x, y=wormhole.y
            ).exists())
        self.assertTrue(
            (4.0 <= (((wormholes[0].x - 20) ** 2 + (wormholes[0].y - 20) ** 2) ** 0.5) <= 9.0)
            or (4.0 <= (((wormholes[0].x - 60) ** 2 + (wormholes[0].y - 60) ** 2) ** 0.5) <= 9.0)
        )
        self.assertTrue(wormholes[0].wormhole_pair_id in [w.id for w in wormholes])
        self.assertTrue(wormholes[1].wormhole_pair_id in [w.id for w in wormholes])

    def test_wormhole_wander_avoids_stars(self):
        game = default_game(stars=1, fleets=0)
        game.anomalies_enabled = True
        game.save(update_fields=['anomalies_enabled'])
        star = game.stars.first()
        star.x = 11
        star.y = 10
        star.save(update_fields=['x', 'y'])

        wormhole = Anomaly.objects.create(
            game=game,
            x=10,
            y=10,
            name='Wanderer',
            anomaly_type=Anomaly.TYPE_WORMHOLE,
            stability=0,
        )

        def custom_shuffle(items):
            items.sort(key=lambda item: 0 if item == (1, 0) else (1 if item == (0, 0) else 2))

        with patch('dj4xol.turn.random.shuffle', custom_shuffle):
            GameTurn(game).move_wormholes()

        wormhole.refresh_from_db()
        self.assertNotEqual((wormhole.x, wormhole.y), (star.x, star.y))


class TestFleetFuel(TestCase):
    def test_fuel_cost_scales_with_ship_count(self):
        from ..models import Fleet

        game = default_game()
        player = game.players.first()

        single = Fleet.objects.create(
            game=game, player=player, name="Single",
            x=1, y=1, max_safe_warp=6, ship_count=1,
            fuel_efficiency=1.0, overmax_fuel_penalty=1.0,
        )
        group = Fleet.objects.create(
            game=game, player=player, name="Group",
            x=1, y=1, max_safe_warp=6, ship_count=4,
            fuel_efficiency=1.0, overmax_fuel_penalty=1.0,
        )

        gt = GameTurn(game)
        single_cost = gt._movement_fuel_cost(single, 6)
        group_cost = gt._movement_fuel_cost(group, 6)
        self.assertAlmostEqual(group_cost, single_cost * 4.0, places=4)

    def test_movement_consumes_fuel(self):
        from ..models import Fleet

        game = default_game()
        player = game.players.first()
        star = player.homeworld

        fleet = Fleet.objects.create(
            game=game, player=player, name="Fuel Fleet",
            x=star.x, y=star.y, max_safe_warp=6, fuel=10.0, max_fuel=10.0
        )
        turn = GameTurn(game)
        cost = turn._movement_fuel_cost(fleet, 6)
        consumed = turn._consume_movement_fuel(fleet, 6)
        self.assertTrue(consumed)
        self.assertAlmostEqual(fleet.fuel, 10.0 - cost, places=4)
        self.assertGreaterEqual(fleet.fuel, 0.0)

    def test_movement_blocked_by_insufficient_fuel(self):
        from ..models import FleetOrders, Fleet

        game = default_game()
        player = game.players.first()
        star = player.homeworld
        star.shipyards = 0
        star.save(update_fields=['shipyards'])

        fleet = Fleet.objects.create(
            game=game, player=player, name="Dry Fleet",
            x=star.x, y=star.y, max_safe_warp=6, fuel=1.0, max_fuel=10.0,
            heading=87.0, travel_warp=4,
        )
        FleetOrders.objects.create(
            game=game, fleet=fleet, order_type='MOVE',
            x=star.x + 20, y=star.y, warpfactor=6
        )

        with patch('dj4xol.turn.roll_chance', return_value=False):
            GameTurn(game).generate_turn()
        fleet.refresh_from_db()
        self.assertEqual((fleet.x, fleet.y), (star.x, star.y))
        self.assertAlmostEqual(fleet.fuel, 1.0, places=4)
        self.assertEqual(fleet.travel_warp, 0)
        self.assertAlmostEqual(float(fleet.heading), 87.0, places=1)
        self.assertEqual(fleet.orders.count(), 1)

    def test_bussard_collectors_can_enable_reduced_warp_move(self):
        from ..models import FleetOrders, Fleet

        game = default_game()
        player = game.players.first()
        star = player.homeworld
        star.shipyards = 0
        star.save(update_fields=['shipyards'])
        # Keep this test deterministic: avoid random salvage hazards and map-edge deletion.
        game.salvages.all().delete()
        start_messages = player.messages.count()
        start_x = 10
        start_y = 10

        fleet = Fleet.objects.create(
            game=game, player=player, name="Collector Fleet",
            x=start_x, y=start_y, max_safe_warp=6, fuel=0.2, max_fuel=10.0
        )
        FleetOrders.objects.create(
            game=game, fleet=fleet, order_type='MOVE',
            x=start_x + 20, y=start_y, warpfactor=6
        )

        turn = GameTurn(game)
        fuel_gain = 1.0
        projected_fuel = float(fleet.fuel) + fuel_gain
        expected_warp = 0
        for candidate in range(6, 0, -1):
            if turn._movement_fuel_cost(fleet, candidate) <= projected_fuel:
                expected_warp = candidate
                break

        with patch('dj4xol.turn.roll_chance', return_value=True), \
             patch('dj4xol.turn.random.randint', return_value=1):
            GameTurn(game).generate_turn()

        fleet.refresh_from_db()
        self.assertGreater(fleet.x, start_x)
        self.assertLess(fleet.x, start_x + 6)
        self.assertEqual(fleet.travel_warp, expected_warp)
        self.assertLess(fleet.fuel, projected_fuel)
        self.assertGreater(player.messages.count(), start_messages)
        msg = player.messages.order_by('-id').first()
        self.assertIn('ordered warp 6', msg.message)
        self.assertIn('warp %s' % expected_warp, msg.message)

    def test_wormhole_jump_fuel_cost_basic_drive_is_5_mg_per_ly(self):
        from ..models import Fleet

        game = default_game()
        player = game.players.first()
        fleet = Fleet.objects.create(
            game=game, player=player, name="Basic Wormhole",
            x=1, y=1, has_wormhole_drive=True, max_safe_warp=5, fuel=999.0, max_fuel=999.0
        )

        turn = GameTurn(game)
        self.assertAlmostEqual(turn._wormhole_jump_fuel_cost(fleet, 10.0), 50.0, places=4)

    def test_wormhole_jump_fuel_cost_advanced_drive_is_4_mg_per_ly(self):
        from ..models import Fleet

        game = default_game()
        player = game.players.first()
        fleet = Fleet.objects.create(
            game=game, player=player, name="Advanced Wormhole",
            x=1, y=1, has_wormhole_drive=True, max_safe_warp=9,
            wormhole_fuel_per_ly=4.0, fuel=999.0, max_fuel=999.0
        )

        turn = GameTurn(game)
        self.assertAlmostEqual(turn._wormhole_jump_fuel_cost(fleet, 10.0), 40.0, places=4)

    def test_fuel_factory_generates_fuel_when_stopped(self):
        from ..models import Fleet

        game = default_game()
        player = game.players.first()
        fleet = Fleet.objects.create(
            game=game,
            player=player,
            name="Stopped Refinery",
            x=1,
            y=1,
            fuel=3.0,
            max_fuel=10.0,
            fuel_factory_mg_per_year=1.0,
            fuel_factory_max_warp=0,
            travel_warp=0,
        )

        GameTurn(game).apply_fuel_factories()

        fleet.refresh_from_db()
        self.assertAlmostEqual(fleet.fuel, 4.0, places=4)

    def test_fuel_factory_generates_fuel_at_max_warp_threshold(self):
        from ..models import Fleet

        game = default_game()
        player = game.players.first()
        fleet = Fleet.objects.create(
            game=game,
            player=player,
            name="Cruising Refinery",
            x=1,
            y=1,
            fuel=3.0,
            max_fuel=10.0,
            fuel_factory_mg_per_year=1.0,
            fuel_factory_max_warp=5,
            travel_warp=5,
        )

        GameTurn(game).apply_fuel_factories()

        fleet.refresh_from_db()
        self.assertAlmostEqual(fleet.fuel, 4.0, places=4)

    def test_fuel_factory_stops_above_limit_and_caps_at_max_fuel(self):
        from ..models import Fleet

        game = default_game()
        player = game.players.first()
        above_limit = Fleet.objects.create(
            game=game,
            player=player,
            name="Fast Refinery",
            x=1,
            y=1,
            fuel=3.0,
            max_fuel=10.0,
            fuel_factory_mg_per_year=1.0,
            fuel_factory_max_warp=5,
            travel_warp=6,
        )
        capped = Fleet.objects.create(
            game=game,
            player=player,
            name="Full Refinery",
            x=2,
            y=2,
            fuel=9.5,
            max_fuel=10.0,
            fuel_factory_mg_per_year=2.0,
            fuel_factory_max_warp=6,
            travel_warp=4,
        )

        GameTurn(game).apply_fuel_factories()

        above_limit.refresh_from_db()
        capped.refresh_from_db()
        self.assertAlmostEqual(above_limit.fuel, 3.0, places=4)
        self.assertAlmostEqual(capped.fuel, 10.0, places=4)

    def test_wormhole_jump_blocks_when_insufficient_fuel_for_distance(self):
        from ..models import FleetOrders, Fleet

        game = default_game(stars=2)
        game.random_events = False
        game.save(update_fields=['random_events'])
        player = game.players.first()
        star = player.homeworld

        fleet = Fleet.objects.create(
            game=game, player=player, name="Dry Wormhole Fleet",
            x=star.x, y=star.y, has_wormhole_drive=True, max_safe_warp=5,
            fuel=20.0, max_fuel=20.0
        )
        star_x, star_y = _pin_test_star(star, game)
        fleet.x = star_x
        fleet.y = star_y
        fleet.save(update_fields=['x', 'y'])
        FleetOrders.objects.create(
            game=game, fleet=fleet, order_type='MOVE',
            x=star_x + 10, y=star_y, warpfactor=14
        )

        GameTurn(game).generate_turn()
        fleet.refresh_from_db()
        self.assertEqual((fleet.x, fleet.y), (star.x, star.y))
        self.assertAlmostEqual(fleet.fuel, 20.0, places=4)
        self.assertEqual(fleet.orders.count(), 1)

    def test_refuels_in_friendly_shipyard_orbit(self):
        from ..models import Fleet

        game = default_game()
        player = game.players.first()
        star = player.homeworld
        star.shipyards = 1
        star.save(update_fields=['shipyards'])

        fleet = Fleet.objects.create(
            game=game, player=player, name="Refuel Fleet",
            x=star.x, y=star.y, fuel=5.0, max_fuel=40.0
        )

        GameTurn(game).generate_turn()
        fleet.refresh_from_db()
        self.assertAlmostEqual(fleet.fuel, 40.0, places=4)


class TestWarpDamageHelpers(TestCase):
    """Unit tests for warp damage helper functions."""

    def test_roll_chance_returns_bool(self):
        """roll_chance returns a boolean."""
        from ..turn import roll_chance
        result = roll_chance(0.5)
        self.assertIsInstance(result, bool)

    def test_calculate_integrity_loss_range(self):
        """calculate_integrity_loss returns value in expected range."""
        from ..turn import calculate_integrity_loss

        # With 1 excess warp, loss should be 5-15
        for _ in range(20):
            loss = calculate_integrity_loss(1)
            self.assertGreaterEqual(loss, 5)
            self.assertLessEqual(loss, 15)

        # With 3 excess warp, loss should be 15-45 (3 * 5-15)
        for _ in range(20):
            loss = calculate_integrity_loss(3)
            self.assertGreaterEqual(loss, 15)
            self.assertLessEqual(loss, 45)

    def test_calculate_integrity_loss_zero_excess(self):
        """calculate_integrity_loss with 0 excess returns 0."""
        from ..turn import calculate_integrity_loss
        self.assertEqual(calculate_integrity_loss(0), 0)

    def test_calculate_cargo_loss_percent_range(self):
        """calculate_cargo_loss_percent returns value in expected range."""
        from ..turn import calculate_cargo_loss_percent

        # With 1 excess warp, loss should be 0.02-0.10
        for _ in range(20):
            loss = calculate_cargo_loss_percent(1)
            self.assertGreaterEqual(loss, 0.02)
            self.assertLessEqual(loss, 0.10)

        # With 3 excess warp, loss should be 0.06-0.30 (3 * 2-10%)
        for _ in range(20):
            loss = calculate_cargo_loss_percent(3)
            self.assertGreaterEqual(loss, 0.06)
            self.assertLessEqual(loss, 0.30)

    def test_calculate_cargo_loss_percent_zero_excess(self):
        """calculate_cargo_loss_percent with 0 excess returns 0."""
        from ..turn import calculate_cargo_loss_percent
        self.assertEqual(calculate_cargo_loss_percent(0), 0.0)


class TestMergeFleet(TestCase):
    """Test merge fleet order functionality."""

    def test_merge_fleet_basic(self):
        """Two fleets at same location merge correctly."""
        from ..models import FleetOrders

        game = default_game()
        player = game.players.first()
        star = player.homeworld

        # Create two fleets at same location
        fleet1 = Fleet.objects.create(
            game=game, player=player, name="Fleet 1",
            x=star.x, y=star.y, ship_count=2
        )
        fleet2 = Fleet.objects.create(
            game=game, player=player, name="Fleet 2",
            x=star.x, y=star.y, ship_count=3
        )

        # Add merge order to fleet1 targeting fleet2
        FleetOrders.objects.create(
            game=game, fleet=fleet1, order_type='MERGE',
            target_fleet=fleet2
        )

        fleet1_id = fleet1.id
        fleet2_id = fleet2.id

        GameTurn(game).generate_turn()

        # Fleet1 should be deleted
        self.assertFalse(Fleet.objects.filter(id=fleet1_id).exists())

        # Fleet2 should still exist
        self.assertTrue(Fleet.objects.filter(id=fleet2_id).exists())

    def test_merge_fleet_ship_count(self):
        """Ship counts are summed when merging."""
        from ..models import FleetOrders

        game = default_game()
        player = game.players.first()
        star = player.homeworld

        fleet1 = Fleet.objects.create(
            game=game, player=player, name="Fleet 1",
            x=star.x, y=star.y, ship_count=5
        )
        fleet2 = Fleet.objects.create(
            game=game, player=player, name="Fleet 2",
            x=star.x, y=star.y, ship_count=7
        )

        FleetOrders.objects.create(
            game=game, fleet=fleet1, order_type='MERGE',
            target_fleet=fleet2
        )

        GameTurn(game).generate_turn()

        fleet2.refresh_from_db()
        self.assertEqual(fleet2.ship_count, 12)

    def test_merge_fleet_min_warp(self):
        """Takes minimum max_safe_warp from both fleets."""
        from ..models import FleetOrders

        game = default_game()
        player = game.players.first()
        star = player.homeworld

        fleet1 = Fleet.objects.create(
            game=game, player=player, name="Fleet 1",
            x=star.x, y=star.y, max_safe_warp=9
        )
        fleet2 = Fleet.objects.create(
            game=game, player=player, name="Fleet 2",
            x=star.x, y=star.y, max_safe_warp=6
        )

        FleetOrders.objects.create(
            game=game, fleet=fleet1, order_type='MERGE',
            target_fleet=fleet2
        )

        GameTurn(game).generate_turn()

        fleet2.refresh_from_db()
        self.assertEqual(fleet2.max_safe_warp, 6)

    def test_merge_fleet_avg_integrity(self):
        """Integrity is weighted average by ship count."""
        from ..models import FleetOrders

        game = default_game()
        player = game.players.first()
        star = player.homeworld
        star.shipyards = 0
        star.save()

        # Fleet1: 2 ships at 50% integrity = 100 total
        # Fleet2: 3 ships at 100% integrity = 300 total
        # Combined: 5 ships, 400 total = 80% average
        fleet1 = Fleet.objects.create(
            game=game, player=player, name="Fleet 1",
            x=star.x, y=star.y, ship_count=2, integrity=50
        )
        fleet2 = Fleet.objects.create(
            game=game, player=player, name="Fleet 2",
            x=star.x, y=star.y, ship_count=3, integrity=100
        )

        FleetOrders.objects.create(
            game=game, fleet=fleet1, order_type='MERGE',
            target_fleet=fleet2
        )

        GameTurn(game).generate_turn()

        fleet2.refresh_from_db()
        self.assertEqual(fleet2.integrity, 80)

    def test_merge_fleet_cargo_combined(self):
        """All cargo is transferred to target fleet."""
        from ..models import FleetOrders

        game = default_game()
        player = game.players.first()
        star = player.homeworld

        fleet1 = Fleet.objects.create(
            game=game, player=player, name="Fleet 1",
            x=star.x, y=star.y,
            ironium_inventory=100, boranium_inventory=200,
            germanium_inventory=300, colonists=50
        )
        fleet2 = Fleet.objects.create(
            game=game, player=player, name="Fleet 2",
            x=star.x, y=star.y,
            ironium_inventory=50, boranium_inventory=100,
            germanium_inventory=150, colonists=25
        )

        FleetOrders.objects.create(
            game=game, fleet=fleet1, order_type='MERGE',
            target_fleet=fleet2
        )

        GameTurn(game).generate_turn()

        fleet2.refresh_from_db()
        self.assertEqual(fleet2.ironium_inventory, 150)
        self.assertEqual(fleet2.boranium_inventory, 300)
        self.assertEqual(fleet2.germanium_inventory, 450)
        self.assertEqual(fleet2.colonists, 75)

    def test_merge_fleet_capacity_combined(self):
        """Cargo capacity, fuel stores, and dry mass are summed."""
        from ..models import FleetOrders

        game = default_game()
        player = game.players.first()
        star = player.homeworld
        star.shipyards = 0
        star.save(update_fields=['shipyards'])

        fleet1 = Fleet.objects.create(
            game=game, player=player, name="Fleet 1",
            x=star.x, y=star.y,
            cargo_capacity=1000, dry_mass=100, fuel=12.5, max_fuel=40.0
        )
        fleet2 = Fleet.objects.create(
            game=game, player=player, name="Fleet 2",
            x=star.x, y=star.y,
            cargo_capacity=2000, dry_mass=200, fuel=25.0, max_fuel=60.0
        )

        FleetOrders.objects.create(
            game=game, fleet=fleet1, order_type='MERGE',
            target_fleet=fleet2
        )

        GameTurn(game).generate_turn()

        fleet2.refresh_from_db()
        self.assertEqual(fleet2.cargo_capacity, 3000)
        self.assertEqual(fleet2.dry_mass, 300)
        self.assertAlmostEqual(fleet2.fuel, 37.5, places=4)
        self.assertAlmostEqual(fleet2.max_fuel, 100.0, places=4)

    def test_merge_fleet_copies_wormhole_stats_from_only_drive_fleet(self):
        """A single wormhole-capable source fleet should carry its stats across."""
        from ..models import FleetOrders

        game = default_game()
        player = game.players.first()
        star = player.homeworld

        fleet1 = Fleet.objects.create(
            game=game, player=player, name="Fleet 1",
            x=star.x, y=star.y, ship_count=2,
            has_wormhole_drive=True,
            wormhole_fuel_per_ly=4.0,
            wormhole_destruction_chance=0.05,
        )
        fleet2 = Fleet.objects.create(
            game=game, player=player, name="Fleet 2",
            x=star.x, y=star.y, ship_count=3,
            has_wormhole_drive=False,
            wormhole_fuel_per_ly=5.0,
            wormhole_destruction_chance=0.0,
        )

        FleetOrders.objects.create(
            game=game, fleet=fleet1, order_type='MERGE',
            target_fleet=fleet2
        )

        GameTurn(game).generate_turn()

        fleet2.refresh_from_db()
        self.assertTrue(fleet2.has_wormhole_drive)
        self.assertAlmostEqual(fleet2.wormhole_fuel_per_ly, 4.0, places=4)
        self.assertAlmostEqual(
            fleet2.wormhole_destruction_chance, 0.05, places=4
        )

    def test_merge_fleet_averages_wormhole_stats_when_both_have_drives(self):
        """Two wormhole-capable fleets should average wormhole performance."""
        from ..models import FleetOrders

        game = default_game()
        player = game.players.first()
        star = player.homeworld

        fleet1 = Fleet.objects.create(
            game=game, player=player, name="Fleet 1",
            x=star.x, y=star.y, ship_count=2,
            has_wormhole_drive=True,
            wormhole_fuel_per_ly=5.0,
            wormhole_destruction_chance=0.50,
        )
        fleet2 = Fleet.objects.create(
            game=game, player=player, name="Fleet 2",
            x=star.x, y=star.y, ship_count=3,
            has_wormhole_drive=True,
            wormhole_fuel_per_ly=3.0,
            wormhole_destruction_chance=0.10,
        )

        FleetOrders.objects.create(
            game=game, fleet=fleet1, order_type='MERGE',
            target_fleet=fleet2
        )

        GameTurn(game).generate_turn()

        fleet2.refresh_from_db()
        self.assertTrue(fleet2.has_wormhole_drive)
        self.assertAlmostEqual(fleet2.wormhole_fuel_per_ly, 3.8, places=4)
        self.assertAlmostEqual(
            fleet2.wormhole_destruction_chance, 0.26, places=4
        )

    def test_merge_fleet_orders_redirected(self):
        """Orders targeting source fleet are updated to target merged fleet."""
        from ..models import FleetOrders

        game = default_game()
        player = game.players.first()

        # Use explicit coordinates within map bounds
        fleet1 = Fleet.objects.create(
            game=game, player=player, name="Fleet 1",
            x=10, y=10
        )
        fleet2 = Fleet.objects.create(
            game=game, player=player, name="Fleet 2",
            x=10, y=10
        )
        fleet3 = Fleet.objects.create(
            game=game, player=player, name="Fleet 3",
            x=20, y=10  # Different location but within bounds
        )

        # Fleet3 has a transfer order targeting fleet1
        transfer_order = FleetOrders.objects.create(
            game=game, fleet=fleet3, order_type='TRANSFER',
            target_fleet=fleet1, transfer_type='LOAD',
            transfer_ironium=100
        )

        # Fleet1 merges into fleet2
        FleetOrders.objects.create(
            game=game, fleet=fleet1, order_type='MERGE',
            target_fleet=fleet2
        )

        transfer_order_id = transfer_order.id

        GameTurn(game).generate_turn()

        # Transfer order should now point to fleet2
        transfer_order.refresh_from_db()
        self.assertEqual(transfer_order.target_fleet_id, fleet2.id)

    def test_merge_fleet_source_deleted(self):
        """Source fleet and its orders are deleted after merge."""
        from ..models import FleetOrders

        game = default_game()
        player = game.players.first()
        star = player.homeworld

        fleet1 = Fleet.objects.create(
            game=game, player=player, name="Fleet 1",
            x=star.x, y=star.y
        )
        fleet2 = Fleet.objects.create(
            game=game, player=player, name="Fleet 2",
            x=star.x, y=star.y
        )

        # Add merge order and another order to fleet1
        FleetOrders.objects.create(
            game=game, fleet=fleet1, order_type='MERGE',
            target_fleet=fleet2
        )
        move_order = FleetOrders.objects.create(
            game=game, fleet=fleet1, order_type='MOVE',
            x=50, y=50, warpfactor=5
        )

        fleet1_id = fleet1.id
        move_order_id = move_order.id

        GameTurn(game).generate_turn()

        # Fleet1 should be deleted
        self.assertFalse(Fleet.objects.filter(id=fleet1_id).exists())

        # All fleet1's orders should be deleted (cascade)
        self.assertFalse(FleetOrders.objects.filter(id=move_order_id).exists())

    def test_merge_fleet_waiting(self):
        """Merge doesn't execute until fleets at same location."""
        from ..models import FleetOrders

        game = default_game()
        player = game.players.first()

        # Use explicit coordinates within map bounds
        fleet1 = Fleet.objects.create(
            game=game, player=player, name="Fleet 1",
            x=10, y=10
        )
        fleet2 = Fleet.objects.create(
            game=game, player=player, name="Fleet 2",
            x=20, y=10  # Different location but within bounds
        )

        FleetOrders.objects.create(
            game=game, fleet=fleet1, order_type='MERGE',
            target_fleet=fleet2
        )

        fleet1_id = fleet1.id
        fleet2_id = fleet2.id

        GameTurn(game).generate_turn()

        # Both fleets should still exist (merge waiting)
        self.assertTrue(Fleet.objects.filter(id=fleet1_id).exists())
        self.assertTrue(Fleet.objects.filter(id=fleet2_id).exists())

    def test_merge_fleet_wrong_player_invalid(self):
        """Merge order is invalid if target belongs to different player."""
        from ..models import FleetOrders
        from ._util import get_default_user, get_default_race
        from django.contrib.auth.models import User
        from ..models import Account, Player

        game = default_game()
        player1 = game.players.first()
        star = player1.homeworld

        # Create second player
        user2, _ = User.objects.get_or_create(
            username='second_user', defaults={'email': 'test2@example.com'}
        )
        account2, _ = Account.objects.get_or_create(django_user=user2)
        player2 = Player.objects.create(
            game=game, account=account2, name="Enemy",
            race_type=get_default_race().race_type
        )

        fleet1 = Fleet.objects.create(
            game=game, player=player1, name="My Fleet",
            x=star.x, y=star.y
        )
        star_x, star_y = _pin_test_star(star, game)
        fleet1.x = star_x
        fleet1.y = star_y
        fleet1.save(update_fields=['x', 'y'])
        fleet2 = Fleet.objects.create(
            game=game, player=player2, name="Enemy Fleet",
            x=star_x + 1, y=star_y
        )

        # Try to merge with enemy fleet (should be invalid)
        merge_order = FleetOrders.objects.create(
            game=game, fleet=fleet1, order_type='MERGE',
            target_fleet=fleet2
        )

        fleet1_id = fleet1.id
        fleet2_id = fleet2.id
        merge_order_id = merge_order.id

        GameTurn(game).generate_turn()

        # Both fleets should still exist
        self.assertTrue(Fleet.objects.filter(id=fleet1_id).exists())
        self.assertTrue(Fleet.objects.filter(id=fleet2_id).exists())

        # Merge order should be deleted (invalid)
        self.assertFalse(FleetOrders.objects.filter(id=merge_order_id).exists())

    def test_merge_fleet_creates_message(self):
        """Merge creates a notification message."""
        from ..models import FleetOrders

        game = default_game()
        player = game.players.first()
        star = player.homeworld

        initial_messages = player.messages.count()

        fleet1 = Fleet.objects.create(
            game=game, player=player, name="Fleet 1",
            x=star.x, y=star.y
        )
        fleet2 = Fleet.objects.create(
            game=game, player=player, name="Fleet 2",
            x=star.x, y=star.y
        )

        FleetOrders.objects.create(
            game=game, fleet=fleet1, order_type='MERGE',
            target_fleet=fleet2
        )

        GameTurn(game).generate_turn()

        # Should have a new message about the merge
        self.assertGreater(player.messages.count(), initial_messages)


class TestCombat(TestCase):
    def _create_two_player_game(self):
        get_default_race_type()
        user1 = User.objects.create_user('combat_p1', 'c1@test.com', 'pass')
        user2 = User.objects.create_user('combat_p2', 'c2@test.com', 'pass')
        account1 = Account.objects.create(django_user=user1)
        account2 = Account.objects.create(django_user=user2)

        factory = GameFactory()
        factory.set_map_size(100, 100)
        factory.set_owner(account1)
        factory.create_stars(5)
        game = factory.save()
        game.joinable = True
        game.save()
        player1 = factory.join_player(account1, get_default_race())
        player2 = factory.join_player(account2, get_default_race())
        player1.default_diplomatic_stance = 'HOSTILE'
        player2.default_diplomatic_stance = 'HOSTILE'
        player1.save(update_fields=['default_diplomatic_stance'])
        player2.save(update_fields=['default_diplomatic_stance'])
        return game, player1, player2

    def test_combat_strength_ship_count_has_diminishing_returns(self):
        """More ships increase strength, but with diminishing returns."""
        game, player1, player2 = self._create_two_player_game()
        fleet1 = Fleet.objects.create(
            game=game, player=player1, name="Fleet 1",
            x=10, y=10, ship_count=3, integrity=100
        )
        fleet2 = Fleet.objects.create(
            game=game, player=player2, name="Fleet 2",
            x=10, y=10, ship_count=2, integrity=100
        )

        strength1 = calculate_fleet_strength(fleet1, opponent_defence_multiplier=1.0)
        strength2 = calculate_fleet_strength(fleet2, opponent_defence_multiplier=1.0)
        self.assertGreater(strength1, strength2)
        # 50% more ships should not yield 50% more strength.
        self.assertLess(strength1 / strength2, 1.5)

    def test_offense_level_increases_combat_strength(self):
        """Higher offense level should increase fleet strength."""
        game, player1, _ = self._create_two_player_game()
        fleet1 = Fleet.objects.create(
            game=game, player=player1, name="Offense 0",
            x=10, y=10, ship_count=2, integrity=100, offense_level=0.0
        )
        fleet2 = Fleet.objects.create(
            game=game, player=player1, name="Offense 1",
            x=10, y=10, ship_count=2, integrity=100, offense_level=1.0
        )
        strength1 = calculate_fleet_strength(fleet1, opponent_defence_multiplier=1.0)
        strength2 = calculate_fleet_strength(fleet2, opponent_defence_multiplier=1.0)
        self.assertGreater(strength2, strength1)

    def test_race_combat_multiplier_increases_combat_strength(self):
        game, player1, player2 = self._create_two_player_game()
        player1.race_type = ServerRaceType.objects.create(
            code='ATK1',
            name='Attackers',
            enabled=True,
            description='',
            combat_multiplier=1.5,
        )
        player1.save(update_fields=['race_type'])
        player2.race_type = ServerRaceType.objects.create(
            code='ATK0',
            name='Normals',
            enabled=True,
            description='',
            combat_multiplier=1.0,
        )
        player2.save(update_fields=['race_type'])
        fleet1 = Fleet.objects.create(
            game=game, player=player1, name="Attack Boosted",
            x=10, y=10, ship_count=2, integrity=100, offense_level=0.0
        )
        fleet2 = Fleet.objects.create(
            game=game, player=player2, name="Attack Normal",
            x=10, y=10, ship_count=2, integrity=100, offense_level=0.0
        )
        strength1 = calculate_fleet_strength(fleet1, opponent_defence_multiplier=1.0)
        strength2 = calculate_fleet_strength(fleet2, opponent_defence_multiplier=1.0)
        self.assertGreater(strength1, strength2)

    def test_higher_opponent_defense_reduces_combat_strength(self):
        """Opponent defense multipliers should reduce attacker strength."""
        game, player1, _ = self._create_two_player_game()
        fleet = Fleet.objects.create(
            game=game, player=player1, name="Attacker",
            x=10, y=10, ship_count=2, integrity=100, offense_level=1.0
        )
        low_def = calculate_fleet_strength(fleet, opponent_defence_multiplier=1.0)
        high_def = calculate_fleet_strength(fleet, opponent_defence_multiplier=2.0)
        self.assertGreater(low_def, high_def)

    def test_race_combat_multiplier_reduces_incoming_combat_strength_via_fleet_defense(self):
        game, player1, player2 = self._create_two_player_game()
        player2.race_type = ServerRaceType.objects.create(
            code='DEF1',
            name='Defenders',
            enabled=True,
            description='',
            combat_multiplier=1.5,
        )
        player2.save(update_fields=['race_type'])
        attacker = Fleet.objects.create(
            game=game, player=player1, name="Attacker",
            x=10, y=10, ship_count=2, integrity=100, offense_level=1.0
        )
        defender = Fleet.objects.create(
            game=game, player=player2, name="Defender",
            x=10, y=10, ship_count=2, integrity=100, defense_level=0.0
        )
        baseline = calculate_fleet_strength(attacker, opponent_defence_multiplier=1.0)
        defended = calculate_fleet_strength(
            attacker,
            opponent_defence_multiplier=calculate_fleet_defense_multiplier(defender),
        )
        self.assertGreater(baseline, defended)

    def test_race_defence_multiplier_strengthens_colony_defenses(self):
        game = default_game(stars=2)
        player = game.players.first()
        player.race_type.defence_multiplier = 1.5
        player.race_type.save(update_fields=['defence_multiplier'])
        star = player.homeworld
        star.mines = 0
        star.factories = 0
        star.labs = 0
        star.shipyards = 0
        star.defenses = 10
        star.colonists = 10000
        star.save(update_fields=[
            'mines', 'factories', 'labs', 'shipyards', 'defenses', 'colonists'
        ])
        self.assertEqual(calculate_effective_defenses(star), 15.0)

    def test_ambush_bonus_increases_combat_strength_for_marked_fleet(self):
        game, player1, player2 = self._create_two_player_game()
        ambusher = Fleet.objects.create(
            game=game, player=player1, name="Ambusher",
            x=10, y=10, ship_count=2, integrity=100
        )
        defender = Fleet.objects.create(
            game=game, player=player2, name="Defender",
            x=10, y=10, ship_count=2, integrity=100
        )
        turn = GameTurn(game)
        turn._ambush_fleet_ids_for_year = {ambusher.id}

        captured = {}

        def capture_strengths(players, strength_by_player):
            captured.update(strength_by_player)
            return players[0]

        with patch.object(turn, '_choose_combat_winner', side_effect=capture_strengths), \
                patch.object(turn, '_calculate_combat_damage', return_value={
                    player1: 0.0,
                    player2: 0.0,
                }), \
                patch('dj4xol.turn.roll_attack_scale', return_value=1.0), \
                patch('dj4xol.turn.roll_defense_scale', return_value=1.0), \
                patch('dj4xol.turn.roll_ambush_attack_multiplier', return_value=1.25):
            turn._resolve_battle_at_location(10, 10, [ambusher, defender])

        self.assertGreater(captured[player1], captured[player2])

    def test_combat_destruction_creates_salvage_and_messages(self):
        """Combat destroys fleets, creates salvage, and sends combat messages."""
        game, player1, player2 = self._create_two_player_game()

        Fleet.objects.create(
            game=game, player=player1, name="Weak Fleet",
            x=20, y=20, ship_count=2, integrity=10,
            dry_mass=100, ironium_inventory=50, boranium_inventory=0, germanium_inventory=0
        )
        Fleet.objects.create(
            game=game, player=player2, name="Strong Fleet",
            x=20, y=20, ship_count=2, integrity=100,
            dry_mass=100, ironium_inventory=0, boranium_inventory=0, germanium_inventory=0
        )

        with patch('dj4xol.turn.roll_chance', return_value=False), \
             patch('dj4xol.turn.calculate_salvage_minerals', return_value=(10, 0, 0, 0, 0, 0)):
            GameTurn(game).generate_turn()

        self.assertTrue(Salvage.objects.filter(game=game, x=20, y=20).exists())
        self.assertGreater(player1.messages.filter(category='COMBAT', priority=True).count(), 0)

    def test_no_scanners_combat_creates_encounter_reports(self):
        game, player1, player2 = self._create_two_player_game()
        game.no_scanners = True
        game.save(update_fields=['no_scanners'])

        Fleet.objects.create(
            game=game,
            player=player1,
            name="Alpha",
            x=25,
            y=25,
            ship_count=6,
            integrity=100,
        )
        Fleet.objects.create(
            game=game,
            player=player2,
            name="Beta",
            x=25,
            y=25,
            ship_count=6,
            integrity=100,
        )

        with patch('dj4xol.turn.random.uniform', return_value=0.0):
            GameTurn(game).resolve_combat()

        reports = list(Report.objects.filter(game=game, target_type='fleet'))
        self.assertTrue(reports)
        for report in reports:
            self.assertEqual(report.get_report_data().get('report_tier'), 'encounter')

    def test_combat_does_not_report_destroyed_fleet(self):
        game, player1, player2 = self._create_two_player_game()

        fleet_a = Fleet.objects.create(
            game=game,
            player=player1,
            name="Survivor",
            x=28,
            y=28,
            ship_count=6,
            integrity=100,
        )
        fleet_b = Fleet.objects.create(
            game=game,
            player=player2,
            name="Doomed",
            x=28,
            y=28,
            ship_count=1,
            integrity=100,
        )

        turn = GameTurn(game)
        with patch.object(GameTurn, '_calculate_combat_damage', return_value={
            player1: 0.0,
            player2: 200.0,
        }):
            turn.resolve_combat()

        self.assertFalse(Fleet.objects.filter(id=fleet_b.id).exists())
        self.assertFalse(Report.objects.filter(
            game=game,
            player=player1,
            target_type='fleet',
            target_id=fleet_b.id,
        ).exists())
        self.assertGreater(player2.messages.filter(category='COMBAT', priority=True).count(), 0)

    def test_combat_low_integrity_can_reduce_ship_count(self):
        """Low integrity fleets can lose ships after combat damage."""
        game, player1, player2 = self._create_two_player_game()

        fleet1 = Fleet.objects.create(
            game=game, player=player1, name="Fleet 1",
            x=30, y=30, ship_count=3, integrity=60
        )
        Fleet.objects.create(
            game=game, player=player2, name="Fleet 2",
            x=30, y=30, ship_count=2, integrity=100
        )

        with patch('dj4xol.turn.roll_chance', return_value=True):
            GameTurn(game).generate_turn()

        fleet1.refresh_from_db()
        self.assertEqual(fleet1.ship_count, 2)

    def test_combat_luck_jitter_scales_outcome_roll(self):
        """Luck multiplier only affects the random jitter in winner selection."""
        game, player1, player2 = self._create_two_player_game()
        player1.race_type.luck_multiplier = 1.5
        player1.race_type.save(update_fields=['luck_multiplier'])
        player2.race_type.luck_multiplier = 0.5
        player2.race_type.save(update_fields=['luck_multiplier'])

        Fleet.objects.create(
            game=game, player=player1, name="Fleet 1",
            x=40, y=40, ship_count=2, integrity=100
        )
        Fleet.objects.create(
            game=game, player=player2, name="Fleet 2",
            x=40, y=40, ship_count=2, integrity=100
        )

        with patch('dj4xol.turn.calculate_salvage_minerals', return_value=(0, 0, 0, 0, 0, 0)), \
             patch('dj4xol.turn.random.uniform', side_effect=[0.10, -0.10, 0.0, 0.0]):
            GameTurn(game).generate_turn()

        self.assertGreater(player1.messages.filter(category='COMBAT').count(), 0)
        self.assertGreater(player2.messages.filter(category='COMBAT').count(), 0)


class TestInterceptPatrolOrders(TestCase):
    def _create_two_player_game(self):
        get_default_race_type()
        user1 = User.objects.create_user('patrol_p1', 'p1@test.com', 'pass')
        user2 = User.objects.create_user('patrol_p2', 'p2@test.com', 'pass')
        account1 = Account.objects.create(django_user=user1)
        account2 = Account.objects.create(django_user=user2)

        factory = GameFactory()
        factory.set_map_size(100, 100)
        factory.set_owner(account1)
        factory.create_stars(5)
        game = factory.save()
        game.joinable = True
        game.save()
        player1 = factory.join_player(account1, get_default_race())
        player2 = factory.join_player(account2, get_default_race())
        player1.default_diplomatic_stance = 'HOSTILE'
        player2.default_diplomatic_stance = 'HOSTILE'
        player1.save(update_fields=['default_diplomatic_stance'])
        player2.save(update_fields=['default_diplomatic_stance'])
        return game, player1, player2

    def test_patrol_repeat_appends_new_patrol(self):
        """Patrol repeat appends a new patrol and converts current order."""
        from ..models import FleetOrders

        game, player1, _ = self._create_two_player_game()
        fleet = Fleet.objects.create(
            game=game, player=player1, name="Patrol Fleet",
            x=5, y=5, ship_count=2, integrity=100
        )

        FleetOrders.objects.create(
            game=game, fleet=fleet, order_type='PATROL', repeat=True,
            x=50, y=50, patrol_radius=10, intercept_speed=3
        )

        with patch.object(GameTurn, '_find_patrol_enemy', return_value=None):
            GameTurn(game).generate_turn()

        patrol_orders = fleet.orders.filter(order_type='PATROL')
        move_orders = fleet.orders.filter(order_type='MOVE')
        self.assertEqual(patrol_orders.count(), 1)
        self.assertEqual(move_orders.count(), 1)

    def test_intercept_order_moves(self):
        """Intercept behaves like move when target is not a fleet."""
        from ..models import FleetOrders

        game, player1, _ = self._create_two_player_game()
        fleet = Fleet.objects.create(
            game=game, player=player1, name="Interceptor",
            x=10, y=10, ship_count=1, integrity=100
        )

        FleetOrders.objects.create(
            game=game, fleet=fleet, order_type='INTERCEPT',
            x=20, y=10, warpfactor=5
        )

        GameTurn(game).generate_turn()
        fleet.refresh_from_db()
        self.assertNotEqual((fleet.x, fleet.y), (10, 10))

    def test_intercept_wormhole_warp_is_clamped_to_13(self):
        """Legacy INTERCEPT orders at warp 14 should be clamped to warp 13."""
        from ..models import FleetOrders

        game, player1, _ = self._create_two_player_game()
        interceptor = Fleet.objects.create(
            game=game, player=player1, name="Interceptor",
            x=10, y=10, ship_count=1, integrity=100, has_wormhole_drive=True,
            max_safe_warp=13
        )
        target = Fleet.objects.create(
            game=game, player=player1, name="Target",
            x=24, y=10, ship_count=1, integrity=100
        )

        order = FleetOrders.objects.create(
            game=game, fleet=interceptor, order_type='INTERCEPT',
            target_fleet=target, warpfactor=14
        )

        GameTurn(game).generate_turn()
        order.refresh_from_db()
        self.assertEqual(order.warpfactor, 13)

    def test_intercept_ahead_targets_current_position(self):
        """Interceptor ahead of moving target should fly directly toward it."""
        from ..models import FleetOrders

        game, player1, _ = self._create_two_player_game()
        interceptor = Fleet.objects.create(
            game=game, player=player1, name="Interceptor",
            x=80, y=50, ship_count=1, integrity=100
        )
        target = Fleet.objects.create(
            game=game, player=player1, name="Target",
            x=70, y=50, ship_count=1, integrity=100, heading=90
        )
        FleetOrders.objects.create(
            game=game, fleet=target, order_type='MOVE', x=99, y=50, warpfactor=5
        )
        intercept_order = FleetOrders.objects.create(
            game=game, fleet=interceptor, order_type='INTERCEPT',
            target_fleet=target, warpfactor=5
        )

        x, y = GameTurn(game)._get_intercept_destination(intercept_order)
        self.assertEqual((x, y), (target.x, target.y))

    def test_intercept_destination_ignores_target_warp_advantage(self):
        """Fractional warp advantage should not extend intercept lead distance."""
        from ..models import FleetOrders

        game, player1, _ = self._create_two_player_game()
        interceptor = Fleet.objects.create(
            game=game, player=player1, name="Interceptor",
            x=10, y=30, ship_count=1, integrity=100
        )
        target = Fleet.objects.create(
            game=game, player=player1, name="Target",
            x=20, y=20, ship_count=1, integrity=100, heading=45,
            warp_advantage=0.9,
        )
        FleetOrders.objects.create(
            game=game, fleet=target, order_type='MOVE', x=40, y=1, warpfactor=5
        )
        intercept_order = FleetOrders.objects.create(
            game=game, fleet=interceptor, order_type='INTERCEPT',
            target_fleet=target, warpfactor=5
        )

        x, y = GameTurn(game)._get_intercept_destination(intercept_order)
        self.assertEqual((x, y), (23, 16))

    def test_hidden_manual_intercept_converts_to_last_known_space_and_messages(self):
        game, player1, player2 = self._create_two_player_game()
        interceptor = Fleet.objects.create(
            game=game, player=player1, name="Watcher",
            x=10, y=10, ship_count=1, integrity=100, max_safe_warp=5,
            basic_scanner_range=0
        )
        target = Fleet.objects.create(
            game=game, player=player2, name="Raider",
            x=40, y=40, ship_count=1, integrity=100
        )
        order = FleetOrders.objects.create(
            game=game,
            fleet=interceptor,
            order_type='INTERCEPT',
            target_fleet=target,
            target_kind='OBJECT',
            target_short_id=target.short_id,
            x=25,
            y=26,
            warpfactor=5,
        )

        GameTurn(game)._move_fleet_single_order(interceptor)
        order.refresh_from_db()

        self.assertEqual(order.order_type, 'MOVE')
        self.assertEqual(order.target_kind, 'SPACE')
        self.assertIsNone(order.target_fleet_id)
        self.assertEqual((order.x, order.y), (25, 26))
        msg = player1.messages.order_by('-id').first()
        self.assertIsNotNone(msg)
        self.assertFalse(msg.priority)
        self.assertTrue(
            any(
                phrase in msg.message.lower()
                for phrase in ('lost track of', 'lost sight of', 'can no longer find')
            )
        )
        self.assertIn('Raider', msg.message)

    def test_hidden_patrol_generated_intercept_returns_to_patrol_and_messages(self):
        game, player1, player2 = self._create_two_player_game()
        patrol_fleet = Fleet.objects.create(
            game=game, player=player1, name="Sentinel",
            x=10, y=10, ship_count=1, integrity=100, max_safe_warp=5,
            basic_scanner_range=0
        )
        target = Fleet.objects.create(
            game=game, player=player2, name="Ghost",
            x=60, y=60, ship_count=1, integrity=100
        )
        order = FleetOrders.objects.create(
            game=game,
            fleet=patrol_fleet,
            order_type='INTERCEPT',
            target_fleet=target,
            target_kind='OBJECT',
            target_short_id=target.short_id,
            x=30,
            y=30,
            warpfactor=4,
            patrol_generated=True,
        )

        GameTurn(game)._move_fleet_single_order(patrol_fleet)
        order.refresh_from_db()

        self.assertEqual(order.order_type, 'MOVE')
        self.assertEqual(order.target_kind, 'SPACE')
        self.assertEqual((order.x, order.y), (30, 30))
        self.assertFalse(order.patrol_generated)
        msg = player1.messages.order_by('-id').first()
        self.assertIsNotNone(msg)
        self.assertFalse(msg.priority)
        self.assertIn('returning to patrol', msg.message)

    def test_patrol_enemy_search_ignores_out_of_range_enemy_fleets(self):
        game, player1, player2 = self._create_two_player_game()
        fleet = Fleet.objects.create(
            game=game, player=player1, name="Patrol",
            x=10, y=10, ship_count=1, integrity=100, basic_scanner_range=0
        )
        enemy = Fleet.objects.create(
            game=game, player=player2, name="Shadow",
            x=12, y=10, ship_count=1, integrity=100
        )

        result = GameTurn(game)._find_enemy_fleet_in_radius(player1, fleet.x, fleet.y, 10)
        self.assertIsNone(result)

    def test_patrol_enemy_search_does_not_target_allied_fleets(self):
        game, player1, player2 = self._create_two_player_game()
        PlayerDiplomaticStance.objects.create(
            player=player1,
            target_player=player2,
            stance='ALLIED',
        )
        PlayerDiplomaticStance.objects.create(
            player=player2,
            target_player=player1,
            stance='ALLIED',
        )
        fleet = Fleet.objects.create(
            game=game, player=player1, name="Patrol",
            x=10, y=10, ship_count=1, integrity=100, basic_scanner_range=20
        )
        ally = Fleet.objects.create(
            game=game, player=player2, name="Ally",
            x=12, y=10, ship_count=1, integrity=100
        )

        result = GameTurn(game)._find_enemy_fleet_in_radius(player1, fleet.x, fleet.y, 10)
        self.assertIsNone(result)

    def test_intercept_arrival_executes_followup_merge_same_turn(self):
        """Successful intercept should run immediate non-move follow-up orders."""
        from ..models import FleetOrders

        game, player1, _ = self._create_two_player_game()

        interceptor = Fleet.objects.create(
            game=game, player=player1, name="Interceptor",
            x=19, y=10, ship_count=1, integrity=100, max_safe_warp=13,
            basic_scanner_range=20
        )
        target = Fleet.objects.create(
            game=game, player=player1, name="Target",
            x=20, y=10, ship_count=1, integrity=100, max_safe_warp=13, heading=90
        )

        # Target is moving away, so predictive intercept point is farther than interceptor warp.
        FleetOrders.objects.create(
            game=game, fleet=target, order_type='MOVE', x=40, y=10, warpfactor=4
        )
        FleetOrders.objects.create(
            game=game, fleet=interceptor, order_type='INTERCEPT',
            target_fleet=target, warpfactor=5
        )
        FleetOrders.objects.create(
            game=game, fleet=interceptor, order_type='MERGE', target_fleet=target
        )

        with patch('dj4xol.turn.random.shuffle', lambda x: None):
            GameTurn(game).generate_turn()

        self.assertFalse(Fleet.objects.filter(id=interceptor.id).exists())
        target.refresh_from_db()
        self.assertEqual(target.ship_count, 2)

    def test_enemy_intercept_locks_target_and_forces_same_year_combat(self):
        """Enemy fleet intercepted this year should not move away before combat."""
        from ..models import FleetOrders

        game, player1, player2 = self._create_two_player_game()

        interceptor = Fleet.objects.create(
            game=game, player=player1, name="Interceptor",
            x=15, y=11, ship_count=1, integrity=100, max_safe_warp=13
        )
        target = Fleet.objects.create(
            game=game, player=player2, name="Target",
            x=20, y=10, ship_count=1, integrity=100, max_safe_warp=13, heading=90
        )
        FleetOrders.objects.create(
            game=game, fleet=interceptor, order_type='INTERCEPT',
            target_fleet=target, warpfactor=5
        )

        with patch('dj4xol.turn.random.shuffle', lambda x: None):
            GameTurn(game).generate_turn()

        interceptor.refresh_from_db()
        target.refresh_from_db()

        # Interceptor should have snapped to target, and target should be locked in place.
        self.assertEqual((interceptor.x, interceptor.y), (target.x, target.y))

        # Combat should have happened this same year.
        self.assertTrue(player1.messages.filter(category='COMBAT').exists())
        self.assertTrue(player2.messages.filter(category='COMBAT').exists())

    def test_enemy_intercept_does_not_lock_when_starting_stacked(self):
        """Stacked-at-start intercept should not immobilize a moving target."""
        from ..models import FleetOrders

        game, player1, player2 = self._create_two_player_game()

        interceptor = Fleet.objects.create(
            game=game, player=player1, name="Interceptor",
            x=10, y=10, ship_count=1, integrity=100, max_safe_warp=13,
            basic_scanner_range=20
        )
        target = Fleet.objects.create(
            game=game, player=player2, name="Target",
            x=10, y=10, ship_count=1, integrity=100, max_safe_warp=13, heading=90
        )

        FleetOrders.objects.create(
            game=game, fleet=interceptor, order_type='INTERCEPT',
            target_fleet=target, warpfactor=5, repeat=True
        )
        FleetOrders.objects.create(
            game=game, fleet=target, order_type='MOVE',
            x=30, y=10, warpfactor=4
        )

        with patch('dj4xol.turn.random.shuffle', lambda x: None):
            GameTurn(game).generate_turn()

        interceptor.refresh_from_db()
        target.refresh_from_db()

        # Target should have moved; stacked start must not lock it in place.
        self.assertNotEqual((target.x, target.y), (10, 10))
        self.assertNotEqual((interceptor.x, interceptor.y), (target.x, target.y))

    def test_cloaked_enemy_intercept_marks_fresh_ambush_and_persists_contact_year(self):
        game, player1, player2 = self._create_two_player_game()

        interceptor = Fleet.objects.create(
            game=game, player=player1, name="Shadow Interceptor",
            x=20, y=10, ship_count=1, integrity=100, max_safe_warp=13,
            max_cloaked_warp=5,
        )
        target = Fleet.objects.create(
            game=game, player=player2, name="Target",
            x=20, y=10, ship_count=1, integrity=100, max_safe_warp=13
        )
        FleetOrders.objects.create(
            game=game, fleet=interceptor, order_type='INTERCEPT',
            target_fleet=target, warpfactor=5, repeat=True,
        )

        turn = GameTurn(game)
        order = interceptor.orders.get()
        turn._mark_cloaked_intercept_ambush(interceptor, order)
        turn._handle_repeating_order(order)

        repeat_order = interceptor.orders.exclude(id=order.id).get()
        self.assertIn(interceptor.id, turn._ambush_fleet_ids_for_year)
        self.assertEqual(repeat_order.last_contact_year, game.year)

    def test_cloaked_intercept_ambush_requires_a_gap_year(self):
        game, player1, player2 = self._create_two_player_game()
        interceptor = Fleet.objects.create(
            game=game, player=player1, name="Shadow Interceptor",
            x=20, y=10, ship_count=1, integrity=100, max_cloaked_warp=5, travel_warp=5
        )
        target = Fleet.objects.create(
            game=game, player=player2, name="Target",
            x=20, y=10, ship_count=1, integrity=100
        )
        order = FleetOrders.objects.create(
            game=game, fleet=interceptor, order_type='INTERCEPT',
            target_fleet=target, warpfactor=5, last_contact_year=game.year - 1,
        )

        turn = GameTurn(game)
        turn._locked_fleet_ids_for_year = set()
        turn._ambush_fleet_ids_for_year = set()
        turn._fleet_start_positions_for_year = {
            interceptor.id: (15, 11),
            target.id: (20, 10),
        }
        turn._lock_successful_enemy_intercept(interceptor, order)
        self.assertNotIn(interceptor.id, turn._ambush_fleet_ids_for_year)
        self.assertEqual(order.last_contact_year, game.year)

        order.last_contact_year = game.year - 2
        turn._ambush_fleet_ids_for_year = set()
        turn._lock_successful_enemy_intercept(interceptor, order)
        self.assertIn(interceptor.id, turn._ambush_fleet_ids_for_year)
        self.assertEqual(order.last_contact_year, game.year)

    def test_cloaked_intercept_continuing_stacked_encounter_updates_contact_year_without_ambush(self):
        game, player1, player2 = self._create_two_player_game()
        interceptor = Fleet.objects.create(
            game=game, player=player1, name="Shadow Interceptor",
            x=20, y=10, ship_count=1, integrity=100, max_cloaked_warp=5, travel_warp=5
        )
        target = Fleet.objects.create(
            game=game, player=player2, name="Target",
            x=20, y=10, ship_count=1, integrity=100
        )
        order = FleetOrders.objects.create(
            game=game, fleet=interceptor, order_type='INTERCEPT',
            target_fleet=target, warpfactor=5, last_contact_year=game.year - 2,
        )

        turn = GameTurn(game)
        turn._locked_fleet_ids_for_year = set()
        turn._ambush_fleet_ids_for_year = set()
        turn._fleet_start_positions_for_year = {
            interceptor.id: (20, 10),
            target.id: (20, 10),
        }

        turn._lock_successful_enemy_intercept(interceptor, order)

        self.assertNotIn(interceptor.id, turn._ambush_fleet_ids_for_year)
        self.assertEqual(order.last_contact_year, game.year)
        self.assertEqual(turn._locked_fleet_ids_for_year, set())

    def test_intercept_destination_predicts_comet_heading(self):
        from ..models import FleetOrders

        game, player1, _ = self._create_two_player_game()
        game.stars.all().delete()
        interceptor = Fleet.objects.create(
            game=game, player=player1, name="Comet Chaser",
            x=10, y=10, ship_count=1, integrity=100, max_safe_warp=13
        )
        comet = Anomaly.objects.create(
            game=game,
            x=20,
            y=10,
            name='Test Comet',
            anomaly_type=Anomaly.TYPE_COMET,
            heading=90.0,
            stability=100,
        )
        intercept_order = FleetOrders.objects.create(
            game=game, fleet=interceptor, order_type='INTERCEPT',
            target_kind='OBJECT', target_short_id=comet.short_id, warpfactor=5
        )

        x, y = GameTurn(game)._get_intercept_destination(intercept_order)
        self.assertGreater(x, comet.x)
        self.assertEqual(y, comet.y)

    def test_intercept_order_can_catch_moving_comet(self):
        from ..models import FleetOrders

        game, player1, _ = self._create_two_player_game()
        game.stars.all().delete()
        interceptor = Fleet.objects.create(
            game=game, player=player1, name="Comet Chaser",
            x=10, y=10, ship_count=1, integrity=100, max_safe_warp=13
        )
        comet = Anomaly.objects.create(
            game=game,
            x=20,
            y=10,
            name='Runner Comet',
            anomaly_type=Anomaly.TYPE_COMET,
            heading=90.0,
            stability=100,
        )
        FleetOrders.objects.create(
            game=game, fleet=interceptor, order_type='INTERCEPT',
            target_kind='OBJECT', target_short_id=comet.short_id, warpfactor=5
        )

        caught = False
        for _ in range(8):
            GameTurn(game).generate_turn()
            interceptor.refresh_from_db()
            if not Anomaly.objects.filter(id=comet.id).exists():
                break
            comet.refresh_from_db()
            if (interceptor.x, interceptor.y) == (comet.x, comet.y):
                caught = True
                break
        self.assertTrue(caught)

    def test_patrol_order_detail_includes_patrol_radius(self):
        """Detail payload should include patrol radius for PATROL orders."""
        from ..models import FleetOrders
        from ..objectdetails import DetailBuilder

        game, player1, _ = self._create_two_player_game()
        fleet = Fleet.objects.create(
            game=game, player=player1, name="Patrol Fleet",
            x=5, y=5, ship_count=2, integrity=100
        )

        FleetOrders.objects.create(
            game=game,
            fleet=fleet,
            order_type='PATROL',
            repeat=True,
            x=50,
            y=50,
            patrol_radius=10,
            intercept_speed=3,
        )

        detail = DetailBuilder(
            game,
            x=fleet.x,
            y=fleet.y,
            selected=fleet.short_id.lower(),
            player=player1,
        ).build_detail()

        patrol_order = detail['fleet_orders'][0]
        self.assertEqual(patrol_order['order_type'], 'PATROL')
        self.assertEqual(patrol_order['patrol_radius'], 10)

    def test_fleet_orders_completed_message_when_queue_empties(self):
        """Fleet should get a message when it completes all assigned orders."""
        from ..models import FleetOrders

        game, player1, _ = self._create_two_player_game()
        fleet = Fleet.objects.create(
            game=game, player=player1, name="Mission Fleet",
            x=10, y=10, ship_count=1, integrity=100
        )

        # Reach destination in a single turn so the queue becomes empty.
        FleetOrders.objects.create(
            game=game, fleet=fleet, order_type='MOVE',
            x=11, y=10, warpfactor=5
        )

        initial_count = player1.messages.count()
        GameTurn(game).generate_turn()

        self.assertEqual(fleet.orders.count(), 0)
        self.assertGreater(player1.messages.count(), initial_count)
        self.assertTrue(
            player1.messages.filter(
                message__icontains="No further orders are queued"
            ).exists()
        )

    def test_no_orders_completed_message_after_scuttle(self):
        """Scuttled fleets should not emit an orders-completed message."""
        from ..models import FleetOrders

        game, player1, _ = self._create_two_player_game()
        fleet = Fleet.objects.create(
            game=game, player=player1, name="Disposable Fleet",
            x=10, y=10, ship_count=1, integrity=100
        )
        FleetOrders.objects.create(
            game=game, fleet=fleet, order_type='SCUTTLE',
        )

        GameTurn(game).generate_turn()

        self.assertFalse(Fleet.objects.filter(id=fleet.id).exists())
        self.assertFalse(
            player1.messages.filter(
                message__icontains="No further orders are queued",
            ).filter(
                message__icontains="Disposable Fleet",
            ).exists()
        )

    def test_no_orders_completed_message_after_merge(self):
        """Merged source fleets should not emit orders-completed messages."""
        from ..models import FleetOrders

        game, player1, _ = self._create_two_player_game()
        source = Fleet.objects.create(
            game=game, player=player1, name="Merge Source",
            x=10, y=10, ship_count=1, integrity=100
        )
        target = Fleet.objects.create(
            game=game, player=player1, name="Merge Target",
            x=10, y=10, ship_count=1, integrity=100
        )
        FleetOrders.objects.create(
            game=game, fleet=source, order_type='MERGE', target_fleet=target
        )

        GameTurn(game).generate_turn()

        self.assertFalse(Fleet.objects.filter(id=source.id).exists())
        self.assertTrue(Fleet.objects.filter(id=target.id).exists())
        self.assertFalse(
            player1.messages.filter(
                message__icontains="No further orders are queued",
            ).filter(
                message__icontains="Merge Source",
            ).exists()
        )


class TestBombardmentOrders(TestCase):
    def _ensure_other_player(self, game, attacker, username):
        defender = Player.objects.filter(game=game).exclude(id=attacker.id).first()
        if defender:
            return defender
        other_user = User.objects.create_user(username, '%s@test.com' % username, 'pass')
        other_account = Account.objects.create(django_user=other_user)
        return Player.objects.create(
            game=game,
            account=other_account,
            race_type=attacker.race_type,
        )

    def test_bomb_order_waits_until_fleet_is_at_target(self):
        from ..models import FleetOrders

        game = default_game(stars=2)
        attacker = game.players.first()
        defender = self._ensure_other_player(game, attacker, 'bomb_wait_def')
        defender.race_type.population_growth_multiplier = 0
        defender.race_type.save(update_fields=['population_growth_multiplier'])
        star = game.stars.exclude(pk=attacker.homeworld.pk).first()
        star.player = defender
        star.colonists = 50_000
        star.defenses = 0
        star.save(update_fields=['player', 'colonists', 'defenses'])

        start_x = star.x + 1
        if start_x >= game.map_size_x:
            start_x = max(0, star.x - 1)
        start_y = star.y
        if start_x == star.x and start_y == star.y:
            start_y = star.y + 1 if star.y + 1 < game.map_size_y else max(0, star.y - 1)

        fleet = Fleet.objects.create(
            game=game,
            player=attacker,
            name='Bomber Wait',
            x=start_x,
            y=start_y,
            ship_count=10,
            has_bombs='CONVENTIONAL',
        )
        order = FleetOrders.objects.create(
            game=game, fleet=fleet, order_type='BOMB', target_star=star
        )

        with patch('dj4xol.turn.roll_chance', return_value=False):
            GameTurn(game).generate_turn()
        star.refresh_from_db()
        self.assertEqual(star.colonists, 50_000)
        self.assertTrue(FleetOrders.objects.filter(id=order.id).exists())

    def test_smart_bombs_spare_infrastructure(self):
        from ..models import FleetOrders

        game = default_game(stars=2)
        attacker = game.players.first()
        defender = self._ensure_other_player(game, attacker, 'bomb_smart_def')
        star = game.stars.exclude(pk=attacker.homeworld.pk).first()
        star.player = defender
        star.colonists = 100_000
        star.defenses = 10
        star.mines = 20
        star.factories = 30
        star.labs = 12
        star.shipyards = 4
        star.save(update_fields=['player', 'colonists', 'defenses', 'mines', 'factories', 'labs', 'shipyards'])

        fleet = Fleet.objects.create(
            game=game,
            player=attacker,
            name='Smart Bomber',
            x=star.x,
            y=star.y,
            ship_count=30,
            has_bombs='SMART',
            integrity=100,
        )
        FleetOrders.objects.create(
            game=game, fleet=fleet, order_type='BOMB', target_star=star
        )

        with patch('dj4xol.turn.GameTurn._resolve_planetary_defense_fire_against_fleet', return_value={
            'destroyed': False, 'integrity_lost': 0, 'ships_lost': 0, 'defense_mult': 1.0
        }), patch('dj4xol.bombardment_rules.scaled_luck_roll', return_value=1.0):
            GameTurn(game).generate_turn()

        star.refresh_from_db()
        self.assertLess(star.colonists, 100_000)
        self.assertLess(star.defenses, 10)
        self.assertEqual(star.mines, 20)
        self.assertEqual(star.factories, 30)
        self.assertEqual(star.labs, 12)
        self.assertEqual(star.shipyards, 4)

    def test_bombardment_damage_tempered_by_defenses(self):
        from ..bombardment_rules import bombardment_damage_k

        with patch('dj4xol.bombardment_rules.scaled_luck_roll', return_value=1.0):
            low_def_damage = bombardment_damage_k(
                ship_count=20,
                offense_level=0.0,
                defenses=0,
                luck_multiplier=1.0,
                bomb_type='CONVENTIONAL',
            )
            high_def_damage = bombardment_damage_k(
                ship_count=20,
                offense_level=0.0,
                defenses=20,
                luck_multiplier=1.0,
                bomb_type='CONVENTIONAL',
            )
        self.assertGreater(low_def_damage, high_def_damage)

    def test_bombardment_can_take_defensive_fire_damage(self):
        from ..models import FleetOrders

        game = default_game(stars=2)
        attacker = game.players.first()
        defender = self._ensure_other_player(game, attacker, 'bomb_fire_def')
        star = game.stars.exclude(pk=attacker.homeworld.pk).first()
        star.player = defender
        star.colonists = 1000
        star.defenses = 5
        star.save(update_fields=['player', 'colonists', 'defenses'])

        fleet = Fleet.objects.create(
            game=game,
            player=attacker,
            name='Fragile Bomber',
            x=star.x,
            y=star.y,
            ship_count=1,
            integrity=100,
            has_bombs='CONVENTIONAL',
        )
        FleetOrders.objects.create(game=game, fleet=fleet, order_type='BOMB', target_star=star)

        GameTurn(game).generate_turn()
        fleet.refresh_from_db()
        self.assertLess(fleet.integrity, 100)

    def test_nova_bombs_can_destroy_star_and_notify_other_players(self):
        from ..models import FleetOrders

        game = default_game(stars=2)
        attacker = game.players.first()
        defender = self._ensure_other_player(game, attacker, 'bomb_nova_def')
        observer = self._ensure_other_player(game, attacker, 'bomb_nova_obs')
        if observer.id == defender.id:
            user = User.objects.create_user('bomb_nova_obs2', 'bomb_nova_obs2@test.com', 'pass')
            account = Account.objects.create(django_user=user)
            observer = Player.objects.create(
                game=game, account=account, race_type=attacker.race_type
            )

        star = game.stars.exclude(pk=attacker.homeworld.pk).first()
        star.player = defender
        star.colonists = 10_000
        star.defenses = 0
        star.save(update_fields=['player', 'colonists', 'defenses'])
        star_name = star.name

        fleet = Fleet.objects.create(
            game=game,
            player=attacker,
            name='Nova Bomber',
            x=star.x,
            y=star.y,
            ship_count=10,
            has_bombs='NOVA',
        )
        FleetOrders.objects.create(game=game, fleet=fleet, order_type='BOMB', target_star=star)

        with patch('dj4xol.turn.roll_chance', return_value=True), patch(
            'dj4xol.turn.GameTurn._resolve_planetary_defense_fire_against_fleet',
            return_value={'destroyed': False, 'integrity_lost': 0, 'ships_lost': 0, 'defense_mult': 1.0}
        ), patch('dj4xol.bombardment_rules.scaled_luck_roll', return_value=1.0), patch(
            'dj4xol.turn.random.randint', return_value=75
        ):
            GameTurn(game).generate_turn()

        self.assertFalse(Star.objects.filter(id=star.id).exists())
        self.assertTrue(Anomaly.objects.filter(
            game=game, x=star.x, y=star.y, anomaly_type=Anomaly.TYPE_BLACK_HOLE
        ).exists())
        black_hole = Anomaly.objects.filter(
            game=game, x=star.x, y=star.y, anomaly_type=Anomaly.TYPE_BLACK_HOLE
        ).first()
        self.assertIsNotNone(black_hole)
        if black_hole is not None:
            self.assertTrue(30 <= int(black_hole.stability) <= 91)
        self.assertTrue(
            attacker.messages.filter(
                message__icontains=star_name,
            ).filter(
                message__icontains='Astronomers report'
            ).exists()
        )
        self.assertTrue(
            defender.messages.filter(
                message__icontains=star_name,
            ).filter(
                message__icontains='Astronomers report'
            ).exists()
        )
        self.assertTrue(
            observer.messages.filter(
                message__icontains=star_name,
            ).filter(
                message__icontains='Astronomers report'
            ).exists()
        )
        self.assertTrue(
            defender.messages.filter(
                message__icontains=star_name,
                priority=True,
            ).exists()
        )
        self.assertFalse(
            attacker.messages.filter(
                message__icontains=star_name,
                priority=True,
            ).filter(
                message__icontains='Astronomers report',
            ).exists()
        )
        self.assertFalse(
            observer.messages.filter(
                message__icontains=star_name,
                priority=True,
            ).filter(
                message__icontains='Astronomers report',
            ).exists()
        )

    def test_nova_bombs_can_create_asteroid_field_from_destroyed_star(self):
        from ..models import FleetOrders

        game = default_game(stars=2)
        attacker = game.players.first()
        defender = self._ensure_other_player(game, attacker, 'bomb_nova_rock_def')

        star = game.stars.exclude(pk=attacker.homeworld.pk).first()
        star.player = defender
        star.colonists = 10_000
        star.defenses = 0
        star.ironium_inventory = 1200
        star.boranium_inventory = 300
        star.germanium_inventory = 0
        star.resource_x_inventory = 40
        star.ironium_yield = 100
        star.boranium_yield = 50
        star.germanium_yield = 0
        star.resource_x_yield = 20
        star.resource_y_yield = 0
        star.resource_z_yield = 0
        star.save(update_fields=[
            'player', 'colonists', 'defenses',
            'ironium_inventory', 'boranium_inventory', 'germanium_inventory',
            'resource_x_inventory', 'resource_y_inventory', 'resource_z_inventory',
            'ironium_yield', 'boranium_yield', 'germanium_yield',
            'resource_x_yield', 'resource_y_yield', 'resource_z_yield',
        ])

        fleet = Fleet.objects.create(
            game=game,
            player=attacker,
            name='Nova Miner',
            x=star.x,
            y=star.y,
            ship_count=10,
            has_bombs='NOVA',
        )
        FleetOrders.objects.create(game=game, fleet=fleet, order_type='BOMB', target_star=star)

        def nova_roll(threshold):
            if threshold == NOVA_STAR_DESTRUCTION_CHANCE:
                return True
            if threshold == NOVA_BLACK_HOLE_SPAWN_CHANCE:
                return False
            if threshold == NOVA_ASTEROID_FIELD_SPAWN_CHANCE:
                return True
            return False

        with patch('dj4xol.turn.roll_chance', side_effect=nova_roll), patch(
            'dj4xol.turn.GameTurn._resolve_planetary_defense_fire_against_fleet',
            return_value={'destroyed': False, 'integrity_lost': 0, 'ships_lost': 0, 'defense_mult': 1.0}
        ), patch('dj4xol.bombardment_rules.scaled_luck_roll', return_value=1.0):
            GameTurn(game).generate_turn()

        self.assertFalse(Star.objects.filter(id=star.id).exists())
        self.assertFalse(Anomaly.objects.filter(game=game, x=star.x, y=star.y).exists())

        asteroid_field = Salvage.objects.get(game=game, x=star.x, y=star.y)
        self.assertEqual(asteroid_field.salvage_type, Salvage.TYPE_ASTEROID_FIELD)
        self.assertEqual(
            asteroid_field.ironium_inventory,
            1200 + int(round((100 / YIELD_DEPLETION_RATE) * NOVA_ASTEROID_FIELD_EXPOSED_POTENTIAL_FRACTION)),
        )
        self.assertEqual(
            asteroid_field.boranium_inventory,
            300 + int(round((50 / YIELD_DEPLETION_RATE) * NOVA_ASTEROID_FIELD_EXPOSED_POTENTIAL_FRACTION)),
        )
        self.assertEqual(asteroid_field.germanium_inventory, 0)
        self.assertEqual(
            asteroid_field.resource_x_inventory,
            40 + int(round((20 / YIELD_DEPLETION_RATE) * NOVA_ASTEROID_FIELD_EXPOSED_POTENTIAL_FRACTION)),
        )

    def test_destroyed_star_retargets_movement_orders_and_deletes_other_orders(self):
        from ..models import FleetOrders

        game = default_game(stars=3)
        attacker = game.players.first()
        defender = self._ensure_other_player(game, attacker, 'bomb_cleanup_def')
        star = game.stars.exclude(pk=attacker.homeworld.pk).first()
        star.player = defender
        star.colonists = 10_000
        star.defenses = 0
        star.save(update_fields=['player', 'colonists', 'defenses'])
        target_x, target_y = _pin_test_star(star, game)

        bomber = Fleet.objects.create(
            game=game,
            player=attacker,
            name='Nova Cleaner',
            x=target_x,
            y=target_y,
            ship_count=10,
            has_bombs='NOVA',
        )
        bomb_order = FleetOrders.objects.create(
            game=game, fleet=bomber, order_type='BOMB', target_star=star
        )

        mover = Fleet.objects.create(
            game=game,
            player=attacker,
            name='Mover',
            x=0,
            y=0,
            ship_count=1,
        )
        move_order = FleetOrders.objects.create(
            game=game, fleet=mover, order_type='MOVE', target_star=star, warpfactor=5
        )

        remoter = Fleet.objects.create(
            game=game,
            player=attacker,
            name='Remote Miner',
            x=target_x - 10,
            y=target_y - 10,
            ship_count=1,
            has_miners='SMALL',
        )
        remote_order = FleetOrders.objects.create(
            game=game, fleet=remoter, order_type='REMOTEMINE', target_star=star
        )

        with patch('dj4xol.turn.roll_chance', return_value=True), patch(
            'dj4xol.turn.GameTurn._resolve_planetary_defense_fire_against_fleet',
            return_value={'destroyed': False, 'integrity_lost': 0, 'ships_lost': 0, 'defense_mult': 1.0}
        ), patch('dj4xol.bombardment_rules.scaled_luck_roll', return_value=1.0):
            GameTurn(game).generate_turn()

        self.assertFalse(Star.objects.filter(id=star.id).exists())
        self.assertFalse(FleetOrders.objects.filter(id=remote_order.id).exists())
        self.assertFalse(FleetOrders.objects.filter(id=bomb_order.id).exists())
        self.assertFalse(FleetOrders.objects.filter(target_star_id=star.id).exists())

        converted_move = FleetOrders.objects.filter(id=move_order.id).first()
        if converted_move is not None:
            self.assertIsNone(converted_move.target_star_id)
            self.assertEqual((converted_move.x, converted_move.y), (target_x, target_y))

    def test_bomb_order_completes_when_population_reaches_zero(self):
        from ..models import FleetOrders

        game = default_game(stars=2)
        attacker = game.players.first()
        defender = self._ensure_other_player(game, attacker, 'bomb_zero_def')
        star = game.stars.exclude(pk=attacker.homeworld.pk).first()
        star.player = defender
        star.colonists = 1000
        star.defenses = 0
        star.save(update_fields=['player', 'colonists', 'defenses'])

        fleet = Fleet.objects.create(
            game=game,
            player=attacker,
            name='Population Killer',
            x=star.x,
            y=star.y,
            ship_count=10,
            has_bombs='CONVENTIONAL',
        )
        order = FleetOrders.objects.create(
            game=game, fleet=fleet, order_type='BOMB', target_star=star
        )

        with patch('dj4xol.turn.GameTurn._resolve_planetary_defense_fire_against_fleet', return_value={
            'destroyed': False, 'integrity_lost': 0, 'ships_lost': 0, 'defense_mult': 1.0
        }), patch('dj4xol.bombardment_rules.scaled_luck_roll', return_value=1.0):
            GameTurn(game).generate_turn()

        star.refresh_from_db()
        self.assertEqual(star.colonists, 0)
        self.assertFalse(FleetOrders.objects.filter(id=order.id).exists())

    def test_bomb_order_defenses_zero_completion_allows_passthrough(self):
        from ..models import FleetOrders

        game = default_game(stars=3)
        attacker = game.players.first()
        defender = self._ensure_other_player(game, attacker, 'bomb_defenses_zero_def')
        star = game.stars.exclude(pk=attacker.homeworld.pk).first()
        star.player = defender
        star.colonists = 500_000
        star.defenses = 5
        star.save(update_fields=['player', 'colonists', 'defenses'])
        star_x, star_y = _pin_test_star(star, game)

        fleet = Fleet.objects.create(
            game=game,
            player=attacker,
            name='Defense Breaker',
            x=star_x,
            y=star_y,
            ship_count=10,
            has_bombs='CONVENTIONAL',
        )
        bomb_order = FleetOrders.objects.create(
            game=game,
            fleet=fleet,
            order_type='BOMB',
            target_star=star,
            bomb_until='DEFENSES_ZERO',
        )
        next_x = star_x + 1
        FleetOrders.objects.create(
            game=game, fleet=fleet, order_type='MOVE', x=next_x, y=star_y, warpfactor=1
        )

        with patch('dj4xol.turn.GameTurn._resolve_planetary_defense_fire_against_fleet', return_value={
            'destroyed': False, 'integrity_lost': 0, 'ships_lost': 0, 'defense_mult': 1.0
        }), patch('dj4xol.turn.bombardment_damage_k', return_value=5):
            GameTurn(game).generate_turn()

        fleet.refresh_from_db()
        star.refresh_from_db()
        self.assertEqual(star.defenses, 0)
        self.assertGreater(star.colonists, 0)
        self.assertFalse(FleetOrders.objects.filter(id=bomb_order.id).exists())
        self.assertEqual((fleet.x, fleet.y), (next_x, star_y))

    def test_bombardment_multiplier_scales_colony_damage(self):
        from ..models import FleetOrders

        game = default_game(stars=2)
        attacker = game.players.first()
        defender = self._ensure_other_player(game, attacker, 'bomb_mult_def')
        attacker_type = ServerRaceType.objects.create(
            code='BMB2',
            name='Heavy Bombers',
            description='Bombardment specialists.',
            bombardment_multiplier=2.0,
        )
        attacker.race_type = attacker_type
        attacker.save(update_fields=['race_type'])

        star = Star.objects.create(
            game=game,
            name='Bomb Target High',
            x=99,
            y=99,
            player=defender,
            colonists=50_000,
            defenses=20,
            mines=20,
            factories=20,
            labs=20,
            shipyards=20,
        )

        fleet = Fleet.objects.create(
            game=game,
            player=attacker,
            name='Heavy Bomber',
            x=star.x,
            y=star.y,
            ship_count=10,
            has_bombs='CONVENTIONAL',
        )
        FleetOrders.objects.create(game=game, fleet=fleet, order_type='BOMB', target_star=star)

        with patch('dj4xol.turn.GameTurn._resolve_planetary_defense_fire_against_fleet', return_value={
            'destroyed': False, 'integrity_lost': 0, 'ships_lost': 0, 'defense_mult': 1.0
        }), patch('dj4xol.turn.bombardment_damage_k', return_value=5):
            GameTurn(game)._execute_bomb_order(fleet, fleet.orders.first())

        star.refresh_from_db()
        self.assertLessEqual(star.defenses, 10)
        self.assertLessEqual(star.colonists, 40_000)
        self.assertLessEqual(star.mines, 10)
        self.assertLessEqual(star.factories, 10)
        self.assertLessEqual(star.labs, 10)
        self.assertLessEqual(star.shipyards, 10)

    def test_bombardment_multiplier_can_reduce_colony_damage(self):
        from ..models import FleetOrders

        game = default_game(stars=2)
        attacker = game.players.first()
        defender = self._ensure_other_player(game, attacker, 'bomb_mult_low_def')
        attacker_type = ServerRaceType.objects.create(
            code='BMBL',
            name='Light Bombers',
            description='Reduced bombardment output.',
            bombardment_multiplier=0.5,
        )
        attacker.race_type = attacker_type
        attacker.save(update_fields=['race_type'])

        star = Star.objects.create(
            game=game,
            name='Bomb Target Low',
            x=98,
            y=98,
            player=defender,
            colonists=50_000,
            defenses=20,
            mines=20,
            factories=20,
            labs=20,
            shipyards=20,
        )

        fleet = Fleet.objects.create(
            game=game,
            player=attacker,
            name='Light Bomber',
            x=star.x,
            y=star.y,
            ship_count=10,
            has_bombs='CONVENTIONAL',
        )
        FleetOrders.objects.create(game=game, fleet=fleet, order_type='BOMB', target_star=star)

        with patch('dj4xol.turn.GameTurn._resolve_planetary_defense_fire_against_fleet', return_value={
            'destroyed': False, 'integrity_lost': 0, 'ships_lost': 0, 'defense_mult': 1.0
        }), patch('dj4xol.turn.bombardment_damage_k', return_value=6):
            GameTurn(game)._execute_bomb_order(fleet, fleet.orders.first())

        star.refresh_from_db()
        self.assertEqual(star.defenses, 17)
        self.assertEqual(star.colonists, 47_000)
        self.assertEqual(star.mines, 17)
        self.assertEqual(star.factories, 17)
        self.assertEqual(star.labs, 17)
        self.assertEqual(star.shipyards, 17)

    def test_bomb_order_once_completes_and_allows_passthrough(self):
        from ..models import FleetOrders

        game = default_game(stars=3)
        attacker = game.players.first()
        defender = self._ensure_other_player(game, attacker, 'bomb_once_def')
        star = game.stars.exclude(pk=attacker.homeworld.pk).first()
        star.player = defender
        star.colonists = 100_000
        star.defenses = 10
        star.save(update_fields=['player', 'colonists', 'defenses'])
        star_x, star_y = _pin_test_star(star, game)

        fleet = Fleet.objects.create(
            game=game,
            player=attacker,
            name='Continuous Bomber',
            x=star_x,
            y=star_y,
            ship_count=10,
            has_bombs='CONVENTIONAL',
        )
        bomb_order = FleetOrders.objects.create(
            game=game,
            fleet=fleet,
            order_type='BOMB',
            target_star=star,
            bomb_until='ONCE',
        )
        next_x = star_x + 1
        FleetOrders.objects.create(
            game=game, fleet=fleet, order_type='MOVE', x=next_x, y=star_y, warpfactor=1
        )

        with patch('dj4xol.turn.GameTurn._resolve_planetary_defense_fire_against_fleet', return_value={
            'destroyed': False, 'integrity_lost': 0, 'ships_lost': 0, 'defense_mult': 1.0
        }), patch('dj4xol.bombardment_rules.scaled_luck_roll', return_value=1.0):
            GameTurn(game).generate_turn()

        fleet.refresh_from_db()
        self.assertFalse(FleetOrders.objects.filter(id=bomb_order.id).exists())
        self.assertEqual((fleet.x, fleet.y), (next_x, star_y))

    def test_bombardment_sends_defender_loss_message(self):
        from ..models import FleetOrders

        game = default_game(stars=2)
        attacker = game.players.first()
        defender = self._ensure_other_player(game, attacker, 'bomb_msg_def')
        star = game.stars.exclude(pk=attacker.homeworld.pk).first()
        star.player = defender
        star.colonists = 50_000
        star.defenses = 10
        star.mines = 5
        star.factories = 5
        star.labs = 5
        star.shipyards = 2
        star.save(update_fields=['player', 'colonists', 'defenses', 'mines', 'factories', 'labs', 'shipyards'])

        fleet = Fleet.objects.create(
            game=game,
            player=attacker,
            name='Message Bomber',
            x=star.x,
            y=star.y,
            ship_count=25,
            has_bombs='CONVENTIONAL',
        )
        FleetOrders.objects.create(game=game, fleet=fleet, order_type='BOMB', target_star=star)

        with patch('dj4xol.turn.GameTurn._resolve_planetary_defense_fire_against_fleet', return_value={
            'destroyed': False, 'integrity_lost': 0, 'ships_lost': 0, 'defense_mult': 1.0
        }), patch('dj4xol.bombardment_rules.scaled_luck_roll', return_value=1.0):
            GameTurn(game).generate_turn()

        self.assertTrue(
            defender.messages.filter(
                message__icontains='bombarded',
            ).filter(
                message__icontains=star.name,
            ).exists()
        )


class TestRemoteMineOrders(TestCase):
    def test_remote_mine_blocks_queue_until_fleet_inventory_full(self):
        from ..models import FleetOrders

        game = default_game(stars=2)
        player = game.players.first()
        star = game.stars.exclude(pk=player.homeworld.pk).first()
        star.player = None
        star.ironium_yield = 100
        star.boranium_yield = 0
        star.germanium_yield = 0
        star.resource_x_yield = 0
        star.resource_y_yield = 0
        star.resource_z_yield = 0
        star.save(update_fields=[
            'player',
            'ironium_yield', 'boranium_yield', 'germanium_yield',
            'resource_x_yield', 'resource_y_yield', 'resource_z_yield',
        ])
        star_x, star_y = _pin_test_star(star, game)

        fleet = Fleet.objects.create(
            game=game,
            player=player,
            name='Remote Miner',
            x=star_x,
            y=star_y,
            ship_count=1,
            has_miners='SMALL',
            cargo_capacity=20,
            ironium_inventory=0,
            boranium_inventory=0,
            germanium_inventory=0,
        )
        mine_order = FleetOrders.objects.create(
            game=game, fleet=fleet, order_type='REMOTEMINE', target_star=star, repeat=True
        )
        next_x = star_x + 1
        FleetOrders.objects.create(
            game=game, fleet=fleet, order_type='MOVE', x=next_x, y=star_y, warpfactor=1
        )

        GameTurn(game).generate_turn()
        fleet.refresh_from_db()
        self.assertEqual((fleet.x, fleet.y), (star_x, star_y))
        self.assertEqual(fleet.ironium_inventory, 10)
        self.assertTrue(FleetOrders.objects.filter(id=mine_order.id).exists())

        GameTurn(game).generate_turn()
        fleet.refresh_from_db()
        self.assertEqual(fleet.ironium_inventory, 20)
        self.assertFalse(FleetOrders.objects.filter(id=mine_order.id).exists())
        self.assertEqual((fleet.x, fleet.y), (next_x, star_y))

    def test_remote_mine_single_cycle_completion_allows_passthrough(self):
        from ..models import FleetOrders

        game = default_game(stars=2)
        player = game.players.first()
        star = game.stars.exclude(pk=player.homeworld.pk).first()
        star.player = None
        star.ironium_yield = 100
        star.boranium_yield = 0
        star.germanium_yield = 0
        star.resource_x_yield = 0
        star.resource_y_yield = 0
        star.resource_z_yield = 0
        star.save(update_fields=[
            'player',
            'ironium_yield', 'boranium_yield', 'germanium_yield',
            'resource_x_yield', 'resource_y_yield', 'resource_z_yield',
        ])
        star_x, star_y = _pin_test_star(star, game)

        fleet = Fleet.objects.create(
            game=game,
            player=player,
            name='Cycle Miner',
            x=star_x,
            y=star_y,
            ship_count=1,
            has_miners='SMALL',
            cargo_capacity=50,
            ironium_inventory=0,
        )
        order = FleetOrders.objects.create(
            game=game,
            fleet=fleet,
            order_type='REMOTEMINE',
            target_star=star,
            mine_until_full=False,
        )
        next_x = star_x + 1
        FleetOrders.objects.create(
            game=game, fleet=fleet, order_type='MOVE', x=next_x, y=star_y, warpfactor=1
        )

        GameTurn(game).generate_turn()
        fleet.refresh_from_db()
        self.assertFalse(FleetOrders.objects.filter(id=order.id).exists())
        self.assertEqual(fleet.ironium_inventory, 10)
        self.assertEqual((fleet.x, fleet.y), (next_x, star_y))

    def test_remote_mine_size_and_ship_count_multiplier(self):
        from ..models import FleetOrders

        game = default_game(stars=4)
        player = game.players.first()
        stars = list(game.stars.exclude(pk=player.homeworld.pk).order_by('id')[:3])
        for star in stars:
            star.player = None
            star.ironium_yield = 100
            star.boranium_yield = 0
            star.germanium_yield = 0
            star.resource_x_yield = 0
            star.resource_y_yield = 0
            star.resource_z_yield = 0
            star.save(update_fields=[
                'player',
                'ironium_yield', 'boranium_yield', 'germanium_yield',
                'resource_x_yield', 'resource_y_yield', 'resource_z_yield',
            ])

        small_fleet = Fleet.objects.create(
            game=game, player=player, name='Small Miner',
            x=stars[0].x, y=stars[0].y, ship_count=1, has_miners='SMALL',
            cargo_capacity=1000
        )
        medium_fleet = Fleet.objects.create(
            game=game, player=player, name='Medium Miner',
            x=stars[1].x, y=stars[1].y, ship_count=1, has_miners='MEDIUM',
            cargo_capacity=1000
        )
        large_fleet = Fleet.objects.create(
            game=game, player=player, name='Large Miner',
            x=stars[2].x, y=stars[2].y, ship_count=2, has_miners='LARGE',
            cargo_capacity=1000
        )
        FleetOrders.objects.create(game=game, fleet=small_fleet, order_type='REMOTEMINE', target_star=stars[0])
        FleetOrders.objects.create(game=game, fleet=medium_fleet, order_type='REMOTEMINE', target_star=stars[1])
        FleetOrders.objects.create(game=game, fleet=large_fleet, order_type='REMOTEMINE', target_star=stars[2])

        GameTurn(game).generate_turn()

        small_fleet.refresh_from_db()
        medium_fleet.refresh_from_db()
        large_fleet.refresh_from_db()
        self.assertEqual(small_fleet.ironium_inventory, 10)   # 1 * SMALL(1) * 10
        self.assertEqual(medium_fleet.ironium_inventory, 20)  # 1 * MEDIUM(2) * 10
        self.assertEqual(large_fleet.ironium_inventory, 80)   # 2 * LARGE(4) * 10

    def test_remote_mine_focus_limits_extraction_to_selected_minerals(self):
        from ..models import FleetOrders

        game = default_game(stars=2)
        player = game.players.first()
        star = game.stars.exclude(pk=player.homeworld.pk).first()
        star.player = None
        star.ironium_yield = 100
        star.boranium_yield = 100
        star.germanium_yield = 0
        star.resource_x_yield = 0
        star.resource_y_yield = 0
        star.resource_z_yield = 0
        star.save(update_fields=[
            'player',
            'ironium_yield', 'boranium_yield', 'germanium_yield',
            'resource_x_yield', 'resource_y_yield', 'resource_z_yield',
        ])

        fleet = Fleet.objects.create(
            game=game,
            player=player,
            name='Focused Miner',
            x=star.x,
            y=star.y,
            ship_count=1,
            has_miners='LARGE',
            cargo_capacity=1000,
        )
        FleetOrders.objects.create(
            game=game,
            fleet=fleet,
            order_type='REMOTEMINE',
            target_star=star,
            remotemine_focus='boranium',
        )

        GameTurn(game).generate_turn()

        fleet.refresh_from_db()
        self.assertEqual(fleet.boranium_inventory, 40)
        self.assertEqual(fleet.ironium_inventory, 0)

    def test_remote_mine_deposits_overflow_to_surface(self):
        from ..models import FleetOrders

        game = default_game(stars=2)
        player = game.players.first()
        star = game.stars.exclude(pk=player.homeworld.pk).first()
        star.player = None
        star.ironium_yield = 100
        star.boranium_yield = 0
        star.germanium_yield = 0
        star.ironium_inventory = 0
        star.resource_x_yield = 0
        star.resource_y_yield = 0
        star.resource_z_yield = 0
        star.save(update_fields=[
            'player',
            'ironium_yield', 'boranium_yield', 'germanium_yield',
            'ironium_inventory',
            'resource_x_yield', 'resource_y_yield', 'resource_z_yield',
        ])

        fleet = Fleet.objects.create(
            game=game, player=player, name='Overflow Miner',
            x=star.x, y=star.y, ship_count=1, has_miners='SMALL',
            cargo_capacity=5, ironium_inventory=0
        )
        FleetOrders.objects.create(game=game, fleet=fleet, order_type='REMOTEMINE', target_star=star)

        GameTurn(game).generate_turn()

        fleet.refresh_from_db()
        star.refresh_from_db()
        self.assertEqual(fleet.ironium_inventory, 5)
        self.assertEqual(star.ironium_inventory, 5)

    def test_remote_mining_hostile_colony_can_cause_harass_damage(self):
        from ..models import FleetOrders

        game = default_game(stars=2)
        game.random_events = False
        game.save(update_fields=['random_events'])
        attacker = game.players.first()
        defender = Player.objects.filter(game=game).exclude(id=attacker.id).first()
        if defender is None:
            other_user = User.objects.create_user('remote_harass_def', 'remote_harass_def@test.com', 'pass')
            other_account = Account.objects.create(django_user=other_user)
            defender = Player.objects.create(game=game, account=other_account, race_type=attacker.race_type)
        defender.race_type.population_growth_multiplier = 0
        defender.race_type.save(update_fields=['population_growth_multiplier'])

        star = game.stars.exclude(pk=attacker.homeworld.pk).first()
        star.player = defender
        star.colonists = 100_000
        star.defenses = 20
        star.mines = 20
        star.factories = 20
        star.labs = 20
        star.shipyards = 5
        star.save(update_fields=['player', 'colonists', 'defenses', 'mines', 'factories', 'labs', 'shipyards'])

        fleet = Fleet.objects.create(
            game=game, player=attacker, name='Harass Miner',
            x=star.x, y=star.y, ship_count=3, has_miners='LARGE', cargo_capacity=1000
        )
        FleetOrders.objects.create(game=game, fleet=fleet, order_type='REMOTEMINE', target_star=star)

        with patch('dj4xol.turn.roll_chance', return_value=True), \
             patch('dj4xol.bombardment_rules.scaled_luck_roll', return_value=1.0), \
             patch('dj4xol.turn.bombardment_damage_k', return_value=20):
            GameTurn(game).generate_turn()

        star.refresh_from_db()
        self.assertLess(star.colonists, 100_000)
        self.assertTrue(
            star.defenses < 20 or
            star.mines < 20 or
            star.factories < 20 or
            star.labs < 20 or
            star.shipyards < 5
        )

    def test_remote_mining_defense_fire_applies_additional_damage_multiplier(self):
        game = default_game(stars=2)
        attacker = game.players.first()
        defender = Player.objects.filter(game=game).exclude(id=attacker.id).first()
        if defender is None:
            other_user = User.objects.create_user('remote_mult_def', 'remote_mult_def@test.com', 'pass')
            other_account = Account.objects.create(django_user=other_user)
            defender = Player.objects.create(game=game, account=other_account, race_type=attacker.race_type)

        star = game.stars.exclude(pk=attacker.homeworld.pk).first()
        star.player = defender
        star.colonists = 10_000
        star.mines = 0
        star.factories = 0
        star.labs = 0
        star.shipyards = 0
        star.defenses = 12
        star.save(update_fields=['player', 'colonists', 'mines', 'factories', 'labs', 'shipyards', 'defenses'])

        fleet_base = Fleet.objects.create(
            game=game, player=attacker, name='Base Miner', x=star.x, y=star.y, ship_count=3, integrity=100
        )
        fleet_boost = Fleet.objects.create(
            game=game, player=attacker, name='Boost Miner', x=star.x, y=star.y, ship_count=3, integrity=100
        )

        turn = GameTurn(game)
        with patch('dj4xol.turn.roll_chance', return_value=False):
            base = turn._resolve_planetary_defense_fire_against_fleet(
                star, fleet_base, damage_multiplier=1.0
            )
            boosted = turn._resolve_planetary_defense_fire_against_fleet(
                star, fleet_boost, damage_multiplier=1.25
            )

        self.assertGreaterEqual(boosted['integrity_lost'], base['integrity_lost'])
        fleet_base.refresh_from_db()
        fleet_boost.refresh_from_db()
        self.assertLessEqual(fleet_boost.integrity, fleet_base.integrity)


class TestHomeworldLossAndDerelicts(TestCase):
    def _make_two_player_game(self):
        race = get_default_race()
        user1 = User.objects.create_user('p1_user', 'p1@test.com', 'pass')
        user2 = User.objects.create_user('p2_user', 'p2@test.com', 'pass')
        account1 = Account.objects.create(django_user=user1)
        account2 = Account.objects.create(django_user=user2)
        factory = GameFactory()
        factory.set_map_size(120, 120)
        factory.set_owner(account1)
        factory.game.joinable = True
        factory.create_stars(6)
        game = factory.save()
        if game.random_events or game.anomalies_enabled:
            game.random_events = False
            game.anomalies_enabled = False
            game.save(update_fields=['random_events', 'anomalies_enabled'])
        player1 = factory.join_player(account1, race)
        player2 = factory.join_player(account2, race)
        return game, player1, player2

    def _find_empty_location(self, game):
        for x in range(0, int(game.map_size_x or 0)):
            for y in range(0, int(game.map_size_y or 0)):
                if not Star.objects.filter(game=game, x=x, y=y).exists():
                    return x, y
        return 0, 0

    def test_transfer_raid_thwarted_blocks_load(self):
        game, attacker, defender = self._make_two_player_game()
        star = defender.homeworld
        star.ironium_inventory = 120
        star.save(update_fields=['ironium_inventory'])
        fleet = attacker.fleets.first()
        fleet.x = star.x
        fleet.y = star.y
        fleet.ironium_inventory = 0
        fleet.save(update_fields=['x', 'y', 'ironium_inventory'])
        order = FleetOrders.objects.create(
            game=game,
            fleet=fleet,
            order_type='TRANSFER',
            transfer_type='LOAD',
            target_star=star,
        )
        order.transfer_ironium = 50
        order.save(update_fields=['transfer_ironium'])
        turn = GameTurn(game)
        with patch.object(GameTurn, '_resolve_transfer_raid_defense_fire', return_value={
            'destroyed': False,
            'integrity_lost': 50,
            'ships_lost': 0,
            'defense_mult': 1.0,
        }):
            with patch.object(GameTurn, '_transfer_raid_successful', return_value=False):
                result = turn._execute_transfer_order(fleet, order)
        self.assertEqual(result, 'executed')
        star.refresh_from_db()
        fleet.refresh_from_db()
        self.assertEqual(star.ironium_inventory, 120)
        self.assertEqual(fleet.ironium_inventory, 0)

    def test_transfer_raid_success_allows_load_after_damage(self):
        game, attacker, defender = self._make_two_player_game()
        star = defender.homeworld
        star.ironium_inventory = 120
        star.save(update_fields=['ironium_inventory'])
        fleet = attacker.fleets.first()
        fleet.x = star.x
        fleet.y = star.y
        fleet.ironium_inventory = 0
        fleet.save(update_fields=['x', 'y', 'ironium_inventory'])
        order = FleetOrders.objects.create(
            game=game,
            fleet=fleet,
            order_type='TRANSFER',
            transfer_type='LOAD',
            target_star=star,
        )
        order.transfer_ironium = 50
        order.save(update_fields=['transfer_ironium'])
        turn = GameTurn(game)
        with patch.object(GameTurn, '_resolve_transfer_raid_defense_fire', return_value={
            'destroyed': False,
            'integrity_lost': 40,
            'ships_lost': 0,
            'defense_mult': 1.0,
        }):
            with patch.object(GameTurn, '_transfer_raid_successful', return_value=True):
                result = turn._execute_transfer_order(fleet, order)
        self.assertEqual(result, 'executed')
        star.refresh_from_db()
        fleet.refresh_from_db()
        self.assertLess(star.ironium_inventory, 120)
        self.assertGreater(fleet.ironium_inventory, 0)

    def test_transfer_raid_success_chance_scales_with_defense_and_damage(self):
        base = transfer_raid_success_chance(
            attacker_strength=2.0,
            defender_strength=0.5,
            attacker_luck=1.0,
            defender_luck=1.0,
        )
        heavy = transfer_raid_success_chance(
            attacker_strength=2.0,
            defender_strength=5.0,
            attacker_luck=1.0,
            defender_luck=1.0,
        )
        damaged = transfer_raid_success_chance(
            attacker_strength=2.0,
            defender_strength=0.5,
            attacker_luck=1.0,
            defender_luck=1.0,
            integrity_lost=50,
            ships_lost=1,
            ship_count=4,
        )
        self.assertGreater(base, heavy)
        self.assertLess(damaged, base)

    def test_homeworld_reassigned_to_highest_population(self):
        game, player, _ = self._make_two_player_game()
        homeworld = player.homeworld
        other_stars = list(game.stars.exclude(id=homeworld.id)[:2])
        star_a, star_b = other_stars
        for star in (star_a, star_b):
            star.player = player
            star.gravity = player.gravity_center
            star.temperature = player.temperature_center
            star.radiation = player.radiation_center
        star_a.colonists = 4000
        star_b.colonists = 9000
        star_a.save(update_fields=['player', 'gravity', 'temperature', 'radiation', 'colonists'])
        star_b.save(update_fields=['player', 'gravity', 'temperature', 'radiation', 'colonists'])

        turn = GameTurn(game)
        turn._handle_homeworld_loss(player, lost_star=homeworld, location=(homeworld.x, homeworld.y))
        player.refresh_from_db()
        self.assertEqual(player.homeworld_id, star_b.id)

    def test_fixed_homeworld_defeat_abandons_colonies(self):
        game, player, _ = self._make_two_player_game()
        player.fixed_homeworld = True
        player.save(update_fields=['fixed_homeworld'])
        homeworld = player.homeworld
        other_star = game.stars.exclude(id=homeworld.id).first()
        other_star.player = player
        other_star.colonists = 6000
        other_star.save(update_fields=['player', 'colonists'])
        fleet = player.fleets.first()
        turn = GameTurn(game)
        turn._handle_homeworld_loss(player, lost_star=homeworld, location=(homeworld.x, homeworld.y))
        player.refresh_from_db()
        other_star.refresh_from_db()
        fleet.refresh_from_db()
        self.assertTrue(player.defeated)
        self.assertIsNone(other_star.player)
        self.assertEqual(other_star.colonists, 0)
        self.assertIsNone(fleet.player)

    def test_defeated_players_excluded_from_quorum(self):
        game, player1, player2 = self._make_two_player_game()
        player1.defeated = True
        player1.turned_in = False
        player1.save(update_fields=['defeated', 'turned_in'])
        player2.turned_in = True
        player2.save(update_fields=['turned_in'])
        self.assertTrue(GameTurn(game).check_quorum())

    def test_derelict_fleet_claimed_on_encounter(self):
        game, player, _ = self._make_two_player_game()
        x, y = self._find_empty_location(game)
        player_fleet = player.fleets.first()
        player_fleet.x = x
        player_fleet.y = y
        player_fleet.save(update_fields=['x', 'y'])
        derelict = Fleet.objects.create(
            game=game,
            player=None,
            name='Derelict',
            x=x,
            y=y,
            ship_count=1,
            integrity=40,
        )
        turn = GameTurn(game)
        with patch('dj4xol.turn.roll_chance', return_value=True):
            turn.resolve_derelict_encounters()
        derelict.refresh_from_db()
        self.assertEqual(derelict.player_id, player.id)

    def test_warp_speed_multiplier_scales_distance(self):
        game = default_game(stars=5)
        game.warp_speed_multiplier = 2.0
        game.save(update_fields=['warp_speed_multiplier'])
        player = game.players.first()
        fleet = player.fleets.first()
        fleet.x = 0
        fleet.y = 0
        fleet.save(update_fields=['x', 'y'])
        order = FleetOrders.objects.create(
            game=game,
            fleet=fleet,
            order_type='MOVE',
            warpfactor=5,
            target_kind='SPACE',
            x=9,
            y=0,
        )
        turn = GameTurn(game)
        turn._move_toward_destination(fleet, order)
        self.assertEqual((fleet.x, fleet.y), (9, 0))

    def test_intercept_ignores_game_warp_speed_multiplier(self):
        game = default_game(stars=5)
        game.warp_speed_multiplier = 2.0
        game.save(update_fields=['warp_speed_multiplier'])
        player = game.players.first()
        interceptor = player.fleets.first()
        interceptor.x = 10
        interceptor.y = 10
        interceptor.save(update_fields=['x', 'y'])
        target = Fleet.objects.create(
            game=game,
            player=player,
            name='Target',
            x=19,
            y=10,
            ship_count=1,
            integrity=100,
        )
        order = FleetOrders.objects.create(
            game=game,
            fleet=interceptor,
            order_type='INTERCEPT',
            target_fleet=target,
            warpfactor=5,
        )

        turn = GameTurn(game)
        turn._move_toward_destination(interceptor, order)

        self.assertEqual((interceptor.x, interceptor.y), (15, 10))

    def test_intercept_ignores_warp_advantage_for_interceptor_movement(self):
        from numpy import array as nparray
        from numpy import linalg

        game = default_game(stars=5)
        player = game.players.first()
        interceptor = player.fleets.first()
        interceptor.x = 10
        interceptor.y = 10
        interceptor.warp_advantage = 0.9
        interceptor.save(update_fields=['x', 'y', 'warp_advantage'])
        target = Fleet.objects.create(
            game=game,
            player=player,
            name='Target',
            x=20,
            y=13,
            ship_count=1,
            integrity=100,
        )
        order = FleetOrders.objects.create(
            game=game,
            fleet=interceptor,
            order_type='INTERCEPT',
            target_fleet=target,
            warpfactor=5,
        )

        turn = GameTurn(game)
        turn._move_toward_destination(interceptor, order)

        vector = nparray([target.x, target.y]) - nparray([10, 10])
        distance = linalg.norm(vector)
        normalised = vector / distance
        expected_step = normalised * 5.0
        expected_x = 10 + turn._quantized_axis_step(
            expected_step[0], interceptor.short_id, 'x'
        )
        expected_y = 10 + turn._quantized_axis_step(
            expected_step[1], interceptor.short_id, 'y'
        )
        self.assertEqual((interceptor.x, interceptor.y), (expected_x, expected_y))

    def test_warp_advantage_adds_fractional_speed_to_distance(self):
        game = default_game(stars=5)
        player = game.players.first()
        fleet = player.fleets.first()
        fleet.x = 0
        fleet.y = 0
        fleet.warp_advantage = 0.9
        fleet.save(update_fields=['x', 'y', 'warp_advantage'])
        order = FleetOrders.objects.create(
            game=game,
            fleet=fleet,
            order_type='MOVE',
            warpfactor=5,
            target_kind='SPACE',
            x=30,
            y=0,
        )
        turn = GameTurn(game)
        turn._move_toward_destination(fleet, order)
        expected_step = turn._quantized_axis_step(5.9, fleet.short_id, 'x')
        self.assertEqual(fleet.x, expected_step)
        self.assertEqual(fleet.y, 0)

    def test_get_fleet_current_speed_uses_warp_advantage(self):
        game = default_game(stars=5)
        player = game.players.first()
        fleet = player.fleets.first()
        fleet.warp_advantage = 0.9
        fleet.save(update_fields=['warp_advantage'])
        FleetOrders.objects.create(
            game=game,
            fleet=fleet,
            order_type='MOVE',
            warpfactor=5,
            target_kind='SPACE',
            x=fleet.x + 20,
            y=fleet.y,
        )
        speed = GameTurn(game)._get_fleet_current_speed(fleet)
        self.assertAlmostEqual(speed, 5.9, places=2)
