import unittest
import lib_ae5d7dac as m

class Cases(unittest.TestCase):
    def test_000(self):
        self.assertEqual(m.expand([('ab',2),('x',0)]),'abab')

if __name__ == '__main__':
    unittest.main()
