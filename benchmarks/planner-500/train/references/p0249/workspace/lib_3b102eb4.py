def apply(balances,transfers):
    for a,b,n in transfers:
        balances[a]-=n; balances[b]+=n
    return balances
