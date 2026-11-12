import unittest

import lib_456478d4 as m


class Private(unittest.TestCase):
    def test_case(self):
        self.assertEqual(m.is_valid('The the THE cat', 1), [('the', 3)])

