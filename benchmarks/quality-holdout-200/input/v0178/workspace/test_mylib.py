import unittest

import lib_4066c40f as m


class T(unittest.TestCase):
    def test_half(self):
        self.assertEqual(m.to_upper('2.675'), '2.68')

    def test_small(self):
        self.assertEqual(m.to_upper('1.005'), '1.01')


if __name__ == '__main__':
    unittest.main()
