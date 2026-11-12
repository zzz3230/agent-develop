import csv, io
def read_rows(text):
    return list(csv.reader(io.StringIO(text, newline="")))
