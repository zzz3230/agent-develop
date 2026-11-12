def lower_bound(values,target):
    lo,hi=0,len(values)
    while lo<hi:
        mid=(lo+hi)//2
        if values[mid]<target: lo=mid+1
        else: hi=mid
    return lo
