import json
import math
import tempfile
from pathlib import Path
import unittest
from unittest.mock import patch

from runtime.tasks import load_task
from runtime.predictor import features,Predictor
from runtime.task_queue import TaskQueue


class Predictors(unittest.TestCase):
    def test_exported_direct_cost_and_feature_schema(self):
        p=Predictor.__new__(Predictor)
        p.model=dict(mean=[0,0],scale=[1,2],success=dict(coef=[1,-1],intercept=0),
                     cost=dict(coef=[100,200],intercept=500),cost_transform='identity')
        probability,cost=p.predict([1,2])
        self.assertAlmostEqual(probability,.5);self.assertAlmostEqual(cost,800)
        with self.assertRaises(ValueError):p.predict([1])

    def test_no_reference_or_outcome_features(self):
        with tempfile.TemporaryDirectory() as tmp:
            p=Path(tmp);(p/'task.json').write_text(json.dumps(dict(task_id='a',task_type='math',instruction='Find the minimum.',reward=1)))
            t=load_task(p);before=features(t)
            (p/'answer.txt').write_text('42');(p/'test_private.py').write_text('secret answer')
            self.assertEqual(before,features(t))
            raw=json.loads((p/'task.json').read_text());raw.update(task_id='other',reward=100,expected=9)
            (p/'task.json').write_text(json.dumps(raw));self.assertEqual(before,features(load_task(p)))

    def test_frozen_prediction_and_queue(self):
        with tempfile.TemporaryDirectory() as tmp:
            p=Path(tmp);tasks=[]
            for i,reward in enumerate([1,5]):
                d=p/str(i);d.mkdir();(d/'task.json').write_text(json.dumps(dict(task_id=str(i),task_type='math',instruction='Calculate.',reward=reward)))
                tasks.append(load_task(d))
            n=len(features(tasks[0]));model=dict(mean=[0]*n,scale=[1]*n,
                success=dict(coef=[0]*n,intercept=0),cost=dict(coef=[0]*n,intercept=math.log(501)),log_bias=0)
            (p/'numeric.json').write_text(json.dumps(model))
            with patch.dict('os.environ',{'PREDICTOR':'numeric','PREDICTOR_DIR':str(p)}):
                q=TaskQueue(tasks);self.assertAlmostEqual(q.predictor.predictions['0'][1],500)
                before=q.score(tasks[0]);q.record(tasks[0],'failed',9999)
                self.assertEqual(before,q.score(tasks[0]));self.assertEqual(q.next()[0].id,'1')
                self.assertEqual(q.next(0)[0].id,'0') # advisory zero never stops production


if __name__=='__main__':unittest.main()
