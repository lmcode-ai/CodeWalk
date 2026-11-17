"""
Step 3: build L3 = compositions of 3 components.
  Positive: 3 distinct verified pairs from the FEMPD positive pool.
  Negative: 2 verified pairs + 1 confirmed-non-equivalent pair from the negative
            pool, inserted at a random position among the 3 slots.
Same execution-verification discipline as L2 -- every composition is compiled,
run, and compared; accepted only if the outcome matches expectation.
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
from build_l2 import get_component_cache

SEED = 1
TARGET_POS = 350
TARGET_NEG = 350
MAX_ATTEMPTS_POS = 700
MAX_ATTEMPTS_NEG = 700


def main():
    conn = connect()
    pos_pool = json.load(open("../fempd/fempd_verified_pairs.json"))
    neg_pool_all = json.load(open("../fempd/fempd_verified_negative_pairs.json"))
    neg_pool = [p for p in neg_pool_all if p["independent_verdict"] == "MISLABELED"]

    comp_cache = get_component_cache(conn, pos_pool)
    comp_cache.update(get_component_cache(conn, neg_pool))
    pos_pool = [p for p in pos_pool if comp_cache.get(p["idx_a"]) and comp_cache.get(p["idx_b"])]
    neg_pool = [p for p in neg_pool if comp_cache.get(p["idx_a"]) and comp_cache.get(p["idx_b"])]
    print(f"positive pool: {len(pos_pool)}, negative pool (composable): {len(neg_pool)}")

    rng = random.Random(SEED)
    accepted_pos, accepted_neg, dropped = [], [], []
    start = time.time()

    # --- positive: 3 distinct verified pairs ---
    attempts = 0
    used_combos = set()
    while len(accepted_pos) < TARGET_POS and attempts < MAX_ATTEMPTS_POS:
        attempts += 1
        pa, pb, pc = rng.sample(pos_pool, 3)
        combo_key = tuple(sorted([pa["pairid"], pb["pairid"], pc["pairid"]]))
        if combo_key in used_combos:
            continue
        used_combos.add(combo_key)

        comps1 = [comp_cache[p["idx_a"]] for p in (pa, pb, pc)]
        comps2 = [comp_cache[p["idx_b"]] for p in (pa, pb, pc)]
        tag = f"l3_pos_{pa['pairid']}_{pb['pairid']}_{pc['pairid']}"
        res = verify_composition(comps1, comps2, tag)
        if res["verdict"] == "VERIFIED":
            accepted_pos.append({
                "l3_id": tag, "component_pairids": [pa["pairid"], pb["pairid"], pc["pairid"]],
                "side_a_idxs": [pa["idx_a"], pb["idx_a"], pc["idx_a"]],
                "side_b_idxs": [pa["idx_b"], pb["idx_b"], pc["idx_b"]],
            })
        else:
            dropped.append({"kind": "l3_positive", "tag": tag,
                             "component_pairids": [pa["pairid"], pb["pairid"], pc["pairid"]],
                             "verdict": res["verdict"], "detail": res})
        if attempts % 50 == 0:
            print(f"  [pos {attempts}/{MAX_ATTEMPTS_POS}] accepted={len(accepted_pos)} "
                  f"elapsed={time.time()-start:.0f}s", file=sys.stderr)

    # --- negative: 2 verified pairs + 1 negative-pool pair, random position ---
    attempts = 0
    used_combos_neg = set()
    while len(accepted_neg) < TARGET_NEG and attempts < MAX_ATTEMPTS_NEG:
        attempts += 1
        pa, pb = rng.sample(pos_pool, 2)
        pn = rng.choice(neg_pool)
        combo_key = (pa["pairid"], pb["pairid"], pn["pairid"])
        if combo_key in used_combos_neg:
            continue
        used_combos_neg.add(combo_key)

        pos_a1, pos_a2 = comp_cache[pa["idx_a"]], comp_cache[pa["idx_b"]]
        pos_b1, pos_b2 = comp_cache[pb["idx_a"]], comp_cache[pb["idx_b"]]
        n1, n2 = comp_cache[pn["idx_a"]], comp_cache[pn["idx_b"]]

        slot1 = [pos_a1, pos_b1, n1]
        slot2 = [pos_a2, pos_b2, n2]
        neg_pos = rng.randint(0, 2)
        # rotate so the negative component lands at neg_pos
        order = [i for i in range(3) if i != 2]
        order.insert(neg_pos, 2)
        side1 = [slot1[i] for i in order]
        side2 = [slot2[i] for i in order]

        tag = f"l3_neg_{pa['pairid']}_{pb['pairid']}_{pn['pairid']}_pos{neg_pos}"
        res = verify_composition(side1, side2, tag)
        if res["verdict"] == "MISLABELED":
            idxs1 = [pa["idx_a"], pb["idx_a"], pn["idx_a"]]
            idxs2 = [pa["idx_b"], pb["idx_b"], pn["idx_b"]]
            accepted_neg.append({
                "l3_id": tag, "component_pairids": [pa["pairid"], pb["pairid"], pn["pairid"]],
                "neg_position": neg_pos,
                "side_a_idxs": [idxs1[i] for i in order],
                "side_b_idxs": [idxs2[i] for i in order],
            })
        else:
            dropped.append({"kind": "l3_negative", "tag": tag,
                             "component_pairids": [pa["pairid"], pb["pairid"], pn["pairid"]],
                             "verdict": res["verdict"], "detail": res})
        if attempts % 50 == 0:
            print(f"  [neg {attempts}/{MAX_ATTEMPTS_NEG}] accepted={len(accepted_neg)} "
                  f"elapsed={time.time()-start:.0f}s", file=sys.stderr)

    with open("l3_accepted_positive.json", "w") as f:
        json.dump(accepted_pos, f, indent=2)
    with open("l3_accepted_negative.json", "w") as f:
        json.dump(accepted_neg, f, indent=2)
    with open("l3_dropped.json", "w") as f:
        json.dump(dropped, f, indent=2, default=str)

    print(f"\ndone in {time.time()-start:.0f}s")
    print(f"positive: {len(accepted_pos)} accepted")
    print(f"negative: {len(accepted_neg)} accepted")
    print(f"dropped: {len(dropped)}")


if __name__ == "__main__":
    main()
