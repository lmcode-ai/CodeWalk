import json
from collections import defaultdict

with open("clusters.json") as f:
    clusters = json.load(f)

member_to_cluster = {}
for cid, members in clusters.items():
    for m in members:
        member_to_cluster[m] = cid

# count positive-labeled edges (train.txt) whose BOTH endpoints fall in the same cluster
pair_counts = defaultdict(int)
total_pos_edges = 0
cross_cluster = 0
with open("../Code-Code/Clone-detection-BigCloneBench/dataset/train.txt") as f:
    for line in f:
        a, b, label = line.split()
        if label != "1":
            continue
        total_pos_edges += 1
        ca, cb = member_to_cluster.get(a), member_to_cluster.get(b)
        if ca is None or cb is None:
            continue
        if ca == cb:
            pair_counts[ca] += 1
        else:
            cross_cluster += 1

print(f"total positive edges in train.txt: {total_pos_edges}")
print(f"cross-cluster positive edges (shouldn't happen if union-find is correct): {cross_cluster}")
print()
print("cluster_id  n_members  n_positive_edges_within_cluster")
for cid, members in sorted(clusters.items(), key=lambda kv: -len(kv[1])):
    print(f"{cid:>12} {len(members):>10} {pair_counts.get(cid, 0):>10}")
print()
print("sum of within-cluster positive edges:", sum(pair_counts.values()))
