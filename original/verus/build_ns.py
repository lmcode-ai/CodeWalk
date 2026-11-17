"""Build NS2/NS3: compositions restricted to building blocks the model got RIGHT.

  NS2 = 2-chains whose BOTH functions were solved as S1 tasks
  NS3 = 3-chains formed by extending a solved S2 chain with a solved S1 function

This isolates composition difficulty from per-function difficulty: every part is
known-solvable by this model, so a failure is attributable to the seams.

Usage: python3 build_ns.py <model_tag> [seed]
"""
import json
import os
import random
import subprocess
import sys
import threading
import queue
from collections import Counter

import compose as C
import taskify as T

HERE = os.path.dirname(os.path.abspath(__file__))
TAG = sys.argv[1]
SEED = int(sys.argv[2]) if len(sys.argv) > 2 else 17
REF = f"{HERE}/ns_refs_{TAG}"
TASK = f"{HERE}/ns_tasks_{TAG}"
TARGET = {2: 30, 3: 30}
CAPS = {2: 150, 3: 400}
NPROC = 12


def load_manifests():
    """file -> {level, fns, sources} across both generation rounds."""
    m = {}
    for d in ("refs", "refs2"):
        p = f"{HERE}/{d}/manifest.json"
        if os.path.exists(p):
            for e in json.load(open(p)):
                m[e["file"]] = e
    return m


def solved_set(tag):
    """Files the model solved under the GOLD standard (frozen spec restored)."""
    p = f"{HERE}/results_{tag}/results_gold.json"
    if not os.path.exists(p):
        p = f"{HERE}/results_{tag}/results.json"
        return {r["file"] for r in json.load(open(p)) if r.get("verified")}
    return {r["file"] for r in json.load(open(p)) if r.get("gold_ok")}


def certify(paths):
    ok, lock, q = set(), threading.Lock(), queue.Queue()
    for p in paths:
        q.put(p)

    def w():
        while True:
            try:
                p = q.get_nowait()
            except queue.Empty:
                return
            try:
                r = subprocess.run([T.VERUS, p], capture_output=True, text=True, timeout=600)
                good = "0 errors" in r.stdout + r.stderr
            except Exception:
                good = False
            if good:
                with lock:
                    ok.add(os.path.basename(p))

    ths = [threading.Thread(target=w) for _ in range(NPROC)]
    for t in ths:
        t.start()
    for t in ths:
        t.join()
    return ok


if __name__ == "__main__":
    os.makedirs(REF, exist_ok=True)
    os.makedirs(TASK, exist_ok=True)
    random.seed(SEED)

    man = load_manifests()
    solved = solved_set(TAG)
    s1_ok = [man[f] for f in solved if man.get(f, {}).get("level") == 1]
    s2_ok = [man[f] for f in solved if man.get(f, {}).get("level") == 2]
    print(f"[{TAG}] solved: S1 {len(s1_ok)}, S2 {len(s2_ok)}")

    pool = C.load_pool()
    index = {(e["file"], f["name"]): (e, f) for e in pool for f in e["fns"]}
    # the exact (source file, fn) pairs the model proved at S1
    s1_units = [index[(m["sources"][0], m["fns"][0])] for m in s1_ok
                if (m["sources"][0], m["fns"][0]) in index]
    s2_units = [[index[(s, n)] for s, n in zip(m["sources"], m["fns"])
                 if (s, n) in index] for m in s2_ok]
    s2_units = [c for c in s2_units if len(c) == 2]
    print(f"[{TAG}] usable units: S1 {len(s1_units)}, S2 chains {len(s2_units)}")

    chains = {2: [], 3: []}
    for e1, f1 in s1_units:                                   # NS2
        for e2, f2 in s1_units:
            if e2["file"] != e1["file"] and C.usable_downstream(f2, f1["rtype"]) is not None:
                chains[2].append([(e1, f1), (e2, f2)])
    if os.environ.get("NS3_LOOSE") == "1":  # Loose NS3: all three stages are S1-correct.
        for e1, f1 in s1_units:
            for e2, f2 in s1_units:
                if e2["file"] == e1["file"] or C.usable_downstream(f2, f1["rtype"]) is None:
                    continue
                for e3, f3 in s1_units:
                    if e3["file"] in (e1["file"], e2["file"]):
                        continue
                    if C.usable_downstream(f3, f2["rtype"]) is not None:
                        chains[3].append([(e1, f1), (e2, f2), (e3, f3)])
    else:  # Strict NS3: an S2-correct chain followed by an S1-correct stage.
        for chain in s2_units:
            (e1, f1), (e2, f2) = chain
            for e3, f3 in s1_units:
                if e3["file"] in (e1["file"], e2["file"]):
                    continue
                if C.usable_downstream(f3, f2["rtype"]) is not None:
                    chains[3].append([(e1, f1), (e2, f2), (e3, f3)])
    print("enumerated:", {k: len(v) for k, v in chains.items()})

    manifest = []
    for lvl in (2, 3):
        random.shuffle(chains[lvl])
        made = 0
        for chain in chains[lvl]:
            if made >= CAPS[lvl]:
                break
            entries = [e for e, _ in chain]
            fns = [f for _, f in chain]
            try:
                content = C.build(entries, fns)
            except Exception:
                continue
            if content is None:
                continue
            name = f"NS{lvl}_{made:03d}.rs"
            open(f"{REF}/{name}", "w").write(content)
            manifest.append({"file": name, "level": lvl,
                             "fns": [f["name"] for f in fns],
                             "sources": [e["file"] for e in entries]})
            made += 1
        print(f"NS{lvl}: {made} candidates")
    json.dump(manifest, open(f"{REF}/manifest.json", "w"), indent=1)

    print("certifying...")
    ok = certify([f"{REF}/{m['file']}" for m in manifest])
    print("certified:", dict(Counter(m["level"] for m in manifest if m["file"] in ok)))

    picked, rejects = [], Counter()
    for lvl in (2, 3):
        cnt = 0
        for m in manifest:
            if m["level"] != lvl or m["file"] not in ok or cnt >= TARGET[lvl]:
                continue
            t = T.taskify(open(f"{REF}/{m['file']}").read())
            p = f"{TASK}/{m['file']}"
            open(p, "w").write(t)
            if T.verus_kind(p) == "VERIF_FAIL":
                picked.append({"file": m["file"], "level": lvl})
                cnt += 1
            else:
                os.remove(p)
                rejects[lvl] += 1
        print(f"NS{lvl}: {cnt}/{TARGET[lvl]} legal tasks")
    json.dump(picked, open(f"{TASK}/tasks.json", "w"), indent=1)
    print("rejects:", dict(rejects))
