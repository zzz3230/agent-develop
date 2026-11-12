import unittest
import lib_d3dc7be3 as m

class Cases(unittest.TestCase):
    def test_000(self):
        self.assertEqual(m.expand([]),'')

    def test_001(self):
        self.assertEqual(m.expand([('',9),('x',3),('yz',1)]),'xxxyz')

    def test_002(self):
        for n in [-1,True,1.5,'2']:
         with self.assertRaises(ValueError): m.expand([('x',n)])

if __name__ == '__main__':
    unittest.main()
