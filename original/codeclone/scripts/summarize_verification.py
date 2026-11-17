"""
Summarize verify_results.json: per-cluster and aggregate counts, wrong-label rate
with Wilson score confidence intervals, and write out three cleaned dataset files
(verified / mislabeled / unverifiable pairs) as JSON.
"""
import json
import math

CLUSTER_EDGE_TOTALS = {
    # from scope_pairs.py: total within-cluster positive edges in train.txt
    "10447015": 366944, "13771944": 64398, "17102809": 18432, "2450": 1044,
    "22634542": 18, "1829463": 12, "23677151": 12, "23295333": 2,
}


def wilson_ci(x, n, z=1.96):
    if n == 0:
        return (float("nan"), float("nan"))
    phat = x / n
    denom = 1 + z * z / n
    center = (phat + z * z / (2 * n)) / denom
    margin = (z * math.sqrt(phat * (1 - phat) / n + z * z / (4 * n * n))) / denom
    return (max(0, center - margin), min(1, center + margin))


def main():
    with open("verify_results.json") as f:
        results = json.load(f)

    verified, mislabeled, unverifiable = [], [], []
    print(f"{'cluster':>12} {'n':>5} {'VER':>5} {'MIS':>5} {'UNV':>5} "
          f"{'wrong_rate':>11} {'95% CI':>20} {'total_edges':>12}")
    agg_v, agg_m = 0, 0
    for cid, edges in results.items():
        v = [e for e in edges if e["verdict"] == "VERIFIED"]
        m = [e for e in edges if e["verdict"] == "MISLABELED"]
        u = [e for e in edges if e["verdict"] == "UNVERIFIABLE"]
        for e in v:
            verified.append({**e, "cluster": cid})
        for e in m:
            mislabeled.append({**e, "cluster": cid})
        for e in u:
            unverifiable.append({**e, "cluster": cid})

        n_vm = len(v) + len(m)
        rate = len(m) / n_vm if n_vm else float("nan")
        lo, hi = wilson_ci(len(m), n_vm)
        ci_str = f"[{lo:.2f},{hi:.2f}]" if n_vm else "n/a"
        agg_v += len(v)
        agg_m += len(m)
        print(f"{cid:>12} {len(edges):>5} {len(v):>5} {len(m):>5} {len(u):>5} "
              f"{rate:>11.3f} {ci_str:>20} {CLUSTER_EDGE_TOTALS.get(cid, 0):>12}")

    n_vm_total = agg_v + agg_m
    rate_total = agg_m / n_vm_total if n_vm_total else float("nan")
    lo, hi = wilson_ci(agg_m, n_vm_total)
    print(f"\nAGGREGATE over verifiable pairs: n={n_vm_total} VERIFIED={agg_v} "
          f"MISLABELED={agg_m} wrong_rate={rate_total:.3f} 95%CI=[{lo:.3f},{hi:.3f}]")
    print(f"Total sampled: {len(verified)+len(mislabeled)+len(unverifiable)} "
          f"(verified={len(verified)}, mislabeled={len(mislabeled)}, unverifiable={len(unverifiable)})")

    with open("clonebench_verified_pairs.json", "w") as f:
        json.dump([{"idx_a": e["a"], "idx_b": e["b"], "cluster": e["cluster"]} for e in verified], f, indent=2)
    with open("clonebench_mislabeled_pairs.json", "w") as f:
        json.dump([
            {"idx_a": e["a"], "idx_b": e["b"], "cluster": e["cluster"],
             "outputs_a": e["outputs_a"], "outputs_b": e["outputs_b"]}
            for e in mislabeled
        ], f, indent=2)
    with open("clonebench_unverifiable_pairs.json", "w") as f:
        json.dump([
            {"idx_a": e["a"], "idx_b": e["b"], "cluster": e["cluster"],
             "reason_a": e.get("reason_a"), "reason_b": e.get("reason_b")}
            for e in unverifiable
        ], f, indent=2)

    print(f"\nwrote clonebench_verified_pairs.json ({len(verified)} pairs)")
    print(f"wrote clonebench_mislabeled_pairs.json ({len(mislabeled)} pairs)")
    print(f"wrote clonebench_unverifiable_pairs.json ({len(unverifiable)} pairs)")


if __name__ == "__main__":
    main()
