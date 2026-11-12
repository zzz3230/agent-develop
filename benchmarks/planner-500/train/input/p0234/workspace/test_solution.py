import unittest
import lib_2cca3f78 as m

class Cases(unittest.TestCase):
    def test_000(self):
        self.assertEqual(m.read_rows('a,b\n1,"x,y"\n'),[['a','b'],['1','x,y']])

if __name__ == '__main__':
    unittest.main()
