"""Fetch PASS_TO_PASS for all benchmark instances -> p2p_cache.json.
Streams both sources; keeps only instance_ids that appear in benchmark_dataset.jsonl."""
import json
need = set()
src_of = {}
for l in open('benchmark_dataset.jsonl'):
    r = json.loads(l)
    for b in r['bugs']:
        need.add(b['instance_id']); src_of[b['instance_id']] = r['source']
print(f"need PASS_TO_PASS for {len(need)} instances", flush=True)

SRC = {"swerebench": ("nebius/SWE-rebench", "test"),
       "swerebenchv2": ("nebius/SWE-rebench-v2", "train")}
import datasets
from revisions import revision
def as_list(x):
    if x is None: return []
    if isinstance(x, str):
        try: return json.loads(x)
        except Exception: return [x]
    return list(x)

p2p = {}
for source in ("swerebench", "swerebenchv2"):
    name, split = SRC[source]
    want = {i for i in need if src_of[i] == source}
    ds = datasets.load_dataset(name, split=split, streaming=True, revision=revision(name))
    got = 0
    for r in ds:
        iid = r.get("instance_id")
        if iid in want:
            p2p[iid] = as_list(r.get("PASS_TO_PASS")); got += 1
            if got == len(want): break
    print(f"[{source}] got {got}/{len(want)}", flush=True)

json.dump(p2p, open('p2p_cache.json', 'w'))
miss = need - set(p2p)
sizes = [len(v) for v in p2p.values()]
print(f"wrote p2p_cache.json: {len(p2p)} instances, {len(miss)} missing")
if sizes:
    import statistics
    print(f"P2P set sizes: median {statistics.median(sizes):.0f}, max {max(sizes)}, "
          f"empty(no P2P) {sum(1 for s in sizes if s==0)}")
