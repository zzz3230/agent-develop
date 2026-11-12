import unittest
import lib_a352cde5 as m

class Cases(unittest.TestCase):
    def test_000(self):
        self.assertEqual(m.to_cents('1.005'),101)

if __name__ == '__main__':
    unittest.main()
