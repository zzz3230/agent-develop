import unittest
import lib_0e0706c4 as m


class T(unittest.TestCase):
    def test_behavior(self):
        self.assertEqual(m.parse_duration('1h30m'), 5400)
        self.assertEqual(m.parse_duration('2d'), 172800)
        with self.assertRaises(ValueError):
            m.parse_duration('')


if __name__ == "__main__":
    unittest.main()
