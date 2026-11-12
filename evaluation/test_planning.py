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

    def test_fast_replay_matches_live_order(self):
        # Independently implemented replay must agree with the live greedy queue.
        from evaluation.tune_planning import replay
        rng=random.Random(911)
        for alpha in (0,.5,1,2,4):
            for policy in ('greedy','knapsack'):
                records=[dict(reward=rng.randint(1,10),p=rng.uniform(.1,.9),
                    predicted_cost=rng.randint(2,20),actual_cost=rng.randint(2,20),correct=rng.randrange(2)) for _ in range(12)]
                tasks=[SimpleNamespace(id=str(i),type='math',reward=r['reward']) for i,r in enumerate(records)]
                with patch.dict('os.environ',{'SCORE_ALPHA':str(alpha),'QUEUE_POLICY':policy}):q=TaskQueue(tasks)
                q.predictor=SimpleNamespace(predictions={str(i):(r['p'],r['predicted_cost']) for i,r in enumerate(records)})
                spent=0;completed=[]
                while spent<80 and (picked:=q.next(80-spent)):
                    i=int(picked[0].id);spent+=records[i]['actual_cost']
                    if spent<=80:completed.append(i)
                self.assertEqual(replay(records,80,alpha,policy)['completed'],completed)


if __name__=='__main__':unittest.main()
