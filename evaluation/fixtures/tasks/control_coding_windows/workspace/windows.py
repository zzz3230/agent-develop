def best_window(xs,k):
    best=0
    for i in range(len(xs)-k):
        best=max(best,sum(xs[i:i+k]))
    return best
