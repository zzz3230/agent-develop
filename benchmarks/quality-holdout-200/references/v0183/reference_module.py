def unique(xs):
    """Remove repeated items, keeping the first occurrence of each in order."""
    return list(dict.fromkeys(xs))
