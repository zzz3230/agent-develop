import unittest
import lib_c4d6f4ea as m


class T(unittest.TestCase):
    def test_behavior(self):
        r = m.exact_root(3)
        self.assertIs(type(r), int)
        self.assertEqual(r * r, 3)


if __name__ == "__main__":
    unittest.main()
