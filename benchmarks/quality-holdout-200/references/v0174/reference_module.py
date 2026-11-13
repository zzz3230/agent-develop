import ast,re
def calculate(text):
    if not isinstance(text,str) or re.search(r'[^0-9+*()\s-]',text): raise ValueError('syntax')
    normalized=re.sub(r'\s+',' ',text).strip()
    normalized=re.sub(r'\d+',lambda m:str(int(m.group())),normalized)
    try: node=ast.parse(normalized,mode='eval').body
    except (SyntaxError,ValueError): raise ValueError('syntax')
    def visit(n):
        if isinstance(n,ast.Constant) and type(n.value) is int: return n.value
        if isinstance(n,ast.UnaryOp) and isinstance(n.op,(ast.UAdd,ast.USub)):
            v=visit(n.operand); return v if isinstance(n.op,ast.UAdd) else -v
        if isinstance(n,ast.BinOp) and isinstance(n.op,(ast.Add,ast.Sub,ast.Mult)):
            a,b=visit(n.left),visit(n.right)
            return a+b if isinstance(n.op,ast.Add) else a-b if isinstance(n.op,ast.Sub) else a*b
        raise ValueError('syntax')
    return visit(node)
