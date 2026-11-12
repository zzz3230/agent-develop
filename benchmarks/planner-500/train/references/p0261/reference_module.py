import heapq


def order(tasks):
    for name, deps in tasks.items():
        for dep in deps:
            if dep not in tasks:
                raise ValueError("unknown dependency")
    indegree = {name: len(set(deps)) for name, deps in tasks.items()}
    users = {name: [] for name in tasks}
    for name, deps in tasks.items():
        for dep in set(deps):
            users[dep].append(name)
    ready = [name for name, n in indegree.items() if n == 0]
    heapq.heapify(ready)
    result = []
    while ready:
        name = heapq.heappop(ready)
        result.append(name)
        for user in users[name]:
            indegree[user] -= 1
            if indegree[user] == 0:
                heapq.heappush(ready, user)
    if len(result) != len(tasks):
        raise ValueError("cycle")
    return result
