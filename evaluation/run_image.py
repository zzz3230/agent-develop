"""Run one agent image on a task set under the contest sandbox, then grade it.

    python -m evaluation.run_image --image hack:latest --tasks TASKS --out benchmark-runs/NAME \
        [--references REF] [--env QUEUE=0 ...] [--mock] [--hard-budget 24000]

* The container gets exactly the flags of docs/rules.md: read-only root, tmpfs /tmp 2g,
  HOME=/tmp, no capabilities, 8 CPU, 16g RAM, 512 pids. Only a fresh copy of TASKS is
  mounted (task.json `expected` removed); the journal goes to OUT/harness on the host.
* --mock starts evaluation/mock_llm.py from the same image in a neighbour container on a
  private Docker network (free, no proxy). Without --mock, LLM_BASE_URL and LLM_API_KEY
  are passed through from this terminal; the key is never written to OUT.
* --hard-budget N kills the container once the journal shows N spent, like the proxy
  cutting the key; it works for any image version. The container is always killed after
  --wall-limit seconds (default 3600, the contest hour).
* OUT/run.json records image id, commit, flags, the in-image configuration (model, limits),
  wall time, exit code and why it was stopped; OUT/graded.json the grade (evaluation.grade).
"""
from __future__ import annotations

import argparse
import json
import os
import shutil
import subprocess
import sys
import time
import uuid
from datetime import datetime, timezone
from pathlib import Path

from evaluation.grade import grade, print_report

ROOT = Path(__file__).resolve().parents[1]
PROBE = Path(__file__).resolve().parent / 'container_probe.py'
NETWORK = 'hack-test'
CONTEST_FLAGS = ['--read-only', '--tmpfs', '/tmp:rw,size=2g', '--env', 'HOME=/tmp', '--cap-drop', 'ALL',
                 '--security-opt', 'no-new-privileges', '--cpus', '8', '--memory', '16g', '--pids-limit', '512',
                 '--workdir', '/app', '--entrypoint', 'python']
LEAKS = ('answer.json', 'reference_solution.py', 'manifest.json', 'selection.json')


def docker(*args, check=True, timeout=120) -> subprocess.CompletedProcess:
    done = subprocess.run(['docker', *args], capture_output=True, text=True, encoding='utf-8',
                          errors='replace', timeout=timeout)
    if check and done.returncode:
        raise RuntimeError(f"docker {' '.join(args[:3])} failed: {(done.stderr or done.stdout)[-800:]}")
    return done


def bind(source: Path, target: str, readonly=False) -> list[str]:
    return ['--mount', f'type=bind,source={source.resolve()},target={target}' + (',readonly' if readonly else '')]


def image_id(image: str) -> str:
    return json.loads(docker('image', 'inspect', image).stdout)[0]['Id']


def git_commit() -> str | None:
    done = subprocess.run(['git', 'rev-parse', 'HEAD'], cwd=ROOT, capture_output=True, text=True)
    return done.stdout.strip() or None


def copy_tasks(source: Path, target: Path) -> int:
    """Fresh agent input; drops `expected`, refuses folders that carry references."""
    for leak in LEAKS:
        if any(source.rglob(leak)):
            raise ValueError(f'{source} contains {leak}: mount only prepared agent inputs')
    if any(source.rglob('test_private*')):
        raise ValueError(f'{source} contains private tests')
    shutil.copytree(source, target)
    count = 0
    for task_json in target.glob('*/task.json'):
        raw = json.loads(task_json.read_text(encoding='utf-8'))
        if raw.pop('expected', None) is not None or 'solvable' in raw:
            raw.pop('solvable', None)
            task_json.write_text(json.dumps(raw, ensure_ascii=False, indent=2), encoding='utf-8')
        for stale in ('answer.txt', '.answer.tmp'):
            (task_json.parent / stale).unlink(missing_ok=True)
        count += 1
    if not count:
        raise ValueError(f'{source}: no task folders with task.json')
    return count


def probe(image: str, tasks: Path) -> dict:
    done = docker('run', '--rm', '--network', 'none', *CONTEST_FLAGS, *bind(tasks, '/data/tasks'),
                  *bind(PROBE.parent, '/probe', readonly=True), image, '/probe/container_probe.py', timeout=180)
    return json.loads(done.stdout.strip().splitlines()[-1])


class Mock:
    """mock_llm.py from the image, reachable as http://NAME:8099/v1 on a private network."""

    def __init__(self, image: str, budget: float | None = None, delay: float = 0.0):
        self.image, self.budget, self.delay = image, budget, delay
        self.name = 'hack-mock-' + uuid.uuid4().hex[:8]

    def __enter__(self):
        if docker('network', 'inspect', NETWORK, check=False).returncode:
            docker('network', 'create', NETWORK)
        args = ['--port', '8099', '--delay', str(self.delay)]
        if self.budget is not None:
            args += ['--budget', str(self.budget)]
        docker('run', '-d', '--rm', '--name', self.name, '--network', NETWORK, '--read-only',
               '--entrypoint', 'python', self.image, '/app/evaluation/mock_llm.py', *args)
        check = f"import urllib.request; urllib.request.urlopen('http://{self.name}:8099/stats', timeout=2)"
        for _ in range(20):
            if docker('run', '--rm', '--network', NETWORK, '--entrypoint', 'python', self.image, '-c', check,
                      check=False).returncode == 0:
                return self
            time.sleep(1)
        raise RuntimeError('mock LLM did not start')

    @property
    def url(self) -> str:
        return f'http://{self.name}:8099/v1'

    def stats(self) -> dict:
        code = f"import urllib.request; print(urllib.request.urlopen('http://{self.name}:8099/stats').read().decode())"
        done = docker('run', '--rm', '--network', NETWORK, '--entrypoint', 'python', self.image, '-c', code, check=False)
        try:
            data = json.loads(done.stdout)
            return {k: data[k] for k in ('requests', 'spent', 'rejected')}
        except (ValueError, KeyError):
            return {}

    def __exit__(self, *exc):
        docker('rm', '-f', self.name, check=False)


def journal_spent(path: Path) -> float:
    try:
        with path.open('rb') as stream:
            stream.seek(max(0, path.stat().st_size - 20000))
            lines = stream.read().decode('utf-8', 'replace').splitlines()
    except OSError:
        return 0.0
    for line in reversed(lines):
        if '"llm_call"' in line:
            try:
                return float(json.loads(line)['spent'])
            except (ValueError, KeyError):
                continue
    return 0.0


def run(image: str, tasks: Path, out: Path, env: dict[str, str] | None = None, *, mock: Mock | None = None,
        network: str | None = None, hard_budget: float | None = None, kill_after: float | None = None,
        wall_limit: float = 3600, references: Path | None = None, private: Path | None = None,
        label: str | None = None, commit: str | None = None, with_probe: bool = True, quiet: bool = False) -> dict:
    out = out.resolve()
    if out.exists():
        raise ValueError(f'{out} exists; use a new folder for every run')
    out.mkdir(parents=True)
    count = copy_tasks(tasks, out / 'tasks')
    (out / 'harness').mkdir()
    trajectory = out / 'harness' / 'trajectory.jsonl'
    info = dict(label=label or out.name, image=image, image_id=image_id(image), commit=commit or git_commit(), commit_from='--commit' if commit else 'git HEAD of this checkout',
                tasks_source=str(tasks.resolve()), tasks=count, env=env or {}, mock=bool(mock),
                hard_budget=hard_budget, kill_after=kill_after, wall_limit=wall_limit,
                started=datetime.now(timezone.utc).isoformat(timespec='seconds'))
    if with_probe:
        info['probe'] = probe(image, out / 'tasks')
    flags = []
    for key, value in (env or {}).items():
        flags += ['--env', f'{key}={value}']
    flags += ['--env', 'TRAJECTORY=/data/harness/trajectory.jsonl']
    if mock:
        flags += ['--network', NETWORK, '--env', f'LLM_BASE_URL={mock.url}', '--env', 'LLM_API_KEY=mock-not-a-key']
    else:
        missing = [k for k in ('LLM_BASE_URL', 'LLM_API_KEY') if not os.environ.get(k)]
        if missing:
            raise ValueError('set ' + ' and '.join(missing) + ' in this terminal, or use --mock')
        flags += ['--env', 'LLM_BASE_URL', '--env', 'LLM_API_KEY'] + (['--network', network] if network else [])
    name = 'hack-run-' + uuid.uuid4().hex[:8]
    command = ['docker', 'run', '--rm', '--name', name, *CONTEST_FLAGS, *flags, *bind(out / 'tasks', '/data/tasks'),
               *bind(out / 'harness', '/data/harness'), image, '/app/run_agent.py', '--tasks-dir', '/data/tasks']
    started, stopped_by = time.monotonic(), None
    resource_samples=[]
    resource_errors=[]
    last_resource=started
    with (out / 'console.log').open('w', encoding='utf-8') as log:
        process = subprocess.Popen(command, stdout=log, stderr=subprocess.STDOUT)
        while process.poll() is None:
            time.sleep(1)
            elapsed = time.monotonic() - started
            if time.monotonic()-last_resource>=10:
                try:
                    measured=docker('stats','--no-stream','--format','{{json .}}',name,check=False,timeout=15)
                    if measured.returncode==0 and measured.stdout.strip():
                        resource_samples.append(json.loads(measured.stdout.strip()))
                except (OSError,subprocess.TimeoutExpired,ValueError) as exc:
                    resource_errors.append(str(exc)[:250])
                last_resource=time.monotonic()
            reason = ('wall_limit' if elapsed >= wall_limit else
                      'kill_after' if kill_after and elapsed >= kill_after else
                      'hard_budget' if hard_budget and journal_spent(trajectory) >= hard_budget else None)
            if reason:
                stopped_by = reason
                docker('kill', name, check=False)
                process.wait(timeout=60)
    info.update(wall_seconds=round(time.monotonic() - started, 1), exit_code=process.returncode, stopped_by=stopped_by)
    info['resource_samples']=resource_samples
    info['resource_sampling_errors']=resource_errors
    if mock:
        info['mock_stats'] = mock.stats()
    answers = list((out / 'tasks').glob('*/answer.txt'))
    info['answers'] = len(answers)
    info['leftover_tmp'] = [str(p.relative_to(out)) for p in (out / 'tasks').rglob('.answer.tmp')]
    info['incomplete_answers'] = [str(p.relative_to(out)) for p in answers
                                  if not p.read_bytes().endswith(b'\n') or not p.read_bytes().strip()]
    finish = next((json.loads(l) for l in reversed(trajectory.read_text(encoding='utf-8').splitlines())
                   if '"finish"' in l), {}) if trajectory.is_file() else {}
    info['finish'] = {k: finish.get(k) for k in ('spent', 'seconds', 'stop')}
    if references:
        report = grade(references, out / 'tasks', trajectory, private, docker_image=image)
        report['run'] = info
        (out / 'graded.json').write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding='utf-8')
        info['total'] = report['total']
        info['spent'] = report.get('spent')
        if not quiet:
            print_report(report)
    (out / 'run.json').write_text(json.dumps(info, ensure_ascii=False, indent=2), encoding='utf-8')
    if not quiet:
        print(json.dumps({k: info[k] for k in ('label', 'wall_seconds', 'exit_code', 'stopped_by', 'answers', 'finish')},
                         ensure_ascii=False))
        print(f'Saved {out}')
    return info


def parse_env(items):
    env = {}
    for item in items or []:
        key, _, value = item.partition('=')
        if not key or not _:
            raise ValueError(f'--env expects KEY=VALUE, got {item!r}')
        env[key] = value
    return env


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument('--image', default='hack:latest')
    parser.add_argument('--tasks', type=Path, required=True, help='prepared agent inputs (no references)')
    parser.add_argument('--out', type=Path, required=True, help='new folder for this run')
    parser.add_argument('--references', type=Path, help='grade right after the run')
    parser.add_argument('--private', type=Path, help='extra private tests for evaluation.grade')
    parser.add_argument('--env', action='append', help='KEY=VALUE for the agent, e.g. QUEUE=0 or BUDGET=24000')
    parser.add_argument('--label')
    parser.add_argument('--commit', help='commit the image was built from, if not the current checkout HEAD')
    parser.add_argument('--mock', action='store_true', help='free run against mock_llm.py, no proxy')
    parser.add_argument('--mock-budget', type=float, help='mock answers 429 after this weighted spend')
    parser.add_argument('--mock-delay', type=float, default=0.0, help='seconds per mock response')
    parser.add_argument('--network', help='docker network for the real proxy, if your setup needs one')
    parser.add_argument('--hard-budget', type=float, help='kill the run at this journal spend')
    parser.add_argument('--kill-after', type=float, help='kill after N seconds (persistence check)')
    parser.add_argument('--wall-limit', type=float, default=3600)
    args = parser.parse_args(argv)
    try:
        kwargs = dict(network=args.network, hard_budget=args.hard_budget, kill_after=args.kill_after,
                      wall_limit=args.wall_limit, references=args.references, private=args.private, label=args.label,
                      commit=args.commit)
        if args.mock:
            with Mock(args.image, args.mock_budget, args.mock_delay) as mock:
                run(args.image, args.tasks, args.out, parse_env(args.env), mock=mock, **kwargs)
        else:
            run(args.image, args.tasks, args.out, parse_env(args.env), **kwargs)
    except (ValueError, RuntimeError, OSError, subprocess.SubprocessError) as exc:
        parser.exit(1, f'{exc}\n')
    return 0


if __name__ == '__main__':
    sys.exit(main())
