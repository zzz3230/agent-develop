import unittest
import lib_2d0c1274 as m

class Cases(unittest.TestCase):
    def test_000(self):
        d={'a':5,'b':0}; self.assertEqual(m.apply(d,[('a','b',3)]),{'a':2,'b':3}); self.assertEqual(d,{'a':5,'b':0})

if __name__ == '__main__':
    unittest.main()
