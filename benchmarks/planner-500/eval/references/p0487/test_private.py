import unittest

import lib_557276ac as m


class Private(unittest.TestCase):
    def test_short_tail(self):
        self.assertEqual(m.chunks([1, 2, 3, 4, 5], 2), [[1, 2], [3, 4], [5]])

    def test_empty(self):
        self.assertEqual(m.chunks([], 3), [])

