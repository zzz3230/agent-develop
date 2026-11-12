import unittest
import lib_41d99e7d as m


class T(unittest.TestCase):
    def test_behavior(self):
        r = m.exact_root(2)
        self.assertIs(type(r), int)
        self.assertEqual(r * r, 2)


if __name__ == "__main__":
    unittest.main()
