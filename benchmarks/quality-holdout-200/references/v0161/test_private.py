import unittest
import lib_7edf67f8 as m

class Cases(unittest.TestCase):
    def test_000(self):
        self.assertIsNone(m.lookup({'a':None},['a'],99))

    def test_001(self):
        self.assertEqual(m.lookup({'a':[1]},['a',-1],99),99)

    def test_002(self):
        for path in [['a',True],['a',2],['a','0'],['x'],['a',0,'b']]:
         self.assertEqual(m.lookup({'a':[1]},path,'missing'),'missing')

    def test_003(self):
        d={'a':1}; self.assertIs(m.lookup(d,[]),d)

if __name__ == '__main__':
    unittest.main()
