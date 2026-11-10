import random
import unittest
import intervals as m

class Hidden(unittest.TestCase):
    def test_generated(self):
        rng=random.Random(811)
        for _ in range(150):
            xs=[tuple(sorted((rng.randrange(-20,21),rng.randrange(-20,21)))) for _ in range(rng.randrange(14))]
            expected=[]
            for a,b in sorted(xs):
                if a==b: continue
                if expected and a<expected[-1][1]: expected[-1]=(expected[-1][0],max(expected[-1][1],b))
                else: expected.append((a,b))
            original=list(xs)
            self.assertEqual(m.merge(xs),expected)
            self.assertEqual(xs,original)
            self.assertEqual(m.covered(xs),sum(b-a for a,b in expected))

    def test_invalid_mixed(self):
        with self.assertRaises(ValueError): m.merge([(1,3),(5,4),(8,9)])
