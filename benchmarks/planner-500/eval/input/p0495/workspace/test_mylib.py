import unittest

import lib_be26539b as m


class T(unittest.TestCase):
    def test_type(self):
        self.assertIsInstance(m.code(7), int)

    def test_value(self):
        self.assertEqual(m.code(7), '007')


if __name__ == '__main__':
    unittest.main()
