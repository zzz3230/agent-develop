import unittest
import lib_32456221 as m


class T(unittest.TestCase):
    def test_behavior(self):
        r = m.exact_root(6)
        self.assertIs(type(r), int)
        self.assertEqual(r * r, 6)


if __name__ == "__main__":
    unittest.main()
