"""PRECHECK=1: facts about the files that the agent would otherwise spend steps on.

Checked before the first model call, without a model and without references: whether files and
directories named in the question exist, and, for search tasks, whether the names and IDs from the
question occur in the files at all. Each fact comes with the closest existing spelling, so a typo
in the question costs nothing either. The agent gets facts, not a verdict.
"""
import csv
import difflib
import re
from pathlib import Path

_FILE = re.compile(r"(?<![\w/.-])((?:[\w-]+/)*[\w.-]+\.(?:csv|tsv|json|jsonl|md|txt|py))\b")
_DIR = re.compile(r"(?<![\w/.-])((?:[\w-]+/)+)(?![\w.-])")
_NAME = re.compile(r"\b[A-Z][a-z]+(?: [A-Z][a-z]+)+\b")
_ID = re.compile(r"\b[A-Z]{1,4}-\d+\b")
_SKIP = {'The', 'In', 'What', 'Which', 'Who', 'How', 'Use', 'Using', 'Work', 'When', 'Return', 'Put', 'Do',
         'Files', 'Give', 'Report', 'Find', 'For', 'If', 'Only', 'Each'}
TEXT = {'.md', '.txt', '.json', '.csv', '.tsv', '.jsonl'}


def _corpus(root: Path, limit_files: int = 300, limit_bytes: int = 100_000):
    files, texts = [], []
    for path in sorted(root.rglob('*')):
        if len(files) >= limit_files:
            break
        if not path.is_file() or path.is_symlink() or path.name in ('task.json', 'answer.txt'):
            continue
        files.append(path.relative_to(root).as_posix())
        if path.suffix.lower() in TEXT and path.stat().st_size <= limit_bytes:
            try:
                texts.append((files[-1], path.read_text(encoding='utf-8', errors='replace')))
            except OSError:
                pass
    return files, texts


def _closest(word: str, options) -> str | None:
    found = difflib.get_close_matches(word.lower(), {o.lower(): o for o in options}, n=1, cutoff=0.75)
    if not found:
        return None
    return {o.lower(): o for o in options}[found[0]]


def _missing_paths(root: Path, question: str, files: list[str]) -> list[str]:
    notes = []
    names = {f.rsplit('/', 1)[-1] for f in files}
    dirs = {d + '/' for f in files for d in ['/'.join(f.split('/')[:i]) for i in range(1, f.count('/') + 1)]}
    for path in sorted(set(_FILE.findall(question))):
        name = path.rsplit('/', 1)[-1]
        if (root / path).exists() or name in names or name in ('answer.txt', 'task.json'):
            continue
        near = _closest(name, names)
        same = sorted(f for f in files if f.endswith(Path(name).suffix))[:5]
        notes.append(f"the file {path} does not exist" + (f"; the closest existing file is {near}" if near else
                     f"; existing {Path(name).suffix} files: {', '.join(same)}" if same else ''))
    for path in sorted(set(_DIR.findall(question))):
        if (root / path).is_dir() or path in dirs or '//' in path:
            continue
        near = _closest(path, dirs)
        top = sorted(d for d in dirs if d.count('/') == 1)[:5]
        notes.append(f"the directory {path} does not exist" + (f"; the closest existing directory is {near}" if near else
                     f"; existing directories: {', '.join(top)}" if top else ''))
    return notes


def _search_facts(question: str, texts: list[tuple[str, str]]) -> list[str]:
    notes = []
    corpus = '\n'.join(text for _, text in texts)
    lowered = corpus.lower()
    keys = [m for m in _NAME.findall(question) if m.split()[0] not in _SKIP] + _ID.findall(question)
    candidates = set(_NAME.findall(corpus)) | set(_ID.findall(corpus))
    for key in dict.fromkeys(keys):
        if key.lower() in lowered:
            titled = [name for name, text in texts if re.match(r'#\s*' + re.escape(key) + r'\s*$', text.strip().splitlines()[0] if text.strip() else '', re.I)]
            if len(titled) > 1:
                notes.append(f"'{key}' is the title of {len(titled)} files: {', '.join(titled[:5])}")
            continue
        near = _closest(key, candidates)
        notes.append(f"'{key}' does not occur in any file" + (f"; the closest name in the files is '{near}'" if near else ''))
    return notes



def _read_csv(path: Path, limit_rows: int = 5000):
    try:
        with path.open(encoding='utf-8', errors='replace', newline='') as handle:
            rows = list(csv.reader(handle))[:limit_rows + 1]
    except OSError:
        return None
    if len(rows) < 2:
        return None
    header = [h.strip() for h in rows[0]]
    return header, [[c.strip() for c in r] for r in rows[1:] if r]


def _csv_facts(root: Path, question: str, files: list[str]) -> list[str]:
    tables = {}
    for name in [f for f in files if f.endswith('.csv')][:6]:
        table = _read_csv(root / name)
        if table:
            tables[name] = table
    notes = []
    numbers = set(re.findall(r'\b\d+\b', question))
    for name, (header, rows) in tables.items():
        if header and header[0].lower().endswith('id'):
            values = [r[0] for r in rows if r]
            for value in sorted(numbers & set(values), key=values.count, reverse=True)[:1]:
                if values.count(value) > 1:
                    notes.append(f"in {name} {header[0]} {value} occurs in {values.count(value)} rows")
    names = list(tables)
    for i, a in enumerate(names):
        for b in names[i + 1:]:
            (ha, ra), (hb, rb) = tables[a], tables[b]
            for column in [c for c in ha if c in hb and c.lower() != 'id']:
                big, small = (a, b) if len(ra) >= len(rb) else (b, a)
                (hbig, rbig), (hsmall, rsmall) = tables[big], tables[small]
                vb = [r[hbig.index(column)] for r in rbig if len(r) > hbig.index(column)]
                vs = [r[hsmall.index(column)] for r in rsmall if len(r) > hsmall.index(column)]
                absent = sorted(set(vb) - set(vs))
                if absent and len(absent) <= 5:
                    notes.append(f"{column} values of {big} absent from {small}: " + ', '.join(
                        f"{v} ({vb.count(v)} rows)" for v in absent))
                for name, values, other in ((small, vs, vb), (big, vb, vs)):
                    doubled = sorted(v for v in set(values) & set(other) if values.count(v) > 1)
                    if doubled and len(doubled) <= 3 and len(values) - len(set(values)) <= 3:
                        notes.append(f"{column} values that occur more than once in {name}: " + ', '.join(doubled))
    return notes


def precheck(root: Path, question: str, task_type: str) -> str:
    if task_type == 'coding':
        return ''
    root = root.resolve()
    files, texts = _corpus(root)
    notes = _missing_paths(root, question, files)
    if task_type == 'search':
        notes += _search_facts(question, texts)
    if task_type == 'data_analysis':
        notes += _csv_facts(root, question, files)
    if not notes:
        return ''
    return ('Pre-check of the files by the harness (facts, computed before you start): '
            + '; '.join(notes[:6]) + '.')
