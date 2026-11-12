import unittest

import mylib as m


class T(unittest.TestCase):
    def test_day_first(self):
        self.assertEqual(m.parse_all(['03/04/2025']), ['2025-04-03'])


if __name__ == '__main__':
    unittest.main()
