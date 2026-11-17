"""Build an S10 task bank by walking proven seams.

A certified level-2 reference proves that one stage's output can drive the next.
Walking only those seams keeps deep chains from dying at certification, which is
what a naive 10-stage enumeration does.

Stage 1: collect proven seams, enumerate distinct length-10 walks
Stage 2: compose + certify references with Verus (parallel)
Stage 3: taskify and keep only legal tasks (parse-clean, fails only at verification)

Usage: python3 build_deep.py [target] [candidates] [seed]
"""
import json
import os
import queue
import random
import subprocess
import sys
import threading
from collections import Counter, defaultdict

import compose as C
import taskify as T

HERE = os.path.dirname(os.path.abspath(__file__))
REF, TASK = f"{HERE}/refs10", f"{HERE}/tasks_s10"
LEVEL = 10
REUSE_CAP = 2          # how often one source program may appear in a chain
NPROC = 12


def proven_seams():
    """Edges (upstream fn -> downstream fn) that a certified level-2 ref proved."""
    edges = set()

    def add(sources, fns):
        for i in range(len(fns) - 1):
            edges.add(((sources[i], fns[i]), (sources[i + 1], fns[i + 1])))

    for d in ("refs2", "refs3"):
        man = {m["file"]: m for m in json.load(open(f"{HERE}/{d}/manifest.json"))}
        for name in set(json.load(open(f"{HERE}/{d}/certified.json"))):
            m = man.get(name)
            if m and m["level"] == 2:
                add(m["sources"], m["fns"])
    for r in json.load(open(f"{HERE}/provenance.json")).values():
        if r["level"] >= 2:
            add(r["sources"], r["fns"])
    out = defaultdict(list)
    for u, v in edges:
        out[u].append(v)
    for k in out:
        out[k].sort()
    return out


def walks(out, length, want, used_chains):
    """Distinct length-N walks, spread over start nodes so one hub function
    cannot supply every chain."""
    found, starts = [], sorted(out)
    random.shuffle(starts)

    def dfs(path, used, quota):
        """Collect up to `quota` walks below `path`; returns how many."""
        if len(path) == length:
            key = tuple(path)
            if key in used_chains:
                return 0
            used_chains.add(key)
            found.append(list(path))
            return 1
        got = 0
        nxt = [v for v in out.get(path[-1], ()) if used[v[0]] < REUSE_CAP]
        random.shuffle(nxt)
        for v in nxt:
            if got >= quota or len(found) >= want:
                break
            used[v[0]] += 1
            path.append(v)
            got += dfs(path, used, quota - got)
            path.pop()
            used[v[0]] -= 1
        return got

    for quota in (2, 8, 32):
        for s in starts:
            if len(found) >= want:
                return found
            dfs([s], Counter([s[0]]), quota)
    return found


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
                r = subprocess.run([T.VERUS, p], capture_output=True, text=True, timeout=1800)
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
    target = int(sys.argv[1]) if len(sys.argv) > 1 else 100
    want = int(sys.argv[2]) if len(sys.argv) > 2 else 220
    random.seed(int(sys.argv[3]) if len(sys.argv) > 3 else 11)
    os.makedirs(REF, exist_ok=True)
    os.makedirs(TASK, exist_ok=True)

    pool = {(e["file"], f["name"]): (e, f) for e in C.load_pool() for f in e["fns"]}
    out = proven_seams()
    print(f"proven seams: {sum(len(v) for v in out.values())} from {len(out)} functions", flush=True)

    prov = json.load(open(f"{HERE}/provenance.json"))
    used_chains = {tuple(zip(r["sources"], r["fns"])) for r in prov.values()}
    cand = walks(out, LEVEL, want, used_chains)
    print(f"walks enumerated: {len(cand)}", flush=True)

    man = []
    for ch in cand:
        if any(node not in pool for node in ch):
            continue
        entries = [pool[node][0] for node in ch]
        fns = [pool[node][1] for node in ch]
        try:
            content = C.build(entries, fns)
        except Exception:
            continue
        if content is None:
            continue
        name = f"S10_{len(man):03d}.rs"
        open(f"{REF}/{name}", "w").write(content)
        man.append({"file": name, "level": LEVEL, "fns": [f["name"] for f in fns],
                    "sources": [e["file"] for e in entries]})
    json.dump(man, open(f"{REF}/manifest.json", "w"), indent=1)
    print(f"composed: {len(man)} candidate references", flush=True)

    print("certifying...", flush=True)
    ok = certify([f"{REF}/{m['file']}" for m in man])
    json.dump(sorted(ok), open(f"{REF}/certified.json", "w"))
    print(f"certified: {len(ok)}/{len(man)}", flush=True)

    print("taskifying...", flush=True)
    tasks, prov10, rejects = [], {}, Counter()
    for m in man:
        if len(tasks) >= target or m["file"] not in ok:
            continue
        p = f"{TASK}/{m['file']}"
        open(p, "w").write(T.taskify(open(f"{REF}/{m['file']}").read()))
        kind = T.verus_kind(p, timeout=1800)
        if kind == "VERIF_FAIL":
            tasks.append({"file": m["file"], "level": LEVEL})
            prov10[m["file"]] = {"round": "refs10", **m}
        else:
            os.remove(p)
            rejects[kind] += 1
    json.dump(tasks, open(f"{TASK}/tasks.json", "w"), indent=1)
    json.dump(prov10, open(f"{HERE}/provenance_s10.json", "w"), indent=1)
    print(f"legal tasks: {len(tasks)}/{target} | rejects: {dict(rejects)}", flush=True)
