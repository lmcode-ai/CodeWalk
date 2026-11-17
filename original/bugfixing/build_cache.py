"""Step 1: build a memory-light per-instance cache (base/patch/test_patch/F2P[/image])
for every instance referenced by all_candidates.json and all_valid.jsonl, so the
gate and assemble steps never reload the full HF datasets. Resumable.

Usage: build_cache.py   -> instances_cache.json
"""
import json, os, datasets
from revisions import revision
HERE=os.path.dirname(os.path.abspath(__file__))
cache=json.load(open(os.path.join(HERE,'instances_cache.json'))) if os.path.exists(os.path.join(HERE,'instances_cache.json')) else {}
# id -> source from candidates, plus validated groups (all_valid.jsonl also holds the
# swerebenchv2 L1 singles, which are drawn directly rather than chain-mined)
src={}
for t in json.load(open(os.path.join(HERE,'all_candidates.json'))):
    for i in t['ids']: src[i]=t['source']
if os.path.exists(os.path.join(HERE,'all_valid.jsonl')):
    for l in open(os.path.join(HERE,'all_valid.jsonl')):
        t=json.loads(l)
        for i in t['ids']: src[i]=t['source']
need_v1={i for i,s in src.items() if s=='swerebench' and i not in cache}
need_v2={i for i,s in src.items() if s=='swerebenchv2' and i not in cache}
print('cache has',len(cache),'| need v1',len(need_v1),'v2',len(need_v2),flush=True)
if need_v1:
    for r in datasets.load_dataset('nebius/SWE-rebench',split='test',streaming=True,revision=revision('nebius/SWE-rebench')):
        if r['instance_id'] in need_v1:
            cache[r['instance_id']]={'base':r['base_commit'],'patch':r['patch'],'test_patch':r['test_patch'],'F2P':r['FAIL_TO_PASS'],'source':'swerebench'}
    print('v1 filled',flush=True)
if need_v2:
    got=0
    for r in datasets.load_dataset('nebius/SWE-rebench-v2',split='train',streaming=True,revision=revision('nebius/SWE-rebench-v2')):
        if r['instance_id'] in need_v2:
            cache[r['instance_id']]={'base':r['base_commit'],'patch':r['patch'],'test_patch':r['test_patch'],'F2P':r['FAIL_TO_PASS'],'source':'swerebenchv2','image':r['image_name'].replace('docker.io/','')}
            got+=1
            if got%800==0: print('v2',got,flush=True)
    print('v2 filled',flush=True)
json.dump(cache, open(os.path.join(HERE,'instances_cache.json'),'w'))
print('cache now',len(cache),'entries',flush=True); print('CACHE_FILL_DONE',flush=True)
