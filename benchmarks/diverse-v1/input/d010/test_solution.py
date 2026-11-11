import unittest
import solution as m

class Cases(unittest.TestCase):
    def test_000(self):
        self.assertEqual(m.covered([(1,4),(3,6)]),5)

if __name__ == '__main__':
    unittest.main()
