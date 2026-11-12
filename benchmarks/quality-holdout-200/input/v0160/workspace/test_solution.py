import unittest
import lib_1eeea9b9 as m

class Cases(unittest.TestCase):
    def test_000(self):
        self.assertEqual(m.compare('1.10','1.9'),1)

if __name__ == '__main__':
    unittest.main()
