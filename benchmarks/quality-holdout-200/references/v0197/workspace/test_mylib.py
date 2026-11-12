import unittest

import lib_b26aaaaa as m


class T(unittest.TestCase):
    def test_add_tax(self):
        self.assertEqual(m.add_tax(100), 120)

    def test_add_tax_again(self):
        self.assertEqual(m.add_tax(100), 121)


if __name__ == '__main__':
    unittest.main()
