import unittest

import lib_22b996ea as m


class T(unittest.TestCase):
    def test_half_odd(self):
        self.assertEqual(m.half(3), 1.5)

    def test_half_even_int(self):
        self.assertEqual(m.half(4), 2)

    def test_half_even_float(self):
        self.assertEqual(m.half(4), 2.0)


if __name__ == '__main__':
    unittest.main()
