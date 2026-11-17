#!/usr/bin/env python3
"""Unified runner over a questions JSON. Each task: {ids:[...], source, level}.
Dispatches v1 (swerebench -> gate_v1.py, /testbed+conda) vs
v2 (swerebenchv2 -> gate_v2.py, /<repo>). 
Usage: run_bench.py QUESTIONS.json MODE RESULTS [MODEL] [MAXJOBS]
  MODE = validate   -> gates only (no agent), records VALID tasks to RESULTS
  MODE = eval       -> --run-agent with MODEL, records solve to RESULTS
"""
import json, os, subprocess, sys, time, collections
from concurrent.futures import ThreadPoolExecutor, as_completed
HERE=os.path.dirname(os.path.abspath(__file__)); PY=os.environ.get("MODAL_PY") or sys.executable
QF=sys.argv[1]; MODE=sys.argv[2]; RESULTS=sys.argv[3]
MODEL=sys.argv[4] if len(sys.argv)>4 else "together_ai/moonshotai/Kimi-K3"
MAXJOBS=int(sys.argv[5]) if len(sys.argv)>5 else 6
tasks=json.load(open(os.path.join(HERE,QF)))
# skip tasks already recorded for this model (save credits)
if MODE=="eval" and os.path.exists(os.path.join(HERE,RESULTS)):
    done={json.loads(l).get("task") for l in open(os.path.join(HERE,RESULTS))}
    def tk(t): return f"{t['ids'][0]}_x{len(t['ids'])}"
    tasks=[t for t in tasks if tk(t) not in done]
tag=(MODE if MODE=="validate" else MODEL.split('/')[-1])
print(f"[run_bench {QF} {MODE} {tag}] {len(tasks)} tasks, by level {dict(collections.Counter(t['level'] for t in tasks))}, conc {MAXJOBS}",flush=True)
outf=open(os.path.join(HERE,RESULTS),"a")
found=collections.Counter()
def run(i):
    t=tasks[i]; src=t.get('source','swerebench')
    script="gate_v2.py" if src=="swerebenchv2" else "gate_v1.py"
    cmd=[PY,"-u",os.path.join(HERE,script),"--ids",*t['ids']]
    if src!="swerebenchv2": cmd+=["--source",src]
    if MODE=="eval": cmd+=["--run-agent","--model",MODEL,"--steps","100","--cost","1.5"]
    cmd+=["--results",os.path.join(HERE,f".raw_{RESULTS}")]  # harness writes its own; we parse log
    log=os.path.join(HERE,f"rb_{tag}_L{t['level']}_{i}.log")
    with open(log,"w") as f: subprocess.run(cmd,stdout=f,stderr=subprocess.STDOUT,cwd=HERE)
    txt=open(log).read()
    valid="VALID TASK" in txt
    solved="-> SOLVED" in txt or "SOLVED ✅" in txt or "SOLVED " in txt
    return i,t,valid,solved
t0=time.time(); done=0
with ThreadPoolExecutor(max_workers=MAXJOBS) as ex:
    futs={ex.submit(run,i):i for i in range(len(tasks))}
    for fut in as_completed(futs):
        i,t,valid,solved=fut.result(); done+=1
        if MODE=="validate" and valid:
            found[t['level']]+=1; outf.write(json.dumps({**t,'valid':True})+"\n"); outf.flush()
        elif MODE=="eval" and valid:
            found[t['level']]+=1; outf.write(json.dumps({**t,'solved':solved,'model':MODEL})+"\n"); outf.flush()
        if done%15==0: print(f"[{done}/{len(tasks)}] {dict(found)} ({time.time()-t0:.0f}s)",flush=True)
print(f"[DONE {tag}] {dict(found)}",flush=True); print(f"ALL_{MODE.upper()}_DONE",flush=True)
