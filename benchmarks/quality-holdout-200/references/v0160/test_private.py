import unittest
import lib_1eeea9b9 as m

class Cases(unittest.TestCase):
    def test_000(self):
        self.assertEqual(m.compare('1','01.0.00'),0); self.assertEqual(m.compare('0.1','1'),-1)

    def test_001(self):
        import random
        r=random.Random(22)
        for _ in range(100):
         x=[r.randrange(20) for _ in range(r.randrange(1,6))]; y=[r.randrange(20) for _ in range(r.randrange(1,6))]
         xp=x+[0]*(5-len(x)); yp=y+[0]*(5-len(y)); want=(xp>yp)-(xp<yp)
         self.assertEqual(m.compare('.'.join(map(str,x)),'.'.join(map(str,y))),want)

if __name__ == '__main__':
    unittest.main()
