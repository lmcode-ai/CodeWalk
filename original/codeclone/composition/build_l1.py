"""
Step 1: format L1 = single verified FEMPD pairs, both classes.
Positive: fempd_verified_pairs.json (994, both paths agree VERIFIED).
Negative: fempd_verified_negative_pairs.json (159, at least one path confirmed
a concrete divergence) -- included so L1 is a meaningful balanced-class problem
set for the difficulty eval and for Runyuan's training data, not positive-only.
This inclusion is an interpretive addition beyond the handoff's literal "no new
work needed" note -- documented in the final summary.
"""
import json
import sys

sys.path.insert(0, "../fempd")
import fempd_common
fempd_common.DB_PATH = "../fempd/ijadataset.db"
from fempd_common import connect, load_method


def main():
    conn = connect()
    pos = json.load(open("../fempd/fempd_verified_pairs.json"))
    neg = json.load(open("../fempd/fempd_verified_negative_pairs.json"))

    problems = []
    for p in pos:
        ma, mb = load_method(conn, p["idx_a"]), load_method(conn, p["idx_b"])
        problems.append({
            "id": f"l1_pos_{p['pairid']}", "level": 1, "label": "equivalent",
            "side_a_code": ma["rtext"], "side_b_code": mb["rtext"],
            "source": "fempd_verified_pairs", "pairid": p["pairid"],
        })
    for p in neg:
        ma, mb = load_method(conn, p["idx_a"]), load_method(conn, p["idx_b"])
        problems.append({
            "id": f"l1_neg_{p['pairid']}", "level": 1, "label": "not_equivalent",
            "side_a_code": ma["rtext"], "side_b_code": mb["rtext"],
            "source": "fempd_verified_negative_pairs", "pairid": p["pairid"],
        })

    with open("l1_full.json", "w") as f:
        json.dump(problems, f, indent=2)
    print(f"L1 total: {len(problems)} ({len(pos)} equivalent, {len(neg)} not_equivalent)")


if __name__ == "__main__":
    main()
