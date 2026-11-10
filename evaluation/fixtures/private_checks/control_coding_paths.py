import random
import unittest
from paths import clean

class Hidden(unittest.TestCase):
 def test_generated(self):
  rng=random.Random(719)
  for _ in range(150):
   parts=[rng.choice(['a','b','node','','.','..']) for _ in range(rng.randrange(1,15))]
   text='/'.join(parts)
   stack=[]; invalid=text.startswith('/')
   for p in parts:
    if p in ('','.'): continue
    if p=='..':
     if not stack: invalid=True; break
     stack.pop()
    else: stack.append(p)
   if invalid:
    with self.assertRaises(ValueError): clean(text)
   else: self.assertEqual(clean(text),'/'.join(stack))
