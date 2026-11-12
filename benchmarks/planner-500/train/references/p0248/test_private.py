import unittest
import lib_ad801f51 as m

class Cases(unittest.TestCase):
    def test_000(self):
        self.assertEqual(m.split_fields(''),['']); self.assertEqual(m.split_fields('||'),['','',''])

    def test_001(self):
        self.assertEqual(m.split_fields('abc'+chr(92)),['abc'+chr(92)])

    def test_002(self):
        self.assertEqual(m.split_fields(chr(92)+chr(92)+'|z'),[chr(92),'z'])

    def test_003(self):
        import random
        r=random.Random(20)
        for _ in range(70):
         fields=[''.join(r.choice('ab|'+chr(92)) for _ in range(r.randrange(8))) for _ in range(4)]
         encoded='|'.join(''.join(chr(92)+c if c in '|'+chr(92) else c for c in s) for s in fields)
         self.assertEqual(m.split_fields(encoded),fields)

if __name__ == '__main__':
    unittest.main()
