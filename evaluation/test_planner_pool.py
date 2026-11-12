"""Reward resampling must preserve answers, cases and reproducibility."""
import contextlib
import io
import json
from pathlib import Path
import tempfile
import unittest

from evaluation.prepare_planner_pool import prepare


class PlannerPoolTests(unittest.TestCase):
    def test_rewards_and_reproducibility(self):
        pool=Path(__file__).resolve().parents[1]/'benchmarks'/'planner-500'
        with tempfile.TemporaryDirectory() as tmp:
            outputs=[Path(tmp)/str(i) for i in range(3)]
            with contextlib.redirect_stdout(io.StringIO()):
                for out,seed in zip(outputs,(1001,1001,1002)):
                    prepare(pool,out,'eval',20,101,seed)
            manifests=[json.loads((p/'manifest.json').read_text(encoding='utf-8')) for p in outputs]
            self.assertEqual(manifests[0],manifests[1])
            self.assertEqual([r['id'] for r in manifests[0]['tasks']],
                             [r['id'] for r in manifests[2]['tasks']])
            self.assertNotEqual(manifests[0]['input_sha256'],manifests[2]['input_sha256'])
            for out,manifest in zip(outputs,manifests):
                self.assertEqual(sum(not r['solvable'] for r in manifest['tasks']),4)
                for directory in (out/'input').iterdir():
                    task=json.loads((directory/'task.json').read_text(encoding='utf-8'))
                    reference=json.loads((out/'references'/task['task_id']/'task.json').read_text(encoding='utf-8'))
                    self.assertEqual(reference,dict(task,expected=reference['expected']))
                    self.assertNotIn('expected',task)
                    self.assertFalse(list(directory.rglob('test_private*')))
            with self.assertRaises(ValueError):
                prepare(pool,outputs[0],'eval',20,101,1001)

    def test_invalid_count_has_no_side_effect(self):
        with tempfile.TemporaryDirectory() as tmp:
            out=Path(tmp)/'unused'
            with self.assertRaises(ValueError):
                prepare(Path('missing-pool'),out,'eval',0,1,2)
            self.assertFalse(out.exists())


if __name__=='__main__':
    unittest.main()
