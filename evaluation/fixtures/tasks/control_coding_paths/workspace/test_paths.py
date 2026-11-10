import unittest
from paths import clean
class T(unittest.TestCase):
 def test_parent(self): self.assertEqual(clean("a/b/../c//"),"a/c")
 def test_empty(self): self.assertEqual(clean("./"),"")
 def test_escape(self):
  with self.assertRaises(ValueError): clean("a/../../b")
 def test_absolute(self):
  with self.assertRaises(ValueError): clean("/a")
 def test_type(self):
  with self.assertRaises(TypeError): clean(None)
if __name__=="__main__": unittest.main()
