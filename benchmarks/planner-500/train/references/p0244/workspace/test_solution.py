import unittest
import lib_8487e08f as m

class Cases(unittest.TestCase):
    def test_000(self):
        s=m.Store(); s.put('a',7,0,3); self.assertIsNone(s.get('a',3))

if __name__ == '__main__':
    unittest.main()
