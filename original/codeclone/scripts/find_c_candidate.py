import json

DATASET = "../Code-Code/Clone-detection-BigCloneBench/dataset"

with open("clusters.json") as f:
    clusters = json.load(f)

hash_cluster_members = set(clusters["13771944"])

candidates = []
with open(f"{DATASET}/data.jsonl") as f:
    for line in f:
        obj = json.loads(line)
        idx, func = obj["idx"], obj["func"]
        if idx in hash_cluster_members:
            continue  # skip anything BigCloneBench already clustered with B1/B2
        if "byte[]" in func and "String" in func and "MessageDigest" in func and len(func) < 400:
            candidates.append((len(func), idx, func))

candidates.sort()
for length, idx, func in candidates[:10]:
    print(f"--- idx={idx} len={length} ---")
    print(func)
    print()
