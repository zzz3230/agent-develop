import unittest

import lib_a02a74df as m


class T(unittest.TestCase):
    def test_port(self):
        self.assertEqual(m.parse_port('8080'), 8080)

    def test_zero_rejected(self):
        with self.assertRaises(ValueError):
            m.parse_port('0')


if __name__ == '__main__':
    unittest.main()
