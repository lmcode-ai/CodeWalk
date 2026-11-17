"""Generate + certify + taskify an S1/S2/S3 task bank.

Stage 1: enumerate distinct chains (S1 = every fn, S2/S3 = walks over usable pairs)
Stage 2: certify reference files with Verus (parallel)
Stage 3: taskify and keep only legal tasks (parse-clean, fails only at verification)
"""
import json
import os
import random
import subprocess
import sys
import threading
import queue

import compose as C
import taskify as T

HERE = os.path.dirname(os.path.abspath(__file__))
REF, TASK = f"{HERE}/refs", f"{HERE}/tasks"
TARGET = {1: 30, 2: 30, 3: 30}
CAPS = {1: 60, 2: 120, 3: 200}
NPROC = 12


def certify(paths):
    ok, lock, q = set(), threading.Lock(), queue.Queue()
    for p in paths:
        q.put(p)

    def worker():
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

    ths = [threading.Thread(target=worker) for _ in range(NPROC)]
    for t in ths:
        t.start()
    for t in ths:
        t.join()
    return ok


if __name__ == "__main__":
    os.makedirs(REF, exist_ok=True)
    os.makedirs(TASK, exist_ok=True)
    random.seed(int(sys.argv[1]) if len(sys.argv) > 1 else 5)

    pool = C.load_pool()
    allf = [(e, f) for e in pool for f in e["fns"]]
    print(f"pool: {len(pool)} files, {len(allf)} fns with ensures")

    chains = {1: [[x] for x in allf], 2: [], 3: []}
    for e1, f1 in allf:
        for e2, f2 in allf:
            if e2["file"] != e1["file"] and C.usable_downstream(f2, f1["rtype"]) is not None:
                chains[2].append([(e1, f1), (e2, f2)])
    random.shuffle(chains[2])
    for c in chains[2][:600]:
        (e1, f1), (e2, f2) = c
        for e3, f3 in allf:
            if e3["file"] not in (e1["file"], e2["file"]) and \
                    C.usable_downstream(f3, f2["rtype"]) is not None:
                chains[3].append(c + [(e3, f3)])
    print("enumerated:", {k: len(v) for k, v in chains.items()})

    manifest = []
    for lvl in (1, 2, 3):
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
            name = f"S{lvl}_{made:03d}.rs"
            open(f"{REF}/{name}", "w").write(content)
            manifest.append({"file": name, "level": lvl,
                             "fns": [f["name"] for f in fns],
                             "sources": [e["file"] for e in entries]})
            made += 1
        print(f"S{lvl}: {made} candidates written")
    json.dump(manifest, open(f"{REF}/manifest.json", "w"), indent=1)

    print("certifying...")
    ok = certify([f"{REF}/{m['file']}" for m in manifest])
    from collections import Counter
    print("certified:", dict(Counter(m["level"] for m in manifest if m["file"] in ok)))

    print("taskifying...")
    picked, rejects = [], Counter()
    for lvl in (1, 2, 3):
        cnt = 0
        for m in manifest:
            if m["level"] != lvl or m["file"] not in ok or cnt >= TARGET[lvl]:
                continue
            t = T.taskify(open(f"{REF}/{m['file']}").read())
            p = f"{TASK}/{m['file']}"
            open(p, "w").write(t)
            kind = T.verus_kind(p)
            if kind == "VERIF_FAIL":
                picked.append({"file": m["file"], "level": lvl})
                cnt += 1
            else:
                os.remove(p)
                rejects[(lvl, kind)] += 1
        print(f"S{lvl}: {cnt}/{TARGET[lvl]} legal tasks")
    json.dump(picked, open(f"{TASK}/tasks.json", "w"), indent=1)
    print("rejects:", dict(rejects))
