"""Offline end-to-end check of export and grading. Runs no LLM, needs a local Docker image."""
import argparse
import contextlib
import io
import json
from pathlib import Path
import shutil
import tempfile

import suite


def main(image):
    suite.validate()
    with tempfile.TemporaryDirectory(prefix='diverse-pipeline-') as tmp:
        run=Path(tmp)/'run'
        suite.prepare('all',run,order_seed=101)
        selection=suite.read(run/'selection.json')
        rows={r['id']:r for r in suite.selected('all')}
        directories={e['id']:run/'tasks'/e['directory'] for e in selection['tasks']}
        assert not list((run/'tasks').rglob('answer.json'))
        assert not list((run/'tasks').rglob('test_private.py'))
        assert not (run/'tasks'/'manifest.json').exists()
        try:
            suite.prepare('all',run)
        except ValueError:
            pass
        else:
            raise AssertionError('prepare overwrote an existing run')
        # A complete run of known reference solutions verifies the judging path, not an agent.
        for task_id,work in directories.items():
            row=rows[task_id]
            ref=suite.ROOT/'references'/task_id
            if row['check']=='unittest':
                shutil.copy2(ref/'solution.py',work/'solution.py')
                answer='DONE'
            else:
                answer=suite.read(ref/'answer.json')['expected']
            (work/'answer.txt').write_text(answer+'\n',encoding='utf-8')
        # Include a charge for an interrupted task without any completed answer.
        usage=run/'usage.jsonl'
        usage.write_text('\n'.join(json.dumps(e) for e in [
            {'event':'llm_call','task':'d001','input':90,'output':7,'estimated':False},
            {'event':'attempt_stop','task':'d001'},
            {'event':'llm_call','task':'interrupted','input':110,'output':3,'estimated':False},
        ])+'\n',encoding='utf-8')
        with contextlib.redirect_stdout(io.StringIO()):
            report=suite.grade(run,image,usage=usage)
        assert report['total']['correct']==60, report['total']
        assert report['total']['points']==report['total']['possible_points']
        assert report['total']['abstentions_on_unavailable']==4
        assert report['usage']['weighted_tokens']==30 and report['usage']['calls']==2
        print('PASS: all 60 solvable reference submissions accepted, 4 unavailable yield no points.')
        print('PASS: shuffled export, fresh-run guard, no reference leakage, interrupted usage accounting.')
        # Isolate false-positive regressions: missing, malformed, wrong and changed-test answers.
        target=next(r for r in rows.values() if r['family']=='unit_conversion')
        (directories[target['id']]/'answer.txt').write_text('The answer is 2275000',encoding='utf-8')
        target=next(r for r in rows.values() if r['family']=='entity_disambiguation')
        (directories[target['id']]/'answer.txt').write_text('1973',encoding='utf-8')
        target=next(r for r in rows.values() if r['family']=='latest_snapshot')
        (directories[target['id']]/'answer.txt').unlink()
        target=next(r for r in rows.values() if r['family']=='lower_bound')
        # Passes its public example, fails unseen inputs.
        (directories[target['id']]/'solution.py').write_text('def lower_bound(values,target): return 3\n',encoding='utf-8')
        target=next(r for r in rows.values() if r['family']=='stable_unique')
        (directories[target['id']]/'test_solution.py').write_text('print("OK")\n',encoding='utf-8')
        with contextlib.redirect_stdout(io.StringIO()):
            report=suite.grade(run,image)
        assert report['total']['correct']==55,report['total']
        assert report['usage'] is None
        print('PASS: malformed/missing/wrong answers, example-only coding and edited tests rejected.')


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--image',default='hack:latest')
    main(p.parse_args().image)
