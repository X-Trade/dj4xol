from django.test import TestCase
from ..templatetags.numbers import human_number, exact_number


class TestHumanNumber(TestCase):
    def test_zero(self):
        self.assertEqual(human_number(0), "0")

    def test_small_number(self):
        self.assertEqual(human_number(500), "500")

    def test_thousands_exact(self):
        self.assertEqual(human_number(100000), "100k")

    def test_thousands_round(self):
        self.assertEqual(human_number(127000), "127k")

    def test_thousands_approx(self):
        self.assertEqual(human_number(127900), "~128k")

    def test_millions(self):
        self.assertEqual(human_number(5000000), "5m")

    def test_millions_approx(self):
        self.assertEqual(human_number(5500000), "~6m")

    def test_billions(self):
        result = human_number(1234567890)
        self.assertIn("1", result)
        self.assertIn("bn", result)
        self.assertIn("~", result)

    def test_billions_round_up(self):
        result = human_number(2501000000)
        self.assertIn("3", result)
        self.assertIn("bn", result)

    def test_negative(self):
        self.assertEqual(human_number(-5000), "-5k")

    def test_show_sign_positive(self):
        self.assertEqual(human_number(5000, show_sign=True), "+5k")

    def test_show_sign_negative(self):
        self.assertEqual(human_number(-5000, show_sign=True), "-5k")

    def test_none(self):
        self.assertEqual(human_number(None), "")


class TestExactNumber(TestCase):
    def test_with_commas(self):
        self.assertEqual(exact_number(1234567), "1,234,567")

    def test_small(self):
        self.assertEqual(exact_number(500), "500")

    def test_none(self):
        self.assertEqual(exact_number(None), "")
