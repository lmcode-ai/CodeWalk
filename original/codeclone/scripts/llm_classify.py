"""
Zero-shot LLM clone detector.

Usage:
    export TOGETHER_API_KEY="..."
    python3 llm_classify.py <idx_a> <idx_b> [--model MODEL]
    python3 llm_classify.py --text "<source a>" "<source b>"

Prints: label (0/1) parsed from the model's verdict.
"""
import argparse
import json
import os
import re
import sys

import requests

DATASET = "../Code-Code/Clone-detection-BigCloneBench/dataset"
CHAT_URL = "https://api.together.ai/v1/chat/completions"
DEFAULT_MODEL = "openai/gpt-oss-120b"

SYSTEM_PROMPT = (
    "You are a program equivalence judge. Given two Java functions, decide whether "
    "they are semantically equivalent (compute the same result / have the same "
    "observable behavior for the same inputs), regardless of variable names, "
    "formatting, or minor syntactic differences. "
    "Respond with exactly one line: VERDICT: 1 (equivalent) or VERDICT: 0 (not equivalent)."
)


def load_funcs():
    funcs = {}
    with open(f"{DATASET}/data.jsonl") as f:
        for line in f:
            obj = json.loads(line)
            funcs[obj["idx"]] = obj["func"]
    return funcs


def classify(func_a, func_b, model=DEFAULT_MODEL):
    api_key = os.environ.get("TOGETHER_API_KEY")
    if not api_key:
        sys.exit("TOGETHER_API_KEY not set in environment")

    user_prompt = f"Function A:\n```java\n{func_a}\n```\n\nFunction B:\n```java\n{func_b}\n```"
    resp = requests.post(
        CHAT_URL,
        headers={"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"},
        json={
            "model": model,
            "messages": [
                {"role": "system", "content": SYSTEM_PROMPT},
                {"role": "user", "content": user_prompt},
            ],
            "temperature": 0,
            "max_tokens": 4000,
            "stream": True,
        },
        timeout=120,
        stream=True,
    )
    resp.raise_for_status()

    content = ""
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

    m = re.search(r"VERDICT:\s*([01])", content)
    if not m:
        # fall back: look for a bare 0/1 anywhere, else treat as unparseable
        m = re.search(r"\b([01])\b", content)
    label = int(m.group(1)) if m else None
    return label, content


def main():
    p = argparse.ArgumentParser()
    p.add_argument("a")
    p.add_argument("b")
    p.add_argument("--text", action="store_true", help="treat a/b as raw source, not idx's")
    p.add_argument("--model", default=DEFAULT_MODEL)
    args = p.parse_args()

    if args.text:
        func_a, func_b = args.a, args.b
    else:
        funcs = load_funcs()
        func_a, func_b = funcs[args.a], funcs[args.b]

    label, raw = classify(func_a, func_b, args.model)
    print(f"label={label} model={args.model}")
    print(f"raw_response={raw!r}")


if __name__ == "__main__":
    main()
