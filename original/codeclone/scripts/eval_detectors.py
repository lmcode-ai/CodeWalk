"""
Systematic composition-consistency eval: sample (func_a, func_b) pairs across the 8
clusters (same cluster = ground-truth equivalent, different cluster = ground-truth
non-equivalent), run both detectors on every pair, report precision/recall/F1.

Usage:
    export TOGETHER_API_KEY="..."
    python3 eval_detectors.py [--n-pos 10] [--n-neg 10] [--seed 0]
"""
import argparse
import json
import random
import sys

from embed_similarity import classify as embed_classify
from llm_classify import classify as llm_classify, DEFAULT_MODEL, load_funcs as _load  # noqa: reuse loader

MAX_FUNC_LEN = 1500  # embeddings model caps at 512 tokens (~3.8 chars/token observed); leave margin


def load_data():
    funcs = {}
    with open("../Code-Code/Clone-detection-BigCloneBench/dataset/data.jsonl") as f:
        for line in f:
            obj = json.loads(line)
            if len(obj["func"]) <= MAX_FUNC_LEN:
                funcs[obj["idx"]] = obj["func"]
    with open("clusters.json") as f:
        clusters = json.load(f)
    # keep only members that survived the length filter
    clusters = {cid: [m for m in members if m in funcs] for cid, members in clusters.items()}
    clusters = {cid: members for cid, members in clusters.items() if len(members) >= 2}
    return funcs, clusters


def sample_pairs(funcs, clusters, n_pos, n_neg, seed):
    rng = random.Random(seed)
    cluster_ids = list(clusters.keys())
    pairs = []  # (idx_a, idx_b, ground_truth_label)

    tries = 0
    while len(pairs) < n_pos and tries < n_pos * 20:
        tries += 1
        cid = rng.choice(cluster_ids)
        a, b = rng.sample(clusters[cid], 2)
        pairs.append((a, b, 1))

    tries = 0
    while len([p for p in pairs if p[2] == 0]) < n_neg and tries < n_neg * 20:
        tries += 1
        c1, c2 = rng.sample(cluster_ids, 2)
        a = rng.choice(clusters[c1])
        b = rng.choice(clusters[c2])
        pairs.append((a, b, 0))

    return pairs


def prf1(y_true, y_pred):
    tp = sum(1 for t, p in zip(y_true, y_pred) if t == 1 and p == 1)
    fp = sum(1 for t, p in zip(y_true, y_pred) if t == 0 and p == 1)
    fn = sum(1 for t, p in zip(y_true, y_pred) if t == 1 and p == 0)
    tn = sum(1 for t, p in zip(y_true, y_pred) if t == 0 and p == 0)
    precision = tp / (tp + fp) if (tp + fp) else float("nan")
    recall = tp / (tp + fn) if (tp + fn) else float("nan")
    f1 = 2 * precision * recall / (precision + recall) if (precision + recall) else float("nan")
    acc = (tp + tn) / len(y_true) if y_true else float("nan")
    return {"tp": tp, "fp": fp, "fn": fn, "tn": tn, "precision": precision, "recall": recall, "f1": f1, "acc": acc}


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--n-pos", type=int, default=10)
    p.add_argument("--n-neg", type=int, default=10)
    p.add_argument("--seed", type=int, default=0)
    p.add_argument("--skip-llm", action="store_true")
    p.add_argument("--skip-embed", action="store_true")
    p.add_argument("--llm-model", default=DEFAULT_MODEL)
    args = p.parse_args()

    funcs, clusters = load_data()
    pairs = sample_pairs(funcs, clusters, args.n_pos, args.n_neg, args.seed)
    print(f"sampled {len(pairs)} pairs ({sum(1 for p in pairs if p[2]==1)} pos / "
          f"{sum(1 for p in pairs if p[2]==0)} neg) from {len(clusters)} clusters")

    y_true, y_embed, y_llm = [], [], []
    results = []
    for i, (a, b, truth) in enumerate(pairs):
        row = {"a": a, "b": b, "truth": truth}
        if not args.skip_embed:
            try:
                elabel, escore = embed_classify(funcs[a], funcs[b])
            except Exception as e:
                print(f"  [embed error on {a},{b}] {e}", file=sys.stderr)
                elabel, escore = None, None
            row["embed_label"], row["embed_score"] = elabel, escore
            if elabel is not None:
                y_true.append(truth)
                y_embed.append(elabel)
        if not args.skip_llm:
            try:
                llabel, _ = llm_classify(funcs[a], funcs[b], model=args.llm_model)
            except Exception as e:
                print(f"  [llm error on {a},{b}] {e}", file=sys.stderr)
                llabel = None
            row["llm_label"] = llabel
            if llabel is not None:
                y_llm.append(llabel)
        results.append(row)
        escore = row.get("embed_score")
        escore_str = f"{escore:.3f}" if escore is not None else "NA"
        print(f"[{i+1}/{len(pairs)}] a={a} b={b} truth={truth} "
              f"embed={row.get('embed_label')}({escore_str}) "
              f"llm={row.get('llm_label')}")

    model_tag = args.llm_model.replace("/", "_")
    out_name = f"eval_results_{model_tag}.json" if not args.skip_llm else "eval_results_embed_only.json"
    with open(out_name, "w") as f:
        json.dump(results, f, indent=2)

    if not args.skip_embed:
        print("\n=== Embedding + cosine similarity ===")
        print(prf1(y_true[: len(y_embed)], y_embed))
    if not args.skip_llm:
        # y_true for llm uses same ordering since we append in lockstep only when present
        y_true_llm = [truth for (a, b, truth), row in zip(pairs, results) if row.get("llm_label") is not None]
        print(f"\n=== Zero-shot LLM ({args.llm_model}) ===")
        print(prf1(y_true_llm, y_llm))


if __name__ == "__main__":
    main()
