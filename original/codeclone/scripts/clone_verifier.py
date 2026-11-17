"""
Execution-based verifier for BigCloneBench "positive" (labeled-clone) pairs.

Core idea: for each unique function, parse its signature, generate a battery of
type-driven test inputs, compile + run it standalone, and cache its output vector.
For each labeled pair, compare the two functions' cached output vectors:
  - both present and match on every test case -> VERIFIED
  - both present and diverge on any test case  -> MISLABELED
  - either function couldn't be parsed/compiled/run standalone -> UNVERIFIABLE

No LLM involved anywhere in this file -- signature parsing and test generation are
pure static analysis / type-driven heuristics, deterministic and free to run at scale.
"""
import os
import re
import subprocess

WORK_DIR = "verify_work"
NUM_TESTS = 6
COMPILE_TIMEOUT = 20
RUN_TIMEOUT = 8

# --- supported scalar types and their test-value literal candidates -----------------
SCALAR_LITERALS = {
    "int": ["0", "1", "-1", "42", "Integer.MAX_VALUE", "Integer.MIN_VALUE"],
    "Integer": ["0", "1", "-1", "42", "Integer.MAX_VALUE", "null"],
    "long": ["0L", "1L", "-1L", "123456789L", "Long.MAX_VALUE", "Long.MIN_VALUE"],
    "Long": ["0L", "1L", "-1L", "123456789L", "Long.MAX_VALUE", "null"],
    "double": ["0.0", "1.5", "-1.5", "3.14159", "Double.MAX_VALUE", "-0.0001"],
    "Double": ["0.0", "1.5", "-1.5", "3.14159", "Double.MAX_VALUE", "null"],
    "float": ["0.0f", "1.5f", "-1.5f", "3.14f", "Float.MAX_VALUE", "-0.0001f"],
    "Float": ["0.0f", "1.5f", "-1.5f", "3.14f", "Float.MAX_VALUE", "null"],
    "boolean": ["true", "false", "true", "false", "true", "false"],
    "Boolean": ["true", "false", "true", "false", "null", "true"],
    "char": ["'a'", "'Z'", "'0'", "' '", "'\\n'", "'9'"],
    "Character": ["'a'", "'Z'", "'0'", "' '", "null", "'9'"],
    "byte": ["(byte)0", "(byte)1", "(byte)-1", "(byte)127", "(byte)-128", "(byte)42"],
    "short": ["(short)0", "(short)1", "(short)-1", "(short)32000", "(short)-32000", "(short)7"],
    "String": [
        '""', '"hello"', '"a b c"', "null", '"12345"', '"The quick brown fox! @#$%"',
    ],
}

ARRAY_LITERALS = {
    "int": ["{}", "{0}", "{1, 2, 3}", "{-5, 10, 0, -3, 8}", "{5, 5, 2, 2, 1}", "null"],
    "long": ["{}", "{0L}", "{1L, 2L, 3L}", "{-5L, 10L, 0L}", "{5L, 5L, 2L}", "null"],
    "double": ["{}", "{0.0}", "{1.5, 2.5, 3.5}", "{-5.5, 10.1, 0.0}", "{5.0, 5.0, 2.0}", "null"],
    "float": ["{}", "{0.0f}", "{1.5f, 2.5f}", "{-5.5f, 10.1f}", "{5.0f, 2.0f}", "null"],
    "boolean": ["{}", "{true}", "{true, false}", "{false, false, true}", "{true, true}", "null"],
    "char": ["{}", "{'a'}", "{'a', 'b', 'c'}", "{'x', 'y'}", "{'0', '9'}", "null"],
    "byte": ["{}", "{(byte)0}", "{(byte)1, (byte)2}", "{(byte)-1, (byte)127}", "{(byte)5, (byte)5}", "null"],
    "short": ["{}", "{(short)0}", "{(short)1, (short)2}", "{(short)-1, (short)32000}", "{(short)5, (short)5}", "null"],
    "String": [
        "{}", '{""}', '{"a", "b"}', '{"hello", "world", ""}', '{"x", null, "y"}', "null",
    ],
}

SUPPORTED_SCALARS = set(SCALAR_LITERALS)
SUPPORTED_ARRAY_ELEMS = set(ARRAY_LITERALS)

MODIFIERS = {"public", "private", "protected", "static", "final", "synchronized",
             "native", "abstract", "strictfp", "@Override"}


def find_method_header(src):
    """Return (start_idx, header_text, brace_idx, method_name, return_type, params)
    for the first top-level method declaration, or None if not found/unsupported."""
    # crude but effective: look for `<ret> <name>(...)` immediately followed (after
    # optional throws clause) by `{`. Search all candidates, take the first that
    # parses cleanly.
    for m in re.finditer(r"([A-Za-z_][\w<>\[\],\s]*?)\s+([A-Za-z_]\w*)\s*\(", src):
        ret_type_raw, name = m.group(1), m.group(2)
        paren_start = m.end() - 1
        depth = 0
        i = paren_start
        for i in range(paren_start, len(src)):
            if src[i] == "(":
                depth += 1
            elif src[i] == ")":
                depth -= 1
                if depth == 0:
                    break
        else:
            continue
        params_src = src[paren_start + 1:i]
        rest = src[i + 1:]
        brace_m = re.match(r"\s*(?:throws\s+[\w.,\s]+)?\s*\{", rest)
        if not brace_m:
            continue
        brace_idx = i + 1 + brace_m.end() - 1

        ret_tokens = ret_type_raw.split()
        ret_tokens = [t for t in ret_tokens if t not in MODIFIERS]
        if not ret_tokens:
            continue
        ret_type = ret_tokens[-1]
        if name in ("if", "for", "while", "switch", "catch", "synchronized"):
            continue

        params = parse_params(params_src)
        if params is None:
            continue

        return {
            "name": name,
            "return_type": ret_type,
            "params": params,
            "body_brace_idx": brace_idx,
            "header_end": i + 1,
        }
    return None


def parse_params(params_src):
    params_src = params_src.strip()
    if not params_src:
        return []
    parts = []
    depth = 0
    current = ""
    for ch in params_src:
        if ch in "<(":
            depth += 1
        elif ch in ">)":
            depth -= 1
        if ch == "," and depth == 0:
            parts.append(current)
            current = ""
        else:
            current += ch
    parts.append(current)

    params = []
    for p in parts:
        p = p.strip()
        if not p or p == "final":
            continue
        p = re.sub(r"^final\s+", "", p)
        tokens = p.split()
        if len(tokens) < 2:
            return None
        pname = tokens[-1].lstrip("[]")
        ptype = " ".join(tokens[:-1])
        # handle `int[] a` vs `int a[]`
        trailing_brackets = ""
        while pname.startswith("[]"):
            trailing_brackets += "[]"
            pname = pname[2:]
        m = re.match(r"^([A-Za-z_]\w*)((?:\[\])*)$", tokens[-1])
        if m:
            pname = m.group(1)
            ptype = ptype + m.group(2)
        params.append((ptype.strip(), pname))
    return params


def classify_type(t):
    """Return ('scalar', base) or ('array', elem) or None if unsupported."""
    t = t.strip()
    if t.endswith("[]"):
        elem = t[:-2].strip()
        if elem in SUPPORTED_ARRAY_ELEMS:
            return ("array", elem)
        return None
    if t in SUPPORTED_SCALARS:
        return ("scalar", t)
    return None


def gen_literals_for_param(ptype):
    kind = classify_type(ptype)
    if kind is None:
        return None
    if kind[0] == "scalar":
        return SCALAR_LITERALS[kind[1]]
    else:
        return ARRAY_LITERALS[kind[1]]


def extract_method_source(func_src, header):
    """Slice out just the method (signature through matching closing brace)."""
    brace_idx = header["body_brace_idx"]
    depth = 0
    for i in range(brace_idx, len(func_src)):
        if func_src[i] == "{":
            depth += 1
        elif func_src[i] == "}":
            depth -= 1
            if depth == 0:
                return func_src[:i + 1]
    return None


def parse_function(idx, func_src):
    header = find_method_header(func_src)
    if header is None:
        return {"status": "unverifiable", "reason": "no_parsable_method"}

    param_literal_lists = []
    for ptype, pname in header["params"]:
        lits = gen_literals_for_param(ptype)
        if lits is None:
            return {"status": "unverifiable", "reason": f"unsupported_param_type:{ptype}"}
        param_literal_lists.append(lits)

    ret_type = header["return_type"]
    if ret_type == "void":
        # void functions can't feed an L2 composition (nothing to pass forward), and
        # comparing them against a non-void "clone" partner is an apples-to-oranges
        # return-value mismatch, not the semantic-divergence question we care about.
        return {"status": "unverifiable", "reason": "void_return_not_composable"}
    if classify_type(ret_type) is None:
        return {"status": "unverifiable", "reason": f"unsupported_return_type:{ret_type}"}

    method_src = extract_method_source(func_src, header)
    if method_src is None:
        return {"status": "unverifiable", "reason": "brace_mismatch"}

    # ensure method is accessible without instance-field context; force static if not
    if not re.match(r"\s*(?:public|private|protected)?\s*static\b", method_src):
        method_src = re.sub(r"^(\s*(?:public|private|protected)\s+)?", r"\1static ", method_src, count=1)
        if "static" not in method_src.split("{")[0]:
            method_src = "static " + method_src

    return {
        "status": "ok",
        "name": header["name"],
        "params": header["params"],
        "return_type": ret_type,
        "method_src": method_src,
    }


# --- driver generation / compile / run -----------------------------------------------

COMMON_IMPORTS = """import java.util.*;
import java.security.*;
import java.math.*;
import java.text.*;
import java.io.*;
import java.nio.charset.*;
"""

FMT_HELPER = """
    static String fmt(Object o) {
        if (o == null) return "null";
        if (o instanceof int[]) return Arrays.toString((int[]) o);
        if (o instanceof long[]) return Arrays.toString((long[]) o);
        if (o instanceof double[]) return Arrays.toString((double[]) o);
        if (o instanceof float[]) return Arrays.toString((float[]) o);
        if (o instanceof boolean[]) return Arrays.toString((boolean[]) o);
        if (o instanceof char[]) return Arrays.toString((char[]) o);
        if (o instanceof byte[]) return Arrays.toString((byte[]) o);
        if (o instanceof short[]) return Arrays.toString((short[]) o);
        if (o instanceof Object[]) return Arrays.deepToString((Object[]) o);
        return o.toString();
    }
"""


def build_driver_source(parsed, class_name="Driver"):
    params = parsed["params"]
    ret_type = parsed["return_type"]
    method_name = parsed["name"]

    param_lits = [gen_literals_for_param(ptype) for ptype, _ in params]

    calls = []
    for t in range(NUM_TESTS):
        decls = []
        arg_names = []
        for pi, (ptype, pname) in enumerate(params):
            var = f"p{pi}"
            lit = param_lits[pi][t]
            decls.append(f"                {ptype} {var} = {lit};")
            arg_names.append(var)
        call_args = ", ".join(arg_names)
        invoke = f"inst.{method_name}({call_args})"
        if ret_type == "void":
            call_stmt = f"                {invoke};\n                Object r = null;"
        else:
            boxed_ret = ret_type if not ret_type in (
                "int", "long", "double", "float", "boolean", "char", "byte", "short"
            ) else {
                "int": "Integer", "long": "Long", "double": "Double", "float": "Float",
                "boolean": "Boolean", "char": "Character", "byte": "Byte", "short": "Short",
            }[ret_type]
            call_stmt = f"                Object r = ({boxed_ret}) {invoke};" if ret_type in (
                "int", "long", "double", "float", "boolean", "char", "byte", "short"
            ) else f"                Object r = {invoke};"

        param_prints = "".join(
            f' + "|P{pi}:" + fmt(p{pi})' for pi in range(len(params))
        )
        block = f"""            try {{
{chr(10).join(decls)}
{call_stmt}
                System.out.println("R{t}:" + fmt(r){param_prints});
            }} catch (Throwable e) {{
                System.out.println("R{t}:__EXC__:" + e.getClass().getSimpleName());
            }}"""
        calls.append(block)

    body = "\n".join(calls)
    src = f"""{COMMON_IMPORTS}
public class {class_name} {{
{parsed['method_src']}
{FMT_HELPER}
    public static void main(String[] args) {{
        {class_name} inst = new {class_name}();
{body}
    }}
}}
"""
    return src


def compile_and_run_function(idx, parsed):
    attempt_dir = os.path.join(WORK_DIR, f"fn_{idx}")
    os.makedirs(attempt_dir, exist_ok=True)
    src = build_driver_source(parsed)
    src_path = os.path.join(attempt_dir, "Driver.java")
    with open(src_path, "w") as f:
        f.write(src)

    try:
        compile_proc = subprocess.run(
            ["javac", "-d", attempt_dir, src_path],
            capture_output=True, text=True, timeout=COMPILE_TIMEOUT,
        )
    except subprocess.TimeoutExpired:
        return {"status": "unverifiable", "reason": "compile_timeout"}
    if compile_proc.returncode != 0:
        return {"status": "unverifiable", "reason": f"compile_error:{compile_proc.stderr.strip()[:200]}"}

    try:
        run_proc = subprocess.run(
            ["java", "-cp", attempt_dir, "Driver"],
            capture_output=True, text=True, timeout=RUN_TIMEOUT,
        )
    except subprocess.TimeoutExpired:
        return {"status": "unverifiable", "reason": "run_timeout"}

    lines = [ln for ln in run_proc.stdout.strip().splitlines() if ln.strip()]
    if len(lines) != NUM_TESTS:
        return {"status": "unverifiable", "reason": f"incomplete_output:{len(lines)}/{NUM_TESTS}"}

    return {"status": "ok", "outputs": lines}


def verify_function(idx, func_src, cache):
    if idx in cache:
        return cache[idx]
    parsed = parse_function(idx, func_src)
    if parsed["status"] != "ok":
        cache[idx] = parsed
        return parsed
    result = compile_and_run_function(idx, parsed)
    cache[idx] = result
    return result


def compare_pair(idx_a, idx_b, funcs, cache):
    ra = verify_function(idx_a, funcs[idx_a], cache)
    rb = verify_function(idx_b, funcs[idx_b], cache)
    if ra["status"] != "ok" or rb["status"] != "ok":
        return {
            "verdict": "UNVERIFIABLE",
            "reason_a": ra.get("reason") if ra["status"] != "ok" else None,
            "reason_b": rb.get("reason") if rb["status"] != "ok" else None,
        }
    match = ra["outputs"] == rb["outputs"]
    return {
        "verdict": "VERIFIED" if match else "MISLABELED",
        "outputs_a": ra["outputs"],
        "outputs_b": rb["outputs"],
    }
