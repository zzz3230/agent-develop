import unittest

import lib_39b80d06 as m


class Private(unittest.TestCase):
    def test_capacity(self):
        q = m.Q(1)
        q.a(1)
        with self.assertRaises(ValueError):
            q.a(2)

    def test_empty(self):
        with self.assertRaises(IndexError):
            m.Q(3).b()

