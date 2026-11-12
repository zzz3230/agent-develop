_PAIRS = [(1000, "M"), (900, "CM"), (500, "D"), (400, "CD"), (100, "C"), (90, "XC"),
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
