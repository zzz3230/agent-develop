import unittest
import lib_af4e8ec9 as m

class Cases(unittest.TestCase):
    def test_000(self):
        self.assertEqual(m.to_cents('-1.005'),-101)

    def test_001(self):
        self.assertEqual(m.to_cents('0.0049'),0)

    def test_002(self):
        from fractions import Fraction
        import random
        r=random.Random(17)
        for _ in range(100):
         n=r.randrange(-999999,999999); text=f'{n/1000:.3f}'; v=Fraction(text)*100
         sign=1 if v>=0 else -1; v=abs(v); want=sign*((2*v.numerator+v.denominator)//(2*v.denominator))
         self.assertEqual(m.to_cents(text),want)

    def test_003(self):
        self.assertEqual(m.to_cents('123456789012345.995'),12345678901234600)

if __name__ == '__main__':
    unittest.main()
