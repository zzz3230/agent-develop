import unittest

import mylib as m


class Private(unittest.TestCase):
    def test_median_odd(self):
        self.assertEqual(m.median([5, 1, 3]), 3)

    def test_safe_div(self):
        self.assertEqual(m.safe_div(6, 3), 2)

