def distance(a,b):
    return abs(len(a)-len(b))+sum(x!=y for x,y in zip(a,b))
