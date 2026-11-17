"""Gold-standard scoring: splice the ORIGINAL frozen blocks back into the model's
solution and re-verify, plus a cheat scan.

Textual frozen checks are unreliable — models reformat (drop redundant parens),
and a "these lines are present" check misses ADDED clauses (spec gaming, which
gpt-5 was caught doing). Restoring the frozen text and re-verifying settles both.

Usage: python3 rescore.py <tag> [tasks_dir] [results_dir]
"""
import json
import os
import re
import subprocess
import sys
import threading
import queue
from collections import Counter

HERE = os.path.dirname(os.path.abspath(__file__))
VERUS = f"{HERE}/tools/verus-x86-linux/verus"
CHEAT = re.compile(r'\bassume\s*\(|\badmit\s*\(|external_body|exec_allows_no_decreases')
NPROC = 12


def match_brace(s, i):
    depth = 0
    for j in range(i, len(s)):
        if s[j] == "{":
            depth += 1
        elif s[j] == "}":
            depth -= 1
            if depth == 0:
                return j
    return -1


def find_blocks(txt):
    out = []
    for m in re.finditer(r'spec fn (step\d+)\s*\(', txt):
        bo = txt.index("{", m.end())
        be = match_brace(txt, bo)
        if be > 0:
            out.append((m.group(1), m.start(), be + 1))
    m = re.search(r'fn chain_driver\s*\(', txt)
    if m:
        bo = txt.index("{", m.end())
        be = match_brace(txt, bo)
        if be > 0:
            out.append(("driver", m.start(), be + 1))
    return sorted(out, key=lambda x: x[1])


def splice(task_txt, reply_txt):
    tb = {n: task_txt[s:e] for n, s, e in find_blocks(task_txt)}
    rb = find_blocks(reply_txt)
    if {n for n, _, _ in rb} != set(tb):
        return None
    out = reply_txt
    for name, s, e in sorted(rb, key=lambda x: -x[1]):
        out = out[:s] + tb[name] + out[e:]
    return out


def gold_score(tag, tasks_dir=None, results_dir=None):
    tasks_dir = tasks_dir or f"{HERE}/tasks"
    results_dir = results_dir or f"{HERE}/results_{tag}"
    work = f"{results_dir}/_gold"
    os.makedirs(work, exist_ok=True)
    rows = json.load(open(f"{results_dir}/results.json"))
    res, lock, q = {}, threading.Lock(), queue.Queue()
    for r in rows:
        if r.get("verified"):
            q.put(r)

    def w():
        while True:
            try:
                r = q.get_nowait()
            except queue.Empty:
                return
            f = r["file"]
            reply = open(f"{results_dir}/sol_{f}").read()
            task = open(f"{tasks_dir}/{f}").read()
            if CHEAT.search(reply):
                with lock:
                    res[f] = ("cheat", False)
                continue
            sp = splice(task, reply)
            if sp is None:
                with lock:
                    res[f] = ("block_missing", False)
                continue
            p = f"{work}/{f}"
            open(p, "w").write(sp)
            try:
                v = subprocess.run([VERUS, p], capture_output=True, text=True, timeout=900)
                ok = "0 errors" in v.stdout + v.stderr
            except Exception:
                ok = False
            with lock:
                res[f] = ("ok" if ok else "fails_with_original_spec", ok)

    ths = [threading.Thread(target=w) for _ in range(NPROC)]
    for t in ths:
        t.start()
    for t in ths:
        t.join()

    out = []
    for r in rows:
        r2 = dict(r)
        kind, ok = res.get(r["file"], ("not_verified", False))
        r2["gold_kind"], r2["gold_ok"] = kind, ok
        out.append(r2)
    json.dump(out, open(f"{results_dir}/results_gold.json", "w"), indent=1)
    return out


if __name__ == "__main__":
    tag = sys.argv[1]
    out = gold_score(tag, *(sys.argv[2:4] or []))
    parts = []
    for l in sorted({x["level"] for x in out}):
        g = [x for x in out if x["level"] == l]
        parts.append(f"S{l}: {sum(1 for x in g if x['gold_ok'])}/{len(g)}")
    print(f"{tag} gold: " + "  ".join(parts))
    print("kinds:", dict(Counter(x["gold_kind"] for x in out)))
