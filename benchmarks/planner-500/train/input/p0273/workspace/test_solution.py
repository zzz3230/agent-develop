import unittest
import lib_b4d3e6b7 as m

class Cases(unittest.TestCase):
    def test_000(self):
        self.assertEqual(m.lower_bound([1,3,3,8],4),3)

if __name__ == '__main__':
    unittest.main()
