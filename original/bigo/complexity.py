"""
complexity.py -- work out the time complexity of a chain.

Model.  On chain input n, stage i receives the value G_{i-1}(n) and takes time T_i of that value:

        cost(n) = T_1(n) + T_2(G_1(n)) + T_3(G_2(n)) + ...      G_0(n) = n,  G_i = g_i(G_{i-1}(n))

  T_i  = the stage's running time as a function of its input value: its dataset label
         (constant, logn, linear, nlogn, quadratic, cubic, np  ->  1, log m, m, m log m, m^2, m^3, 2^m).
  g_i  = how big the stage's OUTPUT is as a function of its input value.  The labels do not say this,
         so we measure it: run the stage on growing inputs and fit a curve to the largest outputs.

The chain's complexity is the biggest term.  Example: a constant-time stage that returns about n^3,
followed by a linear stage, costs n^3 overall -- the chain is cubic.

Growth classes are  n^a (log n)^b  stored as a tuple (a, b), or EXP for 2^n.
"""
import math
import random
from fractions import Fraction as F

from runner import run, as_int

EXP = "exp"
LABEL_TO_CLASS = {"constant": (F(0), 0), "logn": (F(0), 1), "linear": (F(1), 0), "nlogn": (F(1), 1),
                  "quadratic": (F(2), 0), "cubic": (F(3), 0), "np": EXP}
CLASS_TO_LABEL = {cls: label for label, cls in LABEL_TO_CLASS.items()}
CONSTANT = LABEL_TO_CLASS["constant"]


def big_o(cls):
    """(2, 1) -> 'O(n^2 log n)'"""
    if cls is None:
        return None
    if cls == EXP:
        return "O(2^n)"
    a, b = cls
    if a == 0 and b == 0:
        return "O(1)"
    parts = []
    if a:
        parts.append("n" if a == 1 else f"n^{a}" if a.denominator == 1 else f"n^({a})")
    if b:
        parts.append("log n" if b == 1 else f"log^{b} n")
    return "O(" + " ".join(parts) + ")"


def size_order(cls):
    """Sort key: bigger means grows faster."""
    return (1, 0, 0) if cls == EXP else (0, *cls)


# ================================================================== algebra
def apply(T, G):
    """Growth class of T(G(n)): T applied to a value of size G(n).

    Returns None when the result is not of the form n^a log^b n or 2^n (e.g. log log n)."""
    if T == CONSTANT or G == CONSTANT:
        return CONSTANT                                  # constant function, or a bounded argument
    if G == EXP:                                         # the argument is about 2^n
        if T == EXP:
            return EXP                                   # really 2^(2^n); only np stages do this
        a, b = T
        return EXP if a > 0 else (F(b), 0)               # poly(2^n) = 2^O(n);  log^b(2^n) = n^b
    c, d = G                                             # the argument is about n^c log^d n
    if T == EXP:
        if c > 0:
            return EXP
        return (F(1), 0) if d == 1 else None             # 2^(log n) = n
    a, b = T                                             # T(m) = m^a log^b m
    if c > 0:
        return (c * a, d * a + b)                        # log(n^c ...) is still about log n
    # The argument is log^d n: only a pure power of it stays in our classes.
    if b == 0 and (d * a).denominator == 1:
        return (F(0), int(d * a))
    return None


def chain_cost(labels, growths):
    """labels: each stage's dataset label.  growths: each stage's output growth (last one unused).

    Returns {"terms": cost class of every stage, "total": the biggest, "dominant": its index},
    or None if a term cannot be expressed in our classes."""
    size = (F(1), 0)                                     # stage 1 sees the chain input n
    terms = []
    for i, label in enumerate(labels):
        cost = apply(LABEL_TO_CLASS[label], size)
        if cost is None:
            return None
        terms.append(cost)
        if i < len(labels) - 1:
            size = apply(growths[i], size)
            if size is None:
                return None
    dominant = max(range(len(terms)), key=lambda i: size_order(terms[i]))
    return {"terms": terms, "total": terms[dominant], "dominant": dominant}


# ================================================================== measuring output growth
SIZES = [10, 30, 100, 300, 1000, 3000, 10**4, 10**5, 10**6]
# Highly composite numbers: they bring out solutions whose answer depends on divisors.
HIGHLY_COMPOSITE = [12, 60, 360, 840, 2520, 5040, 27720, 55440, 720720]
# Exponents a tried in the fit n^a log^b n (b is 0, 1 or 2).
EXPONENTS = [F(0), F(1, 3), F(1, 2), F(2, 3), F(1), F(3, 2), F(2), F(3), F(4), F(5)]
CLOSE_ENOUGH = 0.1     # prefer the simplest class whose fit error is within this of the best
NO_FIT = 0.3           # a best polynomial fit worse than this means "no polynomial fits"


def inputs_near(N, rng):
    """About ten inputs of size around N: N itself, neighbours, a power of two, random ones, divisor-rich ones."""
    xs = [N, max(1, N - 1), N + 1, max(1, 9 * N // 10), 1 << (N.bit_length() - 1)]
    xs += [rng.randint(max(1, N // 10), N) for _ in range(3)]
    xs += sorted(h for h in HIGHLY_COMPOSITE if h <= N)[-2:]
    return list(dict.fromkeys(xs))                       # drop duplicates, keep order


def rank_correlation(values):
    """Spearman correlation between position and value (1 = always increasing)."""
    n = len(values)
    order = sorted(range(n), key=lambda i: values[i])
    rank = [0.0] * n
    i = 0
    while i < n:                                         # tied values share their average rank
        j = i
        while j + 1 < n and values[order[j + 1]] == values[order[i]]:
            j += 1
        for k in range(i, j + 1):
            rank[order[k]] = (i + j) / 2
        i = j + 1
    mean_pos, mean_rank = (n - 1) / 2, sum(rank) / n
    num = sum((i - mean_pos) * (rank[i] - mean_rank) for i in range(n))
    den = math.sqrt(sum((i - mean_pos) ** 2 for i in range(n)) * sum((r - mean_rank) ** 2 for r in rank))
    return num / den if den else 0.0


def fit_growth(points):
    """points: [(input size N, largest |output| near N)].  Returns (class or None, fit error, note)."""
    points = sorted((N, max(1, M)) for N, M in points)
    if len(points) < 4:
        return None, None, f"only {len(points)} input sizes ran"
    Ns, Ms = [p[0] for p in points], [p[1] for p in points]
    if len(set(Ms)) == 1 or rank_correlation(Ms) < 0.7:
        return CONSTANT, 0.0, "bounded: no upward trend"

    # Fit  log M = a log N + b log(log N + 2) + const  for every candidate (a, b); error = sum of squares.
    # (log N + 2 instead of log N absorbs the "+1" of digit and bit counts.)
    xs, ys = [math.log(N) for N in Ns], [math.log(M) for M in Ms]

    def error(a, b):
        residuals = [y - a * x - b * math.log(x + 2) for x, y in zip(xs, ys)]
        mean = sum(residuals) / len(residuals)
        return sum((r - mean) ** 2 for r in residuals)

    candidates = [(error(float(a), b), a, b) for a in EXPONENTS for b in (0, 1, 2) if (a, b) != (0, 0)]
    best = min(e for e, _, _ in candidates)
    if best <= NO_FIT:
        # Among the fits almost as good as the best, take the slowest-growing one.
        _, a, b = min((c for c in candidates if c[0] <= best + CLOSE_ENOUGH), key=lambda c: (c[1], c[2]))
        return (a, b), best, "ok"

    # No polynomial fits: is log M a straight line in N (exponential growth)?
    n = len(Ns)
    mean_x, mean_y = sum(Ns) / n, sum(ys) / n
    slope = sum((x - mean_x) * (y - mean_y) for x, y in zip(Ns, ys)) / sum((x - mean_x) ** 2 for x in Ns)
    exp_error = sum((y - mean_y - slope * (x - mean_x)) ** 2 for x, y in zip(Ns, ys))
    if slope > 0 and exp_error < best / 3 and exp_error < NO_FIT:
        return EXP, exp_error, "log(output) is linear in the input: exponential"
    return None, best, f"no growth model fits (best error {best:.2f})"


def measure_growth(src, seed=0):
    """Run a solution on growing inputs and fit the growth of its (integer) output."""
    rng = random.Random(seed)
    points = []
    for N in SIZES:
        largest = None
        for j, x in enumerate(inputs_near(N, rng)):
            ok, out = run(src, f"{x}\n")
            if not ok:
                if j == 0:
                    break                                # failed on N itself: stop growing
                continue
            value = as_int(out)
            if value is None:
                return dict(cls=None, error=None, points=points, note="output is not a single integer")
            largest = abs(value) if largest is None else max(largest, abs(value))
        if largest is None:
            break
        points.append((N, largest))
    cls, err, note = fit_growth(points)
    return dict(cls=cls, error=err, points=points, note=note)


# ================================================================== self-test
def self_test():
    L = LABEL_TO_CLASS
    q4 = (F(4), 0)
    for T, G, want in [(L["quadratic"], L["linear"], L["quadratic"]), (L["quadratic"], L["quadratic"], q4),
                       (L["logn"], L["quadratic"], L["logn"]), (L["quadratic"], L["logn"], (F(0), 2)),
                       (L["nlogn"], L["quadratic"], (F(2), 1)), (L["constant"], L["cubic"], CONSTANT),
                       (L["np"], L["logn"], L["linear"]), (L["logn"], EXP, L["linear"]),
                       ((F(1, 2), 0), L["quadratic"], L["linear"])]:
        assert apply(T, G) == want, (big_o(T), big_o(G), big_o(apply(T, G)))
    r = chain_cost(["constant", "linear"], [L["cubic"]])
    assert r["total"] == L["cubic"] and r["dominant"] == 1
    r = chain_cost(["linear", "constant", "quadratic"], [L["linear"], CONSTANT])
    assert r["total"] == L["linear"]
    print("algebra: ok")
    for src, want in [("n=int(input())\nprint(n*n)", "O(n^2)"), ("n=int(input())\nprint(n%7)", "O(1)"),
                      ("n=int(input())\nprint(len(str(n)))", "O(log n)"),
                      ("import math\nn=int(input())\nprint(math.isqrt(n))", "O(n^(1/2))"),
                      ("n=int(input())\nprint(n*len(str(n)))", "O(n log n)"),
                      ("n=int(input())\nprint(2**n)", "O(2^n)")]:
        got = big_o(measure_growth(src)["cls"])
        assert got == want, (src, got, want)
    print("growth measurement: ok")


if __name__ == "__main__":
    self_test()
