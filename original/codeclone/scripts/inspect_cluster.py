import json
import sys

DATASET = "../Code-Code/Clone-detection-BigCloneBench/dataset"

funcs = {}
with open(f"{DATASET}/data.jsonl") as f:
    for line in f:
        obj = json.loads(line)
        funcs[obj["idx"]] = obj["func"]

with open("clusters.json") as f:
    clusters = json.load(f)

sizes = sorted(clusters.items(), key=lambda kv: -len(kv[1]))
for cid, members in sizes:
    print(cid, len(members))

# Inspect a mid-size cluster's shortest functions
target = sys.argv[1] if len(sys.argv) > 1 else sizes[3][0]  # size-132 cluster
members = clusters[target]
lens = sorted(((len(funcs[m]), m) for m in members if m in funcs))
print(f"\ncluster {target}: {len(members)} members, showing 8 shortest")
for l, m in lens[:8]:
    print(f"--- idx={m} len={l} ---")
    print(funcs[m])
    print()
