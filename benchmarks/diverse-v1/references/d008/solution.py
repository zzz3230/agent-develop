def expand(pairs):
    parts=[]
    for text,count in pairs:
        if type(count) is not int or count<0: raise ValueError('count')
        parts.append(text*count)
    return ''.join(parts)
