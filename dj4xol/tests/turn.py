from ..turn import (
    GameTurn, habitability_proportion, calculate_growth_factor, capacity_modifier,
    effective_capacity, BILLION, calculate_employment_percent, calculate_economy_percent,
    calculate_available_buildpoints, calculate_productivity_percent, calculate_economy_factor,
    COLONISTS_PER_JOB, BUILDPOINTS_PER_FACTORY, KT_PER_MINE, HOMEWORLD_MIN_YIELD
)
from ..models import ProductionOrder, GameMessage, Fleet, Star
from django.test import TestCase
from ._util import default_game, get_default_race
from unittest.mock import patch
import random


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

    def test_no_growth_at_edge(self):
        """Population stable when all envs at edge of habitability."""
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
        # Should be stable (no growth, no decline)
        self.assertEqual(homeworld.colonists, 1000)

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
        latest_msg = player.messages.order_by('-id').first()
        # Check for environmental death keywords
        msg_lower = latest_msg.message.lower()
        self.assertTrue(
            'perished' in msg_lower or 'died' in msg_lower or
            'lost' in msg_lower or 'succumbed' in msg_lower or
            'claimed' in msg_lower or 'fatal' in msg_lower or
            'environment' in msg_lower or 'harsh' in msg_lower or
            'hostile' in msg_lower or 'inhospitable' in msg_lower or
            'hazard' in msg_lower or 'exposure' in msg_lower,
            f"Expected death-related message, got: {latest_msg.message}"
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


class TestTerraforming(TestCase):
    def test_terraforming_moves_toward_ideal(self):
        """Terraforming order should move environmental value toward player's ideal."""
        game = default_game(stars=5)
        player = game.players.first()
        homeworld = player.homeworld
        # Set gravity away from player's ideal
        homeworld.gravity = 0.5
        homeworld.factories = 10  # Provide buildpoints (100 bp)
        homeworld.colonists = 10000  # Staff the factories
        homeworld.ironium_inventory = 2000  # Provide resources
        homeworld.save()
        player_ideal = player.gravity_center  # Should be 1.0 by default
        # Add terraforming order
        ProductionOrder.objects.create(
            game=game,
            star=homeworld,
            order_type='TERRAFORM_GRAVITY'
        )
        initial_gravity = homeworld.gravity
        GameTurn(game).generate_turn()
        homeworld.refresh_from_db()
        # Gravity should have moved toward player's ideal
        self.assertGreater(homeworld.gravity, initial_gravity)
        self.assertLess(homeworld.gravity, player_ideal)

    def test_terraforming_multiple_factors(self):
        """Multiple terraforming orders should all be processed."""
        game = default_game(stars=5)
        player = game.players.first()
        homeworld = player.homeworld
        homeworld.gravity = 0.5
        homeworld.temperature = 1.8
        homeworld.factories = 20  # Provide buildpoints (200 bp for 2 terraforms)
        homeworld.colonists = 20000  # Staff the factories
        homeworld.ironium_inventory = 2000  # For gravity terraform
        homeworld.boranium_inventory = 2000  # For temperature terraform
        homeworld.save()
        ProductionOrder.objects.create(game=game, star=homeworld, order_type='TERRAFORM_GRAVITY')
        ProductionOrder.objects.create(game=game, star=homeworld, order_type='TERRAFORM_TEMPERATURE')
        initial_g = homeworld.gravity
        initial_t = homeworld.temperature
        GameTurn(game).generate_turn()
        homeworld.refresh_from_db()
        # Both should have moved toward ideals
        self.assertGreater(homeworld.gravity, initial_g)
        self.assertLess(homeworld.temperature, initial_t)


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
        star.factories = 7
        star.colonists = 7000  # Fully staff the factories
        self.assertEqual(calculate_available_buildpoints(star), 7 * BUILDPOINTS_PER_FACTORY)

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

    def test_economy_percent_employment_only(self):
        """With no productivity, economy is employment/2."""
        game = default_game()
        star = game.stars.first()
        star.colonists = 10000
        star.mines = 5
        star.factories = 5  # 100% employment
        # economy = 100/2 + 0/2 = 50%
        self.assertEqual(calculate_economy_percent(star), 50)

    def test_economy_percent_minimum_zero(self):
        """Economy percent never goes below 0."""
        game = default_game()
        star = game.stars.first()
        star.colonists = 100000
        star.mines = 0
        star.factories = 0  # 0% employment
        self.assertEqual(calculate_economy_percent(star), 0)

    def test_economy_factor_range(self):
        """Economy factor should be in 0-1 range (coefficient form)."""
        game = default_game()
        star = game.stars.first()
        star.colonists = 10000
        star.mines = 5
        star.factories = 5  # 100% employment -> 50% economy
        self.assertEqual(calculate_economy_factor(star), 0.5)

    def test_economy_boosts_habitability_factor(self):
        """Economy factor should boost habitability calculation."""
        from ..turn import calculate_habitability_factor
        game = default_game()
        player = game.players.first()
        star = player.homeworld

        # Get baseline habitability with no economy
        star.mines = 0
        star.factories = 0
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

    def test_mining_extracts_minerals(self):
        """Mines should extract minerals to surface inventory."""
        game = default_game()
        player = game.players.first()
        star = player.homeworld
        star.mines = 5
        star.ironium = 50  # 50% yield
        star.boranium = 30  # 30% yield
        star.germanium_yield = 20  # 20% yield
        star.ironium_inventory = 0
        star.boranium_inventory = 0
        star.germanium_inventory = 0
        star.save()

        GameTurn(game).generate_turn()

        star.refresh_from_db()
        # 5 mines * 10kt = 50kt total, distributed by yield
        # Total yield = 100%, so: 50*50/100=25, 50*30/100=15, 50*20/100=10
        self.assertEqual(star.ironium_inventory, 25)
        self.assertEqual(star.boranium_inventory, 15)
        self.assertEqual(star.germanium_inventory, 10)

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
        star.ironium = 100  # 100% yield (only ironium)
        star.boranium = 0
        star.germanium_yield = 0
        star.ironium_inventory = 100  # Start with some
        star.save()

        GameTurn(game).generate_turn()

        star.refresh_from_db()
        # 2 mines * 10kt = 20kt, all to ironium (100% of total yield)
        self.assertEqual(star.ironium_inventory, 120)

    def test_mining_low_yield_has_chance(self):
        """Low yield resources should still have a chance to produce."""
        game = default_game()
        player = game.players.first()
        star = player.homeworld
        star.mines = 1
        star.ironium = 1  # 1% yield
        star.boranium = 99  # 99% yield
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
        star.ironium = HOMEWORLD_MIN_YIELD  # At the floor
        star.boranium = 0
        star.germanium_yield = 0
        star.save()

        # Run several turns
        for _ in range(10):
            GameTurn(game).generate_turn()

        star.refresh_from_db()
        self.assertGreaterEqual(star.ironium, HOMEWORLD_MIN_YIELD)

    def test_mining_non_homeworld_can_deplete(self):
        """Non-homeworld yields can drop below 30%."""
        game = default_game(stars=5)
        player = game.players.first()
        # Get a non-homeworld star
        other_star = game.stars.exclude(pk=player.homeworld.pk).first()
        other_star.player = player
        other_star.colonists = 1000
        other_star.mines = 5000  # Many mines to force depletion
        other_star.ironium = 31  # Just above homeworld floor
        other_star.boranium = 0
        other_star.germanium_yield = 0
        other_star.save()

        # Run many turns to trigger depletion
        # With 5000 mines * 10kt = 50000kt, depletion_chance = 50000/(31*10000) = 16% per turn
        for _ in range(50):
            GameTurn(game).generate_turn()

        other_star.refresh_from_db()
        # Should have depleted below 31 (with high probability)
        self.assertLess(other_star.ironium, 31)


class TestFleetTransferOrders(TestCase):
    """Test fleet transfer order functionality."""
    
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
        self.assertEqual(fleet.germanium, 100)
        self.assertEqual(fleet.colonists, 50)  # 50k individuals stored as 50kt
        
        # Order should be deleted
        self.assertEqual(fleet.orders.count(), 0)
    
    def test_transfer_unload_to_star_at_location(self):
        """Test instant unload transfer execution."""
        from ..models import FleetOrders, Fleet
        
        game = default_game()
        player = game.players.first()
        star = player.homeworld
        
        # Set up star with some existing resources
        star.ironium_inventory = 100
        star.boranium_inventory = 50
        star.germanium_inventory = 25
        star.colonists = 5000  # 5k individuals
        star.save()
        
        # Create fleet with cargo at same location
        fleet = Fleet.objects.create(
            game=game,
            player=player,
            name="Cargo Fleet",
            x=star.x,
            y=star.y,
            ironium=200,
            boranium=150,
            germanium=75,
            colonists=10  # 10k individuals stored as 10kt
        )
        
        # Create unload order
        order = FleetOrders.objects.create(
            game=game,
            fleet=fleet,
            order_type='TRANSFER',
            target_star=star,
            transfer_type='UNLOAD',
            transfer_ironium=200,
            transfer_boranium=150,
            transfer_germanium=75,
            transfer_colonists=10
        )
        
        # Generate turn
        GameTurn(game).generate_turn()
        
        # Refresh objects
        star.refresh_from_db()
        fleet.refresh_from_db()
        
        # Star should have resources added
        self.assertEqual(star.ironium_inventory, 300)   # 100 + 200
        self.assertEqual(star.boranium_inventory, 200)  # 50 + 150
        self.assertEqual(star.germanium_inventory, 100) # 25 + 75
        self.assertEqual(star.colonists, 15000)       # 5000 + 10000
        
        # Fleet should have resources removed
        self.assertEqual(fleet.ironium_inventory, 0)
        self.assertEqual(fleet.boranium_inventory, 0)
        self.assertEqual(fleet.germanium, 0)
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
        self.assertEqual(fleet.germanium, 250) # 1000 * 0.25
        self.assertEqual(fleet.colonists, 250) # 1000 * 0.25
        
        # Total cargo should equal capacity
        self.assertEqual(fleet.cargo_used, 1000)
        
        # Star should have corresponding amounts removed
        self.assertEqual(star.ironium_inventory, 4750)  # 5000 - 250
        self.assertEqual(star.boranium_inventory, 4750)
        self.assertEqual(star.germanium_inventory, 4750)
        self.assertEqual(star.colonists, 50000)  # 100000 - 50000 (250kt * 1000)
    
    def test_transfer_move_then_execute(self):
        """Test transfer that requires movement first."""
        from ..models import FleetOrders, Fleet
        
        game = default_game(stars=5)
        player = game.players.first()
        source_star = player.homeworld
        
        # Find a distant star
        target_star = game.stars.exclude(pk=source_star.pk).first()
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
        
        # Create transfer order for distant star
        order = FleetOrders.objects.create(
            game=game,
            fleet=fleet,
            order_type='TRANSFER',
            target_star=target_star,
            transfer_type='LOAD',
            transfer_ironium=500
        )
        
        # First turn - should move toward target
        GameTurn(game).generate_turn()
        
        fleet.refresh_from_db()
        # Fleet should have moved but not reached destination
        self.assertNotEqual(fleet.x, source_star.x)  # Has moved
        self.assertNotEqual(fleet.x, target_star.x)  # But hasn't arrived
        
        # Order should still exist
        self.assertEqual(fleet.orders.count(), 1)
        
        # Fleet cargo should be unchanged (no transfer yet)
        self.assertEqual(fleet.ironium_inventory, 0)
        
        # Generate several more turns until fleet arrives
        for _ in range(10):  # Max attempts to avoid infinite loop
            if fleet.x == target_star.x and fleet.y == target_star.y:
                break
            GameTurn(game).generate_turn()
            fleet.refresh_from_db()
        
        # Fleet should now be at target and transfer should have executed
        self.assertEqual(fleet.x, target_star.x)
        self.assertEqual(fleet.y, target_star.y)
        self.assertEqual(fleet.orders.count(), 0)  # Order completed
        self.assertEqual(fleet.ironium_inventory, 500)       # Transfer executed
    
    def test_transfer_fleet_target_waiting(self):
        """Test transfer waiting behavior when target fleet is not at expected location."""
        from ..models import FleetOrders, Fleet
        
        game = default_game()
        player = game.players.first()
        star = player.homeworld
        
        # Create two fleets at same location
        fleet1 = Fleet.objects.create(
            game=game,
            player=player,
            name="Transfer Fleet",
            x=star.x,
            y=star.y,
            ironium=1000
        )
        
        fleet2 = Fleet.objects.create(
            game=game,
            player=player,
            name="Target Fleet", 
            x=star.x,
            y=star.y
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
        
        # Move target fleet away
        fleet2.x = star.x + 10
        fleet2.y = star.y + 10
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
        targets = builder.get_transfer_targets()
        
        # Should include star_b and fleet2 (both will be at star_b)
        target_names = [t['name'] for t in targets]
        self.assertIn(star_b.name, target_names)
        self.assertIn(fleet2.name, target_names)
        
        # Should not include fleet1 itself
        self.assertNotIn(fleet1.name, target_names)
    
    def test_multiple_instant_transfers(self):
        """Test multiple transfer orders executing in same turn."""
        from ..models import FleetOrders, Fleet
        
        game = default_game()
        player = game.players.first()
        star = player.homeworld
        
        # Set up star with resources
        star.ironium_inventory = 2000
        star.boranium_inventory = 2000
        star.save()
        
        fleet = Fleet.objects.create(
            game=game,
            player=player,
            name="Multi-Transfer Fleet",
            x=star.x,
            y=star.y
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
        self.assertNotEqual(fleet.x, 20)  # Hasn't reached destination
        self.assertNotEqual(fleet.x, 1)   # But has moved
        
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
        """New fleets should have 100,000kt cargo capacity and empty inventory."""
        game = default_game()
        player = game.players.first()
        
        fleet = Fleet.objects.create(
            game=game,
            player=player,
            name="Test Fleet",
            x=5,
            y=5
        )
        
        self.assertEqual(fleet.cargo_capacity, 100000)
        self.assertEqual(fleet.ironium_inventory, 0)
        self.assertEqual(fleet.boranium_inventory, 0)
        self.assertEqual(fleet.germanium, 0) 
        self.assertEqual(fleet.colonists, 0)
    
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
            ironium=1000,
            boranium=2000,
            germanium=3000,
            colonists=4000
        )
        
        # Total cargo used: 1000 + 2000 + 3000 + 4000 = 10,000kt
        self.assertEqual(fleet.cargo_used, 10000)
        # Remaining: 100,000 - 10,000 = 90,000kt
        self.assertEqual(fleet.cargo_remaining, 90000)
    
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
            colonists=100000  # Full capacity with colonists only
        )
        
        self.assertEqual(fleet.cargo_used, 100000)
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
            ironium=25000,   # 25,000kt ironium
            boranium=25000,  # 25,000kt boranium  
            germanium=25000, # 25,000kt germanium
            colonists=25000  # 25,000k colonists = 25,000kt equivalent
        )
        
        # Total: 100,000kt exactly at capacity
        self.assertEqual(fleet.cargo_used, 100000)
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
            ironium=5000,
            boranium=3000,
            germanium=2000,
            colonists=1500
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
        self.assertEqual(cargo_info['capacity'], 100000)
        self.assertEqual(cargo_info['used'], 11500)  # 5000+3000+2000+1500
        self.assertEqual(cargo_info['remaining'], 88500)  # 100000-11500
        self.assertEqual(cargo_info['ironium'], 5000)
        self.assertEqual(cargo_info['boranium'], 3000)
        self.assertEqual(cargo_info['germanium'], 2000)
        self.assertEqual(cargo_info['colonists'], 1500)
        
        # Test inventory display data
        inventory = details['fleet_inventory']
        self.assertEqual(inventory['Ironium']['amount'], 5000)
        self.assertEqual(inventory['Ironium']['percent'], 5.0)  # 5000/100000 = 5%
        self.assertEqual(inventory['Ironium']['display'], '5,000kt')
        
        self.assertEqual(inventory['Boranium']['amount'], 3000)
        self.assertEqual(inventory['Boranium']['percent'], 3.0)  # 3000/100000 = 3%
        self.assertEqual(inventory['Boranium']['display'], '3,000kt')
        
        self.assertEqual(inventory['Germanium']['amount'], 2000)
        self.assertEqual(inventory['Germanium']['percent'], 2.0)  # 2000/100000 = 2%
        self.assertEqual(inventory['Germanium']['display'], '2,000kt')
        
        self.assertEqual(inventory['Colonists']['amount'], 1500)
        self.assertEqual(inventory['Colonists']['percent'], 1.5)  # 1500/100000 = 1.5%
        self.assertEqual(inventory['Colonists']['display'], '1,500k')


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
        
        # Create production order for BUILD_DEFENSE (bp: 20, resources: 300kt total)
        # During turn generation, 10 BP has been allocated
        order = ProductionOrder.objects.create(
            game=game,
            star=star,
            order_type='BUILD_DEFENSE',
            quantity=1,
            spent_bp=10,  # 50% of BP requirement (10/20)
            spent_ironium=100,  # Full ironium (simulates turn generation)
            spent_boranium=50,  # Full boranium  
            spent_germanium=50  # Full germanium (total 200/200 = 100% of resources)
        )
        
        detail_builder = DetailBuilder(game, x=10, y=10, selected=star.short_id.lower(), player=player)
        details = detail_builder.build_detail()
        
        production_order = details['production_orders'][0]
        
        # Should have dual progress: resources 50% + labor 25% = 75%
        self.assertEqual(production_order['has_labor'], True)
        self.assertEqual(production_order['resource_progress'], 50)  # All resources complete = 50%
        self.assertEqual(production_order['labor_progress'], 25)     # 10/20 BP = 25% of 50%
        self.assertEqual(production_order['progress_percent'], 75)   # 50% + 25%
    
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
        
        # Create TERRAFORM_GRAVITY order (bp: 100, ironium: 1000, others: 0)
        # During turn generation, some resources have been allocated
        order = ProductionOrder.objects.create(
            game=game,
            star=star,
            order_type='TERRAFORM_GRAVITY',
            quantity=1,
            spent_bp=50,     # 50% of BP requirement (50/100)
            spent_ironium=500  # 50% of ironium requirement (500/1000)
        )
        
        detail_builder = DetailBuilder(game, x=10, y=10, selected=star.short_id.lower(), player=player)
        details = detail_builder.build_detail()
        
        production_order = details['production_orders'][0]
        
        # Should have dual progress: resources 25% + labor 25% = 50%
        self.assertEqual(production_order['has_labor'], True)
        self.assertEqual(production_order['resource_progress'], 25)  # 500/1000 = 25% of 50%
        self.assertEqual(production_order['labor_progress'], 25)     # 50/100 BP = 25% of 50%
        self.assertEqual(production_order['progress_percent'], 50)   # 25% + 25%
    
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


class TestFleetTransferOrders(TestCase):
    """Test fleet transfer order functionality."""
    
    def test_transfer_order_requires_destination_arrival(self):
        """Transfer orders should only execute when fleet arrives at destination."""
        game = default_game(stars=5, fleets=1)
        player = game.players.first()
        fleet = game.fleets.first()
        target_star = game.stars.exclude(pk=player.homeworld.pk).first()
        
        # Position fleet far from target
        fleet.x = target_star.x - 20  # 20 units away
        fleet.y = target_star.y
        fleet.ironium_inventory = 1000  # Fleet has cargo to unload
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
        
        # Generate turn - fleet should move toward target but not execute transfer
        GameTurn(game).generate_turn()
        
        fleet.refresh_from_db()
        target_star.refresh_from_db()
        
        # Fleet should have moved but not reached destination
        self.assertNotEqual(fleet.x, target_star.x)  # Not at destination
        self.assertNotEqual(fleet.x, target_star.x - 20)  # But has moved
        
        # Transfer should not have executed
        self.assertEqual(fleet.ironium_inventory, 1000)  # Fleet still has cargo
        self.assertEqual(target_star.ironium_inventory, original_star_ironium)  # Star unchanged
        self.assertTrue(FleetOrders.objects.filter(id=transfer_order.id).exists())  # Order still exists
    
    def test_load_transfer_from_star(self):
        """Test loading resources from star to fleet."""
        game = default_game(stars=5, fleets=1)
        player = game.players.first()
        fleet = game.fleets.first()
        target_star = game.stars.exclude(pk=player.homeworld.pk).first()
        
        # Position fleet at target star and clear cargo
        fleet.x = target_star.x
        fleet.y = target_star.y
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
    
    def test_proportional_loading_when_over_capacity(self):
        """Test proportional resource allocation when transfer would exceed fleet capacity.""" 
        game = default_game(stars=5, fleets=1)
        player = game.players.first()
        fleet = game.fleets.first()
        target_star = game.stars.exclude(pk=player.homeworld.pk).first()
        
        # Position fleet at target with existing cargo (almost full)
        fleet.x = target_star.x
        fleet.y = target_star.y
        fleet.ironium_inventory = 0
        fleet.boranium_inventory = 0
        fleet.germanium_inventory = 0
        fleet.colonists = 900000  # Fleet almost full (900 units of 1000 capacity used)
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
        
        # Fleet can only take 100 units more (1000 - 900)
        # Proportions: ironium = 80/120 = 2/3, boranium = 40/120 = 1/3
        # Actual transfer: ironium = 100 * 2/3 = 66kt, boranium = 100 * 1/3 = 33kt
        expected_ironium = int(100 * 80/120)  # 66
        expected_boranium = int(100 * 40/120)  # 33
        
        self.assertEqual(fleet.ironium_inventory, expected_ironium)
        self.assertEqual(fleet.boranium_inventory, expected_boranium)
        self.assertEqual(fleet.colonists, 900000)  # Unchanged
        
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
        fleet = game.fleets.first()
        target_star = game.stars.exclude(pk=player.homeworld.pk).first()
        
        # Position fleet at target with limited cargo
        fleet.x = target_star.x
        fleet.y = target_star.y
        fleet.ironium_inventory = 30   # Less than order requests
        fleet.boranium_inventory = 0
        fleet.germanium_inventory = 0
        fleet.colonists = 15000  # Less than order requests (= 15 cargo units)
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
        self.assertEqual(fleet.ironium_inventory, 0)      # Unloaded all 30
        self.assertEqual(fleet.colonists, 0)    # Unloaded all 15000
        
        # Star should receive what was actually unloaded
        self.assertEqual(target_star.ironium_inventory, original_star_ironium + 30)
        self.assertEqual(target_star.colonists, original_star_colonists + 15000)
    
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


class TestFleetOrderExecution(TestCase):
    """Test fleet order execution behavior fixes."""

    def test_transfer_orders_execute_once_per_turn(self):
        """Test that repeating transfer orders only execute once per turn."""
        game = default_game(stars=5, fleets=1)
        player = game.players.first()
        fleet = game.fleets.first()
        target_star = game.stars.exclude(pk=player.homeworld.pk).first()
        
        # Position fleet at target star and clear its cargo
        fleet.x = target_star.x
        fleet.y = target_star.y
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