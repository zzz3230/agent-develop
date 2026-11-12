import unittest

import lib_456478d4 as m


class T(unittest.TestCase):
    def test_ties(self):
        self.assertEqual(m.is_valid('b a b a c', 2), [('a', 2), ('b', 2)])


if __name__ == '__main__':
    unittest.main()
