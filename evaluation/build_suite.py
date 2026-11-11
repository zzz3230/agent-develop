"""Training suite v2: 20 templates (4 types), 20% clearly impossible, dev/holdout split.

Host-only: references and private tests never go into the agent's task directory or image.

    # the hand-made set: one instance per template, written to OUT/dev and OUT/holdout
    python -m evaluation.build_suite base --output OUT
    # fast generator for load tests (dev templates only by default)
    python -m evaluation.build_suite load --output OUT --count 100 --seed 7
    # independent grading of answer.txt files written by run_agent.py
    python -m evaluation.grade_suite --suite OUT/dev --run TASKS_COPY

Rewards are drawn from a separate RNG (1..10) and never depend on template or difficulty.
Holdout templates are for the final measurement only: do not tune prompts, limits or the
queue on them. `load --split holdout` refuses unless --allow-holdout is given.
"""
from __future__ import annotations

import argparse
import bisect
import csv
import hashlib
import heapq
import io
import json
import math
import random
import re
import shutil
import subprocess
import sys
from collections import deque
from dataclasses import dataclass
from datetime import date, timedelta
from decimal import Decimal, ROUND_HALF_UP
from pathlib import Path
from typing import Callable

TAIL_ANSWER = (' Work only inside the current directory. If the provided information cannot determine '
               'the answer, write IMPOSSIBLE instead. When you are done, write ONLY the final answer to '
               'the file answer.txt in the current directory (for example with bash: echo 42 > answer.txt).')
TAIL_CODE = (' Work only inside the current directory. Do not edit the tests. If the requirements are '
             'contradictory, write IMPOSSIBLE instead. When you are done, write ONLY the word DONE to the '
             'file answer.txt in the current directory (for example with bash: echo 42 > answer.txt).')


@dataclass(frozen=True)
class Template:
    name: str
    kind: str
    split: str          # dev | holdout
    solvable: bool
    build: Callable     # (rng, workspace) -> dict(prompt, expected, check, [private, reference, reason])


def write_csv(path, header, rows):
    with path.open('w', encoding='utf-8', newline='') as stream:
        writer = csv.writer(stream)
        writer.writerow(header)
        writer.writerows(rows)


def half_up(value: Decimal) -> int:
    return int(value.quantize(Decimal('1'), rounding=ROUND_HALF_UP))


# ----------------------------------------------------------------- math
def math_loan(rng, ws):
    principal = rng.randint(500_000, 3_000_000)
    rate = Decimal(rng.randint(35, 149)) / 10          # annual percent, e.g. 7.3
    payment = rng.randint(principal // 30, principal // 12)
    balance, total_interest, months = principal, 0, 0
    while balance > 0:
        interest = half_up(Decimal(balance) * rate / Decimal(1200))
        total_interest += interest
        balance += interest
        balance -= min(payment, balance)
        months += 1
    prompt = (f'A loan of {principal} cents has a nominal annual rate of {rate}% charged monthly. '
              f'Each month first add interest equal to balance*{rate}/1200 rounded HALF_UP to whole cents, '
              f'then pay {payment} cents, or the whole remaining balance if it is smaller. '
              'Repeat until the balance is zero. Return the total interest charged in cents as an integer. '
              'Compute it exactly with Python (decimal).')
    return dict(prompt=prompt, expected=str(total_interest), check='exact_int')


def math_divisible(rng, ws):
    n = rng.randint(10**9, 10**12)
    a, b, c = rng.sample([3, 4, 6, 7, 9, 10, 11, 12, 14, 15], 3)
    lcm = math.lcm
    union = n // a + n // b - n // lcm(a, b)
    with_c = n // lcm(a, c) + n // lcm(b, c) - n // lcm(a, b, c)
    small = 5000  # cross-check the formula by brute force on a prefix
    brute = sum(1 for k in range(1, small + 1) if (k % a == 0 or k % b == 0) and k % c)
    fu = small // a + small // b - small // lcm(a, b) - (small // lcm(a, c) + small // lcm(b, c) - small // lcm(a, b, c))
    assert brute == fu
    prompt = (f'How many integers k with 1 <= k <= {n} are divisible by {a} or by {b}, '
              f'but not divisible by {c}? Return the integer.')
    return dict(prompt=prompt, expected=str(union - with_c), check='exact_int')


def math_grid(rng, ws):
    size = rng.randint(14, 22)
    while True:
        grid = [['#' if rng.random() < 0.28 else '.' for _ in range(size)] for _ in range(size)]
        start, end = (0, rng.randrange(size)), (size - 1, rng.randrange(size))
        grid[start[0]][start[1]], grid[end[0]][end[1]] = 'S', 'E'
        dist = {start: 0}
        queue = deque([start])
        while queue:
            r, c = queue.popleft()
            for dr, dc in ((1, 0), (-1, 0), (0, 1), (0, -1)):
                nr, nc = r + dr, c + dc
                if 0 <= nr < size and 0 <= nc < size and grid[nr][nc] != '#' and (nr, nc) not in dist:
                    dist[nr, nc] = dist[r, c] + 1
                    queue.append((nr, nc))
        if end in dist and dist[end] > size:
            break
    (ws / 'grid.txt').write_text('\n'.join(''.join(row) for row in grid) + '\n', encoding='utf-8', newline='\n')
    prompt = ('grid.txt is a maze: S start, E exit, # wall, . open cell. Moves go up, down, left or right '
              'by one cell, never through walls or outside the grid. Return the minimum number of moves '
              'from S to E as an integer.')
    return dict(prompt=prompt, expected=str(dist[end]), check='exact_int')


def math_business_days(rng, ws):
    start = date(2026, 1, 1) + timedelta(days=rng.randrange(200))
    end = start + timedelta(days=rng.randint(60, 160))
    holidays = sorted({start + timedelta(days=rng.randrange((end - start).days + 1)) for _ in range(9)})
    (ws / 'holidays.txt').write_text('\n'.join(d.isoformat() for d in holidays) + '\n', encoding='utf-8', newline='\n')
    holiday_set = set(holidays)
    count = sum(1 for i in range((end - start).days + 1)
                if (d := start + timedelta(days=i)).weekday() < 5 and d not in holiday_set)
    prompt = (f'Count business days from {start} to {end}, both inclusive. A business day is Monday-Friday '
              'and not listed in holidays.txt (one ISO date per line; a holiday on a weekend changes nothing). '
              'Return the integer.')
    return dict(prompt=prompt, expected=str(count), check='exact_int')


def math_impossible(rng, ws):
    total = rng.randint(20, 400)
    prompt = (f'Two positive real numbers x and y satisfy x + y = {total}. No other relation between them '
              'is given. Return the exact value of x as an integer.')
    return dict(prompt=prompt, expected=None, check='exact_int', reason='underdetermined: one equation, two unknowns')


# ----------------------------------------------------------------- data analysis
def data_latency(rng, ws):
    endpoints = ['/api/orders', '/api/users', '/api/search', '/health']
    target = rng.choice(endpoints[:3])
    lines, values = [], []
    for i in range(rng.randint(900, 1600)):
        endpoint = rng.choice(endpoints)
        status = rng.choice([200, 200, 200, 201, 204, 301, 404, 500, 503])
        ms = None if rng.random() < 0.04 else rng.randint(3, 2500)
        lines.append(json.dumps({'ts': 1_780_000_000 + i * 7, 'endpoint': endpoint, 'status': status, 'ms': ms}))
        if endpoint == target and 200 <= status <= 299 and ms is not None:
            values.append(ms)
    values.sort()
    p95 = values[math.ceil(0.95 * len(values)) - 1]
    (ws / 'requests.jsonl').write_text('\n'.join(lines) + '\n', encoding='utf-8', newline='\n')
    prompt = (f'requests.jsonl has one JSON object per line with ts, endpoint, status, ms (ms may be null). '
              f'For endpoint {target} and statuses 200..299 only, ignoring null ms, return the nearest-rank '
              '95th percentile of ms: sort ascending and take the element at 1-based rank ceil(0.95*n). '
              'Return the integer.')
    return dict(prompt=prompt, expected=str(p95), check='exact_int')


def data_transfers(rng, ws):
    depts = ['ops', 'sales', 'rnd', 'legal', 'hr']
    target, as_of = rng.choice(depts), date(2026, 6, 1) + timedelta(days=rng.randrange(120))
    employees, transfers, terminations = [], [], []
    for i in range(rng.randint(120, 220)):
        hired = date(2023, 1, 1) + timedelta(days=rng.randrange(1300))
        employees.append((f'E{i:04}', f'Name{i}', rng.choice(depts), hired.isoformat()))
        day = hired
        for _ in range(rng.randint(0, 3)):
            day += timedelta(days=rng.randint(20, 300))
            transfers.append((f'E{i:04}', day.isoformat(), rng.choice(depts)))
        if rng.random() < 0.2:
            terminations.append((f'E{i:04}', (hired + timedelta(days=rng.randint(30, 1100))).isoformat()))
    rng.shuffle(transfers)
    ended = {e: date.fromisoformat(d) for e, d in terminations}
    count = 0
    for emp, _, dept, hired in employees:
        if date.fromisoformat(hired) > as_of or (emp in ended and ended[emp] <= as_of):
            continue
        moves = sorted((date.fromisoformat(d), new) for e, d, new in transfers if e == emp and date.fromisoformat(d) <= as_of)
        count += (moves[-1][1] if moves else dept) == target
    write_csv(ws / 'employees.csv', ['id', 'name', 'dept', 'hired'], employees)
    write_csv(ws / 'transfers.csv', ['emp_id', 'effective', 'new_dept'], transfers)
    write_csv(ws / 'terminations.csv', ['emp_id', 'date'], terminations)
    prompt = (f'How many employees were in department {target} on {as_of}? employees.csv gives the initial '
              'department and hire date (employees hired after that date do not count). transfers.csv moves an '
              'employee to new_dept from its effective date inclusive; the latest effective transfer on or '
              'before the date wins. An employee terminated on or before the date does not count. Return the integer.')
    return dict(prompt=prompt, expected=str(count), check='exact_int')


def normalize_email(raw):
    local, _, domain = raw.strip().lower().partition('@')
    local = local.split('+', 1)[0]
    if domain in ('gmail.com', 'googlemail.com'):
        local, domain = local.replace('.', ''), 'gmail.com'
    return f'{local}@{domain}'


def data_dedupe(rng, ws):
    people = [f'{rng.choice(["anna", "ivan", "li", "sara", "omar", "kim"])}{rng.randint(1, 90)}' for _ in range(160)]
    rows, unique = [], set()
    for i in range(rng.randint(300, 500)):
        base = rng.choice(people)
        domain = rng.choice(['gmail.com', 'googlemail.com', 'mail.ru', 'example.org'])
        local = base
        if rng.random() < 0.3:
            local = '.'.join([base[:2], base[2:]])
        if rng.random() < 0.3:
            local += f'+tag{rng.randint(1, 9)}'
        email = f'{" " if rng.random() < .2 else ""}{local.upper() if rng.random() < .2 else local}@{domain}'
        status = rng.choice(['active', 'active', 'inactive'])
        rows.append((i, email, status))
        if status == 'active':
            unique.add(normalize_email(email))
    write_csv(ws / 'customers.csv', ['row', 'email', 'status'], rows)
    prompt = ('customers.csv lists signups. Count distinct customers with status active after normalizing '
              'email: trim spaces and lowercase; drop everything from the first + in the local part; for '
              'gmail.com and googlemail.com additionally remove dots from the local part and treat both '
              'domains as gmail.com. Other domains keep dots. Return the integer.')
    return dict(prompt=prompt, expected=str(len(unique)), check='exact_int')


def data_growth(rng, ws):
    region = rng.choice(['north', 'south', 'east'])
    rows, totals = [], {}
    months = [(2025, m) for m in range(1, 13)] + [(2026, m) for m in range(1, 7)]
    skipped = rng.sample(months[1:-1], 2)
    for y, m in months:
        for _ in range(rng.randint(8, 30)):
            r = rng.choice(['north', 'south', 'east'])
            if r == region and (y, m) in skipped:
                continue
            amount = rng.randint(100, 90_000)
            rows.append((date(y, m, rng.randint(1, 28)).isoformat(), r, amount))
            if r == region:
                totals[(y, m)] = totals.get((y, m), 0) + amount
    rng.shuffle(rows)
    best, best_month = None, None
    for previous, current in zip(months, months[1:]):
        delta = totals.get(current, 0) - totals.get(previous, 0)
        if best is None or delta > best:
            best, best_month = delta, current
    write_csv(ws / 'sales.csv', ['date', 'region', 'amount_cents'], rows)
    prompt = (f'sales.csv covers 2025-01..2026-06. For region {region}, compute monthly totals (a month '
              'without rows is 0). For every month from 2025-02 to 2026-06, the increase is its total minus '
              'the previous calendar month total. Return the month with the largest increase as YYYY-MM; '
              'on ties return the earliest.')
    return dict(prompt=prompt, expected=f'{best_month[0]}-{best_month[1]:02}', check='exact_str')


def data_impossible(rng, ws):
    rows = [(i, rng.choice(['EUR', 'USD', 'GBP']), rng.randint(100, 9000)) for i in range(rng.randint(40, 90))]
    if not any(c == 'GBP' for _, c, _ in rows):
        rows[0] = (0, 'GBP', 1234)
    write_csv(ws / 'orders.csv', ['id', 'currency', 'amount_cents'], rows)
    write_csv(ws / 'rates.csv', ['currency', 'usd_per_unit'], [('EUR', '1.12'), ('USD', '1')])
    prompt = ('Return the exact total of orders.csv in USD cents, converting each order with rates.csv. '
              'rates.csv is the only allowed rate source; do not assume or look up any other rate.')
    return dict(prompt=prompt, expected=None, check='exact_int', reason='GBP rate is missing and required')


# ----------------------------------------------------------------- search
FEATURES = ['dark-mode', 'csv-export', 'sso-login', 'webhooks', 'audit-log', 'bulk-edit', 'api-keys']
NAMES = ['Alice Novak', 'Boris Chen', 'Chen Sato', 'Dana Petrov', 'Emil Haddad', 'Farah Kim',
         'Gleb Muller', 'Hana Ivanova', 'Igor Wang', 'Jana Smith', 'Karl Garcia', 'Lena Kowalski']


def search_changelog(rng, ws):
    kb = ws / 'kb'
    kb.mkdir()
    target = rng.choice(FEATURES)
    present, last_added = set(), {}
    versions = []
    major, minor = 1, 0
    for _ in range(rng.randint(9, 14)):
        minor += 1
        if rng.random() < 0.25:
            major, minor = major + 1, 0
        versions.append(f'{major}.{minor}.0')
    for v in versions:
        lines = [f'# Release {v}', '']
        for feature in rng.sample(FEATURES, 3):
            if feature in present and rng.random() < 0.5:
                present.discard(feature)
                lines.append(f'- Removed {feature}.')
            elif feature not in present:
                restored = feature in last_added
                present.add(feature)
                last_added[feature] = v
                lines.append(f'- {"Restored" if restored else "Added"} {feature}.')
            else:
                lines.append(f'- Improved {feature} performance.')
        (kb / f'release_{v.replace(".", "_")}.md').write_text('\n'.join(lines) + '\n', encoding='utf-8', newline='\n')
    if target not in last_added:
        target = sorted(last_added)[0]
    # Withdrawn release: its notes must be ignored.
    fake = f'{major}.{minor}.1'
    (kb / f'release_{fake.replace(".", "_")}.md').write_text(
        f'# Release {fake}\n\nStatus: WITHDRAWN, never shipped; ignore these notes.\n- Added {target}.\n', encoding='utf-8', newline='\n')
    prompt = (f'kb/ contains release notes. In which shipped version was {target} most recently added or '
              'restored? Withdrawn releases never shipped. Return only the version, e.g. 3.1.0.')
    return dict(prompt=prompt, expected=last_added[target], check='exact_str')


def search_actions(rng, ws):
    kb = ws / 'kb'
    kb.mkdir()
    people = rng.sample(NAMES, 6)
    items = {f'AI-{n}': {'owner': rng.choice(people), 'closed_by_owner': None} for n in rng.sample(range(10, 60), 6)}
    target = rng.choice(sorted(items))
    day = date(2026, 1, 5)
    for meeting in range(8):
        lines = [f'# Weekly sync {day}', '', 'Action items:']
        for key, item in items.items():
            if item['closed_by_owner'] is not None:
                continue
            if meeting == 0:
                lines.append(f'- {key}: owner {item["owner"]}.')
            elif rng.random() < 0.35:
                new = rng.choice([p for p in people if p != item['owner']])
                lines.append(f'- {key} reassigned from {item["owner"]} to {new}.')
                item['owner'] = new
            elif meeting >= 3 and rng.random() < 0.3:
                lines.append(f'- {key} closed.')
                item['closed_by_owner'] = item['owner']
        (kb / f'minutes_{day}.md').write_text('\n'.join(lines) + '\n', encoding='utf-8', newline='\n')
        day += timedelta(days=7)
    if items[target]['closed_by_owner'] is None:
        lines = [f'# Weekly sync {day}', '', 'Action items:', f'- {target} closed.']
        (kb / f'minutes_{day}.md').write_text('\n'.join(lines) + '\n', encoding='utf-8', newline='\n')
        items[target]['closed_by_owner'] = items[target]['owner']
    prompt = (f'kb/ holds weekly meeting minutes (file names carry dates). Who owned action item {target} '
              'when it was closed? Follow reassignments in date order. Return only the full name.')
    return dict(prompt=prompt, expected=items[target]['closed_by_owner'], check='exact_str')


def search_org(rng, ws):
    as_of = date(2026, 5, 1) + timedelta(days=rng.randrange(90))
    while True:
        people = rng.sample(NAMES, 10)
        history = {}
        for i, person in enumerate(people):
            records, start = [], date(2024, 1, 1)
            if i:
                for _ in range(rng.randint(1, 3)):
                    records.append((start, rng.choice(people[:i])))
                    start += timedelta(days=rng.randint(120, 500))
            history[person] = records

        def manager(person):
            valid = [m for d, m in history[person] if d <= as_of]
            return valid[-1] if valid else None
        candidates = [p for p in people if manager(p) and manager(manager(p))]
        if candidates:
            break
    kb = ws / 'kb' / 'people'
    kb.mkdir(parents=True)
    for person, records in history.items():
        lines = [f'- From {d}: manager {m}.' for d, m in records] or ['- Reports to the board; no manager.']
        rng.shuffle(lines)
        (kb / f"{person.lower().replace(' ', '_')}.md").write_text(f'# {person}\n\n' + '\n'.join(lines) + '\n', encoding='utf-8', newline='\n')
    target = rng.choice(candidates)
    prompt = (f'kb/people/ has one file per employee with dated manager records. As of {as_of}, who is the '
              f"skip-level manager (the manager's manager) of {target}? The latest record dated on or before "
              'that day applies at each level. Return only the full name.')
    return dict(prompt=prompt, expected=manager(manager(target)), check='exact_str')


def search_sku(rng, ws):
    kb = ws / 'kb'
    kb.mkdir()
    warehouses = ['W1', 'W2', 'W3', 'W4', 'W5', 'W6']
    skus = [f'SKU-{n}' for n in rng.sample(range(100, 999), 5)]
    target = rng.choice(skus)
    as_of = date(2026, 9, 1)
    location = {s: rng.choice(warehouses) for s in skus}
    (kb / 'initial_stock.md').write_text('# Stock on 2026-01-01\n' + ''.join(f'- {s} at {w}\n' for s, w in location.items()), encoding='utf-8', newline='\n')
    current = dict(location)
    day = date(2026, 1, 10)
    for number in range(1, 15):
        sku = rng.choice(skus)
        new = rng.choice([w for w in warehouses if w != current[sku]])
        cancelled = rng.random() < 0.25
        text = f'# Transfer T{number:03}\nDate: {day}\nItem: {sku}\nFrom: {current[sku]}\nTo: {new}\n'
        (kb / f'transfer_T{number:03}.md').write_text(text, encoding='utf-8', newline='\n')
        if cancelled:
            (kb / f'cancellation_T{number:03}.md').write_text(f'Transfer T{number:03} was cancelled before shipping; the item stayed put.\n', encoding='utf-8', newline='\n')
        elif day <= as_of:
            current[sku] = new
        day += timedelta(days=rng.randint(10, 30))
    prompt = (f'kb/ holds the initial stock list, transfer notes and cancellations. Where was {target} stored '
              f'on {as_of}? Cancelled transfers never happened; transfers dated after that day do not count. '
              'Return only the warehouse code.')
    return dict(prompt=prompt, expected=current[target], check='exact_str')


def search_impossible(rng, ws):
    kb = ws / 'kb'
    kb.mkdir()
    person = rng.choice(NAMES)
    (kb / f'{person.lower().replace(" ", "_")}.md').write_text(
        f'# {person}\n- Role: analyst\n- Office: Riga\n- Birth city: not recorded (privacy request).\n', encoding='utf-8', newline='\n')
    for other in rng.sample([n for n in NAMES if n != person], 4):
        (kb / f'{other.lower().replace(" ", "_")}.md').write_text(f'# {other}\n- Birth city: {rng.choice(["Oslo", "Porto", "Graz"])}\n', encoding='utf-8', newline='\n')
    prompt = f'Using only kb/, what is the birth city of {person}? Return only the city name.'
    return dict(prompt=prompt, expected=None, check='exact_str', reason='birth city explicitly not recorded')


# ----------------------------------------------------------------- coding
def coding_files(ws, buggy, visible, private, reference):
    (ws / 'solution.py').write_text(buggy, encoding='utf-8', newline='\n')
    (ws / 'test_solution.py').write_text(visible, encoding='utf-8', newline='\n')
    return dict(check='unittest', expected='tests_pass', private=private, reference=reference)


def unit(name, body):
    return (f'import unittest\nimport solution as m\n\n\nclass {name}(unittest.TestCase):\n'
            f'    def test_behavior(self):\n{body}\n\n\nif __name__ == "__main__":\n    unittest.main()\n')


SEMVER_REF = '''import re

_RE = re.compile(r"^(0|[1-9]\\d*)\\.(0|[1-9]\\d*)\\.(0|[1-9]\\d*)"
                 r"(?:-((?:0|[1-9]\\d*|\\d*[A-Za-z-][0-9A-Za-z-]*)(?:\\.(?:0|[1-9]\\d*|\\d*[A-Za-z-][0-9A-Za-z-]*))*))?"
                 r"(?:\\+([0-9A-Za-z-]+(?:\\.[0-9A-Za-z-]+)*))?$")


def _parse(text):
    if not isinstance(text, str):
        raise ValueError("version")
    match = _RE.match(text)
    if not match:
        raise ValueError("version")
    core = tuple(int(x) for x in match.group(1, 2, 3))
    pre = match.group(4)
    return core, pre.split(".") if pre else None


def _key(ident):
    return (0, int(ident), "") if ident.isdigit() else (1, 0, ident)


def compare(a, b):
    (ca, pa), (cb, pb) = _parse(a), _parse(b)
    if ca != cb:
        return -1 if ca < cb else 1
    if pa == pb:
        return 0
    if pa is None:
        return 1
    if pb is None:
        return -1
    ka, kb = [_key(x) for x in pa], [_key(x) for x in pb]
    return -1 if ka < kb else 1 if ka > kb else 0
'''


def coding_semver(rng, ws):
    buggy = 'def compare(a, b):\n    return (a > b) - (a < b)\n'
    ns = {}
    exec(SEMVER_REF, ns)
    chain = ['1.0.0-alpha', '1.0.0-alpha.1', '1.0.0-alpha.beta', '1.0.0-beta', '1.0.0-beta.2',
             '1.0.0-beta.11', '1.0.0-rc.1', '1.0.0', '1.0.1', '1.2.0', '1.10.0', '2.0.0']
    cases = []
    for _ in range(60):
        a = f'{rng.randint(0, 12)}.{rng.randint(0, 12)}.{rng.randint(0, 12)}' + rng.choice(['', '-rc.1', '-alpha', '-2', '-x.7'])
        b = f'{rng.randint(0, 12)}.{rng.randint(0, 12)}.{rng.randint(0, 12)}' + rng.choice(['', '-rc.10', '-beta', '-11'])
        if rng.random() < 0.2:
            b = a + '+build.5'
        cases.append((a, b, ns['compare'](a, b)))
    visible = unit('T', "        self.assertEqual(m.compare('1.10.0', '1.9.0'), 1)\n"
                        "        self.assertEqual(m.compare('1.0.0-alpha', '1.0.0'), -1)\n"
                        "        self.assertEqual(m.compare('1.0.0+build.1', '1.0.0'), 0)")
    private = unit('Hidden', f"        chain = {chain!r}\n"
                             "        for i, a in enumerate(chain):\n"
                             "            for j, b in enumerate(chain):\n"
                             "                self.assertEqual(m.compare(a, b), (i > j) - (i < j), (a, b))\n"
                             f"        for a, b, want in {cases!r}:\n"
                             "            self.assertEqual(m.compare(a, b), want, (a, b))\n"
                             "        for bad in ['1.0', '01.0.0', '1.0.0-', '1.0.0-01', 'v1.0.0', '', '1.0.0+']:\n"
                             "            with self.assertRaises(ValueError):\n"
                             "                m.compare(bad, '1.0.0')")
    out = coding_files(ws, buggy, visible, private, SEMVER_REF)
    out['prompt'] = ('Fix solution.py: compare(a, b) returns -1, 0 or 1 by Semantic Versioning 2.0.0 '
                     'precedence: numeric MAJOR.MINOR.PATCH, a pre-release is lower than the release, '
                     'pre-release identifiers compare numerically if digits-only, otherwise ASCII, numeric '
                     'lower than alphanumeric, a longer list wins when all previous are equal; build metadata '
                     'is ignored. Invalid versions (including leading zeros) raise ValueError. '
                     'Run `python3 test_solution.py`.')
    return out


DURATION_REF = '''import re

_RE = re.compile(r"(?:(\\d+)d)?(?:(\\d+)h)?(?:(\\d+)m)?(?:(\\d+)s)?")


def parse_duration(text):
    if not isinstance(text, str) or not text:
        raise ValueError("duration")
    match = _RE.fullmatch(text)
    if not match or not any(match.groups()):
        raise ValueError("duration")
    d, h, m, s = (int(x) if x else 0 for x in match.groups())
    return ((d * 24 + h) * 60 + m) * 60 + s
'''


def coding_duration(rng, ws):
    buggy = ('import re\n\n\ndef parse_duration(text):\n    total = 0\n'
             '    for value, unit in re.findall(r"(\\d+)([hms])", text):\n'
             '        total += int(value) * {"h": 360, "m": 60, "s": 1}[unit]\n    return total\n')
    ns = {}
    exec(DURATION_REF, ns)
    cases = []
    for _ in range(60):
        parts = [(u, rng.randint(0, 99)) for u in 'dhms' if rng.random() < 0.6] or [('s', 5)]
        text = ''.join(f'{v}{u}' for u, v in parts)
        cases.append((text, ns['parse_duration'](text)))
    visible = unit('T', "        self.assertEqual(m.parse_duration('1h30m'), 5400)\n"
                        "        self.assertEqual(m.parse_duration('2d'), 172800)\n"
                        "        with self.assertRaises(ValueError):\n            m.parse_duration('')")
    private = unit('Hidden', f"        for text, want in {cases!r}:\n"
                             "            self.assertEqual(m.parse_duration(text), want, text)\n"
                             "        for bad in ['1m1h', '1h 2m', '5', 'h', '1x', '-1s', '1h1h', '1.5h', ' 1s']:\n"
                             "            with self.assertRaises(ValueError):\n"
                             "                m.parse_duration(bad)")
    out = coding_files(ws, buggy, visible, private, DURATION_REF)
    out['prompt'] = ('Fix solution.py: parse_duration(text) converts strings like "2d4h30m15s" to integer '
                     'seconds. Units d, h, m, s each appear at most once, in exactly that order, each with a '
                     'non-negative integer; at least one unit is required. Anything else (empty string, '
                     'spaces, wrong order, repeats, fractions, signs, unknown units) raises ValueError. '
                     'Run `python3 test_solution.py`.')
    return out


TOPO_REF = '''import heapq


def order(tasks):
    for name, deps in tasks.items():
        for dep in deps:
            if dep not in tasks:
                raise ValueError("unknown dependency")
    indegree = {name: len(set(deps)) for name, deps in tasks.items()}
    users = {name: [] for name in tasks}
    for name, deps in tasks.items():
        for dep in set(deps):
            users[dep].append(name)
    ready = [name for name, n in indegree.items() if n == 0]
    heapq.heapify(ready)
    result = []
    while ready:
        name = heapq.heappop(ready)
        result.append(name)
        for user in users[name]:
            indegree[user] -= 1
            if indegree[user] == 0:
                heapq.heappush(ready, user)
    if len(result) != len(tasks):
        raise ValueError("cycle")
    return result
'''


def coding_topo(rng, ws):
    buggy = ('def order(tasks):\n    seen, out = set(), []\n    def visit(n):\n        if n in seen:\n            return\n'
             '        seen.add(n)\n        for d in tasks.get(n, []):\n            visit(d)\n        out.append(n)\n'
             '    for n in tasks:\n        visit(n)\n    return out\n')
    ns = {}
    exec(TOPO_REF, ns)
    cases = []
    for _ in range(25):
        names = rng.sample([f'{c}{i}' for c in 'abcxyz' for i in range(4)], rng.randint(4, 12))
        graph = {n: rng.sample(names[:i], min(i, rng.randint(0, 3))) for i, n in enumerate(names)}
        graph = dict(rng.sample(list(graph.items()), len(graph)))
        cases.append((graph, ns['order'](graph)))
    visible = unit('T', "        self.assertEqual(m.order({'b': ['a'], 'a': [], 'c': ['a']}), ['a', 'b', 'c'])\n"
                        "        with self.assertRaises(ValueError):\n            m.order({'a': ['b'], 'b': ['a']})")
    private = unit('Hidden', f"        for graph, want in {cases!r}:\n"
                             "            self.assertEqual(m.order(graph), want)\n"
                             "        with self.assertRaises(ValueError):\n            m.order({'a': ['zz']})\n"
                             "        with self.assertRaises(ValueError):\n            m.order({'a': ['c'], 'b': ['a'], 'c': ['b'], 'd': []})\n"
                             "        self.assertEqual(m.order({'b': ['a', 'a'], 'a': []}), ['a', 'b'])")
    out = coding_files(ws, buggy, visible, private, TOPO_REF)
    out['prompt'] = ('Fix solution.py: order(tasks) takes a dict name -> list of dependency names and returns '
                     'all names in a dependency-respecting order; among valid orders return the '
                     'lexicographically smallest (always pick the smallest available name). Duplicate '
                     'dependencies are allowed. Raise ValueError for an unknown dependency or a cycle. '
                     'Run `python3 test_solution.py`.')
    return out


ROMAN_REF = '''_PAIRS = [(1000, "M"), (900, "CM"), (500, "D"), (400, "CD"), (100, "C"), (90, "XC"),
          (50, "L"), (40, "XL"), (10, "X"), (9, "IX"), (5, "V"), (4, "IV"), (1, "I")]


def to_roman(n):
    if type(n) is not int or not 1 <= n <= 3999:
        raise ValueError("range")
    out = []
    for value, letters in _PAIRS:
        while n >= value:
            out.append(letters)
            n -= value
    return "".join(out)


_CANON = {to_roman(n): n for n in range(1, 4000)}


def from_roman(text):
    if not isinstance(text, str) or text not in _CANON:
        raise ValueError("roman")
    return _CANON[text]
'''


def coding_roman(rng, ws):
    buggy = ('_V = {"I": 1, "V": 5, "X": 10, "L": 50, "C": 100, "D": 500, "M": 1000}\n\n\n'
             'def to_roman(n):\n    out = ""\n    for value, letters in [(1000, "M"), (500, "D"), (100, "C"), (50, "L"), (10, "X"), (5, "V"), (1, "I")]:\n'
             '        while n >= value:\n            out += letters\n            n -= value\n    return out\n\n\n'
             'def from_roman(text):\n    return sum(_V[c] for c in text.upper())\n')
    numbers = rng.sample(range(1, 4000), 80)
    ns = {}
    exec(ROMAN_REF, ns)
    pairs = [(n, ns['to_roman'](n)) for n in numbers]
    visible = unit('T', "        self.assertEqual(m.to_roman(1994), 'MCMXCIV')\n"
                        "        self.assertEqual(m.from_roman('XLII'), 42)\n"
                        "        with self.assertRaises(ValueError):\n            m.from_roman('IIII')")
    private = unit('Hidden', f"        for n, text in {pairs!r}:\n"
                             "            self.assertEqual(m.to_roman(n), text)\n"
                             "            self.assertEqual(m.from_roman(text), n)\n"
                             "        for bad in ['', 'IC', 'VX', 'IIII', 'xlii', 'MMMM', 'IVI', 'LL', 'A']:\n"
                             "            with self.assertRaises(ValueError):\n                m.from_roman(bad)\n"
                             "        for bad in [0, 4000, -1, 2.0, True]:\n"
                             "            with self.assertRaises(ValueError):\n                m.to_roman(bad)")
    out = coding_files(ws, buggy, visible, private, ROMAN_REF)
    out['prompt'] = ('Fix solution.py: to_roman(n) converts an int 1..3999 to canonical Roman numerals '
                     '(subtractive forms IV, IX, XL, XC, CD, CM); other values, including bool and float, raise '
                     'ValueError. from_roman(text) accepts only canonical uppercase numerals for 1..3999 and '
                     'returns the int; anything else (e.g. IIII, IC, lowercase, empty) raises ValueError. '
                     'Run `python3 test_solution.py`.')
    return out


def coding_impossible(rng, ws):
    k = rng.choice([2, 3, 5, 6, 7, 8])
    (ws / 'solution.py').write_text('def exact_root(n):\n    return 0\n', encoding='utf-8', newline='\n')
    (ws / 'test_solution.py').write_text(unit('T', f"        r = m.exact_root({k})\n"
                                                     "        self.assertIs(type(r), int)\n"
                                                     f"        self.assertEqual(r * r, {k})"), encoding='utf-8', newline='\n')
    prompt = (f'Fix solution.py so that `python3 test_solution.py` passes: exact_root(n) must return an '
              f'ordinary int r (type exactly int) with r*r == n, and the test calls exact_root({k}). '
              'Do not modify tests, builtins or the interpreter.')
    return dict(prompt=prompt, expected=None, check='unittest', reason=f'no integer squares to {k}')


TEMPLATES = [
    Template('math_loan', 'math', 'dev', True, math_loan),
    Template('math_divisible', 'math', 'dev', True, math_divisible),
    Template('math_grid', 'math', 'holdout', True, math_grid),
    Template('math_business_days', 'math', 'holdout', True, math_business_days),
    Template('math_underdetermined', 'math', 'dev', False, math_impossible),
    Template('data_latency', 'data_analysis', 'dev', True, data_latency),
    Template('data_transfers', 'data_analysis', 'dev', True, data_transfers),
    Template('data_dedupe', 'data_analysis', 'holdout', True, data_dedupe),
    Template('data_growth', 'data_analysis', 'holdout', True, data_growth),
    Template('data_missing_rate', 'data_analysis', 'holdout', False, data_impossible),
    Template('search_changelog', 'search', 'dev', True, search_changelog),
    Template('search_actions', 'search', 'dev', True, search_actions),
    Template('search_org', 'search', 'holdout', True, search_org),
    Template('search_sku', 'search', 'holdout', True, search_sku),
    Template('search_not_recorded', 'search', 'dev', False, search_impossible),
    Template('coding_semver', 'coding', 'dev', True, coding_semver),
    Template('coding_duration', 'coding', 'dev', True, coding_duration),
    Template('coding_topo', 'coding', 'holdout', True, coding_topo),
    Template('coding_roman', 'coding', 'holdout', True, coding_roman),
    Template('coding_contradiction', 'coding', 'holdout', False, coding_impossible),
]


def verify_coding(spec, ws):
    """Reference passes visible+private tests; the shipped buggy code fails the visible test."""
    import tempfile
    with tempfile.TemporaryDirectory() as temp:
        temp = Path(temp)
        shutil.copy2(ws / 'test_solution.py', temp / 'test_solution.py')
        (temp / 'solution.py').write_text(spec['reference'], encoding='utf-8', newline='\n')
        (temp / 'test_private.py').write_text(spec['private'], encoding='utf-8', newline='\n')
        done = subprocess.run([sys.executable, '-B', '-m', 'unittest', 'discover', '-q'], cwd=temp, capture_output=True, text=True)
        if done.returncode:
            raise ValueError('reference fails: ' + done.stderr[-1500:])
        shutil.copy2(ws / 'solution.py', temp / 'solution.py')
        done = subprocess.run([sys.executable, '-B', 'test_solution.py'], cwd=temp, capture_output=True, text=True)
        if done.returncode == 0:
            raise ValueError('buggy solution already passes the visible tests')


def emit(output: Path, template: Template, task_id: str, seed: int, reward: int) -> dict:
    rng = random.Random(seed)
    reference_dir = output / 'references' / task_id
    workspace = output / 'input' / task_id / 'workspace'
    workspace.mkdir(parents=True)
    spec = template.build(rng, workspace)
    if template.kind == 'coding' and template.solvable:
        verify_coding(spec, workspace)
    if not any(workspace.iterdir()):
        (workspace / '.gitkeep').write_text('')
    tail = TAIL_CODE if template.kind == 'coding' else TAIL_ANSWER
    public = dict(task_id=task_id, task_type=template.kind, instruction=spec['prompt'] + tail,
                  reward=reward, check=spec['check'])
    (output / 'input' / task_id / 'task.json').write_text(json.dumps(public, ensure_ascii=False, indent=2), encoding='utf-8', newline='\n')
    reference_dir.mkdir(parents=True)
    shutil.copytree(workspace, reference_dir / 'workspace')
    (reference_dir / 'task.json').write_text(json.dumps({**public, 'expected': spec['expected']}, ensure_ascii=False, indent=2), encoding='utf-8', newline='\n')
    if 'private' in spec:
        (reference_dir / 'test_private.py').write_text(spec['private'], encoding='utf-8', newline='\n')
        (reference_dir / 'reference_solution.py').write_text(spec['reference'], encoding='utf-8', newline='\n')
    return dict(id=task_id, type=template.kind, template=template.name, split=template.split,
                solvable=template.solvable, reward=reward, seed=seed, expected=spec['expected'],
                check=spec['check'], reason=spec.get('reason'))


def finish(output: Path, rows: list, meta: dict) -> None:
    digest = hashlib.sha256()
    for path in sorted((output / 'input').rglob('*')):
        if path.is_file():
            digest.update(str(path.relative_to(output / 'input')).encode())
            digest.update(path.read_bytes())
    manifest = dict(meta, input_sha256=digest.hexdigest(), tasks=rows,
                    impossible_share=round(sum(not r['solvable'] for r in rows) / len(rows), 3))
    (output / 'manifest.json').write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding='utf-8', newline='\n')
    print(f'{output}: {len(rows)} tasks, impossible {manifest["impossible_share"]:.0%}, sha256 {digest.hexdigest()[:16]}')


def fresh(output: Path) -> None:
    if output.exists() and any(output.iterdir()):
        raise SystemExit(f'{output} is not empty; suites are frozen once written')
    output.mkdir(parents=True, exist_ok=True)


def build_base(output: Path, seed: int) -> None:
    rewards = random.Random(seed + 991)
    for split in ('dev', 'holdout'):
        target = output / split
        fresh(target)
        rows = []
        counters: dict[str, int] = {}
        for template in [t for t in TEMPLATES if t.split == split]:
            reward = rewards.randint(1, 10)
            number = counters.get(template.kind, 0)
            counters[template.kind] = number + 1
            task_seed = int(hashlib.sha256(f'{seed}:{template.name}'.encode()).hexdigest()[:8], 16)
            rows.append(emit(target, template, f'{template.kind}_{number:04}', task_seed, reward))
        finish(target, rows, dict(kind='base', split=split, seed=seed))


def build_load(output: Path, count: int, seed: int, split: str, impossible_share: float) -> None:
    fresh(output)
    pool = [t for t in TEMPLATES if split == 'all' or t.split == split]
    solvable = [t for t in pool if t.solvable]
    impossible = [t for t in pool if not t.solvable]
    rng, rewards = random.Random(seed), random.Random(seed + 991)
    n_impossible = round(count * impossible_share) if impossible else 0
    plan = [rng.choice(impossible) for _ in range(n_impossible)] + [solvable[i % len(solvable)] for i in range(count - n_impossible)]
    rng.shuffle(plan)
    counters: dict[str, int] = {}
    rows = []
    for template in plan:
        number = counters.get(template.kind, 0)
        counters[template.kind] = number + 1
        rows.append(emit(output, template, f'{template.kind}_{number:04}', rng.getrandbits(32), rewards.randint(1, 10)))
    finish(output, rows, dict(kind='load', split=split, seed=seed, count=count))


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = parser.add_subparsers(dest='mode', required=True)
    base = sub.add_parser('base')
    base.add_argument('--output', type=Path, required=True)
    base.add_argument('--seed', type=int, default=20261111)
    load = sub.add_parser('load')
    load.add_argument('--output', type=Path, required=True)
    load.add_argument('--count', type=int, default=100)
    load.add_argument('--seed', type=int, default=7)
    load.add_argument('--split', choices=['dev', 'holdout', 'all'], default='dev')
    load.add_argument('--impossible-share', type=float, default=0.2)
    load.add_argument('--allow-holdout', action='store_true')
    args = parser.parse_args()
    if args.mode == 'base':
        build_base(args.output, args.seed)
    else:
        if args.split != 'dev' and not args.allow_holdout:
            raise SystemExit('holdout templates are for the final measurement; pass --allow-holdout explicitly')
        build_load(args.output, args.count, args.seed, args.split, args.impossible_share)


if __name__ == '__main__':
    main()
