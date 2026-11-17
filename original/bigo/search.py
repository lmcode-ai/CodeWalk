"""
search.py -- find chains  f_k(...f_2(f_1(x)))  that actually work.

A "stage" is one solution of one problem.  A chain is a list of stages.  To test a chain we push a
set of starting integers through it, one stage at a time:

    x -> stage 1 -> v1 -> stage 2 -> v2 -> ...

A value v may enter a stage only if that problem's checkers agree v is a valid input
(Problem.accepts), and the stage must then print a usable answer.  Inputs that fail are dropped;
the chain survives while at least `min_alive` inputs make it through every stage.

The search is a random depth-first search: start from a random stage, try random next stages, and
back up when too few inputs survive.  A budget limits how many stage extensions are tried.
"""
import random
from collections import Counter
from dataclasses import dataclass

from runner import run, as_int, tidy, same_output

START_INPUTS = [1, 2, 3, 4, 5, 6, 7, 8, 10, 13, 21, 47, 100, 1000]


@dataclass
class SearchSettings:
    max_chains: int = 500         # stop a level after this many chains
    max_per_sequence: int = 4     # at most this many chains with the same sequence of problems
    budget: int = 100000          # stage extensions tried per level
    restart_budget: int = 300     # extensions tried from one random start before starting over
    min_alive: int = 3            # inputs that must survive every stage
    min_outputs: int = 2          # different final answers needed (so the chain is not a constant)


class ChainSearch:
    def __init__(self, problems, settings, pool, seed=0):
        self.problems = problems                  # name -> Problem
        self.settings = settings
        self.pool = pool                          # thread pool for running stages in parallel
        self.seed = seed
        # every stage, as (problem name, solution index)
        self.stages = [(name, i) for name in sorted(problems) for i in range(len(problems[name].solutions))]
        self.outputs = {}                         # memo: (problem, solution index, value) -> answer or None

    # ---------------------------------------------------------- running one stage
    def answer(self, stage, value):
        """What the stage prints for `value` (an int, or text for non-integer problems); None on failure."""
        key = (*stage, value)
        if key not in self.outputs:
            name, i = stage
            problem = self.problems[name]
            ok, out = run(problem.solutions[i].src, f"{value}\n")
            result = None
            if ok:
                result = as_int(out) if problem.int_output else (tidy(out) or None)
            if result is not None and i > 0:      # other solutions must agree with the reference solution
                reference = self.answer((name, 0), value)
                if reference is None or not (result == reference if problem.int_output
                                             else same_output(result, reference)):
                    result = None
            self.outputs[key] = result
        return self.outputs[key]

    def answer_if_valid(self, stage, value):
        return self.answer(stage, value) if self.problems[stage[0]].accepts(value) else None

    def advance(self, stage, traces):
        """Push every surviving input one stage further.

        traces: {starting input: [x, v1, v2, ...]}.  Returns the traces that survive this stage."""
        values = sorted({trace[-1] for trace in traces.values()})
        answers = dict(zip(values, self.pool.map(lambda v: self.answer_if_valid(stage, v), values)))
        return {x: trace + [answers[trace[-1]]] for x, trace in traces.items()
                if answers[trace[-1]] is not None}

    # ---------------------------------------------------------- searching
    def find(self, level):
        """Find up to max_chains chains with `level` stages.  Returns [(chain, traces)] and extensions used."""
        s = self.settings
        rng = random.Random(f"{self.seed}:{level}")
        self.budget = s.budget
        self.found, self.seen, self.per_sequence = [], set(), Counter()

        # A stage whose problem can only come last cannot start a chain (unless the chain has one stage).
        starts = [st for st in self.stages if level == 1 or not self.problems[st[0]].last_only]
        failures_in_a_row = 0
        while starts and len(self.found) < s.max_chains and self.budget > 0 and failures_in_a_row < 3 * len(starts):
            start = rng.choice(starts)
            self.restart_left = s.restart_budget
            traces = self.advance(start, {x: [x] for x in START_INPUTS})
            result = self.extend([start], traces, level, rng) if len(traces) >= s.min_alive else None
            if result is None:
                failures_in_a_row += 1
                continue
            failures_in_a_row = 0
            chain, traces = result
            self.seen.add(tuple(chain))
            self.per_sequence[tuple(name for name, _ in chain)] += 1
            self.found.append(result)
        return self.found, s.budget - self.budget

    def extend(self, chain, traces, level, rng):
        """Depth-first: add stages until the chain has `level` of them.  Returns (chain, traces) or None."""
        if len(chain) == level:
            return (chain, traces) if self.is_wanted(chain, traces, level) else None
        adding_last = len(chain) + 1 == level
        candidates = [st for st in self.stages
                      if st[0] != chain[-1][0]                                   # no problem twice in a row
                      and (adding_last or not self.problems[st[0]].last_only)]
        rng.shuffle(candidates)
        for stage in candidates:
            if self.budget <= 0 or self.restart_left <= 0:
                return None
            self.budget -= 1
            self.restart_left -= 1
            new_traces = self.advance(stage, traces)
            if len(new_traces) >= self.settings.min_alive:
                result = self.extend(chain + [stage], new_traces, level, rng)
                if result:
                    return result
        return None

    def is_wanted(self, chain, traces, level):
        """Keep a finished chain only if it is new and does something non-trivial."""
        s = self.settings
        # The values must actually change along the way: each surviving trace needs a few distinct values.
        min_distinct = 2 if level <= 2 else 3
        changing = sum(len(set(trace)) >= min_distinct for trace in traces.values())
        final_answers = {trace[-1] for trace in traces.values()}
        return (changing >= s.min_alive
                and len(final_answers) >= s.min_outputs
                and tuple(chain) not in self.seen
                and self.per_sequence[tuple(name for name, _ in chain)] < s.max_per_sequence)
