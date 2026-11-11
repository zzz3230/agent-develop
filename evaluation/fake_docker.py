#!/usr/bin/env python3
"""Test-only stand-in for the `docker` CLI so run_image/check_image logic runs without Docker.

Containers become local processes: /app is this repository, bind mounts map to their host
sources, `hack-mock-*` hostnames resolve to 127.0.0.1. Sandbox limits are NOT enforced, so
results say nothing about read-only root, CPU or memory; that needs real Docker.
"""
import json
import os
import signal
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
STATE = Path(os.environ.get('FAKE_DOCKER_STATE', '/tmp/fake-docker'))
VALUED = {'--name', '--network', '--tmpfs', '--env', '-e', '--cap-drop', '--security-opt', '--cpus', '--memory',
          '--pids-limit', '--workdir', '--entrypoint', '--mount', '--pull'}


def translate(text: str, mounts: dict) -> str:
    for target, source in sorted(mounts.items(), key=lambda kv: -len(kv[0])):
        text = text.replace(target, source)
    import re
    return re.sub(r'hack-mock-[0-9a-f]+', '127.0.0.1', text)


def run(args):
    opts, env_items, mounts = {}, [], {'/app': str(ROOT)}
    detach = False
    i = 0
    while i < len(args) and args[i].startswith('-'):
        flag = args[i]
        if flag in ('-d', '--detach'):
            detach = True
        elif flag in VALUED:
            value = args[i + 1]
            i += 1
            if flag in ('--env', '-e'):
                env_items.append(value)
            elif flag == '--mount':
                parts = dict(p.split('=', 1) for p in value.split(',') if '=' in p)
                mounts[parts['target']] = parts['source']
            else:
                opts[flag] = value
        i += 1
    image, command = args[i], args[i + 1:]
    env = dict(os.environ)
    for item in env_items:
        key, eq, value = item.partition('=')
        if eq:
            env[key] = translate(value, mounts)
    if env.get('HOME') == '/tmp':
        env['HOME'] = str(STATE)
    env['PYTHONPATH'] = str(ROOT)
    argv = [sys.executable] + [translate(a, mounts) for a in command]
    cwd = translate(opts.get('--workdir', '/app'), mounts)
    STATE.mkdir(parents=True, exist_ok=True)
    name = opts.get('--name')
    if detach:
        proc = subprocess.Popen(argv, cwd=cwd, env=env, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                                start_new_session=True)
        if name:
            (STATE / f'{name}.pid').write_text(str(proc.pid))
        print(name or proc.pid)
        return 0
    proc = subprocess.Popen(argv, cwd=cwd, env=env)
    if name:
        (STATE / f'{name}.pid').write_text(str(proc.pid))
    code = proc.wait()
    if name:
        (STATE / f'{name}.pid').unlink(missing_ok=True)
    return 137 if code == -signal.SIGKILL else code


def kill(name):
    pid_file = STATE / f'{name}.pid'
    if pid_file.is_file():
        try:
            os.kill(int(pid_file.read_text()), signal.SIGKILL)
        except ProcessLookupError:
            pass
        pid_file.unlink(missing_ok=True)
    return 0


def main(args):
    if args[:2] == ['image', 'inspect']:
        print(json.dumps([{'Id': 'sha256:fake-' + args[2]}]))
        return 0
    if args[:1] == ['network']:
        return 0
    if args[:1] == ['run']:
        return run(args[1:])
    if args[:1] == ['kill']:
        return kill(args[1])
    if args[:2] == ['rm', '-f']:
        return kill(args[2])
    print('fake docker: unsupported ' + ' '.join(args), file=sys.stderr)
    return 1


if __name__ == '__main__':
    sys.exit(main(sys.argv[1:]))
