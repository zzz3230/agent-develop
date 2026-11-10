import unittest
from decimal import Decimal
import ledger as m
class T(unittest.TestCase):
 def test_money(self): self.assertEqual(m.total("category,amount\nsale,0.1\nsale,0.2\nrefund,0.05\n"),Decimal("0.25"))
 def test_filter(self): self.assertEqual(m.total("category,amount\n Sale ,7\nrefund,2\nother,99\nsale,NaN\nsale,wrong\n"),Decimal(5))
 def test_quoted(self): self.assertEqual(m.total('category,amount\n"other,word",7\n"other\nline",8\nsale,3\n'),Decimal(3))
 def test_empty(self): self.assertEqual(m.total(""),Decimal(0))
 def test_type(self): self.assertIsInstance(m.total("category,amount\nsale,1\n"),Decimal)
if __name__=="__main__": unittest.main()
