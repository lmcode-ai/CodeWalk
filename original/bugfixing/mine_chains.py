#!/usr/bin/env python3
"""Step 0a: mine overlap-connected windows of consecutive fixes (after the ChainSWE
mining pipeline, arXiv 2607.02606, stages 1-3).

Stage 1  Pool instances from SWE-bench-family datasets (repo, base_commit,
         patch, test_patch, problem_statement, F2P/P2P, date).
Stage 2  Group by repo, sort by commit date, form sliding windows of
         consecutive instances (candidate chains), lengths min..max.
Stage 3  Code-overlap heuristic filter: parse each gold patch's diff hunks to
         extract modified files / functions / classes, and keep only windows
         whose bugs form a *connected* overlap graph (no bug is isolated).

Pure data processing; the execution gates live in gate_v1.py / gate_v2.py.

Usage (as used for the release):
  python mine_chains.py --sources swerebench   --min-window 2 --max-window 5 --out candidates_swerebench_w2.jsonl
  python mine_chains.py --sources swerebenchv2 --min-window 2 --max-window 4 --out candidates_v2.jsonl
"""
import argparse, json, re, sys
from collections import defaultdict

# ---- Stage 1: source adapters ------------------------------------------------
# Each adapter yields normalized instance dicts. Field names differ slightly
# across the SWE-bench family; we map them to a common schema.
SOURCES = {
    "swebench_verified": ("princeton-nlp/SWE-bench_Verified", "test"),
    "swebench":          ("princeton-nlp/SWE-bench", "test"),
    "swebench_lite":     ("princeton-nlp/SWE-bench_Lite", "test"),
    "swegym":            ("SWE-Gym/SWE-Gym", "train"),
    "swerebench":        ("nebius/SWE-rebench", "test"),
    "swerebenchv2":      ("nebius/SWE-rebench-v2", "train"),
}

def load_source(key):
    import datasets
    from revisions import revision
    name, split = SOURCES[key]
    ds = datasets.load_dataset(name, split=split, revision=revision(name))
    out = []
    for r in ds:
        if key=="swerebenchv2" and (r.get("language") or "").lower()!="python": continue
        out.append({
            "instance_id": r.get("instance_id"),
            "source": key,
            "repo": r.get("repo"),
            "base_commit": r.get("base_commit"),
            "date": r.get("created_at") or r.get("date") or "",
            "patch": r.get("patch") or "",
            "test_patch": r.get("test_patch") or "",
            "problem_statement": r.get("problem_statement") or "",
            "FAIL_TO_PASS": r.get("FAIL_TO_PASS"),
            "PASS_TO_PASS": r.get("PASS_TO_PASS"),
            "version": r.get("version"),
        })
    return out

# ---- Stage 3: patch -> (files, functions, classes) ---------------------------
FILE_RE  = re.compile(r'^\+\+\+ b/(.+)$', re.M)
HUNK_RE  = re.compile(r'^@@ -\d+(?:,\d+)? \+\d+(?:,\d+)? @@(.*)$', re.M)
# enclosing def/class that git writes into the hunk section header
SECTION_DEF = re.compile(r'\b(?:def|class)\s+([A-Za-z_]\w*)')
# def/class definitions that are themselves added/removed in the hunk body
BODY_DEF = re.compile(r'^[+-]\s*(?:async\s+)?(?:def|class)\s+([A-Za-z_]\w*)', re.M)

def parse_patch(patch):
    """Return (files:set, symbols:set) touched by a unified diff.

    files   -> modified source paths
    symbols -> function/class names, namespaced as 'path::name', gathered from
               (a) the hunk section header (enclosing def/class) and
               (b) def/class lines added or removed in the hunk body.
    """
    files, symbols = set(), set()
    cur = None
    for line in patch.splitlines():
        m = re.match(r'^\+\+\+ b/(.+)$', line)
        if m:
            cur = m.group(1)
            files.add(cur)
            continue
        h = re.match(r'^@@ -\d+(?:,\d+)? \+\d+(?:,\d+)? @@(.*)$', line)
        if h and cur:
            for name in SECTION_DEF.findall(h.group(1)):
                symbols.add(f"{cur}::{name}")
            continue
        b = re.match(r'^[+-]\s*(?:async\s+)?(?:def|class)\s+([A-Za-z_]\w*)', line)
        if b and cur:
            symbols.add(f"{cur}::{b.group(1)}")
    # keep only python source files for overlap scoring (paper targets Python)
    py_files = {f for f in files if f.endswith(".py")}
    return py_files, symbols

def pairwise_overlap(a, b):
    """Overlap between two instances: shared files and shared symbols."""
    fa, sa = a["_files"], a["_symbols"]
    fb, sb = b["_files"], b["_symbols"]
    return fa & fb, sa & sb

def connected(window):
    """True if the window's bugs form one connected component under file/symbol
    overlap (every bug shares code with at least one neighbour in the group)."""
    n = len(window)
    if n < 2:
        return False
    adj = defaultdict(set)
    for i in range(n):
        for j in range(i + 1, n):
            f, s = pairwise_overlap(window[i], window[j])
            if f or s:
                adj[i].add(j); adj[j].add(i)
    seen, stack = {0}, [0]
    while stack:
        u = stack.pop()
        for v in adj[u]:
            if v not in seen:
                seen.add(v); stack.append(v)
    return len(seen) == n

# ---- Stage 2 + 3 driver ------------------------------------------------------
def mine(instances, min_window=3, max_window=5):
    for it in instances:
        it["_files"], it["_symbols"] = parse_patch(it["patch"])
    by_repo = defaultdict(list)
    for it in instances:
        if it["repo"] and it["date"]:
            by_repo[it["repo"]].append(it)

    chains = []
    for repo, items in by_repo.items():
        items.sort(key=lambda x: x["date"])
        # sliding windows of consecutive instances, lengths min..max
        for size in range(min_window, max_window + 1):
            for start in range(0, len(items) - size + 1):
                window = items[start:start + size]
                if not connected(window):
                    continue
                # record per-adjacent-pair overlap for inspection
                pairs = []
                for i in range(len(window) - 1):
                    f, s = pairwise_overlap(window[i], window[i + 1])
                    pairs.append({"files": sorted(f), "symbols": sorted(s)})
                chains.append({
                    "repo": repo,
                    "length": size,
                    "source": window[0]["source"],
                    "base_commit": window[0]["base_commit"],
                    "date_range": f'{window[0]["date"]} .. {window[-1]["date"]}',
                    "instance_ids": [w["instance_id"] for w in window],
                    "adjacent_overlap": pairs,
                    "shared_files_all": sorted(set.intersection(*[w["_files"] for w in window])) if all(w["_files"] for w in window) else [],
                })
    return chains

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--sources", nargs="+", default=["swebench_verified"],
                    choices=list(SOURCES))
    ap.add_argument("--min-window", type=int, default=3)
    ap.add_argument("--max-window", type=int, default=5)
    ap.add_argument("--out", default="candidates.jsonl")
    args = ap.parse_args()

    pooled, seen = [], set()
    for s in args.sources:
        rows = load_source(s)
        kept = 0
        for r in rows:
            key = r["instance_id"] or (r["repo"], r["base_commit"])
            if key in seen:
                continue
            seen.add(key); pooled.append(r); kept += 1
        print(f"[stage1] {s}: {len(rows)} instances ({kept} new after dedup)", file=sys.stderr)
    print(f"[stage1] pooled total: {len(pooled)} instances across "
          f"{len({r['repo'] for r in pooled})} repos", file=sys.stderr)

    chains = mine(pooled, args.min_window, args.max_window)
    with open(args.out, "w") as f:
        for c in chains:
            f.write(json.dumps(c) + "\n")

    # summary
    from collections import Counter
    lens = Counter(c["length"] for c in chains)
    repos = {c["repo"] for c in chains}
    print(f"[stage3] {len(chains)} overlap-connected candidate chains "
          f"(len {args.min_window}-{args.max_window}) across {len(repos)} repos",
          file=sys.stderr)
    print(f"[stage3] length distribution: {dict(sorted(lens.items()))}", file=sys.stderr)
    print(f"[out] -> {args.out}", file=sys.stderr)

if __name__ == "__main__":
    main()
