import unittest
from decimal import Decimal
from pricing import invoice_total


class InvoiceTotalTests(unittest.TestCase):
    def test_negative_quantity_rejected(self):
        with self.assertRaises(ValueError):
            invoice_total("10.00", -1)

    def test_positive_quantity_unchanged(self):
        self.assertEqual(invoice_total("3.25", 2), Decimal("6.50"))

    def test_zero_quantity_unchanged(self):
        self.assertEqual(invoice_total("3.25", 0), Decimal("0.00"))
