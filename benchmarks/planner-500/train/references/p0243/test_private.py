import unittest
import lib_78e20bbf as m

class Cases(unittest.TestCase):
    def test_000(self):
        self.assertEqual(m.unique([]), [])

    def test_001(self):
        self.assertEqual(m.unique(['z','a','z','b']), ['z','a','b'])

    def test_002(self):
        v=[None,3,'a',None,3]; before=v[:]; self.assertEqual(m.unique(v),[None,3,'a']); self.assertEqual(v,before)

    def test_003(self):
        import random
        r=random.Random(11)
        for _ in range(80):
         v=[r.randrange(9) for _ in range(r.randrange(50))]
         want=[]
         for x in v:
          if x not in want: want.append(x)
         self.assertEqual(m.unique(v),want)

if __name__ == '__main__':
    unittest.main()
