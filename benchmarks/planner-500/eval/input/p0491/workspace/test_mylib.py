import unittest

import lib_c9652e7f as m


class T(unittest.TestCase):
    def test_type(self):
        self.assertIsInstance(m.code(7), int)

    def test_value(self):
        self.assertEqual(m.code(7), '007')


if __name__ == '__main__':
    unittest.main()
