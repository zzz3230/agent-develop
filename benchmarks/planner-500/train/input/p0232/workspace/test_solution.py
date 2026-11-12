import unittest
import lib_add39042 as m

class Cases(unittest.TestCase):
    def test_000(self):
        self.assertEqual(m.distances([('b','c',1),('a','b',2)],'a'),{'a':0,'b':2,'c':3})

if __name__ == '__main__':
    unittest.main()
