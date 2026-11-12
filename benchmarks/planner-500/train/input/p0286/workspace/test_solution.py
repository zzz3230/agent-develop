import unittest
import lib_de87d725 as m


class T(unittest.TestCase):
    def test_behavior(self):
        r = m.exact_root(7)
        self.assertIs(type(r), int)
        self.assertEqual(r * r, 7)


if __name__ == "__main__":
    unittest.main()
