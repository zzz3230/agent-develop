def lookup(data,path,default=None):
    for key in path:
        if isinstance(data,dict):
            try: data=data[key]
            except (KeyError,TypeError): return default
        elif isinstance(data,list) and type(key) is int and 0<=key<len(data): data=data[key]
        else: return default
    return data
