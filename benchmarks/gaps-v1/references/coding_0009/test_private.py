import unittest

import mylib as m


class Private(unittest.TestCase):
    def test_strings(self):
        self.assertEqual(m.unique(['b', 'a', 'b']), ['b', 'a'])

    def test_empty(self):
        self.assertEqual(m.unique([]), [])

