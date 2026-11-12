import unittest

import lib_548a0d67 as m


class T(unittest.TestCase):
    def test_clamp(self):
        self.assertEqual(m.clamp(15, 0, 10), 10)

    def test_median_even(self):
        self.assertEqual(m.median([4, 1, 3, 2]), 2.5)

    def test_palindrome(self):
        self.assertTrue(m.is_palindrome('Never odd or even'))

    def test_safe_div_zero(self):
        self.assertIsNone(m.safe_div(1, 0))

    def test_flatten(self):
        self.assertEqual(m.flatten([[1], [2, 3]]), [1, 2, 3])


if __name__ == '__main__':
    unittest.main()
