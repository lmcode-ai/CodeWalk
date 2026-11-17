#!/usr/bin/env python3
"""Co-located N-bug tasks on SWE-rebench-v2 images (repo at /<name>, no conda).

Same gold-verified co-located construction as gate_v1.py, adapted to v2:
- image = earliest bug's `image_name` (docker.io/swerebenchv2/...), passed per task
- repo dir auto-detected (the dir under / that has a .git)
- system python, test_cmd = pytest (v2 convention)
- v2 image HEAD is the FIXED state; we checkout the earliest bug's base_commit
Model-agnostic: --model picks key by prefix (openrouter/ else together).

Usage: gate_v2.py --ids a b [c] --run-agent --model ... --results f.jsonl
"""
import argparse, base64, json, os, re, modal
app = modal.App.lookup("chainswe-eval", create_if_missing=True)

def al(v): return json.loads(v) if isinstance(v, str) else list(v)

_CACHE=None
def _cache():
    global _CACHE
    if _CACHE is None:
        import os,json as _j
        p=os.path.join(os.path.dirname(os.path.abspath(__file__)),"instances_cache.json")
        _CACHE=_j.load(open(p)) if os.path.exists(p) else {}
    return _CACHE

def load(iid):
    c=_cache().get(iid)                       # memory-light cache first
    if c and c.get("image"):
        return {"id":iid,"base":c["base"],"patch":c["patch"],"test_patch":c["test_patch"],
                "F2P":al(c["F2P"]),"image":c["image"]}
    import datasets                            # fallback (streaming)
    from revisions import revision
    for r in datasets.load_dataset("nebius/SWE-rebench-v2",split="train",streaming=True,revision=revision("nebius/SWE-rebench-v2")):
        if r["instance_id"]==iid:
            return {"id":iid,"base":r["base_commit"],"patch":r["patch"],"test_patch":r["test_patch"],
                    "F2P":al(r["FAIL_TO_PASS"]),"image":r["image_name"].replace("docker.io/","")}
    raise KeyError(iid)

def sh(sb,c,t=250):
    p=sb.exec("bash","-lc",c,timeout=t); o=p.stdout.read()+p.stderr.read(); p.wait(); return p.returncode,o
def wf(sb,path,s): sh(sb,f"echo {base64.b64encode(s.encode()).decode()} | base64 -d > {path}")
def counts(o):
    g=lambda w:int(m.group(1)) if (m:=re.search(r"(\d+) "+w,o)) else 0
    return g("passed"),g("failed"),g("error")
def green(r,n): return r[1]==0 and r[2]==0 and r[0]>=n
def failing(r): return r[1]+r[2]>0

SYSTEM="You are a software engineer fixing bugs by running bash commands."
BASH_TOOL=[{"type":"function","function":{"name":"bash","description":"Run a bash command in the repo sandbox.",
    "parameters":{"type":"object","properties":{"command":{"type":"string"}},"required":["command"]}}}]

def prompt(f2p, repo):
    tests="\n".join(f"  {t}" for t in f2p)
    return (f"A Python repo is checked out at {repo}. There are MULTIPLE bugs in the source. "
            f"These tests FAIL:\n{tests}\n\nFix the source so ALL of them pass. There may be more "
            f"than one bug. Use the bash tool, one command/turn (fresh shell; prefix `cd {repo} && ...`). "
            f"Run tests: `cd {repo} && python -m pytest <node id> -q`. Do NOT edit tests. "
            f"When all pass, run `echo COMPLETE_TASK_AND_SUBMIT`.")

def _complete(model,msgs):
    import litellm,time
    key=os.environ["OPENROUTER_API_KEY" if model.startswith("openrouter/") else "TOGETHER_API_KEY"]
    last=None
    for a in range(4):
        try:
            return litellm.completion(model=model,messages=msgs,tools=BASH_TOOL,tool_choice="auto",
                max_tokens=16000,temperature=0.5,timeout=180,request_timeout=180,api_key=key)
        except Exception as e: last=e; time.sleep(3*(a+1))
    raise last

def agent_loop(sb,f2p,repo,model,steps,cost_limit,traj,wall=1500):
    import time
    t0=time.time(); msgs=[{"role":"system","content":SYSTEM},{"role":"user","content":prompt(f2p,repo)}]
    cost=0.0; submitted=False
    for step in range(steps):
        if time.time()-t0>wall: print("    [stop] wall"); break
        r=_complete(model,msgs); m=r.choices[0].message
        try: cost+=r._hidden_params.get("response_cost") or 0.0
        except Exception: pass
        tcs=m.tool_calls or []
        msgs.append({"role":"assistant","content":m.content or "","tool_calls":[{"id":t.id,"type":"function",
            "function":{"name":t.function.name,"arguments":t.function.arguments}} for t in tcs]} if tcs
            else {"role":"assistant","content":m.content or ""})
        if not tcs: msgs.append({"role":"user","content":"Call the bash tool."}); continue
        for t in tcs:
            try: cmd=json.loads(t.function.arguments).get("command","")
            except Exception: cmd=""
            if "COMPLETE_TASK_AND_SUBMIT" in cmd:
                submitted=True; msgs.append({"role":"tool","tool_call_id":t.id,"name":"bash","content":"submitted"}); continue
            rc,out=sh(sb,cmd,t=150)
            if len(out)>6000: out=out[:3000]+"\n...[elided]...\n"+out[-3000:]
            msgs.append({"role":"tool","tool_call_id":t.id,"name":"bash","content":f"<rc>{rc}</rc>\n<output>\n{out}\n</output>"})
            print(f"    [step {step+1}] ${cost:.3f} {cmd[:60].replace(chr(10),' ')}",flush=True)
        if submitted: print(f"    [step {step+1}] submitted"); break
        if cost_limit and cost>cost_limit: print("    [stop] cost"); break
    json.dump(msgs,open(traj,"w"),indent=1); return cost

def main():
    ap=argparse.ArgumentParser()
    ap.add_argument("--ids",nargs="+",required=True)
    ap.add_argument("--steps",type=int,default=100); ap.add_argument("--cost",type=float,default=1.5)
    ap.add_argument("--model",default="together_ai/moonshotai/Kimi-K3")
    ap.add_argument("--run-agent",action="store_true"); ap.add_argument("--results",default="v2_results.jsonl")
    args=ap.parse_args()
    bugs=[load(i) for i in args.ids]; f2p=[t for b in bugs for t in b["F2P"]]
    tag=f"{args.ids[0]}_x{len(bugs)}"; img=bugs[0]["image"]
    print(f"=== v2 co-located: {tag} | {len(f2p)} tests | img={img} | {args.model}",flush=True)
    sb=modal.Sandbox.create(app=app,image=modal.Image.from_registry(img),block_network=True,cpu=2,memory=4096,timeout=2400)
    try:
        rc,o=sh(sb,"for d in $(ls -d /*/ 2>/dev/null); do [ -d \"$d/.git\" ] && echo ${d%/}; done | head -1")
        repo=o.strip().splitlines()[-1] if o.strip() else "/workspace"
        print(f"    repo={repo}",flush=True)
        GIT=f"cd {repo} && git config user.email x@x && git config user.name x &&"
        def grade(ids):
            q=" ".join(f'"{t}"' for t in ids)
            rc,o=sh(sb,f"cd {repo} && python -m pytest {q} --no-header -rN --tb=no 2>&1 | tail -4")
            return counts(o)
        for j,b in enumerate(bugs):
            wf(sb,f"/tmp/g{j}.patch",b["patch"]); wf(sb,f"/tmp/t{j}.patch",b["test_patch"])
        def reset(): sh(sb,f"{GIT} git checkout -qf {bugs[0]['base']} 2>/dev/null; git clean -qfd 2>/dev/null")
        # GATE1: all tests apply + all fail at earliest base
        reset()
        for j in range(len(bugs)):
            if "OK" not in sh(sb,f"{GIT} git apply /tmp/t{j}.patch && echo OK")[1]:
                print(f"    [gate1 FAIL] test {j} no apply"); return
        befores=[grade(b["F2P"]) for b in bugs]
        print(f"    [before] "+" ".join(f"b{j}={r}" for j,r in enumerate(befores)),flush=True)
        if not all(failing(r) for r in befores): print("    [gate1 FAIL] not all fail"); return
        # GATE2: all golds apply + all pass
        okg=all("OK" in sh(sb,f"{GIT} git apply /tmp/g{j}.patch && echo OK")[1] for j in range(len(bugs)))
        golds=[grade(b["F2P"]) for b in bugs]
        gold_ok=okg and all(green(r,len(b["F2P"])) for r,b in zip(golds,bugs))
        print(f"    [gold] apply={okg} "+" ".join(f"b{j}={r}" for j,r in enumerate(golds))+f" -> {'VERIFIED' if gold_ok else 'GOLD NOT GREEN'}",flush=True)
        if not gold_ok: print("    [gate2 FAIL]"); return
        print(f"    [VALID TASK] {len(f2p)} tests",flush=True)
        if not args.run_agent: return
        # task: base + all test patches, seal
        reset()
        for j in range(len(bugs)): sh(sb,f"{GIT} git apply /tmp/t{j}.patch")
        sh(sb,f"cd {repo} && rm -rf .git && git init -q && git config user.email x@x && git config user.name x && git add -A && git commit -qm base")
        p0=grade(f2p); print(f"    [agent-before] {p0}",flush=True)
        c=agent_loop(sb,f2p,repo,args.model,args.steps,args.cost,f"v2_{tag}.traj.json")
        p1=grade(f2p); ok=green(p1,len(f2p))
        print(f"    [after] {p1} -> {'SOLVED' if ok else 'FAILED'} ${c:.3f}",flush=True)
        with open(args.results,"a") as rf:
            rf.write(json.dumps({"task":tag,"level":len(bugs),"n_tests":len(f2p),"solved":ok,"cost":round(c,3),"model":args.model})+"\n")
    finally: sb.terminate()

if __name__=="__main__": main()
