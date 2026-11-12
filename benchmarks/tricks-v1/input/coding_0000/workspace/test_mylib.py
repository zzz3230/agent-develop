import unittest

import mylib as m


class T(unittest.TestCase):
    def test_week(self):
        self.assertEqual(m.make_list('2026-11-09', '2026-11-16'), 5)


if __name__ == '__main__':
    unittest.main()
