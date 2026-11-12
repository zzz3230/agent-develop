def covered(intervals):
    end=None; total=0
    for a,b in sorted(intervals):
        total+=max(0,b-max(a,end if end is not None else a))
        end=b if end is None else max(end,b)
    return total
