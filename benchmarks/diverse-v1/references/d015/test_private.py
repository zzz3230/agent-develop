import unittest
import solution as m

class Cases(unittest.TestCase):
    def test_000(self):
        self.assertEqual(m.read_rows(''),[])

    def test_001(self):
        self.assertEqual(m.read_rows('"a\nb","say ""hi"""\n'),[['a\nb','say "hi"']])

    def test_002(self):
        import csv,io,random
        r=random.Random(13)
        for _ in range(60):
         rows=[[r.choice(['a,b','x\ny','"','', ' spaced ']) for _ in range(3)] for _ in range(5)]
         s=io.StringIO(newline=''); csv.writer(s,lineterminator='\n').writerows(rows)
         self.assertEqual(m.read_rows(s.getvalue()), rows)

if __name__ == '__main__':
    unittest.main()
