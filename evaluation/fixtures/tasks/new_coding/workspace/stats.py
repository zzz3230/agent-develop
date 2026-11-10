def median(xs):
    xs = sorted(xs)
    n = len(xs)
    return xs[n // 2]

def longest_run(xs):
    best = current = 0
    for value in xs:
        current = current + 1 if value else 0
        best = current
    return best
