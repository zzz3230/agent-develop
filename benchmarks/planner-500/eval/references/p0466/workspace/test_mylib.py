import unittest

import lib_0d124f47 as m


class T(unittest.TestCase):
    def test_unique(self):
        self.assertEqual(m.unique([3, 1, 3, 2, 1]), [3, 1, 2])


if __name__ == '__main__':
    unittest.main()
