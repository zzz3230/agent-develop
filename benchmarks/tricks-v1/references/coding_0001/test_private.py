import unittest

import mylib as m


class Private(unittest.TestCase):
    def test_case(self):
        self.assertEqual(m.is_valid('The the THE cat', 1), [('the', 3)])

