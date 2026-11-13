"""Prepare and label 213 planner-train variants without quality holdout family overlap."""
import json
import random
import shutil
from pathlib import Path

from evaluation.quality_dataset import META, ROOT, dump, input_hash
from evaluation.run_image import run

SOURCE = ROOT / 'benchmarks/planner-500/train'
OUT = ROOT / 'benchmark-runs/quality-large-v1'
IMAGE = 'agent-develop:main-candidate'


def prepare():
    original = json.loads((SOURCE / 'manifest.json').read_text(encoding='utf-8'))
    quality = json.loads((META / 'manifest.json').read_text(encoding='utf-8'))['tasks']
    groups = {r['family']: r['group'] for r in quality}
    held = {r['group'] for r in quality if r['split'] == 'holdout'}
    chosen = [r for r in original['tasks'] if groups.get(r['family'], r['family']) not in held]
    assert len(chosen) == 213
    assert not {groups.get(r['family'], r['family']) for r in chosen} & held
    random.Random(20261113).shuffle(chosen)
    batches = [chosen[i:i + 71] for i in range(0, len(chosen), 71)]
    assert len(batches) == 3 and all(len(b) == 71 for b in batches)
    OUT.mkdir(parents=True, exist_ok=True)
    manifest = dict(source_input_sha256=original['input_sha256'], quality_split_sha256=input_hash(META),
                    count=len(chosen), groups=len({groups.get(r['family'], r['family']) for r in chosen}),
                    excluded=len(original['tasks'])-len(chosen), batches=[])
    for index, rows in enumerate(batches):
        batch = OUT / f'batch-{index + 1}'
        folder = batch / 'input'
        folder.mkdir(parents=True, exist_ok=True)
        for row in rows:
            shutil.copytree(SOURCE / 'input' / row['id'], folder / row['id'], dirs_exist_ok=True)
        manifest['batches'].append(dict(name=batch.name, ids=[r['id'] for r in rows],
                                        input_sha256=input_hash(folder)))
    path = OUT / 'manifest.json'
    if path.exists():
        assert json.loads(path.read_text(encoding='utf-8')) == manifest
    else:
        dump(path, manifest)
    print(json.dumps(dict(count=manifest['count'], groups=manifest['groups'], batches=3)), flush=True)
    return manifest


def collect():
    manifest = prepare()
    for row in manifest['batches']:
        batch = OUT / row['name']
        primary = batch / 'run/graded.json'
        if primary.exists():
            report = json.loads(primary.read_text(encoding='utf-8'))
            missing = [r['id'] for r in report['rows'] if r['cost'] <= 0]
            if not missing:
                print('REUSE', row['name'], flush=True)
                continue
            assert row['name'] == 'batch-3' and len(missing) == 7
            retry = batch / 'retry-input'
            retry.mkdir(parents=True, exist_ok=True)
            for identifier in missing:
                shutil.copytree(SOURCE / 'input' / identifier, retry / identifier, dirs_exist_ok=True)
            retry_report = batch / 'retry-run/graded.json'
            if retry_report.exists():
                retry_rows = json.loads(retry_report.read_text(encoding='utf-8'))['rows']
                assert {r['id'] for r in retry_rows} == set(missing)
                assert all(r['cost'] > 0 for r in retry_rows)
                print('REUSE RETRY', row['name'], flush=True)
                continue
            print('RETRY', row['name'], len(missing), flush=True)
            result = run(IMAGE, retry, batch / 'retry-run',
                         env={'QUEUE': '0', 'RETRY': '0', 'BUDGET': '1000000', 'ENFORCE_BUDGET': '0'},
                         references=SOURCE, quiet=True, wall_limit=1800)
            assert result['finish']['stop'] == 'all tasks handled', 'Incomplete retry'
            print('RESULT RETRY', row['name'], result['spent'], flush=True)
            continue
        print('START', row['name'], flush=True)
        result = run(IMAGE, batch / 'input', batch / 'run',
                     env={'QUEUE': '0', 'RETRY': '0', 'BUDGET': '1000000', 'ENFORCE_BUDGET': '0'},
                     references=SOURCE, quiet=True, wall_limit=3600)
        assert result['finish']['stop'] == 'all tasks handled', 'Incomplete training collection'
        print('RESULT', row['name'], result['spent'], flush=True)


if __name__ == '__main__':
    import sys
    {'prepare': prepare, 'collect': collect}[sys.argv[1]]()
