import re


def parse_duration(text):
    total = 0
    for value, unit in re.findall(r"(\d+)([hms])", text):
        total += int(value) * {"h": 360, "m": 60, "s": 1}[unit]
    return total
