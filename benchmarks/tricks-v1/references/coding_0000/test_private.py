import unittest

import mylib as m


class Private(unittest.TestCase):
    def test_year_boundary(self):
        self.assertEqual(m.make_list('2025-12-29', '2026-01-05'), 5)

    def test_weekend_only(self):
        self.assertEqual(m.make_list('2026-11-14', '2026-11-16'), 0)

    def test_reversed(self):
        self.assertEqual(m.make_list('2026-11-16', '2026-11-09'), 0)

