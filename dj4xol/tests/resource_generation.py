import random

from django.test import TestCase

from ..models import (
    random_surface_boranium_init,
    random_surface_germanium_init,
    random_surface_ironium_init,
)


class ResourceGenerationTest(TestCase):
    def test_surface_deposit_abundance_order_and_totals(self):
        state = random.getstate()
        random.seed(12345)
        try:
            samples = 20000
            iron = [random_surface_ironium_init() for _ in range(samples)]
            bor = [random_surface_boranium_init() for _ in range(samples)]
            germ = [random_surface_germanium_init() for _ in range(samples)]

            avg_iron = sum(iron) / float(samples)
            avg_bor = sum(bor) / float(samples)
            avg_germ = sum(germ) / float(samples)
            self.assertGreater(avg_iron, avg_bor)
            self.assertGreater(avg_bor, avg_germ)

            totals_below_2000 = 0
            for idx in range(samples):
                if (iron[idx] + bor[idx] + germ[idx]) < 2000:
                    totals_below_2000 += 1
            self.assertGreaterEqual(totals_below_2000 / float(samples), 0.60)
        finally:
            random.setstate(state)

    def test_surface_deposit_jackpot_rate_is_about_one_in_two_hundred(self):
        state = random.getstate()
        random.seed(424242)
        try:
            samples = 50000
            iron_jackpots = sum(1 for _ in range(samples) if random_surface_ironium_init() > 15000)
            bor_jackpots = sum(1 for _ in range(samples) if random_surface_boranium_init() > 10000)
            germ_jackpots = sum(1 for _ in range(samples) if random_surface_germanium_init() > 7000)

            for jackpots in (iron_jackpots, bor_jackpots, germ_jackpots):
                rate = jackpots / float(samples)
                self.assertGreaterEqual(rate, 0.003)
                self.assertLessEqual(rate, 0.007)
        finally:
            random.setstate(state)
