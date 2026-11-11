import unittest
import solution as m


class T(unittest.TestCase):
    def test_behavior(self):
        self.assertEqual(m.compare('1.10.0', '1.9.0'), 1)
        self.assertEqual(m.compare('1.0.0-alpha', '1.0.0'), -1)
        self.assertEqual(m.compare('1.0.0+build.1', '1.0.0'), 0)


if __name__ == "__main__":
    unittest.main()
