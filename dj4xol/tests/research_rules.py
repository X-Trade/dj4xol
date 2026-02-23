from django.test import TestCase

from ..research_rules import (
    allocate_rp,
    normalise_percentages,
    resolve_level_progress,
    rp_cost_for_level,
)


class ResearchRulesTest(TestCase):
    def test_rp_cost_sequence(self):
        self.assertEqual(rp_cost_for_level(1), 50)
        self.assertEqual(rp_cost_for_level(2), 80)
        self.assertEqual(rp_cost_for_level(3), 130)
        self.assertEqual(rp_cost_for_level(4), 210)
        self.assertEqual(rp_cost_for_level(5), 340)

    def test_normalise_percentages_handles_invalid_totals(self):
        result = normalise_percentages([100, 100, 0, -5])
        self.assertAlmostEqual(sum(result), 100.0, places=5)
        self.assertGreater(result[0], 0)
        self.assertGreater(result[1], 0)
        self.assertEqual(result[3], 0.0)

    def test_normalise_percentages_all_zero_equal_split(self):
        result = normalise_percentages([0, 0, 0, 0])
        self.assertAlmostEqual(sum(result), 100.0, places=5)
        self.assertAlmostEqual(result[0], 25.0, places=5)
        self.assertAlmostEqual(result[3], 25.0, places=5)

    def test_allocate_rp(self):
        alloc = allocate_rp(200.0, [50, 25, 25])
        self.assertAlmostEqual(alloc[0], 100.0, places=5)
        self.assertAlmostEqual(alloc[1], 50.0, places=5)
        self.assertAlmostEqual(alloc[2], 50.0, places=5)

    def test_resolve_level_progress(self):
        level, rem = resolve_level_progress(0.0, 260.0, 10)
        self.assertEqual(level, 3.0)  # 50 + 80 + 130 = 260
        self.assertEqual(rem, 0.0)
