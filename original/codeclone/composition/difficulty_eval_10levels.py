"""
10-level difficulty-trend sweep (L1-L10, ~20 balanced problems each, from
l{n}_small20.json) -- higher-resolution follow-up to the original 3-level
(L1-L3, 150/level) eval. Supports both Together AI and OpenRouter, since the
two models being compared here live on different platforms:
  - moonshotai/Kimi-K3            -> Together AI
  - openai/gpt-5.6-sol             -> OpenRouter

Same non-exclusion discipline as the corrected 3-level script: a response
that comes back without a parseable verdict (reasoning-budget exhaustion,
malformed output) counts as SCORED WRONG, not excluded -- only a true
no-response-at-all (network exception / retries exhausted) is excluded from
the denominator, since silently dropping a model's hardest failures would
inflate its reported accuracy.

Usage:
    export TOGETHER_API_KEY="..."     # for Together-hosted models
    export OPENROUTER_API_KEY="..."   # for OpenRouter-hosted models
    python3 difficulty_eval_10levels.py together moonshotai/Kimi-K3 [problem_file_tag]
    python3 difficulty_eval_10levels.py openrouter openai/gpt-5.6-sol [problem_file_tag]
    # problem_file_tag selects which l{level}_<tag>.json files to load (default
    # "small20", the original 20-per-level set); results write to a
    # tag-suffixed file so different scales never clobber each other.
"""
import json
import os
import re
import sys
import time

import requests

PROVIDER = sys.argv[1]
MODEL = sys.argv[2]
PROBLEM_FILE_TAG = sys.argv[3] if len(sys.argv) > 3 else "small20"
# optional 4th arg: comma-separated levels to (re-)run, e.g. "3" or "3,4,5".
# Only those levels are touched -- existing levels already in OUT_PATH are
# loaded and kept as-is, never silently dropped or overwritten.
LEVELS_ARG = sys.argv[4] if len(sys.argv) > 4 else None
MODEL_SLUG = re.sub(r"[^a-zA-Z0-9]+", "_", MODEL).strip("_").lower()
OUT_PATH = f"difficulty_eval_10lvl_results_{MODEL_SLUG}_{PROBLEM_FILE_TAG}.json"

PROVIDER_CONFIG = {
    "together": {
        "url": "https://api.together.ai/v1/chat/completions",
        "key_env": "TOGETHER_API_KEY",
        "extra_headers": {},
    },
    "openrouter": {
        "url": "https://openrouter.ai/api/v1/chat/completions",
        "key_env": "OPENROUTER_API_KEY",
        "extra_headers": {
            "HTTP-Referer": "https://github.com/clonebench",
            "X-Title": "clonebench-difficulty-eval",
        },
    },
}
if PROVIDER not in PROVIDER_CONFIG:
    sys.exit(f"unknown provider {PROVIDER!r}, expected 'together' or 'openrouter'")
CFG = PROVIDER_CONFIG[PROVIDER]

MAX_TOKENS = 8000
ALL_LEVELS = list(range(1, 11))
LEVELS = [int(x) for x in LEVELS_ARG.split(",")] if LEVELS_ARG else ALL_LEVELS

SYSTEM_PROMPT = (
    "You are a program equivalence judge. You will be shown two Java code "
    "snippets, each possibly composed of several helper classes and an outer "
    "method that calls them in sequence. Decide whether the two snippets are "
    "semantically equivalent (compute the same results / have the same "
    "observable behavior for the same inputs to the outer method), regardless "
    "of variable/class names or formatting. "
    "Respond with exactly one line: VERDICT: 1 (equivalent) or VERDICT: 0 (not equivalent)."
)


def classify(side_a, side_b, retries=8):
    """Returns (predicted, content, finish_reason). finish_reason is None only
    when no response was received at all -- that's the one case treated as an
    excluded infra failure rather than a scored wrong answer.

    Retries on rate limits (429), server-side errors (5xx), and transient
    network failures (read timeouts, connection errors, malformed
    streaming chunks) -- these are provider-side flakiness, not a signal
    about the model's capability, so they must not silently become an
    excluded "infra failure" without at least a few real attempts first."""
    api_key = os.environ.get(CFG["key_env"])
    if not api_key:
        sys.exit(f"{CFG['key_env']} not set")
    user_prompt = f"Snippet A:\n```java\n{side_a}\n```\n\nSnippet B:\n```java\n{side_b}\n```"

    for attempt in range(retries):
        try:
            resp = requests.post(
                CFG["url"],
                headers={"Authorization": f"Bearer {api_key}", "Content-Type": "application/json",
                         **CFG["extra_headers"]},
                json={
                    "model": MODEL,
                    "messages": [{"role": "system", "content": SYSTEM_PROMPT},
                                 {"role": "user", "content": user_prompt}],
                    "temperature": 0, "max_tokens": MAX_TOKENS, "stream": True,
                },
                timeout=240, stream=True,
            )
            if resp.status_code == 429 or resp.status_code >= 500:
                time.sleep(min(2 ** attempt, 30))
                continue
            resp.raise_for_status()
            content, finish_reason = "", None
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
        except (requests.exceptions.Timeout, requests.exceptions.ConnectionError,
                json.JSONDecodeError) as e:
            time.sleep(min(2 ** attempt, 30))
            continue
    return None, "RETRIES_EXHAUSTED", None


def loc(code):
    return len([ln for ln in code.splitlines() if ln.strip()])


def cyclomatic_approx(code):
    keywords = re.findall(r"\b(if|for|while|case|catch)\b|(\&\&|\|\|)", code)
    return 1 + len(keywords)


def _eval_one(p, level):
    expected = 1 if p["label"] == "equivalent" else 0
    try:
        pred, raw, finish_reason = classify(p["side_a_code"], p["side_b_code"])
    except Exception as e:
        pred, raw, finish_reason = None, f"ERROR:{e}", None
    scoreable = finish_reason is not None
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
    import os as _os

    results = {}
    if _os.path.exists(OUT_PATH):
        with open(OUT_PATH) as f:
            existing = json.load(f)
        results.update({int(k): v for k, v in existing.items()})
        print(f"loaded existing results for levels {sorted(results)}, "
              f"will (re-)run only {LEVELS}", file=sys.stderr)

    for level in LEVELS:
        sample = json.load(open(f"l{level}_{PROBLEM_FILE_TAG}.json"))
        print(f"L{level}: evaluating {len(sample)} problems...", file=sys.stderr)
        rows = []
        correct = 0
        start = time.time()
        with concurrent.futures.ThreadPoolExecutor(max_workers=4) as pool:
            futures = [pool.submit(_eval_one, p, level) for p in sample]
            for fut in concurrent.futures.as_completed(futures):
                row = fut.result()
                rows.append(row)
                correct += bool(row["correct"])

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
              f"avg_loc={avg_loc:.1f} elapsed={time.time()-start:.0f}s")

        # save after every level, not just at the end -- a killed process
        # (laptop sleep/close, etc.) should lose at most one level's worth
        # of calls, not the whole run. Keys as strings for consistent
        # round-tripping with existing files.
        with open(OUT_PATH, "w") as f:
            json.dump({str(k): v for k, v in results.items()}, f, indent=2)
        print(f"  (saved progress through L{level} to {OUT_PATH})", file=sys.stderr)

    done_levels = sorted(results)
    print(f"\n{'Model':<20} " + " ".join(f"L{l:>3}" for l in done_levels))
    print(f"{MODEL:<20} " + " ".join(f"{results[l]['accuracy']:.2f}" for l in done_levels))


if __name__ == "__main__":
    main()
