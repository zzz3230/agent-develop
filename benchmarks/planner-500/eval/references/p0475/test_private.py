import unittest

import lib_4d07d03c as m


class Private(unittest.TestCase):
    def test_dots_and_order(self):
        self.assertEqual(m.parse_all(['31.12.2024', '01/02/2026']), ['2024-12-31', '2026-02-01'])

