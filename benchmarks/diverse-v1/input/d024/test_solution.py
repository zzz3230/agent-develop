import unittest
import solution as m

class Cases(unittest.TestCase):
    def test_000(self):
        self.assertEqual(m.lookup({'a':[{'b':7}]},['a',0,'b']),7)

if __name__ == '__main__':
    unittest.main()
