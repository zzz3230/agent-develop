import unittest
import intervals as m
class T(unittest.TestCase):
 def test_unsorted_nested(self): self.assertEqual(m.merge([(5,8),(1,10),(2,3)]),[(1,10)])
 def test_adjacent(self): self.assertEqual(m.merge([(1,2),(2,3)]),[(1,2),(2,3)])
 def test_zero_empty(self): self.assertEqual(m.merge([(4,4)]),[]); self.assertEqual(m.merge([]),[])
 def test_invalid(self):
  with self.assertRaises(ValueError): m.merge([(4,2)])
 def test_coverage(self): self.assertEqual(m.covered([(-3,2),(0,5)]),8)
 def test_input(self):
  x=[(5,8),(1,4)]; m.merge(x); self.assertEqual(x,[(5,8),(1,4)])
if __name__=="__main__": unittest.main()
