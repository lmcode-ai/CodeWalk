"""
Step 2: build L2 = compositions of 2 components.
  Positive: 2 distinct verified pairs from the FEMPD positive pool.
  Negative: 1 verified pair + 1 confirmed-non-equivalent pair from the negative
            pool (position randomized), expecting the composition to flip.
Every composition is empirically compiled/run/compared (not assumed from the
rule) -- accepted only if the execution outcome matches what's expected;
otherwise dropped and logged with the reason.
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

SEED = 0
TARGET_POS = 350
TARGET_NEG = 350
MAX_ATTEMPTS_POS = 600
MAX_ATTEMPTS_NEG = 600


def get_component_cache(conn, pool):
    """Parse every method referenced in pool once, cache by idx."""
    cache = {}
    for p in pool:
        for idx in (p["idx_a"], p["idx_b"]):
            if idx not in cache:
                m = load_method(conn, idx)
                cache[idx] = parse_component(m["rtext"]) if m else None
    return cache


def main():
    conn = connect()
    pos_pool = json.load(open("../fempd/fempd_verified_pairs.json"))
    neg_pool_all = json.load(open("../fempd/fempd_verified_negative_pairs.json"))
    neg_pool = [p for p in neg_pool_all if p["independent_verdict"] == "MISLABELED"]
    print(f"positive pool: {len(pos_pool)}, negative pool (composable): {len(neg_pool)}")

    comp_cache = get_component_cache(conn, pos_pool)
    comp_cache.update(get_component_cache(conn, neg_pool))
    # drop pool entries whose components failed to parse (shouldn't happen given
    # the L1 verifier already required supported types, but check defensively)
    pos_pool = [p for p in pos_pool if comp_cache.get(p["idx_a"]) and comp_cache.get(p["idx_b"])]
    neg_pool = [p for p in neg_pool if comp_cache.get(p["idx_a"]) and comp_cache.get(p["idx_b"])]
    print(f"after parse filter -- positive: {len(pos_pool)}, negative: {len(neg_pool)}")

    rng = random.Random(SEED)
    accepted_pos, accepted_neg, dropped = [], [], []
    start = time.time()

    # --- positive ---
    attempts = 0
    used_combos = set()
    while len(accepted_pos) < TARGET_POS and attempts < MAX_ATTEMPTS_POS:
        attempts += 1
        pa, pb = rng.sample(pos_pool, 2)
        combo_key = tuple(sorted([pa["pairid"], pb["pairid"]]))
        if combo_key in used_combos:
            continue
        used_combos.add(combo_key)

        a1, a2 = comp_cache[pa["idx_a"]], comp_cache[pa["idx_b"]]
        b1, b2 = comp_cache[pb["idx_a"]], comp_cache[pb["idx_b"]]
        tag = f"l2_pos_{pa['pairid']}_{pb['pairid']}"
        res = verify_composition([a1, b1], [a2, b2], tag)
        if res["verdict"] == "VERIFIED":
            accepted_pos.append({
                "l2_id": tag, "component_pairids": [pa["pairid"], pb["pairid"]],
                "side_a_idxs": [pa["idx_a"], pb["idx_a"]],
                "side_b_idxs": [pa["idx_b"], pb["idx_b"]],
            })
        else:
            dropped.append({"kind": "l2_positive", "tag": tag,
                             "component_pairids": [pa["pairid"], pb["pairid"]],
                             "verdict": res["verdict"], "detail": res})
        if attempts % 50 == 0:
            print(f"  [pos {attempts}/{MAX_ATTEMPTS_POS}] accepted={len(accepted_pos)} "
                  f"elapsed={time.time()-start:.0f}s", file=sys.stderr)

    # --- negative ---
    attempts = 0
    used_combos_neg = set()
    while len(accepted_neg) < TARGET_NEG and attempts < MAX_ATTEMPTS_NEG:
        attempts += 1
        pa = rng.choice(pos_pool)
        pn = rng.choice(neg_pool)
        combo_key = (pa["pairid"], pn["pairid"])
        if combo_key in used_combos_neg:
            continue
        used_combos_neg.add(combo_key)

        a1, a2 = comp_cache[pa["idx_a"]], comp_cache[pa["idx_b"]]
        n1, n2 = comp_cache[pn["idx_a"]], comp_cache[pn["idx_b"]]
        neg_first = rng.random() < 0.5
        side1 = [n1, a1] if neg_first else [a1, n1]
        side2 = [n2, a2] if neg_first else [a2, n2]
        tag = f"l2_neg_{pa['pairid']}_{pn['pairid']}_{'nf' if neg_first else 'nl'}"
        res = verify_composition(side1, side2, tag)
        if res["verdict"] == "MISLABELED":
            accepted_neg.append({
                "l2_id": tag, "component_pairids": [pa["pairid"], pn["pairid"]],
                "neg_position": 0 if neg_first else 1,
                "side_a_idxs": [pn["idx_a"], pa["idx_a"]] if neg_first else [pa["idx_a"], pn["idx_a"]],
                "side_b_idxs": [pn["idx_b"], pa["idx_b"]] if neg_first else [pa["idx_b"], pn["idx_b"]],
            })
        else:
            dropped.append({"kind": "l2_negative", "tag": tag,
                             "component_pairids": [pa["pairid"], pn["pairid"]],
                             "verdict": res["verdict"], "detail": res})
        if attempts % 50 == 0:
            print(f"  [neg {attempts}/{MAX_ATTEMPTS_NEG}] accepted={len(accepted_neg)} "
                  f"elapsed={time.time()-start:.0f}s", file=sys.stderr)

    with open("l2_accepted_positive.json", "w") as f:
        json.dump(accepted_pos, f, indent=2)
    with open("l2_accepted_negative.json", "w") as f:
        json.dump(accepted_neg, f, indent=2)
    with open("l2_dropped.json", "w") as f:
        json.dump(dropped, f, indent=2, default=str)

    print(f"\ndone in {time.time()-start:.0f}s")
    print(f"positive: {len(accepted_pos)} accepted / {attempts if 'pos' else 0} range attempted")
    print(f"negative: {len(accepted_neg)} accepted")
    print(f"dropped: {len(dropped)}")


if __name__ == "__main__":
    main()
