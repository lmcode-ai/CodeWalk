#!/usr/bin/env python3
"""Combination #1 done right: SIMULTANEOUS coupled two-bug task, gold-VERIFIED.

Construction (on the EARLIER bug's prebuilt image = baseA, where BOTH bugs are
still broken):
  task-before : baseA + testA + testB           -> both F2P suites FAIL (verified)
  GOLD        : baseA + testA+testB + goldA+goldB -> both F2P suites PASS (verified)
Only if BOTH checks hold is the task valid. Then seal .git (no oracle) and let the
agent fix BOTH coupled bugs at once. Grader = pytest (repo must be pytest-native).

This replaces the fragile merge-marker construction: no drift, no manual union, and
a machine-checked gold answer BEFORE any agent run.

Usage: gate_v1.py --idA dask__dask-9272 --idB dask__dask-9349 \
         --source swegym --steps 80 --cost 1.2
"""
import argparse, base64, json, os, re, modal

app = modal.App.lookup("chainswe-eval", create_if_missing=True)
GIT = "cd /testbed && git config user.email x@x && git config user.name x &&"
CONDA = "source /opt/miniconda3/etc/profile.d/conda.sh && conda activate testbed && cd /testbed &&"

def img_name(iid, source):
    if source == "swegym":
        return f"xingyaoww/sweb.eval.x86_64.{iid.replace('__','_s_').lower()}:latest"
    if source == "swerebench":
        return f"swerebench/sweb.eval.x86_64.{iid.replace('__','_1776_').lower()}:latest"
    return f"swebench/sweb.eval.x86_64.{iid.replace('__','_1776_').lower()}:latest"

def al(v): return json.loads(v) if isinstance(v, str) else list(v)

_CACHE=None
def _cache():
    global _CACHE
    if _CACHE is None:
        import os,json as _j
        p=os.path.join(os.path.dirname(os.path.abspath(__file__)),"instances_cache.json")
        _CACHE=_j.load(open(p)) if os.path.exists(p) else {}
    return _CACHE

def load(iid, source):
    c=_cache().get(iid)                       # memory-light cache first
    if c:
        return {"id": iid, "base": c["base"], "patch": c["patch"],
                "test_patch": c["test_patch"], "F2P": al(c["F2P"])}
    import datasets                            # fallback (streaming to avoid OOM)
    from revisions import revision
    n, s = {"swegym":("SWE-Gym/SWE-Gym","train"),"swerebench":("nebius/SWE-rebench","test")}.get(source,("princeton-nlp/SWE-bench","test"))
    for r in datasets.load_dataset(n, split=s, streaming=True, revision=revision(n)):
        if r["instance_id"] == iid:
            return {"id": iid, "base": r["base_commit"], "patch": r["patch"],
                    "test_patch": r["test_patch"], "F2P": al(r["FAIL_TO_PASS"])}
    raise KeyError(iid)

def sh(sb, c, t=250):
    p = sb.exec("bash", "-lc", c, timeout=t)
    o = p.stdout.read() + p.stderr.read(); p.wait()
    return p.returncode, o

def wf(sb, path, s):
    sh(sb, f"echo {base64.b64encode(s.encode()).decode()} | base64 -d > {path}")

def counts(o):
    g = lambda w: int(m.group(1)) if (m := re.search(r"(\d+) " + w, o)) else 0
    return g("passed"), g("failed"), g("error")

def grade(sb, ids):
    q = " ".join(f'"{t}"' for t in ids)
    rc, o = sh(sb, f"{CONDA} python -m pytest {q} -p no:cacheprovider --tb=no -rN 2>&1 | tail -4")
    return counts(o)

def green(res, n):  # all pass, none fail/error
    return res[1] == 0 and res[2] == 0 and res[0] >= n

def failing(res):   # at least one fail/error
    return res[1] + res[2] > 0

SYSTEM = "You are a software engineer fixing bugs by running bash commands."
BASH_TOOL = [{"type": "function", "function": {"name": "bash",
    "description": "Run a bash command in the repo sandbox.",
    "parameters": {"type": "object", "properties": {"command": {"type": "string"}}, "required": ["command"]}}}]

def prompt(f2p):
    tests = "\n".join(f"  {t}" for t in f2p)
    return (f"A Python repo is at /testbed (conda env `testbed` active). There are "
            f"MULTIPLE bugs in the library source. These tests FAIL:\n{tests}\n\n"
            f"Fix the source so ALL of them pass. Note there may be more than one "
            f"independent bug to fix. Use the bash tool, one command per turn (fresh "
            f"shell, so prefix `cd /testbed && ...`). Run tests with "
            f"`cd /testbed && python -m pytest <node id> -q`. Do NOT edit tests. "
            f"When all pass, run `echo COMPLETE_TASK_AND_SUBMIT`.")

def _complete(model, msgs):
    import litellm, time
    last = None
    for a in range(4):
        try:
            return litellm.completion(model=model, messages=msgs, tools=BASH_TOOL,
                                      tool_choice="auto", max_tokens=16000, temperature=0.5, timeout=180, request_timeout=180,
                                      api_key=os.environ["OPENROUTER_API_KEY" if model.startswith("openrouter/") else "TOGETHER_API_KEY"])
        except Exception as e:
            last = e; time.sleep(3 * (a + 1))
    raise last

def agent_loop(sb, f2p, model, steps, cost_limit, traj, wall=1500):
    import time
    t0 = time.time()
    msgs = [{"role": "system", "content": SYSTEM}, {"role": "user", "content": prompt(f2p)}]
    cost = 0.0; submitted = False
    for step in range(steps):
        if time.time() - t0 > wall: print("    [stop] wall"); break
        r = _complete(model, msgs); m = r.choices[0].message
        try: cost += r._hidden_params.get("response_cost") or 0.0
        except Exception: pass
        tcs = m.tool_calls or []
        msgs.append({"role": "assistant", "content": m.content or "",
                     "tool_calls": [{"id": t.id, "type": "function",
                        "function": {"name": t.function.name, "arguments": t.function.arguments}}
                        for t in tcs]} if tcs else {"role": "assistant", "content": m.content or ""})
        if not tcs:
            msgs.append({"role": "user", "content": "Call the bash tool with a command."}); continue
        for t in tcs:
            try: cmd = json.loads(t.function.arguments).get("command", "")
            except Exception: cmd = ""
            if "COMPLETE_TASK_AND_SUBMIT" in cmd:
                submitted = True
                msgs.append({"role": "tool", "tool_call_id": t.id, "name": "bash", "content": "submitted"}); continue
            rc, out = sh(sb, f"{CONDA} {cmd}", t=150)
            if len(out) > 6000: out = out[:3000] + "\n...[elided]...\n" + out[-3000:]
            msgs.append({"role": "tool", "tool_call_id": t.id, "name": "bash",
                         "content": f"<rc>{rc}</rc>\n<output>\n{out}\n</output>"})
            print(f"    [step {step+1}] ${cost:.3f} {cmd[:64].replace(chr(10),' ')}", flush=True)
        if submitted: print(f"    [step {step+1}] submitted"); break
        if cost_limit and cost > cost_limit: print("    [stop] cost"); break
    json.dump(msgs, open(traj, "w"), indent=1)
    return cost

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--ids", nargs="+", required=True)
    ap.add_argument("--source", default="swegym")
    ap.add_argument("--steps", type=int, default=80); ap.add_argument("--cost", type=float, default=1.2)
    ap.add_argument("--model", default="together_ai/moonshotai/Kimi-K3")
    ap.add_argument("--run-agent", action="store_true", help="run Kimi (else just validate task)")
    ap.add_argument("--results", default="colocated_results.jsonl")
    args = ap.parse_args()

    bugs = [load(i, args.source) for i in args.ids]
    f2p = [t for b in bugs for t in b["F2P"]]
    tag = f"{args.ids[0]}_x{len(bugs)}"
    print(f"=== co-located #1: {tag} | {len(f2p)} tests | base={args.ids[0]} level={len(bugs)} ===", flush=True)
    sb = modal.Sandbox.create(app=app, image=modal.Image.from_registry(img_name(args.ids[0], args.source)),
                              block_network=True, cpu=2, memory=4096, timeout=2400)
    try:
        for j, b in enumerate(bugs):
            wf(sb, f"/tmp/g{j}.patch", b["patch"])
            wf(sb, f"/tmp/t{j}.patch", b["test_patch"])
        def reset(): sh(sb, f"{GIT} git checkout -qf HEAD -- . 2>/dev/null; git stash -u >/dev/null 2>&1")

        # ---- GATE 1: all test patches apply and all suites FAIL at earliest base ----
        reset()
        for j in range(len(bugs)):
            if "OK" not in sh(sb, f"{GIT} git apply /tmp/t{j}.patch && echo OK")[1]:
                print(f"    [gate1 FAIL] test patch {j} does not apply"); return
        befores=[grade(sb, b["F2P"]) for b in bugs]
        print(f"    [before] " + " ".join(f"b{j}={r}" for j,r in enumerate(befores)))
        if not all(failing(r) for r in befores):
            print("    [gate1 FAIL] all bugs must FAIL at earliest base"); return

        # ---- GATE 2: GOLD verified -> all golds apply and all suites PASS ----
        okg=all("OK" in sh(sb, f"{GIT} git apply /tmp/g{j}.patch && echo OK")[1] for j in range(len(bugs)))
        golds=[grade(sb, b["F2P"]) for b in bugs]
        gold_ok = okg and all(green(r, len(b["F2P"])) for r,b in zip(golds,bugs))
        print(f"    [gold]   apply_all={okg} -> " + " ".join(f"b{j}={r}" for j,r in enumerate(golds)) +
              f" -> {'VERIFIED ✅' if gold_ok else 'GOLD NOT GREEN ❌'}")
        if not gold_ok:
            print("    [gate2 FAIL] no verified gold -> task rejected (would be unfair)"); return

        print(f"    [VALID TASK] both bugs fail; gold makes all {len(f2p)} pass. "
              f"file(s) coupled.", flush=True)
        if not args.run_agent:
            print("    (validation-only; pass --run-agent to run Kimi)"); return

        # ---- build agent task: baseA + both test patches (no fixes), sealed ----
        reset()
        for j in range(len(bugs)): sh(sb, f"{GIT} git apply /tmp/t{j}.patch")
        sh(sb, "cd /testbed && rm -rf .git && git init -q && git config user.email x@x && "
               "git config user.name x && git add -A && git commit -qm base")
        seal = sh(sb, "cd /testbed && git log --oneline --all | wc -l")[1].strip()
        print(f"    [seal] git log --all -> {seal} commit(s)")
        p0 = grade(sb, f2p); print(f"    [agent-before] {p0}")
        c = agent_loop(sb, f2p, args.model, args.steps, args.cost, f"colocated_{tag}.traj.json")
        p1 = grade(sb, f2p); ok = green(p1, len(f2p))
        print(f"    [after] {p1} -> {'SOLVED ✅' if ok else 'FAILED ❌'}  ${c:.3f}")
        with open(args.results, "a") as rf:
            rf.write(json.dumps({"task": tag, "level": len(bugs), "n_tests": len(f2p),
                                 "solved": ok, "cost": round(c, 3)}) + "\n")
    finally:
        sb.terminate()

if __name__ == "__main__":
    main()
