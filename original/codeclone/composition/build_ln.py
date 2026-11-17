"""
Generic N-component composition builder, for the 1-10 level difficulty-trend
sweep (supersedes the fixed TARGET=350 per-level scale of build_l2.py/
build_l3.py for this smaller-scale, more-levels experiment).

  Positive: N distinct verified pairs from the FEMPD positive pool.
  Negative: N-1 verified pairs + 1 confirmed-non-equivalent pair from the
            negative pool, inserted at a random position among the N slots.

Same execution-verification discipline as L2/L3: every composition is
compiled, run, and compared -- accepted only if the outcome matches
expectation, never assumed from the rule.

Usage: python3 build_ln.py <N> [target_per_class]
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

MAX_ATTEMPTS_MULT = 20  # generous headroom; at this pool size/N, collisions are rare


def get_component_cache(conn, pool):
    cache = {}
    for p in pool:
        for idx in (p["idx_a"], p["idx_b"]):
            if idx not in cache:
                m = load_method(conn, idx)
                cache[idx] = parse_component(m["rtext"]) if m else None
    return cache


def build_level(n, target_per_class, seed):
    conn = connect()
    pos_pool = json.load(open("../fempd/fempd_verified_pairs.json"))
    neg_pool_all = json.load(open("../fempd/fempd_verified_negative_pairs.json"))
    neg_pool = [p for p in neg_pool_all if p["independent_verdict"] == "MISLABELED"]

    comp_cache = get_component_cache(conn, pos_pool)
    comp_cache.update(get_component_cache(conn, neg_pool))
    pos_pool = [p for p in pos_pool if comp_cache.get(p["idx_a"]) and comp_cache.get(p["idx_b"])]
    neg_pool = [p for p in neg_pool if comp_cache.get(p["idx_a"]) and comp_cache.get(p["idx_b"])]

    rng = random.Random(seed)
    accepted_pos, accepted_neg, dropped = [], [], []
    start = time.time()
    max_attempts = max(target_per_class * MAX_ATTEMPTS_MULT, 200)

    # --- positive: N distinct verified pairs ---
    attempts = 0
    used_combos = set()
    while len(accepted_pos) < target_per_class and attempts < max_attempts:
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

    # --- negative: N-1 verified pairs + 1 negative-pool pair, random position ---
    attempts = 0
    used_combos_neg = set()
    while len(accepted_neg) < target_per_class and attempts < max_attempts:
        attempts += 1
        chosen_pos = rng.sample(pos_pool, n - 1)
        pn = rng.choice(neg_pool)
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
        else:
            dropped.append({"kind": f"l{n}_negative", "tag": tag,
                             "component_pairids": pairids,
                             "verdict": res["verdict"], "detail": res})

    print(f"L{n}: pos {len(accepted_pos)}/{target_per_class} accepted, "
          f"neg {len(accepted_neg)}/{target_per_class} accepted, "
          f"dropped {len(dropped)}, elapsed {time.time()-start:.0f}s", file=sys.stderr)

    with open(f"l{n}_accepted_positive.json", "w") as f:
        json.dump(accepted_pos, f, indent=2)
    with open(f"l{n}_accepted_negative.json", "w") as f:
        json.dump(accepted_neg, f, indent=2)
    with open(f"l{n}_dropped.json", "w") as f:
        json.dump(dropped, f, indent=2, default=str)

    return accepted_pos, accepted_neg, dropped


if __name__ == "__main__":
    n = int(sys.argv[1])
    target = int(sys.argv[2]) if len(sys.argv) > 2 else 10
    seed = n  # distinct, reproducible seed per level
    build_level(n, target, seed)
