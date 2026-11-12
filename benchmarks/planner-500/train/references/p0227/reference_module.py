import heapq
def order(deps):
    nodes=set(deps)|{x for vs in deps.values() for x in vs}
    incoming={n:set(deps.get(n,[])) for n in nodes}
    ready=[n for n in nodes if not incoming[n]]; heapq.heapify(ready)
    out=[]
    while ready:
        n=heapq.heappop(ready); out.append(n)
        for v in nodes:
            if n in incoming[v]:
                incoming[v].remove(n)
                if not incoming[v]: heapq.heappush(ready,v)
    if len(out)!=len(nodes): raise ValueError('cycle')
    return out
