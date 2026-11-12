import unittest
import lib_6e978a70 as m

class Cases(unittest.TestCase):
    def test_000(self):
        self.assertEqual(m.order({'a':['z'],'z':[]}),['z','a'])

if __name__ == '__main__':
    unittest.main()
