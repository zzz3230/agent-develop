import unittest

import lib_557276ac as m


class T(unittest.TestCase):
    def test_chunks(self):
        self.assertEqual(m.chunks([1, 2, 3, 4, 5, 6], 2), [[1, 2], [3, 4], [5, 6]])


if __name__ == '__main__':
    unittest.main()
