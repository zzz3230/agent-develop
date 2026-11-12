import unittest
import lib_7c5b134c as m

class Cases(unittest.TestCase):
    def test_000(self):
        self.assertEqual(m.lower_bound([],7),0)

    def test_001(self):
        import random,bisect
        r=random.Random(14)
        for _ in range(120):
         v=sorted(r.randrange(-20,21) for _ in range(r.randrange(60))); t=r.randrange(-25,26); before=v[:]
         self.assertEqual(m.lower_bound(v,t),bisect.bisect_left(v,t)); self.assertEqual(v,before)

if __name__ == '__main__':
    unittest.main()
