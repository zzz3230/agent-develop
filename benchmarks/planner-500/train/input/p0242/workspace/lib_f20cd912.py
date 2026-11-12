def lookup(data,path,default=None):
    for key in path: data=data.get(key,default)
    return data
