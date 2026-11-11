import itertools
import random
import unittest
from types import SimpleNamespace
from unittest.mock import patch
from runtime.planning import knapsack
from runtime.task_queue import TaskQueue


class Planning(unittest.TestCase):
    def test_exact_small_cases(self):
        rng=random.Random(193)
        for _ in range(60):
            items=[(rng.randint(1,20),rng.randint(1,15)) for _ in range(8)]
            budget=rng.randint(5,40);chosen=knapsack(items,budget)
            actual=sum(items[i][0] for i in chosen)
            best=max(sum(v for (v,c),take in zip(items,bits) if take) for bits in itertools.product([0,1],repeat=8)
                if sum(c for (v,c),take in zip(items,bits) if take)<=budget)
            self.assertEqual(actual,best);self.assertEqual(len(chosen),len(set(chosen)))

    def test_rounding_is_conservative(self):
        items=[(i+1,103.4+i*.9) for i in range(40)]
        chosen=knapsack(items,1234.5,max_states=32)
        self.assertLessEqual(sum(items[i][1] for i in chosen),1234.5)

    def test_score_alpha_and_knapsack_are_separate(self):
        ts=[SimpleNamespace(id=str(i),type='math',reward=v) for i,v in enumerate([60,100,120])]
        fake=SimpleNamespace(predictions={t.id:(1,c) for t,c in zip(ts,[10,20,30])})
        with patch.dict('os.environ',{'SCORE_ALPHA':'1','QUEUE_POLICY':'greedy'}):q=TaskQueue(ts)
        q.predictor=fake;self.assertEqual(q.next(50)[0].id,'0')
        with patch.dict('os.environ',{'SCORE_ALPHA':'1','QUEUE_POLICY':'knapsack'}):q=TaskQueue(ts)
        q.predictor=fake;self.assertEqual(q.next(50)[0].id,'1');self.assertEqual(q.next(30)[0].id,'2')
        self.assertIsNotNone(q.next(0)) # advisory zero never stops production
        with patch.dict('os.environ',{'SCORE_ALPHA':'2','QUEUE_POLICY':'greedy'}):q=TaskQueue(ts)
        q.predictor=fake;self.assertEqual(q.next(50)[0].id,'1')


if __name__=='__main__':unittest.main()
