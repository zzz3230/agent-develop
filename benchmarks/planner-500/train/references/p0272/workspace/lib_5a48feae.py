def distances(edges,start):
    result={start:0}
    for a,b,w in edges:
        if a in result: result[b]=result[a]+w
    return result
