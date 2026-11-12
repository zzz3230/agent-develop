import unittest
import lib_b52fb11b as m

class Cases(unittest.TestCase):
    def test_000(self):
        self.assertEqual(m.transpose([]),[]); self.assertEqual(m.transpose([[],[]]),[])

    def test_001(self):
        r=[[],[None,4],[5]]; self.assertEqual(m.transpose(r,'x'),[['x',None,5],['x',4,'x']]); self.assertEqual(r,[[],[None,4],[5]])

if __name__ == '__main__':
    unittest.main()
