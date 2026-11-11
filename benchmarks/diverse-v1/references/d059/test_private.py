import unittest
import solution as m

class Cases(unittest.TestCase):
    def test_000(self):
        d={'a':5,'b':0}
        with self.assertRaises(ValueError): m.apply(d,[('a','b',3),('b','a',4)])
        self.assertEqual(d,{'a':5,'b':0})

    def test_001(self):
        for t in [('a','b',True),('a','b',-1),('a','x',0),('x','b',0),('a','a',6),('a','b',1.5)]:
         with self.assertRaises(ValueError): m.apply({'a':5,'b':0},[t])

    def test_002(self):
        d={'a':5,'b':0}; result=m.apply(d,[('a','a',5),('a','b',0)]); self.assertEqual(result,d); self.assertIsNot(result,d)

if __name__ == '__main__':
    unittest.main()
