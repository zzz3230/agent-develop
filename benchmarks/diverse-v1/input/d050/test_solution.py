import unittest
import solution as m

class Cases(unittest.TestCase):
    def test_000(self):
        self.assertEqual(m.split_fields(r'a\|b|c'),['a|b','c'])

if __name__ == '__main__':
    unittest.main()
