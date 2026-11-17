"""
Render accepted L2/L3 compositions (which store component idxs) into full
problem records matching L1's schema: {id, level, label, side_a_code,
side_b_code, source, component_pairids}. side_X_code is the plain composed
Java source (component classes + outer() method) -- no test-harness/Driver
scaffolding, since that's verification-internal, not part of the problem.
"""
import json
import sys

sys.path.insert(0, "../fempd")
import fempd_common
fempd_common.DB_PATH = "../fempd/ijadataset.db"
from fempd_common import connect, load_method

from composition_common import parse_component, build_composition_source


def render_side(conn, idxs):
    comps = [parse_component(load_method(conn, idx)["rtext"]) for idx in idxs]
    src, _ = build_composition_source(comps)
    return src


def render_level(conn, level, accepted_pos_path, accepted_neg_path, out_path):
    pos = json.load(open(accepted_pos_path))
    neg = json.load(open(accepted_neg_path))
    problems = []
    for p in pos:
        problems.append({
            "id": f"l{level}_pos_{'_'.join(str(x) for x in p['component_pairids'])}",
            "level": level, "label": "equivalent",
            "side_a_code": render_side(conn, p["side_a_idxs"]),
            "side_b_code": render_side(conn, p["side_b_idxs"]),
            "source": f"l{level}_accepted_positive", "component_pairids": p["component_pairids"],
        })
    for p in neg:
        problems.append({
            "id": f"l{level}_neg_{'_'.join(str(x) for x in p['component_pairids'])}",
            "level": level, "label": "not_equivalent",
            "side_a_code": render_side(conn, p["side_a_idxs"]),
            "side_b_code": render_side(conn, p["side_b_idxs"]),
            "source": f"l{level}_accepted_negative", "component_pairids": p["component_pairids"],
        })
    with open(out_path, "w") as f:
        json.dump(problems, f, indent=2)
    print(f"L{level}: {len(problems)} total ({len(pos)} equivalent, {len(neg)} not_equivalent) -> {out_path}")
    return problems


def main():
    conn = connect()
    render_level(conn, 2, "l2_accepted_positive.json", "l2_accepted_negative.json", "l2_full.json")
    render_level(conn, 3, "l3_accepted_positive.json", "l3_accepted_negative.json", "l3_full.json")


if __name__ == "__main__":
    main()
