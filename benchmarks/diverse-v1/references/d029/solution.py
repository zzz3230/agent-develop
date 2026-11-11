class Store:
    def __init__(self): self.data={}
    def put(self,key,value,now,ttl):
        if ttl<=0: self.data.pop(key,None)
        else: self.data[key]=(value,now+ttl)
    def get(self,key,now):
        if key not in self.data: return None
        value,end=self.data[key]
        if now>=end:
            del self.data[key]; return None
        return value
