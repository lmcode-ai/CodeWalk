"""
Run the execution-based verifier across a stratified sample of BigCloneBench's
labeled-positive pairs (see clone_verifier.py for the verification logic).

Sampling plan (documented decision, see clonebench-verifier-README.md):
  - 400 randomly-sampled within-cluster positive edges from each of the 4
    substantial clusters (10447015, 13771944, 17102809, 2450)
  - full coverage of the 4 tiny clusters (22634542, 23677151, 1829463, 23295333)
Exhaustive verification of all 450,862 positive edges is not feasible in this
session; this sample size gives a ~5% margin of error at 95% CI per cluster.

Usage:
    python3 run_clone_verification.py
"""
import json
import random
import sys
import time
from collections import defaultdict

from clone_verifier import compare_pair

DATASET = "../Code-Code/Clone-detection-BigCloneBench/dataset"
SAMPLE_PER_BIG_CLUSTER = 400
BIG_CLUSTERS = {"10447015", "13771944", "17102809", "2450"}
SEED = 0


def load_data():
    funcs = {}
    with open(f"{DATASET}/data.jsonl") as f:
        for line in f:
            obj = json.loads(line)
            funcs[obj["idx"]] = obj["func"]
    with open("clusters.json") as f:
        clusters = json.load(f)
    member_to_cluster = {}
    for cid, members in clusters.items():
        for m in members:
            member_to_cluster[m] = cid
    return funcs, clusters, member_to_cluster


def load_within_cluster_edges(member_to_cluster):
    by_cluster = defaultdict(list)
    with open(f"{DATASET}/train.txt") as f:
        for line in f:
            a, b, label = line.split()
            if label != "1":
                continue
            ca, cb = member_to_cluster.get(a), member_to_cluster.get(b)
            if ca is not None and ca == cb:
                by_cluster[ca].append((a, b))
    return by_cluster


def sample_edges(by_cluster):
    rng = random.Random(SEED)
    sampled = {}
    for cid, edges in by_cluster.items():
        if cid in BIG_CLUSTERS:
            n = min(SAMPLE_PER_BIG_CLUSTER, len(edges))
            sampled[cid] = rng.sample(edges, n)
        else:
            sampled[cid] = edges  # full coverage for tiny clusters
    return sampled


def main():
    funcs, clusters, member_to_cluster = load_data()
    by_cluster = load_within_cluster_edges(member_to_cluster)
    sampled = sample_edges(by_cluster)

    total = sum(len(v) for v in sampled.values())
    print(f"sampling plan: {sum(1 for c in sampled if c in BIG_CLUSTERS)} big clusters x up to "
          f"{SAMPLE_PER_BIG_CLUSTER}, {sum(1 for c in sampled if c not in BIG_CLUSTERS)} small clusters (full)")
    print(f"total sampled edges: {total}")
    for cid, edges in sorted(sampled.items(), key=lambda kv: -len(kv[1])):
        print(f"  cluster {cid}: {len(edges)} sampled (of {len(by_cluster[cid])} available, "
              f"{len(clusters[cid])} members)")

    cache = {}
    results = defaultdict(list)  # cid -> list of {a, b, verdict, ...}
    start = time.time()
    n_done = 0
    for cid, edges in sampled.items():
        for a, b in edges:
            res = compare_pair(a, b, funcs, cache)
            results[cid].append({"a": a, "b": b, **res})
            n_done += 1
            if n_done % 50 == 0:
                elapsed = time.time() - start
                print(f"  [{n_done}/{total}] elapsed={elapsed:.0f}s "
                      f"unique_functions_verified={len(cache)}", file=sys.stderr)

    elapsed = time.time() - start
    print(f"\ndone: {n_done} edges verified in {elapsed:.0f}s, "
          f"{len(cache)} unique functions compiled/run")

    with open("verify_results.json", "w") as f:
        json.dump({cid: edges for cid, edges in results.items()}, f, indent=2)
    with open("verify_function_cache.json", "w") as f:
        json.dump(cache, f, indent=2)

    print("\n=== summary ===")
    for cid, edges in sorted(results.items(), key=lambda kv: -len(kv[1])):
        n = len(edges)
        v = sum(1 for e in edges if e["verdict"] == "VERIFIED")
        m = sum(1 for e in edges if e["verdict"] == "MISLABELED")
        u = sum(1 for e in edges if e["verdict"] == "UNVERIFIABLE")
        print(f"cluster {cid}: n={n} VERIFIED={v} MISLABELED={m} UNVERIFIABLE={u} "
              f"wrong_rate_of_verifiable={m/(v+m) if (v+m) else float('nan'):.3f}")


if __name__ == "__main__":
    main()
