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
        homeworld.ironium_surface = 2000  # Provide resources
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
        homeworld.ironium_surface = 2000  # For gravity terraform
        homeworld.boranium_surface = 2000  # For temperature terraform
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
        homeworld.ironium_surface = 0
        homeworld.boranium_surface = 0
        homeworld.germanium_surface = 0
        homeworld.save()
        total_before = homeworld.ironium_surface + homeworld.boranium_surface + homeworld.germanium_surface
        turn = GameTurn(game)
        turn._apply_mining_discovery(homeworld)
        homeworld.refresh_from_db()
        total_after = homeworld.ironium_surface + homeworld.boranium_surface + homeworld.germanium_surface
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
        star.ironium_surface = 100  # Provide resources for building
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
        star.ironium_surface = 100  # Provide resources for building
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
        star.germanium = 20  # 20% yield
        star.ironium_surface = 0
        star.boranium_surface = 0
        star.germanium_surface = 0
        star.save()

        GameTurn(game).generate_turn()

        star.refresh_from_db()
        # 5 mines * 10kt = 50kt total, distributed by yield
        # Total yield = 100%, so: 50*50/100=25, 50*30/100=15, 50*20/100=10
        self.assertEqual(star.ironium_surface, 25)
        self.assertEqual(star.boranium_surface, 15)
        self.assertEqual(star.germanium_surface, 10)

    def test_mining_no_mines(self):
        """No mines should not extract any minerals."""
        game = default_game()
        player = game.players.first()
        star = player.homeworld
        star.mines = 0
        star.ironium_surface = 0
        star.boranium_surface = 0
        star.germanium_surface = 0
        star.save()

        GameTurn(game).generate_turn()

        star.refresh_from_db()
        self.assertEqual(star.ironium_surface, 0)
        self.assertEqual(star.boranium_surface, 0)
        self.assertEqual(star.germanium_surface, 0)

    def test_mining_accumulates(self):
        """Mining should accumulate surface minerals over turns."""
        game = default_game()
        player = game.players.first()
        star = player.homeworld
        star.mines = 2
        star.ironium = 100  # 100% yield (only ironium)
        star.boranium = 0
        star.germanium = 0
        star.ironium_surface = 100  # Start with some
        star.save()

        GameTurn(game).generate_turn()

        star.refresh_from_db()
        # 2 mines * 10kt = 20kt, all to ironium (100% of total yield)
        self.assertEqual(star.ironium_surface, 120)

    def test_mining_low_yield_has_chance(self):
        """Low yield resources should still have a chance to produce."""
        game = default_game()
        player = game.players.first()
        star = player.homeworld
        star.mines = 1
        star.ironium = 1  # 1% yield
        star.boranium = 99  # 99% yield
        star.germanium = 0
        star.ironium_surface = 0
        star.boranium_surface = 0
        star.save()

        # Run many turns - ironium should eventually produce something
        produced_ironium = False
        for _ in range(100):
            GameTurn(game).generate_turn()
            star.refresh_from_db()
            if star.ironium_surface > 0:
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
        star.germanium = 0
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
        other_star.germanium = 0
        other_star.save()

        # Run many turns to trigger depletion
        # With 5000 mines * 10kt = 50000kt, depletion_chance = 50000/(31*10000) = 16% per turn
        for _ in range(50):
            GameTurn(game).generate_turn()

        other_star.refresh_from_db()
        # Should have depleted below 31 (with high probability)
        self.assertLess(other_star.ironium, 31)


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
        self.assertEqual(fleet.ironium, 0)
        self.assertEqual(fleet.boranium, 0)
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