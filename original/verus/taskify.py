"""Turn a certified composition into a task: delete the chained fns' ensures and
their in-body proof annotations, keep the driver (incl. its proof block) frozen.
"""
import os
import re
import subprocess

HERE = os.path.dirname(os.path.abspath(__file__))
VERUS = f"{HERE}/tools/verus-x86-linux/verus"


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


def strip_body_annotations(body):
    while True:                                   # proof { ... }
        m = re.search(r'\bproof\s*\{', body)
        if not m:
            break
        end = match_brace(body, body.index("{", m.start()))
        if end < 0:
            break
        body = body[:m.start()] + body[end + 1:]
    while True:                                   # assert ... by { ... };
        m = re.search(r'\bassert\b[^;{]*\bby\s*\{', body)
        if not m:
            break
        end = match_brace(body, body.rindex("{", m.start(), m.end()))
        if end < 0:
            break
        tail = body[end + 1:]
        body = body[:m.start()] + (tail[1:] if tail.startswith(";") else tail)
    body = re.sub(r'^[ \t]*assert\b[^;]*;[ \t]*\n', '', body, flags=re.M)
    body = re.sub(r'^[ \t]*let\s+ghost\b[^;]*;[ \t]*\n', '', body, flags=re.M)
    body = re.sub(r'^[ \t]*reveal(_with_fuel)?\([^;]*\);[ \t]*\n', '', body, flags=re.M)
    # invariant / decreases sections, single- or multi-line, before the loop brace
    body = re.sub(r'^[ \t]*invariant\b.*?(?=^[ \t]*(decreases\b|\{))', '', body,
                  flags=re.M | re.S)
    body = re.sub(r'^[ \t]*decreases\b.*?(?=^[ \t]*\{)', '', body, flags=re.M | re.S)
    body = re.sub(r'^[ \t]*decreases\b[^\n]*\n(?=[ \t]*\{)', '', body, flags=re.M)
    return body


def body_brace(s, start):
    """First `{` at paren/bracket depth 0 after the signature = the body brace.

    Braces inside an ensures expression (e.g. `(if x { a } else { b })`) sit at
    paren depth > 0, so plain `index("{")` would split the fn in the wrong place.
    """
    d = 0
    for i in range(start, len(s)):
        c = s[i]
        if c in "([":
            d += 1
        elif c in ")]":
            d -= 1
        elif c == "{" and d == 0:
            return i
    return -1


def taskify(txt):
    out = txt
    for m in list(re.finditer(r'^(?:pub )?fn f\d+_\w+', out, re.M)):
        name = m.group(0).split("fn ")[1]
        mm = re.search(r'^(?:pub )?fn ' + re.escape(name) + r'\b', out, re.M)
        start = mm.start()
        bo = body_brace(out, start)
        if bo < 0:
            continue
        be = match_brace(out, bo)
        spec = re.sub(r'ensures.*$', '', out[start:bo], flags=re.S)
        if not spec.rstrip().endswith("\n"):
            spec = spec.rstrip() + "\n"
        out = out[:start] + spec + strip_body_annotations(out[bo:be + 1]) + out[be + 1:]
    return out


def verus_kind(path, timeout=600):
    """PASS (already verifies) / MALFORMED (won't parse) / VERIF_FAIL (a legal task)."""
    try:
        p = subprocess.run([VERUS, path], capture_output=True, text=True, timeout=timeout)
    except subprocess.TimeoutExpired:
        return "TIMEOUT"
    o = p.stdout + p.stderr
    if "0 errors" in o:
        return "PASS"
    if re.search(r'error\[E|expected|unexpected|mismatched closing', o):
        return "MALFORMED"
    return "VERIF_FAIL"
