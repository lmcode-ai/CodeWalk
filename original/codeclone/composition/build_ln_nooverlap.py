"""
No-overlap variant of build_ln.py, built to directly answer a methodological
concern raised in a lab meeting: that reusing the same small pool of
confirmed-non-equivalent "atoms" as the injected divergent component across
many different levels could let a model's accuracy reflect memorization/
pattern-recognition of a specific repeated snippet rather than genuine
per-instance equivalence judgment, and that this could be inflating or
otherwise distorting the depth-vs-accuracy trend.

Fix: partition the 127 usable negative atoms (negative_atom_buckets_nooverlap.json,
seed 42) into 10 disjoint per-level buckets ahead of time. Each level's
negative compositions draw their injected atom ONLY from that level's own
bucket -- no atom is ever used at two different levels. Positive-side
sampling is unrestricted (994-pair pool, no cross-level uniqueness
guarantee attempted -- earlier analysis found no confound-controlled reuse
effect there, and full disjointness isn't feasible: L10 alone needs up to
450 distinct positive pairs for its own within-level uniqueness).

Per-level target is capped at the bucket size (12 or 13) rather than 45, so
every level is exactly balanced (n positive == n negative == bucket size)
and no atom is EVER reused across levels by construction, not by post-hoc
statistical control.

Usage: python3 build_ln_nooverlap.py <N>   (N in 2..10; L1 handled separately)
"""
import json
import random
import sys
import time

sys.path.insert(0, "../fempd")
import fempd_common
fempd_common.DB_PATH = "../fempd/ijadataset.db"
from fempd_common import connect, load_method

from composition_common import parse_component, verify_composition
from build_ln import get_component_cache

MAX_ATTEMPTS_MULT = 30


def build_level_nooverlap(n, bucket, seed):
    conn = connect()
    pos_pool = json.load(open("../fempd/fempd_verified_pairs.json"))
    neg_pool = bucket  # ONLY this level's assigned atoms -- no cross-level overlap

    comp_cache = get_component_cache(conn, pos_pool)
    comp_cache.update(get_component_cache(conn, neg_pool))
    pos_pool = [p for p in pos_pool if comp_cache.get(p["idx_a"]) and comp_cache.get(p["idx_b"])]
    neg_pool = [p for p in neg_pool if comp_cache.get(p["idx_a"]) and comp_cache.get(p["idx_b"])]

    target = len(neg_pool)  # exactly balanced, capped at this level's bucket size
    rng = random.Random(seed)
    accepted_pos, accepted_neg, dropped = [], [], []
    start = time.time()
    max_attempts = max(target * MAX_ATTEMPTS_MULT, 200)

    attempts = 0
    used_combos = set()
    while len(accepted_pos) < target and attempts < max_attempts:
        attempts += 1
        chosen = rng.sample(pos_pool, n)
        combo_key = tuple(sorted(p["pairid"] for p in chosen))
        if combo_key in used_combos:
            continue
        used_combos.add(combo_key)
        comps1 = [comp_cache[p["idx_a"]] for p in chosen]
        comps2 = [comp_cache[p["idx_b"]] for p in chosen]
        tag = f"l{n}_pos_{'_'.join(str(p['pairid']) for p in chosen)}"
        res = verify_composition(comps1, comps2, tag)
        if res["verdict"] == "VERIFIED":
            accepted_pos.append({
                "l_id": tag, "component_pairids": [p["pairid"] for p in chosen],
                "side_a_idxs": [p["idx_a"] for p in chosen],
                "side_b_idxs": [p["idx_b"] for p in chosen],
            })
        else:
            dropped.append({"kind": f"l{n}_positive", "tag": tag,
                             "component_pairids": [p["pairid"] for p in chosen],
                             "verdict": res["verdict"], "detail": res})

    # every atom in this level's bucket is used exactly once as the injected
    # negative component (bucket size == target), each paired with a fresh
    # random set of n-1 positive partners
    attempts = 0
    used_combos_neg = set()
    neg_atoms_remaining = list(neg_pool)
    rng.shuffle(neg_atoms_remaining)
    for pn in neg_atoms_remaining:
        placed = False
        local_attempts = 0
        while not placed and local_attempts < MAX_ATTEMPTS_MULT:
            local_attempts += 1
            attempts += 1
            chosen_pos = rng.sample(pos_pool, n - 1)
            combo_key = tuple(sorted(p["pairid"] for p in chosen_pos)) + (pn["pairid"],)
            if combo_key in used_combos_neg:
                continue
            used_combos_neg.add(combo_key)

            slot1 = [comp_cache[p["idx_a"]] for p in chosen_pos] + [comp_cache[pn["idx_a"]]]
            slot2 = [comp_cache[p["idx_b"]] for p in chosen_pos] + [comp_cache[pn["idx_b"]]]
            neg_pos = rng.randint(0, n - 1)
            order = [i for i in range(n) if i != n - 1]
            order.insert(neg_pos, n - 1)
            side1 = [slot1[i] for i in order]
            side2 = [slot2[i] for i in order]

            pairids = [p["pairid"] for p in chosen_pos] + [pn["pairid"]]
            tag = f"l{n}_neg_{'_'.join(str(x) for x in pairids)}_pos{neg_pos}"
            res = verify_composition(side1, side2, tag)
            if res["verdict"] == "MISLABELED":
                idxs1 = [p["idx_a"] for p in chosen_pos] + [pn["idx_a"]]
                idxs2 = [p["idx_b"] for p in chosen_pos] + [pn["idx_b"]]
                accepted_neg.append({
                    "l_id": tag, "component_pairids": pairids, "neg_position": neg_pos,
                    "side_a_idxs": [idxs1[i] for i in order],
                    "side_b_idxs": [idxs2[i] for i in order],
                })
                placed = True
            else:
                dropped.append({"kind": f"l{n}_negative", "tag": tag,
                                 "component_pairids": pairids,
                                 "verdict": res["verdict"], "detail": res})

    print(f"L{n}: pos {len(accepted_pos)}/{target} accepted, "
          f"neg {len(accepted_neg)}/{target} accepted (every bucket atom used once), "
          f"dropped {len(dropped)}, elapsed {time.time()-start:.0f}s", file=sys.stderr)

    with open(f"l{n}_nooverlap_accepted_positive.json", "w") as f:
        json.dump(accepted_pos, f, indent=2)
    with open(f"l{n}_nooverlap_accepted_negative.json", "w") as f:
        json.dump(accepted_neg, f, indent=2)
    with open(f"l{n}_nooverlap_dropped.json", "w") as f:
        json.dump(dropped, f, indent=2, default=str)

    return accepted_pos, accepted_neg, dropped


if __name__ == "__main__":
    n = int(sys.argv[1])
    buckets = json.load(open("negative_atom_buckets_nooverlap.json"))
    bucket = buckets[n - 1]
    build_level_nooverlap(n, bucket, seed=1000 + n)
