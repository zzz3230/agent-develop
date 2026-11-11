import unittest
import solution as m

class Cases(unittest.TestCase):
    def test_000(self):
        self.assertEqual(m.distance('','abc'),3); self.assertEqual(m.distance('ab','ba'),2)

    def test_001(self):
        self.assertEqual(m.distance('café','cafe'),1)

    def test_002(self):
        from functools import lru_cache
        import random
        r=random.Random(21)
        @lru_cache(None)
        def oracle(a,b):
         if not a: return len(b)
         if not b: return len(a)
         return min(1+oracle(a[1:],b),1+oracle(a,b[1:]),(a[0]!=b[0])+oracle(a[1:],b[1:]))
        for _ in range(80):
         a=''.join(r.choice('abc') for _ in range(r.randrange(7))); b=''.join(r.choice('abc') for _ in range(r.randrange(7)))
         self.assertEqual(m.distance(a,b),oracle(a,b))

if __name__ == '__main__':
    unittest.main()
