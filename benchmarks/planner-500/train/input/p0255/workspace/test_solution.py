import unittest
import lib_ca1bf34c as m


class T(unittest.TestCase):
    def test_behavior(self):
        self.assertEqual(m.to_roman(1994), 'MCMXCIV')
        self.assertEqual(m.from_roman('XLII'), 42)
        with self.assertRaises(ValueError):
            m.from_roman('IIII')


if __name__ == "__main__":
    unittest.main()
