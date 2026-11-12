import unittest

import mylib as m


class Private(unittest.TestCase):
    def test_negative(self):
        self.assertEqual(m.half(-3), -1.5)

