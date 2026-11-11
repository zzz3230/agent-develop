def transpose(rows,fill=None):
    return [[row[i] if i<len(row) else fill for row in rows] for i in range(max(map(len,rows),default=0))]
