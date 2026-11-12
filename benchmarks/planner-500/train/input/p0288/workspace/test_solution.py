import unittest
import lib_61eea481 as m


class T(unittest.TestCase):
    def test_behavior(self):
        r = m.exact_root(5)
        self.assertIs(type(r), int)
        self.assertEqual(r * r, 5)


if __name__ == "__main__":
    unittest.main()
