"""Check one image before release. Mock part is free; --real spends the proxy budget.

    python -m evaluation.check_image --image hack:release --out benchmark-runs/check-release
    python -m evaluation.check_image --image hack:release --out ... --real [--holdout DIR]

Mock (local, mock_llm.py instead of the proxy; says nothing about answer quality):
  sandbox   read-only root, writable /tmp and tasks, 8 CPU, 16 GiB, 512 pids, HOME=/tmp,
            no benchmark references baked into the image, model and limits in the image
  load100   100 generated tasks: every task gets an outcome, answers match the journal,
            no half-written files, run ends with "all tasks handled"
  budget    mock proxy refuses after a small spend: run stops cleanly, answers kept
  hour      RUN_TIME_LIMIT=20 with a slow mock: the agent stops itself in time
  kill      container killed mid-run: every answer.txt on disk is complete
  hard      --hard-budget kill at a journal spend: run.json records it
Real proxy (--real, needs LLM_BASE_URL and LLM_API_KEY in this terminal):
  pairs     the 4 official sample pairs (math, data, search, coding): both of each pair correct
  holdout   optional: prepared holdout tasks (--holdout X/tasks), graded with --references

Writes OUT/report.md and OUT/report.json with the mock and real sections kept apart.
Exit code 1 when any critical check fails.
"""
from __future__ import annotations

import argparse
import json
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

from evaluation import run_image

ROOT = Path(__file__).resolve().parents[1]
FIXTURES = ROOT / 'evaluation' / 'fixtures'
PAIRS = [('math_0000', 'math_0004'), ('data_analysis_0002', 'data_analysis_0006'),
         ('search_0001', 'search_0005'), ('coding_0003', 'coding_0007')]
GIB = 1 << 30


class Report:
    def __init__(self):
        self.rows: list[dict] = []

    def add(self, section: str, check: str, ok: bool, detail='', critical=True):
        self.rows.append(dict(section=section, check=check, ok=bool(ok), critical=critical, detail=str(detail)[:400]))
        mark = 'OK  ' if ok else ('FAIL' if critical else 'WARN')
        print(f'[{section}] {mark} {check} {detail}'[:300], flush=True)

    @property
    def failed(self):
        return [r for r in self.rows if not r['ok'] and r['critical']]


def outcomes(trajectory: Path) -> dict[str, str]:
    result = {}
    if trajectory.is_file():
        for line in trajectory.read_text(encoding='utf-8').splitlines():
            event = json.loads(line)
            if event.get('event') == 'outcome':
                result[event['task']] = event.get('status')
    return result


def generated(count: int, out: Path) -> Path:
    subprocess.run([sys.executable, str(ROOT / 'evaluation' / 'build_suite.py'), 'load', '--output', str(out),
                    '--count', str(count)], check=True, capture_output=True)
    return out / 'input'


def mock_run(rep: Report, section: str, image: str, tasks: Path, out: Path, *, budget=None, delay=0.0, **kwargs):
    try:
        with run_image.Mock(image, budget, delay) as mock:
            return run_image.run(image, tasks, out, mock=mock, with_probe=False, quiet=True, **kwargs)
    except Exception as exc:  # a crash is a failed check, keep going with the rest
        rep.add(section, 'run finished', False, repr(exc))
        return None


def check_sandbox(rep: Report, image: str, tmp: Path):
    tasks = generated(2, tmp / 'probe-suite')
    work = tmp / 'probe-tasks'
    shutil.copytree(tasks, work)
    p = run_image.probe(image, work)
    s = 'sandbox'
    rep.add(s, 'root is read-only', p['root_readonly'])
    rep.add(s, '/tmp writable', p['tmp_writable'], f"{p['tmp_bytes'] / GIB:.1f} GiB")
    rep.add(s, '/data/tasks writable', p['tasks_writable'])
    rep.add(s, '8 CPU', p['cpus'] == 8, p['cpus'])
    rep.add(s, '16 GiB RAM', p['memory_bytes'] == 16 * GIB, p['memory_bytes'])
    rep.add(s, '512 pids', p['pids_max'] == 512, p['pids_max'], critical=False)
    rep.add(s, 'HOME=/tmp', p['home'] == '/tmp', p['home'])
    baked = p['image_has_references']
    rep.add(s, 'no benchmarks/ in image', not baked.get('/app/benchmarks'), baked)
    rep.add(s, 'no suite builder or fixtures in image', not any(v for k, v in baked.items() if k != '/app/benchmarks'),
            'dev-only files; not answers of the contest, but better kept out', critical=False)
    c = p['config']
    rep.add(s, 'openjiuwen installed', bool(c.get('openjiuwen')), c.get('openjiuwen'))
    rep.add(s, 'agent config loads', 'error' not in c, c.get('error') or
            f"model={c.get('model')} time_limit={c.get('time_limit_s')} budget={c.get('default_budget')}")
    rep.add(s, 'time limit under one hour', (c.get('time_limit_s') or 3600) < 3600, c.get('time_limit_s'))
    return p


def check_mock(rep: Report, image: str, out: Path, tmp: Path, env: dict):
    load = generated(100, tmp / 'load-suite')
    info = mock_run(rep, 'load100', image, load, out / 'load100', env=env)
    if info:
        done = outcomes(out / 'load100' / 'harness' / 'trajectory.jsonl')
        answered = {p.parent.name for p in (out / 'load100' / 'tasks').glob('*/answer.txt')}
        solved = {t for t, st in done.items() if st == 'solved'}
        rep.add('load100', '100 outcomes in journal', len(done) == 100, f'{len(done)} outcomes')
        rep.add('load100', 'answer files match journal "solved"', answered == solved,
                f'{len(answered)} answers, {len(solved)} solved')
        rep.add('load100', 'run ended "all tasks handled"', info['finish'].get('stop') == 'all tasks handled',
                info['finish'].get('stop'))
        rep.add('load100', 'no half-written answers', not info['incomplete_answers'] and not info['leftover_tmp'],
                info['incomplete_answers'] + info['leftover_tmp'])
        rep.add('load100', 'wall time', True, f"{info['wall_seconds']} s")

    small = generated(12, tmp / 'small-suite')
    info = mock_run(rep, 'budget', image, small, out / 'budget', env=env, budget=400)
    if info:
        stop = info['finish'].get('stop') or ''
        rep.add('budget', 'stops cleanly when the proxy refuses', info['exit_code'] == 0 and bool(stop), stop)
        rep.add('budget', 'proxy actually refused', info.get('mock_stats', {}).get('rejected', 0) > 0, info.get('mock_stats'))
        rep.add('budget', 'answers kept and complete', info['answers'] > 0 and not info['incomplete_answers'],
                f"{info['answers']} answers")

    info = mock_run(rep, 'hour', image, small, out / 'hour', env={**env, 'RUN_TIME_LIMIT': '20'}, delay=1.5,
                    wall_limit=200)
    if info:
        stop = info['finish'].get('stop') or ''
        rep.add('hour', 'agent stops itself at its time limit', 'time' in stop and info['stopped_by'] is None, stop)
        rep.add('hour', 'stop within 60 s of the limit', info['wall_seconds'] <= 20 + 60, f"{info['wall_seconds']} s")
        rep.add('hour', 'answers complete', not info['incomplete_answers'], info['answers'])

    info = mock_run(rep, 'kill', image, small, out / 'kill', env=env, delay=1.0, kill_after=10)
    if info:
        rep.add('kill', 'container was killed', info['stopped_by'] == 'kill_after', info['stopped_by'])
        rep.add('kill', 'answers on disk are complete', info['answers'] > 0 and not info['incomplete_answers'],
                f"{info['answers']} answers, incomplete {info['incomplete_answers']}")

    info = mock_run(rep, 'hard', image, small, out / 'hard', env=env, hard_budget=300)
    if info:
        rep.add('hard', 'run killed at the hard budget', info['stopped_by'] == 'hard_budget', info['stopped_by'],
                critical=False)
        rep.add('hard', 'answers complete', not info['incomplete_answers'], info['answers'])


def check_real(rep: Report, image: str, out: Path, tmp: Path, env: dict, holdout: Path | None, references: Path,
               hard_budget):
    pairs = tmp / 'pairs'
    pairs.mkdir()
    for pair in PAIRS:
        for task in pair:
            shutil.copytree(FIXTURES / 'tasks' / task, pairs / task)
    try:
        info = run_image.run(image, pairs, out / 'pairs', env, references=FIXTURES / 'tasks',
                             private=FIXTURES / 'private_checks', with_probe=False, quiet=True)
        graded = json.loads((out / 'pairs' / 'graded.json').read_text(encoding='utf-8'))
        right = {r['id']: r['correct'] for r in graded['rows']}
        for pair in PAIRS:
            rep.add('pairs', f'{pair[0]} + {pair[1]}', all(right.get(t) for t in pair),
                    ', '.join(f"{t}={'да' if right.get(t) else 'нет'}" for t in pair))
        rep.add('pairs', 'spend', True, f"{graded.get('spent')} за {info['wall_seconds']} s")
    except Exception as exc:
        rep.add('pairs', 'run finished', False, repr(exc))
    if holdout:
        try:
            run_image.run(image, holdout, out / 'holdout', env, references=references,
                          hard_budget=hard_budget, with_probe=False, quiet=True)
            total = json.loads((out / 'holdout' / 'graded.json').read_text(encoding='utf-8'))['total']
            rep.add('holdout', 'points', True, f"{total['points']} из {total['possible']}, верно {total['correct']}, "
                                              f"ложных {total['false_claims']}", critical=False)
            rep.add('holdout', 'no false claims on unavailable tasks', total['false_claims'] == 0, total['false_claims'],
                    critical=False)
        except Exception as exc:
            rep.add('holdout', 'run finished', False, repr(exc))


def write_report(rep: Report, out: Path, image: str, probe: dict | None):
    titles = {'sandbox': 'Mock', 'load100': 'Mock', 'budget': 'Mock', 'hour': 'Mock', 'kill': 'Mock', 'hard': 'Mock',
              'pairs': 'Настоящий прокси', 'holdout': 'Настоящий прокси'}
    lines = [f'# Проверка образа {image}', '',
             f"Критических провалов: {len(rep.failed)}", '']
    for title in ('Mock', 'Настоящий прокси'):
        rows = [r for r in rep.rows if titles[r['section']] == title]
        lines += [f'## {title}', '']
        if title == 'Mock':
            lines += ['Модель заменена mock_llm.py: проверены песочница, очередь, остановки и сохранение, '
                      'но не качество ответов.', '']
        if not rows:
            lines += ['Не запускалось (нужен флаг --real и ключ).', '']
            continue
        lines += ['| Блок | Проверка | Итог | Детали |', '|---|---|---|---|']
        for r in rows:
            mark = 'OK' if r['ok'] else ('ПРОВАЛ' if r['critical'] else 'внимание')
            lines.append(f"| {r['section']} | {r['check']} | {mark} | {r['detail'].replace('|', '/')} |")
        lines.append('')
    (out / 'report.md').write_text('\n'.join(lines), encoding='utf-8')
    (out / 'report.json').write_text(json.dumps(dict(image=image, image_id=run_image.image_id(image), probe=probe,
                                                     checks=rep.rows, critical_failures=len(rep.failed)),
                                                ensure_ascii=False, indent=2, default=str), encoding='utf-8')


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument('--image', default='hack:latest')
    parser.add_argument('--out', type=Path, required=True)
    parser.add_argument('--env', action='append', help='KEY=VALUE for the agent (same as the release config)')
    parser.add_argument('--skip-mock', action='store_true')
    parser.add_argument('--real', action='store_true', help='also run on the real proxy (paid)')
    parser.add_argument('--holdout', type=Path, help='prepared holdout tasks (suite.py prepare ... --out X -> X/tasks)')
    parser.add_argument('--references', type=Path, default=ROOT / 'benchmarks' / 'diverse-v1',
                        help='references for --holdout (default benchmarks/diverse-v1)')
    parser.add_argument('--hard-budget', type=float, help='cap for the holdout run')
    args = parser.parse_args(argv)
    out = args.out.resolve()
    if out.exists():
        parser.exit(1, f'{out} exists; choose a new folder\n')
    out.mkdir(parents=True)
    env = run_image.parse_env(args.env)
    rep, probe = Report(), None
    with tempfile.TemporaryDirectory(prefix='check-image-') as name:
        tmp = Path(name)
        try:
            probe = check_sandbox(rep, args.image, tmp)
        except Exception as exc:
            rep.add('sandbox', 'probe container ran', False, repr(exc))
        if not args.skip_mock:
            check_mock(rep, args.image, out, tmp, env)
        if args.real:
            check_real(rep, args.image, out, tmp, env, args.holdout, args.references, args.hard_budget)
    write_report(rep, out, args.image, probe)
    print(f"\n{len(rep.failed)} critical failures; report: {out / 'report.md'}")
    return 1 if rep.failed else 0


if __name__ == '__main__':
    sys.exit(main())
