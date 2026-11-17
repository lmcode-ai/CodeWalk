"""Verus-Bench composition generator (end-to-end existential specification).

Lifts each function's ensures into a `step_k` spec predicate, chains K functions,
and gives the driver an existential end-to-end postcondition witnessed by the
real intermediate values.

Rebuilt 2026-08-10 after scratchpad loss; includes all previously-fixed issues:
  * &[u8] / Vec<T> -> Seq<T> lifting
  * #![verifier::loop_isolation(false)] carried over as a fn-level attribute
  * multi-param downstream fns (scalar extras hoisted to driver params)
"""
import json
import os
import re

POOL_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "verus_pool")

SCALARS = {"i8", "i16", "i32", "i64", "i128", "u8", "u16", "u32", "u64", "u128",
           "usize", "isize", "bool", "char", "int", "nat"}


# ---------------------------------------------------------------- parsing

def extract_verus_block(txt):
    m = re.search(r'verus!\s*\{', txt)
    if not m:
        return None
    depth, i = 1, m.end()
    while i < len(txt) and depth:
        if txt[i] == "{":
            depth += 1
        elif txt[i] == "}":
            depth -= 1
        i += 1
    return txt[m.end():i - 1]


def match_paren(s, i):
    depth = 0
    for j in range(i, len(s)):
        if s[j] == "(":
            depth += 1
        elif s[j] == ")":
            depth -= 1
            if depth == 0:
                return j
    return -1


def top_level_names(block):
    return set(re.findall(r'^\s*(?:pub\s+)?(?:spec\s+fn|proof\s+fn|fn)\s+(\w+)', block, re.M))


def parse_fns(block):
    """Exec fns with a named return value and an ensures clause."""
    fns = []
    for m in re.finditer(r'^(?:pub\s+)?fn\s+(\w+)\s*\(', block, re.M):
        prefix = block[max(0, m.start() - 20):m.start()].strip().split("\n")[-1]
        if re.search(r'(spec|proof)\s*$', prefix):
            continue
        p_open = block.index("(", m.end() - 1)
        p_close = match_paren(block, p_open)
        if p_close < 0:
            continue
        after = block[p_close + 1:]
        rm = re.match(r'\s*->\s*\(', after)
        if not rm:
            continue
        r_open = rm.end() - 1
        r_close = match_paren(after, r_open)
        ret = after[r_open + 1:r_close]
        if r_close < 0 or ":" not in ret or "(" in ret.split(":", 1)[1]:
            continue
        rname, rtype = (x.strip() for x in ret.split(":", 1))
        brace = after.find("{", r_close)
        if brace < 0:
            continue
        spec_s = after[r_close + 1:brace]
        params = []
        depth, cur = 0, ""
        for ch in block[p_open + 1:p_close]:
            if ch in "<(":
                depth += 1
            elif ch in ">)":
                depth -= 1
            if ch == "," and depth == 0:
                params.append(cur)
                cur = ""
            else:
                cur += ch
        if cur.strip():
            params.append(cur)
        plist = [(n.strip(), re.sub(r'\s+', '', t))
                 for n, t in (p.split(":", 1) for p in params if ":" in p)]
        req = re.search(r'requires(.*?)(?=ensures|$)', spec_s, re.S)
        if not re.search(r'ensures', spec_s):
            continue
        fns.append({"name": m.group(1), "params": plist, "rname": rname,
                    "rtype": re.sub(r'\s+', '', rtype),
                    "requires": req.group(1).strip().rstrip(",") if req else ""})
    return fns


def load_pool():
    pool = []
    for fn in sorted(os.listdir(POOL_DIR)):
        if not fn.endswith(".rs"):
            continue
        txt = open(os.path.join(POOL_DIR, fn), errors="replace").read()
        block = extract_verus_block(txt)
        if block is None:
            continue
        fns = parse_fns(block)
        if not fns:
            continue
        pool.append({"file": fn, "block": block, "fns": fns,
                     "names": top_level_names(block),
                     "uses": [u for u in re.findall(r'^use .*?;', txt, re.M)
                              if u != "use vstd::prelude::*;"],
                     "loop_iso": "loop_isolation(false)" in txt})
    return pool


# ---------------------------------------------------------------- types

def nrm(t):
    return t.replace("&", "").replace("mut", "")


def is_view(t):
    t = nrm(t)
    return t.startswith("Vec<") or (t.startswith("[") and t.endswith("]"))


def seq_of(t):
    t = nrm(t)
    m = re.match(r'Vec<(.*)>$', t) or re.match(r'\[(.*)\]$', t)
    return f"Seq<{m.group(1)}>" if m else t


def is_scalar(t):
    return nrm(t) in SCALARS


def adapter(prev_rt, pt):
    """How to pass an upstream value of type prev_rt into a param of type pt."""
    a, b = nrm(prev_rt), nrm(pt)
    if a == b:
        return (lambda x: f"&{x}") if pt.startswith("&") and not prev_rt.startswith("&") else (lambda x: x)
    ma, mb = re.match(r'Vec<(.*)>$', a), re.match(r'\[(.*)\]$', b)
    if ma and mb and ma.group(1) == mb.group(1):
        return lambda x: f"{x}.as_slice()"
    return None


def chain_param_idx(f, prev_rt):
    for i, (_, t) in enumerate(f["params"]):
        if adapter(prev_rt, t):
            return i
    return -1


def usable_downstream(f, prev_rt):
    """Index of the chained param, if the other params are all scalars."""
    i = chain_param_idx(f, prev_rt)
    if i < 0:
        return None
    if any(not is_scalar(t) for j, (_, t) in enumerate(f["params"]) if j != i):
        return None
    return i


# ---------------------------------------------------------------- building

def prefixed(entry, k):
    block = entry["block"]
    for n in sorted(entry["names"], key=len, reverse=True):
        block = re.sub(r'(?<![\.\w])' + re.escape(n) + r'\b', f"f{k}_{n}", block)
    if entry.get("loop_iso"):
        block = re.sub(r'^((?:pub\s+)?fn\s+f\d+_)',
                       r'#[verifier::loop_isolation(false)]\n\1', block, flags=re.M)
    return block


def rewrite(expr, name, newvar, view):
    if view:
        expr = re.sub(r'\b' + re.escape(name) + r'@', newvar, expr)
        expr = re.sub(r'\b' + re.escape(name) + r'\.len\(\)', newvar + '.len()', expr)
        expr = re.sub(r'\b' + re.escape(name) + r'\[', newvar + '[', expr)
    return re.sub(r'\b' + re.escape(name) + r'\b', newvar, expr)


def get_ensures(block, fname):
    m = re.search(r'fn\s+' + re.escape(fname) + r'\b.*?ensures(.*?)\n\{', block, re.S)
    return m.group(1).strip().rstrip(",") if m else None


def split_clauses(text):
    """Split an ensures/requires list on top-level commas only.

    Splitting naively on ",\\n" breaks clauses that span lines inside a call's
    argument list (trailing commas there are not clause separators), which used
    to emit bogus fragments like `&& ()`.
    """
    out, depth, cur, in_binder = [], 0, "", False
    i = 0
    while i < len(text):
        ch = text[i]
        if ch in "([{":
            depth += 1
        elif ch in ")]}":
            depth -= 1
        elif ch == "|" and text[i:i + 2] != "||" and (i == 0 or text[i - 1] != "|"):
            in_binder = not in_binder          # forall|..|, exists|..|, closures
        if ch == "," and depth == 0 and not in_binder:
            if cur.strip():
                out.append(cur.strip())
            cur = ""
        else:
            cur += ch
        i += 1
    if cur.strip():
        out.append(cur.strip())
    return out


def build(entries, fns):
    """Return the composed reference file, or None if the chain can't be built."""
    n = len(fns)
    blocks = [prefixed(e, k + 1) for k, e in enumerate(entries)]
    step_defs, extra_params, extra_reqs = [], [], []
    calls, step_args = [], []
    prev_rt = None
    for k, f in enumerate(fns):
        pf = f"f{k+1}_{f['name']}"
        ens = get_ensures(blocks[k], pf)
        if ens is None:
            return None
        ci = 0 if k == 0 else chain_param_idx(f, prev_rt)
        if k > 0 and ci < 0:
            return None
        spec_params, call_args, s_args = [], [], []
        for j, (pn, pt) in enumerate(f["params"]):
            if k == 0:
                ens = rewrite(ens, pn, f"__hp{j}", is_view(pt))
                spec_params.append((f"__hp{j}", seq_of(pt)))
                call_args.append(pn)
                s_args.append(pn + ("@" if is_view(pt) else ""))
            elif j == ci:
                ens = rewrite(ens, pn, "inp", is_view(pt))
                spec_params.append(("inp", seq_of(pt)))
                call_args.append(None)
                s_args.append(None)
            else:
                hn = f"p{k+1}_{pn}"
                ens = rewrite(ens, pn, hn, False)
                spec_params.append((hn, nrm(pt)))
                extra_params.append((hn, nrm(pt)))
                call_args.append(hn)
                s_args.append(hn)
        ens = rewrite(ens, f["rname"], "outp", is_view(f["rtype"]))
        body = "\n    && ".join(f"({c})" for c in split_clauses(ens))
        sig = ", ".join(f"{a}: {t}" for a, t in spec_params) + f", outp: {seq_of(f['rtype'])}"
        step_defs.append(f"spec fn step{k+1}({sig}) -> bool {{\n    {body}\n}}")
        if f["requires"].strip():
            for c in split_clauses(f["requires"]):
                if k == 0:
                    extra_reqs.append(c)
                else:
                    cp = f["params"][ci][0]
                    if not re.search(r'\b' + re.escape(cp) + r'\b', c):
                        for j, (pn, _) in enumerate(f["params"]):
                            if j != ci:
                                c = rewrite(c, pn, f"p{k+1}_{pn}", False)
                        extra_reqs.append(c)
        calls.append((pf, call_args, ci))
        step_args.append(s_args)
        prev_rt = f["rtype"]

    head, tail = fns[0], fns[-1]
    drv_params = [f"{p}: {t}" for p, t in head["params"]] + \
                 [f"{a}: {t}" for a, t in extra_params]
    rN = "r_final" + ("@" if is_view(tail["rtype"]) else "")
    terms, bounds = [], []
    for k, f in enumerate(fns):
        args = list(step_args[k])
        if k > 0:
            args[args.index(None)] = f"v{k}"
        out = rN if k == n - 1 else f"v{k+1}"
        if k < n - 1:
            bounds.append(f"v{k+1}: {seq_of(f['rtype'])}")
        t = f"step{k+1}({', '.join(args)}, {out})"
        terms.append(("#[trigger] " + t) if k < n - 1 else t)
    ens_line = (terms[0] if n == 1
                else f"exists|{', '.join(bounds)}| " + " && ".join(terms))
    req_block = ("    requires\n" + "".join(f"        {c},\n" for c in extra_reqs)) if extra_reqs else ""

    body_lines, asserts = [], []
    for k, (pf, cargs, ci) in enumerate(calls):
        args = list(cargs)
        if k > 0:
            args[ci] = adapter(fns[k - 1]["rtype"], fns[k]["params"][ci][1])(f"x{k}")
        body_lines.append(f"    let x{k+1} = {pf}({', '.join(args)});")
    for k, f in enumerate(fns):
        args = list(step_args[k])
        if k > 0:
            args[args.index(None)] = f"x{k}" + ("@" if is_view(fns[k - 1]["rtype"]) else "")
        out = f"x{k+1}" + ("@" if is_view(f["rtype"]) else "")
        asserts.append(f"        assert(step{k+1}({', '.join(args)}, {out}));")
    driver = (f"fn chain_driver({', '.join(drv_params)}) -> (r_final: {tail['rtype']})\n"
              + req_block + f"    ensures\n        {ens_line},\n{{\n"
              + "\n".join(body_lines) + "\n    proof {\n" + "\n".join(asserts)
              + f"\n    }}\n    x{n}\n}}")
    uses = sorted({u for e in entries for u in e.get("uses", [])})
    return ("use vstd::prelude::*;\n" + "\n".join(uses) + ("\n" if uses else "")
            + "fn main() {}\nverus!{\n\n" + "\n\n".join(blocks) + "\n\n"
            + "\n\n".join(step_defs) + "\n\n" + driver + "\n\n} // verus!\n")
