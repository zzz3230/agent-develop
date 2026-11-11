import re

_PATTERN = re.compile(r"^(?:(\d+)d)?(?:(\d+)h)?(?:(\d+)m)?(?:(\d+)s)?$")
_MULT = {"d": 86400, "h": 3600, "m": 60, "s": 1}


def parse_duration(text):
    if not isinstance(text, str):
        raise ValueError("duration must be a string")
    m = _PATTERN.match(text)
    if m is None or not any(m.groups()):
        raise ValueError("invalid duration: %r" % (text,))
    total = 0
    for value, unit in zip(m.groups(), "dhms"):
        if value is not None:
            total += int(value) * _MULT[unit]
    return total
