import unittest
import lib_c9752849 as m

class Cases(unittest.TestCase):
    def test_000(self):
        self.assertEqual(m.calculate('2*(3+4)-5'),9)

if __name__ == '__main__':
    unittest.main()
