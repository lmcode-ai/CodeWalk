"""Top up tasks/ to N per level using certified refs, with collision-proof naming."""
import json, os, sys, hashlib
from collections import Counter
import taskify as T

TARGET = int(sys.argv[1]) if len(sys.argv) > 1 else 50
tasks = json.load(open("tasks/tasks.json"))
prov = json.load(open("provenance.json"))
have_chain = {tuple(prov[t["file"]]["sources"] + prov[t["file"]]["fns"])
              for t in tasks if t["file"] in prov}
cnt = Counter(t["level"] for t in tasks)
print("Current:", dict(cnt), "Target:", TARGET)

cert2 = set(json.load(open("refs2/certified.json")))
man2 = {e["file"]: e for e in json.load(open("refs2/manifest.json"))}
added, rej = Counter(), Counter()
for f in sorted(cert2):
    m = man2.get(f)
    if not m or cnt[m["level"]] + added[m["level"]] >= TARGET:
        continue
    key = tuple(m["sources"] + m["fns"])
    if key in have_chain:
        continue
    new = f"R2_{f}"
    if os.path.exists(f"tasks/{new}"):
        continue
    open(f"tasks/{new}", "w").write(T.taskify(open(f"refs2/{f}").read()))
    if T.verus_kind(f"tasks/{new}") == "VERIF_FAIL":
        tasks.append({"file": new, "level": m["level"]})
        prov[new] = {"round": "refs2", **m}
        have_chain.add(key)
        added[m["level"]] += 1
    else:
        os.remove(f"tasks/{new}")
        rej[m["level"]] += 1
json.dump(tasks, open("tasks/tasks.json", "w"), indent=1)
json.dump(prov, open("provenance.json", "w"), indent=1)
print("Added:", dict(added), "| Rejected:", dict(rej))
print("Final:", dict(Counter(t["level"] for t in tasks)))
