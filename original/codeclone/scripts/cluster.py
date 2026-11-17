import json
from collections import defaultdict

DATASET = "../Code-Code/Clone-detection-BigCloneBench/dataset"

parent = {}

def find(x):
    while parent[x] != x:
        parent[x] = parent[parent[x]]
        x = parent[x]
    return x

def union(a, b):
    ra, rb = find(a), find(b)
    if ra != rb:
        parent[ra] = rb

edges = 0
with open(f"{DATASET}/train.txt") as f:
    for line in f:
        a, b, label = line.split()
        if label != "1":
            continue
        for x in (a, b):
            parent.setdefault(x, x)
        union(a, b)
        edges += 1

clusters = defaultdict(list)
for node in parent:
    clusters[find(node)].append(node)

sizes = sorted((len(v) for v in clusters.values()), reverse=True)
print(f"positive edges: {edges}")
print(f"nodes: {len(parent)}")
print(f"clusters: {len(clusters)}")
print(f"cluster sizes: {sizes}")

with open("clusters.json", "w") as f:
    json.dump({str(k): v for k, v in clusters.items()}, f)
