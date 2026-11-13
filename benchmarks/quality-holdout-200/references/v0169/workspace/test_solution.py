import unittest
import lib_af4e8ec9 as m

class Cases(unittest.TestCase):
    def test_000(self):
        self.assertEqual(m.to_cents('1.005'),101)

if __name__ == '__main__':
    unittest.main()
