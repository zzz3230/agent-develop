import unittest

import lib_0d2e706d as m


class T(unittest.TestCase):
    def test_small(self):
        self.assertEqual(m.flt([1, 2, 3]), 14)

    def test_medium(self):
        self.assertEqual(m.flt([200, 3]), 40009)


if __name__ == '__main__':
    unittest.main()
