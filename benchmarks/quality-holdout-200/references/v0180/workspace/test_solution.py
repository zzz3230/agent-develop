import unittest
import lib_0252a0f6 as m

class Cases(unittest.TestCase):
    def test_000(self):
        self.assertEqual(m.unique([3,1,3,2]), [3,1,2])

if __name__ == '__main__':
    unittest.main()
