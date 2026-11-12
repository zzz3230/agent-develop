import unittest
import lib_55448a51 as m

class Cases(unittest.TestCase):
    def test_000(self):
        self.assertEqual(m.distance('abc','zabc'),1)

if __name__ == '__main__':
    unittest.main()
