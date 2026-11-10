import csv
import io
import random
import unittest
from decimal import Decimal
import ledger as m

class Hidden(unittest.TestCase):
    def test_generated(self):
        rng=random.Random(981)
        categories=[' Sale ','REFUND','other,ignored','other\nignored','sale',' refund ']
        rows=[]
        expected=Decimal(0)
        for _ in range(200):
            category=rng.choice(categories)
            amount=Decimal(rng.randrange(-999,1000))/Decimal(100)
            rows.append([category,str(amount)])
            if category.strip().lower()=='sale': expected+=amount
            if category.strip().lower()=='refund': expected-=amount
        stream=io.StringIO(newline='')
        w=csv.writer(stream); w.writerow(['category','amount']); w.writerows(rows)
        self.assertEqual(m.total(stream.getvalue()),expected)

    def test_invalid_and_nonfinite(self):
        self.assertEqual(m.total('category,amount\nsale,Infinity\nrefund,-Infinity\nsale,NaN\nsale,bad\nsale,1.005\nrefund,0.005\n'),Decimal(1))
