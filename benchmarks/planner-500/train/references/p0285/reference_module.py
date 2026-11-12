import re

_RE = re.compile(r"^(0|[1-9]\d*)\.(0|[1-9]\d*)\.(0|[1-9]\d*)"
                 r"(?:-((?:0|[1-9]\d*|\d*[A-Za-z-][0-9A-Za-z-]*)(?:\.(?:0|[1-9]\d*|\d*[A-Za-z-][0-9A-Za-z-]*))*))?"
                 r"(?:\+([0-9A-Za-z-]+(?:\.[0-9A-Za-z-]+)*))?$")


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
