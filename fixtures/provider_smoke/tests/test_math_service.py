import unittest
from src.math_service import add, format_currency


class MathServiceTests(unittest.TestCase):
    def test_add(self):
        self.assertEqual(add(7, 5), 12)

    def test_currency_has_two_decimals(self):
        self.assertEqual(format_currency(12), "$12.00")
        self.assertEqual(format_currency(3.5), "$3.50")


if __name__ == "__main__":
    unittest.main()
