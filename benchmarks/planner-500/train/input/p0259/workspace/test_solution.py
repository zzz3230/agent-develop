import unittest
import lib_15daa5bf as m

class Cases(unittest.TestCase):
    def test_000(self):
        self.assertEqual(m.transpose([[1,2],[3]],0),[[1,3],[2,0]])

if __name__ == '__main__':
    unittest.main()
