import unittest

import mylib as m


class Private(unittest.TestCase):
    def test_upper_bound(self):
        self.assertEqual(m.parse_port('65535'), 65535)
        with self.assertRaises(ValueError):
            m.parse_port('65536')

