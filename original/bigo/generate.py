#!/usr/bin/env python3
"""
generate.py -- build the chain dataset.

    python chains/generate.py --data data/python_data.jsonl --levels 2 3 10

Steps
  1. Keep the solutions that can become a function (see convert.py).
  2. Keep the problems whose input is one integer, tested by running sibling solutions (problems.py).
  3. For each level k, search for chains of k stages that work on several inputs (search.py).
  4. Write each chain as one program; run it and check it gives the same answers as the stages did one by one.
  5. Label its time complexity from the stage labels and the measured output growth (complexity.py).
  6. Keep only chains whose label is trustworthy and one of the seven dataset classes.

Output (in --out):
  chains_L<k>.jsonl   the dataset: one chain per line, with "src" (the program) and "complexity" (the label)
  growth.json         the measured output growth of every solution used inside a chain
  report.json         counts: problems used, chains found, why chains were dropped

Solutions are executed: use a sandbox if you do not trust the data.  Run results are cached in --cache.
"""
import argparse
import json
import os
import sys
import time
import warnings
from collections import Counter
from concurrent.futures import ThreadPoolExecutor

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))   # so the modules next to this file import

import runner
from complexity import CLASS_TO_LABEL, big_o, chain_cost, measure_growth
from convert import MAIN_BLOCK, Unconvertible, build_program
from problems import check_problem, load_convertible
from runner import run, same_output
from search import ChainSearch, SearchSettings

warnings.filterwarnings("ignore")     # old solutions trigger harmless SyntaxWarnings when parsed

HERE = os.path.dirname(os.path.abspath(__file__))
MAX_FIT_ERROR = 0.2      # a growth fit worse than this makes the chain's label untrustworthy
MIN_SUPPORT = 3          # each problem must have been confirmed by at least this many agreeing siblings


def verify(program, traces):
    """Run the finished program and compare with the stage-by-stage answers.  Returns an error or None."""
    inputs = sorted(traces)
    expected = "".join(f"{traces[x][-1]}\n" for x in inputs)
    # All surviving inputs in one process (this also catches state leaking from one call to the next) ...
    ok, out = run(program + f"\n\nfor _x in {inputs!r}:\n    print(composed(_x))\n", "", timeout=30)
    if not ok or not same_output(out, expected):
        return "program disagrees with the stage-by-stage answers"
    # ... and once as a normal solution, reading stdin.
    ok, out = run(program + MAIN_BLOCK, f"{inputs[0]}\n")
    if not ok or not same_output(out, f"{traces[inputs[0]][-1]}\n"):
        return "program fails when reading stdin"
    return None


def make_record(level, chain, traces, problems, growth):
    """Build, check and label one chain.  Returns (record, None) or (None, reason it was dropped)."""
    stages = [problems[name].solutions[i] for name, i in chain]
    try:
        program = build_program([s.src for s in stages])
    except Unconvertible as e:
        return None, f"could not assemble: {e}"
    error = verify(program, traces)
    if error:
        return None, error

    labels = [s.label for s in stages]
    inner = stages[:-1]                                   # the last stage's output size does not matter
    if any(growth[s.line]["cls"] is None for s in inner):
        return None, "output growth of a stage could not be measured"
    cost = chain_cost(labels, [growth[s.line]["cls"] for s in inner])
    if cost is None:
        return None, "complexity is not of the form n^a log^b n"
    if "np" in labels:
        return None, "contains an exponential (np) stage"
    if any(growth[s.line]["error"] > MAX_FIT_ERROR for s in inner):
        return None, "a growth fit is weak"
    if any(problems[name].support < MIN_SUPPORT for name, _ in chain):
        return None, f"a problem was confirmed by fewer than {MIN_SUPPORT} siblings"
    label = CLASS_TO_LABEL.get(cost["total"])
    if label is None:
        return None, f"complexity {big_o(cost['total'])} is not one of the seven labels"

    inputs = sorted(traces)
    return dict(
        level=level,
        complexity=label,
        big_o=big_o(cost["total"]),
        problems=[s.problem for s in stages],
        lines=[s.line for s in stages],
        stage_labels=labels,
        stage_output_growth=[big_o(growth[s.line]["cls"]) for s in inner] + [None],
        stage_costs=[big_o(t) for t in cost["terms"]],
        dominant_stage=cost["dominant"],
        valid_inputs=inputs,
        example={"input": inputs[0], "values": traces[inputs[0]]},
        src=program + MAIN_BLOCK,
    ), None


def main():
    ap = argparse.ArgumentParser(description="Build chains f_k(...f_1(x)) and label their time complexity.")
    ap.add_argument("--data", default=os.path.join(HERE, "..", "data", "python_data.jsonl"))
    ap.add_argument("--levels", type=int, nargs="+", default=[2, 3, 10], help="chain lengths to build")
    ap.add_argument("--out", default=os.path.join(HERE, "output"))
    ap.add_argument("--cache", default=os.path.join(HERE, "cache.sqlite"), help="'' turns the disk cache off")
    ap.add_argument("--max-chains", type=int, default=500, help="chains searched for per level")
    ap.add_argument("--budget", type=int, default=100000, help="stage extensions tried per level")
    ap.add_argument("--workers", type=int, default=min(32, (os.cpu_count() or 1) * 2))
    ap.add_argument("--timeout", type=float, default=3.0, help="seconds per run")
    ap.add_argument("--seed", type=int, default=0)
    args = ap.parse_args()

    runner.TIMEOUT = args.timeout
    if args.cache:
        runner.open_cache(args.cache)
    os.makedirs(args.out, exist_ok=True)
    pool = ThreadPoolExecutor(args.workers)
    started = time.time()
    report = {}

    # 1. Solutions that can become a function.
    by_problem, total = load_convertible(args.data)
    n_convertible = sum(len(v) for v in by_problem.values())
    print(f"{total} solutions; {n_convertible} can be converted, in {len(by_problem)} problems", flush=True)

    # 2. Problems whose input is one integer.
    names = sorted(by_problem)
    checked = pool.map(lambda name: check_problem(name, by_problem[name]), names)
    problems = {name: p for name, p in zip(names, checked) if p is not None}
    runner.cache.save()
    print(f"{len(problems)} problems usable as stages "
          f"({sum(p.last_only for p in problems.values())} only as the last stage)", flush=True)
    report["data"] = dict(solutions=total, convertible_solutions=n_convertible,
                          problems_with_convertible_solutions=len(by_problem), usable_problems=sorted(problems),
                          stage_solutions=sum(len(p.solutions) for p in problems.values()))

    # 3-6. Each level: search, build, check, label, filter, write.
    search = ChainSearch(problems, SearchSettings(max_chains=args.max_chains, budget=args.budget), pool, args.seed)
    growth = {}                                           # data line -> measured output growth
    for level in args.levels:
        t = time.time()
        found, used = search.find(level)

        # Measure the output growth of every solution used before the last stage (once per solution).
        inner = {problems[name].solutions[i].line: problems[name].solutions[i]
                 for chain, _ in found for name, i in chain[:-1]}
        todo = [s for line, s in inner.items() if line not in growth]
        for s, g in zip(todo, pool.map(lambda s: measure_growth(s.src), todo)):
            growth[s.line] = dict(g, problem=s.problem, label=s.label)

        results = pool.map(lambda c: make_record(level, c[0], c[1], problems, growth), found)
        kept, dropped, seen_src = [], Counter(), set()
        for record, reason in results:
            if record is None:
                dropped[reason] += 1
            elif record["src"] in seen_src:
                dropped["duplicate program"] += 1
            else:
                seen_src.add(record["src"])
                record = {"id": f"L{level}_{len(kept):04d}", **record}
                kept.append(record)

        path = os.path.join(args.out, f"chains_L{level}.jsonl")
        with open(path, "w") as f:
            for record in kept:
                f.write(json.dumps(record) + "\n")
        runner.cache.save()
        report[f"L{level}"] = dict(found=len(found), kept=len(kept), labels=dict(Counter(r["complexity"] for r in kept)),
                                   dropped=dict(dropped), extensions_tried=used, seconds=round(time.time() - t, 1))
        print(f"level {level}: {report[f'L{level}']}", flush=True)

    with open(os.path.join(args.out, "growth.json"), "w") as f:
        json.dump({str(line): dict(problem=g["problem"], label=g["label"], output_growth=big_o(g["cls"]),
                                   fit_error=g["error"], note=g["note"], points=g["points"])
                   for line, g in sorted(growth.items())}, f, indent=1)
    report["seconds"] = round(time.time() - started, 1)
    with open(os.path.join(args.out, "report.json"), "w") as f:
        json.dump(report, f, indent=1)
    pool.shutdown()
    runner.cache.save()


if __name__ == "__main__":
    main()
