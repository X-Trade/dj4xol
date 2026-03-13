from django.test import TestCase
from ..models import ServerRaceType, ServerRace, Player, Star, Game, Account
from ..habitability_rules import HabitabilityRules, RaceCreationRules
from django.contrib.auth.models import User


class TestHabitabilityMixin(TestCase):
    def setUp(self):
        self.race_type = ServerRaceType.objects.create(
            code='TEST', name='Test', description='Test'
        )
        self.race = ServerRace.objects.create(
            name='Testling', plural_name='Testlings',
            race_type=self.race_type,
            gravity_center=1.0, gravity_width=1.0,
            temperature_center=1.0, temperature_width=1.0,
            radiation_center=1.0, radiation_width=1.0,
        )

    def test_hab_min_max(self):
        """Test hab_min and hab_max calculations."""
        self.race.gravity_center = 1.2
        self.race.gravity_width = 0.6
        self.assertAlmostEqual(self.race.hab_min('gravity'), 0.9)
        self.assertAlmostEqual(self.race.hab_max('gravity'), 1.5)

    def test_habitability_width_cost(self):
        """Test width cost calculation."""
        self.race.gravity_width = 1.0
        self.race.temperature_width = 0.8
        self.race.radiation_width = 1.2
        self.assertAlmostEqual(self.race.habitability_width_cost(), 3.0)

    def test_habitability_center_cost(self):
        """Test center cost calculation - average centers cost more."""
        # All at center (1.0) = maximum cost
        self.race.gravity_center = 1.0
        self.race.temperature_center = 1.0
        self.race.radiation_center = 1.0
        self.assertAlmostEqual(self.race.habitability_center_cost(), 3.0)

        # All at extremes (0.0 or 2.0) = minimum cost
        self.race.gravity_center = 0.0
        self.race.temperature_center = 2.0
        self.race.radiation_center = 0.0
        self.assertAlmostEqual(self.race.habitability_center_cost(), 0.0)

        # Mixed
        self.race.gravity_center = 0.5  # cost = 1.0 - 0.5 = 0.5
        self.race.temperature_center = 1.0  # cost = 1.0
        self.race.radiation_center = 1.5  # cost = 1.0 - 0.5 = 0.5
        self.assertAlmostEqual(self.race.habitability_center_cost(), 2.0)

    def test_habitability_total_cost_default(self):
        """Default config should cost exactly 6.0."""
        self.assertAlmostEqual(self.race.habitability_total_cost(), 6.0)

    def test_validate_habitability_valid(self):
        """Valid configuration should return no errors."""
        errors = self.race.validate_habitability()
        self.assertEqual(errors, [])

    def test_validate_habitability_exceeds_budget(self):
        """Exceeding budget should return error."""
        self.race.gravity_width = 2.0
        errors = self.race.validate_habitability()
        self.assertTrue(any('exceeds budget' in e for e in errors))

    def test_rules_per_env_cost(self):
        rules = HabitabilityRules(
            centers={'gravity': 1.0, 'temperature': 0.5, 'radiation': 1.5},
            widths={'gravity': 1.0, 'temperature': 0.8, 'radiation': 1.2},
        )
        self.assertAlmostEqual(rules.per_env_cost('gravity'), 2.0)
        self.assertAlmostEqual(rules.per_env_cost('temperature'), 1.3)
        self.assertAlmostEqual(rules.per_env_cost('radiation'), 1.7)

    def test_race_creation_budget_defaults(self):
        rules = RaceCreationRules(
            centers={'gravity': 1.0, 'temperature': 1.0, 'radiation': 1.0},
            widths={'gravity': 1.0, 'temperature': 1.0, 'radiation': 1.0},
            starting_colonists=20,
            starting_labs=1,
        )
        self.assertAlmostEqual(rules.total_cost(), rules.budget)

    def test_race_creation_race_type_points_balance_adjusts_total(self):
        rules = RaceCreationRules(
            centers={'gravity': 1.0, 'temperature': 1.0, 'radiation': 1.0},
            widths={'gravity': 1.0, 'temperature': 1.0, 'radiation': 1.0},
            starting_colonists=20,
            starting_labs=1,
            race_type_points_balance=-8.5,
        )
        self.assertAlmostEqual(rules.race_type_balance_cost(), -8.5)
        self.assertAlmostEqual(rules.total_cost(), rules.budget - 8.5)

    def test_race_creation_width_cost_curve_keeps_1_and_raises_2(self):
        rules_narrow = RaceCreationRules(
            centers={'gravity': 0.0, 'temperature': 1.0, 'radiation': 1.0},
            widths={'gravity': 1.0, 'temperature': 1.0, 'radiation': 1.0},
        )
        rules_wide = RaceCreationRules(
            centers={'gravity': 0.0, 'temperature': 1.0, 'radiation': 1.0},
            widths={'gravity': 2.0, 'temperature': 1.0, 'radiation': 1.0},
        )
        # Center at 0.0 removes center-cost component for gravity, isolating width cost.
        self.assertAlmostEqual(rules_narrow.per_env_cost('gravity'), 8.0)
        self.assertAlmostEqual(rules_wide.per_env_cost('gravity'), 20.0)

    def test_race_creation_tiny_extreme_range_costs_about_one_point(self):
        rules = RaceCreationRules(
            centers={'gravity': 0.05, 'temperature': 1.0, 'radiation': 1.0},
            widths={'gravity': 0.1, 'temperature': 1.0, 'radiation': 1.0},
        )
        self.assertAlmostEqual(rules.per_env_cost('gravity'), 1.0)

    def test_validate_habitability_range_below_zero(self):
        """Range extending below 0 should return error."""
        self.race.gravity_center = 0.2
        self.race.gravity_width = 1.0  # min would be -0.3
        errors = self.race.validate_habitability()
        self.assertTrue(any('below 0' in e for e in errors))

    def test_validate_habitability_range_above_two(self):
        """Range extending above 2 should return error."""
        self.race.temperature_center = 1.8
        self.race.temperature_width = 1.0  # max would be 2.3
        errors = self.race.validate_habitability()
        self.assertTrue(any('above 2' in e for e in errors))

    def test_is_habitable(self):
        """Test is_habitable check against star."""
        user = User.objects.create_user('test', 'test@test.com', 'pass')
        account = Account.objects.create(django_user=user)
        game = Game.objects.create(name='Test', map_size_x=100, map_size_y=100, owner=account)

        # Create a star with specific environmental values
        star = Star.objects.create(
            game=game, name='Test Star', x=50, y=50,
            gravity=1.0, temperature=1.0, radiation=1.0
        )

        # Default race with center 1.0 and width 1.0 for all = range 0.5-1.5
        self.assertTrue(self.race.is_habitable(star))

        # Star outside gravity range
        star.gravity = 0.2
        self.assertFalse(self.race.is_habitable(star))

    def test_copy_habitability_from(self):
        """Test copying habitability fields."""
        source = ServerRace.objects.create(
            name='Source', plural_name='Sources',
            race_type=self.race_type,
            gravity_center=0.5, gravity_width=0.8,
            temperature_center=1.5, temperature_width=0.6,
            radiation_center=0.3, radiation_width=1.2,
        )
        self.race.copy_habitability_from(source)
        self.assertAlmostEqual(self.race.gravity_center, 0.5)
        self.assertAlmostEqual(self.race.gravity_width, 0.8)
        self.assertAlmostEqual(self.race.temperature_center, 1.5)
        self.assertAlmostEqual(self.race.temperature_width, 0.6)
        self.assertAlmostEqual(self.race.radiation_center, 0.3)
        self.assertAlmostEqual(self.race.radiation_width, 1.2)
