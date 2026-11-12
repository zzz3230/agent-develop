import unittest
import lib_bde32256 as m


class T(unittest.TestCase):
    def test_behavior(self):
        r = m.exact_root(8)
        self.assertIs(type(r), int)
        self.assertEqual(r * r, 8)


if __name__ == "__main__":
    unittest.main()
