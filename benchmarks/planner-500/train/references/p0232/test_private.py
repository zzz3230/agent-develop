import unittest
import lib_add39042 as m

class Cases(unittest.TestCase):
    def test_000(self):
        self.assertEqual(m.distances([],'x'),{'x':0})

    def test_001(self):
        self.assertEqual(m.distances([('a','b',0),('b','a',0),('a','b',9),('x','y',1)],'a'),{'a':0,'b':0})

    def test_002(self):
        import random
        r=random.Random(18)
        for _ in range(60):
         es=[(a,b,r.randrange(8)) for a in 'abcde' for b in 'abcde' if r.random()<.25]; r.shuffle(es)
         ds={'a':0}
         for k in range(5):
          for a,b,w in es:
           if a in ds: ds[b]=min(ds.get(b,float('inf')),ds[a]+w)
         self.assertEqual(m.distances(es,'a'),ds)

if __name__ == '__main__':
    unittest.main()
