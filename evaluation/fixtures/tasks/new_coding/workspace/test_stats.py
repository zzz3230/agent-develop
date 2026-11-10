import unittest
import stats as s
class Tests(unittest.TestCase):
    def test_median_odd(self): self.assertEqual(s.median([7,1,3]),3)
    def test_median_even(self): self.assertEqual(s.median([8,2,4,6]),5)
    def test_run(self): self.assertEqual(s.longest_run([1,1,1,0,1]),3)
    def test_empty_run(self): self.assertEqual(s.longest_run([]),0)
if __name__ == "__main__": unittest.main()
