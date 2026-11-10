import random
import unittest
from windows import best_window

class Hidden(unittest.TestCase):
 def test_generated(self):
  rng=random.Random(702)
  for _ in range(120):
   xs=[rng.randrange(-99,100) for _ in range(rng.randrange(1,25))]
   k=rng.randrange(1,len(xs)+1); original=list(xs)
   self.assertEqual(best_window(xs,k),max(sum(xs[i:i+k]) for i in range(len(xs)-k+1)))
   self.assertEqual(xs,original)
