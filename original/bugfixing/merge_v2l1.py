#!/usr/bin/env python3
"""Step 3c: append the first 100 gold-verified v2 L1 tasks (v2l1_valid.jsonl, from
run_bench.py ... validate) to all_valid.jsonl, skipping groups already present.

Usage: merge_v2l1.py [--v2l1 v2l1_valid.jsonl] [--valid all_valid.jsonl] [--cap 100]
"""
import argparse, json, os
HERE = os.path.dirname(os.path.abspath(__file__))

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--v2l1", default=os.path.join(HERE, "v2l1_valid.jsonl"))
    ap.add_argument("--valid", default=os.path.join(HERE, "all_valid.jsonl"))
    ap.add_argument("--cap", type=int, default=100)
    args = ap.parse_args()

    existing = {tuple(json.loads(l)['ids']) for l in open(args.valid)}
    v2l1 = [json.loads(l) for l in open(args.v2l1)][:args.cap]
    added = 0
    with open(args.valid, 'a') as f:
        for t in v2l1:
            if tuple(t['ids']) not in existing:
                f.write(json.dumps({'ids': t['ids'], 'source': 'swerebenchv2', 'level': 1, 'repo': t.get('repo', '')}) + "\n")
                added += 1
    print(f'merged {added} v2 L1 tasks into {args.valid}')

if __name__ == "__main__":
    main()
