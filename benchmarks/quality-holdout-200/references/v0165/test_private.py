import unittest

import lib_897220e2 as m


class Private(unittest.TestCase):
    def test_huge(self):
        self.assertEqual(m.flt([4_000_000_000, 1]), 16_000_000_000_000_000_001)

    def test_empty(self):
        self.assertEqual(m.flt([]), 0)

