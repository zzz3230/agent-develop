def total(xs):
    s = 0
    for x in xs:
        s += x
    return s


def maximum(xs):
    best = 0
    for x in xs:
        if x > best:
            best = x
    return best
