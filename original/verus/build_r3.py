"""Round 3: top up to N per level (S1 capped by pool size), dedup by chain."""
import json, os, random, subprocess, sys, threading, queue
from collections import Counter
import compose as C, taskify as T

TARGET = int(sys.argv[1]) if len(sys.argv) > 1 else 100
random.seed(int(sys.argv[2]) if len(sys.argv) > 2 else 77)
REF = "refs4"; os.makedirs(REF, exist_ok=True)
CAPS = {1: 120, 2: 60, 3: 60}

prov = json.load(open("provenance.json"))
tasks = json.load(open("tasks/tasks.json"))
used = {tuple(prov[t["file"]]["sources"] + prov[t["file"]]["fns"])
        for t in tasks if t["file"] in prov}
have = Counter(t["level"] for t in tasks)
print("Current:", dict(have), "Target:", TARGET, "| Used chains:", len(used))

pool = C.load_pool()
allf = [(e, f) for e in pool for f in e["fns"]]
chains = {1: [[x] for x in allf], 2: [], 3: []}
for e1, f1 in allf:
    for e2, f2 in allf:
        if e2["file"] != e1["file"] and C.usable_downstream(f2, f1["rtype"]) is not None:
            chains[2].append([(e1, f1), (e2, f2)])
random.shuffle(chains[2])
for c in chains[2][:700]:
    (e1, f1), (e2, f2) = c
    for e3, f3 in allf:
        if e3["file"] not in (e1["file"], e2["file"]) and \
           C.usable_downstream(f3, f2["rtype"]) is not None:
            chains[3].append(c + [(e3, f3)])
print("Compatible chains:", {k: len(v) for k, v in chains.items()})

man = []
for lvl in (1, 2, 3):
    need = TARGET - have[lvl]
    if need <= 0: continue
    random.shuffle(chains[lvl]); made = 0
    for ch in chains[lvl]:
        if made >= CAPS[lvl]: break
        key = tuple([e["file"] for e, _ in ch] + [f["name"] for _, f in ch])
        if key in used: continue
        try: content = C.build([e for e, _ in ch], [f for _, f in ch])
        except Exception: continue
        if content is None: continue
        name = f"R4_S{lvl}_{made:03d}.rs"
        open(f"{REF}/{name}", "w").write(content)
        man.append({"file": name, "level": lvl, "fns": [f["name"] for _, f in ch],
                    "sources": [e["file"] for e, _ in ch]})
        used.add(key); made += 1
    print(f"S{lvl}: need {need}, generated {made} candidates")
json.dump(man, open(f"{REF}/manifest.json", "w"), indent=1)

ok, lock, q = set(), threading.Lock(), queue.Queue()
for m in man: q.put(f"{REF}/{m['file']}")
def w():
    while True:
        try: p = q.get_nowait()
        except queue.Empty: return
        try:
            r = subprocess.run([T.VERUS, p], capture_output=True, text=True, timeout=600)
            good = "0 errors" in r.stdout + r.stderr
        except Exception: good = False
        if good:
            with lock: ok.add(os.path.basename(p))
ths = [threading.Thread(target=w) for _ in range(14)]
for t in ths: t.start()
for t in ths: t.join()
print("Certified:", dict(Counter(m["level"] for m in man if m["file"] in ok)))
json.dump(sorted(ok), open(f"{REF}/certified.json", "w"))

added, rej = Counter(), Counter()
for m in man:
    lvl = m["level"]
    if m["file"] not in ok or have[lvl] + added[lvl] >= TARGET: continue
    p = f"tasks/{m['file']}"
    open(p, "w").write(T.taskify(open(f"{REF}/{m['file']}").read()))
    if T.verus_kind(p) == "VERIF_FAIL":
        tasks.append({"file": m["file"], "level": lvl})
        prov[m["file"]] = {"round": "refs4", **m}
        added[lvl] += 1
    else:
        os.remove(p); rej[lvl] += 1
json.dump(tasks, open("tasks/tasks.json", "w"), indent=1)
json.dump(prov, open("provenance.json", "w"), indent=1)
print("Added:", dict(added), "| Rejected:", dict(rej))
print("Final:", dict(Counter(t["level"] for t in tasks)))
