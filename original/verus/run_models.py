"""Run AutoVerus over the S1/S2/S3 task bank with a given model tag.

Usage: python3 run_models.py <tag> [workers]
Scoring is done separately by rescore.py (gold standard).
"""
import json
import os
import re
import subprocess
import sys
import threading
import queue
import time

HERE = os.path.dirname(os.path.abspath(__file__))
AV = f"{HERE}/vps/autoverus"
PY = f"{HERE}/avenv/bin/python"
VERUS = f"{HERE}/tools/verus-x86-linux/verus"

TAG = sys.argv[1]
WORKERS = int(sys.argv[2]) if len(sys.argv) > 2 else 16
TASKS_DIR = sys.argv[3] if len(sys.argv) > 3 else f"{HERE}/tasks"
SUFFIX = sys.argv[4] if len(sys.argv) > 4 else ""
TIMEOUT = int(os.environ.get("AV_TASK_TIMEOUT", "4800"))

ENV = dict(os.environ)
ENV["PATH"] = f"{HERE}/tools/verus-x86-linux:" + os.path.expanduser("~/.cargo/bin") + ":" + ENV["PATH"]
ENV["AV_LOOP_N"] = "1"                      # third-party endpoints: no n>1
ENV["AV_USAGE_LOG"] = f"{HERE}/usage_{TAG}{SUFFIX}.jsonl"

OUTDIR = f"{HERE}/results_{TAG}{SUFFIX}"
os.makedirs(OUTDIR, exist_ok=True)

items = [{"file": t["file"], "level": t["level"], "path": f"{TASKS_DIR}/{t['file']}"}
         for t in json.load(open(f"{TASKS_DIR}/tasks.json"))]

results, done = [], set()
if os.path.exists(f"{OUTDIR}/results.json"):
    for r in json.load(open(f"{OUTDIR}/results.json")):
        results.append(r)
        done.add(r["file"])
q = queue.Queue()
for it in items:
    if it["file"] not in done:
        q.put(it)
print(f"[{TAG}] total={len(items)} done={len(done)} todo={q.qsize()} workers={WORKERS}", flush=True)

lock = threading.Lock()


def worker():
    while True:
        try:
            it = q.get_nowait()
        except queue.Empty:
            return
        out_rs = f"{OUTDIR}/sol_{it['file']}"
        t0 = time.time()
        rec = {"file": it["file"], "level": it["level"], "ok": False}
        try:
            subprocess.run([PY, "main.py", "--config", f"config-{TAG}.json",
                            "--input", it["path"], "--output", out_rs, "--disable-safe"],
                           cwd=AV, env=ENV, capture_output=True, text=True, timeout=TIMEOUT)
            rec["seconds"] = round(time.time() - t0)
            if os.path.exists(out_rs):
                v = subprocess.run([VERUS, out_rs], capture_output=True, text=True, timeout=600)
                rec["verified"] = "0 errors" in v.stdout + v.stderr
            else:
                rec["error"] = "no output"
        except subprocess.TimeoutExpired:
            rec["error"] = "timeout"
            rec["seconds"] = TIMEOUT
        except Exception as e:
            rec["error"] = str(e)[:120]
        with lock:
            results.append(rec)
            json.dump(results, open(f"{OUTDIR}/results.json", "w"), indent=1)
            print(f"[{TAG}] {len(results)}/{len(items)} {it['file']} "
                  f"verified={rec.get('verified')} ({rec.get('seconds','-')}s) {rec.get('error','')}",
                  flush=True)


ths = [threading.Thread(target=worker) for _ in range(WORKERS)]
for t in ths:
    t.start()
for t in ths:
    t.join()
print(f"[{TAG}] ALL DONE", flush=True)
