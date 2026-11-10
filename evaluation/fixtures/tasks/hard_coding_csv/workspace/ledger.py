def total(text):
    value=0.0
    for line in text.splitlines()[1:]:
        category,amount=line.split(",")
        value+=float(amount)
    return value
