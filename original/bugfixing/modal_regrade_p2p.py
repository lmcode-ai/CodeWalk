#!/usr/bin/env python3
"""Re-grade a completed GPT task on BOTH F2P and P2P (complete pass = all tests green,
including PASS_TO_PASS regression check). No LLM: replays the saved GPT trajectory to
reconstruct the agent's final source, restores test files (anti-tamper), then runs
F2P and P2P. Works for both sources (v1 /testbed+conda ; v2 /<repo>+system python).

Usage: modal_regrade_p2p.py --task <task_id> [--out regrade.jsonl]
"""
import argparse, base64, json, os, re, modal

app = modal.App.lookup("chainswe-eval", create_if_missing=True)
DS = {json.loads(l)['task_id']: json.loads(l) for l in open(
      os.path.join(os.path.dirname(os.path.abspath(__file__)), 'benchmark_dataset.jsonl'))}
P2P = json.load(open(os.path.join(os.path.dirname(os.path.abspath(__file__)), 'p2p_cache.json')))

def sh(sb, c, t=250):
    p = sb.exec("bash", "-lc", c, timeout=t); o = p.stdout.read() + p.stderr.read(); p.wait()
    return p.returncode, o
def wf(sb, path, s):
    sh(sb, f"echo {base64.b64encode(s.encode()).decode()} | base64 -d > {path}")
def counts(o):
    g = lambda w: int(m.group(1)) if (m := re.search(r"(\d+) " + w, o)) else 0
    return g("passed"), g("failed"), g("error")
def al(v): return json.loads(v) if isinstance(v, str) else (list(v) if v else [])
def testfiles(patch): return sorted({f for f in re.findall(r'^\+\+\+ b/(.+)$', patch or '', re.M)})

def replay_commands(tag):
    """full commands from the saved GPT trajectory, in order, minus the submit sentinel."""
    for p in (f"v2_{tag}.traj.json", f"colocated_{tag}.traj.json"):
        if os.path.exists(p):
            msgs = json.load(open(p)); cmds = []
            for m in msgs:
                if m.get('role') != 'assistant': continue
                for tc in (m.get('tool_calls') or []):
                    try: c = json.loads(tc['function']['arguments']).get('command', '')
                    except Exception: c = ''
                    if not c: continue
                    if 'COMPLETE_TASK_AND_SUBMIT' in c:
                        return cmds, p          # loop broke here originally; drop trailing cmds
                    cmds.append(c)
            return cmds, p
    return None, None

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--task", required=True); ap.add_argument("--out", default="regrade_p2p.jsonl")
    args = ap.parse_args()
    t = DS[args.task]; tag = args.task; src = t['source']; bugs = t['bugs']
    v2 = (src == 'swerebenchv2')
    f2p = [x for b in bugs for x in al(b['FAIL_TO_PASS'])]
    p2p = sorted({x for b in bugs for x in P2P.get(b['instance_id'], [])})
    cmds, trajpath = replay_commands(tag)
    print(f"=== regrade {tag} | src={src} | {len(f2p)} F2P + {len(p2p)} P2P | traj={trajpath} ({len(cmds) if cmds else 0} cmds) ===", flush=True)
    if not cmds:
        print("    [SKIP] no trajectory"); return
    sb = modal.Sandbox.create(app=app, image=modal.Image.from_registry(t['image']),
                              block_network=True, cpu=2, memory=4096, timeout=2400)
    try:
        if v2:
            o = sh(sb, "for d in $(ls -d /*/ 2>/dev/null); do [ -d \"$d/.git\" ] && echo ${d%/}; done | head -1")[1]
            repo = o.strip().splitlines()[-1] if o.strip() else "/workspace"
            GIT = f"cd {repo} && git config user.email x@x && git config user.name x &&"
            PY = f"cd {repo} && python -m pytest"
        else:
            repo = "/testbed"; GIT = "cd /testbed && git config user.email x@x && git config user.name x &&"
            PY = "source /opt/miniconda3/etc/profile.d/conda.sh && conda activate testbed && cd /testbed && python -m pytest"
        def grade(ids, t=250):
            if not ids: return (0, 0, 0)
            q = " ".join(f'"{x}"' for x in ids)
            return counts(sh(sb, f"{PY} {q} -p no:cacheprovider --tb=no -rN 2>&1 | tail -4", t=t)[1])
        # rebuild the exact sealed task state the agent started from: base + all test patches, sealed
        sh(sb, f"{GIT} git checkout -qf {bugs[0]['base_commit']} 2>/dev/null; git clean -qfd 2>/dev/null")
        for j, b in enumerate(bugs):
            wf(sb, f"/tmp/t{j}.patch", b['test_patch']); sh(sb, f"{GIT} git apply /tmp/t{j}.patch")
        sh(sb, f"cd {repo} && rm -rf .git && git init -q && git config user.email x@x && git config user.name x && git add -A && git commit -qm base")
        # replay the agent's commands to reconstruct its final tree
        for c in cmds: sh(sb, c, t=200)
        # anti-tamper: restore test files to the sealed (patched) version
        tf = sorted({f for b in bugs for f in testfiles(b['test_patch'])})
        if tf: sh(sb, f"{GIT} git checkout HEAD -- {' '.join(chr(39)+f+chr(39) for f in tf)} 2>/dev/null")
        # grade
        rf2p = grade(f2p); f2p_ok = (rf2p[1] == 0 and rf2p[2] == 0 and rf2p[0] >= len(f2p))
        rp2p = grade(p2p, t=600); p2p_ok = (rp2p[1] == 0 and rp2p[2] == 0)  # no regression: 0 fail/error
        complete = f2p_ok and p2p_ok
        print(f"    F2P {rf2p} -> {'PASS' if f2p_ok else 'FAIL'} | P2P {rp2p} -> {'PASS' if p2p_ok else 'FAIL'} | COMPLETE={complete}", flush=True)
        with open(args.out, "a") as fh:
            fh.write(json.dumps({"task": tag, "level": t['level'], "source": src,
                "f2p_pass": f2p_ok, "p2p_pass": p2p_ok, "complete_pass": complete,
                "n_f2p": len(f2p), "n_p2p": len(p2p), "f2p_counts": rf2p, "p2p_counts": rp2p}) + "\n")
    finally: sb.terminate()

if __name__ == "__main__": main()
