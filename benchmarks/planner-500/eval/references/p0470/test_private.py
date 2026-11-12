import unittest

import lib_a4cd9c69 as m


class Private(unittest.TestCase):
    def test_maximum_negative(self):
        self.assertEqual(m.maximum([-5, -2, -9]), -2)

    def test_total_empty(self):
        self.assertEqual(m.total([]), 0)

