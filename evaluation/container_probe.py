"""Runs inside the agent container (mounted read-only, works for any image version).

Prints one JSON line: sandbox facts (read-only root, writable /tmp and tasks, cgroup CPU,
memory and pids limits, what the image contains) and the agent configuration baked into
the image (model, limits, time limit, budget default). Never prints the API key.
"""
import importlib.metadata
import json
import os
import sys
from dataclasses import asdict
from pathlib import Path


def writable(path: str) -> bool:
    probe = Path(path) / f'.probe-{os.getpid()}'
    try:
        probe.write_text('x')
        probe.unlink()
        return True
    except OSError:
        return False


def read(path: str):
    try:
        return Path(path).read_text().strip()
    except OSError:
        return None


def cpus():
    v2 = read('/sys/fs/cgroup/cpu.max')
    if v2 and v2.split()[0] != 'max':
        quota, period = v2.split()
        return int(quota) / int(period)
    quota, period = read('/sys/fs/cgroup/cpu/cpu.cfs_quota_us'), read('/sys/fs/cgroup/cpu/cpu.cfs_period_us')
    if quota and period and int(quota) > 0:
        return int(quota) / int(period)
    return None


def number(*paths):
    for path in paths:
        value = read(path)
        if value and value != 'max':
            return int(value)
    return None


def config():
    sys.path.insert(0, os.environ.get('PROBE_APP', '/app'))
    out = {}
    try:
        import run_agent
        for name in ('MODEL', 'TIME_LIMIT_S', 'DEFAULT_BUDGET', 'MAX_CONSECUTIVE_ERRORS', 'TOOLS'):
            out[name.lower()] = getattr(run_agent, name, None)
    except Exception as exc:  # report, do not fail the probe
        out['error'] = repr(exc)[:300]
    try:
        from runtime import attempt_policy
        out['attempt_limits'] = {k: asdict(v) for k, v in attempt_policy.DEFAULTS.items()}
    except Exception as exc:
        out['attempt_limits_error'] = repr(exc)[:300]
    try:
        out['openjiuwen'] = importlib.metadata.version('openjiuwen')
    except Exception:
        out['openjiuwen'] = None
    out['env'] = {k: os.environ.get(k) for k in ('QUEUE', 'RETRY', 'PROMPT_ECONOMY', 'ADAPTIVE_LIMITS',
                                                 'CSV_SCHEMA', 'SEARCH_CONTEXT', 'CSV_SQL', 'BUDGET')}
    return out


def main():
    facts = dict(
        python=sys.version.split()[0], user=os.getuid(), home=os.environ.get('HOME'), cwd=os.getcwd(),
        root_readonly=not writable('/') and not writable('/app'),
        tmp_writable=writable('/tmp'),
        tmp_bytes=os.statvfs('/tmp').f_blocks * os.statvfs('/tmp').f_frsize,
        tasks_writable=writable('/data/tasks'),
        cpus=cpus(),
        memory_bytes=number('/sys/fs/cgroup/memory.max', '/sys/fs/cgroup/memory/memory.limit_in_bytes'),
        pids_max=number('/sys/fs/cgroup/pids.max', '/sys/fs/cgroup/pids/pids.max'),
        image_has_references={p: Path(p).exists() for p in (
            '/app/evaluation/fixtures', '/app/evaluation/build_suite.py', '/app/evaluation/generate_suite.py',
            '/app/benchmarks', '/app/docs')},
        config=config(),
    )
    print(json.dumps(facts, ensure_ascii=False, default=str))


if __name__ == '__main__':
    main()
