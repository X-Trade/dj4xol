from ..turn import (
    GameTurn, habitability_proportion, calculate_growth_factor, capacity_modifier,
    effective_capacity, BILLION, calculate_employment_percent, calculate_economy_percent,
    calculate_available_buildpoints, calculate_productivity_percent, calculate_economy_factor,
    COLONISTS_PER_JOB, BUILDPOINTS_PER_FACTORY
)
from ..models import ProductionOrder
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

    def test_mining_discovery_increases_resources(self):
        """Mining discovery should increase a resource."""
        game = default_game(stars=5)
        game.random_events = True
        game.save()
        player = game.players.first()
        homeworld = player.homeworld
        homeworld.ironium = 10
        homeworld.boranium = 10
        homeworld.germanium = 10
        homeworld.save()
        total_before = homeworld.ironium + homeworld.boranium + homeworld.germanium
        turn = GameTurn(game)
        turn._apply_mining_discovery(homeworld)
        homeworld.refresh_from_db()
        total_after = homeworld.ironium + homeworld.boranium + homeworld.germanium
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
        """Buildpoints equal factories * BUILDPOINTS_PER_FACTORY."""
        game = default_game()
        star = game.stars.first()
        star.factories = 7
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
        star.save()

        ProductionOrder.objects.create(game=game, star=star, order_type='BUILD_FACTORY')
        GameTurn(game).generate_turn()

        star.refresh_from_db()
        self.assertEqual(star.factories, 1)