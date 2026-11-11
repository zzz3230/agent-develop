class Store:
    def __init__(self): self.data={}
    def put(self,key,value,now,ttl): self.data[key]=value
    def get(self,key,now): return self.data.get(key)
