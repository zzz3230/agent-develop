import unittest
import lib_33c0f582 as m

class Cases(unittest.TestCase):
    def test_000(self):
        self.assertEqual(m.calculate('  --3 + -2*4  '),-5)

    def test_001(self):
        self.assertEqual(m.calculate('001 +\n 002'),3)

    def test_002(self):
        for s in ['True','x','f()','1/2','2**3','[2]','0x10','', '1+','1.5','1//2']:
         with self.assertRaises(ValueError): m.calculate(s)

    def test_003(self):
        import random
        r=random.Random(19)
        def tree(d):
         if d==0:
          n=r.randrange(10); return str(n),n
         a,x=tree(d-1); b,y=tree(d-1); op=r.choice(['+','-','*'])
         return '('+a+op+b+')',x+y if op=='+' else x-y if op=='-' else x*y
        for _ in range(70):
         s,want=tree(3); self.assertEqual(m.calculate(s),want)

if __name__ == '__main__':
    unittest.main()
