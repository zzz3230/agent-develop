def compare(a,b):
    x=list(map(int,a.split('.'))); y=list(map(int,b.split('.')))
    size=max(len(x),len(y)); x+=[0]*(size-len(x)); y+=[0]*(size-len(y))
    return (x>y)-(x<y)
