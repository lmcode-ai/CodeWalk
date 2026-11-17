#!/usr/bin/env python3
"""Regrade all solved tasks of an eval run on F2P+P2P. Concurrency-controlled; skips already done.
Usage: regrade_p2p.py RESULTS.jsonl [OUT] [MAXJOBS]
  RESULTS.jsonl = an `eval` results file written by run_bench.py"""
import json, os, subprocess, sys, time, collections
from concurrent.futures import ThreadPoolExecutor, as_completed
HERE=os.path.dirname(os.path.abspath(__file__)); PY=os.environ.get("MODAL_PY") or sys.executable
if len(sys.argv)<2: sys.exit(__doc__)
RESULTS=sys.argv[1]
OUT=sys.argv[2] if len(sys.argv)>2 else "regrade_p2p.jsonl"
MAXJOBS=int(sys.argv[3]) if len(sys.argv)>3 else 8
DS={json.loads(l)['task_id'] for l in open(os.path.join(HERE,'benchmark_dataset.jsonl'))}
# solved tasks that have a trajectory and are in the dataset
solved=[]
for l in open(os.path.join(HERE,RESULTS)):
    r=json.loads(l)
    if not (r.get('ids') and r.get('solved')): continue
    tag=f"{r['ids'][0]}_x{len(r['ids'])}"
    if tag not in DS: continue
    if not any(os.path.exists(os.path.join(HERE,p)) for p in (f"v2_{tag}.traj.json",f"colocated_{tag}.traj.json")): continue
    solved.append(tag)
solved=sorted(set(solved))
done=set()
if os.path.exists(os.path.join(HERE,OUT)):
    done={json.loads(l)['task'] for l in open(os.path.join(HERE,OUT))}
todo=[t for t in solved if t not in done]
print(f"[regrade] {len(solved)} solved w/traj | {len(done)} done | {len(todo)} to run | conc {MAXJOBS}",flush=True)
def run(tag):
    log=os.path.join(HERE,f"rg_{tag}.log")
    with open(log,"w") as f:
        subprocess.run([PY,"-u",os.path.join(HERE,"modal_regrade_p2p.py"),"--task",tag,"--out",os.path.join(HERE,OUT)],
                       stdout=f,stderr=subprocess.STDOUT,cwd=HERE,timeout=2600)
    return tag
t0=time.time(); n=0
with ThreadPoolExecutor(max_workers=MAXJOBS) as ex:
    futs={ex.submit(run,t):t for t in todo}
    for fut in as_completed(futs):
        n+=1
        try: fut.result()
        except Exception as e: print(f"  err {futs[fut]}: {e}",flush=True)
        if n%20==0: print(f"[{n}/{len(todo)}] ({time.time()-t0:.0f}s)",flush=True)
print(f"[REGRADE DONE] {n} run",flush=True); print("ALL_REGRADE_DONE",flush=True)
