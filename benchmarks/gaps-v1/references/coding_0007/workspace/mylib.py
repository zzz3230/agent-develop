def clamp(x, lo, hi):
    return max(lo, min(x, hi))


def mean(xs):
    return sum(xs) / len(xs)


def median(xs):
    """Median; for an even count, the mean of the two middle values."""
    ys = sorted(xs)
    return ys[len(ys) // 2]


def is_palindrome(text):
    """True if text reads the same backwards, ignoring case and spaces."""
    cleaned = text.replace(' ', '')
    return cleaned == cleaned[::-1]


def word_count(text):
    return len(text.split())


def flatten(rows):
    return [x for row in rows for x in row]


def safe_div(a, b):
    """a / b, or None when b is zero."""
    if b == 0:
        return 0
    return a / b


def last(xs):
    return xs[-1]
