import re

_RE = re.compile(r"(?:(\d+)d)?(?:(\d+)h)?(?:(\d+)m)?(?:(\d+)s)?")


def parse_duration(text):
    if not isinstance(text, str) or not text:
        raise ValueError("duration")
    match = _RE.fullmatch(text)
    if not match or not any(match.groups()):
        raise ValueError("duration")
    d, h, m, s = (int(x) if x else 0 for x in match.groups())
    return ((d * 24 + h) * 60 + m) * 60 + s
