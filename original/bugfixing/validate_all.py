#!/usr/bin/env python3
"""Validate all_candidates.json across v1+v2, early-stop each (source,level) at
TARGET valid, hard per-job timeout (no stalls). Writes all_valid.jsonl.
Dispatch: swerebenchv2 -> gate_v2.py ; else gate_v1.py --source ...
"""
import json, os, subprocess, sys, time, threading, collections, random
from concurrent.futures import ThreadPoolExecutor, as_completed
HERE=os.path.dirname(os.path.abspath(__file__)); PY=os.environ.get("MODAL_PY") or sys.executable
TARGET=int(sys.argv[1]) if len(sys.argv)>1 else 100
MAXJOBS=int(sys.argv[2]) if len(sys.argv)>2 else 8
JOB_TIMEOUT=int(sys.argv[3]) if len(sys.argv)>3 else 420
cands=json.load(open(os.path.join(HERE,"all_candidates.json")))
random.seed(0); random.shuffle(cands)   # interleave levels/sources
# resume: count already-valid per (source,level) from all_valid.jsonl
found=collections.Counter(); done_keys=set()
if os.path.exists(os.path.join(HERE,"all_valid.jsonl")):
    for l in open(os.path.join(HERE,"all_valid.jsonl")):
        t=json.loads(l); found[(t['source'],t['level'])]+=1; done_keys.add(tuple(t['ids']))
lock=threading.Lock()
outf=open(os.path.join(HERE,"all_valid.jsonl"),"a")
print(f"[validate_all] {len(cands)} cands, target {TARGET}/(src,lvl), conc {MAXJOBS}, timeout {JOB_TIMEOUT}s",flush=True)
print(f"  resume state: {dict(found)}",flush=True)

def check(t):
    src=t['source']; script="gate_v2.py" if src=="swerebenchv2" else "gate_v1.py"
    cmd=[PY,"-u",os.path.join(HERE,script),"--ids",*t['ids']]
    if src!="swerebenchv2": cmd+=["--source",src]
    log=os.path.join(HERE,f"va_{src}_L{t['level']}_{'_'.join(t['ids'])[:40]}.log")
    try:
        with open(log,"w") as f: subprocess.run(cmd,stdout=f,stderr=subprocess.STDOUT,cwd=HERE,timeout=JOB_TIMEOUT)
    except subprocess.TimeoutExpired:
        return t, False
    return t, ("VALID TASK" in open(log).read())

# controlled submission: skip a (src,lvl) already at TARGET; keep <=MAXJOBS in flight
it=iter(cands); t0=time.time(); checked=0
with ThreadPoolExecutor(max_workers=MAXJOBS) as ex:
    inflight={}
    def submit_next():
        for t in it:
            k=(t['source'],t['level'])
            if tuple(t['ids']) in done_keys: continue
            if found[k]>=TARGET: continue
            fut=ex.submit(check,t); inflight[fut]=t; return True
        return False
    for _ in range(MAXJOBS):
        if not submit_next(): break
    while inflight:
        for fut in as_completed(list(inflight)):
            t=inflight.pop(fut); checked+=1
            try: tt,valid=fut.result()
            except Exception: valid=False
            k=(t['source'],t['level'])
            if valid:
                with lock:
                    found[k]+=1; outf.write(json.dumps({**t,'valid':True})+"\n"); outf.flush()
            if checked%25==0: print(f"[{checked}] valid={dict(found)} ({time.time()-t0:.0f}s)",flush=True)
            submit_next()
            break
print(f"[validate_all DONE] valid per (src,lvl): {dict(found)}",flush=True); print("ALL_VALIDATE_ALL_DONE",flush=True)
