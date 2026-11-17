"""
Retry only the true-infra-failure rows (scoreable == False) from a prior
difficulty_eval_10levels.py run -- for recovering from a provider-side outage
without re-spending the whole eval. Loads the existing results file, re-runs
classify() (with the improved multi-cause retry logic) for each failed row,
replaces it in place, and rewrites the file with recomputed per-level stats.

Usage:
    python3 retry_failed.py <provider> <model>
    # reads/writes the same difficulty_eval_10lvl_results_<slug>.json
    # that difficulty_eval_10levels.py produced for that model.
"""
import json
import sys

import difficulty_eval_10levels as ev

provider = sys.argv[1]
model = sys.argv[2]
assert provider == ev.PROVIDER and model == ev.MODEL, (
    "run as: python3 retry_failed.py <provider> <model>  (same argv contract as the main script)"
)


def main():
    results = json.load(open(ev.OUT_PATH))
    level_problems = {n: {p["id"]: p for p in json.load(open(f"l{n}_{ev.PROBLEM_FILE_TAG}.json"))} for n in ev.LEVELS}

    total_retried = 0
    total_fixed = 0
    for level_str, lvl in results.items():
        level = int(level_str)
        rows = lvl["rows"]
        for i, row in enumerate(rows):
            if row["scoreable"]:
                continue
            p = level_problems[level][row["id"]]
            total_retried += 1
            print(f"retrying L{level} {row['id']} (was: {row['raw_response'][:80]!r})", file=sys.stderr)
            new_row = ev._eval_one(p, level)
            if new_row["scoreable"]:
                total_fixed += 1
            rows[i] = new_row

        correct = sum(1 for r in rows if r["correct"])
        n_scored = sum(1 for r in rows if r["scoreable"])
        n_truncated = sum(1 for r in rows if r["scoreable"] and r["predicted"] is None)
        lvl["n_scored"] = n_scored
        lvl["accuracy"] = correct / n_scored if n_scored else float("nan")
        print(f"L{level}: accuracy={lvl['accuracy']:.3f} ({correct}/{n_scored} scored, "
              f"{n_truncated} scored-wrong-via-no-answer, {len(rows)-n_scored} true infra failures)")

    with open(ev.OUT_PATH, "w") as f:
        json.dump(results, f, indent=2)

    print(f"\nretried {total_retried} failed rows, recovered {total_fixed} into scoreable results "
          f"({total_retried - total_fixed} still failed)")
    print(f"\n{'Model':<20} " + " ".join(f"L{l:>3}" for l in ev.LEVELS))
    print(f"{model:<20} " + " ".join(f"{results[str(l)]['accuracy']:.2f}" for l in ev.LEVELS))


if __name__ == "__main__":
    main()
