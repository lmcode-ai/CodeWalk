#!/usr/bin/env python3
"""Step 4: cap gold-verified groups at <=100 per (source, level) and package the
self-contained dataset.

Inputs : all_valid.jsonl      (gold-verified groups, from validate_all.py)
         instances_cache.json (per-instance base/patch/test_patch/F2P, from build_cache.py)
Outputs: benchmark_all.json   (lightweight index: ids/source/level/repo)
         benchmark_dataset.jsonl (released dataset, one task per line)

Usage: assemble.py [--cache instances_cache.json] [--out-dir .]
"""
import argparse, json, collections, os
HERE = os.path.dirname(os.path.abspath(__file__))

def img_for(iid, src, c):
    return c.get('image') if src == 'swerebenchv2' else f"swerebench/sweb.eval.x86_64.{iid.replace('__','_1776_').lower()}:latest"

def al(v): return json.loads(v) if isinstance(v, str) else list(v)

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--valid", default=os.path.join(HERE, "all_valid.jsonl"))
    ap.add_argument("--cache", default=os.path.join(HERE, "instances_cache.json"))
    ap.add_argument("--out-dir", default=HERE)
    args = ap.parse_args()

    # cap <=100 per (source, level), first-seen order, dedup by ids
    rows = [json.loads(l) for l in open(args.valid)]
    by = collections.defaultdict(list); seen = set()
    for t in rows:
        k = tuple(t['ids'])
        if k in seen: continue
        seen.add(k); by[(t['source'], t['level'])].append({'ids': t['ids'], 'source': t['source'], 'level': t['level'], 'repo': t.get('repo', '')})
    bench = []
    for key in sorted(by): bench += by[key][:100]
    json.dump(bench, open(os.path.join(args.out_dir, 'benchmark_all.json'), 'w'), indent=1)

    # package self-contained dataset
    cache = json.load(open(args.cache))
    out = []
    for t in bench:
        ids = t['ids']; src = t['source']; bugs = []
        if not all(i in cache for i in ids): continue
        for iid in ids:
            c = cache[iid]; bugs.append({'instance_id': iid, 'base_commit': c['base'], 'gold_patch': c['patch'], 'test_patch': c['test_patch'], 'FAIL_TO_PASS': al(c['F2P'])})
        first = cache[ids[0]]
        out.append({'task_id': f"{ids[0]}_x{len(ids)}", 'level': t['level'], 'source': src, 'repo': t.get('repo', ''),
                    'image': img_for(ids[0], src, first), 'base_commit': first['base'], 'num_bugs': len(ids), 'bugs': bugs,
                    'all_FAIL_TO_PASS': [x for b in bugs for x in b['FAIL_TO_PASS']],
                    'construction': 'co-located: checkout base_commit; apply all bugs test_patches; fix all so all_FAIL_TO_PASS pass; gold=apply all gold_patch.'})
    with open(os.path.join(args.out_dir, 'benchmark_dataset.jsonl'), 'w') as f:
        for r in out: f.write(json.dumps(r) + "\n")
    print('ASSEMBLED:', len(out), 'tasks |', dict(collections.Counter((r['source'], r['level']) for r in out)))

if __name__ == "__main__":
    main()
