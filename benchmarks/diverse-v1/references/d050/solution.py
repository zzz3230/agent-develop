def split_fields(text):
    out=[]; part=[]; escaped=False
    for c in text:
        if escaped: part.append(c); escaped=False
        elif c=='\\': escaped=True
        elif c=='|': out.append(''.join(part)); part=[]
        else: part.append(c)
    if escaped: part.append('\\')
    out.append(''.join(part)); return out
