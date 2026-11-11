import unittest
import solution as m

class Cases(unittest.TestCase):
    def test_000(self):
        self.assertEqual(m.covered([]),0)

    def test_001(self):
        v=[(3,3),(-5,2),(0,1),(2,6)]; before=v[:]; self.assertEqual(m.covered(v),11); self.assertEqual(v,before)

    def test_002(self):
        import random
        r=random.Random(12)
        for _ in range(100):
         v=[tuple(sorted([r.randrange(-15,16),r.randrange(-15,16)])) for _ in range(r.randrange(12))]
         cells=set()
         for a,b in v: cells.update(range(a,b))
         self.assertEqual(m.covered(v),len(cells))

if __name__ == '__main__':
    unittest.main()
