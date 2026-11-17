"""
Build and execution-verify L2/L3 "outer method" compositions from FEMPD verified
components, per Alvin's composition rule and the sub-call convention (each
component keeps its own class/scope -- no variable-name rewriting needed).

Composition design:
  - Each component becomes its own small static-method class (Comp0, Comp1, ...)
    so component method names never collide, regardless of what they were
    originally called.
  - The outer method's parameter list is the concatenation of every component's
    own parameters (so it's still a properly-typed, testable method via the same
    type-driven test generation used for L1).
  - Return convention (fixed, applied consistently to every composition, both
    sides of every pair): `Object[]` with one boxed slot per component's result,
    in call order. This is exactly parallel to a component-level `void` handling:
    void components are excluded (same policy as the L1 verifier) since they
    can't contribute a comparable value.

Reuses clone_verifier.py's signature parsing / type system / literal generation
directly (same generic Java-method verification logic used for L1).
"""
import os
import re
import subprocess
import sys

sys.path.insert(0, "../scripts")
import clone_verifier

WORK_DIR = "composition_work"
NUM_TESTS = 6
COMPILE_TIMEOUT = 30
RUN_TIMEOUT = 15


def parse_component(rtext):
    """Returns clone_verifier.parse_function()-style dict, or None if this
    method can't safely be used as a composition component (unsupported types,
    void return, parse failure)."""
    parsed = clone_verifier.parse_function("x", rtext)
    if parsed["status"] != "ok":
        return None
    if parsed["return_type"] == "void":
        return None
    return parsed


def build_composition_source(components, class_name="Outer"):
    """components: list of parsed dicts (from parse_component). Returns
    (java_source, outer_params) where outer_params is the concatenated
    [(type, unique_name), ...] list used to generate test literals."""
    comp_classes = []
    call_stmts = []
    outer_params = []

    for ci, comp in enumerate(components):
        comp_class_name = f"Comp{ci}"
        comp_classes.append(f"class {comp_class_name} {{\n{comp['method_src']}\n}}")

        arg_names = []
        for pi, (ptype, _pname) in enumerate(comp["params"]):
            uname = f"c{ci}_p{pi}"
            outer_params.append((ptype, uname))
            arg_names.append(uname)
        call = f"{comp_class_name}.{comp['name']}({', '.join(arg_names)})"
        # each component call gets its own try/catch so one component throwing
        # can never mask/skip a later component's call -- both are always
        # genuinely exercised on every test case, regardless of the other's
        # exception behavior.
        call_stmts.append(
            f"        try {{ results[{ci}] = {call}; }} "
            f'catch (Throwable e{ci}) {{ results[{ci}] = "__EXC__:" + e{ci}.getClass().getSimpleName(); }}'
        )

    header = ", ".join(f"{t} {n}" for t, n in outer_params)
    body = "\n".join(call_stmts)
    outer = f"""class {class_name} {{
    public static Object[] outer({header}) {{
        Object[] results = new Object[{len(components)}];
{body}
        return results;
    }}
{clone_verifier.FMT_HELPER}
}}"""

    src = f"{clone_verifier.COMMON_IMPORTS}\n" + "\n\n".join(comp_classes) + "\n\n" + outer
    return src, outer_params


def build_driver_source(java_src, outer_params, class_name="Outer"):
    """Wraps the composition class with a Driver main() that calls outer()
    NUM_TESTS times with generated literals and prints formatted results."""
    param_lits = [clone_verifier.gen_literals_for_param(ptype) for ptype, _ in outer_params]

    calls = []
    for t in range(NUM_TESTS):
        decls, arg_names = [], []
        for pi, (ptype, pname) in enumerate(outer_params):
            var = f"p{pi}"
            decls.append(f"                {ptype} {var} = {param_lits[pi][t]};")
            arg_names.append(var)
        call_args = ", ".join(arg_names)
        block = f"""            try {{
{chr(10).join(decls)}
                Object[] r = {class_name}.outer({call_args});
                System.out.println("R{t}:" + {class_name}.fmt(r));
            }} catch (Throwable e) {{
                System.out.println("R{t}:__EXC__:" + e.getClass().getSimpleName());
            }}"""
        calls.append(block)

    driver = f"""public class Driver {{
    public static void main(String[] args) {{
{chr(10).join(calls)}
    }}
}}
"""
    return java_src + "\n\n" + driver


def compile_and_run(full_src, tag):
    attempt_dir = os.path.join(WORK_DIR, tag)
    os.makedirs(attempt_dir, exist_ok=True)
    src_path = os.path.join(attempt_dir, "Driver.java")
    with open(src_path, "w") as f:
        f.write(full_src)

    try:
        compile_proc = subprocess.run(
            ["javac", "-d", attempt_dir, src_path],
            capture_output=True, text=True, timeout=COMPILE_TIMEOUT,
        )
    except subprocess.TimeoutExpired:
        return None, "compile_timeout"
    if compile_proc.returncode != 0:
        return None, f"compile_error:{compile_proc.stderr.strip()[:400]}"

    try:
        run_proc = subprocess.run(
            ["java", "-cp", attempt_dir, "Driver"],
            capture_output=True, text=True, timeout=RUN_TIMEOUT,
        )
    except subprocess.TimeoutExpired:
        return None, "run_timeout"

    lines = [ln for ln in run_proc.stdout.strip().splitlines() if ln.strip()]
    if len(lines) != NUM_TESTS:
        return None, f"incomplete_output:{len(lines)}/{NUM_TESTS}:{run_proc.stderr.strip()[:200]}"
    return lines, None


def build_and_run_side(components, tag):
    """components: list of parsed dicts. Returns (outputs, error)."""
    src, outer_params = build_composition_source(components)
    driver_src = build_driver_source(src, outer_params)
    return compile_and_run(driver_src, tag)


def verify_composition(components_side1, components_side2, tag):
    """Build+run both sides of a composed pair, compare. Returns dict with
    verdict VERIFIED/MISLABELED/UNVERIFIABLE + details."""
    out1, err1 = build_and_run_side(components_side1, f"{tag}_side1")
    out2, err2 = build_and_run_side(components_side2, f"{tag}_side2")
    if err1 or err2:
        return {"verdict": "UNVERIFIABLE", "error_side1": err1, "error_side2": err2}
    match = out1 == out2
    return {
        "verdict": "VERIFIED" if match else "MISLABELED",
        "outputs_side1": out1, "outputs_side2": out2,
    }
