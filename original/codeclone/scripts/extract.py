import json, sys

DATASET = "../Code-Code/Clone-detection-BigCloneBench/dataset"
funcs = {}
with open(f"{DATASET}/data.jsonl") as f:
    for line in f:
        obj = json.loads(line)
        funcs[obj["idx"]] = obj["func"]

for idx in sys.argv[1:]:
    print(f"===== idx={idx} =====")
    print(funcs[idx])
    print()
