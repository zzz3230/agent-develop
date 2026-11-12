import json
from pathlib import Path
import tempfile
import unittest

from evaluation.compare_pool_predictors import summarize


class CutoffTests(unittest.TestCase):
    def test_exact_boundary_and_late_correct_answer(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);(root/'harness').mkdir()
            grade=dict(total=dict(points=19,correct=3,possible=19),spent=50001,
                       rows=[dict(id=i,points=p,correct=True) for i,p in [('a',8),('b',5),('c',6)]])
            info=dict(env=dict(PREDICTOR='numeric',QUEUE_POLICY='greedy'),wall_seconds=10,
                      stopped_by='hard_budget',finish={},exit_code=137)
            (root/'graded.json').write_text(json.dumps(grade),encoding='utf-8')
            (root/'run.json').write_text(json.dumps(info),encoding='utf-8')
            events=[]
            for task,cost in [('a',49000),('b',1000),('c',1)]:
                events.extend([dict(event='llm_call',cost=cost,input=0,output=cost),dict(event='outcome',task=task)])
            (root/'harness/trajectory.jsonl').write_text('\n'.join(json.dumps(r) for r in events),encoding='utf-8')
            row=summarize(root)
            self.assertEqual(row['strict_points'],13)
            self.assertEqual(row['strict_correct'],2)
            self.assertEqual(row['points'],19)
            self.assertEqual(row['spent'],50001)


if __name__=='__main__':unittest.main()
