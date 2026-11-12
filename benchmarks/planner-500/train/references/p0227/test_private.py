import unittest
import lib_a1ddafae as m

class Cases(unittest.TestCase):
    def test_000(self):
        self.assertEqual(m.order({}),[])

    def test_001(self):
        self.assertEqual(m.order({'b':['a','a'],'d':['c']}),['a','b','c','d'])

    def test_002(self):
        for d in [{'a':['a']},{'a':['b'],'b':['a']},{'z':[],'x':['y'],'y':['x']}]:
         with self.assertRaises(ValueError): m.order(d)

    def test_003(self):
        import random,copy,itertools
        r=random.Random(15)
        for _ in range(25):
         names=list('abcde'); r.shuffle(names)
         d={n:[p for p in names[:i] if r.random()<0.4] for i,n in enumerate(names)}
         original=copy.deepcopy(d)
         valid=[p for p in itertools.permutations(sorted(names)) if all(p.index(u)<p.index(v) for v,us in d.items() for u in us)]
         self.assertEqual(m.order(d),list(min(valid))); self.assertEqual(d,original)

if __name__ == '__main__':
    unittest.main()
