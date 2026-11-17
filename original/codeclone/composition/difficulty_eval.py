"""
Step 5: difficulty-trend proof. Zero-shot clone-detection eval across L1/L2/L3
using Together AI. Reports accuracy per level plus a structural sanity-check
stat (lines of code, approximate cyclomatic complexity). Same fixed SEED/level
sampling regardless of model, so different models are scored on the identical
150-problem-per-level sample -- a paired comparison, not independent samples.

Usage:
    export TOGETHER_API_KEY="..."
    python3 difficulty_eval.py ["ModelName/On-Together"]
    # defaults to Qwen/Qwen3.7-Max if no argument given
    # writes to difficulty_eval_results_<model-slug>.json
"""
import json
import os
import random
import re
import sys
import time

import requests

MODEL = sys.argv[1] if len(sys.argv) > 1 else "Qwen/Qwen3.7-Max"
MODEL_SLUG = re.sub(r"[^a-zA-Z0-9]+", "_", MODEL).strip("_").lower()
OUT_PATH = f"difficulty_eval_results_{MODEL_SLUG}.json"
CHAT_URL = "https://api.together.ai/v1/chat/completions"
N_PER_LEVEL = 150
SEED = 0

SYSTEM_PROMPT = (
    "You are a program equivalence judge. You will be shown two Java code "
    "snippets, each possibly composed of several helper classes and an outer "
    "method that calls them in sequence. Decide whether the two snippets are "
    "semantically equivalent (compute the same results / have the same "
    "observable behavior for the same inputs to the outer method), regardless "
    "of variable/class names or formatting. "
    "Respond with exactly one line: VERDICT: 1 (equivalent) or VERDICT: 0 (not equivalent)."
)


def sample_for_eval(path, level, n, seed):
    problems = json.load(open(path))
    pos = [p for p in problems if p["label"] == "equivalent"]
    neg = [p for p in problems if p["label"] == "not_equivalent"]
    rng = random.Random(seed + level)
    n_pos, n_neg = n // 2, n - n // 2
    n_pos, n_neg = min(n_pos, len(pos)), min(n_neg, len(neg))
    sampled = rng.sample(pos, n_pos) + rng.sample(neg, n_neg)
    rng.shuffle(sampled)
    return sampled


MAX_TOKENS = 8000


def classify(side_a, side_b, model=MODEL, retries=5):
    """Returns (predicted, content, finish_reason). finish_reason is None only
    when no response was received at all (network exception / retries
    exhausted on 429) -- that's the one case _eval_one treats as an excluded
    infra failure rather than a scored wrong answer. A reasoning model that
    burns its whole token budget on reasoning_content and never emits content
    (finish_reason == "length") is a real capability limitation, not infra
    flakiness, so it must stay in the scored denominator as incorrect."""
    api_key = os.environ.get("TOGETHER_API_KEY")
    if not api_key:
        sys.exit("TOGETHER_API_KEY not set")
    user_prompt = f"Snippet A:\n```java\n{side_a}\n```\n\nSnippet B:\n```java\n{side_b}\n```"

    for attempt in range(retries):
        resp = requests.post(
            CHAT_URL,
            headers={"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"},
            json={
                "model": model,
                "messages": [{"role": "system", "content": SYSTEM_PROMPT},
                             {"role": "user", "content": user_prompt}],
                "temperature": 0, "max_tokens": MAX_TOKENS, "stream": True,
            },
            timeout=180, stream=True,
        )
        if resp.status_code == 429:
            wait = 2 ** attempt
            time.sleep(wait)
            continue
        resp.raise_for_status()
        break
    else:
        return None, "RATE_LIMITED_EXHAUSTED", None
    content = ""
    finish_reason = None
    for line in resp.iter_lines(decode_unicode=True):
        if not line or not line.startswith("data:"):
            continue
        payload = line[len("data:"):].strip()
        if payload == "[DONE]":
            break
        chunk = json.loads(payload)
        choices = chunk.get("choices") or []
        if not choices:
            continue
        delta = choices[0].get("delta", {})
        if delta.get("content"):
            content += delta["content"]
        if choices[0].get("finish_reason"):
            finish_reason = choices[0]["finish_reason"]
    m = re.search(r"VERDICT:\s*([01])", content)
    if not m:
        m = re.search(r"\b([01])\b", content)
    return (int(m.group(1)) if m else None), content, finish_reason


def loc(code):
    return len([ln for ln in code.splitlines() if ln.strip()])


def cyclomatic_approx(code):
    # rough proxy: count decision points
    keywords = re.findall(r"\b(if|for|while|case|catch)\b|(\&\&|\|\|)", code)
    return 1 + len(keywords)


def _eval_one(p, level):
    expected = 1 if p["label"] == "equivalent" else 0
    try:
        pred, raw, finish_reason = classify(p["side_a_code"], p["side_b_code"])
    except Exception as e:
        pred, raw, finish_reason = None, f"ERROR:{e}", None
    # a response that came back but didn't yield a parseable verdict (most
    # commonly finish_reason == "length" -- a reasoning model exhausting its
    # token budget on reasoning_content before emitting an answer) is a real
    # scored miss, not an excluded infra failure -- excluding it would inflate
    # accuracy by dropping exactly the cases the model failed hardest on.
    no_response_at_all = finish_reason is None
    scoreable = not no_response_at_all
    return {
        "id": p["id"], "level": level, "expected": expected, "predicted": pred,
        "correct": (pred == expected) if scoreable else None,
        "scoreable": scoreable, "finish_reason": finish_reason,
        "raw_response": raw,
        "loc_a": loc(p["side_a_code"]), "loc_b": loc(p["side_b_code"]),
        "cc_a": cyclomatic_approx(p["side_a_code"]), "cc_b": cyclomatic_approx(p["side_b_code"]),
    }


def main():
    import concurrent.futures

    level_files = {1: "l1_full.json", 2: "l2_full.json", 3: "l3_full.json"}
    results = {}
    for level, path in level_files.items():
        sample = sample_for_eval(path, level, N_PER_LEVEL, SEED)
        print(f"L{level}: evaluating {len(sample)} problems...", file=sys.stderr)
        rows = []
        correct = 0
        start = time.time()
        with concurrent.futures.ThreadPoolExecutor(max_workers=4) as pool:
            futures = [pool.submit(_eval_one, p, level) for p in sample]
            for i, fut in enumerate(concurrent.futures.as_completed(futures)):
                row = fut.result()
                rows.append(row)
                correct += bool(row["correct"])
                if (i + 1) % 25 == 0:
                    print(f"  [{i+1}/{len(sample)}] elapsed={time.time()-start:.0f}s", file=sys.stderr)

        n_scored = sum(1 for r in rows if r["scoreable"])
        n_truncated = sum(1 for r in rows if r["scoreable"] and r["predicted"] is None)
        acc = correct / n_scored if n_scored else float("nan")
        avg_loc = sum(r["loc_a"] + r["loc_b"] for r in rows) / (2 * len(rows))
        avg_cc = sum(r["cc_a"] + r["cc_b"] for r in rows) / (2 * len(rows))
        results[level] = {
            "n": len(rows), "n_scored": n_scored, "accuracy": acc,
            "avg_loc": avg_loc, "avg_cyclomatic_approx": avg_cc, "rows": rows,
        }
        print(f"L{level}: accuracy={acc:.3f} ({correct}/{n_scored} scored, "
              f"{n_truncated} scored-wrong-via-no-answer, {len(rows)-n_scored} true infra failures) "
              f"avg_loc={avg_loc:.1f} avg_cc={avg_cc:.1f}")

    with open(OUT_PATH, "w") as f:
        json.dump(results, f, indent=2)

    print(f"\n{'Model':<20} {'L1 acc':>10} {'L2 acc':>10} {'L3 acc':>10}")
    print(f"{MODEL:<20} {results[1]['accuracy']:>10.3f} {results[2]['accuracy']:>10.3f} {results[3]['accuracy']:>10.3f}")
    print(f"\n{'':<20} {'L1 LOC':>10} {'L2 LOC':>10} {'L3 LOC':>10}")
    print(f"{'avg lines':<20} {results[1]['avg_loc']:>10.1f} {results[2]['avg_loc']:>10.1f} {results[3]['avg_loc']:>10.1f}")
    print(f"{'avg cyclo. (approx)':<20} {results[1]['avg_cyclomatic_approx']:>10.1f} "
          f"{results[2]['avg_cyclomatic_approx']:>10.1f} {results[3]['avg_cyclomatic_approx']:>10.1f}")


if __name__ == "__main__":
    main()
