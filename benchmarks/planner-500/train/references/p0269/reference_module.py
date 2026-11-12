def apply(balances,transfers):
    result=dict(balances)
    for a,b,n in transfers:
        if a not in result or b not in result or type(n) is not int or n<0 or result[a]<n: raise ValueError('transfer')
        result[a]-=n; result[b]+=n
    return result
