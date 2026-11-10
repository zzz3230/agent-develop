"""Offline regression checks for the SQL adapter, without LLM usage."""
import csv
import tempfile
import unittest
from pathlib import Path
from runtime.sql_tables import scalar, describe


class SqlTablesTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        with (self.root / 'sales.csv').open('w', newline='', encoding='utf-8') as f:
            writer = csv.writer(f)
            writer.writerow(['code', 'name', 'units', 'price'])
            writer.writerows([['001', 'quoted, item', '2', '1.005'], ['002', 'two\nlines', '3', '0.10']])

    def tearDown(self):
        self.temp.cleanup()

    def test_scalar_and_original_text(self):
        self.assertEqual(scalar(self.root, 'SELECT SUM(CAST(units AS INTEGER)) FROM sales'), 5)
        self.assertEqual(scalar(self.root, "SELECT code FROM sales WHERE name='quoted, item'"), '001')
        self.assertIn('two\\nlines', describe(self.root))

    def test_decimal_rounding_before_sum(self):
        self.assertEqual(scalar(self.root, 'SELECT SUM(CENTS(DEC_MUL(units,price))) FROM sales'), 231)

    def test_errors_do_not_return_candidates(self):
        for query in ['SELECT missing FROM sales', 'SELECT code FROM sales', 'SELECT NULL',
                      'DELETE FROM sales', "ATTACH DATABASE '/tmp/unwanted.db' AS other"]:
            with self.subTest(query=query), self.assertRaises(Exception):
                scalar(self.root, query)
        self.assertEqual(scalar(self.root, 'SELECT COUNT(*) FROM sales'), 2)


if __name__ == '__main__':
    unittest.main()
