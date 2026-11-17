"""
Cross-check both verification paths (independent type-driven, EvoSuite-reuse)
against the paper's own human 3-judge consensus (verifiedpairs.consensus).

Reports:
 - overall verdict distribution per path, and per consensus value
 - agreement rate (restricted to pairs where the verifier reached a definite
   VERIFIED/MISLABELED verdict -- UNVERIFIABLE pairs are reported separately,
   not counted as agreement or disagreement)
 - confusion matrix per path
 - concrete disagreement examples with actual source code, categorized by
   return type, to check whether disagreements cluster around string/boolean
   returns as the paper itself flags
"""
import json
from collections import Counter, defaultdict

from fempd_common import connect, load_method


def load_jsonl(path):
    return [json.loads(l) for l in open(path)]


def confusion(rows):
    """rows: list of dicts with 'verdict' and 'consensus'. Only counts rows
    with a definite verdict (VERIFIED/MISLABELED)."""
    definite = [r for r in rows if r["verdict"] in ("VERIFIED", "MISLABELED")]
    unverifiable = len(rows) - len(definite)
    tp = sum(1 for r in definite if r["verdict"] == "VERIFIED" and r["consensus"] == 1)
    fp = sum(1 for r in definite if r["verdict"] == "VERIFIED" and r["consensus"] == 0)
    fn = sum(1 for r in definite if r["verdict"] == "MISLABELED" and r["consensus"] == 1)
    tn = sum(1 for r in definite if r["verdict"] == "MISLABELED" and r["consensus"] == 0)
    agree = tp + tn
    n = len(definite)
    return {
        "n_definite": n, "n_unverifiable": unverifiable,
        "tp_verified_and_human_equiv": tp,
        "fp_verified_but_human_nonequiv": fp,
        "fn_mislabeled_but_human_equiv": fn,
        "tn_mislabeled_and_human_nonequiv": tn,
        "agreement_rate": agree / n if n else float("nan"),
    }


def categorize_return_type(conn, method_id):
    m = load_method(conn, method_id)
    if not m or not m["rtext"]:
        return "unknown"
    rtext = m["rtext"].strip()
    first_line = rtext.split("(")[0]
    tokens = first_line.split()
    if not tokens:
        return "unknown"
    ret = tokens[-2] if len(tokens) >= 2 else "unknown"
    if ret in ("boolean", "Boolean"):
        return "boolean"
    if ret == "String":
        return "String"
    if ret == "void":
        return "void"
    if ret.endswith("[]"):
        return "array"
    if ret in ("int", "long", "double", "float", "Integer", "Long", "Double", "Float"):
        return "numeric"
    return "other:" + ret


def main():
    conn = connect()
    indep = load_jsonl("fempd_independent_results.jsonl")
    evo = load_jsonl("fempd_evosuite_results.jsonl")

    for name, rows in [("independent (type-driven)", indep), ("evosuite-reuse", evo)]:
        print(f"\n===== {name} =====")
        print("overall:", Counter(r["verdict"] for r in rows))
        c = confusion(rows)
        print(f"agreement rate (of {c['n_definite']} definite verdicts): {c['agreement_rate']:.3f}")
        print(f"  VERIFIED & human=equivalent (agree):      {c['tp_verified_and_human_equiv']}")
        print(f"  VERIFIED & human=non-equivalent (DISAGREE): {c['fp_verified_but_human_nonequiv']}")
        print(f"  MISLABELED & human=equivalent (DISAGREE):   {c['fn_mislabeled_but_human_equiv']}")
        print(f"  MISLABELED & human=non-equivalent (agree):  {c['tn_mislabeled_and_human_nonequiv']}")
        print(f"  unverifiable (excluded from above): {c['n_unverifiable']}")

    # disagreement examples + return-type clustering, for the evosuite path
    # (the one with the striking specificity problem) and the independent path
    for name, rows in [("independent", indep), ("evosuite-reuse", evo)]:
        print(f"\n===== {name}: disagreement return-type breakdown =====")
        fp_types = Counter()  # verifier says equiv, human says not
        fn_types = Counter()  # verifier says non-equiv, human says equiv
        fp_examples, fn_examples = [], []
        for r in rows:
            if r["verdict"] not in ("VERIFIED", "MISLABELED"):
                continue
            rt = categorize_return_type(conn, r["left"])
            if r["verdict"] == "VERIFIED" and r["consensus"] == 0:
                fp_types[rt] += 1
                if len(fp_examples) < 5:
                    fp_examples.append(r)
            elif r["verdict"] == "MISLABELED" and r["consensus"] == 1:
                fn_types[rt] += 1
                if len(fn_examples) < 5:
                    fn_examples.append(r)
        print("false VERIFIED (verifier says equiv, human says not) by return type:", dict(fp_types))
        print("false MISLABELED (verifier says non-equiv, human says equiv) by return type:", dict(fn_types))

        with open(f"fempd_{name}_disagreements.json", "w") as f:
            out = {"false_verified_examples": [], "false_mislabeled_examples": []}
            for r in fp_examples:
                ml, mr = load_method(conn, r["left"]), load_method(conn, r["right"])
                out["false_verified_examples"].append({
                    **r, "left_code": ml["rtext"], "right_code": mr["rtext"],
                })
            for r in fn_examples:
                ml, mr = load_method(conn, r["left"]), load_method(conn, r["right"])
                out["false_mislabeled_examples"].append({
                    **r, "left_code": ml["rtext"], "right_code": mr["rtext"],
                })
            json.dump(out, f, indent=2)
        print(f"wrote fempd_{name}_disagreements.json")


if __name__ == "__main__":
    main()
