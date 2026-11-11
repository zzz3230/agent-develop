import unittest
import solution as m

class Cases(unittest.TestCase):
    def test_000(self):
        s=m.Store(); self.assertIsNone(s.get('missing',0)); s.put('a',1,0,5); s.put('a',2,1,1); self.assertEqual(s.get('a',1),2); self.assertIsNone(s.get('a',2))

    def test_001(self):
        s=m.Store(); s.put('a',8,0,10); s.put('a',7,1,0); self.assertIsNone(s.get('a',1))

    def test_002(self):
        import random
        r=random.Random(16); s=m.Store(); history=[]
        for t in range(140):
         key=r.choice('abcd')
         if r.random()<.6:
          value=r.randrange(99); ttl=r.randrange(-1,9); s.put(key,value,t,ttl); history.append((key,value,t,ttl))
         else:
          old=next((h for h in reversed(history) if h[0]==key),None)
          want=old[1] if old and t<old[2]+old[3] else None
          self.assertEqual(s.get(key,t),want)

if __name__ == '__main__':
    unittest.main()
