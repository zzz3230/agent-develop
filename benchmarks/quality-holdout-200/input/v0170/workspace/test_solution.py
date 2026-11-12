import unittest
import lib_7f97fe78 as m

class Cases(unittest.TestCase):
    def test_000(self):
        self.assertEqual(m.distance('abc','zabc'),1)

if __name__ == '__main__':
    unittest.main()
