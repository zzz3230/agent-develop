import heapq
def distances(edges,start):
    graph={}
    for a,b,w in edges: graph.setdefault(a,[]).append((b,w))
    ds={start:0}; q=[(0,start)]
    while q:
        d,u=heapq.heappop(q)
        if d!=ds[u]: continue
        for v,w in graph.get(u,[]):
            if d+w<ds.get(v,float('inf')):
                ds[v]=d+w; heapq.heappush(q,(d+w,v))
    return ds
