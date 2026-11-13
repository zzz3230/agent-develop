import unittest

import lib_05c0a8cc as m


class T(unittest.TestCase):
    def test_week(self):
        self.assertEqual(m.make_list('2026-11-09', '2026-11-16'), 5)


if __name__ == '__main__':
    unittest.main()
