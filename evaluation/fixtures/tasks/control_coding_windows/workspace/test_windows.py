import unittest
from windows import best_window as f
class T(unittest.TestCase):
 def test_last(self): self.assertEqual(f([1,2,8],2),10)
 def test_negative(self): self.assertEqual(f([-9,-2,-3],2),-5)
 def test_full(self): self.assertEqual(f((2,3),2),5)
 def test_bad(self):
  for k in [0,-1,4,1.5]:
   with self.assertRaises(ValueError): f([1,2],k)
if __name__=="__main__": unittest.main()
