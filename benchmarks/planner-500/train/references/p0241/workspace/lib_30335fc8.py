def order(tasks):
    seen, out = set(), []
    def visit(n):
        if n in seen:
            return
        seen.add(n)
        for d in tasks.get(n, []):
            visit(d)
        out.append(n)
    for n in tasks:
        visit(n)
    return out
