import re

_FULL = re.compile(
    r'^(0|[1-9]\d*)\.(0|[1-9]\d*)\.(0|[1-9]\d*)'
    r'(?:-((?:0|[1-9]\d*|\d*[a-zA-Z-][0-9a-zA-Z-]*)'
    r'(?:\.(?:0|[1-9]\d*|\d*[a-zA-Z-][0-9a-zA-Z-]*))*))?'
    r'(?:\+([0-9a-zA-Z-]+(?:\.[0-9a-zA-Z-]+)*))?$'
)


def _parse(v):
    if not isinstance(v, str):
        raise ValueError('invalid version')
    m = _FULL.match(v)
    if not m:
        raise ValueError('invalid version: %r' % v)
    major, minor, patch = int(m.group(1)), int(m.group(2)), int(m.group(3))
    pre = m.group(4)
    pre_ids = pre.split('.') if pre is not None else None
    return (major, minor, patch), pre_ids


def _cmp_id(x, y):
    x_num = x.isdigit()
    y_num = y.isdigit()
    if x_num and y_num:
        xi, yi = int(x), int(y)
        return (xi > yi) - (xi < yi)
    if x_num:
        return -1
    if y_num:
        return 1
    return (x > y) - (x < y)


def _cmp_pre(a, b):
    if a is None and b is None:
        return 0
    if a is None:
        return 1
    if b is None:
        return -1
    for x, y in zip(a, b):
        c = _cmp_id(x, y)
        if c:
            return c
    la, lb = len(a), len(b)
    return (la > lb) - (la < lb)


def compare(a, b):
    ka, pa = _parse(a)
    kb, pb = _parse(b)
    if ka != kb:
        return (ka > kb) - (ka < kb)
    return _cmp_pre(pa, pb)
