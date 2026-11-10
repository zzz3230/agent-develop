"""Load workspace CSVs as text-only SQLite tables; execute one scalar SELECT."""
from __future__ import annotations

import argparse
import csv
import json
import math
import sqlite3
from decimal import Decimal, ROUND_HALF_UP
from pathlib import Path

RESULT_PREFIX = 'OJ_SQL_SCALAR_JSON='


def decimal_value(value):
    number = Decimal(str(value))
    if not number.is_finite():
        raise ValueError('nonfinite decimal')
    return number


def multiply(*values):
    result = Decimal(1)
    for value in values:
        result *= decimal_value(value)
    return str(result)


def quoted(name: str) -> str:
    return '"' + name.replace('"', '""') + '"'


def connect(root: Path):
    db = sqlite3.connect(':memory:')
    metadata = []
    for path in sorted(root.rglob('*.csv')):
        name = path.relative_to(root).as_posix()[:-4].replace('/', '__')
        with path.open(encoding='utf-8-sig', newline='') as stream:
            reader = csv.reader(stream)
            columns = next(reader, [])
            if not columns or len(set(c.casefold() for c in columns)) != len(columns) or not all(columns):
                raise ValueError(f'Unsupported empty/duplicate CSV header: {path.name}')
            rows = list(reader)
        if any(len(row) != len(columns) for row in rows):
            raise ValueError(f'Ragged CSV rows: {path.name}; use Python fallback')
        db.execute(f'CREATE TABLE {quoted(name)} ({", ".join(quoted(c)+" TEXT" for c in columns)})')
        db.executemany(f'INSERT INTO {quoted(name)} VALUES ({",".join("?" for _ in columns)})', rows)
        values = {}
        for index, column in enumerate(columns):
            distinct = sorted({row[index] for row in rows})
            if len(distinct) <= 12 and all(len(v) <= 48 for v in distinct):
                values[column] = distinct
        metadata.append({'table': name, 'columns': columns, 'rows': len(rows),
                         'sample': rows[:2], 'small_distinct': values})
    if not metadata:
        raise ValueError('No CSV files; use the regular agent')
    db.create_function('DEC_MUL', -1, multiply)
    db.create_function('DEC_SUB', 2, lambda a, b: str(decimal_value(a) - decimal_value(b)))
    db.create_function('CENTS', 1, lambda value: int(decimal_value(value).quantize(Decimal('.01'), rounding=ROUND_HALF_UP) * 100))
    # The query sees only an in-memory database, built before authorizing SQL.
    allowed = {sqlite3.SQLITE_SELECT, sqlite3.SQLITE_READ, sqlite3.SQLITE_FUNCTION, sqlite3.SQLITE_RECURSIVE}
    db.set_authorizer(lambda action, *_: sqlite3.SQLITE_OK if action in allowed else sqlite3.SQLITE_DENY)
    remaining = [2000]
    def progress():
        remaining[0] -= 1
        return remaining[0] <= 0
    db.set_progress_handler(progress, 1000)
    return db, metadata


def describe(root: Path) -> str:
    db, schema = connect(root)
    db.close()
    return json.dumps(schema, ensure_ascii=False, separators=(',', ':'))


def scalar(root: Path, query: str):
    db, _ = connect(root)
    try:
        cursor = db.execute(query)
        rows = cursor.fetchmany(2)
        if len(cursor.description or []) != 1 or len(rows) != 1 or rows[0][0] is None:
            raise ValueError('Expected exactly one non-NULL cell; repair SQL or use Python')
        value = rows[0][0]
        if isinstance(value, float):
            if not math.isfinite(value):
                raise ValueError('Nonfinite result')
            if value.is_integer():
                value = int(value)
        if not isinstance(value, (str, int, float)) or not str(value).strip() or '\n' in str(value):
            raise ValueError('Expected a nonempty single-line scalar')
        return value
    finally:
        db.close()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--query', required=True)
    parser.add_argument('--final', action='store_true', help='Commit this scalar as the task answer')
    args = parser.parse_args()
    prefix = RESULT_PREFIX if args.final else 'OJ_SQL_PROBE_JSON='
    print(prefix + json.dumps(scalar(Path.cwd(), args.query), ensure_ascii=False))


if __name__ == '__main__':
    main()
