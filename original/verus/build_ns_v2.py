"""NS2/NS3 built from CORRECTLY-traced S1/S2-correct units (provenance.json)."""
import json, os, random, subprocess, sys, threading, queue
from collections import Counter
import compose as C, taskify as T

TAG = sys.argv[1] if len(sys.argv) > 1 else "kimi"
random.seed(int(sys.argv[2]) if len(sys.argv) > 2 else 41)
REF, TASK = f"ns2_refs_{TAG}", f"ns2_tasks_{TAG}"
os.makedirs(REF, exist_ok=True); os.makedirs(TASK, exist_ok=True)
TARGET = {2: 30, 3: 30}; CAPS = {2: 200, 3: 300}

prov = json.load(open("provenance.json"))
g = json.load(open(f"results_{TAG}/results_gold.json"))
solved = {x["file"] for x in g if x.get("gold_ok")}
pool = C.load_pool()
idx = {(e["file"], f["name"]): (e, f) for e in pool for f in e["fns"]}

s1_units, s2_chains = [], []
for f in solved:
    m = prov.get(f)
    if not m: continue
    units = [idx[(s, n)] for s, n in zip(m["sources"], m["fns"]) if (s, n) in idx]
    if m["level"] == 1 and len(units) == 1: s1_units.append(units[0])
    elif m["level"] == 2 and len(units) == 2: s2_chains.append(units)
print(f"[{TAG}] Correct sources: {len(s1_units)} S1-correct units, {len(s2_chains)} S2-correct chains")

chains = {2: [], 3: []}
for e1, f1 in s1_units:
    for e2, f2 in s1_units:
        if e2["file"] != e1["file"] and C.usable_downstream(f2, f1["rtype"]) is not None:
            chains[2].append([(e1, f1), (e2, f2)])
for e1, f1 in s1_units:  # NS3: all three stages are S1-correct.
    for e2, f2 in s1_units:
        if e2["file"] == e1["file"] or C.usable_downstream(f2, f1["rtype"]) is None: continue
        for e3, f3 in s1_units:
            if e3["file"] in (e1["file"], e2["file"]): continue
            if C.usable_downstream(f3, f2["rtype"]) is not None:
                chains[3].append([(e1, f1), (e2, f2), (e3, f3)])
print("Compatible chains:", {k: len(v) for k, v in chains.items()})

man = []
for lvl in (2, 3):
    random.shuffle(chains[lvl]); made = 0
    for ch in chains[lvl]:
        if made >= CAPS[lvl]: break
        try: content = C.build([e for e, _ in ch], [f for _, f in ch])
        except Exception: continue
        if content is None: continue
        name = f"NS{lvl}_{made:03d}.rs"
        open(f"{REF}/{name}", "w").write(content)
        man.append({"file": name, "level": lvl, "fns": [f["name"] for _, f in ch],
                    "sources": [e["file"] for e, _ in ch]})
        made += 1
    print(f"NS{lvl}: {made} candidates")
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
ths = [threading.Thread(target=w) for _ in range(8)]
for t in ths: t.start()
for t in ths: t.join()
print("Certified:", dict(Counter(m["level"] for m in man if m["file"] in ok)))

picked = []
for lvl in (2, 3):
    cnt = 0
    for m in man:
        if m["level"] != lvl or m["file"] not in ok or cnt >= TARGET[lvl]: continue
        p = f"{TASK}/{m['file']}"
        open(p, "w").write(T.taskify(open(f"{REF}/{m['file']}").read()))
        if T.verus_kind(p) == "VERIF_FAIL":
            picked.append({"file": m["file"], "level": lvl}); cnt += 1
        else: os.remove(p)
    print(f"NS{lvl}: {cnt}/{TARGET[lvl]} legal tasks")
json.dump(picked, open(f"{TASK}/tasks.json", "w"), indent=1)
