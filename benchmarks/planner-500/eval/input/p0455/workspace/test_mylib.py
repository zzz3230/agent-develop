import unittest

import lib_9e56047b as m


class T(unittest.TestCase):
    def test_total(self):
        self.assertEqual(m.total([1, 2, 3]), 6)

    def test_maximum(self):
        self.assertEqual(m.maximum([3, 9, 2]), 9)


if __name__ == '__main__':
    unittest.main()
