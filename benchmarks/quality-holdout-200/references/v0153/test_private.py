import unittest

import lib_3c96b15e as m


class Private(unittest.TestCase):
    def test_huge(self):
        self.assertEqual(m.flt([4_000_000_000, 1]), 16_000_000_000_000_000_001)

    def test_empty(self):
        self.assertEqual(m.flt([]), 0)

