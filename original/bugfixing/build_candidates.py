#!/usr/bin/env python3
"""Step 0b: turn mined windows into the per-level candidate pool (all_candidates.json).

  v1 (nebius/SWE-rebench)
    L1     250 single instances that have a prebuilt docker image, round-robin
           across repos (<=6 per repo) for diversity
    L2/L3  the first N ids of each mined window (candidates_swerebench_w2.jsonl)
           whose first N instances all have an image; dedup; <=500 per level
  v2 (nebius/SWE-rebench-v2)
    L2/L3  the first N ids of every mined window (candidates_v2.jsonl); dedup

A level-N candidate is the N-prefix of a mined window, so it need not itself be
overlap-connected. v2 L1 is built separately from validated v2 chains
(build_v2l1_candidates.py).

Usage: build_candidates.py --v1-windows candidates_swerebench_w2.jsonl \
                           --v2-windows candidates_v2.jsonl [--out all_candidates.json]
"""
import argparse, json, collections, os
HERE = os.path.dirname(os.path.abspath(__file__))

def v1_candidates(v1_windows):
    import datasets
    from revisions import revision
    ds1 = {x['instance_id']: x for x in datasets.load_dataset('nebius/SWE-rebench', split='test', revision=revision('nebius/SWE-rebench'))}
    have1 = [i for i, x in ds1.items() if x.get('docker_image')]
    cand = []
    # L1: diverse image-having singles
    byrepo = collections.defaultdict(list)
    for i in have1: byrepo[ds1[i]['repo']].append(i)
    pools = {r: list(v) for r, v in byrepo.items()}; per = collections.Counter(); n = 0
    while n < 250 and any(pools.values()):
        for r in list(pools):
            if pools[r] and per[r] < 6:
                cand.append({'ids': [pools[r].pop(0)], 'source': 'swerebench', 'level': 1, 'repo': r}); per[r] += 1; n += 1
            if n >= 250: break
    # L2/L3: N-prefixes of all-image mined windows
    w2 = [json.loads(l) for l in open(v1_windows)]
    himg = set(have1)
    seen = set()
    for N in (2, 3):
        cnt = 0
        for c in w2:
            if c['length'] >= N and all(i in himg for i in c['instance_ids'][:N]):
                k = tuple(c['instance_ids'][:N])
                if k in seen: continue
                seen.add(k); cand.append({'ids': list(k), 'source': 'swerebench', 'level': N, 'repo': c['repo']}); cnt += 1
            if cnt >= 500: break
    return cand

def v2_candidates(v2_windows):
    cands = [json.loads(l) for l in open(v2_windows)]
    out = []; seen = set()
    for N in (2, 3):
        for c in cands:
            if c['length'] >= N:
                k = tuple(c['instance_ids'][:N])
                if k in seen: continue
                seen.add(k); out.append({'ids': list(k), 'source': 'swerebenchv2', 'level': N, 'repo': c['repo']})
    return out

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--v1-windows", default=os.path.join(HERE, "candidates_swerebench_w2.jsonl"))
    ap.add_argument("--v2-windows", default=os.path.join(HERE, "candidates_v2.jsonl"))
    ap.add_argument("--out", default=os.path.join(HERE, "all_candidates.json"))
    args = ap.parse_args()

    cand = v1_candidates(args.v1_windows) + v2_candidates(args.v2_windows)
    json.dump(cand, open(args.out, 'w'))
    print('combined candidates:', len(cand))
    print('by (source,level):', dict(collections.Counter((t['source'], t['level']) for t in cand)))

if __name__ == "__main__":
    main()
