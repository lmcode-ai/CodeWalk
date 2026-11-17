"""
Step 4: sample exactly 100 problems per level for Runyuan's handoff.
Problems only (no reasoning traces, per his request). Balanced 50/50
equivalent/not_equivalent per level for a meaningful classification set.
"""
import json
import random

SEED = 0


def sample_level(path, level, n=100):
    problems = json.load(open(path))
    pos = [p for p in problems if p["label"] == "equivalent"]
    neg = [p for p in problems if p["label"] == "not_equivalent"]
    rng = random.Random(SEED + level)
    n_pos = n // 2
    n_neg = n - n_pos
    if len(pos) < n_pos or len(neg) < n_neg:
        raise ValueError(f"L{level}: not enough problems (pos={len(pos)}, neg={len(neg)}, need {n_pos}/{n_neg})")
    sampled = rng.sample(pos, n_pos) + rng.sample(neg, n_neg)
    rng.shuffle(sampled)
    return sampled


def main():
    l1 = sample_level("l1_full.json", 1)
    l2 = sample_level("l2_full.json", 2)
    l3 = sample_level("l3_full.json", 3)

    for level, sample in [(1, l1), (2, l2), (3, l3)]:
        out_path = f"l{level}_sample_100.json"
        with open(out_path, "w") as f:
            json.dump(sample, f, indent=2)
        n_pos = sum(1 for p in sample if p["label"] == "equivalent")
        print(f"L{level}: wrote {len(sample)} ({n_pos} equivalent, {len(sample)-n_pos} not_equivalent) -> {out_path}")


if __name__ == "__main__":
    main()
