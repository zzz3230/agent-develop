import unittest

import lib_84666595 as m


class Private(unittest.TestCase):
    def test_negative(self):
        self.assertEqual(m.half(-3), -1.5)

