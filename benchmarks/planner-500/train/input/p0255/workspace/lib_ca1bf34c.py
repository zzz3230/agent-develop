_V = {"I": 1, "V": 5, "X": 10, "L": 50, "C": 100, "D": 500, "M": 1000}


def to_roman(n):
    out = ""
    for value, letters in [(1000, "M"), (500, "D"), (100, "C"), (50, "L"), (10, "X"), (5, "V"), (1, "I")]:
        while n >= value:
            out += letters
            n -= value
    return out


def from_roman(text):
    return sum(_V[c] for c in text.upper())
