#!/usr/bin/env python3
"""Step 3b: v2 L1 candidates = the constituent single bugs of the validated v2
L2/L3 chains (first-seen order, dedup), restricted to cached instances, first 160.

Run after validate_all.py has produced the v2 L2/L3 rows of all_valid.jsonl.
Validate the result with
  run_bench.py v2_l1_candidates.json validate v2l1_valid.jsonl
then fold it in with merge_v2l1.py.

Usage: build_v2l1_candidates.py [--valid all_valid.jsonl] [--cache instances_cache.json]
                                [--limit 160] [--out v2_l1_candidates.json]
"""
import argparse, json, collections, os
HERE = os.path.dirname(os.path.abspath(__file__))

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--valid", default=os.path.join(HERE, "all_valid.jsonl"))
    ap.add_argument("--cache", default=os.path.join(HERE, "instances_cache.json"))
    ap.add_argument("--limit", type=int, default=160)
    ap.add_argument("--out", default=os.path.join(HERE, "v2_l1_candidates.json"))
    args = ap.parse_args()

    v2chains = [t for t in map(json.loads, open(args.valid)) if t['source'] == 'swerebenchv2' and t['level'] >= 2]
    singles = collections.OrderedDict()   # instance_id -> repo
    for t in v2chains:
        for iid in t['ids']:
            if iid not in singles: singles[iid] = t.get('repo', '')
    cand = [{'ids': [iid], 'source': 'swerebenchv2', 'level': 1, 'repo': repo} for iid, repo in singles.items()]
    cache = json.load(open(args.cache))
    cand = [c for c in cand if c['ids'][0] in cache][:args.limit]
    json.dump(cand, open(args.out, 'w'), indent=1)
    print(f'v2 L1 candidates: {len(cand)} (from {len(singles)} chain bugs across {len(set(singles.values()))} repos)')

if __name__ == "__main__":
    main()
