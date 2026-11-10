def merge(intervals):
    out=[]
    for start,end in intervals:
        if out and start <= out[-1][1]:
            out[-1]=(out[-1][0],end)
        else:
            out.append((start,end))
    return out

def covered(intervals):
    return sum(b-a for a,b in intervals)
