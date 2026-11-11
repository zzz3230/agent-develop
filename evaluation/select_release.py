"""Pick the release and the backup from finished holdout runs (evaluation.run_image).

    python -m evaluation.select_release --out docs/release \
        all_on=benchmark-runs/h-all_on queue_off=benchmark-runs/h-queue_off prev=benchmark-runs/h-prev [--tag]

A label may be given several times (repeated runs are averaged). Rule: highest mean points;
on a tie the lower mean spend. All runs must be on the same task ids with the same hard
budget, otherwise the comparison is refused. The backup is the next candidate, preferring
another image so it still works if the release image is broken. Writes selection.json and
selection.md (commit, image id, model, attempt limits, time limit, env flags, every run);
--tag also tags the images hack:release / hack:backup.
"""
from __future__ import annotations

import argparse
import json
import subprocess
import sys
from collections import defaultdict
from pathlib import Path
from statistics import mean

TEST_ONLY = {'BUDGET', 'RUN_TIME_LIMIT'}  # scale the run for the holdout size; not part of the release


def load(run_dir: Path) -> dict:
    graded = json.loads((run_dir / 'graded.json').read_text(encoding='utf-8'))
    info = json.loads((run_dir / 'run.json').read_text(encoding='utf-8'))
    total = graded['total']
    return dict(dir=str(run_dir), points=total['points'], max_points=total['possible'], correct=total['correct'],
                false_claims=total['false_claims'], spent=graded.get('spent') or total.get('spent') or 0,
                tasks=sorted(r['id'] for r in graded['rows']), info=info)


def choose(candidates: dict[str, list[dict]]) -> list[dict]:
    rows = []
    for label, runs in candidates.items():
        info = runs[0]['info']
        rows.append(dict(label=label, runs=len(runs), points=mean(r['points'] for r in runs),
                         max_points=runs[0]['max_points'], spent=mean(r['spent'] for r in runs),
                         false_claims=mean(r['false_claims'] for r in runs), image=info['image'],
                         image_id=info['image_id'], commit=info.get('commit'), env=info.get('env', {}),
                         config=(info.get('probe') or {}).get('config'), hard_budget=info.get('hard_budget'),
                         dirs=[r['dir'] for r in runs]))
    return sorted(rows, key=lambda r: (-r['points'], r['spent']))


def check_same(candidates: dict[str, list[dict]]):
    runs = [r for rs in candidates.values() for r in rs]
    tasks = {tuple(r['tasks']) for r in runs}
    budgets = {r['info'].get('hard_budget') for r in runs}
    if len(tasks) > 1:
        raise ValueError('runs were graded on different task sets; use the same prepared holdout')
    if len(budgets) > 1:
        raise ValueError(f'runs used different --hard-budget values {budgets}; the budget must be equal')


def backup_of(ranked: list[dict]) -> dict | None:
    rest = ranked[1:]
    other = [r for r in rest if r['image_id'] != ranked[0]['image_id']]
    return (other or rest or [None])[0]


def markdown(ranked, release, backup) -> str:
    def describe(r):
        c = r['config'] or {}
        return [f"- метка: `{r['label']}`, образ `{r['image']}` (`{r['image_id'][:19]}`), commit `{r['commit']}`",
                f"- модель: `{c.get('model')}`, лимит времени агента: {c.get('time_limit_s')} с, "
                f"бюджет по умолчанию: {c.get('default_budget')}",
                f"- флаги окружения: `{json.dumps(r['env'], ensure_ascii=False)}`",
                f"- лимиты попыток: `{json.dumps(c.get('attempt_limits'), ensure_ascii=False)}`",
                f"- баллы {r['points']:g} из {r['max_points']}, расход {r['spent']:.1f}, прогонов {r['runs']}"]
    lines = ['# Выбор конфигурации', '',
             f"Правило: максимум баллов на одном отложенном наборе при одинаковом бюджете "
             f"(hard budget {ranked[0]['hard_budget']}); при равенстве меньший расход.", '',
             '| Место | Метка | Баллы | Расход | Ложные | Прогонов | Образ | Commit |', '|---|---|---|---|---|---|---|---|']
    for i, r in enumerate(ranked, 1):
        lines.append(f"| {i} | {r['label']} | {r['points']:g} из {r['max_points']} | {r['spent']:.1f} | "
                     f"{r['false_claims']:g} | {r['runs']} | {r['image']} | {(r['commit'] or '')[:10]} |")
    lines += ['', '## Основная', '', *describe(release), '']
    lines += ['## Резервная', '', *(describe(backup) if backup else ['- нет второго кандидата']), '']
    baked = {k: v for k, v in release['env'].items() if k not in TEST_ONLY}
    if baked:
        lines += [f'Внимание: у основной конфигурации есть флаги окружения {baked}. Организаторы запускают образ без них, '
                  'поэтому эти значения надо сделать значениями по умолчанию в коде, пересобрать образ и '
                  'прогнать evaluation.check_image ещё раз.', '']
    lines += ['После выбора: только критические исправления; каждое исправление проверять evaluation.check_image.', '']
    return '\n'.join(lines)


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument('runs', nargs='+', help='label=run_dir')
    parser.add_argument('--out', type=Path, default=Path('docs/release'))
    parser.add_argument('--tag', action='store_true', help='docker tag release/backup images')
    args = parser.parse_args(argv)
    candidates: dict[str, list[dict]] = defaultdict(list)
    try:
        for item in args.runs:
            label, _, path = item.partition('=')
            if not path:
                raise ValueError(f'expected label=run_dir, got {item!r}')
            candidates[label].append(load(Path(path)))
        check_same(candidates)
    except (ValueError, OSError, KeyError) as exc:
        parser.exit(1, f'{exc}\n')
    ranked = choose(candidates)
    release, backup = ranked[0], backup_of(ranked)
    args.out.mkdir(parents=True, exist_ok=True)
    (args.out / 'selection.json').write_text(json.dumps(dict(release=release, backup=backup, ranking=ranked),
                                                        ensure_ascii=False, indent=2, default=str), encoding='utf-8')
    (args.out / 'selection.md').write_text(markdown(ranked, release, backup), encoding='utf-8')
    if args.tag:
        subprocess.run(['docker', 'tag', release['image_id'], 'hack:release'], check=True)
        if backup:
            subprocess.run(['docker', 'tag', backup['image_id'], 'hack:backup'], check=True)
    print((args.out / 'selection.md').read_text(encoding='utf-8'))
    return 0


if __name__ == '__main__':
    sys.exit(main())
