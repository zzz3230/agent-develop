def clean(path):
    return "/".join(p for p in path.split("/") if p and p != ".")
