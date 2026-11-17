"""
Option (a): independent verification of FEMPD pairs using the same type-driven
test generation / compile / execute / compare approach as the BigCloneBench pass.
Reuses clone_verifier.py's compile+run+compare logic directly (it's generic Java
method verification, not BigCloneBench-specific) -- only the data source differs.

Processes consensus=1 (claimed-equivalent) pairs first since that's the priority
deliverable, then consensus=0 pairs for the full cross-check. Writes results
incrementally (one JSON line per pair) so a long run can be safely interrupted.
"""
import json
import sys
import time

sys.path.insert(0, "../scripts")
import clone_verifier
clone_verifier.WORK_DIR = "fempd_verify_work_independent"

from fempd_common import connect, load_verifiedpairs, load_method

OUT_PATH = "fempd_independent_results.jsonl"


def main():
    conn = connect()
    edges = load_verifiedpairs(conn)
    edges.sort(key=lambda e: -e["consensus"])  # consensus=1 first

    funcs = {}
    cache = {}
    start = time.time()
    with open(OUT_PATH, "w") as out:
        for i, e in enumerate(edges):
            left, right = e["left"], e["right"]
            m_left = load_method(conn, left)
            m_right = load_method(conn, right)

            reasons = {}
            skip = False
            for side, m in (("left", m_left), ("right", m_right)):
                if m is None:
                    reasons[side] = "fempd_method_missing"
                    skip = True
                elif m["compilable"] != 1:
                    reasons[side] = f"fempd_not_compilable:{m['compilable']}"
                    skip = True

            if skip:
                row = {
                    "pairid": e["pairid"], "left": left, "right": right,
                    "consensus": e["consensus"], "verdict": "UNVERIFIABLE",
                    "reason_a": reasons.get("left"), "reason_b": reasons.get("right"),
                }
            else:
                sleft, sright = str(left), str(right)
                funcs[sleft] = m_left["rtext"]
                funcs[sright] = m_right["rtext"]
                res = clone_verifier.compare_pair(sleft, sright, funcs, cache)
                row = {"pairid": e["pairid"], "left": left, "right": right,
                       "consensus": e["consensus"], **res}

            out.write(json.dumps(row) + "\n")
            out.flush()

            if (i + 1) % 100 == 0:
                elapsed = time.time() - start
                print(f"  [{i+1}/{len(edges)}] elapsed={elapsed:.0f}s", file=sys.stderr)

    print(f"done: {len(edges)} pairs in {time.time()-start:.0f}s")


if __name__ == "__main__":
    main()
