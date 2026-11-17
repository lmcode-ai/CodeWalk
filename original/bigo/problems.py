"""
problems.py -- load the dataset and decide which problems can be chain stages.

A problem can be a stage if its input is one integer.  We cannot read that from the problem
statement, so we test it: several solutions of the same problem ("siblings") are run on the same
small integers, and they must print the same answer.  If they agree on enough inputs, the input is
taken to be one integer and the agreeing siblings become the problem's "checkers".

Later, when a chain wants to feed a value v into this problem, the checkers are run on v first.
The value is accepted only if they all agree, i.e. v is a valid input for the problem.
"""
import json
import math
import random
from collections import defaultdict
from dataclasses import dataclass, field

from convert import can_convert
from runner import run, as_int, tidy, same_output

TEST_INPUTS = [1, 2, 3, 4, 5, 6, 7, 8, 10, 13, 21, 47, 100, 1000]   # small integers every problem is tried on
BIG_INPUTS = [10**4, 10**6, 10**9]     # larger sizes probed to find how big an input a problem handles
NEGATIVE_LIMIT = -100                  # negative inputs are only ever tried down to this
SIBLINGS = 5            # siblings sampled per problem for the test
ATTEMPTS = 3            # new sample of siblings if one broken solution spoils the agreement
MIN_AGREED = 3          # test inputs the siblings must agree on
CHECKERS = 3            # agreeing siblings used later to accept values
SOLUTIONS_PER_PROBLEM = 3


@dataclass
class Solution:
    problem: str
    line: int             # line number in the data file (0-based)
    src: str
    label: str            # the dataset's complexity label for this solution
    verified: bool = True # True if it was one of the agreeing siblings


@dataclass
class Problem:
    name: str
    solutions: list       # solutions used as stages; solutions[0] is the reference the others must match
    checkers: list        # sources of the siblings that decide whether a value is a valid input
    int_output: bool      # prints a single integer, so it can feed another stage
    last_only: bool       # can only be the last stage (non-integer output, or the same answer for every input)
    support: int          # how many siblings agreed on every test input
    min_value: int        # smallest input worth trying (1, 0 or NEGATIVE_LIMIT)
    max_value: int        # largest input worth trying (1000 or one of BIG_INPUTS)
    accepted: dict = field(default_factory=dict)   # memo: value -> is it a valid input?

    def accepts(self, value):
        """Is `value` a valid input?  It must be in the problem's range, and all checkers
        must run on it and print the same answer."""
        if value not in self.accepted:
            ok = self.min_value <= value <= self.max_value
            if ok:
                answer, _ = agreed_answer(self.checkers, f"{value}\n", need=len(self.checkers))
                ok = answer is not None
            self.accepted[value] = ok
        return self.accepted[value]


def load_convertible(path):
    """All solutions that can be turned into a stage function, grouped by problem."""
    by_problem = defaultdict(list)
    total = 0
    with open(path) as f:
        for line_no, line in enumerate(f):
            if not line.strip():
                continue
            total += 1
            record = json.loads(line)
            if can_convert(record["src"]):
                by_problem[record["problem"]].append(
                    Solution(record["problem"], line_no, record["src"], record["complexity"]))
    return by_problem, total


def agreed_answer(sources, stdin_text, need):
    """Run every source on the same input.  Returns (answer, indices that ran) if all that ran
    printed the same answer and at least `need` of them ran; otherwise (None, [])."""
    answer, ran = None, []
    for i, src in enumerate(sources):
        ok, out = run(src, stdin_text)
        if not (ok and out.strip()):
            if len(sources) - (i + 1 - len(ran)) < need:   # too many failures to still reach `need`
                return None, []
            continue
        if answer is not None and not same_output(answer, out):
            return None, []                                # two siblings disagree
        answer = answer if answer is not None else out
        ran.append(i)
    return (answer, ran) if len(ran) >= need else (None, [])


def check_problem(name, solutions):
    """Return a Problem if its input is one integer and its siblings agree, else None."""
    for attempt in range(ATTEMPTS):
        rng = random.Random(f"{name}:{attempt}")
        siblings = solutions if len(solutions) <= SIBLINGS else rng.sample(solutions, SIBLINGS)
        sources = [s.src for s in siblings]
        need = max(math.ceil(0.6 * len(sources)), 2 if len(sources) > 1 else 1)

        # Run the siblings on the test inputs and keep the inputs they agree on.
        agreed = []                     # (input text, answer)
        ran_on_all = defaultdict(int)   # sibling index -> number of agreed inputs it ran on
        for i, x in enumerate(TEST_INPUTS):
            answer, ran = agreed_answer(sources, f"{x}\n", need)
            if answer is not None:
                agreed.append((f"{x}\n", tidy(answer)))
                for j in ran:
                    ran_on_all[j] += 1
            elif i >= 3 and not agreed:
                break                   # nothing agreed on the first four inputs: give up early
        if len(agreed) < MIN_AGREED:
            continue

        # Siblings that ran on every agreed input; if there are none, the one that ran on the most.
        fully_agreeing = [j for j in range(len(siblings)) if ran_on_all[j] == len(agreed)]
        good = fully_agreeing or [max(ran_on_all, key=ran_on_all.get)]
        min_value, max_value, extra_answers = probe_range(sources, need, rng)
        answers = [a for _, a in agreed] + extra_answers
        int_output = all(as_int(a) is not None for a in answers)
        return Problem(
            name=name,
            solutions=pick_solutions(name, siblings, good, solutions, agreed),
            checkers=[siblings[j].src for j in good[:CHECKERS]],
            int_output=int_output,
            last_only=not int_output or len(set(answers)) < 2,
            support=len(fully_agreeing),
            min_value=min_value,
            max_value=max_value,
        )
    return None


def probe_range(sources, need, rng):
    """Find which inputs beyond the test inputs the problem handles.  A kind of input counts if the
    siblings agree on at least 2 of 3 random tries.  Returns (min_value, max_value, answers seen)."""
    answers = []

    def works(pick):
        agreed = 0
        for _ in range(3):
            answer, _ = agreed_answer(sources, f"{pick()}\n", need)
            if answer is not None:
                agreed += 1
                answers.append(tidy(answer))
        return agreed >= 2

    max_value = max(TEST_INPUTS)
    for size in BIG_INPUTS:                  # stop at the first size the siblings cannot handle
        if not works(lambda: rng.randint(size // 10, size)):
            break
        max_value = size
    negatives_ok = works(lambda: rng.randint(NEGATIVE_LIMIT, -1))
    zero_ok = works(lambda: 0)
    min_value = NEGATIVE_LIMIT if negatives_ok and zero_ok else 0 if zero_ok else 1
    return min_value, max_value, answers


def pick_solutions(name, siblings, good, all_solutions, agreed):
    """Up to SOLUTIONS_PER_PROBLEM solutions to use as stages: the agreeing siblings first,
    then other solutions that reproduce the agreed answers."""
    picked = [siblings[j] for j in good][:SOLUTIONS_PER_PROBLEM]
    used = {s.line for s in picked}
    others = [s for s in all_solutions if s.line not in used]
    random.Random(f"0:{name}:reps").shuffle(others)
    for s in others:
        if len(picked) >= SOLUTIONS_PER_PROBLEM:
            break
        if all(run(s.src, x)[0] and same_output(run(s.src, x)[1], a) for x, a in agreed[:8]):
            picked.append(Solution(s.problem, s.line, s.src, s.label, verified=False))
    return picked
