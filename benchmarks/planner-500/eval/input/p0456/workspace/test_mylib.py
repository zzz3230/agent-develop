import unittest

import lib_dfb04942 as m


class T(unittest.TestCase):
    def test_spaces(self):
        self.assertEqual(m.x1('city,amount\nOslo,5\n Oslo ,7\nRiga,1\n'), {'Oslo': 12, 'Riga': 1})


if __name__ == '__main__':
    unittest.main()
