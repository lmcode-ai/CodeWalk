"""
Embedding + cosine-similarity clone detector.

Usage:
    export TOGETHER_API_KEY="..."
    python3 embed_similarity.py <idx_a> <idx_b> [--threshold 0.85]
    python3 embed_similarity.py --text "<source a>" "<source b>"

Prints: label (0/1), cosine similarity score.
"""
import argparse
import json
import math
import os
import sys

import requests

DATASET = "../Code-Code/Clone-detection-BigCloneBench/dataset"
EMBED_URL = "https://api.together.ai/v1/embeddings"
MODEL = "intfloat/multilingual-e5-large-instruct"
DEFAULT_THRESHOLD = 0.85


def load_funcs():
    funcs = {}
    with open(f"{DATASET}/data.jsonl") as f:
        for line in f:
            obj = json.loads(line)
            funcs[obj["idx"]] = obj["func"]
    return funcs


def embed(texts):
    api_key = os.environ.get("TOGETHER_API_KEY")
    if not api_key:
        sys.exit("TOGETHER_API_KEY not set in environment")
    resp = requests.post(
        EMBED_URL,
        headers={"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"},
        json={"model": MODEL, "input": texts},
        timeout=60,
    )
    resp.raise_for_status()
    data = resp.json()["data"]
    data.sort(key=lambda d: d["index"])
    return [d["embedding"] for d in data]


def cosine(a, b):
    dot = sum(x * y for x, y in zip(a, b))
    na = math.sqrt(sum(x * x for x in a))
    nb = math.sqrt(sum(y * y for y in b))
    return dot / (na * nb)


def classify(func_a, func_b, threshold=DEFAULT_THRESHOLD):
    emb_a, emb_b = embed([func_a, func_b])
    score = cosine(emb_a, emb_b)
    label = 1 if score >= threshold else 0
    return label, score


def main():
    p = argparse.ArgumentParser()
    p.add_argument("a")
    p.add_argument("b")
    p.add_argument("--text", action="store_true", help="treat a/b as raw source, not idx's")
    p.add_argument("--threshold", type=float, default=DEFAULT_THRESHOLD)
    args = p.parse_args()

    if args.text:
        func_a, func_b = args.a, args.b
    else:
        funcs = load_funcs()
        func_a, func_b = funcs[args.a], funcs[args.b]

    label, score = classify(func_a, func_b, args.threshold)
    print(f"label={label} score={score:.4f} threshold={args.threshold}")


if __name__ == "__main__":
    main()
