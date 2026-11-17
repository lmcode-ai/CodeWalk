"""
Produce the final cleaned FEMPD dataset, combining both verification paths for
the strongest signal (per handoff: "do BOTH for the strongest result"):

  VERIFIED     -- both independent and evosuite-reuse paths say VERIFIED
  MISLABELED   -- either path found a concrete divergence (MISLABELED) --
                  a single confirmed divergence disqualifies the pair regardless
                  of what the other path found
  UNVERIFIABLE -- everything else (at least one path inconclusive, neither found
                  a concrete divergence)

Restricted to consensus=1 (claimed-equivalent) pairs, matching the actual
L1-candidate purpose -- same output format as the BigCloneBench pass.
"""
import json

from fempd_common import connect, load_method


def load_jsonl(path):
    return {json.loads(l)["pairid"]: json.loads(l) for l in open(path)}


def main():
    conn = connect()
    indep = load_jsonl("fempd_independent_results.jsonl")
    evo = load_jsonl("fempd_evosuite_results.jsonl")

    pos_pairids = [pid for pid, r in indep.items() if r["consensus"] == 1]

    verified, mislabeled, unverifiable = [], [], []
    for pid in pos_pairids:
        ri, re_ = indep[pid], evo[pid]
        vi, ve = ri["verdict"], re_["verdict"]
        row = {
            "pairid": pid, "idx_a": ri["left"], "idx_b": ri["right"],
            "independent_verdict": vi, "evosuite_verdict": ve,
        }
        if vi == "MISLABELED" or ve == "MISLABELED":
            mislabeled.append(row)
        elif vi == "VERIFIED" and ve == "VERIFIED":
            verified.append(row)
        else:
            row["independent_reason"] = ri.get("reason_a") or ri.get("reason_b")
            row["evosuite_reason"] = re_.get("reason_d1") or re_.get("reason_d2")
            unverifiable.append(row)

    with open("fempd_verified_pairs.json", "w") as f:
        json.dump(verified, f, indent=2)
    with open("fempd_mislabeled_pairs.json", "w") as f:
        json.dump(mislabeled, f, indent=2)
    with open("fempd_unverifiable_pairs.json", "w") as f:
        json.dump(unverifiable, f, indent=2)

    print(f"consensus=1 total: {len(pos_pairids)}")
    print(f"VERIFIED (both paths agree): {len(verified)}")
    print(f"MISLABELED (either path found divergence): {len(mislabeled)}")
    print(f"UNVERIFIABLE (inconclusive): {len(unverifiable)}")


if __name__ == "__main__":
    main()
